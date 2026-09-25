"""Inactive, provider-neutral product contracts for the ATLAS beta foundation.

This module has no acquisition, scoring, valuation, selection, delivery, or
publication side effects.  It freezes boundaries that future activated
services must satisfy.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

VERSION = "ATLAS_PRODUCT_FOUNDATION_V1"
CANONICAL_ACTIONS = (
    "BUY_NOW", "BUILD_A_POSITION", "WAIT_FOR_BETTER_ENTRY",
    "WAIT_FOR_CONFIRMATION", "WATCH_NOT_READY", "AVOID",
    "RATING_NOT_PUBLISHED",
)
AI_ALLOWED_EVIDENCE_TIERS = (
    "CERTIFIED_ATLAS", "CONTEXTUAL_EXTERNAL_EVIDENCE", "TRANSCRIPT_CONTEXT",
)
AI_PROHIBITED_OUTPUTS = (
    "canonical_financial_fact", "fair_value", "opportunity", "confidence",
    "canonical_action", "buy_now_eligibility", "personalized_allocation",
)
MODEL_PORTFOLIO_CONTRACT = {
    "status": "INACTIVE_INTERNAL_SIMULATION_CONTRACT",
    "starting_capital": 100_000,
    "initial_position_pct": 5.0,
    "maximum_holdings": 20,
    "unique_strongest_opportunities_only": True,
    "leverage_allowed": False,
    "cash_allowed": True,
    "forced_investment": False,
    "repeat_consecutive_purchase": False,
    "dividends": "INCLUDED_ONLY_WHEN_GOVERNED_DATA_SUPPORTS_IT",
    "benchmark": "SPY",
    "exit_methodology": "NOT_DEFINED",
    "prohibited_states": ("HOLD", "ADD", "REDUCE", "EXIT"),
}
VOLUME_OPPORTUNITY_CONTEXT_CONTRACT = {
    "status": "INTERFACE_ONLY",
    "inputs": (
        "completed_session_consolidated_volume", "relative_volume",
        "average_volume", "average_dollar_volume", "technical_structure",
        "breakout_state", "liquidity", "catalyst_context",
    ),
    "output": "VOLUME_OPPORTUNITY_CONTEXT",
    "non_scoring": True,
    "may_create_core_buy_now": False,
}
PERSONALIZED_ADVICE_CONTRACT = {
    "v1_status": "PROHIBITED",
    "future_status": "POST_V1_REQUIRES_SEPARATE_PRODUCT_AND_COMPLIANCE_REVIEW",
    "prohibited_promises": (
        "personalized_buy_sell_instructions", "personalized_allocation",
        "invest_amount_into_named_securities", "personalized_suitability",
    ),
}
FINNHUB_ACTIVATION_SEQUENCE = (
    "credential_installation", "license_class_transition", "entitlement_smoke",
    "broad_universe_certification", "provider_authority_review",
    "fresh_immutable_candidate", "release_certification",
    "prospective_report_card_activation",
)


def build_ai_tutor_evidence_package(
    *, ticker: str, certified_atlas: Mapping[str, Any],
    contextual_external: Sequence[Mapping[str, Any]] = (),
    transcript_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a copy-isolated tutor package; missing evidence stays missing."""
    canonical = deepcopy(dict(certified_atlas))
    action = str(canonical.get("canonical_action") or "RATING_NOT_PUBLISHED")
    if action not in CANONICAL_ACTIONS:
        raise ValueError("UNREGISTERED_CANONICAL_ACTION")
    context = [deepcopy(dict(item)) for item in contextual_external]
    transcript = deepcopy(dict(transcript_context or {}))
    return {
        "version": VERSION,
        "ticker": str(ticker).upper(),
        "evidence": {
            "CERTIFIED_ATLAS": canonical,
            "CONTEXTUAL_EXTERNAL_EVIDENCE": context,
            "TRANSCRIPT_CONTEXT": transcript,
        },
        "canonical_action": action,
        "canonical_fair_value": canonical.get("fair_value"),
        "limitations": list(canonical.get("limitations") or ()),
        "response_policy": {
            "explanation_only": True,
            "must_cite_evidence_ids": True,
            "may_infer_missing_values": False,
            "personalized_advice": False,
            "prohibited_outputs": AI_PROHIBITED_OUTPUTS,
        },
    }


def validate_ai_tutor_response(package: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed when an explanation contradicts protected ATLAS outputs."""
    evidence = package.get("evidence") or {}
    known_ids = {
        str(value) for tier in evidence.values()
        for item in ([tier] if isinstance(tier, Mapping) else tier if isinstance(tier, Sequence) and not isinstance(tier, (str, bytes)) else [])
        if isinstance(item, Mapping)
        for value in item.get("evidence_ids", ()) if value
    }
    cited = {str(value) for value in response.get("evidence_ids", ()) if value}
    failures = []
    if response.get("canonical_action") not in (None, package.get("canonical_action")):
        failures.append("CANONICAL_ACTION_CONTRADICTION")
    if response.get("fair_value") not in (None, package.get("canonical_fair_value")):
        failures.append("FAIR_VALUE_CONTRADICTION")
    if cited.difference(known_ids):
        failures.append("UNGROUNDED_EVIDENCE_ID")
    if response.get("personalized_allocation") not in (None, ""):
        failures.append("PERSONALIZED_ADVICE_PROHIBITED")
    return {"valid": not failures, "failures": failures, "grounded_evidence_ids": sorted(cited)}


__all__ = [
    "AI_ALLOWED_EVIDENCE_TIERS", "AI_PROHIBITED_OUTPUTS", "CANONICAL_ACTIONS",
    "FINNHUB_ACTIVATION_SEQUENCE", "MODEL_PORTFOLIO_CONTRACT",
    "PERSONALIZED_ADVICE_CONTRACT", "VERSION", "VOLUME_OPPORTUNITY_CONTEXT_CONTRACT",
    "build_ai_tutor_evidence_package", "validate_ai_tutor_response",
]
