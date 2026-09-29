from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from services.report_card_governance import (
    AMBIGUOUS_BAR_RULE, MODEL_PORTFOLIO_FILL_ASSUMPTION, CorporateActionEvent,
    GovernedCeiling, PipelineState, PositionExitType, REPORT_CARD_ACTIVATION_READY,
    REPORT_CARD_PROSPECTIVE_ACTIVE, SignalLifecycleEvent, SignalOutcome,
    append_immutable, assert_signal_may_execute, build_corporate_action, build_long_term_buy_range,
    build_long_term_signal, build_swing_signal, classify_long_term_gap,
    build_position_exit, evaluate_portfolio_capacity, first_qualifying_long_term_execution,
    pipeline_public_message, portfolio_performance_population,
    open_model_portfolio_position, public_report_allowed, record_prospective_execution,
    record_prospective_signal, resolve_daily_bar_target_stop, signal_quality_population,
    summarize_signal_outcomes, swing_position_size,
)


class Calendar:
    """Deterministic exchange-session fixture with holiday, half-day and DST closes."""
    closes = {
        "2026-11-25": "2026-11-25T21:00:00+00:00",
        # Thanksgiving is intentionally absent.
        "2026-11-27": "2026-11-27T18:00:00+00:00",  # half day
        "2026-11-30": "2026-11-30T21:00:00+00:00",
        "2026-12-01": "2026-12-01T21:00:00+00:00",
        "2026-12-02": "2026-12-02T21:00:00+00:00",
        "2027-03-12": "2027-03-12T21:00:00+00:00",
        "2027-03-15": "2027-03-15T20:00:00+00:00",  # after DST change
        "2027-03-16": "2027-03-16T20:00:00+00:00",
        "2027-03-17": "2027-03-17T20:00:00+00:00",
        "2027-03-18": "2027-03-18T20:00:00+00:00",
    }

    def session_at_or_after(self, timestamp):
        day = timestamp.date().isoformat()
        return next(key for key in self.closes if key >= day)

    def next_sessions(self, session, count):
        keys = list(self.closes)
        start = keys.index(session)
        return keys[start:start + count]

    def session_close(self, session):
        return datetime.fromisoformat(self.closes[session])

    def is_regular_hours(self, timestamp):
        return 14 <= timestamp.hour <= 21


def ceiling(kind, value, *, applicable=True, certified=True):
    return GovernedCeiling(kind, value, applicable, certified, (f"E-{kind}",))


def buy_range(**overrides):
    values = dict(
        buy_range_lower=90, preferred_entry=95, buy_range_upper=99,
        valuation_ceiling=ceiling("VALUATION", 105), technical_ceiling=ceiling("TECHNICAL", 100),
        risk_reward_ceiling=ceiling("RISK_REWARD", 102), other_ceilings=(),
    )
    values.update(overrides)
    return build_long_term_buy_range(**values)


