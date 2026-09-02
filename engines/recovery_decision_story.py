"""Deterministic presentation contract for Recovery VNext.

This module reads persisted Recovery outputs and normalized evidence.  It does
not score, rank, value, trade, fetch, or choose providers.
"""
from __future__ import annotations

from typing import Any, Final, Mapping, Sequence

from engines.research_context import build_production_decision, security_type_of
from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE, NOT_APPLICABLE


RECOVERY_DECISION_STORY_VERSION: Final = "RECOVERY_DECISION_STORY_V1"
TARGET_PRIOR_LIMITATION: Final = (
    "Prior target was not provided by the source, so ATLAS does not calculate "
    "an individual target change."
)
ESTIMATE_ACCUMULATION_MESSAGE: Final = "Estimate revision history is still being accumulated."


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
    text = str(value).strip()
    return text or None


def _items(value: Any, *, limit: int = 12) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)[:limit]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(";") if part.strip()][:limit]
    return []


def _family(families: Mapping[str, Any], name: str, *, etf: bool = False) -> dict[str, Any]:
    family = families.get(name)
    if isinstance(family, Mapping):
        return dict(family)
    status = NOT_APPLICABLE if etf else DATA_UNAVAILABLE
    return {"semantic_status": status, "data": None, "evidence_ids": [], "limitations": []}


def _family_data(family: Mapping[str, Any]) -> dict[str, Any]:
    value = family.get("data")
    return dict(value) if isinstance(value, Mapping) else {}


def _available_value(value: Any) -> bool:
    return value is not None and value != "" and not isinstance(value, (Mapping, list, tuple, set))


