from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CALENDAR = ROOT / ".github/workflows/atlas_report_card_exchange_calendar.yml"
ACQUISITION = ROOT / ".github/workflows/atlas_report_card_market_evidence_acquisition.yml"
DAILY = ROOT / ".github/workflows/atlas_report_card_daily_operations.yml"
PROTECTED = ROOT / ".github/workflows/atlas_report_card_protected_runner_validation.yml"


def _workflow(path: Path) -> tuple[str, dict]:
    source = path.read_text(encoding="utf-8")
    parsed = yaml.load(source, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return source, parsed


def test_calendar_registration_is_manual_read_only_and_replay_bound():
    source, workflow = _workflow(CALENDAR)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert "schedule:" not in source
    assert workflow["permissions"] == {"contents": "read"}
    assert "REPORT_CARD_CALENDAR_PRODUCE_ONCE" in source
    assert "build_report_card_exchange_calendar.py" in source
    assert "actions/upload-artifact@v4" in source


def test_acquisition_registration_separates_plan_and_live_authority():
    source, workflow = _workflow(ACQUISITION)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert "schedule:" not in source
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert "REPORT_CARD_PLAN_ONCE" in source
    assert "REPORT_CARD_ACQUIRE_ONCE" in source
    assert "execution_mode" in workflow["on"]["workflow_dispatch"]["inputs"]
    assert "atlas-internal-report-card" in source
    assert "atlas-worker-1" in source
    assert "append_observation" not in source
    assert "REPORT_CARD_APPEND_ONCE" not in source


def test_registration_ci_is_provider_free_and_does_not_dispatch_operations():
    source = (ROOT / ".github/workflows/atlas_report_card_registration_ci.yml").read_text(encoding="utf-8")
    assert "pull_request:" in source
    assert "workflow_dispatch:" not in source
    assert "FINNHUB_API_KEY" not in source
    assert "acquire_report_card_market_evidence.py --" not in source


def test_daily_schedule_is_dst_gated_serialized_and_inert_until_certified():
    source, workflow = _workflow(DAILY)
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    crons = {item["cron"] for item in workflow["on"]["schedule"]}
    assert crons == {"30 22 * * 1-5", "30 23 * * 1-5"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert "ATLAS_REPORT_CARD_AUTOMATION_ENABLED == 'true'" in source
    assert "ATLAS_REPORT_CARD_KILL_SWITCH" in source
    assert "SECOND_CYCLE_RELIABILITY_PASS" in source
    assert "preflight_report_card_daily_operations.py" in source
    assert "FINNHUB_API_KEY" not in source
    assert "run_internal_report_card_observations.py" not in source
    assert "Live operation remains separately gated" in source


def test_protected_runner_validation_is_manual_provider_free_and_non_mutating():
    source, workflow = _workflow(PROTECTED)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert "schedule:" not in source
    assert workflow["permissions"] == {"contents": "read"}
    assert "REPORT_CARD_PROTECTED_VALIDATE_ONCE" in source
    assert 'test -z "${FINNHUB_API_KEY:-}"' in source
    assert "validate_report_card_storage.py" in source
    assert "build_report_card_exchange_calendar.py" in source
    assert "acquire_market_evidence" not in source
    assert "append_observation" not in source
