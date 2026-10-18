from datetime import date, timedelta

from services.report_card_chart import build_chart_projection, normalize_price_history, slice_timeframe


def bars(count=80, *, flat=False):
    start = date(2026, 1, 1)
    result = []
    for i in range(count):
        close = 100 if flat else 100 + i * .2
        result.append({"date": (start + timedelta(days=i)).isoformat(), "close": close,
                       "high": close + 1, "low": close - 1, "volume": 1000,
                       "completed": True})
    return result


PROVENANCE = {"source": "FINNHUB_RETAINED", "evidence_ids": ["raw-1"], "adjustment": "SPLIT_ADJUSTED"}


def test_chart_is_source_bound_and_non_scoring():
    model = build_chart_projection(reversed(bars()), PROVENANCE, signal_date="2026-01-10", signal_price=102,
                                   spy_rows=bars())
    assert model["status"] == "AVAILABLE"
    assert model["classification"] == "EDUCATIONAL_NON_SCORING"
    assert model["bars"][0]["date"] < model["bars"][-1]["date"]
    assert model["support_zone"][0] <= model["support_zone"][1]
    assert model["resistance_zone"][0] <= model["resistance_zone"][1]
    assert model["trendline"]["method"] == "OLS_CLOSE_BY_SESSION"
    assert model["spy_status"] == "AVAILABLE"
    assert model["spy_comparison"][0]["indexed_close"] == 100.0


def test_missing_identity_and_short_history_fail_explicitly():
    assert build_chart_projection(bars(), {},)["status"] == "UNAVAILABLE"
    assert build_chart_projection(bars(10), PROVENANCE)["status"] == "INCOMPLETE"


def test_duplicate_session_is_rejected_not_silently_selected():
    duplicate = bars(20) + [bars(20)[0]]
    assert build_chart_projection(duplicate, PROVENANCE)["status"] == "INVALID"


def test_split_provenance_and_discontinuity_fail_closed():
    assert build_chart_projection(bars(), {"source": "x", "evidence_ids": ["e"]})["status"] == "INCOMPLETE"
    provenance = {**PROVENANCE, "unhandled_split_discontinuity": True}
    assert "discontinuity" in build_chart_projection(bars(), provenance)["message"]


def test_flat_history_has_no_directional_slope():
    assert build_chart_projection(bars(flat=True), PROVENANCE)["trendline"] is None


def test_missing_volume_is_disclosed_but_does_not_invent_price():
    values = bars()
    values[0].pop("volume")
    assert build_chart_projection(values, PROVENANCE)["volume_status"] == "INCOMPLETE_NON_SCORING"


def test_unverified_session_is_never_presented_as_completed_history():
    values = bars()
    values[-1].pop("completed")
    model = build_chart_projection(values, PROVENANCE)
    assert model["status"] == "AVAILABLE"
    assert model["bar_count"] == len(values) - 1
    assert model["as_of"] == values[-2]["date"]


def test_invalid_volume_is_disclosed_without_corrupting_valid_price_history():
    for invalid in (-1, float("inf"), "not-a-number"):
        values = bars()
        values[-1]["volume"] = invalid
        model = build_chart_projection(values, PROVENANCE)
        assert model["status"] == "AVAILABLE"
        assert model["latest_price"] == values[-1]["close"]
        assert model["bars"][-1]["volume"] is None
        assert model["volume_status"] == "INCOMPLETE_NON_SCORING"


def test_timeframe_slice_and_invalid_rows():
    values = bars(100)
    values.append({"date": "bad", "close": 0, "high": 0, "low": 0})
    normalized = normalize_price_history(values)
    assert len(normalized) == 100
    assert len(slice_timeframe(normalized, "1M")) < 100

