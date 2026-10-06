from pathlib import Path

from agents.atlas_runtime_qa_v3 import governed_production_certification_passed
from agents.runtime_qa_architecture import certification_record
from services.runtime_projection_loader import load_exact_customer_inventory_with_status


def _passing_report():
    return {
        "status": "COMPLETE",
        "audit_valid": True,
        "user_journeys": {"required_journey_completeness": {"status": "PASS"}},
        "visual_certification": {"full_certification_allowed": True},
        "interaction_certification": {"coverage": {"full_certification_allowed": True}},
    }


def test_full_mode_semantic_exit_is_fail_closed():
    report = _passing_report()
    assert governed_production_certification_passed(report)
    for mutation in (
        lambda r: r.update(status="AUDIT_INVALID"),
        lambda r: r.update(audit_valid=False),
        lambda r: r["user_journeys"]["required_journey_completeness"].update(status="INCOMPLETE"),
        lambda r: r["visual_certification"].update(full_certification_allowed=False),
        lambda r: r["interaction_certification"]["coverage"].update(full_certification_allowed=False),
    ):
        candidate = _passing_report()
        mutation(candidate)
        assert not governed_production_certification_passed(candidate)


def test_journey_failure_does_not_become_navigation_failure():
    record = certification_record(
        page="Research Any Ticker", journey="Research NVDA", classification="QA_DEFECT",
        navigation_status="NOT_APPLICABLE", journey_status="FAIL",
        semantic_status="FAIL", reconciliation_status="FAIL",
    )
    assert record["navigation_status"] == "NOT_APPLICABLE"
    assert record["journey_status"] == "FAIL"


def test_versioned_projection_loader_remains_fail_closed(tmp_path: Path):
    missing = tmp_path / "missing.json"
    payload, valid, failures = load_exact_customer_inventory_with_status(missing, {})
    assert payload == []
    assert valid is False
    assert failures == ("RUNTIME_PROJECTION_UNREADABLE",)
