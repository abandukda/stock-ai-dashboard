"""Fail-closed governance for contracted Finnhub families beyond the core executor.

This module records contract readiness.  It does not change production provider
selection, publication, scoring, or the full-universe acquisition families.
"""
from __future__ import annotations

from typing import Any, Mapping

from services.finnhub_shadow_provider import FINNHUB_ESTIMATE_CAPABILITIES


VERSION = "FINNHUB_CONTRACT_GAP_GOVERNANCE_V1"

CONTEXTUAL_CAPABILITIES = frozenset({
    "peers", "ownership", "insider_transactions", "executives", "company_news",
    "sec_filings", "revenue_breakdown", "recommendations", "price_targets",
    "analyst_actions", "earnings_calendar", "stock_earnings", "press_releases",
    "insider_sentiment", "fund_ownership", "institutional_profile",
    "institutional_portfolio", "institutional_ownership", "price_metrics",
    "sector_metrics", "earnings_quality",
})

CONTRACTED_NOT_AUTHORIZED = frozenset({
    *FINNHUB_ESTIMATE_CAPABILITIES, *CONTEXTUAL_CAPABILITIES,
    "dividends", "quote_us", "historical_market_cap",
})


def estimate_bridge(
    profile: Mapping[str, Any], estimate: Mapping[str, Any], *, capability: str,
    price_currency: str | None = None,
) -> dict[str, Any]:
    """Certify only the provider-written unit/currency/period bridge."""
    currency = profile.get("estimate_currency")
    frequency = estimate.get("frequency")
    rows = estimate.get("estimates") if isinstance(estimate.get("estimates"), list) else []
    blockers: list[str] = []
    if capability not in FINNHUB_ESTIMATE_CAPABILITIES:
        blockers.append("NOT_A_CONTRACTED_ESTIMATE_CAPABILITY")
    if not currency:
        blockers.append("ESTIMATE_CURRENCY_MISSING")
    if price_currency and currency and str(price_currency).upper() != str(currency).upper():
        blockers.append("PRICE_ESTIMATE_CURRENCY_MISMATCH")
    if frequency not in {"annual", "quarterly"}:
        blockers.append("ESTIMATE_FREQUENCY_UNRESOLVED")
    if not rows:
        blockers.append("PROVIDER_DATA_UNAVAILABLE")
    for row in rows:
        if not row.get("period"):
            blockers.append("FISCAL_PERIOD_MISSING")
            break
        if row.get("frequency") not in {"annual", "quarterly"}:
            blockers.append("ROW_FREQUENCY_UNRESOLVED")
            break
    return {
        "version": VERSION,
        "status": "CERTIFIED_PROVIDER_CONTRACT" if not blockers else "CONTRACT_MISMATCH",
        "capability": capability,
        "value_scale": "ABSOLUTE_UNITS",
        "currency": currency,
        "basis": "PER_SHARE" if capability in {"eps_estimates", "dps_estimates"} else "MONETARY_ABSOLUTE",
        "frequency": frequency,
        "provider_vintage": "UNAVAILABLE",
        "revision_history": "UNPROVEN",
        "row_count": len(rows),
        "blockers": sorted(set(blockers)),
    }


def forward_route_gate(
    *, route: str, estimate_bridge_result: Mapping[str, Any],
    peer_certified: bool, accounting_bridge_certified: bool = False,
    scenario_evidence_certified: bool = False, wacc_inputs_complete: bool = False,
) -> dict[str, Any]:
    blockers = list(estimate_bridge_result.get("blockers") or ())
    if not peer_certified and route in {"VAL_FORWARD_PE_V1", "VAL_EV_EBITDA_V1"}:
        blockers.append("PEER_EVIDENCE_NOT_CERTIFIED")
    if route == "VAL_FCFF_DCF_V1":
        if not accounting_bridge_certified: blockers.append("ACCOUNTING_BRIDGE_NOT_CERTIFIED")
        if not scenario_evidence_certified: blockers.append("SCENARIO_EVIDENCE_NOT_CERTIFIED")
        if not wacc_inputs_complete: blockers.append("WACC_INPUTS_INCOMPLETE")
    return {"route": route, "status": "ELIGIBLE_COMPLETE" if not blockers else "FAIL_CLOSED",
            "blockers": sorted(set(blockers))}


def authority_state(capability: str, *, live_status: str | None = None,
                    semantics_certified: bool = False, provenance_complete: bool = False) -> str:
    if live_status in {"DATA_UNAVAILABLE", "ENTITLEMENT_UNAVAILABLE"}:
        return "PROVIDER_DATA_UNAVAILABLE"
    if capability in {"live_quote", "quote_us"}:
        return "DISPLAY_ONLY" if live_status == "UNVERIFIED_SHADOW" and provenance_complete else "NOT_CERTIFIED"
    if capability in CONTEXTUAL_CAPABILITIES:
        return "CONTEXTUAL_CERTIFIED" if live_status == "UNVERIFIED_SHADOW" and provenance_complete else "NOT_CERTIFIED"
    if capability in FINNHUB_ESTIMATE_CAPABILITIES or capability in {"historical_market_cap", "dividends"}:
        return "CANONICAL_CERTIFIED" if live_status == "UNVERIFIED_SHADOW" and semantics_certified and provenance_complete else "CONTRACT_PENDING"
    return "NOT_CERTIFIED"


__all__ = ["CONTEXTUAL_CAPABILITIES", "CONTRACTED_NOT_AUTHORIZED", "VERSION",
           "authority_state", "estimate_bridge", "forward_route_gate"]
