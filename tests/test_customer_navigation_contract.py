from pathlib import Path

from services.customer_navigation_contract import (
    CUSTOMER_NAV_CONTRACT_VERSION,
    CUSTOMER_ROUTES,
    internal_routes_allowed,
    migrate_navigation_state,
    role_category,
)


def test_customer_navigation_is_exact_vnext_contract() -> None:
    assert CUSTOMER_NAV_CONTRACT_VERSION == "ATLAS_CUSTOMER_NAV_R1_1"
    assert CUSTOMER_ROUTES == ("Home", "Research", "Watchlist", "Ask ATLAS")
    assert "Earnings" not in CUSTOMER_ROUTES
    assert "Recovery" not in CUSTOMER_ROUTES
    assert "ETFs" not in CUSTOMER_ROUTES


def test_authenticated_navigation_marker_binds_runtime_source_sha() -> None:
    source = Path("app.py").read_text(encoding="utf-8")
    marker = source.split('data-atlas-qa="customer-navigation-contract"', 1)[1]
    assert 'data-atlas-source-sha="{html.escape(BOOTSTRAP_SOURCE_SHA)}"' in marker[:1000]


def test_visual_crawler_resolves_navigation_contract_across_streamlit_frames() -> None:
    source = Path("agents/atlas_visual_crawler_v1.py").read_text(encoding="utf-8")
    method = source.split("async def _customer_navigation_contract", 1)[1]
    assert "_marker_in_streamlit_scopes" in method[:1200]
    resolver = source.split("async def _marker_in_streamlit_scopes", 1)[1]
    assert "for scope in _scopes(page)" in resolver[:1200]
    assert "source_sha == self.expected_deployed_source_sha" in method[:1200]


def test_stale_research_and_other_legacy_routes_migrate() -> None:
    state = {
        "v79_pending_page": "Research Any Ticker",
        "v73_page": "Earnings Intelligence",
        "v784_single_nav": "Watchlist Intelligence",
    }
    migrate_navigation_state(state, allowed_routes=CUSTOMER_ROUTES)
    assert state == {
        "v79_pending_page": "Research",
        "v73_page": "Home",
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


def test_internal_routes_require_explicit_admin_role() -> None:
    assert internal_routes_allowed("admin") is True
    assert internal_routes_allowed("viewer") is False
    assert internal_routes_allowed(None) is False
    assert internal_routes_allowed("") is False


def test_earnings_is_reachable_for_admin_and_denied_to_customer() -> None:
    import ast
    module = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    main = next(node for node in reversed(module.body)
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    internal = next(node.value for node in ast.walk(main)
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "internal_pages"
                            for target in node.targets))
    internal_pages = ast.literal_eval(internal)
    assert "Earnings" in internal_pages
    for role in ("admin", "viewer", None):
        allowed = (*CUSTOMER_ROUTES, *internal_pages) if internal_routes_allowed(role) else CUSTOMER_ROUTES
        state = {"v784_single_nav": "Earnings Intelligence"}
        migrate_navigation_state(state, allowed_routes=allowed)
        assert state["v784_single_nav"] == ("Earnings" if role == "admin" else "Home")
    assert "Earnings" not in CUSTOMER_ROUTES
