import json
from pathlib import Path

import pytest

from services.release_operational_closure import (
    monitoring_drill, persist_and_restore_evidence, publication_rollback_drill,
)


def test_monitoring_success_failure_and_missed_heartbeat_are_provider_free_and_sanitized():
    result = monitoring_drill(
        cronitor_url="https://cronitor.link/p/test-only/atlas-release",
        owner_email="release-owner@example.test", run_id="123", source_sha="a" * 40,
        trading_session="2026-10-14",
    )
    assert result["status"] == "PASS"
    assert result["delivery_attempted"] is False
    assert [row["status"] for row in result["synthetic_receipts"]] == [204, 204]
    assert all(row["destination"] == "CRONITOR" for row in result["synthetic_receipts"])
    assert result["missed_heartbeat"]["requires_independent_deadline"] is True
    encoded = json.dumps(result)
    assert "release-owner@example.test" not in encoded
    assert "cronitor.link/p/test-only" not in encoded


@pytest.mark.parametrize("email", ["", "owner", "owner@localhost", "owner @example.com"])
def test_owner_email_is_required_from_configuration(email):
    with pytest.raises(RuntimeError, match="OWNER_EMAIL"):
        monitoring_drill(
            cronitor_url="https://cronitor.link/p/test/atlas", owner_email=email,
            run_id="123", source_sha="a" * 40, trading_session="2026-10-14",
        )


def test_evidence_storage_round_trip_is_hash_verified(tmp_path):
    result = persist_and_restore_evidence(
        evidence={"monitor": {"status": "PASS"}, "rollback": {"status": "PASS"}},
        storage=tmp_path / "durable", restore=tmp_path / "restored",
    )
    assert result["status"] == "PASS"
    assert result["files"] == result["restored_sha256"]
    manifest_files = json.loads((tmp_path / "durable/evidence_manifest.json").read_text())["files"]
    assert manifest_files == {key: value for key, value in result["files"].items()
                              if key != "evidence_manifest.json"}


def test_publication_failure_restores_every_prior_file_without_protected_mutation():
    result = publication_rollback_drill()
    assert result["status"] == "PASS"
    assert result["production_state_restored"] is True
    assert result["prior_sha256"] == result["restored_sha256"]
    assert result["protected_state_mutated"] is False


def test_workflow_runs_provider_free_closure_and_retains_durable_evidence():
    source = Path(".github/workflows/atlas_finnhub_full_universe_certification.yml").read_text()
    assert "run_release_operational_closure.py" in source
    assert "ATLAS_DAILY_BUY_NOW_OWNER_EMAIL" in source
    assert "ATLAS_DAILY_BUY_NOW_CRONITOR_TEST_URL" in source
    assert "atlas-daily-buy-now-operational-closure-${{ github.run_id }}" in source
    assert "retention-days: 365" in source
    assert "@example." not in source and "@gmail." not in source
