import json

import pytest
from pathlib import Path

from services.full_qa_pipeline import (
    FAST_PREVIEW, RELEASE_FULL, RELEASE_SMOKE, TimingReport, validate_tier,
    visual_completion_contract, write_early_blocker_bundle,
)


def _summary(**updates):
    return {"finished": True, "authentication_success": True, "required_pages_passed": True,
            "candidate_binding_valid": True, **updates}


def _interaction(**updates):
    return {"required": True, "click_success": True, "opened": True,
            "collapse_success": True, "required_content_present": True, **updates}


def test_fast_preview_can_never_promote():
    with pytest.raises(ValueError, match="EXHAUSTIVE_VISUAL_CERTIFICATION_REQUIRED_FOR_PROMOTION"):
        validate_tier(FAST_PREVIEW, promotion_requested=True)
    assert validate_tier(RELEASE_SMOKE, promotion_requested=False) == RELEASE_SMOKE
    with pytest.raises(ValueError, match="EXHAUSTIVE_VISUAL_CERTIFICATION_REQUIRED_FOR_PROMOTION"):
        validate_tier(RELEASE_SMOKE, promotion_requested=True)
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
    backend = workflow.split("  backend-certification:", 1)[1].split("  visual-certification:", 1)[0]
    visual = workflow.split("  visual-certification:", 1)[1].split("  finalization:", 1)[0]
    assert "Build governed backend certification handoff" in backend
    assert "if: steps.data_qa.outcome == 'success'" in backend
    assert "needs: backend-certification" in visual
    assert "Capture and validate RELEASE_FULL desktop/mobile customer surfaces" in visual


def test_workflow_release_tier_is_mandatory_for_automatic_promotion():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert 'qa_tier="RELEASE_FULL"' in workflow
    assert "EXHAUSTIVE_VISUAL_CERTIFICATION_REQUIRED_FOR_PROMOTION" in (Path(__file__).resolve().parents[1] / "services/full_qa_pipeline.py").read_text()


def test_developer_center_exposes_latest_qa_timing_summary():
    source = (Path(__file__).resolve().parents[1] / "ui/developer_center.py").read_text()
    assert "Latest QA timing" in source
    assert 'qa.get("qa_timing")' in source


@pytest.mark.parametrize("candidate,accepted", [
    ("",False),("qa:",False),("qa:123",True),("full-universe:37216506983",True),
    ("publication:123",True),("123",True),("123\nrun_id=456",False),("latest",False),
])
def test_full_qa_requires_existing_candidate_without_provider_acquisition(candidate,accepted):
    import os, subprocess, yaml
    workflow=yaml.safe_load(Path(".github/workflows/atlas_full_qa_certification.yml").read_text())
    backend=workflow["jobs"]["backend-certification"]
    first=backend["steps"][0]
    assert first["name"]=="Require existing candidate before setup"
    result=subprocess.run(["bash","-c",first["run"]],env={**os.environ,"RETAINED_CANDIDATE":candidate},capture_output=True,text=True)
    assert (result.returncode==0)==accepted
    if not accepted:
        assert result.returncode==78 and "RETAINED_CANDIDATE_REQUIRED" in result.stdout
    assert backend["env"]["ATLAS_QA_PROVIDER_CALLS_ALLOWED"]=="0"
    assert backend["env"]["TWELVE_DATA_ENABLED"]=="false"
    assert backend["env"]["ATLAS_ALLOW_EXTERNAL_AI"]=="false"
    assert not any("API_KEY" in key for key in backend["env"])
    assert "python overnight_market_scan.py" not in str(backend["steps"])
