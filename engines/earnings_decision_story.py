"""Deterministic presentation synthesis for Earnings Intelligence.

This module consumes normalized, persisted evidence.  It has no provider,
scoring, valuation, recommendation, or technical-state authority.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Final, Mapping, Sequence

from engines.earnings_intelligence import (
    build_earnings_intelligence,
    build_earnings_summary,
    build_management_guidance,
    build_transcript_intelligence,
)
from engines.research_context import build_production_decision, security_type_of
from engines.semantic_fields import DATA_UNAVAILABLE, NOT_APPLICABLE, safe_mapping, safe_sequence


EARNINGS_DECISION_STORY_VERSION: Final = "EARNINGS_DECISION_STORY_V1"


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and not (isinstance(value, str) and not value.strip()):
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or isinstance(value, (Mapping, list, tuple, set)):
        return None
    try:
        result = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in {float("inf"), float("-inf")} else None


def _date_text(value: Any) -> str | None:
    if isinstance(value, (Mapping, list, tuple, set)) or value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        return text[:40] or None


def normalized_earnings_history(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    deep = safe_mapping(row.get("deep_research_evidence"))
    raw = safe_mapping(row.get("Raw") or row.get("raw"))
    candidates = (
        row.get("earnings_history") or raw.get("earnings_history")
        or deep.get("earnings_history") or row.get("historical_earnings")
        or row.get("quarterly_earnings") or []
    )
    output: list[dict[str, Any]] = []
    for item in safe_sequence(candidates):
        if not isinstance(item, Mapping):
            continue
        output.append({
            "fiscal_period": _first(item, "fiscal_period", "period", "quarter"),
            "report_date": _date_text(_first(item, "report_date", "date")),
            "eps_actual": _number(_first(item, "eps_actual", "epsActual", "actual_eps")),
            "eps_estimate": _number(_first(item, "eps_estimate", "epsEstimated", "estimated_eps")),
            "eps_surprise_pct": _number(_first(item, "eps_surprise_pct", "epsSurprisePct")),
            "revenue_actual": _number(_first(item, "revenue_actual", "revenueActual")),
            "revenue_estimate": _number(_first(item, "revenue_estimate", "revenueEstimated")),
            "revenue_surprise_pct": _number(_first(item, "revenue_surprise_pct", "revenueSurprisePct")),
            "provider": _first(item, "provider", "source"),
            "evidence_timestamp": _first(item, "evidence_timestamp", "as_of"),
        })
    return output


def _as_list(value: Any, limit: int = 7) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    result = []
    for item in safe_sequence(value):
        if isinstance(item, (str, int, float)) and str(item).strip():
            result.append(str(item).strip())
        elif isinstance(item, Mapping):
            text = _first(item, "condition", "summary", "detail", "title", "description")
            if text is not None:
                result.append(str(text).strip())
        if len(result) >= limit:
            break
    return result


def _conditions(row: Mapping[str, Any], key: str) -> list[str]:
    guidance = safe_mapping(row.get("guidance_summary"))
    research = safe_mapping(row.get("research_report"))
    return _as_list(
        _first(row, key, key.replace("thesis_", ""))
        or guidance.get(key) or safe_mapping(research.get("guidance_summary")).get(key)
    )


def build_earnings_decision_story(row: Mapping[str, Any]) -> dict[str, Any]:
    """Build presentation-only Earnings story from one persisted canonical row."""
    nested = safe_mapping(row.get("Raw") or row.get("raw"))
    # The display-normalized scan row can contain authoritative decision
    # aliases while Raw retains the deep evidence graph.  Merge for read-only
    # presentation so neither family is silently discarded.
    source = {**dict(nested), **dict(row)} if nested else dict(row)
    ticker = str(_first(row, "ticker", "Ticker") or _first(source, "ticker", "Ticker") or "UNKNOWN").upper()
    company = str(_first(row, "company", "Company", "company_name", "Name") or _first(source, "company", "Company", "company_name", "Name") or ticker)
    is_etf = security_type_of(source) == "ETF"
    history = normalized_earnings_history(row)
    if not history and source is not row:
        history = normalized_earnings_history(source)
    intelligence = build_earnings_intelligence(history, is_etf=is_etf)
    summary = build_earnings_summary(intelligence, ticker=ticker)
    guidance = build_management_guidance(source, is_etf=is_etf)
    transcript = build_transcript_intelligence(source, is_etf=is_etf)
    decision = dict(build_production_decision(source))
    latest = safe_mapping(intelligence.get("latest_quarter"))
    event_date = latest.get("report_date")
    next_date = _date_text(_first(source, "next_earnings_date", "Next Earnings Date", "earnings_date"))
    upcoming = bool(next_date and next_date > date.today().isoformat())
    why = [summary.get("what_improved"), summary.get("what_deteriorated"), summary.get("trend_assessment")]
    why = [str(item) for item in why if item]
    limitations = []
    if guidance.get("semantic_status") != "AVAILABLE":
        limitations.append("Management guidance unavailable or unverified.")
    limitations.append("Estimate revision direction cannot be verified from the available point-in-time evidence.")
    limitations.append("Event-aligned market reaction: Unavailable")
    if transcript.get("semantic_status") != "AVAILABLE":
        limitations.append("Transcript intelligence unavailable.")
    evidence_ids = _as_list(_first(source, "evidence_ids", "source_evidence_ids"), 20)
    return {
        "version": EARNINGS_DECISION_STORY_VERSION,
        "semantic_status": intelligence.get("semantic_status", DATA_UNAVAILABLE),
        "ticker": ticker,
        "company": company,
        "security_type": "ETF" if is_etf else "EQUITY",
        "event_identity": {
            "state": "UPCOMING" if upcoming and not latest else "REPORTED" if latest else "UNAVAILABLE",
            "fiscal_period": latest.get("fiscal_period"),
            "report_date": event_date,
            "next_event_date": next_date,
        },
        "event_result": intelligence.get("latest_quarter_classification", "UNAVAILABLE"),
        "latest_quarter": dict(latest),
        "what_happened": summary.get("what_happened") or summary.get("summary"),
        "why_it_matters": why[:5],
        "what_improved": summary.get("what_improved"),
        "what_deteriorated": summary.get("what_deteriorated"),
        "primary_constraint": why[1] if len(why) > 1 else None,
        "management_guidance": guidance,
        "transcript_intelligence": transcript,
        "estimate_revisions_status": DATA_UNAVAILABLE if not is_etf else NOT_APPLICABLE,
        "market_reaction": {"semantic_status": DATA_UNAVAILABLE, "status_detail": "Event-aligned market reaction: Unavailable"},
        "production_decision": decision,
        "technical_state": _first(source, "technical_state", "deterministic_technical_state"),
        "wall_street_consensus": _first(source, "analyst_target_mean", "target_mean_price", "consensus_target"),
        "thesis_strengtheners": _conditions(source, "thesis_strengtheners"),
        "thesis_weakeners": _conditions(source, "thesis_weakeners"),
        "thesis_invalidators": _conditions(source, "thesis_invalidators"),
        "watch_next": (_conditions(source, "watch_next") or _as_list(summary.get("watch_next")))[:7],
        "analyst_actions": [dict(item) for item in safe_sequence(source.get("analyst_actions")) if isinstance(item, Mapping)][:10],
        "history": intelligence.get("history", []),
        "limitations": limitations,
        "evidence_ids": evidence_ids,
        "as_of": _first(source, "production_scan_timestamp", "scan_time", "generated_at") or latest.get("evidence_timestamp"),
    }


__all__ = ["EARNINGS_DECISION_STORY_VERSION", "build_earnings_decision_story", "normalized_earnings_history"]
