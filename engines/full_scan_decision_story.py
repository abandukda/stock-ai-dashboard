"""Read-only decision-story contract for Full Scan VNext.

The builder projects one persisted production row into customer-facing evidence.
It never ranks, scores, values, fetches, or selects a provider.
"""
from __future__ import annotations

from typing import Any, Final, Mapping, Sequence

from engines.research_context import build_production_decision
from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE


FULL_SCAN_DECISION_STORY_VERSION: Final = "FULL_SCAN_DECISION_STORY_V1"
NO_PRIOR_SCAN_COMPARISON: Final = (
    "Prior Full Scan comparison is not available for this production snapshot."
)


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            value = source.get(key)
            if value is not None and not (isinstance(value, str) and not value.strip()):
                return value
    return None


def _number(source: Mapping[str, Any], *keys: str) -> float | int | None:
    value = _first(source, *keys)
    if value is None or isinstance(value, bool) or isinstance(value, (Mapping, list, tuple, set)):
        return None
    try:
        return float(str(value).replace("$", "").replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _text(source: Mapping[str, Any], *keys: str) -> str | None:
    value = _first(source, *keys)
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None
    result = str(value).strip()
    return result or None


def _items(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = [str(item).strip() for item in value if not isinstance(item, Mapping)]
    elif isinstance(value, str):
        values = [part.strip() for part in value.split(";")]
    else:
        values = []
    return list(dict.fromkeys(item for item in values if item))[:limit]


def _raw_row(row: Mapping[str, Any]) -> dict[str, Any]:
    wrapper = dict(row or {})
    raw = wrapper.get("Raw") or wrapper.get("raw")
    return dict(raw) if isinstance(raw, Mapping) else wrapper


def _canonical_decision(wrapper: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    context = wrapper.get("research_context")
    if not isinstance(context, Mapping):
        context = raw.get("research_context")
    embedded = context.get("production_decision") if isinstance(context, Mapping) else None
    return dict(embedded) if isinstance(embedded, Mapping) else dict(build_production_decision(raw))


def _why_ranked(raw: Mapping[str, Any]) -> list[str]:
    factors: list[str] = []
    factors.extend(_items(_first(raw, "setup_tags", "Setup Tags"), limit=3))
    factors.extend(_items(_first(raw, "finance_agent_findings", "Finance Agent Findings"), limit=3))
    if not factors:
        for key in ("why_ranked_high", "Why Ranked High", "table_reason"):
            text = _text(raw, key)
            if text:
                factors.append(text)
                break
    return list(dict.fromkeys(factors))[:3]


def _constraints(raw: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    values.extend(_items(_first(raw, "risk_tags", "Risk Tags"), limit=4))
    values.extend(_items(_first(raw, "finance_agent_risks", "Finance Agent Risks"), limit=4))
    direct = _text(raw, "what_could_go_wrong", "Primary Risk", "primary_risk")
    if direct:
        values.append(direct)
    flags = _items(_first(raw, "atlas_valuation_assumption_flags"), limit=3)
    values.extend(f"Valuation limitation: {flag}" for flag in flags)
    return list(dict.fromkeys(item for item in values if item))[:4]


def _news(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = _first(raw, "news_evidence", "recent_headlines")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)][:5]


def _evidence_health(raw: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "ranking": _number(raw, "relative_rank_score") is not None,
        "valuation": decision.get("atlas_fair_value") is not None,
        "fundamentals": any(_first(raw, key) is not None for key in (
            "revenue_growth", "earnings_growth", "free_cash_flow", "operating_profit_margin",
        )),
        "technical": any(_first(raw, key) is not None for key in (
            "deterministic_technical_state", "technical_state", "rsi", "sma20", "sma50",
        )),
        "analyst": any(_first(raw, key) is not None for key in (
            "analyst_target_mean", "analyst_count", "analyst_actions",
        )),
        "news": bool(_news(raw)),
        "risk": bool(_constraints(raw)),
    }
    available = sum(checks.values())
    return {
        "available": available,
        "total": len(checks),
        "label": f"{available}/{len(checks)} evidence families available",
        "families": checks,
        "semantic_status": AVAILABLE if available else DATA_UNAVAILABLE,
    }


def _actionability(decision: Mapping[str, Any]) -> dict[str, str]:
    recommendation = decision.get("recommendation")
    if not recommendation:
        return {
            "state": "Decision unavailable",
            "explanation": "ATLAS does not currently publish an actionable recommendation for this security.",
        }
    normalized = str(recommendation).upper().replace("-", "_").replace(" ", "_")
    if normalized in {"BUY_NOW", "BUY", "ACCUMULATE"}:
        state = "Actionable now"
    elif normalized in {"MONITOR", "WATCH", "WATCHLIST", "WAIT", "HOLD"}:
        state = "Needs confirmation"
    elif normalized in {"AVOID", "SELL"}:
        state = "Not actionable"
    else:
        state = "Canonical state published"
    return {"state": state, "explanation": f"Canonical ATLAS state: {recommendation}."}


def build_full_scan_decision_story(
    row: Mapping[str, Any], *, production_rank: int, filtered_position: int | None = None,
) -> dict[str, Any]:
    """Build one Full Scan story while preserving all production authority."""
    wrapper = dict(row or {})
    raw = _raw_row(wrapper)
    decision = _canonical_decision(wrapper, raw)
    ticker = str(_first(raw, "ticker", "Ticker", "symbol") or _first(wrapper, "Ticker", "ticker") or "UNKNOWN").upper().strip()
    company = str(_first(raw, "company", "company_name", "name", "Company") or _first(wrapper, "Company", "company") or ticker).strip()
    constraints = _constraints(raw)
    health = _evidence_health(raw, decision)

    valuation = {
        "atlas_fair_value": decision.get("atlas_fair_value"),
        "expected_return": decision.get("decision_expected_return"),
        "wall_street_mean": _number(raw, "analyst_target_mean", "target_mean_price"),
        "wall_street_low": _number(raw, "analyst_target_low", "target_low_price"),
        "wall_street_high": _number(raw, "analyst_target_high", "target_high_price"),
        "analyst_count": _number(raw, "analyst_count", "finnhub_analyst_total"),
        "analyst_support": _text(raw, "analyst_support_label"),
    }
    technical = {
        "state": _text(raw, "deterministic_technical_state", "technical_state"),
        "rsi": _number(raw, "rsi", "RSI"),
        "atr_pct": _number(raw, "atr_pct", "ATR %"),
        "volume_ratio": _number(raw, "volume_ratio", "Volume Ratio"),
        "twenty_day_pct": _number(raw, "twenty_day_pct", "20D %"),
        "support": _number(raw, "v42_support_1"),
        "resistance": _number(raw, "v42_resistance_1"),
    }
    progressive = {
        "fundamentals_earnings": {
            "revenue_growth": _number(raw, "revenue_growth"),
            "earnings_growth": _number(raw, "earnings_growth"),
            "gross_margin": _number(raw, "gross_profit_margin"),
            "operating_margin": _number(raw, "operating_profit_margin"),
            "free_cash_flow": _number(raw, "free_cash_flow"),
            "cash": _number(raw, "cash_and_equivalents"),
            "debt": _number(raw, "total_debt"),
            "eps_surprise_pct": _number(raw, "eps_surprise_pct"),
            "revenue_surprise_pct": _number(raw, "revenue_surprise_pct"),
        },
        "analyst": {
            **valuation,
            "actions": [dict(item) for item in (_first(raw, "analyst_actions") or []) if isinstance(item, Mapping)][:5],
        },
        "catalysts_news": {
            "items": _news(raw),
            "sentiment": _text(raw, "latest_news_sentiment", "news_sentiment_label"),
        },
        "risk": {"constraints": constraints},
        "recovery": {
            "score": _number(raw, "recovery_score"),
            "label": _text(raw, "recovery_label"),
            "thesis": _text(raw, "recovery_thesis"),
        },
    }
    freshness = raw.get("_evidence_freshness")
    evidence_ids = []
    context = raw.get("research_context")
    families = context.get("evidence_families") if isinstance(context, Mapping) else None
    if isinstance(families, Mapping):
        for family in families.values():
            if isinstance(family, Mapping):
                evidence_ids.extend(str(item) for item in family.get("evidence_ids") or () if item)

    return {
        "version": FULL_SCAN_DECISION_STORY_VERSION,
        "identity": {"ticker": ticker, "company": company},
        "production_rank": int(production_rank),
        "filtered_position": int(filtered_position) if filtered_position is not None else None,
        "production_conviction": _number(raw, "conviction", "conviction_score", "Final Conviction"),
        "relative_rank_score": _number(raw, "relative_rank_score"),
        "production_decision": decision,
        "canonical_state_status": (
            decision.get("semantic_status", DATA_UNAVAILABLE)
            if decision.get("recommendation") else DATA_UNAVAILABLE
        ),
        "canonical_state": decision.get("recommendation"),
        "opportunity": decision.get("opportunity"),
        "confidence": decision.get("confidence"),
        "valuation": valuation,
        "technical_state": technical,
        "why_ranked": _why_ranked(raw),
        "actionability": _actionability(decision),
        "constraints": constraints,
        "evidence_health": health,
        "progressive_evidence": progressive,
        "what_changed": {"semantic_status": DATA_UNAVAILABLE, "message": NO_PRIOR_SCAN_COMPARISON},
        "provenance": {
            "scan_time": _text(raw, "scan_time", "generated_at"),
            "freshness": dict(freshness) if isinstance(freshness, Mapping) else {},
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "limitations": [NO_PRIOR_SCAN_COMPARISON],
        },
    }


__all__ = [
    "FULL_SCAN_DECISION_STORY_VERSION", "NO_PRIOR_SCAN_COMPARISON",
    "build_full_scan_decision_story",
]
