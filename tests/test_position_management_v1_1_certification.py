import sqlite3

import pytest

from services.position_management import (
    DataCertainty, PersistenceState, ReasonCode, TechnicalState, ThesisState,
    ValuationState, episode_transition, evaluate_shadow_position, load_methodology,
)
from services.position_management_ledgers import ShadowPositionLedger
from services.position_universe_validation import UniverseValidationLedger


CFG = load_methodology()
ACTIVATION = "2026-10-08T20:00:00+00:00"
NOW = "2026-10-08T21:00:00+00:00"


def decide(thesis=ThesisState.INTACT, valuation=ValuationState.FAIR,
           technical=TechnicalState.HEALTHY, certainty=DataCertainty.CERTIFIED, **kwargs):
    return evaluate_shadow_position(
        thesis_state=thesis, valuation_state=valuation, technical_state=technical,
        data_certainty=certainty, current_action="BUY_NOW", scan_timestamp=NOW,
        config=CFG, **kwargs,
    )


@pytest.mark.parametrize("thesis", list(ThesisState))
@pytest.mark.parametrize("valuation", list(ValuationState))
@pytest.mark.parametrize("technical", list(TechnicalState))
@pytest.mark.parametrize("certainty", list(DataCertainty))
def test_full_state_matrix_is_deterministic_and_fail_closed(thesis, valuation, technical, certainty):
    kwargs = {}
    if valuation in {ValuationState.STRETCHED, ValuationState.ABOVE_FV} and thesis != ThesisState.BROKEN:
        kwargs["persistence"] = PersistenceState(
            trigger=valuation.value, count=2, first_triggered_at=NOW, confirmed_at=NOW)
    first = decide(thesis=thesis, valuation=valuation, technical=technical, certainty=certainty, **kwargs)
    second = decide(thesis=thesis, valuation=valuation, technical=technical, certainty=certainty, **kwargs)
    assert first == second
    assert first.reason_codes and all(ReasonCode(code) for code in first.reason_codes)
    if certainty == DataCertainty.REVIEW_REQUIRED or thesis == ThesisState.UNAVAILABLE or technical == TechnicalState.UNAVAILABLE:
        assert first.instruction == "SUSPENDED" and first.review_required
    elif valuation == ValuationState.UNAVAILABLE and thesis != ThesisState.BROKEN:
        assert first.instruction == "SUSPENDED" and first.review_required
    elif thesis == ThesisState.BROKEN:
        assert first.instruction == "EXIT"


def shadow_payload(**changes):
    row = {
        "signal_id": "signal-1", "ticker": "NVDA", "scan_timestamp": NOW,
        "methodology_version": CFG["methodology_version"], "rule_table_version": CFG["rule_table_version"],
        "candidate_digest": "candidate", "publication_digest": "publication",
        "evaluation_snapshot": "snapshot", "source_sha": "source", "thesis_state": "INTACT",
        "valuation_state": "FAIR", "technical_state": "HEALTHY", "data_certainty": "CERTIFIED",
        "position_instruction": "HOLD", "add_eligible": True, "review_required": False,
        "review_reason_codes": [], "reason_codes": ["THESIS_INTACT"], "price": 100,
        "certified_fair_value": 110, "valuation_confidence": 80,
        "fair_value_band": {"lower": 90, "base": 110, "upper": 125},
        "inputs_digest": "inputs", "customer_visible": False,
    }
    row.update(changes)
    return row


@pytest.mark.parametrize(("valuation", "technical"), [
    (ValuationState.ATTRACTIVE, TechnicalState.HEALTHY),
    (ValuationState.STRETCHED, TechnicalState.HEALTHY),
    (ValuationState.ABOVE_FV, TechnicalState.HEALTHY),
    (ValuationState.FAIR, TechnicalState.DETERIORATING),
    (ValuationState.FAIR, TechnicalState.BROKEN),
])
def test_certified_hard_break_has_precedence_over_valuation_and_technical(valuation, technical):
    result = decide(thesis=ThesisState.BROKEN, valuation=valuation, technical=technical)
    assert result.instruction == "EXIT"
    assert result.data_certainty == "CERTIFIED"


def test_pending_event_and_missing_confidence_suspend():
    event = decide(review_reason_codes=[ReasonCode.EVENT_REVIEW_PENDING])
    assert (event.data_certainty, event.instruction, event.review_required) == ("REVIEW_REQUIRED", "SUSPENDED", True)
    missing = decide(valuation_confidence_available=False)
    assert missing.valuation_state == "UNAVAILABLE"
    assert missing.instruction == "SUSPENDED" and missing.review_required
    assert "VALUATION_CONFIDENCE_UNAVAILABLE" in missing.reason_codes


def test_reason_codes_are_closed_enum():
    with pytest.raises(ValueError, match="UNKNOWN_POSITION_REASON_CODE"):
        decide(review_reason_codes=["LLM_SAYS_EXIT"])
    assert all(ReasonCode(code) for code in decide().reason_codes)


