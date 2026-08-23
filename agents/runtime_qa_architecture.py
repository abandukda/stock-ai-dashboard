"""Architecture-aware ATLAS product certification primitives.

The module is intentionally read-only.  It inventories governance and canonical
Research metadata, produces sanitized digests, and reconciles those contracts
with browser-visible QA markers without acquiring provider data.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from engines.research_context import (
    CORPORATE_ONLY_FAMILIES, EVIDENCE_FAMILIES, RESEARCH_CONTEXT_VERSION,
    build_production_decision, load_production_row,
)
from services.provider_ownership import (
    EXPLICIT_RESEARCH_FMP_PRIMARY, PROVIDER_OWNERSHIP_VERSION,
)
from services.yahoo_dependency_registry import (
    EXPECTED_YAHOO_DEPENDENCY_COUNT_V1, YAHOO_DEPENDENCY_REGISTRY_VERSION,
    YAHOO_DEPENDENCIES, yahoo_migration_metrics,
)


RUNTIME_QA_FRAMEWORK_VERSION: Final = "ATLAS-PRODUCT-CERTIFICATION-QA.1"
CERTIFICATION_ARTIFACT: Final = "atlas_product_certification.json"

CERTIFICATION_CLASSIFICATIONS: Final = (
    "PASS", "PASS_WITH_EVIDENCE_LIMITATIONS", "PRODUCT_DEFECT",
    "DATA_PIPELINE_DEFECT", "QA_DEFECT", "PROVIDER_LIMITATION",
    "ARCHITECTURE_DRIFT",
)
CERTIFICATION_SEVERITIES: Final = ("P0", "P1", "P2", "P3")
FAMILY_RECONCILIATIONS: Final = (
    "AVAILABLE_BACKEND_AND_DISPLAYED", "AVAILABLE_BACKEND_MISSING_UI",
    "DISPLAYED_WITHOUT_CANONICAL_EVIDENCE", "CORRECTLY_UNAVAILABLE",
    "STALE_OR_FRESHNESS_MISMATCH",
)

PROTECTED_DECISION_FIELDS: Final = (
    "recommendation", "opportunity", "confidence", "buy_now", "ranking",
    "atlas_fair_value", "decision_expected_return", "entry_low", "entry_high",
    "decision_target", "trade_target_1", "trade_target_2", "stop",
    "position_sizing",
)

ROLLOUT_STATE: Final = {
    "active": (
        "FMP_EXPLICIT_RESEARCH", "RESEARCH_CONTEXT_V1",
        "FAMILY_EVIDENCE_CACHE", "BOUNDED_ANALYST_ACTION_HISTORY",
    ),
    "inactive": (
        "TOP_ANALYST_ACTIONS_CUSTOMER_UI", "TRANSCRIPT_INTELLIGENCE",
        "MANAGEMENT_GUIDANCE", "ATLAS_RESEARCH_SYNTHESIS_V2",
        "FULL_FMP_ETF_RESEARCH",
    ),
}

CORE_PAGE_CONTRACTS: Final = {
    "Home": {
        "backend": "persisted production scan + Home discovery",
        "critical": ("recommendation", "confidence", "atlas_fair_value"),
        "freshness": "latest production scan; market tape separately labeled",
    },
    "Today's Opportunities": {
        "backend": "persisted ranked production scan",
        "critical": ("recommendation", "opportunity", "confidence", "atlas_fair_value"),
        "freshness": "latest production scan",
    },
    "Research Any Ticker": {
        "backend": "RESEARCH_CONTEXT_V1 + immutable production decision",
        "critical": ("production_decision", "evidence_families", "evidence_registry"),
        "freshness": "family-level fetched/cache state",
    },
    "Earnings Intelligence": {
        "backend": "EARNINGS_INTELLIGENCE_V1",
        "critical": ("earnings_history", "next_earnings"),
        "freshness": "reported/observation dates",
    },
    "ETFs": {
        "backend": "persisted ETF scan; FIRST.7 ETF Research inactive",
        "critical": ("security_type", "not_applicable_semantics"),
        "freshness": "latest production scan",
    },
    "Watchlist Intelligence": {
        "backend": "customer watchlist + persisted production scan",
        "critical": ("ticker", "recommendation"),
        "freshness": "latest production scan",
    },
    "Ask AI": {
        "backend": "Ask Atlas grounded report and canonical Research context",
        "critical": ("ticker", "evidence_used", "evidence_missing"),
        "freshness": "same canonical context as Research",
    },
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def checked_out_sha(root: str | Path = ".") -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(root), check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return "UNKNOWN"


def architecture_versions(root: str | Path = ".") -> dict[str, Any]:
    return {
        "source_commit": checked_out_sha(root),
        "provider_registry_version": PROVIDER_OWNERSHIP_VERSION,
        "yahoo_registry_version": YAHOO_DEPENDENCY_REGISTRY_VERSION,
        "research_context_version": RESEARCH_CONTEXT_VERSION,
        "runtime_qa_framework_version": RUNTIME_QA_FRAMEWORK_VERSION,
    }


def architecture_preflight(root: str | Path = ".") -> dict[str, Any]:
    metrics = yahoo_migration_metrics()
    failures: list[str] = []
    if PROVIDER_OWNERSHIP_VERSION != "PROVIDER_OWNERSHIP_V1":
        failures.append("PROVIDER_REGISTRY_VERSION_DRIFT")
    if YAHOO_DEPENDENCY_REGISTRY_VERSION != "YAHOO_DEPENDENCY_REGISTRY_V1":
        failures.append("YAHOO_REGISTRY_VERSION_DRIFT")
    if RESEARCH_CONTEXT_VERSION != "RESEARCH_CONTEXT_V1":
        failures.append("RESEARCH_CONTEXT_VERSION_DRIFT")
    if len(YAHOO_DEPENDENCIES) != EXPECTED_YAHOO_DEPENDENCY_COUNT_V1:
        failures.append("YAHOO_DEPENDENCY_COUNT_DRIFT")
    if metrics["active_yahoo_dependencies"] > 8:
        failures.append("ACTIVE_YAHOO_DEPENDENCY_INCREASE")
    if not EXPLICIT_RESEARCH_FMP_PRIMARY:
        failures.append("FMP_EXPLICIT_RESEARCH_AUTHORITY_MISSING")
    return {
        "status": "PASS" if not failures else "ARCHITECTURE_DRIFT",
        "severity": None if not failures else "P1",
        "versions": architecture_versions(root),
        "yahoo_metrics": metrics,
        "explicit_fmp_family_count": len(EXPLICIT_RESEARCH_FMP_PRIMARY),
        "rollout_state": ROLLOUT_STATE,
        "failures": failures,
    }


def protected_decision_snapshot(decision: Mapping[str, Any] | None) -> dict[str, Any]:
    value = decision or {}
    snapshot = {key: value.get(key) for key in PROTECTED_DECISION_FIELDS}
    snapshot["semantic_status"] = value.get("semantic_status", "DATA_UNAVAILABLE")
    return snapshot


def protected_decision_digest(decision: Mapping[str, Any] | None) -> str:
    return stable_digest(protected_decision_snapshot(decision))


def production_decision_for_ticker(ticker: str, root: str | Path = ".") -> dict[str, Any]:
    row = load_production_row(ticker, Path(root) / "market_full_scan.json")
    return dict(build_production_decision(row))


def certify_immutable_decision(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    left, right = protected_decision_snapshot(before), protected_decision_snapshot(after)
    changed = [key for key in left if left.get(key) != right.get(key)]
    return {
        "classification": "PASS" if not changed else "PRODUCT_DEFECT",
        "severity": None if not changed else "P0",
        "changed_fields": changed,
        "before_digest": stable_digest(left),
        "after_digest": stable_digest(right),
    }


def _family_summary(family: str, envelope: Mapping[str, Any]) -> dict[str, Any]:
    ids = list(envelope.get("evidence_ids") or [])
    return {
        "family": family,
        "semantic_status": envelope.get("semantic_status") or "DATA_UNAVAILABLE",
        "provider": envelope.get("provider"),
        "endpoint_family": envelope.get("endpoint_family"),
        "cache_status": envelope.get("cache_status") or "TEMPORARILY_UNAVAILABLE",
        "fetched_at": envelope.get("fetched_at"),
        "observation_date": envelope.get("observation_date"),
        "reporting_date": envelope.get("reporting_date"),
        "filing_date": envelope.get("filing_date"),
        "age_seconds": envelope.get("age_seconds"),
        "evidence_id_digest": stable_digest(ids),
        "evidence_count": len(ids),
        "limitations": list(envelope.get("limitations") or []),
    }


def sanitize_research_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    value = context or {}
    decision = value.get("production_decision")
    families = value.get("evidence_families")
    registry = value.get("evidence_registry")
    family_summaries = {
        family: _family_summary(family, envelope if isinstance(envelope, Mapping) else {})
        for family, envelope in (families.items() if isinstance(families, Mapping) else [])
        if family in EVIDENCE_FAMILIES
    }
    actions_envelope = (families or {}).get("analyst_actions") if isinstance(families, Mapping) else {}
    actions = ((actions_envelope.get("data") or {}).get("actions") or []) if isinstance(actions_envelope, Mapping) else []
    action_required = {"firm", "action", "current_rating", "previous_rating", "date", "provider", "source_family"}
    action_ready = bool(len(actions) <= 25 and all(isinstance(row, Mapping) and action_required.issubset(row) for row in actions))
    return {
        "context_version": value.get("version"),
        "ticker": str(value.get("ticker") or "").upper(),
        "security_type": value.get("security_type"),
        "generated_at": value.get("generated_at"),
        "production_decision_status": (decision or {}).get("semantic_status") if isinstance(decision, Mapping) else "DATA_UNAVAILABLE",
        "production_decision_digest": protected_decision_digest(decision if isinstance(decision, Mapping) else {}),
        "evidence_families": family_summaries,
        "evidence_registry_digest": stable_digest(registry if isinstance(registry, Mapping) else {}),
        "limitations": list(value.get("limitations") or []),
        "analyst_action_readiness": {
            "count": len(actions), "bounded": len(actions) <= 25,
            "required_fields_present": action_ready,
            "customer_top5_active": False,
        },
    }


def encode_context_summary(context: Mapping[str, Any] | None) -> str:
    return base64.urlsafe_b64encode(_canonical_json(sanitize_research_context(context))).decode()


def decode_context_summary(encoded: str) -> dict[str, Any]:
    try:
        value = json.loads(base64.urlsafe_b64decode(str(encoded).encode()).decode())
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def certify_freshness(canonical: Mapping[str, Any], rendered: Mapping[str, Any]) -> dict[str, Any]:
    cache = str(canonical.get("cache_status") or "")
    label = str(rendered.get("freshness") or rendered.get("freshness_label") or "")
    fetched_at = canonical.get("fetched_at")
    rendered_at = rendered.get("fetched_at")
    mismatch = bool(
        (cache == "STALE_FALLBACK" and label.upper() in {"FRESH", "LIVE"})
        or (cache in {"FRESH_CACHE", "STALE_FALLBACK"} and "LIVE" in label.upper())
        or (fetched_at and rendered_at and str(fetched_at) != str(rendered_at))
    )
    return {
        "result": "STALE_OR_FRESHNESS_MISMATCH" if mismatch else "PASS",
        "canonical_cache_status": cache,
        "canonical_fetched_at": fetched_at,
        "rendered_freshness": label,
        "rendered_fetched_at": rendered_at,
    }


def reconcile_family(canonical: Mapping[str, Any], rendered: Mapping[str, Any] | None) -> dict[str, Any]:
    rendered = rendered or {}
    available = canonical.get("semantic_status") == "AVAILABLE"
    displayed = str(rendered.get("displayed") or "").lower() in {"1", "true", "yes"}
    freshness = certify_freshness(canonical, rendered)
    if freshness["result"] != "PASS":
        result = "STALE_OR_FRESHNESS_MISMATCH"
    elif available and displayed:
        result = "AVAILABLE_BACKEND_AND_DISPLAYED"
    elif available:
        result = "AVAILABLE_BACKEND_MISSING_UI"
    elif displayed:
        result = "DISPLAYED_WITHOUT_CANONICAL_EVIDENCE"
    else:
        result = "CORRECTLY_UNAVAILABLE"
    return {"result": result, "freshness": freshness}


def certify_research_context(
    context: Mapping[str, Any] | None,
    rendered_families: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    summary = dict(context or {}) if isinstance(context, Mapping) and "context_version" in context else sanitize_research_context(context)
    failures = []
    if summary["context_version"] != RESEARCH_CONTEXT_VERSION:
        failures.append("CONTEXT_VERSION")
    if not summary["ticker"]:
        failures.append("TICKER")
    if set(summary["evidence_families"]) != set(EVIDENCE_FAMILIES):
        failures.append("EVIDENCE_FAMILY_CONTRACT")
    reconciliations = {
        family: reconcile_family(canonical, (rendered_families or {}).get(family))
        for family, canonical in summary["evidence_families"].items()
    }
    mismatch = [family for family, item in reconciliations.items() if item["result"] in {
        "DISPLAYED_WITHOUT_CANONICAL_EVIDENCE", "STALE_OR_FRESHNESS_MISMATCH",
    }]
    missing_ui = [family for family, item in reconciliations.items() if item["result"] == "AVAILABLE_BACKEND_MISSING_UI"]
    classification = "ARCHITECTURE_DRIFT" if failures else "PRODUCT_DEFECT" if mismatch else "PASS_WITH_EVIDENCE_LIMITATIONS" if missing_ui else "PASS"
    return {
        "classification": classification,
        "severity": "P1" if failures else "P2" if mismatch or missing_ui else None,
        "canonical_summary": summary,
        "family_reconciliation": reconciliations,
        "failures": failures,
    }


def certify_missing_production_ticker(context: Mapping[str, Any]) -> dict[str, Any]:
    decision = context.get("production_decision") if isinstance(context, Mapping) else {}
    snapshot = protected_decision_snapshot(decision if isinstance(decision, Mapping) else {})
    forbidden = [key for key in PROTECTED_DECISION_FIELDS if snapshot.get(key) is not None]
    valid = snapshot["semantic_status"] == "DATA_UNAVAILABLE" and not forbidden
    return {
        "classification": "PASS_WITH_EVIDENCE_LIMITATIONS" if valid else "PRODUCT_DEFECT",
        "severity": None if valid else "P0",
        "forbidden_decision_fields": forbidden,
    }


def certify_etf_context(context: Mapping[str, Any]) -> dict[str, Any]:
    families = context.get("evidence_families") if isinstance(context, Mapping) else {}
    wrong = [family for family in CORPORATE_ONLY_FAMILIES if (families or {}).get(family, {}).get("semantic_status") != "NOT_APPLICABLE"]
    valid = context.get("security_type") == "ETF" and not wrong
    return {
        "classification": "PASS_WITH_EVIDENCE_LIMITATIONS" if valid else "PRODUCT_DEFECT",
        "severity": None if valid else "P0",
        "incorrect_corporate_families": wrong,
    }


def certify_ask_context(research_summary: Mapping[str, Any], ask_metadata: Mapping[str, Any]) -> dict[str, Any]:
    wrong_ticker = str(research_summary.get("ticker") or "").upper() != str(ask_metadata.get("ticker") or "").upper()
    wrong_digest = bool(ask_metadata.get("context_digest") and ask_metadata.get("context_digest") != stable_digest(research_summary))
    valid = not wrong_ticker and not wrong_digest
    return {
        "classification": "PASS" if valid else "PRODUCT_DEFECT",
        "severity": None if valid else "P0",
        "wrong_ticker": wrong_ticker,
        "wrong_context_digest": wrong_digest,
    }


def certify_valuation_separation(
    production_decision: Mapping[str, Any], rendered: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Certify that customer valuation labels reconcile to their canonical families."""
    expected = {
        "atlas_fair_value": production_decision.get("atlas_fair_value"),
        "wall_street_target": production_decision.get("analyst_consensus"),
    }
    failures: list[str] = []
    for role, canonical in expected.items():
        marker = rendered.get(role) or {}
        displayed = str(marker.get("displayed") or "").lower() in {"1", "true", "yes"}
        digest = marker.get("value_digest")
        if canonical is None and displayed:
            failures.append(f"{role.upper()}_DISPLAYED_WITHOUT_CANONICAL_VALUE")
        elif canonical is not None and displayed and digest != stable_digest(canonical):
            failures.append(f"{role.upper()}_VALUE_MISMATCH")
    atlas = rendered.get("atlas_fair_value") or {}
    if str(atlas.get("source_family") or "") not in {"", "production_decision.atlas_fair_value"}:
        failures.append("ATLAS_FAIR_VALUE_CROSS_LABELED")
    return {
        "classification": "PASS" if not failures else "PRODUCT_DEFECT",
        "severity": None if not failures else "P0",
        "failures": failures,
    }


