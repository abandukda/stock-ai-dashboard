import pytest

from ui.customer_research_v2 import _analyst_context_date


def test_native_provider_calendar_clocks_are_not_assigned_utc():
    assert _analyst_context_date("2023-04-06 00:00:00") == (
        "Apr 6, 2023 · provider calendar date · timezone unspecified"
    )
    assert _analyst_context_date("2026-10-01") == "Oct 1, 2026 · provider calendar date"


def test_aware_source_time_is_converted_before_utc_label():
    assert _analyst_context_date("2026-10-23T01:00:00+05:00") == "Oct 22, 2026 · 8:00 PM UTC"


@pytest.mark.parametrize("value", [None, True, 123, "unavailable", "2026-02-30", "2026-10-01 25:00:00"])
def test_invalid_source_dates_remain_unavailable(value):
    assert _analyst_context_date(value) == "Date unavailable"
