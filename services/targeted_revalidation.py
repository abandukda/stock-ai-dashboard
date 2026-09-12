"""Presentation-safe targeted revalidation against existing canonical dependencies."""
from __future__ import annotations

from typing import Any, Mapping


VERSION = "ATLAS_TARGETED_REVALIDATION_V1"
CUSTOMER_STATES = {"CURRENT", "REVALIDATION_REQUIRED", "REVALIDATING", "REVALIDATED", "TEMPORARILY_UNAVAILABLE"}


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _market(evaluation: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict((evaluation or {}).get("market_snapshot") or {})


def _relation(price: float | None, plan: Mapping[str, Any]) -> str:
    low, high = _number(plan.get("entry_low")), _number(plan.get("entry_high"))
    if price is None or low is None or high is None:
        return "UNKNOWN"
    return "BELOW_ENTRY" if price < low else "ABOVE_ENTRY" if price > high else "IN_ENTRY"


def assess_targeted_revalidation(
    persisted: Mapping[str, Any] | None, current: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Use existing entry/trade/decision outputs; this function defines no thresholds."""
    prior, fresh = dict(persisted or {}), dict(current or {})
    prior_market, live_market = _market(prior), _market(fresh)
    prior_price = _number(prior_market.get("price"))
    live_price = _number(live_market.get("price"))
    base = {
        "version": VERSION, "live_price": live_price,
        "price_as_of": live_market.get("provider_timestamp"),
        "price_source": live_market.get("provider"), "market_session": live_market.get("market_session"),
        "freshness_status": "CURRENT" if live_market.get("fresh_current_price") is True else "LATEST_REGULAR_CLOSE" if live_market.get("latest_completed_session_valid") is True else "TEMPORARILY_UNAVAILABLE",
        "evidence_id": live_market.get("evidence_id"),
        "source_type": live_market.get("source_type"),
        "customer_label": live_market.get("customer_label"),
        "stale": live_market.get("stale"),
        "received_timestamp": live_market.get("received_timestamp"),
        "freshness_age_seconds": live_market.get("freshness_age_seconds"),
        "feed_health": live_market.get("feed_health"),
        "prior_decision_digest": prior.get("decision_digest"), "new_decision_digest": fresh.get("decision_digest"),
        "trigger_reasons": (), "non_scoring": True,
    }
    if live_price is None:
        return {**base, "state": "TEMPORARILY_UNAVAILABLE", "customer_message": "Current price is temporarily unavailable."}
    if not prior:
        return {**base, "state": "REVALIDATION_REQUIRED", "customer_message": "ATLAS is validating this opportunity against the latest price."}
    prior_plan, fresh_plan = dict(prior.get("trade_plan") or {}), dict(fresh.get("trade_plan") or {})
    triggers = []
    if _relation(prior_price, prior_plan) != _relation(live_price, prior_plan):
        triggers.append("ENTRY_RELATIONSHIP_CHANGED")
    stop = _number(prior_plan.get("stop_loss") if prior_plan.get("stop_loss") is not None else prior_plan.get("stop"))
    target = _number(prior_plan.get("target_1") or prior_plan.get("trade_target_1") or prior_plan.get("target"))
    if stop is not None and live_price <= stop:
        triggers.append("STOP_LEVEL_REACHED")
    if target is not None and live_price >= target:
        triggers.append("TECHNICAL_TARGET_REACHED")
    prior_action = str(dict(prior.get("guidance") or {}).get("state") or "")
    fresh_action = str(dict(fresh.get("guidance") or {}).get("state") or "")
    if fresh and prior_action != fresh_action:
        triggers.append("CANONICAL_ACTION_CHANGED")
    plan_keys = ("entry_low", "entry_high", "stop_loss", "stop", "target_1", "trade_target_1", "target", "risk_reward")
    if fresh_plan and prior_plan and any(_number(fresh_plan.get(key)) != _number(prior_plan.get(key)) for key in plan_keys):
        triggers.append("TRADE_PLAN_CHANGED")
    triggers = tuple(dict.fromkeys(triggers))
    if not triggers:
        return {**base, "state": "CURRENT", "customer_message": None}
    certification = dict(fresh.get("publication_certification") or {})
    projection = dict(fresh.get("certified_customer_evaluation") or {})
    publishable = certification.get("customer_publication_allowed") is True and projection.get("customer_publication_allowed") is True
    if publishable and fresh.get("decision_digest"):
        return {**base, "state": "REVALIDATED", "trigger_reasons": triggers,
                "customer_message": "ATLAS revalidated the opportunity using the latest governed price."}
    return {**base, "state": "REVALIDATION_REQUIRED", "trigger_reasons": triggers,
            "customer_message": "Price has moved materially since this recommendation was certified. ATLAS is revalidating the opportunity."}


__all__ = ["CUSTOMER_STATES", "VERSION", "assess_targeted_revalidation"]
