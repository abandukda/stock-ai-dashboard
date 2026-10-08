from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from services.prospective_report_card import (
    ProspectiveLedger, append_amendment, append_observation,
    capture_certified_publication, internal_dashboard,
)
from services.report_card_governance import public_report_allowed
from services.report_card_capture_handoff import build_capture_handoff


NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
CANDIDATE = "c" * 64
PUBLICATION = "p" * 64
SOURCE = "s" * 40


def manifest(**overrides):
    result = {
        "publication_gate_status": "PASS", "artifact_lineage_status": "COHERENT",
        "methodology_version": "METHOD_V1", "provider_authority_version": "FINNHUB_V1",
        "executor_candidate_identity": {"candidate_digest": CANDIDATE, "source_sha": SOURCE,
                                        "methodology_version": "METHOD_V1", "provider_authority_version": "FINNHUB_V1"},
        "release_certification": {"candidate_digest": CANDIDATE, "publication_digest": PUBLICATION,
                                  "source_sha": SOURCE, "status": "PASS"},
    }
    result.update(overrides)
    return result


def row(*, ticker="NVDA", allowed=True, action="BUY_NOW", evidence_at=None):
    evidence_at = evidence_at or NOW - timedelta(hours=1)
    snapshot = ticker.lower() + "-snapshot"
    evidence = f"FINNHUB:HISTORICAL_OHLCV:{ticker}:abc"
    return {
        "ticker": ticker, "security_type": "COMMON_STOCK", "candidate_digest": CANDIDATE,
        "source_sha": SOURCE, "current_price": 100.0, "professional_evidence_as_of": evidence_at.isoformat(),
        "methodology_version": "METHOD_V1", "provider_authority_version": "FINNHUB_V1",
        "professional_evidence_lineage": {"evidence_ids": [evidence]},
        "publication_certification": {
            "customer_publication_allowed": allowed, "certified_at": (NOW - timedelta(hours=2)).isoformat(),
            "components": {"market": {"lineage": {"as_of": (NOW - timedelta(hours=1)).isoformat()}}},
        },
        "certified_customer_evaluation": {
            "customer_publication_allowed": allowed,
            "decision": {"action": action, "opportunity": 81.2, "decision_confidence": 88.3,
                         "decision_digest": ticker.lower() + "-decision"},
            "digests": {"evaluation_snapshot_id": snapshot, "decision_digest": ticker.lower() + "-decision"},
            "fields": {
                "atlas_fair_value": {"value": 150.0, "evidence_ids": [evidence]},
                "atlas_upside_pct": {"value": 50.0, "evidence_ids": [evidence]},
                "certified_market_price": {"value": 100.0, "as_of": (NOW - timedelta(hours=1)).isoformat(),
                                           "evidence_ids": [evidence]},
            },
        },
    }


@pytest.fixture
def ledger(tmp_path):
    item = ProspectiveLedger(tmp_path / "primary" / "ledger.sqlite3")
    item.activate(activation_timestamp=NOW.isoformat(), now=NOW)
    return item


def test_activation_boundary_cannot_be_backdated(tmp_path):
    item = ProspectiveLedger(tmp_path / "ledger.sqlite3")
    with pytest.raises(ValueError, match="NOT_BACKDATED"):
        item.activate(activation_timestamp=(NOW - timedelta(days=1)).isoformat(), now=NOW)


def test_activation_timestamp_is_one_time_and_cannot_be_rewritten(tmp_path):
    item = ProspectiveLedger(tmp_path / "ledger.sqlite3")
    original = item.activate(activation_timestamp=NOW.isoformat(), now=NOW)
    repeated = item.activate(activation_timestamp=(NOW + timedelta(days=10)).isoformat(), now=NOW + timedelta(days=10))
    assert repeated == original == NOW.isoformat()


def test_historical_snapshot_cannot_become_fake_prospective_history(ledger):
    result = capture_certified_publication(
        ledger=ledger, manifest=manifest(), rows=[row(evidence_at=NOW - timedelta(days=5))], observed_at=NOW)
    assert result.status == "NO_ELIGIBLE_SIGNAL"
    assert result.captured == 0
    assert "NVDA:STALE_OR_FUTURE_EVIDENCE" in result.reasons


def test_capture_is_idempotent_and_first_seen_is_activation_time(ledger):
    first = capture_certified_publication(ledger=ledger, manifest=manifest(), rows=[row()], observed_at=NOW)
    second = capture_certified_publication(ledger=ledger, manifest=manifest(), rows=[row()], observed_at=NOW + timedelta(minutes=10))
    assert (first.captured, second.idempotent) == (1, 1)
    signals = ledger.rows("SIGNAL")
    assert len(signals) == 1
    assert signals[0]["payload"]["first_seen_at"] == NOW.isoformat()