def certify_sec_authority(canonical: Mapping[str, Any], rendered: Mapping[str, Any]) -> dict[str, Any]:
    displayed = str(rendered.get("displayed") or "").lower() in {"1", "true", "yes"}
    provider = str(canonical.get("provider") or "").upper()
    invalid = displayed and canonical.get("semantic_status") == "AVAILABLE" and provider != "SEC"
    return {
        "classification": "PRODUCT_DEFECT" if invalid else "PASS",
        "severity": "P0" if invalid else None,
        "canonical_provider": provider or None,
    }


def certify_analyst_action_readiness(context: Mapping[str, Any]) -> dict[str, Any]:
    envelope = ((context.get("evidence_families") or {}).get("analyst_actions") or {})
    actions = ((envelope.get("data") or {}).get("actions") or []) if isinstance(envelope, Mapping) else []
    required = {"firm", "action", "current_rating", "previous_rating", "date", "provider", "source_family"}
    valid_rows = all(isinstance(row, Mapping) and required.issubset(row) for row in actions)
    ordered = list(actions) == sorted(actions, key=lambda row: (str(row.get("date") or ""), str(row.get("firm") or ""), str(row.get("action") or "")), reverse=True)
    valid = len(actions) <= 25 and valid_rows and ordered
    return {
        "classification": "PASS" if valid else "DATA_PIPELINE_DEFECT",
        "severity": None if valid else "P2",
        "action_count": len(actions), "bounded": len(actions) <= 25,
        "deterministic_newest_first": ordered, "required_fields_present": valid_rows,
        "customer_top5_active": False,
    }


