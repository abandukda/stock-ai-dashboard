from datetime import datetime, timezone

import pytest

from services.finnhub_freshness_policy import POLICIES, certify_family_freshness


START = datetime(2026, 10, 14, 22, 0, tzinfo=timezone.utc)


def record(payload, captured="2026-10-14T22:00:30+00:00"):
    return {"provenance": {"capture_timestamp": captured}, "payload": payload}


def test_every_authorized_family_has_explicit_policy():
    assert set(POLICIES) == {
        "company_profile", "financial_statements", "basic_financials",
        "historical_ohlcv", "eps_estimates", "ebitda_estimates",
    }


def test_current_run_financial_statement_is_certified_with_period_identity():
    result = certify_family_freshness(
        capability="financial_statements",
        record=record({"reports": [{"fiscal_date": "2026-09-30"}]}),
        acquisition_started_at=START,
        checked_at=datetime(2026, 10, 14, 22, 1, tzinfo=timezone.utc),
    )
    assert result["status"] == "FRESH"
    assert result["latest_effective_period"] == "2026-09-30"


def test_stale_capture_and_future_financial_period_fail_closed():
    with pytest.raises(ValueError, match="STALE_CAPTURE"):
        certify_family_freshness(
            capability="basic_financials", record=record({}, "2026-10-14T21:00:00+00:00"),
            acquisition_started_at=START, checked_at=START,
        )
    with pytest.raises(ValueError, match="PERIOD_AFTER_CAPTURE"):
        certify_family_freshness(
            capability="financial_statements",
            record=record({"reports": [{"fiscal_date": "2026-12-31"}]}),
            acquisition_started_at=START,
            checked_at=datetime(2026, 10, 14, 22, 1, tzinfo=timezone.utc),
        )


def test_market_history_requires_recent_completed_session():
    fresh = certify_family_freshness(
        capability="historical_ohlcv",
        record=record({"timestamps": [1791921600], "completed_session_flags": [True]}),
        acquisition_started_at=START,
        checked_at=datetime(2026, 10, 14, 22, 1, tzinfo=timezone.utc),
    )
    assert fresh["status"] == "FRESH"
    with pytest.raises(ValueError, match="MARKET_SESSION_STALE"):
        certify_family_freshness(
            capability="historical_ohlcv",
            record=record({"timestamps": [1791057600], "completed_session_flags": [True]}),
            acquisition_started_at=START,
            checked_at=datetime(2026, 10, 14, 22, 1, tzinfo=timezone.utc),
        )