@pytest.mark.parametrize("change,error", [
    ({"publication_gate_status": "FAIL"}, "PUBLICATION_NOT_CERTIFIED"),
    ({"artifact_lineage_status": "MIXED"}, "PUBLICATION_NOT_CERTIFIED"),
])
def test_uncertified_publication_rejected(ledger, change, error):
    with pytest.raises(ValueError, match=error):
        capture_certified_publication(ledger=ledger, manifest=manifest(**change), rows=[row()], observed_at=NOW)


def test_green_capture_handoff_supplies_missing_release_publication_authority(ledger):
    source = manifest()
    source.pop("release_certification")
    source["report_card_capture_authority"] = {
        "status": "PASS", "classification": "FINNHUB_FULL_UNIVERSE_CERTIFICATION_CLOSED_GREEN",
        "candidate_digest": CANDIDATE, "publication_digest": PUBLICATION, "source_sha": SOURCE,
    }
    result = capture_certified_publication(ledger=ledger, manifest=source, rows=[row()], observed_at=NOW)
    assert result.captured == 1
    assert ledger.rows("SIGNAL")[0]["payload"]["publication_digest"] == PUBLICATION


def test_withheld_and_non_buy_now_signals_rejected(ledger):
    result = capture_certified_publication(
        ledger=ledger, manifest=manifest(), rows=[row(ticker="AIT", allowed=False), row(ticker="MSFT", action="WAIT_FOR_CONFIRMATION")],
        observed_at=NOW)
    assert result.captured == 0 and result.rejected == 2
    assert any("WITHHELD" in reason for reason in result.reasons)
    assert any("ACTION_NOT_ELIGIBLE" in reason for reason in result.reasons)


def test_ledger_is_immutable_and_amendment_preserves_original(ledger):
    result = capture_certified_publication(ledger=ledger, manifest=manifest(), rows=[row()], observed_at=NOW)
    signal_id = result.signal_ids[0]
    amendment_id = append_amendment(ledger, signal_id=signal_id, amendment={"reason": "clerical annotation"}, now=NOW)
    assert ledger.rows("AMENDMENT")[0]["parent_id"] == signal_id
    assert ledger.rows("SIGNAL")[0]["record_id"] == signal_id
    assert amendment_id != signal_id
    with sqlite3.connect(ledger.path) as db, pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_LEDGER"):
        db.execute("UPDATE records SET payload_json='{}' WHERE record_id=?", (signal_id,))


def available_observation(**changes):
    result = {
        "observed_price": 110.0, "observed_at": "2026-10-08T20:00:00+00:00", "price_source": "CERTIFIED_DAILY_CLOSE",
        "corporate_action_status": "NO_ACTION", "data_status": "AVAILABLE", "benchmark_ticker": "SPY",
        "benchmark_return": 0.01, "benchmark_observed_at": "2026-10-08T20:00:00+00:00",
        "stock_return": 0.10, "excess_return": 0.09, "trading_sessions": ["2026-10-08"],
    }
    result.update(changes)
    return result


def test_observation_horizon_uses_aligned_trading_sessions(ledger):
    signal_id = capture_certified_publication(ledger=ledger, manifest=manifest(), rows=[row()], observed_at=NOW).signal_ids[0]
    append_observation(ledger, signal_id=signal_id, horizon=1, observation=available_observation(), now=NOW)
    with pytest.raises(ValueError, match="TRADING_CALENDAR_INCOMPLETE"):
        append_observation(ledger, signal_id=signal_id, horizon=5,
                           observation=available_observation(trading_sessions=["2026-10-08"] * 5), now=NOW)


def test_missing_delisted_and_ambiguous_outcomes_fail_closed(ledger):
    signal_id = capture_certified_publication(ledger=ledger, manifest=manifest(), rows=[row()], observed_at=NOW).signal_ids[0]
    missing = available_observation(observed_price=None, stock_return=None, excess_return=None,
                                    benchmark_return=None, data_status="MISSING_PRICE", trading_sessions=[])
    append_observation(ledger, signal_id=signal_id, horizon=1, observation=missing, now=NOW)
    ambiguous = available_observation(observed_at="2026-10-09T20:00:00+00:00",
                                      benchmark_observed_at="2026-10-09T20:00:00+00:00",
                                      trading_sessions=["2026-10-09"], target_and_stop_same_daily_bar=True)
    append_observation(ledger, signal_id=signal_id, horizon=1, observation=ambiguous, now=NOW + timedelta(seconds=1))
    assert ledger.rows("OBSERVATION")[-1]["payload"]["target_stop_status"] == "AMBIGUOUS_DAILY_BAR_NO_ORDER_INFERRED"


