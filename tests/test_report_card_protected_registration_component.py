from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/atlas_report_card_protected_runner_validation.yml"

def test_component_is_manual_environment_bound_and_provider_free():
    source=WORKFLOW.read_text(encoding="utf-8")
    workflow=yaml.load(source,Loader=yaml.BaseLoader)
    assert set(workflow["on"])=={"workflow_dispatch"}
    assert "schedule:" not in source
    assert workflow["permissions"]=={"contents":"read"}
    job=workflow["jobs"]["validate"]
    assert job["environment"]=="atlas-internal-report-card"
    assert job["runs-on"]==["self-hosted","Linux","X64","atlas-worker-1"]
    assert "REPORT_CARD_PROTECTED_VALIDATE_ONCE" in source
    assert 'test -z "${FINNHUB_API_KEY:-}"' in source
    assert "prepare_report_card_protected_validation.py" in source
    assert "ACQUISITION_KILL_SWITCH" in source
    assert "schedule:" not in source and "acquire_market_evidence" not in source
    assert "append_observation" not in source and "REPORT_CARD_APPEND_ONCE" not in source

def test_component_runtime_dependencies_exist():
    required=[
        "scripts/prepare_report_card_protected_validation.py",
        "services/report_card_protected_readonly.py",
        "services/report_card_operational_controls.py",
        "services/report_card_market_evidence_acquisition.py",
        "tests/test_report_card_protected_readonly.py",
    ]
    assert all((ROOT/path).is_file() for path in required)
