from dataclasses import replace

import pytest

from services.position_management import ThesisState
from services.position_management_validation import VALIDATION_PLAN, validate_plan
from services.position_thesis import classify_thesis, freeze_thesis_conditions


RAW = [
    {"condition_type": "HARD_BREAK", "issuance_value": 2.0,
     "threshold_or_condition": "net leverage must remain below governed threshold",
     "source_evidence": ["balance-sheet:2026Q3"]},
    {"condition_type": "MATERIAL_WEAKNESS", "issuance_value": 10.0,
     "threshold_or_condition": "certified forward estimate must not breach registered floor",
     "source_evidence": ["estimates:2026Q3"]},
]


def test_thesis_conditions_are_frozen_prospectively_and_deterministically():
    first = freeze_thesis_conditions(signal_id="signal-1", frozen_at="2026-10-08T20:00:00Z",
                                     methodology_version="V1", conditions=RAW)
    second = freeze_thesis_conditions(signal_id="signal-1", frozen_at="2026-10-08T20:00:00Z",
                                      methodology_version="V1", conditions=RAW)
    assert first == second
    assert all(item.current_state == "PASS" and item.triggered_at is None for item in first)
    assert classify_thesis(first) == ThesisState.INTACT


def test_structured_conditions_determine_weakened_broken_and_unavailable():
    conditions = freeze_thesis_conditions(signal_id="signal-1", frozen_at="2026-10-08T20:00:00Z",
                                          methodology_version="V1", conditions=RAW)
    assert classify_thesis((conditions[0], replace(conditions[1], current_state="FAIL"))) == ThesisState.WEAKENED
    assert classify_thesis((replace(conditions[0], current_state="FAIL"), conditions[1])) == ThesisState.BROKEN
    assert classify_thesis((replace(conditions[0], current_state="UNAVAILABLE"), conditions[1])) == ThesisState.UNAVAILABLE


def test_ai_cannot_assign_thesis_condition():
    with pytest.raises(ValueError, match="AI_THESIS_ASSIGNMENT_FORBIDDEN"):
        freeze_thesis_conditions(signal_id="signal-1", frozen_at="2026-10-08T20:00:00Z",
                                 methodology_version="V1",
                                 conditions=[RAW[0] | {"assignment_authority": "AI"}])


def test_validation_plan_is_preregistered_and_cluster_aware():
    assert validate_plan()
    assert VALIDATION_PLAN["inference"] == "CLUSTER_BY_SCAN_DATE_OR_COHORT"
    assert "MATCHED_CONTROLS" in VALIDATION_PLAN["exit_discrimination"]["comparators"]
