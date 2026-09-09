"""Publication guards for governed-provider evidence lineage."""
from __future__ import annotations

from typing import Any, Mapping

PROVIDER_ARCHITECTURE_VERSION = "ATLAS_GOVERNED_PROVIDERS_V2"
EVIDENCE_SNAPSHOT_VERSION = "ATLAS_EVIDENCE_SNAPSHOT_V2"
CACHE_GENERATION_VERSION = "POST_YAHOO_MIGRATION_V2"
DISALLOWED_PROVIDER_TOKENS = ("YAHOO", "YFINANCE", "QUERY1.FINANCE.YAHOO", "QUERY2.FINANCE.YAHOO")
FMP_PROVIDER_TOKENS = ("FMP", "FINANCIAL MODELING PREP")
FMP_EARNINGS_NAMESPACE = "earnings_evidence"


def is_disallowed_provider(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return any(token in text for token in DISALLOWED_PROVIDER_TOKENS)


def disallowed_lineage_paths(payload: Any, path: str = "$") -> list[str]:
    """Return paths containing forbidden provider provenance, not incidental prose."""
    findings: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            child = f"{path}.{key}"
            key_upper = str(key).upper()
            lineage_key = any(part in key_upper for part in ("PROVIDER", "SOURCE", "LINEAGE", "AUTHORITY"))
            if lineage_key and not isinstance(value, (Mapping, list, tuple)) and is_disallowed_provider(value):
                findings.append(child)
            findings.extend(disallowed_lineage_paths(value, child))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            findings.extend(disallowed_lineage_paths(value, f"{path}[{index}]"))
    return findings


def has_disallowed_lineage(payload: Any) -> bool:
    return bool(disallowed_lineage_paths(payload))


def _is_fmp(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return any(token in text for token in FMP_PROVIDER_TOKENS)


def fmp_quantitative_lineage_paths(payload: Any, path: str = "$") -> list[str]:
    """Reject FMP provenance everywhere except the earnings-evidence namespace."""
    if FMP_EARNINGS_NAMESPACE in path.lower().split("."):
        return []
    findings: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            child = f"{path}.{key}"
            if str(key).lower() == FMP_EARNINGS_NAMESPACE:
                continue
            key_upper = str(key).upper()
            lineage_key = any(part in key_upper for part in ("PROVIDER", "SOURCE", "LINEAGE", "AUTHORITY"))
            if lineage_key and not isinstance(value, (Mapping, list, tuple)) and _is_fmp(value):
                findings.append(child)
            findings.extend(fmp_quantitative_lineage_paths(value, child))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            findings.extend(fmp_quantitative_lineage_paths(value, f"{path}[{index}]"))
    return findings


def fmp_earnings_context_reference_count(payload: Any, path: str = "$") -> int:
    if isinstance(payload, Mapping):
        total = 0
        for key, value in payload.items():
            child = f"{path}.{key}"
            if str(key).lower() == FMP_EARNINGS_NAMESPACE:
                total += str(value).upper().count("FMP")
            else:
                total += fmp_earnings_context_reference_count(value, child)
        return total
    if isinstance(payload, (list, tuple)):
        return sum(fmp_earnings_context_reference_count(value, f"{path}[{index}]") for index, value in enumerate(payload))
    return 0


def provider_lineage_counters(payload: Any) -> dict[str, int]:
    yahoo = len(disallowed_lineage_paths(payload))
    fmp_quant = len(fmp_quantitative_lineage_paths(payload))
    return {
        "PRODUCTION_ACTIVE_YAHOO_DECISION_DEPENDENCY_COUNT": yahoo,
        "PRODUCTION_ACTIVE_FMP_QUANTITATIVE_DEPENDENCY_COUNT": fmp_quant,
        "PUBLISHED_YAHOO_LINEAGE_COUNT": yahoo,
        "PUBLISHED_FMP_QUANTITATIVE_LINEAGE_COUNT": fmp_quant,
        "FMP_EARNINGS_CONTEXT_REFERENCE_COUNT": fmp_earnings_context_reference_count(payload),
    }


__all__ = [
    "CACHE_GENERATION_VERSION", "DISALLOWED_PROVIDER_TOKENS", "EVIDENCE_SNAPSHOT_VERSION",
    "PROVIDER_ARCHITECTURE_VERSION", "disallowed_lineage_paths", "has_disallowed_lineage",
    "is_disallowed_provider", "fmp_quantitative_lineage_paths",
    "fmp_earnings_context_reference_count", "provider_lineage_counters",
]
