from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]

def source(name): return (ROOT/".github/workflows"/name).read_text()

def test_g2_is_manual_plan_bound_entitlement_bound_and_kill_switched():
    text=source("atlas_report_card_market_evidence_acquisition.yml")
    parsed=yaml.load(text,Loader=yaml.BaseLoader)
    assert set(parsed["on"])=={"workflow_dispatch"}
    assert "schedule:" not in text
    assert "REPORT_CARD_PLAN_ONCE" in text and "REPORT_CARD_ACQUIRE_ONCE" in text
    assert "approved_plan_sha256" in text and "entitlement_artifact" in text
    assert "ACQUISITION_KILL_SWITCH" in text
    assert "append_observation" not in text

def test_g3_is_manual_exact_token_kill_switched_single_writer_and_zero_provider():
    text=source("atlas_internal_report_card_observation.yml")
    parsed=yaml.load(text,Loader=yaml.BaseLoader)
    assert set(parsed["on"])=={"workflow_dispatch"}
    assert "schedule:" not in text
    assert "REPORT_CARD_APPEND_ONCE" in text and "APPEND_KILL_SWITCH" in text
    assert parsed["concurrency"]["cancel-in-progress"]=="false"
    assert "FINNHUB_API_KEY" not in text

def test_no_g4_schedule_is_registered_by_ws4():
    names={path.name for path in (ROOT/".github/workflows").glob("*report_card*")}
    assert "atlas_report_card_daily_operations.yml" not in names
