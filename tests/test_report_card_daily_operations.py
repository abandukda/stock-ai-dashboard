from datetime import datetime, timezone

import pytest

from services.report_card_daily_operations import (
    AUTOMATION_TOKEN, REQUIRED_CERTIFICATIONS, bounded_call_budget, ordered_catch_up,
    scheduled_wake_decision, simulate_scheduler,
)


def certified():
    return {name: True for name in REQUIRED_CERTIFICATIONS}


@pytest.mark.parametrize("instant", [
    datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc),
    datetime(2026, 12, 15, 23, 30, tzinfo=timezone.utc),
])
def test_dst_safe_wake_accepts_exact_1830_new_york(instant):
    result = scheduled_wake_decision(now=instant, enabled=True, kill_switch=False,
                                     authorization=AUTOMATION_TOKEN, certifications=certified())
    assert result.allowed is True


def test_kill_switch_and_incomplete_certification_fail_closed():
    instant = datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc)
    assert scheduled_wake_decision(now=instant, enabled=True, kill_switch=True,
                                   authorization=AUTOMATION_TOKEN, certifications=certified()).allowed is False
    values = certified(); values["SECOND_CYCLE_RELIABILITY_PASS"] = False
    result = scheduled_wake_decision(now=instant, enabled=True, kill_switch=False,
                                     authorization=AUTOMATION_TOKEN, certifications=values)
    assert result.allowed is False
    assert "SECOND_CYCLE_RELIABILITY_PASS" in result.reason


def test_wrong_dst_wake_and_token_fail_closed():
    wrong = datetime(2026, 7, 15, 23, 30, tzinfo=timezone.utc)
    assert scheduled_wake_decision(now=wrong, enabled=True, kill_switch=False,
                                   authorization=AUTOMATION_TOKEN, certifications=certified()).allowed is False
    right = datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc)
    assert scheduled_wake_decision(now=right, enabled=True, kill_switch=False,
                                   authorization="wrong", certifications=certified()).allowed is False


def test_bounded_budget_counts_horizons_and_retries():
    assert bounded_call_budget(unique_due_tickers=20, due_horizons=1, retry_attempts=0) == 61
    assert bounded_call_budget(unique_due_tickers=20, due_horizons=2, retry_attempts=0) == 61
    assert bounded_call_budget(unique_due_tickers=20, due_horizons=2, retry_attempts=1) == 122
    assert bounded_call_budget(unique_due_tickers=20, due_horizons=0, retry_attempts=0) == 0
    with pytest.raises(ValueError, match="RETRY_LIMIT"):
        bounded_call_budget(unique_due_tickers=20, due_horizons=1, retry_attempts=2)


def test_missed_sessions_are_ordered_and_dst_double_wakes_deduplicate():
    assert ordered_catch_up({20: "2026-11-06", 1: "2026-10-09", 5: "2026-10-15"}) == [
        (1, "2026-10-09"), (5, "2026-10-15"), (20, "2026-11-06")]
    simulation = simulate_scheduler([
        datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc),
        datetime(2026, 7, 15, 23, 30, tzinfo=timezone.utc),
        datetime(2026, 12, 15, 22, 30, tzinfo=timezone.utc),
        datetime(2026, 12, 15, 23, 30, tzinfo=timezone.utc),
    ])
    assert simulation["status"] == "PASS"
    assert len(simulation["accepted_wakes"]) == 2
    assert simulation["provider_calls"] == simulation["ledger_mutations"] == 0
