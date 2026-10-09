"""Canonical customer navigation and fail-closed stale-session migration."""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence


CUSTOMER_NAV_CONTRACT_VERSION = "ATLAS_CUSTOMER_NAV_VNEXT_1"
CUSTOMER_ROUTES = ("Home", "Research", "Earnings", "Watchlist", "Ask ATLAS")
ROUTE_ALIASES = {
    "Research Any Ticker": "Research",
    "Earnings Intelligence": "Earnings",
    "Watchlist Intelligence": "Watchlist",
    "Ask AI": "Ask ATLAS",
}
NAVIGATION_STATE_KEYS = ("v79_pending_page", "v73_page", "v784_single_nav")


def migrate_navigation_state(
    state: MutableMapping[str, object],
    *,
    allowed_routes: Sequence[str],
) -> None:
    """Normalize legacy routes and fail unsupported saved routes back to Home."""
    allowed = set(allowed_routes)
    for key in NAVIGATION_STATE_KEYS:
        value = state.get(key)
        if value in ROUTE_ALIASES:
            value = ROUTE_ALIASES[str(value)]
        if value is not None and value not in allowed:
            value = "Home"
        if value is not None:
            state[key] = value


def role_category(*, viewer: bool) -> str:
    return "customer_viewer" if viewer else "internal_admin"
