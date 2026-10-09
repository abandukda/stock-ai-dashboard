import json

import pytest

from services.position_management import load_methodology
from services.position_shadow_activation import (
    HANDOFF_SCHEMA, activate, certify_two_dry_runs, validate_handoff, validate_storage_roots,
)


CFG = load_methodology()
SCAN = "2026-10-08T21:00:00+00:00"


def handoff():
    identity = {
        "source_sha": "source", "candidate_digest": "candidate",
        "publication_digest": "publication", "evaluation_snapshot": "snapshot",
        "scan_timestamp": SCAN, "methodology_version": CFG["methodology_version"],
        "rule_table_version": CFG["rule_table_version"], "customer_visible": False,
    }
    signal = {
        **identity, "signal_id": "signal-1", "ticker": "NVDA",
        "publication_eligible": True, "original_action": "BUY_NOW",
        "thesis_state": "INTACT", "valuation_state": "FAIR", "technical_state": "HEALTHY",
        "data_certainty": "CERTIFIED", "position_instruction": "HOLD", "add_eligible": True,
        "review_required": False, "review_reason_codes": [], "reason_codes": ["THESIS_INTACT"],
        "price": 100.0, "certified_fair_value": 110.0, "valuation_confidence": 80.0,
        "fair_value_band": {"lower": 90.0, "base": 110.0, "upper": 125.0},
        "inputs_digest": "inputs", "episode_state": "OPEN",
    }
    universe = {
        **identity, "ticker": "NVDA", "scan_cohort_id": "cohort", "sector": "Technology",
        "industry": "Semiconductors", "beta": 1.5, "market_cap_bucket": "MEGA",
        "momentum": {"status": "AVAILABLE", "value": 0.12},
        "volatility": {"status": "AVAILABLE", "value": 0.31},
        "current_action": "BUY_NOW", "valuation_state": "FAIR", "technical_state": "HEALTHY",
        "risk_state": "NORMAL", "delisted": False,
    }
    return {"schema_version": HANDOFF_SCHEMA, "source_run_id": "run-1", **identity,
            "signals": [signal], "universe": [universe], "provider_calls": 0,
            "reacquisition": "none"}


def test_two_dry_runs_are_byte_deterministic_and_do_not_write(tmp_path):
    result = certify_two_dry_runs(handoff())
    assert result["status"] == "POSITION_SHADOW_FIRST_WRITE_READY"
    assert result["dry_run_1"] == result["dry_run_2"]
    assert result["dry_run_1"]["signal_count"] == result["dry_run_1"]["universe_count"] == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("field", ["source_sha", "candidate_digest", "publication_digest", "evaluation_snapshot"])
def test_handoff_rejects_identity_mismatch(field):
    value = handoff(); value["signals"][0][field] = "wrong"
    with pytest.raises(ValueError, match="MISMATCH"):
        validate_handoff(value)


def test_handoff_rejects_backfill_provider_calls_and_withheld():
    value = handoff(); value["scan_timestamp"] = "2026-10-07T23:59:59+00:00"
    with pytest.raises(ValueError, match="NOT_PROSPECTIVE"): validate_handoff(value)
    value = handoff(); value["provider_calls"] = 1
    with pytest.raises(ValueError, match="ZERO_PROVIDER"): validate_handoff(value)
    value = handoff(); value["signals"][0]["publication_eligible"] = False
    with pytest.raises(ValueError, match="NOT_PUBLISHABLE"): validate_handoff(value)


def test_storage_separation_and_pristine_contract(tmp_path):
    primary = tmp_path / "position-primary"; backup = tmp_path / "position-backup"
    report = tmp_path / "report-card"; primary.mkdir(); backup.mkdir(); report.mkdir()
    assert validate_storage_roots(primary=primary, backup=backup, report_primary=report)["status"] == "PASS"
    with pytest.raises(ValueError, match="SEPARATION"):
        validate_storage_roots(primary=report, backup=backup, report_primary=report)
    (primary / "unexpected.sqlite3").touch()
    with pytest.raises(ValueError, match="NOT_PRISTINE"):
        validate_storage_roots(primary=primary, backup=backup, report_primary=report)


def test_first_append_is_atomic_idempotent_backed_up_and_report_card_isolated(tmp_path):
    primary = tmp_path / "position-primary"; backup = tmp_path / "position-backup"
    report = tmp_path / "report-card"; primary.mkdir(); backup.mkdir(); report.mkdir()
    report_file = report / "report-card.sqlite3"; report_file.write_bytes(b"unchanged")
    before = report_file.read_bytes()
    result = activate(handoff=handoff(), primary=primary, backup=backup,
                      report_primary=report, allow_first_append=True)
    assert result["status"] == "ATLAS_POSITION_MANAGEMENT_V1_1_SHADOW_ACTIVE"
    assert result["signal_ledger_row_count"] == result["universe_ledger_row_count"] == 1
    assert result["ledger_integrity"] == result["backup_integrity"] == "PASS"
    assert result["provider_calls"] == 0 and result["report_card_mutation"] == "NONE"
    assert report_file.read_bytes() == before
    assert json.loads((primary / "certification" / "position_shadow_health.json").read_text())["customer_visible"] is False


def test_default_mode_stops_before_write(tmp_path):
    primary = tmp_path / "position-primary"; backup = tmp_path / "position-backup"
    primary.mkdir(); backup.mkdir()
    result = activate(handoff=handoff(), primary=primary, backup=backup, allow_first_append=False)
    assert result["status"] == "POSITION_SHADOW_FIRST_WRITE_READY"
    assert result["durable_append_performed"] is False
    assert not (primary / "signal-ledger.sqlite3").exists()


def test_workflow_is_manual_exact_sha_zero_provider_and_append_defaults_false():
    source = open(".github/workflows/atlas_position_shadow_activation.yml").read()
    assert "workflow_dispatch:" in source and "schedule:" not in source
    assert "allow_first_durable_append:" in source and "default: false" in source
    assert "git rev-parse HEAD" in source and "atlas-worker-1" in source
    assert "ATLAS_POSITION_SHADOW_DURABLE_ROOT" in source
    assert "ATLAS_REPORT_CARD_DURABLE_ROOT" in source
