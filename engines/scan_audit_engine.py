"""
Atlas V94 — Scan Audit & Coverage Engine

New file:
    engines/scan_audit_engine.py

Purpose
-------
Audit the Atlas daily scan without changing any recommendation.

This engine is deliberately READ-ONLY:
- it does not import app.py;
- it does not override decision functions;
- it does not recalculate Buy/Accumulate/Monitor/Avoid;
- it consumes finalized rows and reports pipeline health, coverage, exclusions,
  missing data, and recommendation distribution.

Primary entry points
--------------------
    audit = build_scan_audit(rows)
    stock_audit = audit_stock_row(row)

Expected input
--------------
An iterable of finalized/canonical stock dictionaries. V93 rows may contain:
    row["v93_snapshot"]
    row["v89_decision"]

The engine also works with ordinary normalized dictionaries.

Architecture boundary
---------------------
Earlier versions may enrich or decide. V94 may only observe and report.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence
import math
import re


MISSING_STRINGS = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "nan",
    "unavailable",
    "under review",
    "not available",
    "not reported",
    "-",
    "—",
}

CANONICAL_ACTIONS = {"BUY_NOW", "ACCUMULATE", "MONITOR", "AVOID"}

DEFAULT_EXCLUSIONS = {
    "financials",
    "entertainment",
    "gambling",
    "alcohol",
    "israeli",
}


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return default if text.lower() in MISSING_STRINGS else text


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    text = (
        str(value)
        .replace(",", "")
        .replace("$", "")
        .replace("%", "")
        .replace("x", "")
        .strip()
    )
    if text.lower() in MISSING_STRINGS:
        return default
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default
    try:
        number = float(match.group(0))
        return default if math.isnan(number) or math.isinf(number) else number
    except ValueError:
        return default


def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in MISSING_STRINGS:
            continue
        return value
    return default


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in MISSING_STRINGS
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    try:
        return not math.isnan(float(value))
    except Exception:
        return True


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip(" -•\t") for part in re.split(r"[\n|•]+", value) if part.strip(" -•\t")]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        output: List[str] = []
        for item in value:
            if isinstance(item, Mapping):
                item = _first(item, "headline", "title", "summary", "text", "reason")
            text = _text(item)
            if text:
                output.append(text)
        return output
    text = _text(value)
    return [text] if text else []


def _normalize_action(row: Mapping[str, Any]) -> str:
    decision = row.get("v89_decision")
    if isinstance(decision, Mapping):
        code = _text(decision.get("action_code")).upper()
        if code in CANONICAL_ACTIONS:
            return code

    snapshot = row.get("v93_snapshot")
    if isinstance(snapshot, Mapping):
        code = _text(snapshot.get("action_code")).upper()
        if code in CANONICAL_ACTIONS:
            return code

    raw = _text(_first(row, "Action Code", "Recommendation", "Decision", "Action")).lower()
    if "buy now" in raw or "high conviction" in raw:
        return "BUY_NOW"
    if "accumulate" in raw or "buy on weakness" in raw:
        return "ACCUMULATE"
    if "avoid" in raw or "sell" in raw:
        return "AVOID"
    return "MONITOR"


def _canonical_snapshot(row: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshot = row.get("v93_snapshot")
    return snapshot if isinstance(snapshot, Mapping) else {}


def _canonical_decision(row: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = row.get("v89_decision")
    return decision if isinstance(decision, Mapping) else {}


def _field_status(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    values = [row.get(key) for key in keys if key in row]
    if not values:
        return "missing"
    if any(_present(value) for value in values):
        return "available"
    return "unavailable"


FIELD_GROUPS: Dict[str, Sequence[str]] = {
    "price": ("Current Price", "Price", "current_price", "Close"),
    "fair_value": ("Atlas Fair Value", "atlas_fair_value", "fair_value"),
    "analyst_target": (
        "Wall Street Consensus",
        "Analyst Target",
        "analyst_target",
        "targetMeanPrice",
    ),
    "revenue_growth": ("Revenue Growth", "Revenue Growth %", "revenue_growth", "revenueGrowth"),
    "eps_growth": ("EPS Growth", "eps_growth", "earningsGrowth"),
    "operating_margin": ("Operating Margin", "operating_margin", "operatingMargins"),
    "free_cash_flow": ("Free Cash Flow", "free_cash_flow", "freeCashflow"),
    "liquidity": ("Current Ratio", "current_ratio", "currentRatio"),
    "technicals": (
        "RSI",
        "rsi",
        "Technical Score",
        "technical_score",
        "Above 50DMA",
        "Above 200DMA",
    ),
    "price_history": (
        "price_history",
        "historical_prices",
        "chart_data",
        "historical_data",
    ),
    "news": ("news_items", "latest_news", "news", "latest_news_headline", "Top News"),
    "earnings": (
        "earnings_summary",
        "earnings_ai_summary",
        "guidance_summary",
        "management_guidance",
        "transcript_summary",
    ),
    "institutional": (
        "institutional_summary",
        "institutional_activity",
        "smart_money",
        "ownership_summary",
    ),
    "policy": (
        "political_support",
        "political_context",
        "policy_context",
        "political_support_summary",
    ),
}


@dataclass(frozen=True)
class StockAudit:
    ticker: str
    company: str
    action: str
    research_completeness_pct: float
    available_groups: List[str]
    missing_groups: List[str]
    unavailable_groups: List[str]
    passed_gates: List[str]
    failed_gates: List[str]
    warnings: List[str]
    top_rejection_reason: str
    provider_status: Dict[str, str]


def audit_stock_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = _canonical_snapshot(row)
    decision = _canonical_decision(row)

    ticker = _text(_first(row, "Ticker", "ticker", "symbol"), "UNKNOWN").upper()
    company = _text(_first(row, "Company", "company", "Name", "longName"), ticker)
    action = _normalize_action(row)

    statuses = {name: _field_status(row, keys) for name, keys in FIELD_GROUPS.items()}
    available = [name for name, status in statuses.items() if status == "available"]
    missing = [name for name, status in statuses.items() if status == "missing"]
    unavailable = [name for name, status in statuses.items() if status == "unavailable"]

    completeness = _num(decision.get("research_completeness_pct"))
    if completeness is None:
        completeness = len(available) / max(len(FIELD_GROUPS), 1) * 100.0

    current = _num(snapshot.get("current_price"), _num(_first(row, *FIELD_GROUPS["price"])))
    fair = _num(snapshot.get("atlas_fair_value"), _num(_first(row, *FIELD_GROUPS["fair_value"])))
    expected_return = _num(
        snapshot.get("expected_return_pct"),
        _num(decision.get("expected_return_pct")),
    )
    if expected_return is None and current and fair and current > 0:
        expected_return = ((fair - current) / current) * 100.0

    components = decision.get("component_scores")
    components = components if isinstance(components, Mapping) else {}
    fundamentals = _num(components.get("fundamentals"))
    valuation = _num(components.get("valuation"))
    technicals = _num(components.get("technicals"))
    risk_level = _text(decision.get("risk_level"), "Unknown")

    passed: List[str] = []
    failed: List[str] = []
    warnings: List[str] = []

    if current is not None and current > 0:
        passed.append("valid_price")
    else:
        failed.append("valid_price")

    if fundamentals is not None:
        (passed if fundamentals >= 55 else failed).append("fundamentals")
    elif statuses["revenue_growth"] == "available" or statuses["free_cash_flow"] == "available":
        passed.append("fundamentals_data_present")
    else:
        warnings.append("fundamentals_not_fully_scored")

    if expected_return is not None:
        (passed if expected_return > 0 else failed).append("positive_expected_return")
    else:
        warnings.append("expected_return_unavailable")

    if valuation is not None:
        (passed if valuation >= 55 else failed).append("valuation")
    elif fair is not None:
        passed.append("valuation_data_present")
    else:
        warnings.append("valuation_not_fully_scored")

    if technicals is not None:
        (passed if technicals >= 50 else failed).append("technicals")
    elif statuses["technicals"] == "available":
        passed.append("technical_data_present")
    else:
        warnings.append("technicals_unavailable")

    for group in ("news", "earnings", "institutional", "policy"):
        if statuses[group] == "available":
            passed.append(group)
        else:
            warnings.append(f"{group}_{statuses[group]}")

    if completeness >= 60:
        passed.append("research_completeness")
    elif completeness < 40:
        failed.append("research_completeness")
    else:
        warnings.append("research_completeness_moderate")

    if risk_level.lower() == "high":
        failed.append("risk_control")
    elif risk_level.lower() in {"moderate", "low to moderate", "low"}:
        passed.append("risk_control")
    else:
        warnings.append("risk_level_unavailable")

    provider_status = {
        "financials": "ok" if any(statuses[g] == "available" for g in ("revenue_growth", "eps_growth", "operating_margin", "free_cash_flow")) else "missing",
        "technicals": "ok" if statuses["technicals"] == "available" else "missing",
        "price_history": (
            "ok"
            if statuses["price_history"] == "available"
            else "missing"
        ),
        "valuation": "ok" if statuses["fair_value"] == "available" else "missing",
        "analysts": "ok" if statuses["analyst_target"] == "available" else "missing",
        "news": "ok" if statuses["news"] == "available" else "missing",
        "earnings": "ok" if statuses["earnings"] == "available" else "missing",
        "institutional": "ok" if statuses["institutional"] == "available" else "missing",
        "policy": "ok" if statuses["policy"] == "available" else "missing",
    }

    rejection_priority = [
        ("valid_price", "Invalid or missing current price"),
        ("fundamentals", "Fundamental score did not pass"),
        ("positive_expected_return", "Expected return was not positive"),
        ("valuation", "Valuation gate did not pass"),
        ("technicals", "Technical confirmation did not pass"),
        ("research_completeness", "Research completeness was too low"),
        ("risk_control", "Risk control failed"),
    ]
    rejection = "Passed core gates"
    for gate, message in rejection_priority:
        if gate in failed:
            rejection = message
            break
    if action in {"MONITOR", "AVOID"} and rejection == "Passed core gates":
        first_warning = warnings[0] if warnings else "insufficient independent confirmation"
        rejection = first_warning.replace("_", " ").capitalize()

    return asdict(
        StockAudit(
            ticker=ticker,
            company=company,
            action=action,
            research_completeness_pct=round(completeness, 1),
            available_groups=available,
            missing_groups=missing,
            unavailable_groups=unavailable,
            passed_gates=passed,
            failed_gates=failed,
            warnings=warnings,
            top_rejection_reason=rejection,
            provider_status=provider_status,
        )
    )


def _normalize_rows(rows: Any) -> List[Mapping[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        try:
            return list(rows.to_dict("records"))
        except Exception:
            pass
    if isinstance(rows, Mapping):
        for key in ("rows", "data", "results"):
            value = rows.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        return [rows]
    if isinstance(rows, Iterable) and not isinstance(rows, (str, bytes, bytearray)):
        return [item for item in rows if isinstance(item, Mapping)]
    return []


def build_scan_audit(
    rows: Any,
    *,
    expected_exclusions: Iterable[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build a read-only daily scan audit.

    `metadata` may include upstream counts such as:
        universe_loaded
        excluded_policy
        passed_liquidity
        passed_prescreen
        fully_enriched
        execution_seconds
        provider_status
    """
    normalized = _normalize_rows(rows)
    audits = [audit_stock_row(row) for row in normalized]
    metadata = dict(metadata or {})

    actions = Counter(audit["action"] for audit in audits)
    rejection_reasons = Counter(
        audit["top_rejection_reason"]
        for audit in audits
        if audit["action"] in {"MONITOR", "AVOID"}
    )

    field_coverage: Dict[str, Dict[str, float]] = {}
    for group in FIELD_GROUPS:
        available_count = sum(group in audit["available_groups"] for audit in audits)
        missing_count = sum(group in audit["missing_groups"] for audit in audits)
        unavailable_count = sum(group in audit["unavailable_groups"] for audit in audits)
        total = max(len(audits), 1)
        field_coverage[group] = {
            "available": available_count,
            "missing": missing_count,
            "unavailable": unavailable_count,
            "coverage_pct": round(available_count / total * 100.0, 1),
        }

    provider_rollup: Dict[str, Dict[str, int]] = defaultdict(lambda: {"ok": 0, "missing": 0})
    for audit in audits:
        for provider, status in audit["provider_status"].items():
            provider_rollup[provider][status] += 1

    avg_completeness = (
        sum(audit["research_completeness_pct"] for audit in audits) / len(audits)
        if audits
        else 0.0
    )

    provider_health_pct = 0.0
    provider_checks = 0
    provider_ok = 0
    for counts in provider_rollup.values():
        provider_checks += counts["ok"] + counts["missing"]
        provider_ok += counts["ok"]
    if provider_checks:
        provider_health_pct = provider_ok / provider_checks * 100.0

    explicit_provider_status = metadata.get("provider_status")
    if isinstance(explicit_provider_status, Mapping):
        for provider, status in explicit_provider_status.items():
            provider_rollup[str(provider)]["reported_status"] = _text(status, "unknown")

    health_score = round(
        avg_completeness * 0.65
        + provider_health_pct * 0.35,
        1,
    )

    exclusion_rules = sorted(
        set(str(item).lower() for item in (expected_exclusions or DEFAULT_EXCLUSIONS))
    )

    pipeline = {
        "universe_loaded": int(_num(metadata.get("universe_loaded"), len(normalized)) or 0),
        "excluded_policy": int(_num(metadata.get("excluded_policy"), 0) or 0),
        "passed_liquidity": int(_num(metadata.get("passed_liquidity"), len(normalized)) or 0),
        "passed_prescreen": int(_num(metadata.get("passed_prescreen"), len(normalized)) or 0),
        "fully_enriched": int(
            _num(
                metadata.get("fully_enriched"),
                sum(audit["research_completeness_pct"] >= 60 for audit in audits),
            )
            or 0
        ),
        "buy_now": actions.get("BUY_NOW", 0),
        "accumulate": actions.get("ACCUMULATE", 0),
        "monitor": actions.get("MONITOR", 0),
        "avoid": actions.get("AVOID", 0),
    }

    warnings: List[str] = []
    if pipeline["universe_loaded"] < 1000:
        warnings.append("Universe loaded is below 1,000 symbols; verify the broad-market input.")
    if pipeline["fully_enriched"] < max(10, pipeline["passed_prescreen"] * 0.05):
        warnings.append("Too few prescreened stocks received full enrichment.")
    if actions.get("BUY_NOW", 0) == 0 and actions.get("ACCUMULATE", 0) == 0:
        warnings.append("No actionable candidates were produced; inspect top rejection reasons.")
    if avg_completeness < 50:
        warnings.append("Average research completeness is below 50%.")
    if field_coverage["policy"]["coverage_pct"] < 25:
        warnings.append("Political/policy coverage is below 25%.")
    if field_coverage["earnings"]["coverage_pct"] < 40:
        warnings.append("Earnings/guidance coverage is below 40%.")
    if field_coverage["news"]["coverage_pct"] < 40:
        warnings.append("News/catalyst coverage is below 40%.")

    return {
        "version": "V94",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "canonical_input_expected": "V93 finalized rows",
        "scan_health_score": health_score,
        "average_research_completeness_pct": round(avg_completeness, 1),
        "universe_rows_received": len(normalized),
        "pipeline": pipeline,
        "decision_distribution": dict(actions),
        "top_rejection_reasons": [
            {"reason": reason, "count": count}
            for reason, count in rejection_reasons.most_common(10)
        ],
        "field_coverage": field_coverage,
        "provider_rollup": dict(provider_rollup),
        "expected_exclusion_rules": exclusion_rules,
        "warnings": warnings,
        "stock_audits": audits,
        "metadata": metadata,
    }


