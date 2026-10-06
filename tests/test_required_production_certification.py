from agents.atlas_visual_crawler_v1 import (
    REQUIRED_PHASE_BUDGET,
    REQUIRED_PHASE_TIMEOUT_SECONDS,
    required_home_authority_failures,
    required_research_authority_failures,
)


IDENTITY = {
    "candidate_digest": "candidate",
    "publication_digest": "publication",
    "source_sha": "source",
}
FACT = {
    "action": "BUY_NOW",
    "atlas_fair_value": 346.05,
    "opportunity": 85.96,
    "decision_confidence": 87.46,
    "evaluation_snapshot_id": "snapshot",
}


def valid_observed():
    return {
        **IDENTITY,
        "action": "BUY NOW",
        "atlas_fair_value": "$346.05",
        "opportunity": "85.96",
        "decision_confidence": "87.46",
        "evaluation_snapshot_id": "snapshot",
        "provider_calls": 0,
        "research_terminal_state": "PUBLISHED_RESEARCH_COMPLETE",
    }


def test_required_research_exact_authority_passes():
    assert required_research_authority_failures(valid_observed(), FACT, IDENTITY) == []


def test_each_required_research_boundary_fails_closed():
    mutations = {
        "candidate_digest": "wrong",
        "publication_digest": "wrong",
        "source_sha": "wrong",
        "evaluation_snapshot_id": "wrong",
        "action": "WAIT_FOR_CONFIRMATION",
        "atlas_fair_value": "$1.00",
        "opportunity": "1.00",
        "decision_confidence": "1.00",
        "provider_calls": 1,
        "research_terminal_state": "RESEARCH_RENDER_INCOMPLETE",
    }
    for field, wrong in mutations.items():
        observed = valid_observed()
        observed[field] = wrong
        assert required_research_authority_failures(observed, FACT, IDENTITY), field


def test_required_phase_budget_has_zero_retries_and_workflow_margin():
    worst_case = sum(
        item["timeout_seconds"] * (item["retries"] + 1)
        for item in REQUIRED_PHASE_BUDGET.values()
    )
    assert all(item["retries"] == 0 for item in REQUIRED_PHASE_BUDGET.values())
    assert worst_case == 420
    assert REQUIRED_PHASE_TIMEOUT_SECONDS == 480
    assert 600 - REQUIRED_PHASE_TIMEOUT_SECONDS >= 120


def test_home_identity_inventory_and_leakage_fail_closed():
    expected = {
        "candidate_digest": "candidate", "publication_digest": "publication",
        "source_sha": "source", "projection_digest": "projection",
        "canonical_buy_now_count": 21, "publishable_buy_now_count": 11,
        "withheld_buy_now_count": 10,
        "canonical_buy_now": ["A", "B"], "publishable_buy_now": ["A"],
        "withheld_buy_now": ["B"],
    }
    observed = {**expected, "runtime_ready": True}
    assert required_home_authority_failures(observed, expected) == []
    for field in ("candidate_digest", "publication_digest", "projection_digest", "canonical_buy_now_count"):
        wrong = dict(observed)
        wrong[field] = "wrong"
        assert required_home_authority_failures(wrong, expected), field
    leaked = dict(observed)
    leaked["publishable_buy_now"] = ["A", "B"]
    failures = required_home_authority_failures(leaked, expected)
    assert "WITHHELD_PUBLICATION_LEAKAGE" in failures
