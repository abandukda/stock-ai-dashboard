"""Canonical customer navigation and fail-closed stale-session migration."""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence


CUSTOMER_NAV_CONTRACT_VERSION = "ATLAS_CUSTOMER_NAV_R1_1"
CUSTOMER_ROUTES = ("Home", "Research", "Watchlist", "Ask ATLAS")
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


def internal_routes_allowed(role: object) -> bool:
    """Fail closed: only an explicit admin role may receive internal routes."""
    return str(role or "").strip().lower() == "admin"


def customer_mobile_navigation_css() -> str:
    """All four customer destinations fit without horizontal label clipping."""
    return '''<style>
    @media(max-width:420px){
      [data-testid="stRadio"] [role="radiogroup"]{
        display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
        gap:.3rem!important;overflow:visible!important;width:100%!important;
      }
      [data-testid="stRadio"] label{
        width:100%!important;max-width:100%!important;box-sizing:border-box!important;
        min-width:0!important;white-space:normal!important;
      }
      [data-testid="stRadio"] label p{white-space:normal!important;overflow-wrap:anywhere!important}
    }
    </style>'''
