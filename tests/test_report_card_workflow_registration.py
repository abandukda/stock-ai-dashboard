from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CALENDAR = ROOT / ".github/workflows/atlas_report_card_exchange_calendar.yml"
ACQUISITION = ROOT / ".github/workflows/atlas_report_card_market_evidence_acquisition.yml"


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
    assert "exchange_calendars==4.13.2 PyYAML==6.0.3" in source


def test_g1_does_not_change_production_dependency_or_smoke_contracts():
    calendar, _ = _workflow(CALENDAR)
    acquisition, _ = _workflow(ACQUISITION)
    assert "exchange_calendars==4.13.2" in calendar
    assert "exchange_calendars==4.13.2" in acquisition
    assert "requirements.txt" not in {
        str(path.relative_to(ROOT))
        for path in ROOT.glob("requirements*.txt")
        if "exchange_calendars==4.13.2" in path.read_text(encoding="utf-8")
    }