def _scan_rows(path: Path) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    for key in ("rows", "results", "stocks"):
        rows = payload.get(key) if isinstance(payload, Mapping) else None
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    return []


def research_ticker_matrix(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    full = _scan_rows(root_path / "market_full_scan.json")
    symbols = [str(row.get("ticker") or row.get("Ticker") or "").upper() for row in full]
    top15 = next((symbol for symbol in symbols[:15] if symbol not in {"NVDA", "AAPL"}), "")
    preferred = ("MSFT", "AMZN", "GOOGL", "META", "TSLA", "JPM", "COST", "ORCL")
    missing = next((symbol for symbol in preferred if symbol not in set(symbols)), "")
    if not missing:
        universe = _scan_rows(root_path / "total_market_universe.json")
        missing = next((str(row.get("ticker") or row.get("symbol") or "").upper() for row in universe if re.fullmatch(r"[A-Z]{1,5}", str(row.get("ticker") or row.get("symbol") or "").upper()) and str(row.get("ticker") or row.get("symbol") or "").upper() not in set(symbols)), "")
    tickers = list(dict.fromkeys(filter(None, ("NVDA", "AAPL", top15, missing, "SPY", "INVALID123"))))
    return {"tickers": tickers, "dynamic_top15": top15, "missing_production": missing}


def certification_record(**values: Any) -> dict[str, Any]:
    record = {
        "page": values.get("page"), "journey": values.get("journey"),
        "ticker": values.get("ticker"),
        "canonical_reconciliation": values.get("canonical_reconciliation") or {},
        "freshness_result": values.get("freshness_result") or {},
        "provenance_result": values.get("provenance_result") or {},
        "cross_page_consistency": values.get("cross_page_consistency") or {},
        "screenshot_paths": list(values.get("screenshot_paths") or []),
        "classification": values.get("classification") or "QA_DEFECT",
        "severity": values.get("severity"),
    }
    if record["classification"] not in CERTIFICATION_CLASSIFICATIONS:
        raise ValueError("invalid certification classification")
    if record["severity"] is not None and record["severity"] not in CERTIFICATION_SEVERITIES:
        raise ValueError("invalid certification severity")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--output", default="audit_results/architecture_preflight.json")
    args = parser.parse_args()
    result = architecture_preflight(".")
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": result["status"], "versions": result["versions"]}, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()


__all__ = [
    "CERTIFICATION_ARTIFACT", "CERTIFICATION_CLASSIFICATIONS",
    "CERTIFICATION_SEVERITIES", "CORE_PAGE_CONTRACTS", "FAMILY_RECONCILIATIONS",
    "PROTECTED_DECISION_FIELDS", "ROLLOUT_STATE", "RUNTIME_QA_FRAMEWORK_VERSION",
    "architecture_preflight", "architecture_versions", "certification_record",
    "certify_analyst_action_readiness", "certify_ask_context", "certify_etf_context",
    "certify_freshness", "certify_immutable_decision",
    "certify_missing_production_ticker", "certify_research_context",
    "certify_sec_authority", "certify_valuation_separation",
    "decode_context_summary", "encode_context_summary", "protected_decision_digest",
    "protected_decision_snapshot", "production_decision_for_ticker", "reconcile_family", "research_ticker_matrix",
    "sanitize_research_context", "stable_digest",
]
