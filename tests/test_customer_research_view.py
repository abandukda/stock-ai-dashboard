from copy import deepcopy
from datetime import datetime, timezone

from services.customer_research_view import Availability, build_customer_research_view, certified_freshness, customer_date
from tests.test_customer_research_v2 import report


def test_view_preserves_certified_projection_and_source_input():
    source = report()
    before = deepcopy(source)
    view = build_customer_research_view(source, now=datetime(2026, 10, 9, tzinfo=timezone.utc))

    assert view.ticker == "NVDA"
    assert view.publication_allowed is True
    assert view.payload["header"]["fair_value"] == 346.05
    assert view.payload["identity"]["evaluation_snapshot"] == "snapshot-nvda"
    assert view.availability["certified_close"] == Availability.CERTIFIED_CURRENT.value
    assert source == before


def test_surface_is_the_minimal_cross_route_authority_contract():
    view = build_customer_research_view(report(), now=datetime(2026, 10, 9, tzinfo=timezone.utc))
    surface = view.surface

    assert surface == {
        "ticker": "NVDA",
        "company": "NVIDIA Corporation",
        "status": "AVAILABLE",
        "action": "BUY_NOW",
        "fair_value": 346.05,
        "opportunity": 85.96,
        "confidence": 87.46,
        "publication_allowed": True,
        "evaluation_snapshot": "snapshot-nvda",
        "candidate_digest": "candidate",
        "publication_digest": "publication",
        "source_sha": "source",
        "certified_close": 186.09,
        "certified_close_at": "2026-10-08T20:00:00Z",
        "certified_close_availability": Availability.CERTIFIED_CURRENT.value,
    }


def test_withheld_surface_fails_closed_without_protected_values():
    source = report()
    source["certified_customer_evaluation"]["customer_publication_allowed"] = False
    surface = build_customer_research_view(source).surface
    assert surface["status"] == "RATING_NOT_PUBLISHED"
    assert surface["action"] == "RATING_NOT_PUBLISHED"
    assert surface["fair_value"] is None
    assert surface["opportunity"] is None
    assert surface["confidence"] is None
    assert surface["publication_allowed"] is False


def test_view_marks_dated_and_withheld_states_without_recomputation():
    source = report()
    view = build_customer_research_view(source, now=datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert view.availability["certified_close"] == Availability.CERTIFIED_DATED.value

    source["certified_customer_evaluation"]["customer_publication_allowed"] = False
    withheld = build_customer_research_view(source)
    assert withheld.publication_allowed is False
    assert withheld.availability == {"publication": Availability.PUBLICATION_WITHHELD.value}


def test_customer_dates_are_human_readable_and_invalid_dates_fail_closed():
    assert customer_date("2026-10-08T20:00:00Z") == "Oct 08, 2026"
    assert customer_date("not-a-date") == "Date unavailable"
    assert certified_freshness(None) == Availability.MISSING_RETAINED_EVIDENCE


def test_research_summary_101_explains_protected_metrics_without_redefining_them():
    source = __import__("pathlib").Path("ui/customer_research_v2.py").read_text()
    assert "Research 101 — what these numbers mean" in source
    assert "not a live quote" in source
    assert "not a guaranteed future price" in source
    assert "not the chance the stock will rise" in source


def test_all_four_customer_routes_are_bound_to_the_shared_projection():
    from pathlib import Path

    sources = {
        "research": Path("ui/customer_research_v2.py").read_text(),
        "watchlist": Path("ui/watchlist_vnext.py").read_text(),
        "ask": Path("engines/ask_atlas_engine.py").read_text(),
        "home": Path("engines/home_guidance_story_v1.py").read_text(),
    }
    assert "build_customer_research_view(report)" in sources["research"]
    assert "build_customer_research_view(row)" in sources["watchlist"]
    assert "build_customer_research_view(report)" in sources["ask"]
    assert "customer_research_surface" in sources["home"]


def test_watchlist_does_not_label_a_raw_row_price_as_live_or_certified():
    source = __import__("pathlib").Path("ui/watchlist_vnext.py").read_text()
    live_renderer = source[source.index("def render_watchlist_vnext"):]
    assert 'price = authority.get("certified_close")' in live_renderer
    assert "this is not a live quote" in live_renderer
    assert 'price, price_as_of = _verified_price(row)' not in live_renderer
