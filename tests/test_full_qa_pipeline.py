import json

import pytest
from pathlib import Path

from services.full_qa_pipeline import (
    FAST_PREVIEW, RELEASE_FULL, TimingReport, validate_tier,
    visual_completion_contract, write_early_blocker_bundle,
)


def _summary(**updates):
    return {"finished": True, "authentication_success": True, "required_pages_passed": True,
            "candidate_binding_valid": True, **updates}


def _interaction(**updates):
    return {"required": True, "click_success": True, "opened": True,
            "collapse_success": True, "required_content_present": True, **updates}


def test_fast_preview_can_never_promote():
    with pytest.raises(ValueError, match="FAST_PREVIEW_CANNOT_PROMOTE"):
        validate_tier(FAST_PREVIEW, promotion_requested=True)
    assert validate_tier(RELEASE_FULL, promotion_requested=True) == RELEASE_FULL


@pytest.mark.parametrize("field", ["finished", "authentication_success", "required_pages_passed", "candidate_binding_valid"])
def test_visual_false_completion_field_blocks(field):
    result = visual_completion_contract(_summary(**{field: False}), [_interaction()],
                                        [{"viewport": "desktop"}, {"viewport": "mobile"}], mobile_required=True)
    assert result["status"] == "FAIL"


def test_failed_expander_and_missing_mobile_block():
    result = visual_completion_contract(_summary(), [_interaction(collapse_success=False)],
                                        [{"viewport": "desktop"}], mobile_required=True)
    assert result["status"] == "FAIL"
    assert result["interaction_coverage_pct"] == 0
    assert result["checks"]["mobile_required_coverage"] is False


def test_early_blocker_always_writes_standard_artifacts(tmp_path):
    timing = TimingReport()
    write_early_blocker_bundle(tmp_path, candidate={"run_id": "123", "sha": "abc"},
                               findings=[{"severity": "P1", "ticker": "ABC"}], timing=timing)
    summary = json.loads((tmp_path / "qa_summary.json").read_text())
    assert summary["browser_launched"] is False
    assert (tmp_path / "blocking_findings.json").exists()
    payload = json.loads((tmp_path / "qa_timing_report.json").read_text())
    assert set(payload["stages"]) >= {"identity", "deterministic_qa", "visual", "promotion"}


def test_workflow_stops_before_browser_on_deterministic_failure():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert "timeout-minutes: 90" in workflow
    assert "FULL QA BLOCKED BEFORE VISUAL CRAWL" in workflow
    for step in ("Materialize exact candidate", "Verify production Python grammar",
                 "Launch exact-candidate Streamlit runtime", "Capture and validate desktop/mobile"):
        block = workflow.split(f"- name: {step}", 1)[1].split("\n      - name:", 1)[0]
        assert "if: steps.data_qa.outcome == 'success'" in block


def test_workflow_release_tier_is_mandatory_for_automatic_promotion():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert 'qa_tier="RELEASE_FULL"' in workflow
    assert "FAST_PREVIEW_CANNOT_PROMOTE" in (Path(__file__).resolve().parents[1] / "services/full_qa_pipeline.py").read_text()


def test_developer_center_exposes_latest_qa_timing_summary():
    source = (Path(__file__).resolve().parents[1] / "ui/developer_center.py").read_text()
    assert "Latest QA timing" in source
    assert 'qa.get("qa_timing")' in source
