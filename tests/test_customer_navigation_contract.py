from services.customer_navigation_contract import (
    CUSTOMER_NAV_CONTRACT_VERSION,
    CUSTOMER_ROUTES,
    migrate_navigation_state,
    role_category,
)


def test_customer_navigation_is_exact_vnext_contract() -> None:
    assert CUSTOMER_NAV_CONTRACT_VERSION == "ATLAS_CUSTOMER_NAV_VNEXT_1"
    assert CUSTOMER_ROUTES == ("Home", "Research", "Earnings", "Watchlist", "Ask ATLAS")
    assert "Recovery" not in CUSTOMER_ROUTES
    assert "ETFs" not in CUSTOMER_ROUTES


def test_stale_research_and_other_legacy_routes_migrate() -> None:
    state = {
        "v79_pending_page": "Research Any Ticker",
        "v73_page": "Earnings Intelligence",
        "v784_single_nav": "Watchlist Intelligence",
    }
    migrate_navigation_state(state, allowed_routes=CUSTOMER_ROUTES)
    assert state == {
        "v79_pending_page": "Research",
        "v73_page": "Earnings",
        "v784_single_nav": "Watchlist",
    }


def test_unsupported_customer_route_fails_closed_to_home() -> None:
    state = {"v784_single_nav": "Recovery"}
    migrate_navigation_state(state, allowed_routes=CUSTOMER_ROUTES)
    assert state["v784_single_nav"] == "Home"


def test_internal_route_remains_available_only_when_explicitly_allowed() -> None:
    state = {"v784_single_nav": "Recovery"}
    migrate_navigation_state(state, allowed_routes=(*CUSTOMER_ROUTES, "Recovery"))
    assert state["v784_single_nav"] == "Recovery"
    assert role_category(viewer=True) == "customer_viewer"
    assert role_category(viewer=False) == "internal_admin"
