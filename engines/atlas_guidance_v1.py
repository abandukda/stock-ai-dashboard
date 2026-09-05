"""Founder-approved deterministic Guidance V1 gates.

The evaluator consumes already-canonical component values.  It never acquires
evidence, calculates ranking, or substitutes contextual analyst information.
"""

from __future__ import annotations

import os
from typing import Any, Mapping
import math


GUIDANCE_METHODOLOGY_VERSION = "ATLAS_GUIDANCE_V1"
GUIDANCE_POLICY_VERSION = "HOME_MULTI_THESIS_ACTION_V1"
BUY_NOW = "BUY_NOW"
ACCUMULATE = "ACCUMULATE"
WAIT_FOR_ENTRY = "WAIT_FOR_ENTRY"
WAIT_FOR_CONFIRMATION = "WAIT_FOR_CONFIRMATION"
AVOID = "AVOID"
DATA_LIMITED = "DATA_LIMITED"

ACTIONABILITY = {
    BUY_NOW: "ACTIONABLE", ACCUMULATE: "ACTIONABLE",
    WAIT_FOR_ENTRY: "NOT_ACTIONABLE", WAIT_FOR_CONFIRMATION: "NOT_ACTIONABLE",
    AVOID: "NOT_ACTIONABLE", DATA_LIMITED: "UNAVAILABLE",
}