def test_backup_is_integrity_verified_and_separate(ledger, tmp_path):
    capture_certified_publication(ledger=ledger, manifest=manifest(), rows=[row()], observed_at=NOW)
    backup = ledger.backup(tmp_path / "recovery", now=NOW)
    assert backup.exists() and backup.with_suffix(backup.suffix + ".sha256").exists()
    assert ProspectiveLedger(backup).verify() == ledger.verify()
    with pytest.raises(ValueError, match="SEPARATE_DURABLE_ROOT"):
        ledger.backup(ledger.path.parent, now=NOW)


def test_internal_dashboard_requires_access_and_public_visibility_remains_off(ledger):
    with pytest.raises(PermissionError, match="ACCESS_REQUIRED"):
        internal_dashboard(ledger, authorized=False)
    report = internal_dashboard(ledger, authorized=True)
    assert report["customer_visible"] is False
    assert report["public_performance_claims_allowed"] is False
    assert public_report_allowed() is False


def test_capture_does_not_mutate_decision_or_production_input(ledger):
    original = row()
    before = json.dumps(original, sort_keys=True)
    result = capture_certified_publication(ledger=ledger, manifest=manifest(), rows=[original], observed_at=NOW)
    stored = ledger.rows("SIGNAL")[0]["payload"]
    assert stored["canonical_recommendation"] == "BUY_NOW"
    assert stored["opportunity"] == 81.2 and stored["decision_confidence"] == 88.3
    assert stored["atlas_fair_value"] == 150.0 and stored["expected_return"] == 50.0
    assert json.dumps(original, sort_keys=True) == before
    assert result.captured == 1


def test_cli_stale_publication_does_not_create_operational_activation(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    publication_path = tmp_path / "publication.json"
    output = tmp_path / "output.json"
    manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
    publication_path.write_text(json.dumps([row(evidence_at=NOW - timedelta(days=5))]), encoding="utf-8")
    closure_path = tmp_path / "closure.json"
    required = {"candidate_digest", "publication_digest", "determinism", "analytical_mismatches",
                "manifests", "payloads", "symbols", "repository_integrity", "publication_gate"}
    closure_path.write_text(json.dumps({
        "evidence_source_run_id": "1", "evidence_source_run_identity": "r" * 64,
        "evidence_source_sha": SOURCE, "candidate_digest": CANDIDATE, "publication_digest": PUBLICATION,
        "classification": "FINNHUB_FULL_UNIVERSE_CERTIFICATION_CLOSED_GREEN", "workflow_conclusion": "GREEN",
        "determinism": "PASS", "analytical_mismatches": 0, "closure_provider_calls": 0,
        "checkpoint_validation": {"status": "PASS", "manifests": 41, "payloads": 41},
        "symbol_completeness": {"actual": 6033, "expected": 6033, "status": "PASS"},
        "checks": {key: True for key in required},
    }), encoding="utf-8")
    source_manifest = json.loads(manifest_path.read_text())
    source_manifest["artifact_hashes"] = {"market_full_scan.json": "a" * 64}
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(json.dumps(build_capture_handoff(
        manifest_path=manifest_path, publication_path=publication_path, closure_path=closure_path,
        expected_acquisition_run_id="1", expected_closure_run_id="2", expected_run_identity="r" * 64,
        expected_source_sha=SOURCE, expected_candidate_digest=CANDIDATE,
        expected_publication_digest=PUBLICATION,
    )), encoding="utf-8")
    ledger_path = tmp_path / "durable" / "ledger.sqlite3"
    subprocess.run([
        sys.executable, "scripts/run_internal_prospective_report_card.py",
        "--manifest", str(manifest_path), "--publication", str(publication_path),
        "--closure", str(closure_path), "--capture-handoff", str(handoff_path),
        "--ledger", str(ledger_path), "--backup-root", str(tmp_path / "backup"),
        "--activation-timestamp", datetime.now(timezone.utc).isoformat(),
        "--expected-candidate-digest", CANDIDATE, "--expected-publication-digest", PUBLICATION,
        "--expected-source-sha", SOURCE, "--output", str(output),
    ], check=True)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "NO_ELIGIBLE_SIGNAL"
    assert report["activation_timestamp"] is None
    assert not ledger_path.exists()
