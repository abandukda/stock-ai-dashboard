"""Presentation-only Home story built from immutable production artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable, Mapping

from engines.atlas_guidance_v1 import founder_guidance_v1_enabled
from engines.research_context import build_production_decision
from engines.semantic_fields import analyst_consensus, canonical_atlas_fair_value, atlas_valuation_status, number
from services.on_demand_evaluation_service import evaluate_on_demand


HOME_GUIDANCE_STORY_VERSION = "HOME_GUIDANCE_VNEXT_V1"
GUIDANCE_GROUPS = (
    ("Actionable Now", {"BUY_NOW", "ACCUMULATE"}),
    ("Getting Close", {"WAIT_FOR_CONFIRMATION", "WAIT_FOR_ENTRY"}),
    ("Risk / Avoid", {"AVOID"}),
    ("Data Limited", {"DATA_LIMITED"}),
)

HOME_FIELD_AUTHORITY = {
    "production_rank": "market_full_scan.json immutable file position",
    "guidance": "CANONICAL_INVESTMENT_EVALUATION_V1.guidance",
    "actionability": "CANONICAL_INVESTMENT_EVALUATION_V1.actionability",
    "opportunity": "CANONICAL_INVESTMENT_EVALUATION_V1.opportunity",
    "decision_confidence": "CANONICAL_INVESTMENT_EVALUATION_V1.decision_confidence",
    "scan_conviction": "persisted Full Scan conviction",
    "atlas_fair_value": "ATLAS_VALUATION_V1 published value",
    "atlas_expected_return": "ATLAS_VALUATION_V1 published expected return",
    "technical_state": "canonical technical evaluation state",
    "volume_state": "ATLAS_VOLUME_INTELLIGENCE_V1 state",
    "recovery_score": "recovery_scan.json exact-ticker row",
    "analyst_consensus": "persisted analyst consensus family",
    "trade_plan": "canonical evaluation trade_plan",
    "last_known_price": "persisted Full Scan price observation (never promoted to current quote)",
    "technical_evidence": "persisted Full Scan indicators (context only; never technical state)",
    "volume_evidence": "persisted Full Scan volume observations (context only; never volume state)",
    "fundamentals_evidence": "persisted Full Scan fundamental observations",
    "snapshot_evidence_health": "persisted Full Scan evidence-confidence label",
}

CUSTOMER_ACTION_PRESENTATION = {
    "BUY_NOW": {"label": "BUY NOW", "stars": "★★★★★", "rating": 5.0, "tone": "buy", "instruction": "Entry conditions are satisfied. ATLAS would initiate a position now."},
    "ACCUMULATE": {"label": "BUILD A POSITION", "stars": "★★★★½", "rating": 4.5, "tone": "build", "instruction": "Begin with a partial position and add only as the thesis confirms."},
    "WAIT_FOR_ENTRY": {"label": "WAIT FOR BETTER ENTRY", "stars": "★★★★", "rating": 4.0, "tone": "wait", "instruction": "Do not chase. Wait for price to return to ATLAS's preferred entry area."},
    "WAIT_FOR_CONFIRMATION": {"label": "WAIT FOR CONFIRMATION", "stars": "★★★½", "rating": 3.5, "tone": "wait", "instruction": "Stay patient. The thesis is attractive, but confirmation is incomplete."},
    "DATA_LIMITED": {"label": "WATCH", "stars": "★★½", "rating": 2.5, "tone": "watch", "instruction": "Do not enter yet. Keep it on the watchlist while the setup develops."},
    "AVOID": {"label": "AVOID", "stars": "★", "rating": 1.0, "tone": "avoid", "instruction": "ATLAS would not deploy capital here under current conditions."},
}


def customer_action_presentation(guidance: Any) -> dict[str, Any]:
    return dict(CUSTOMER_ACTION_PRESENTATION.get(str(guidance or "DATA_LIMITED").upper(), CUSTOMER_ACTION_PRESENTATION["DATA_LIMITED"]))


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("rows", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
    return []


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("Ticker") or row.get("symbol") or "").strip().upper()


def _present(value: Any) -> bool:
    return value is not None and value != "" and not isinstance(value, (Mapping, list, tuple, set))


def _technical_status(evaluation: Mapping[str, Any]) -> tuple[str, str]:
    technical = evaluation.get("technical_confirmation") if isinstance(evaluation.get("technical_confirmation"), Mapping) else {}
    return str(technical.get("state") or "UNAVAILABLE"), str(technical.get("status") or "DATA_UNAVAILABLE")


def _reason_copy(code: str) -> str:
    copy = {
        "CURRENT_MARKET_EVIDENCE_UNAVAILABLE": "Fresh market evidence is required.",
        "TECHNICAL_STRUCTURE_UNAVAILABLE": "Canonical technical confirmation is required.",
        "PRICE_EVIDENCE_UNAVAILABLE": "A valid approved price observation is required.",
        "BASIC_FUNDAMENTALS_UNAVAILABLE": "Basic canonical fundamentals are required.",
        "RISK_EVIDENCE_UNAVAILABLE": "Canonical risk evidence is required.",
        "BREAKOUT_VOLUME_NOT_CONFIRMED": "Completed-bar volume confirmation is required.",
        "CANONICAL_OPPORTUNITY_UNAVAILABLE": "Canonical Opportunity must be published.",
        "DECISION_CONFIDENCE_UNAVAILABLE": "Decision Confidence must be published.",
        "TRADE_PLAN_INCOMPLETE": "A complete canonical trade plan is required.",
        "VALUATION_CONFIRMATION_UNAVAILABLE": "Published Atlas valuation confirmation is required.",
        "PRICE_ABOVE_ENTRY_RANGE": "Price must return to an approved entry range.",
        "TECHNICAL_STATE_EXTENDED": "Technical extension must normalize.",
    }
    return copy.get(str(code), str(code).replace("_", " ").capitalize() + ".")


def _evidence_health(evaluation: Mapping[str, Any]) -> str:
    statuses = []
    for key in ("fundamentals", "risk"):
        item = evaluation.get(key) if isinstance(evaluation.get(key), Mapping) else {}
        statuses.append(str(item.get("status") or "DATA_UNAVAILABLE"))
    technical = evaluation.get("technical_confirmation") if isinstance(evaluation.get("technical_confirmation"), Mapping) else {}
    statuses.append(str(technical.get("status") or "DATA_UNAVAILABLE"))
    if statuses and all(status == "AVAILABLE" for status in statuses):
        return "COMPLETE"
    if any(status in {"AVAILABLE", "PARTIAL"} for status in statuses):
        return "PARTIAL"
    return "LIMITED"


def _first_number(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = number(row.get(key))
        if value is not None:
            return value
    return None


def _first_value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _snapshot_evidence(row: Mapping[str, Any], price: float | None) -> dict[str, Any]:
    """Expose persisted observations without promoting them to decision authority."""
    deep = row.get("deep_research_evidence") if isinstance(row.get("deep_research_evidence"), Mapping) else {}
    return {
        "technical": {
            "price": price,
            "rsi": _first_number(row, "rsi"),
            "sma20": _first_number(row, "sma20"),
            "sma50": _first_number(row, "sma50"),
            "sma200": _first_number(row, "sma200") if row.get("sma200") is not None else number(deep.get("sma200")),
            "support": _first_number(row, "v42_support_1", "support"),
            "resistance": _first_number(row, "v42_resistance_1", "resistance"),
            "breakout_setup": row.get("breakout_status") or row.get("setup_status"),
        },
        "volume": {
            "relative_volume": _first_number(row, "volume_ratio", "relative_volume"),
            "average_volume": _first_number(row, "avg_volume_20d", "average_volume"),
            "average_dollar_volume": _first_number(row, "avg_dollar_volume", "dollar_volume"),
        },
        "fundamentals": {
            "revenue_growth": _first_number(row, "revenue_growth"),
            "operating_margin": _first_number(row, "operating_profit_margin"),
            "free_cash_flow": _first_number(row, "free_cash_flow"),
            "cash": _first_number(row, "cash", "cash_and_equivalents"),
            "debt": _first_number(row, "total_debt", "debt"),
        },
        "completeness": row.get("evidence_confidence") or row.get("evidence_completeness"),
    }


def build_home_guidance_candidate(
    row: Mapping[str, Any], *, production_rank: int,
    recovery_row: Mapping[str, Any] | None = None,
    current_evaluation: Mapping[str, Any] | None = None,
    production_snapshot_id: str | None = None,
    production_snapshot_timestamp: Any = None,
) -> dict[str, Any]:
    """Resolve one Home card without ranking or decision recalculation."""
    ticker = _ticker(row)
    production_decision = build_production_decision(row)
    evaluation = dict(current_evaluation or evaluate_on_demand(
        row, context={"production_decision": production_decision, "evidence_registry": {}},
    ))
    guidance = evaluation.get("guidance") if isinstance(evaluation.get("guidance"), Mapping) else {}
    actionability = evaluation.get("actionability") if isinstance(evaluation.get("actionability"), Mapping) else {}
    valuation = evaluation.get("atlas_valuation") if isinstance(evaluation.get("atlas_valuation"), Mapping) else {}
    valuation_status = str(valuation.get("status") or atlas_valuation_status(row) or "DATA_UNAVAILABLE")
    fair_value = valuation.get("fair_value") if valuation_status == "PUBLISHED" else None
    expected_return = valuation.get("expected_return") if valuation_status == "PUBLISHED" and fair_value is not None else None
    street = analyst_consensus(row)
    street_display_allowed = (
        row.get("analyst_targets_commercial_display_allowed") is True
        or str(row.get("analyst_commercial_status") or "").upper() in {"LICENSED", "DISPLAY_ALLOWED"}
    )
    price = _first_number(row, "current_price", "price", "last_price")
    snapshot = _snapshot_evidence(row, price)
    street_upside = (
        round(((street["mean"] / price) - 1) * 100, 1)
        if street.get("mean") is not None and price is not None and price > 0 else None
    )
    reasons = tuple(str(item) for item in guidance.get("reason_codes") or ())
    customer_action = customer_action_presentation(guidance.get("state"))
    technical_state, technical_status = _technical_status(evaluation)
    volume = evaluation.get("volume_intelligence") if isinstance(evaluation.get("volume_intelligence"), Mapping) else {}
    risk = evaluation.get("risk") if isinstance(evaluation.get("risk"), Mapping) else {}
    fundamentals = evaluation.get("fundamentals") if isinstance(evaluation.get("fundamentals"), Mapping) else {}
    market = evaluation.get("market_snapshot") if isinstance(evaluation.get("market_snapshot"), Mapping) else {}
    market_price = number(market.get("price"))
    live_price = market_price if market.get("fresh_current_price") is True else None
    observed_price = live_price if live_price is not None else market_price if market_price is not None else price
    completed_bar = evaluation.get("phase1_completed_bar") if isinstance(evaluation.get("phase1_completed_bar"), Mapping) else {}
    bar_quality = evaluation.get("phase1_bar_quality") if isinstance(evaluation.get("phase1_bar_quality"), Mapping) else {}
    trade_plan = dict(evaluation.get("trade_plan") or {})
    entry_low, entry_high = number(trade_plan.get("entry_low")), number(trade_plan.get("entry_high"))
    entry_relationship = (
        "WITHIN_ENTRY_RANGE" if observed_price is not None and entry_low is not None and entry_high is not None and entry_low <= observed_price <= entry_high else
        "BELOW_ENTRY_RANGE" if observed_price is not None and entry_low is not None and observed_price < entry_low else
        "ABOVE_ENTRY_RANGE" if observed_price is not None and entry_high is not None and observed_price > entry_high else
        "DATA_UNAVAILABLE"
    )
    recovery = dict(recovery_row or {})
    company = row.get("company") or row.get("company_name") or row.get("name") or ticker
    return {
        "ticker": ticker,
        "company": str(company),
        "production_rank": int(production_rank),
        "production_snapshot_id": production_snapshot_id,
        "production_snapshot_timestamp": production_snapshot_timestamp,
        "production_source_artifact": "market_full_scan.json",
        "snapshot_membership": "CURRENT_FULL_SCAN",
        "guidance": str(guidance.get("state") or "DATA_LIMITED"),
        "customer_action": customer_action,
        "guidance_status": str(guidance.get("status") or "DATA_UNAVAILABLE"),
        "actionability": str(actionability.get("status") or guidance.get("actionability") or "UNAVAILABLE"),
        "opportunity": evaluation.get("opportunity"),
        "decision_confidence": evaluation.get("decision_confidence"),
        "scan_conviction": number(row.get("conviction") if row.get("conviction") is not None else row.get("conviction_score")),
        "atlas_fair_value": fair_value,
        "atlas_valuation_status": valuation_status,
        "atlas_expected_return": expected_return,
        "atlas_expected_return_status": "AVAILABLE" if expected_return is not None else "DATA_UNAVAILABLE",
        "technical_state": technical_state,
        "technical_status": technical_status,
        "volume_state": str(volume.get("state") or "UNAVAILABLE"),
        "volume_status": str(volume.get("status") or "DATA_UNAVAILABLE"),
        "fundamentals_status": str(fundamentals.get("status") or "DATA_UNAVAILABLE"),
        "risk_status": str(risk.get("status") or "DATA_UNAVAILABLE"),
        "trade_plan_status": "AVAILABLE" if (evaluation.get("trade_plan") or {}) else "DATA_UNAVAILABLE",
        "reason_codes": reasons,
        "why_atlas": tuple(_reason_copy(code) for code in reasons[:3]),
        "what_changes_guidance": tuple(_reason_copy(code) for code in reasons[:3]),
        "evidence_health": _evidence_health(evaluation),
        "methodology_version": evaluation.get("methodology_version"),
        "evaluation_timestamp": evaluation.get("evaluated_at"),
        "market_source_type": str((evaluation.get("market_snapshot") or {}).get("source_type") or "UNAVAILABLE"),
        "market_customer_label": str((evaluation.get("market_snapshot") or {}).get("customer_label") or "Market evidence unavailable"),
        "current_price": live_price,
        "display_price": observed_price,
        "display_price_label": "Current Price" if live_price is not None else str(market.get("customer_label") or ("Last-known Price" if observed_price is not None else "Price unavailable")),
        "market_evidence": {
            "status": "LIVE" if live_price is not None else ("LAST_KNOWN" if market_price is not None else "UNAVAILABLE"),
            "provider": market.get("provider"), "source_type": market.get("source_type"),
            "market_session": market.get("market_session"), "stale": market.get("stale"),
            "provider_timestamp": market.get("provider_timestamp"),
            "received_timestamp": market.get("received_timestamp"),
            "freshness_age_seconds": market.get("freshness_age_seconds"),
            "feed_health": market.get("feed_health"),
            "evidence_id": (market.get("evidence_id") or (evaluation.get("market_snapshot") or {}).get("evidence_id")),
            "methodology_version": market.get("source_methodology_version") or market.get("version"),
        },
        "latest_completed_bar": dict(completed_bar),
        "completed_bar_quality": dict(bar_quality),
        "home_chart": dict(evaluation.get("phase1_home_chart") or {}),
        "last_known_price": price,
        "last_known_price_label": "Persisted / last-known price" if price is not None else "Persisted price unavailable",
        "technical_evidence": snapshot["technical"],
        "canonical_technical_evidence": dict((evaluation.get("technical_confirmation") or {}).get("evidence") or {}),
        "volume_evidence": snapshot["volume"],
        "fundamentals_evidence": {
            **snapshot["fundamentals"],
            "revenue": _first_number(row, "latest_revenue", "reported_revenue", "revenue"),
            "eps": _first_number(row, "latest_eps", "reported_eps", "eps"),
            "gross_margin": _first_number(row, "gross_profit_margin", "gross_margin"),
            "net_margin": _first_number(row, "net_profit_margin", "net_margin"),
            "operating_cash_flow": _first_number(row, "operating_cash_flow"),
            "net_cash": _first_number(row, "net_cash"),
            "profitability_evidence": _first_value(row, "finance_agent_summary", "financial_summary"),
        },
        "company_evidence": {
            "forward_eps": _first_number(row, "forward_eps", "eps_forward"),
            "forward_revenue": _first_number(row, "forward_revenue", "revenue_forward"),
            "earnings_growth": _first_number(row, "earnings_growth", "eps_growth"),
            "latest_earnings_date": _first_value(row, "latest_earnings_date", "earnings_date"),
            "reported_eps": _first_number(row, "reported_eps"),
            "eps_estimate": _first_number(row, "eps_estimate"),
            "eps_surprise_pct": _first_number(row, "eps_surprise_pct", "earnings_surprise"),
            "reported_revenue": _first_number(row, "reported_revenue"),
            "revenue_estimate": _first_number(row, "revenue_estimate"),
            "revenue_surprise_pct": _first_number(row, "revenue_surprise_pct"),
            "next_earnings_date": row.get("next_earnings_date") or row.get("earnings_date"),
            "estimate_revision": _first_value(row, "estimate_revision", "estimate_revision_trend", "analyst_revision_trend"),
            "estimate_contributor_count": _first_number(row, "estimate_contributor_count", "earnings_estimate_count"),
            "industry": row.get("industry"), "sector": row.get("sector"),
            "business_summary": _first_value(row, "business_summary", "company_description", "description"),
            "business_kpis": _first_value(row, "approved_business_kpis", "business_kpis", "key_business_metrics"),
            "primary_risk": _first_value(row, "primary_risk", "finance_agent_risks", "risk_tags"),
        },
        "snapshot_evidence_health": snapshot["completeness"],
        "trade_plan": trade_plan,
        "entry_relationship": entry_relationship,
        "wall_street": {
            "rating": row.get("recommendation_key") if street_display_allowed else None,
            "analyst_count": street.get("count") if street_display_allowed else None,
            "mean_target": street.get("mean") if street_display_allowed else None,
            "low_target": street.get("low") if street_display_allowed else None,
            "high_target": street.get("high") if street_display_allowed else None,
            "implied_upside": street_upside if street_display_allowed else None,
            "target_actions": tuple(row.get("phase1_target_actions") or ()),
            "recent_rating_action": _first_value(row, "recent_analyst_action", "latest_upgrade_downgrade"),
            "commercial_display_status": "DISPLAY_ALLOWED" if street_display_allowed else "COMMERCIAL_LICENSE_UNCONFIRMED",
        },
        "recent_catalysts": tuple(
            item for item in (row.get("recent_headlines") or row.get("news_evidence") or ())
            if isinstance(item, Mapping) and (
                item.get("commercial_display_allowed") is True
                or str(item.get("commercial_status") or "").upper() in {"LICENSED", "DISPLAY_ALLOWED"}
            ) and (item.get("evidence_id") or item.get("id"))
            and (item.get("publisher") or item.get("source"))
        )[:3],
        "recovery": {
            "score": recovery.get("recovery_score"),
            "state": recovery.get("recovery_label") or recovery.get("recovery_state"),
            "reason": recovery.get("recovery_rebound_reason") or recovery.get("recovery_thesis"),
            "snapshot_timestamp": recovery.get("scan_time") or recovery.get("generated_at"),
        },
        "production_decision": dict(production_decision),
        "evaluation": evaluation,
        "atlas_ai_view": dict(evaluation.get("atlas_ai_view") or {}),
        "presentation_mode": "ACTIVE" if founder_guidance_v1_enabled() and current_evaluation is not None else "PREVIEW",
    }


def build_home_guidance_story(
    full_scan_payload: Any, recovery_payload: Any, *, watchlist_tickers: Iterable[str] = (),
    current_evaluations: Mapping[str, Mapping[str, Any]] | None = None,
    scan_timestamp: Any = None,
) -> dict[str, Any]:
    full_rows = _rows(full_scan_payload)
    recovery_payload_rows = _rows(recovery_payload)
    recovery_rows = {_ticker(row): row for row in recovery_payload_rows if _ticker(row)}
    evaluations = {str(key).upper(): value for key, value in (current_evaluations or {}).items()}
    timestamp = scan_timestamp or next((row.get("scan_time") or row.get("generated_at") for row in full_rows if row.get("scan_time") or row.get("generated_at")), None)
    payload_identity = full_scan_payload if isinstance(full_scan_payload, Mapping) else {}
    snapshot_id = str(
        payload_identity.get("snapshot_id") or payload_identity.get("scan_id") or
        payload_identity.get("artifact_id") or
        hashlib.sha256(json.dumps(full_rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    )
    cards = [
        build_home_guidance_candidate(
            row, production_rank=index, recovery_row=recovery_rows.get(_ticker(row)),
            current_evaluation=evaluations.get(_ticker(row)),
            production_snapshot_id=snapshot_id, production_snapshot_timestamp=timestamp,
        )
        for index, row in enumerate(full_rows, start=1)
        if _ticker(row)
    ]
    groups = [
        {"title": title, "states": tuple(sorted(states)), "cards": [card for card in cards if card["guidance"] in states]}
        for title, states in GUIDANCE_GROUPS
    ]
    watched = {str(value).strip().upper() for value in watchlist_tickers if str(value).strip()}
    cards_by_ticker = {card["ticker"]: card for card in cards}
    recovery_cards = []
    for recovery_row in recovery_payload_rows:
        ticker = _ticker(recovery_row)
        if not ticker:
            continue
        if ticker in cards_by_ticker:
            recovery_cards.append(cards_by_ticker[ticker])
            continue
        recovery_cards.append({
            "ticker": ticker,
            "company": str(recovery_row.get("company") or recovery_row.get("company_name") or ticker),
            "production_rank": None,
            "snapshot_membership": "CURRENT_RECOVERY_ONLY",
            "production_snapshot_id": None,
            "production_snapshot_timestamp": None,
            "production_source_artifact": None,
            "recovery": {
                "score": recovery_row.get("recovery_score"),
                "state": recovery_row.get("recovery_label") or recovery_row.get("recovery_state"),
                "reason": recovery_row.get("recovery_rebound_reason") or recovery_row.get("recovery_thesis"),
                "snapshot_timestamp": recovery_row.get("scan_time") or recovery_row.get("generated_at"),
                "source_artifact": "recovery_scan.json",
            },
        })
    active = founder_guidance_v1_enabled() and bool(evaluations)
    return {
        "version": HOME_GUIDANCE_STORY_VERSION,
        "mode": "ACTIVE" if active else "PREVIEW",
        "title": "ATLAS Today",
        "status_label": "Current ATLAS Guidance" if active else "Founder Guidance Preview",
        "freshness_label": "Snapshot Guidance — based on latest available ATLAS evidence",
        "scan_timestamp": timestamp,
        "production_snapshot_id": snapshot_id,
        "production_source_artifact": "market_full_scan.json",
        "candidate_count": len(cards),
        "groups": groups,
        "cards": cards,
        "recovery_cards": recovery_cards,
        "watchlist_cards": [card for card in cards if card["ticker"] in watched],
        "technical_cards": [card for card in cards if card["technical_status"] == "AVAILABLE"],
        "what_changed": {"status": "DATA_UNAVAILABLE", "message": "What Changed is not yet available for this evaluation snapshot."},
        "field_authority": dict(HOME_FIELD_AUTHORITY),
    }


__all__ = [
    "CUSTOMER_ACTION_PRESENTATION", "GUIDANCE_GROUPS", "HOME_FIELD_AUTHORITY", "HOME_GUIDANCE_STORY_VERSION",
    "build_home_guidance_candidate", "build_home_guidance_story", "customer_action_presentation",
]
