from dataclasses import asdict

import pytest

from services.position_management import (
    DataCertainty, FairValueBand, PersistenceState, PositionInstruction,
    TechnicalState, ThesisState, ValuationState, classify_valuation,
    episode_transition, evaluate_shadow_position, load_methodology, reentry_allowed,
)


NOW = "2026-10-08T20:00:00+00:00"
CFG = load_methodology()


def decide(thesis=ThesisState.INTACT, valuation=ValuationState.FAIR,
           technical=TechnicalState.HEALTHY, certainty=DataCertainty.CERTIFIED,
           action="BUY_NOW", **kwargs):
    return evaluate_shadow_position(
        thesis_state=thesis, valuation_state=valuation, technical_state=technical,
        data_certainty=certainty, current_action=action, scan_timestamp=NOW,
        config=CFG, **kwargs,
    )


def confirmed(state):
    return PersistenceState(trigger=state.value, count=2,
                            first_triggered_at="2026-10-07T20:00:00+00:00", confirmed_at=NOW)


def test_certified_fair_value_band_states_are_config_driven():
    band = FairValueBand(90, 100, 115, 80, "VALUATION_V1")
    assert classify_valuation(89, band) == ValuationState.ATTRACTIVE
    assert classify_valuation(90, band) == ValuationState.FAIR
    assert classify_valuation(100, band) == ValuationState.FAIR
    assert classify_valuation(110, band) == ValuationState.STRETCHED
    assert classify_valuation(116, band) == ValuationState.ABOVE_FV
    assert classify_valuation(None, band) == ValuationState.UNAVAILABLE
    with pytest.raises(ValueError, match="FAIR_VALUE_BAND_INVALID"):
        FairValueBand(110, 100, 115, 80, "VALUATION_V1")


@pytest.mark.parametrize(("thesis", "valuation", "technical", "expected"), [
    (ThesisState.BROKEN, ValuationState.FAIR, TechnicalState.HEALTHY, PositionInstruction.EXIT),
    (ThesisState.WEAKENED, ValuationState.FAIR, TechnicalState.HEALTHY, PositionInstruction.HOLD_NO_ADD),
    (ThesisState.WEAKENED, ValuationState.STRETCHED, TechnicalState.HEALTHY, PositionInstruction.TRIM),
    (ThesisState.INTACT, ValuationState.STRETCHED, TechnicalState.HEALTHY, PositionInstruction.HOLD_NO_ADD),
    (ThesisState.INTACT, ValuationState.STRETCHED, TechnicalState.DETERIORATING, PositionInstruction.TRIM),
    (ThesisState.INTACT, ValuationState.ABOVE_FV, TechnicalState.HEALTHY, PositionInstruction.TRIM),
])
def test_preregistered_rule_table(thesis, valuation, technical, expected):
    persistence = confirmed(valuation) if valuation in {ValuationState.STRETCHED, ValuationState.ABOVE_FV} else None
    assert decide(thesis, valuation, technical, persistence=persistence).instruction == expected.value


def test_data_uncertainty_and_basis_change_suspend():
    assert decide(certainty=DataCertainty.REVIEW_REQUIRED).instruction == "SUSPENDED"
    changed = decide(valuation_basis_changed=True)
    assert changed.instruction == "SUSPENDED"
    assert "VALUATION_BASIS_CHANGED" in changed.review_reason_codes


def test_technical_break_cannot_exit_long_term_position():
    result = decide(technical=TechnicalState.BROKEN)
    assert result.instruction == "HOLD_NO_ADD"
    assert result.review_required is True
    assert result.add_eligible is False


def test_add_is_derived_only_from_current_discovery_action():
    assert decide(action="BUY_NOW").add_eligible is True
    assert decide(action="BUILD_A_POSITION").add_eligible is True
    assert decide(action="WATCH").add_eligible is False
    assert decide(action="BUY_NOW", protected_add_blocked=True).add_eligible is False


def test_protected_valuation_transition_requires_persistence():
    first = decide(valuation=ValuationState.ABOVE_FV)
    assert first.instruction == "SUSPENDED"
    assert first.persistence_scan_count == 1
    second = decide(valuation=ValuationState.ABOVE_FV, persistence=PersistenceState(
        trigger="ABOVE_FV", count=1, first_triggered_at=NOW))
    assert second.instruction == "TRIM"
    assert second.confirmed_at == NOW


def test_axes_are_independent_and_reasoned():
    base = decide()
    changed = decide(technical=TechnicalState.DETERIORATING)
    assert base.thesis_state == changed.thesis_state == "INTACT"
    assert base.valuation_state == changed.valuation_state == "FAIR"
    assert base.inputs_digest != changed.inputs_digest
    assert base.reason_codes and changed.reason_codes


def test_episode_end_and_reentry_hysteresis_are_separate():
    pending = episode_transition(current_action="WATCH", prior_outside_count=0, scan_timestamp=NOW, config=CFG)
    assert pending["status"] == "PENDING_END"
    ended = episode_transition(current_action="WATCH", prior_outside_count=4, scan_timestamp=NOW, config=CFG)
    assert ended["status"] == "ENDED"
    assert not reentry_allowed(prior_episode_confirmed_ended=True,
                               consecutive_regular_sessions_outside_buy_now=4,
                               current_action="BUY_NOW", config=CFG)
    assert reentry_allowed(prior_episode_confirmed_ended=True,
                           consecutive_regular_sessions_outside_buy_now=5,
                           current_action="BUY_NOW", config=CFG)


def test_no_personal_pnl_or_ai_assignment_surface_exists():
    fields = set(asdict(decide()))
    forbidden = {"cost_basis", "purchase_price", "unrealized_gain", "tax_lot", "ai_state"}
    assert fields.isdisjoint(forbidden)
    source = __import__("inspect").getsource(evaluate_shadow_position)
    assert "openai" not in source.lower()
    assert "model" not in source.lower()


def test_customer_visibility_is_fail_closed():
    assert decide().customer_visible is False
    assert CFG["customer_visible"] is False
