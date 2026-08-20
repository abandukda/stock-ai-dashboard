"""Versioned provisional Free/Premium/Pro/Admin entitlement matrix."""

from __future__ import annotations

from .models import AlertType, Capability, Entitlements, PlanTier


ENTITLEMENT_VERSION = "CUSTOMER_ENTITLEMENTS_V1_BETA"

_BASIC_ALERTS = frozenset({
    AlertType.RECOMMENDATION_CHANGED,
    AlertType.BUY_NOW_ENTERED,
    AlertType.BUY_NOW_EXITED,
    AlertType.EARNINGS_APPROACHING,
})
_ADVANCED_ALERTS = frozenset(AlertType)
_BASE = frozenset({Capability.HOME, Capability.TODAYS_OPPORTUNITIES, Capability.ASK_ATLAS})

_MATRIX = {
    PlanTier.FREE: Entitlements(
        ENTITLEMENT_VERSION, PlanTier.FREE, _BASE, 1, 15, 5, 4,
        _BASIC_ALERTS, True,
    ),
    PlanTier.PREMIUM: Entitlements(
        ENTITLEMENT_VERSION, PlanTier.PREMIUM,
        _BASE | frozenset({
            Capability.FULL_RESEARCH, Capability.FULL_EARNINGS_INTELLIGENCE,
            Capability.ADVANCED_ALERTS, Capability.MARKET_MOVING_NEWS,
            Capability.BULL_RUN_RADAR, Capability.PORTFOLIO_INTELLIGENCE,
        }),
        5, 100, None, 8, _ADVANCED_ALERTS, True,
    ),
    PlanTier.PRO: Entitlements(
        ENTITLEMENT_VERSION, PlanTier.PRO,
        frozenset(Capability) - {Capability.ADMIN_CONTROLS},
        20, 500, None, 8, _ADVANCED_ALERTS, True,
    ),
    PlanTier.ADMIN: Entitlements(
        ENTITLEMENT_VERSION, PlanTier.ADMIN, frozenset(Capability),
        100, 5_000, None, 8, _ADVANCED_ALERTS, True,
    ),
}


def entitlements_for(plan: PlanTier | str) -> Entitlements:
    return _MATRIX[PlanTier(plan)]


__all__ = ["ENTITLEMENT_VERSION", "entitlements_for"]