def long_term_payload(**overrides):
    values = {
        "ticker": "AAA", "stable_security_id": "SEC-AAA", "signal_timestamp": "2026-11-25T15:00:00Z",
        "snapshot_timestamp": "2026-11-25T14:59:00Z", "observable_price_at_signal": 95,
        "buy_range": buy_range(), "fair_value": 120, "stop_or_invalidation_level": 80,
        "action": "BUY_NOW", "opportunity": 82, "confidence": 78,
        "six_pillars": {"valuation": 80}, "valuation_methods": ["P_FCF", "FORWARD_PE"],
        "valuation_outputs": {"fair_value": 120}, "valuation_reconciliation": {"status": "PASS"},
        "scenario_evidence": {"status": "PASS"}, "technical_state": {"trend": "UP"},
        "volume_state": {"status": "PASS"}, "risk_state": {"status": "PASS"},
        "market_regime": "NORMAL", "sector_context": {"sector": "Tech"},
        "provider_authority_version": "P1", "methodology_version": "M1",
        "normalization_version": "N1", "candidate_digest": "C1", "evidence_ids": ["E1"],
        "raw_hashes": ["H1"], "publication_state": "CUSTOMER_PUBLISHABLE_CERTIFIED",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(("changed", "expected"), [
    ({"valuation_ceiling": ceiling("VALUATION", 98)}, "VALUATION"),
    ({"technical_ceiling": ceiling("TECHNICAL", 97)}, "TECHNICAL"),
    ({"risk_reward_ceiling": ceiling("RISK_REWARD", 96)}, "RISK_REWARD"),
])
def test_each_governed_ceiling_can_bind(changed, expected):
    result = buy_range(buy_range_upper=95, **changed)
    assert result.binding_ceiling_type == expected
    assert result.max_buy_price == result.binding_ceiling_value


def test_multiple_ceilings_use_min_and_persist_components():
    result = buy_range(other_ceilings=(ceiling("LIQUIDITY", 94),), preferred_entry=93, buy_range_upper=94)
    assert result.max_buy_price == 94 and result.binding_ceiling_type == "LIQUIDITY"
    assert result.valuation_ceiling.value == 105 and result.technical_ceiling.value == 100


def test_uncertified_applicable_ceiling_and_out_of_range_fail_closed():
    with pytest.raises(ValueError, match="APPLICABLE_CEILING_NOT_CERTIFIED"):
        buy_range(technical_ceiling=ceiling("TECHNICAL", 100, certified=False))
    with pytest.raises(ValueError, match="BUY_RANGE_EXCEEDS"):
        buy_range(buy_range_upper=101)


def test_signal_expiration_uses_five_exchange_sessions_and_half_day():
    signal = build_long_term_signal(long_term_payload(), calendar=Calendar())
    assert signal.signal_expiration_timestamp == "2026-12-02T21:00:00+00:00"
    assert "2026-11-26" not in signal.signal_expiration_timestamp


def test_dst_calendar_close_is_not_24_hour_arithmetic():
    payload = long_term_payload(signal_timestamp="2027-03-12T15:00:00Z", snapshot_timestamp="2027-03-12T14:59:00Z")
    signal = build_long_term_signal(payload, calendar=Calendar())
    assert signal.signal_expiration_timestamp == "2027-03-18T20:00:00+00:00"


def test_gap_up_waits_gap_down_requires_new_exact_revalidation():
    signal = build_long_term_signal(long_term_payload(), calendar=Calendar())
    assert classify_long_term_gap(signal, 101) == "NO_EXECUTION_PENDING_CERTIFIED_RANGE_OR_EXPIRATION"
    assert classify_long_term_gap(signal, 89) == "EXACT_SNAPSHOT_REVALIDATION_REQUIRED_NO_OLD_SIGNAL_FILL"
    assert classify_long_term_gap(signal, 95) == "IN_CERTIFIED_BUY_RANGE"


def test_first_qualifying_trade_prohibits_pre_signal_previous_close_vwap_and_extended_hours():
    signal = build_long_term_signal(long_term_payload(), calendar=Calendar())
    trades = [
        {"timestamp": "2026-11-25T14:59:59Z", "price": 95, "price_source": "PRE_SIGNAL"},
        {"timestamp": "2026-11-25T22:00:00Z", "price": 94, "price_source": "EXTENDED_HOURS"},
        {"timestamp": "2026-11-25T15:01:00Z", "price": 101, "price_source": "TRADE"},
        {"timestamp": "2026-11-25T15:02:00Z", "price": 96, "price_source": "CERTIFIED_TRADE_SEQUENCE"},
        {"timestamp": "2026-11-25T15:03:00Z", "price": 95, "price_source": "VWAP"},
    ]
    execution = first_qualifying_long_term_execution(signal, trades, calendar=Calendar())
    assert execution.execution_price == 96
    assert execution.price_source == "CERTIFIED_TRADE_SEQUENCE"
    assert execution.fill_assumption == MODEL_PORTFOLIO_FILL_ASSUMPTION


def test_range_never_reached_returns_no_execution():
    signal = build_long_term_signal(long_term_payload(), calendar=Calendar())
    assert first_qualifying_long_term_execution(signal, [
        {"timestamp": "2026-11-25T15:01:00Z", "price": 110, "price_source": "TRADE"},
    ], calendar=Calendar()) is None


def swing_payload(**overrides):
    values = {
        "ticker": "AAA", "stable_security_id": "SEC-AAA", "signal_timestamp": "2026-11-25T15:00:00Z",
        "setup_type": "BREAKOUT", "setup_state": "LONG", "entry_range_lower": 50,
        "entry_range_upper": 51, "preferred_entry": 50.5, "max_entry": 51.5, "stop": 48,
        "target_1": 56, "target_2": 60, "atr": 2, "risk_per_share": 2.5, "reward_risk": 2.2,
        "trend_state": "UP", "rsi": 58, "moving_average_state": "ABOVE", "volume_confirmation": "YES",
        "relative_strength": 1.1, "market_regime": "NORMAL", "sector_state": "LEADING",
        "catalyst_context": {}, "signal_confidence": 75, "long_term_action_at_signal_time": "AVOID",
        "long_term_signal_id": None, "long_term_reason_category": "VALUATION",
        "methodology_version": "SWING-M1", "snapshot_digest": "D1", "evidence_ids": ["E1"],
    }
    values.update(overrides)
    return values


def test_long_term_swing_conflict_is_retained_not_suppressed():
    signal = build_swing_signal(swing_payload())
    assert signal.long_term_swing_conflict is True
    assert signal.long_term_action_at_signal_time == "AVOID"
    assert signal.long_term_reason_category == "VALUATION"
    assert signal.expiration_sessions == 1


def test_swing_setup_requires_registered_deterministic_expiration():
    with pytest.raises(ValueError, match="EXPIRATION_RULE_UNREGISTERED"):
        build_swing_signal(swing_payload(setup_type="UNDEFINED"))


def test_swing_risk_sizing_and_conservative_daily_bar_ordering():
    assert swing_position_size(portfolio_equity=100_000, risk_per_trade_percentage=.01,
                               entry_price=50, stop_price=48) == 500
    assert resolve_daily_bar_target_stop(low=47, high=57, stop=48, target=56) == AMBIGUOUS_BAR_RULE


def test_pipeline_failure_states_cannot_masquerade_as_no_signals():
    no_signals = pipeline_public_message(PipelineState.NO_QUALIFYING_SIGNALS)
    assert "no qualifying" in no_signals
    for state in (PipelineState.EVALUATION_NOT_PERFORMED, PipelineState.EVALUATION_INCOMPLETE,
                  PipelineState.PROVIDER_DATA_FAILURE, PipelineState.PUBLICATION_FAILURE):
        assert "no qualifying" not in pipeline_public_message(state)


@pytest.mark.parametrize("event_type", [
    "SPLIT", "DIVIDEND", "TICKER_CHANGE", "MERGER", "CASH_ACQUISITION",
    "STOCK_ACQUISITION", "BANKRUPTCY", "DELISTING",
])
def test_corporate_actions_preserve_stable_identity(event_type):
    event = build_corporate_action({
        "stable_security_id": "SEC-AAA", "event_type": event_type,
        "effective_timestamp": "2027-01-04T14:30:00Z", "old_ticker": "AAA", "new_ticker": "BBB",
        "terms": {"ratio": 2}, "evidence_ids": ["E1"], "raw_hashes": ["H1"],
    })
    assert isinstance(event, CorporateActionEvent) and event.stable_security_id == "SEC-AAA"


def test_methodology_v1_record_is_immutable_after_v2_and_rerun_is_deterministic(tmp_path):
    signal_v1 = build_long_term_signal(long_term_payload(methodology_version="M1"), calendar=Calendar())
    same = build_long_term_signal(long_term_payload(methodology_version="M1"), calendar=Calendar())
    assert signal_v1 == same
    path = tmp_path / "long_term_signals.jsonl"
    assert append_immutable(path, signal_v1, identity_field="signal_id") is True
    assert append_immutable(path, same, identity_field="signal_id") is False
    rewritten = replace(signal_v1, methodology_version="M2")
    with pytest.raises(ValueError, match="IMMUTABLE_RECORD_CONFLICT"):
        append_immutable(path, rewritten, identity_field="signal_id")
    assert json.loads(path.read_text())["methodology_version"] == "M1"


def test_report_card_remains_off_blocks_signals_portfolio_and_public_output(tmp_path):
    signal = build_long_term_signal(long_term_payload(), calendar=Calendar())
    assert REPORT_CARD_PROSPECTIVE_ACTIVE is False
    with pytest.raises(PermissionError, match="PROSPECTIVE_INACTIVE"):
        record_prospective_signal(tmp_path / "signals.jsonl", signal)
    execution = first_qualifying_long_term_execution(signal, [
        {"timestamp": "2026-11-25T15:01:00Z", "price": 96, "price_source": "TRADE"},
    ], calendar=Calendar())
    with pytest.raises(PermissionError, match="PROSPECTIVE_INACTIVE"):
        record_prospective_execution(tmp_path / "executions.jsonl", execution)
    with pytest.raises(PermissionError, match="PROSPECTIVE_INACTIVE"):
        open_model_portfolio_position(signal, execution)
    assert not (tmp_path / "signals.jsonl").exists()
    assert not (tmp_path / "executions.jsonl").exists()
    assert REPORT_CARD_ACTIVATION_READY is False
    assert public_report_allowed() is False


def test_signal_issuance_is_independent_of_portfolio_capacity():
    signal = build_long_term_signal(long_term_payload(), calendar=Calendar())
    assert signal.action == "BUY_NOW"
    event = evaluate_portfolio_capacity(
        signal_id=signal.signal_id, signal_kind=signal.signal_kind,
        event_timestamp="2026-11-25T15:02:00Z", executable_price=96,
        capital_available=False, position_slot_available=True,
    )
    assert event.outcome == "SIGNAL_NOT_FUNDED_PORTFOLIO_FULL"
    assert event.terminal_for_execution is True


def test_unfunded_executable_signal_is_terminal_and_never_queued_for_later_slot():
    signal = build_long_term_signal(long_term_payload(), calendar=Calendar())
    event = evaluate_portfolio_capacity(
        signal_id=signal.signal_id, signal_kind="LONG_TERM",
        event_timestamp="2026-11-25T15:02:00Z", executable_price=96,
        capital_available=True, position_slot_available=False,
    )
    with pytest.raises(PermissionError, match="NO_QUEUE_NEW_CERTIFIED_SIGNAL_REQUIRED"):
        assert_signal_may_execute(signal.signal_id, [event])
    # A new signal with a new snapshot and timestamp has a new identity and is independently eligible.
    new_signal = build_long_term_signal(long_term_payload(
        signal_timestamp="2026-11-27T15:00:00Z", snapshot_timestamp="2026-11-27T14:59:00Z",
        candidate_digest="C2",
    ), calendar=Calendar())
    assert new_signal.signal_id != signal.signal_id
    assert_signal_may_execute(new_signal.signal_id, [event])


def test_capacity_pressure_does_not_invalidate_thesis_or_force_existing_position_exit():
    with pytest.raises(PermissionError, match="REBALANCING_EXIT_NOT_GOVERNED"):
        build_position_exit(
            position_id="POS-1", signal_id="SIG-1", event_timestamp="2026-11-25T15:02:00Z",
            exit_type=PositionExitType.PORTFOLIO_REBALANCING, exit_price=100, rule_version="V1",
        )
    invalidation = build_position_exit(
        position_id="POS-1", signal_id="SIG-1", event_timestamp="2026-11-25T15:02:00Z",
        exit_type=PositionExitType.THESIS_INVALIDATION, exit_price=90, rule_version="M1-THESIS",
    )
    assert invalidation["thesis_invalidated"] is True
    future_rebalance = build_position_exit(
        position_id="POS-1", signal_id="SIG-1", event_timestamp="2027-11-25T15:02:00Z",
        exit_type=PositionExitType.PORTFOLIO_REBALANCING, exit_price=110,
        rule_version="M2-REBALANCE", methodology_allows_rebalancing=True,
    )
    assert future_rebalance["exit_type"] == "PORTFOLIO_REBALANCING"
    assert future_rebalance["thesis_invalidated"] is False


def lifecycle(signal_id, outcome, sequence):
    return SignalLifecycleEvent(
        f"E-{sequence}", signal_id, "LONG_TERM", f"2026-11-{25 + sequence:02d}T15:00:00+00:00",
        outcome, None, None, None, True,
    )


def test_signal_outcome_counts_are_separate_and_deterministic():
    signal_ids = ["S1", "S2", "S3", "S4", "S5"]
    events = [
        lifecycle("S1", SignalOutcome.SIGNAL_EXECUTED.value, 0),
        lifecycle("S2", SignalOutcome.SIGNAL_NOT_FUNDED_PORTFOLIO_FULL.value, 1),
        lifecycle("S3", SignalOutcome.SIGNAL_EXPIRED.value, 2),
        lifecycle("S4", SignalOutcome.SIGNAL_NEVER_ENTERED_RANGE.value, 3),
    ]
    assert summarize_signal_outcomes(signal_ids=signal_ids, lifecycle_events=events) == {
        "SIGNALS_ISSUED": 5, "SIGNALS_EXECUTED": 1,
        "SIGNALS_NOT_FUNDED_PORTFOLIO_FULL": 1, "SIGNALS_EXPIRED": 1,
        "SIGNALS_NEVER_ENTERED_RANGE": 1,
    }


def test_signal_quality_includes_unfunded_while_portfolio_performance_uses_executions_only():
    funded = build_long_term_signal(long_term_payload(ticker="AAA", stable_security_id="SEC-A"), calendar=Calendar())
    unfunded = build_long_term_signal(long_term_payload(
        ticker="BBB", stable_security_id="SEC-B", candidate_digest="C-B"), calendar=Calendar())
    execution = first_qualifying_long_term_execution(funded, [
        {"timestamp": "2026-11-25T15:01:00Z", "price": 96, "price_source": "TRADE"},
    ], calendar=Calendar())
    assert signal_quality_population([funded, unfunded]) == (funded.signal_id, unfunded.signal_id)
    assert portfolio_performance_population([execution]) == (execution.execution_id,)