def _price_pressure(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for label, keys in (
        ("20-day move", ("twenty_day_pct", "20 Day %")),
        ("60-day move", ("sixty_day_pct", "60 Day %")),
        ("drawdown from period high", ("drawdown_from_period_high_pct",)),
        ("distance from 52-week high", ("distance_from_52w_high_pct",)),
    ):
        value = _number(source, *keys)
        if value is not None:
            items.append({"label": label, "value_pct": value, "provenance": "persisted price history"})
    rsi = _number(source, "rsi", "RSI")
    if rsi is not None:
        items.append({"label": "RSI", "value": rsi, "provenance": "persisted technical evidence"})
    return items


def _transcript_context(family: Mapping[str, Any]) -> dict[str, Any]:
    data = _family_data(family)
    return {
        "semantic_status": family.get("semantic_status", DATA_UNAVAILABLE),
        "fiscal_quarter": data.get("fiscal_quarter"),
        "call_date": data.get("call_date"),
        "management_themes": _items(data.get("management_themes"), limit=4),
        "supported_opportunities": _items(data.get("supported_opportunities"), limit=4),
        "supported_risks": _items(data.get("supported_risks"), limit=4),
        "verified_guidance_statements": _items(data.get("verified_guidance_statements"), limit=4),
        "monitoring_items": _items(data.get("monitoring_items"), limit=4),
        "evidence_ids": list(family.get("evidence_ids") or data.get("source_evidence_ids") or ()),
        "limitations": list(family.get("limitations") or ()),
    }


def build_recovery_decision_story(
    row: Mapping[str, Any], *, evidence_families: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Recovery story without modifying any canonical authority."""
    source = dict(row or {})
    embedded_context = source.get("research_context") if isinstance(source.get("research_context"), Mapping) else {}
    families = dict(embedded_context.get("evidence_families") or {})
    families.update(dict(evidence_families or {}))
    etf = security_type_of(source) == "ETF"

    production_decision = embedded_context.get("production_decision")
    if not isinstance(production_decision, Mapping):
        production_decision = build_production_decision(source)
    else:
        production_decision = dict(production_decision)

    ticker = str(_first(source, "ticker", "Ticker", "symbol") or "UNKNOWN").upper().strip()
    company = str(_first(source, "company", "Company", "company_name", "name") or ticker).strip()
    recovery_score = _number(source, "recovery_score", "Recovery Score")
    recovery_label = _text(source, "recovery_label", "Recovery Label")
    drop_reason = _text(source, "recovery_drop_reason", "Recovery Drop Reason")
    rebound_reason = _text(source, "recovery_rebound_reason", "Recovery Rebound Reason")
    recovery_risk = _text(source, "recovery_risk", "Recovery Risk")

    transcript_family = _family(families, "transcript_intelligence", etf=etf)
    target_family = _family(families, "analyst_price_target_actions", etf=etf)
    insider_family = _family(families, "insider_transactions", etf=etf)
    snapshot_family = _family(families, "analyst_estimate_snapshots", etf=etf)
    transcript = _transcript_context(transcript_family)
    target_data = _family_data(target_family)
    insider_data = _family_data(insider_family)
    snapshot_data = _family_data(snapshot_family)

    price_pressure = _price_pressure(source)
    decline_summary = (
        "Price pressure included " + "; ".join(
            f"{item['label']} of {item['value_pct']:+.1f}%" if "value_pct" in item
            else f"{item['label']} at {item['value']:.1f}"
            for item in price_pressure
        ) + "."
    ) if price_pressure else "Price-path evidence is unavailable."

    confirmed = _items(rebound_reason, limit=6)
    early: list[str] = []
    missing: list[str] = []
    analyst_support = _number(source, "analyst_support_score", "Analyst Support Score")
    news_score = _number(source, "news_sentiment_score", "News Sentiment Score")
    revenue_growth = _number(source, "revenue_growth", "Revenue Growth")
    earnings_growth = _number(source, "earnings_growth", "Earnings Growth")
    volume_ratio = _number(source, "volume_ratio", "Volume Ratio")
    if analyst_support is not None:
        early.append(f"Persisted analyst support is {analyst_support:.0f}/100.")
    else:
        missing.append("Analyst support is unavailable.")
    if news_score is not None:
        early.append(f"Persisted news sentiment score is {news_score:.0f}.")
    else:
        missing.append("Sourced news sentiment is unavailable.")
    if revenue_growth is not None:
        early.append(f"Revenue growth is {revenue_growth * 100:+.1f}%.")
    else:
        missing.append("Revenue-growth evidence is unavailable.")
    if earnings_growth is not None:
        early.append(f"Earnings growth is {earnings_growth * 100:+.1f}%.")
    else:
        missing.append("Earnings-growth evidence is unavailable.")
    if volume_ratio is not None:
        early.append(f"Volume ratio is {volume_ratio:.2f}x.")
    else:
        missing.append("Volume confirmation is unavailable.")

    if recovery_label and "Strong Recovery Candidate" in recovery_label:
        confirmation = "Confirmed by the persisted Recovery methodology"
    elif recovery_label and "Recovery Watchlist" in recovery_label:
        confirmation = "Partial"
    else:
        confirmation = "Not yet confirmed"

    financial_fields = {
        "revenue_growth": revenue_growth,
        "earnings_growth": earnings_growth,
        "gross_margin": _number(source, "gross_profit_margin"),
        "operating_margin": _number(source, "operating_profit_margin"),
        "net_margin": _number(source, "net_profit_margin"),
        "free_cash_flow": _number(source, "free_cash_flow"),
        "cash": _number(source, "cash_and_equivalents"),
        "total_debt": _number(source, "total_debt"),
    }
    earnings_fields = {
        "report_date": _text(source, "latest_earnings_date"),
        "eps_actual": _number(source, "reported_eps", "latest_eps"),
        "eps_estimate": _number(source, "eps_estimate"),
        "eps_surprise_pct": _number(source, "eps_surprise_pct"),
        "revenue_actual": _number(source, "reported_revenue", "latest_revenue"),
        "revenue_estimate": _number(source, "revenue_estimate"),
        "revenue_surprise_pct": _number(source, "revenue_surprise_pct"),
        "next_earnings_date": _text(source, "next_earnings_date"),
    }

    valuation = {
        "atlas_fair_value": _number(source, "atlas_fair_value", "Atlas Fair Value"),
        "expected_return": production_decision.get("decision_expected_return"),
        "wall_street_mean": _number(source, "analyst_target_mean", "Analyst Target"),
        "wall_street_low": _number(source, "analyst_target_low"),
        "wall_street_high": _number(source, "analyst_target_high"),
        "forward_pe": _number(source, "forward_pe"),
        "ev_to_sales": _number(source, "ev_to_sales"),
        "ev_to_ebitda": _number(source, "ev_to_ebitda"),
        "valuation_status": _text(source, "atlas_valuation_status"),
    }
    technical = {
        "state": _text(source, "deterministic_technical_state", "technical_state"),
        "confirmation": confirmation,
        "rsi": _number(source, "rsi"),
        "atr_pct": _number(source, "atr_pct"),
        "sma20": _number(source, "sma20"),
        "sma50": _number(source, "sma50"),
        "sma200": _number(source, "sma200"),
        "support": _number(source, "v42_support_1"),
        "resistance": _number(source, "v42_resistance_1"),
        "entry_low": production_decision.get("entry_low"),
        "entry_high": production_decision.get("entry_high"),
        "stop": production_decision.get("stop"),
        "target_1": production_decision.get("trade_target_1"),
        "target_2": production_decision.get("trade_target_2"),
    }

    catalysts: list[dict[str, Any]] = []
    if earnings_fields["next_earnings_date"]:
        catalysts.append({"text": f"Next earnings checkpoint: {earnings_fields['next_earnings_date']}.", "provenance": "persisted earnings calendar"})
    for item in transcript["monitoring_items"][:3]:
        catalysts.append({"text": str(item), "provenance": transcript["evidence_ids"]})
    headline = _text(source, "latest_news_headline", "top_news_headline")
    news_source = _text(source, "latest_news_source", "top_news_source")
    news_date = _text(source, "latest_news_date")
    if headline and news_source:
        catalysts.append({"text": headline, "source": news_source, "date": news_date, "provenance": "persisted sourced news"})

    risks = []
    if recovery_risk:
        risks.append({"text": recovery_risk, "provenance": "persisted recovery_risk"})
    for item in _items(_first(source, "what_could_go_wrong", "finance_agent_risks", "risk_tags"), limit=5):
        text = str(item)
        if text and all(text != existing["text"] for existing in risks):
            risks.append({"text": text, "provenance": "persisted risk evidence"})
    for item in transcript["supported_risks"][:3]:
        risks.append({"text": str(item), "provenance": transcript["evidence_ids"]})

    invalidation = []
    if technical["stop"] is not None:
        invalidation.append({"text": "A break below the canonical stop would invalidate the current trade boundary.", "value": technical["stop"], "provenance": "production decision"})
    elif technical["support"] is not None:
        invalidation.append({"text": "A sustained break below canonical support would weaken the recovery setup.", "value": technical["support"], "provenance": "persisted technical evidence"})
    if revenue_growth is not None and revenue_growth < 0:
        invalidation.append({"text": "Persistently negative revenue growth is an identified fundamental invalidation risk.", "provenance": "persisted financial evidence"})
    if earnings_growth is not None and earnings_growth < 0:
        invalidation.append({"text": "Persistently negative earnings growth is an identified earnings invalidation risk.", "provenance": "persisted earnings evidence"})

    watch_next: list[dict[str, Any]] = []
    if earnings_fields["next_earnings_date"]:
        watch_next.append({"text": f"Next earnings report on {earnings_fields['next_earnings_date']}.", "provenance": "persisted earnings calendar"})
    watch_next.append({"text": f"Whether technical recovery remains {confirmation.lower()}.", "provenance": "persisted Recovery label"})
    for item in transcript["monitoring_items"][:2]:
        watch_next.append({"text": str(item), "provenance": transcript["evidence_ids"]})
    watch_next.append({"text": snapshot_data.get("status_detail") or ESTIMATE_ACCUMULATION_MESSAGE, "provenance": "analyst estimate snapshot store"})
    if target_family.get("semantic_status") != AVAILABLE:
        watch_next.append({"text": "Whether a verified individual analyst target action becomes available.", "provenance": "analyst target-action availability"})

    evidence_groups = {
        "price": bool(price_pressure),
        "recovery": recovery_score is not None and bool(recovery_label),
        "financial": any(_available_value(value) for value in financial_fields.values()),
        "earnings": any(_available_value(value) for value in earnings_fields.values()),
        "valuation": any(_available_value(value) for value in valuation.values()),
        "technical": any(_available_value(value) for value in technical.values()),
        "analyst_actions": target_family.get("semantic_status") == AVAILABLE,
        "transcript": transcript["semantic_status"] == AVAILABLE,
        "insider": insider_family.get("semantic_status") == AVAILABLE,
        "news": bool(headline and news_source),
    }
    available_count = sum(evidence_groups.values())
    evidence_ids = sorted({
        str(item) for family in families.values() if isinstance(family, Mapping)
        for item in (family.get("evidence_ids") or ()) if item
    })

    return {
        "version": RECOVERY_DECISION_STORY_VERSION,
        "ticker": ticker,
        "company": company,
        "security_type": "ETF" if etf else "EQUITY",
        "production_decision": dict(production_decision),
        "decision_availability": dict(production_decision.get("availability") or {}),
        "recovery_snapshot": {
            "recovery_score": recovery_score,
            "recovery_label": recovery_label,
            "current_price": _number(source, "current_price", "price", "last_price", "Price"),
            "drawdown_pct": _number(source, "drawdown_from_period_high_pct", "distance_from_52w_high_pct"),
            "expected_return": production_decision.get("decision_expected_return"),
            "opportunity": production_decision.get("opportunity"),
            "confidence": production_decision.get("confidence"),
            "evidence_completeness": f"{available_count}/{len(evidence_groups)} evidence groups available",
        },
        "decline_evidence": {"summary": decline_summary, "items": price_pressure, "persisted_reason": drop_reason, "causal_status": "PRICE_PRESSURE_NOT_CAUSAL_ATTRIBUTION"},
        "recovery_evidence": {"confirmed": confirmed, "early_signals": early[:7], "missing_confirmation": missing[:7], "persisted_thesis": _text(source, "recovery_thesis", "Recovery Thesis")},
        "financial_direction": {"semantic_status": AVAILABLE if any(_available_value(v) for v in financial_fields.values()) else DATA_UNAVAILABLE, **financial_fields},
        "earnings_direction": {"semantic_status": AVAILABLE if any(_available_value(v) for v in earnings_fields.values()) else DATA_UNAVAILABLE, **earnings_fields, "estimate_history_status": snapshot_data.get("status_detail") or (NOT_APPLICABLE if etf else ESTIMATE_ACCUMULATION_MESSAGE)},
        "management_analyst_context": {
            "transcript": transcript,
            "analyst_consensus": {"mean": valuation["wall_street_mean"], "low": valuation["wall_street_low"], "high": valuation["wall_street_high"], "count": _number(source, "analyst_count")},
            "target_actions": list(target_data.get("actions") or ()),
            "target_actions_status": target_family.get("semantic_status", DATA_UNAVAILABLE),
            "prior_target_limitation": TARGET_PRIOR_LIMITATION if target_data.get("actions") else None,
            "estimate_history_status": snapshot_data.get("status_detail") or (NOT_APPLICABLE if etf else ESTIMATE_ACCUMULATION_MESSAGE),
        },
        "valuation_context": valuation,
        "technical_confirmation": technical,
        "catalysts": catalysts[:7],
        "primary_risks": risks[:7],
        "invalidation_conditions": invalidation[:6],
        "watch_next": watch_next[:7],
        "evidence_health": {"groups": evidence_groups, "available": available_count, "total": len(evidence_groups)},
        "provenance": {"evidence_ids": evidence_ids, "limitations": [
            "Recovery VNext is presentation-only and does not change Recovery or investment authority.",
            "Political and insider evidence are contextual and non-scoring.",
            "Estimate revisions are unavailable until same-period dated snapshots accumulate.",
        ]},
        "deep_evidence": {
            "price_history": price_pressure,
            "earnings_history": _items(_first(source, "eps_quarters", "revenue_quarters"), limit=12),
            "financials": financial_fields,
            "analyst_target_actions": list(target_data.get("actions") or ()),
            "transcript": transcript,
            "insider_transactions": list(insider_data.get("transactions") or ()),
            "ownership": {"institutional_ownership_pct": _number(source, "institutional_ownership_pct"), "insider_ownership_pct": _number(source, "insider_ownership_pct")},
            "news": _items(_first(source, "recent_headlines"), limit=10),
            "political": _items(_first(source, "political_transactions", "congressional_transactions"), limit=10),
        },
    }


__all__ = [
    "ESTIMATE_ACCUMULATION_MESSAGE", "RECOVERY_DECISION_STORY_VERSION",
    "TARGET_PRIOR_LIMITATION", "build_recovery_decision_story",
]
