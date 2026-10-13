from datetime import datetime, timezone
from copy import deepcopy

import pytest

from services.report_card_exchange_calendar import build_xnys_calendar, verify_xnys_calendar


UTC = timezone.utc


def test_calendar_handles_holiday_and_finalized_session_deterministically():
    as_of = datetime(2026, 10, 13, 21, 0, tzinfo=UTC)
    first = build_xnys_calendar(start_date="2026-10-08", as_of=as_of)
    second = build_xnys_calendar(start_date="2026-10-08", as_of=as_of)
    assert first == second
    assert first["trading_sessions"] == ["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"]
    assert first["finalized_session"] == "2026-10-13"
    assert first["session_close_at"] == "2026-10-13T20:00:00+00:00"
    verify_xnys_calendar(first, as_of=as_of)


def test_calendar_handles_early_close_and_dst():
    half_day = build_xnys_calendar(
        start_date="2026-11-25", as_of=datetime(2026, 11, 27, 19, 0, tzinfo=UTC)
    )
    assert half_day["finalized_session"] == "2026-11-27"
    assert half_day["early_close"] is True
    assert half_day["session_close_at"] == "2026-11-27T18:00:00+00:00"

    before_dst = build_xnys_calendar(
        start_date="2026-10-30", as_of=datetime(2026, 10, 30, 21, 0, tzinfo=UTC)
    )
    after_dst = build_xnys_calendar(
        start_date="2026-11-02", as_of=datetime(2026, 11, 2, 22, 0, tzinfo=UTC)
    )
    assert before_dst["session_open_at"].endswith("13:30:00+00:00")
    assert after_dst["session_open_at"].endswith("14:30:00+00:00")


def test_calendar_rejects_unfinalized_and_tampered_evidence():
    with pytest.raises(ValueError, match="FINALIZED_SESSION_REQUIRED"):
        build_xnys_calendar(
            start_date="2026-10-13", as_of=datetime(2026, 10, 13, 19, 0, tzinfo=UTC)
        )
    as_of = datetime(2026, 10, 13, 21, 0, tzinfo=UTC)
    value = build_xnys_calendar(start_date="2026-10-08", as_of=as_of)
    tampered = deepcopy(value)
    tampered["trading_sessions"].append("2026-10-14")
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        verify_xnys_calendar(tampered, as_of=as_of)


def test_calendar_workflow_is_inert_and_pinned():
    source = open(".github/workflows/atlas_report_card_exchange_calendar.yml", encoding="utf-8").read()
    assert "schedule:" not in source
    assert "REPORT_CARD_CALENDAR_PRODUCE_ONCE" in source
    assert "provider" not in source.lower()
    assert "python -m pip install exchange_calendars==4.13.2" in source
