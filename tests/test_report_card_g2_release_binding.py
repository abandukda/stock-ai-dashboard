import copy

import pytest

from services.report_card_g2_release_binding import (
    build_g2_release_binding, monitoring_configuration_preflight,
)
from services.report_card_operational_controls import digest


SOURCE = "4" * 40


def fixtures():
    plan = {"artifact_sha256": "a" * 64}
    protected = {
        "schema_version": "ATLAS_REPORT_CARD_PROTECTED_READONLY_V1", "source_sha": SOURCE,
        "provider_calls": 0, "ledger_mutations": 0,
        "kill_switch_evidence": {"state": "CLOSED", "mode": "0o600", "owner": "atlasrunner", "safe_for_live_calls": False},
        "mounts": {"isolated": True},
        "ledger": {"sha256": "b" * 64, "tip": "tip"},
        "backup_root": {"verified_backups": [{"sha256": "c" * 64}]},
        "canonical_plan": plan, "canonical_plan_sha256": "a" * 64,
        "planned_calls": 61, "due_tickers": [f"T{i}" for i in range(20)],
        "package_sha256": "d" * 64,
    }
    entitlement = {"status": "APPROVED", "capabilities": ["historical_ohlcv", "splits", "dividends"]}
    return protected, entitlement


def test_builds_non_executable_source_current_package():
    protected, entitlement = fixtures()
    result = build_g2_release_binding(protected_validation=protected, entitlement=entitlement,
        release_source_sha=SOURCE, validation_run_id="42", validation_artifact="artifact")
    assert result["status"] == "OWNER_AUTHORIZATION_REQUIRED_NOT_EXECUTABLE"
    assert result["scope"]["maximum_provider_calls"] == 61
    assert result["authorization_contract"]["token_issued"] is False
    assert result["entitlement_sha256"] == digest(entitlement)


@pytest.mark.parametrize("field", ["source", "provider", "sentinel", "mount", "backup", "plan", "budget", "tickers"])
def test_fails_closed_on_identity_or_scope_defect(field):
    protected, entitlement = fixtures()
    if field == "source": protected["source_sha"] = "5" * 40
    elif field == "provider": protected["provider_calls"] = 1
    elif field == "sentinel": protected["kill_switch_evidence"]["state"] = "OPEN"
    elif field == "mount": protected["mounts"]["isolated"] = False
    elif field == "backup": protected["backup_root"]["verified_backups"] = []
    elif field == "plan": protected["canonical_plan"]["artifact_sha256"] = "e" * 64
    elif field == "budget": protected["planned_calls"] = 60
    elif field == "tickers": protected["due_tickers"].pop()
    with pytest.raises(PermissionError):
        build_g2_release_binding(protected_validation=protected, entitlement=entitlement,
            release_source_sha=SOURCE, validation_run_id="42", validation_artifact="artifact")


def test_monitoring_preflight_retains_only_hashes_and_performs_no_io():
    result = monitoring_configuration_preflight(
        owner_email="owner@example.com", cronitor_url="https://cronitor.link/opaque-monitor-id")
    assert result["network_request_performed"] is False
    assert result["delivery_proven"] is False
    assert "owner@example.com" not in str(result)
    assert "opaque-monitor-id" not in str(result)


def test_monitoring_preflight_rejects_missing_or_unapproved_configuration():
    with pytest.raises(RuntimeError, match="OWNER_EMAIL"):
        monitoring_configuration_preflight(owner_email="", cronitor_url="https://cronitor.link/x")
    with pytest.raises(ValueError, match="DESTINATION_NOT_APPROVED"):
        monitoring_configuration_preflight(owner_email="owner@example.com", cronitor_url="https://example.com/x")
