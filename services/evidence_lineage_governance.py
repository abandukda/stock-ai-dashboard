"""Publication guards for governed-provider evidence lineage."""
from __future__ import annotations

from typing import Any, Mapping

PROVIDER_ARCHITECTURE_VERSION = "ATLAS_GOVERNED_PROVIDERS_V2"
EVIDENCE_SNAPSHOT_VERSION = "ATLAS_EVIDENCE_SNAPSHOT_V2"
CACHE_GENERATION_VERSION = "POST_YAHOO_MIGRATION_V2"
DISALLOWED_PROVIDER_TOKENS = ("YAHOO", "YFINANCE", "QUERY1.FINANCE.YAHOO", "QUERY2.FINANCE.YAHOO")


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


__all__ = [
    "CACHE_GENERATION_VERSION", "DISALLOWED_PROVIDER_TOKENS", "EVIDENCE_SNAPSHOT_VERSION",
    "PROVIDER_ARCHITECTURE_VERSION", "disallowed_lineage_paths", "has_disallowed_lineage",
    "is_disallowed_provider",
]