def validate_audit_invariants(audit: Mapping[str, Any]) -> List[str]:
    """Return invariant violations without modifying the audit."""
    errors: List[str] = []
    pipeline = audit.get("pipeline")
    pipeline = pipeline if isinstance(pipeline, Mapping) else {}

    universe = int(_num(pipeline.get("universe_loaded"), 0) or 0)
    prescreen = int(_num(pipeline.get("passed_prescreen"), 0) or 0)
    enriched = int(_num(pipeline.get("fully_enriched"), 0) or 0)
    decisions = sum(
        int(_num(pipeline.get(key), 0) or 0)
        for key in ("buy_now", "accumulate", "monitor", "avoid")
    )

    if prescreen > universe:
        errors.append("passed_prescreen exceeds universe_loaded")
    if enriched > prescreen:
        errors.append("fully_enriched exceeds passed_prescreen")
    if decisions > int(_num(audit.get("universe_rows_received"), 0) or 0):
        errors.append("decision count exceeds received rows")
    if audit.get("read_only") is not True:
        errors.append("audit engine must remain read-only")

    return errors


def audit_history_provenance(
    row: Mapping[str, Any],
) -> Dict[str, Any]:
    """Distinguish absent records from fetch or mapping failures."""
    provenance = row.get("history_provenance")
    provenance = (
        provenance
        if isinstance(provenance, Mapping)
        else {}
    )
    history = _first(
        row,
        "price_history",
        "historical_prices",
        "chart_data",
        "historical_data",
        default=[],
    )
    records_found = (
        len(history)
        if isinstance(history, list)
        else int(_num(provenance.get("records_found"), 0) or 0)
    )

    if records_found > 0:
        status = "AVAILABLE"
    else:
        status = _text(
            provenance.get("status"),
            "NOT_LOADED",
        ).upper()

    return {
        "status": status,
        "provider_called": bool(
            provenance.get("provider_called")
        ),
        "provider_success": bool(
            provenance.get("provider_success")
        ),
        "records_found": records_found,
        "mapping_success": bool(
            provenance.get("mapping_success")
        ),
        "source": _text(provenance.get("source")),
        "as_of": _text(provenance.get("as_of")),
        "retrieval_status": _text(
            provenance.get("retrieval_status")
        ),
        "cache_status": _text(
            provenance.get("cache_status")
        ),
        "error": _text(provenance.get("error")),
    }


__all__ = [
    "audit_history_provenance",
    "audit_stock_row",
    "build_scan_audit",
    "validate_audit_invariants",
]
