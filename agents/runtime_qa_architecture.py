"""Architecture-aware ATLAS product certification primitives.

The module is intentionally read-only.  It inventories governance and canonical
Research metadata, produces sanitized digests, and reconciles those contracts
with browser-visible QA markers without acquiring provider data.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import importlib
import importlib.util
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
from agents.runtime_qa_interactions import INTERACTION_REGISTRY_VERSION
from agents.product_hardening_certification import PRODUCT_HARDENING_VERSION


RUNTIME_QA_FRAMEWORK_VERSION: Final = "ATLAS-PRODUCT-CERTIFICATION-QA.1"
CERTIFICATION_ARTIFACT: Final = "atlas_product_certification.json"

DEPLOYMENT_PARITY_GATE_COMMAND: Final = (
    "python3 -m pytest -q tests/test_atlas_deployment_parity_gate.py"
)

ACTIVE_PAGE_RUNTIME_SYMBOLS: Final = {
    "Home": ("app", "v810_render_dynamic_home"),
    "Today's Opportunities": ("app", "v810_render_today_page"),
    "Volume Intelligence": ("ui.daily_opportunities", "render_volume_momentum"),
    "Atlas Core Holdings": ("app", "v810_render_core_page"),
    "Research Any Ticker": ("app", "render_research_any_ticker"),
    "Earnings Intelligence": ("app", "render_v73_earnings_page"),
    "Full Ranked Scan": ("app", "render_v56_ranked_table"),
    "Portfolio Intelligence": ("app", "render_v505_portfolio_analyzer"),
    "Watchlist Intelligence": ("app", "render_v506_watchlist_intelligence"),
    "Recovery": ("app", "render_v56_ranked_table"),
    "ETFs": ("app", "render_v56_ranked_table"),
    "Political Intelligence": ("app", "render_v58_political_intelligence"),
    "Ask AI": ("app", "render_chat_helper"),
    "Developer Center": ("ui.developer_center", "render_developer_center"),
}

RESEARCH_BOOTSTRAP_MODULES: Final = (
    "services.research_render_diagnostics",
    "services.session_stability",
    "engines.research_engine",
    "engines.research_context",
    "engines.live_research_engine",
    "engines.atlas_research_builder_v2",
    "engines.analyst_intelligence",
    "engines.earnings_intelligence",
    "engines.ask_atlas_engine",
    "engines.political_evidence",
    "ui.research_report_v2",
    "ui.research_report_v104",
    "ui.home_v104",
    "ui.institutional_experience",
)

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
    "Political Intelligence": {
        "backend": "congressional transaction disclosures",
        "critical": ("member", "ticker", "transaction_type", "transaction_date", "disclosure_date", "evidence_id"),
        "freshness": "transaction and disclosure dates remain distinct",
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
        "interaction_registry_version": INTERACTION_REGISTRY_VERSION,
        "product_hardening_version": PRODUCT_HARDENING_VERSION,
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
    ordered = (("fixed_equity", "NVDA"), ("fixed_equity", "AAPL"),
               ("dynamic_top15", top15), ("missing_production", missing),
               ("etf", "SPY"), ("invalid", "INVALID123"))
    entries = []
    seen: set[str] = set()
    rows_by_ticker = {str(row.get("ticker") or row.get("Ticker") or "").upper(): row for row in full}
    for role, ticker in ordered:
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        row = rows_by_ticker.get(ticker) or {}
        production_member = ticker in rows_by_ticker
        security_type = "ETF" if ticker == "SPY" else str(row.get("security_type") or row.get("Security Type") or "EQUITY")
        entries.append({
            "role": role, "ticker": ticker,
            "production_member": production_member,
            "security_type": security_type,
            "expected_production_decision_status": "AVAILABLE" if production_member else "DATA_UNAVAILABLE",
        })
    return {
        "tickers": [entry["ticker"] for entry in entries], "entries": entries,
        "dynamic_top15": top15, "missing_production": missing,
    }


def journey_completeness(expected: Mapping[str, int], completed: Mapping[str, Any], *, engine_error: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for family, count in expected.items():
        observed = completed.get(family, 0)
        if isinstance(observed, Mapping):
            attempted = max(0, int(observed.get("attempted", 0)))
            done = max(0, int(observed.get("completed", 0)))
            failed = max(0, int(observed.get("failed", attempted - done)))
        else:
            done = max(0, int(observed))
            attempted, failed = done, 0
        required = max(0, int(count))
        result[family] = {
            "expected": required, "attempted": attempted, "completed": done,
            "failed": failed, "skipped": max(0, required - attempted),
        }
    complete = not engine_error and all(item["skipped"] == 0 and item["failed"] == 0 and item["completed"] == item["expected"] for item in result.values())
    return {"status": "PASS" if complete else "INCOMPLETE", "families": result, "engine_error_category": engine_error or None}


def certification_integrity(
    *, authenticated: bool, page_count: int, journey_state: Mapping[str, Any],
    ticker_matrix: Mapping[str, Any], cross_page: Mapping[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    if not authenticated or page_count < 3:
        failures.append("AUTHENTICATED_PAGE_AUDIT_INCOMPLETE")
    if not ticker_matrix.get("entries"):
        failures.append("TICKER_MATRIX_EMPTY")
    if journey_state.get("status") != "PASS":
        failures.append("REQUIRED_JOURNEYS_INCOMPLETE")
    if not cross_page or cross_page.get("status") in {None, "NOT_EXECUTED"}:
        failures.append("CROSS_PAGE_NOT_EXECUTED")
    return {
        "audit_valid": not failures,
        "classification": "PASS" if not failures else "QA_DEFECT",
        "severity": None if not failures else "P1",
        "failures": failures,
    }


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
        "navigation_status": values.get("navigation_status") or "NOT_EXECUTED",
        "semantic_status": values.get("semantic_status") or "NOT_EXECUTED",
        "reconciliation_status": values.get("reconciliation_status") or "NOT_EXECUTED",
        "responsive_status": values.get("responsive_status") or "NOT_APPLICABLE",
    }
    if record["classification"] not in CERTIFICATION_CLASSIFICATIONS:
        raise ValueError("invalid certification classification")
    if record["severity"] is not None and record["severity"] not in CERTIFICATION_SEVERITIES:
        raise ValueError("invalid certification severity")
    if record["reconciliation_status"] == "PASS" and not record["canonical_reconciliation"]:
        record["reconciliation_status"] = "NOT_EXECUTED"
    required_dimensions = (
        record["navigation_status"], record["semantic_status"],
        record["reconciliation_status"], record["responsive_status"],
    )
    if record["classification"] == "PASS" and any(value in {"FAIL", "NOT_EXECUTED"} for value in required_dimensions):
        record["classification"], record["severity"] = "QA_DEFECT", "P1"
    return record


def _module_source_path(module_name: str, root: Path) -> Path | None:
    candidate = root.joinpath(*module_name.split(".")).with_suffix(".py")
    if candidate.is_file():
        return candidate
    package = root.joinpath(*module_name.split("."), "__init__.py")
    return package if package.is_file() else None


def _research_local_import_graph(root: Path) -> tuple[set[str], list[dict[str, Any]]]:
    """Walk local imports and verify every imported local symbol exists."""
    pending = list(RESEARCH_BOOTSTRAP_MODULES)
    visited: set[str] = set()
    failures: list[dict[str, Any]] = []
    while pending:
        module_name = pending.pop(0)
        if module_name in visited:
            continue
        visited.add(module_name)
        source = _module_source_path(module_name, root)
        if source is None:
            failures.append({"module": module_name, "reason": "LOCAL_MODULE_MISSING"})
            continue
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            imported_module = importlib.import_module(module_name)
        except Exception as exc:
            failures.append({"module": module_name, "reason": type(exc).__name__})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                local_source = _module_source_path(node.module, root)
                if local_source is None:
                    continue
                pending.append(node.module)
                try:
                    target = importlib.import_module(node.module)
                except Exception as exc:
                    failures.append({"module": node.module, "reason": type(exc).__name__})
                    continue
                for alias in node.names:
                    if alias.name != "*" and not hasattr(target, alias.name):
                        failures.append({
                            "module": node.module, "symbol": alias.name,
                            "reason": "IMPORTED_SYMBOL_MISSING", "importer": module_name,
                        })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _module_source_path(alias.name, root) is not None:
                        pending.append(alias.name)
        if imported_module is None:  # pragma: no cover - defensive only
            failures.append({"module": module_name, "reason": "IMPORT_RETURNED_NONE"})
    return visited, failures


def deployment_parity_report(root: str | Path = ".") -> dict[str, Any]:
    """Import and bootstrap active ATLAS surfaces from a tracked-source copy."""
    root_path = Path(root).resolve()
    manifest_path = root_path / ".atlas_tracked_manifest.json"
    if manifest_path.is_file():
        tracked = set(json.loads(manifest_path.read_text(encoding="utf-8")))
    else:
        tracked = set(subprocess.run(
            ["git", "ls-files"], cwd=root_path, check=True,
            capture_output=True, text=True,
        ).stdout.splitlines())

    failures: list[dict[str, Any]] = []
    modules, graph_failures = _research_local_import_graph(root_path)
    failures.extend(graph_failures)
    local_dependencies = sorted(
        path.relative_to(root_path).as_posix()
        for name in modules
        if (path := _module_source_path(name, root_path)) is not None
    )
    untracked_runtime_dependencies = [path for path in local_dependencies if path not in tracked]
    failures.extend(
        {"path": path, "reason": "UNTRACKED_RUNTIME_DEPENDENCY"}
        for path in untracked_runtime_dependencies
    )

    page_results: dict[str, str] = {}
    for page, (module_name, symbol) in ACTIVE_PAGE_RUNTIME_SYMBOLS.items():
        try:
            module = importlib.import_module(module_name)
            value = getattr(module, symbol)
            if not callable(value):
                raise TypeError("runtime symbol is not callable")
            page_results[page] = "PASS"
        except Exception as exc:
            page_results[page] = type(exc).__name__
            failures.append({"page": page, "module": module_name, "symbol": symbol, "reason": type(exc).__name__})

    app_module = importlib.import_module("app")
    final_main = getattr(app_module, "main", None)
    app_tree = ast.parse((root_path / "app.py").read_text(encoding="utf-8"))
    final_main_line = max(
        node.lineno for node in app_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
    )
    if not callable(final_main) or final_main.__code__.co_firstlineno != final_main_line:
        failures.append({"reason": "FINAL_MAIN_RESOLUTION_FAILED"})

    from engines import atlas_research_builder_v2 as builder
    original_history = builder.attach_price_history
    try:
        builder.attach_price_history = lambda row: dict(row)
        report = builder.build_atlas_research_v2({
            "ticker": "NVDA", "company": "NVDA Deployment Fixture",
            "security_type": "EQUITY", "current_price": 100.0,
            "atlas_fair_value": 120.0, "analyst_actions": [],
            "earnings_history": [], "company_news": [],
        })
    finally:
        builder.attach_price_history = original_history
    if report.get("ticker") != "NVDA" or not isinstance(report.get("sections"), Mapping):
        failures.append({"reason": "NVDA_RESEARCH_BOOTSTRAP_FAILED"})

    from engines.ask_atlas_engine import ask_atlas
    from engines.political_evidence import normalize_political_transaction
    from engines.research_engine import begin_research_entry
    state = {"authenticated": True, "role": "viewer", "user_role": "viewer"}
    entry = begin_research_entry(state, "CRM", source="DEPLOYMENT_PARITY_GATE")
    bootstrap_results = {
        "application_import": callable(final_main),
        "final_main_line": final_main_line,
        "nvda_research": report.get("ticker") == "NVDA",
        "home_to_research": entry.get("ticker") == "CRM" and state.get("v79_pending_page") == "Research Any Ticker",
        "ask": callable(ask_atlas),
        "political": normalize_political_transaction({"symbol": "CRM", "transaction": "Purchase"}).get("ticker") == "CRM",
    }
    if not all(value for key, value in bootstrap_results.items() if key != "final_main_line"):
        failures.append({"reason": "BOOTSTRAP_CONTRACT_FAILED", "results": bootstrap_results})

    requirements = {
        re.split(r"[<>=!~\[]", line.strip(), maxsplit=1)[0].lower().replace("_", "-")
        for line in (root_path / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required_runtime_packages = {"streamlit", "pandas", "numpy", "plotly", "requests", "yfinance", "openai"}
    missing_declarations = sorted(required_runtime_packages - requirements)
    failures.extend({"package": name, "reason": "DEPENDENCY_NOT_DECLARED"} for name in missing_declarations)

    return {
        "version": "ATLAS_DEPLOYMENT_PARITY_GATE_V1",
        "status": "PASS" if not failures else "FAIL",
        "page_imports": page_results,
        "page_count": len(page_results),
        "research_modules": sorted(modules),
        "tracked_runtime_dependencies": local_dependencies,
        "untracked_runtime_dependencies": untracked_runtime_dependencies,
        "missing_dependency_declarations": missing_declarations,
        "bootstrap": bootstrap_results,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--deployment-parity", action="store_true")
    parser.add_argument("--output", default="audit_results/architecture_preflight.json")
    args = parser.parse_args()
    result = deployment_parity_report(".") if args.deployment_parity else architecture_preflight(".")
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "versions": result.get("versions", {}),
        "page_count": result.get("page_count"),
    }, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()


__all__ = [
    "CERTIFICATION_ARTIFACT", "CERTIFICATION_CLASSIFICATIONS",
    "CERTIFICATION_SEVERITIES", "CORE_PAGE_CONTRACTS", "FAMILY_RECONCILIATIONS",
    "ACTIVE_PAGE_RUNTIME_SYMBOLS", "DEPLOYMENT_PARITY_GATE_COMMAND",
    "PROTECTED_DECISION_FIELDS", "ROLLOUT_STATE", "RUNTIME_QA_FRAMEWORK_VERSION",
    "architecture_preflight", "architecture_versions", "certification_record", "deployment_parity_report",
    "certification_integrity", "journey_completeness",
    "certify_analyst_action_readiness", "certify_ask_context", "certify_etf_context",
    "certify_freshness", "certify_immutable_decision",
    "certify_missing_production_ticker", "certify_research_context",
    "certify_sec_authority", "certify_valuation_separation",
    "decode_context_summary", "encode_context_summary", "protected_decision_digest",
    "protected_decision_snapshot", "production_decision_for_ticker", "reconcile_family", "research_ticker_matrix",
    "sanitize_research_context", "stable_digest",
]
