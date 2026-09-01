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


def _records(source: Mapping[str, Any], *keys: str, limit: int = 10) -> list[dict[str, Any]]:
    for key in keys:
        value = source.get(key)
        rows = [dict(item) for item in safe_sequence(value) if isinstance(item, Mapping)]
        if rows:
            return rows[:limit]
    return []


def _family_data(context: Mapping[str, Any], family: str) -> Any:
    envelope = safe_mapping(safe_mapping(context.get("evidence_families")).get(family))
    return envelope.get("data")


def _prefer(primary: Any, fallback: Any) -> Any:
    return fallback if primary is None or (isinstance(primary, str) and not primary.strip()) else primary


def _deep_evidence(source: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    action_data = _family_data(context, "analyst_actions")
    action_source = safe_mapping(action_data)
    analyst_actions = (
        _records(source, "analyst_actions", "analyst_grades", "analyst_details")
        or _records(action_source, "actions", "items", "records")
        or [dict(item) for item in safe_sequence(action_data) if isinstance(item, Mapping)][:10]
    )
    consensus_data = safe_mapping(_family_data(context, "analyst_consensus_targets"))
    analyst_consensus = {
        "mean_target": _number(_prefer(_first(consensus_data, "analyst_target_mean", "target_mean_price", "consensus_target", "mean"), _first(source, "analyst_target_mean", "target_mean_price", "consensus_target"))),
        "low_target": _number(_prefer(_first(consensus_data, "analyst_target_low", "target_low_price", "low"), _first(source, "analyst_target_low", "target_low_price"))),
        "high_target": _number(_prefer(_first(consensus_data, "analyst_target_high", "target_high_price", "high"), _first(source, "analyst_target_high", "target_high_price"))),
        "analyst_count": _number(_prefer(_first(consensus_data, "analyst_count", "count"), _first(source, "analyst_count", "finnhub_analyst_total"))),
    }
    analyst_available = bool(analyst_actions or any(value is not None for value in analyst_consensus.values()))
    news_data = _family_data(context, "company_news")
    news_source = safe_mapping(news_data)
    news = (
        _records(source, "company_news", "news_evidence", "market_moving_news", "v42_news_catalysts")
        or _records(news_source, "news", "items", "articles", "records")
        or [dict(item) for item in safe_sequence(news_data) if isinstance(item, Mapping)][:10]
    )
    ownership_data = safe_mapping(_family_data(context, "institutional_ownership"))
    ownership = {
        "institutional_ownership_pct": _number(_prefer(_first(ownership_data, "institutional_ownership_pct", "institutional_pct"), source.get("institutional_ownership_pct"))),
        "insider_ownership_pct": _number(_prefer(_first(ownership_data, "insider_ownership_pct", "insider_pct"), source.get("insider_ownership_pct"))),
        "major_holders": _records(ownership_data, "major_holders", "institutional_holders", "holders", "records") or _records(source, "major_holders", "institutional_holders", "ownership_records"),
    }
    ownership_available = any(
        value is not None and value != [] for value in ownership.values()
    )
    political = _records(
        source, "congressional_transactions", "political_transactions",
        "political_evidence", "congressional_trades",
    )
    target_family = safe_mapping(safe_mapping(context.get("evidence_families")).get("analyst_price_target_actions"))
    insider_family = safe_mapping(safe_mapping(context.get("evidence_families")).get("insider_transactions"))
    return {
        "analyst": {
            "semantic_status": "AVAILABLE" if analyst_available else DATA_UNAVAILABLE,
            "actions": analyst_actions,
            "consensus": analyst_consensus,
        },
        "news": {"semantic_status": "AVAILABLE" if news else DATA_UNAVAILABLE, "items": news},
        "ownership": {
            "semantic_status": "AVAILABLE" if ownership_available else DATA_UNAVAILABLE,
            **ownership,
        },
        "political": {
            "semantic_status": "AVAILABLE" if political else DATA_UNAVAILABLE,
            "transactions": political,
            "scoring_authority": "CONTEXT_ONLY",
        },
        "price_target_actions": {
            "semantic_status": target_family.get("semantic_status", DATA_UNAVAILABLE),
            "actions": safe_sequence(safe_mapping(target_family.get("data")).get("actions")),
        },
        "insider_transactions": {
            "semantic_status": insider_family.get("semantic_status", DATA_UNAVAILABLE),
            "transactions": safe_sequence(safe_mapping(insider_family.get("data")).get("transactions")),
            "scoring_authority": "CONTEXT_ONLY",
        },
    }


def build_earnings_decision_story(row: Mapping[str, Any]) -> dict[str, Any]:
    """Build presentation-only Earnings story from one persisted canonical row."""
    nested = safe_mapping(row.get("Raw") or row.get("raw"))
    # Display normalization can add convenience labels such as a generic
    # ``Recommendation=buy``. Those labels are useful nowhere in the immutable
    # decision boundary. Merge only for evidence presentation; decision fields
    # come from an existing canonical context or the preserved production row.
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
    context = safe_mapping(row.get("research_context")) or safe_mapping(nested.get("research_context"))
    transcript_family = safe_mapping(safe_mapping(context.get("evidence_families")).get("transcript_intelligence"))
    transcript = transcript_family if transcript_family else build_transcript_intelligence(source, is_etf=is_etf)
    snapshot_family = safe_mapping(safe_mapping(context.get("evidence_families")).get("analyst_estimate_snapshots"))
    canonical_decision = safe_mapping(context.get("production_decision"))
    decision = dict(canonical_decision) if canonical_decision else dict(
        build_production_decision(nested if nested else row)
    )
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
        "analyst_estimate_snapshots": safe_mapping(snapshot_family.get("data")),
        "estimate_revisions_status": DATA_UNAVAILABLE if not is_etf else NOT_APPLICABLE,
        "market_reaction": {"semantic_status": DATA_UNAVAILABLE, "status_detail": "Event-aligned market reaction: Unavailable"},
        "production_decision": decision,
        "technical_state": _first(source, "technical_state", "deterministic_technical_state"),
        "wall_street_consensus": _first(source, "analyst_target_mean", "target_mean_price", "consensus_target"),
        "thesis_strengtheners": _conditions(source, "thesis_strengtheners"),
        "thesis_weakeners": _conditions(source, "thesis_weakeners"),
        "thesis_invalidators": _conditions(source, "thesis_invalidators"),
        "watch_next": (_conditions(source, "watch_next") or _as_list(summary.get("watch_next")))[:7],
        "analyst_actions": _records(source, "analyst_actions", "analyst_grades", "analyst_details"),
        "deep_evidence": _deep_evidence(source, context),
        "history": intelligence.get("history", []),
        "limitations": limitations,
        "evidence_ids": evidence_ids,
        "as_of": _first(source, "production_scan_timestamp", "scan_time", "generated_at") or latest.get("evidence_timestamp"),
    }


__all__ = ["EARNINGS_DECISION_STORY_VERSION", "build_earnings_decision_story", "normalized_earnings_history"]
