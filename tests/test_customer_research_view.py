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