def test_pending_end_preserves_first_timestamp_and_resets_on_requalification():
    first = episode_transition(current_action="WAIT", prior_outside_count=0, scan_timestamp="2026-10-09T21:00:00Z", config=CFG)
    state = first
    for count, timestamp in enumerate(("2026-10-10T21:00:00Z", "2026-10-11T21:00:00Z",
                                       "2026-10-12T21:00:00Z", "2026-10-13T21:00:00Z"), start=1):
        state = episode_transition(current_action="WAIT", prior_outside_count=count, scan_timestamp=timestamp,
                                   first_out_of_buy_now_at=state["first_out_of_buy_now_at"], config=CFG)
        assert state["first_out_of_buy_now_at"] == first["first_out_of_buy_now_at"]
    assert state["status"] == "ENDED" and state["confirmation_count"] == 5
    reset = episode_transition(current_action="BUY_NOW", prior_outside_count=2, scan_timestamp=NOW,
                               first_out_of_buy_now_at=first["first_out_of_buy_now_at"], config=CFG)
    assert reset == {"status": "OPEN", "first_out_of_buy_now_at": None,
                     "confirmation_count": 0, "confirmed_episode_end_at": None}


@pytest.mark.parametrize("changes", [
    {"signal_id": ""}, {"ticker": ""}, {"reason_codes": []}, {"reason_codes": ["FREE TEXT"]},
    {"thesis_state": "UNKNOWN"}, {"valuation_state": "UNKNOWN"}, {"technical_state": "UNKNOWN"},
    {"data_certainty": "UNKNOWN"}, {"position_instruction": "SELL"},
    {"methodology_version": "ATLAS_POSITION_MANAGEMENT_SHADOW_V1"},
    {"methodology_version": "ATLAS_POSITION_MANAGEMENT_SHADOW_V2"},
    {"rule_table_version": "ATLAS_POSITION_RULE_TABLE_V9"},
])
def test_shadow_ledger_rejects_invalid_contract(tmp_path, changes):
    ledger = ShadowPositionLedger(tmp_path / "shadow.sqlite3", activation_timestamp=ACTIVATION)
    with pytest.raises(ValueError):
        ledger.append_evaluation(shadow_payload(**changes))


def test_shadow_ledger_detects_corrupt_parent_and_pre_activation(tmp_path):
    ledger = ShadowPositionLedger(tmp_path / "shadow.sqlite3", activation_timestamp=ACTIVATION)
    ledger.append_evaluation(shadow_payload())
    with sqlite3.connect(ledger.path) as db:
        db.execute("DROP TRIGGER state_records_no_update")
        db.execute("UPDATE state_records SET previous_digest='bad-parent'")
    with pytest.raises(ValueError, match="SHADOW_LEDGER_INTEGRITY_FAILURE"):
        ledger.verify()
    with pytest.raises(ValueError, match="PROSPECTIVE_ONLY_NO_BACKFILL"):
        ShadowPositionLedger(tmp_path / "older.sqlite3", activation_timestamp=ACTIVATION).append_evaluation(
            shadow_payload(scan_timestamp="2026-10-08T19:59:59+00:00"))


def universe_payload(**changes):
    row = {"ticker": "NVDA", "scan_timestamp": NOW, "scan_cohort_id": "cohort-20261008",
           "sector": "Technology", "industry": "Semiconductors", "beta": 1.5,
           "market_cap_bucket": "MEGA", "momentum": {"status": "UNAVAILABLE", "value": None},
           "volatility": {"status": "AVAILABLE", "value": 0.31}, "current_action": "BUY_NOW",
           "valuation_state": "FAIR", "technical_state": "HEALTHY", "risk_state": "NORMAL",
           "candidate_digest": "candidate", "publication_digest": "publication",
           "evaluation_snapshot": "snapshot", "source_sha": "source",
           "methodology_version": CFG["methodology_version"], "rule_table_version": CFG["rule_table_version"],
           "customer_visible": False, "delisted": False}
    row.update(changes)
    return row


@pytest.mark.parametrize("missing", ["scan_cohort_id", "momentum", "volatility"])
def test_universe_matching_metadata_required(tmp_path, missing):
    row = universe_payload()
    del row[missing]
    with pytest.raises(ValueError, match="UNIVERSE_STATE_INCOMPLETE"):
        UniverseValidationLedger(tmp_path / "universe.sqlite3", activation_timestamp=ACTIVATION).append_state(row)


def test_universe_explicit_unavailable_is_allowed_but_absence_is_not(tmp_path):
    ledger = UniverseValidationLedger(tmp_path / "universe.sqlite3", activation_timestamp=ACTIVATION)
    assert ledger.append_state(universe_payload())
    with pytest.raises(ValueError, match="UNIVERSE_MATCHING_FIELD_INVALID"):
        UniverseValidationLedger(tmp_path / "bad.sqlite3", activation_timestamp=ACTIVATION).append_state(
            universe_payload(momentum=None))