ACCUMULATE_TECHNICAL_STATES = {
    "SETUP_FORMING", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED",
}
CONSTRUCTIVE_TECHNICAL_STATES = ACCUMULATE_TECHNICAL_STATES
OPPORTUNITY_THESES = {
    "QUALITY_GROWTH", "VALUE_RERATING", "RECOVERY", "ATTRACTIVE_ENTRY",
    "BREAKOUT", "DEVELOPING_SETUP",
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _complete_trade_plan(plan: Mapping[str, Any]) -> bool:
    low = _number(plan.get("entry_low"))
    high = _number(plan.get("entry_high"))
    stop = _number(plan.get("stop") if plan.get("stop") is not None else plan.get("stop_loss"))
    targets = [
        _number(plan.get(key)) for key in
        ("target", "target_1", "target_2", "trade_target_1", "trade_target_2")
    ]
    target = next((value for value in targets if value is not None), None)
    return bool(
        low is not None and high is not None and stop is not None and target is not None
        and 0 < stop < low <= high < target
    )


def classify_opportunity_thesis(inputs: Mapping[str, Any]) -> str | None:
    """Classify the primary investment thesis from canonical evidence only.

    This label is explanatory. It does not alter any pillar, Opportunity, or
    Decision Confidence calculation. A BREAKOUT thesis is reserved for an
    actually volume-confirmed canonical breakout.
    """
    technical = dict(inputs.get("technical") or {})
    fundamentals = dict(inputs.get("fundamentals") or {})
    valuation = dict(inputs.get("valuation") or {})
    metrics = dict(inputs.get("decision_metrics") or {})
    recovery = dict(inputs.get("recovery") or {})
    state = str(technical.get("state") or "").upper()
    fundamental_score = _number(fundamentals.get("score"))
    valuation_score = _number(valuation.get("score"))
    expected_return = _number(valuation.get("expected_return"))
    entry_score = _number((metrics.get("entry_quality") or {}).get("score"))
    recovery_score = _number(recovery.get("score"))
    volume_confirmed = (inputs.get("volume") or {}).get("volume_confirmed") is True

    if recovery_score is not None and recovery_score >= 60:
        return "RECOVERY"
    if fundamental_score is not None and fundamental_score >= 75:
        return "QUALITY_GROWTH"
    if valuation_score is not None and valuation_score >= 70 and expected_return is not None and expected_return >= 15:
        return "VALUE_RERATING"
    if state == "BREAKOUT_CONFIRMED" and volume_confirmed:
        return "BREAKOUT"
    if entry_score is not None and entry_score >= 85:
        return "ATTRACTIVE_ENTRY"
    if state in CONSTRUCTIVE_TECHNICAL_STATES:
        return "DEVELOPING_SETUP"
    return None


def evaluate_guidance(inputs: Mapping[str, Any]) -> dict[str, Any]:
    market = dict(inputs.get("market_snapshot") or {})
    technical = dict(inputs.get("technical") or {})
    volume = dict(inputs.get("volume") or {})
    fundamentals = dict(inputs.get("fundamentals") or {})
    risk = dict(inputs.get("risk") or {})
    valuation = dict(inputs.get("valuation") or {})
    plan = dict(inputs.get("trade_plan") or {})

    minimum_missing = []
    price = _number(market.get("price"))
    if price is None or price <= 0 or not market.get("provider_timestamp"):
        minimum_missing.append("PRICE_EVIDENCE_UNAVAILABLE")
    if market.get("fresh_current_price") is not True and market.get("latest_completed_session_valid") is not True:
        minimum_missing.append("CURRENT_MARKET_EVIDENCE_UNAVAILABLE")
    technical_status = str(technical.get("status") or "DATA_UNAVAILABLE").upper()
    technical_state = str(technical.get("state") or "UNAVAILABLE").upper()
    if technical_status != "AVAILABLE" or technical_state in {"", "UNAVAILABLE"}:
        minimum_missing.append("TECHNICAL_STRUCTURE_UNAVAILABLE")
    fundamental_status = str(fundamentals.get("status") or "DATA_UNAVAILABLE").upper()
    if fundamental_status not in {"AVAILABLE", "PARTIAL"} or _number(fundamentals.get("score")) is None:
        minimum_missing.append("BASIC_FUNDAMENTALS_UNAVAILABLE")
    risk_status = str(risk.get("status") or "DATA_UNAVAILABLE").upper()
    if risk_status != "AVAILABLE":
        minimum_missing.append("RISK_EVIDENCE_UNAVAILABLE")

    if minimum_missing:
        state = DATA_LIMITED
        reasons = tuple(minimum_missing)
        return _result(state, reasons, (), inputs)

    opportunity = _number(inputs.get("opportunity"))
    confidence = _number(inputs.get("decision_confidence"))
    coverage = _number(inputs.get("coverage"))
    fundamentals_score = _number(fundamentals.get("score"))
    technical_score = _number(technical.get("score"))
    valuation_score = _number(valuation.get("score"))
    expected_return = _number(valuation.get("expected_return"))
    valuation_published = str(valuation.get("status") or "").upper() == "PUBLISHED" and _number(valuation.get("fair_value")) is not None
    complete_plan = _complete_trade_plan(plan)
    thesis = classify_opportunity_thesis(inputs)

    negatives = []
    if valuation_published and expected_return is not None and expected_return < 0:
        negatives.append("CANONICAL_EXPECTED_RETURN_NEGATIVE")
    if fundamental_status == "AVAILABLE" and fundamentals_score is not None and fundamentals_score < 40:
        negatives.append("CONFIRMED_FUNDAMENTALS_MATERIALLY_WEAK")
    if technical_score is not None and technical_score < 35:
        negatives.append("CONFIRMED_TECHNICAL_MATERIALLY_WEAK")
    elif technical_state == "FAILED_BREAKOUT":
        negatives.append("CONFIRMED_TECHNICAL_FAILED_BREAKOUT")
    if len(negatives) >= 2:
        return _result(AVOID, tuple(negatives), tuple(negatives), inputs, thesis=thesis)

    entry_reasons = []
    if technical_state == "EXTENDED":
        entry_reasons.append("TECHNICAL_STATE_EXTENDED")
    entry_low, entry_high = _number(plan.get("entry_low")), _number(plan.get("entry_high"))
    if price is not None and entry_high is not None and price > entry_high:
        entry_reasons.append("PRICE_ABOVE_ENTRY_RANGE")
    if plan.get("entry_relationship_valid") is False:
        entry_reasons.append("TRADE_PLAN_ENTRY_RELATIONSHIP_INVALID")
    if entry_reasons:
        return _result(WAIT_FOR_ENTRY, tuple(dict.fromkeys(entry_reasons)), tuple(negatives), inputs, thesis=thesis)

    fresh = market.get("fresh_current_price") is True or market.get("latest_completed_session_valid") is True
    volume_confirmed = volume.get("volume_confirmed") is True
    volume_authority_required = inputs.get("positive_action_volume_authority_required") is True
    volume_authority_available = str(volume.get("status") or "").upper() == "AVAILABLE"
    positive_common = bool(
        fresh and opportunity is not None and confidence is not None and coverage is not None
        and fundamentals_score is not None and technical_score is not None
        and valuation_published and valuation_score is not None and expected_return is not None
        and complete_plan
    )
    breakout_gate_passed = bool(
        thesis != "BREAKOUT" or (volume_authority_available and volume_confirmed)
    )
    buy_now = bool(
        positive_common and technical_state in CONSTRUCTIVE_TECHNICAL_STATES
        and breakout_gate_passed
        and opportunity >= 70 and confidence >= 66 and coverage >= 65
        and fundamentals_score >= 58 and technical_score >= 56
        and valuation_score >= 58 and 10 <= expected_return <= 55
    )
    if buy_now:
        return _result(BUY_NOW, ("ALL_BUY_NOW_GATES_PASSED",), tuple(negatives), inputs, thesis=thesis)

    accumulate = bool(
        positive_common and technical_state in ACCUMULATE_TECHNICAL_STATES
        and breakout_gate_passed
        and opportunity >= 62 and confidence >= 56 and coverage >= 58
        and fundamentals_score >= 48 and valuation_score >= 55 and expected_return >= 8
    )
    if accumulate:
        return _result(ACCUMULATE, ("ALL_ACCUMULATE_GATES_PASSED",), tuple(negatives), inputs, thesis=thesis)

    confirmation = []
    if not fresh:
        confirmation.append("MARKET_EVIDENCE_STALE_BUT_LAST_KNOWN_USABLE")
    if technical_state == "SETUP_FORMING":
        confirmation.append("SETUP_STILL_FORMING")
    elif technical_state == "NEAR_BREAKOUT":
        confirmation.append("NEAR_BREAKOUT_NOT_CONFIRMED")
    elif technical_state == "NO_SETUP":
        confirmation.append("NO_ACTIONABLE_TECHNICAL_SETUP")
    if technical_state != "BREAKOUT_CONFIRMED":
        confirmation.append("ACTIONABLE_TECHNICAL_CONFIRMATION_PENDING")
    elif thesis == "BREAKOUT" and not volume_confirmed:
        confirmation.append("BREAKOUT_VOLUME_NOT_CONFIRMED")
    if thesis == "BREAKOUT" and volume_authority_required and not volume_authority_available:
        confirmation.append("VOLUME_CONFIRMATION_UNAVAILABLE")
    if not valuation_published or expected_return is None:
        confirmation.append("VALUATION_CONFIRMATION_UNAVAILABLE")
    if opportunity is None:
        confirmation.append("CANONICAL_OPPORTUNITY_UNAVAILABLE")
    if confidence is None:
        confirmation.append("DECISION_CONFIDENCE_UNAVAILABLE")
    if not complete_plan:
        confirmation.append("TRADE_PLAN_INCOMPLETE")
    if fundamental_status == "PARTIAL":
        confirmation.append("FUNDAMENTAL_CONFIRMATION_PARTIAL")
    return _result(
        WAIT_FOR_CONFIRMATION,
        tuple(dict.fromkeys(confirmation or ("REQUIRED_CONFIRMATION_MISSING",))),
        tuple(negatives), inputs, thesis=thesis,
    )


def _result(state: str, reasons: tuple[str, ...], negatives: tuple[str, ...], inputs: Mapping[str, Any], *, thesis: str | None = None) -> dict[str, Any]:
    return {
        "version": GUIDANCE_METHODOLOGY_VERSION,
        "policy_version": GUIDANCE_POLICY_VERSION,
        "state": state,
        "status": "DATA_UNAVAILABLE" if state == DATA_LIMITED else "AVAILABLE",
        "actionability": ACTIONABILITY[state],
        "reason_codes": reasons,
        "negative_confirmations": negatives,
        "opportunity_thesis": thesis if thesis in OPPORTUNITY_THESES else None,
        "methodology_version": inputs.get("methodology_version"),
        "threshold_version": inputs.get("threshold_version"),
    }


__all__ = [
    "ACCUMULATE", "ACTIONABILITY", "AVOID", "BUY_NOW", "DATA_LIMITED",
    "FOUNDER_GUIDANCE_V1_FLAG", "founder_guidance_v1_enabled",
    "GUIDANCE_METHODOLOGY_VERSION", "GUIDANCE_POLICY_VERSION", "WAIT_FOR_CONFIRMATION", "WAIT_FOR_ENTRY",
    "classify_opportunity_thesis", "evaluate_guidance",
]
FOUNDER_GUIDANCE_V1_FLAG = "ATLAS_FOUNDER_GUIDANCE_V1_ENABLED"


def founder_guidance_v1_enabled() -> bool:
    """Return the single runtime activation boundary; default is fail-closed."""
    return str(os.getenv(FOUNDER_GUIDANCE_V1_FLAG, "false")).strip().lower() in {
        "1", "true", "yes", "on",
    }
