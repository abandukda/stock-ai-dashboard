from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.prospective_report_card import ProspectiveLedger
from services.report_card_observation_activation import BUNDLE_SCHEMA, apply_observation_bundle


ACTIVATION = datetime(2026, 10, 8, 3, 20, 17, tzinfo=timezone.utc)
CLOSE = datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)


def ledger_with_signals(path: Path) -> ProspectiveLedger:
    ledger = ProspectiveLedger(path)
    ledger.activate(activation_timestamp=ACTIVATION.isoformat(), now=ACTIVATION)
    for ticker, price in (("NVDA", 100.0), ("MSFT", 200.0)):
        ledger.append("SIGNAL", ticker, {"signal_id": ticker, "semantic_identity": ticker,
                      "ticker": ticker, "reference_price": price, "first_seen_at": ACTIVATION.isoformat()},
                      created_at=ACTIVATION + timedelta(seconds=1))
    return ledger


def bundle(ledger: ProspectiveLedger):
    records = []
    for ticker, price in (("NVDA", 110.0), ("MSFT", 190.0)):
        records.append({"signal_id": ticker, "observation": {
            "observed_price": price, "observed_at": "2026-10-08T20:00:00+00:00",
            "price_source": "GOVERNED_OFFICIAL_DAILY_CLOSE", "corporate_action_status": "NONE",
            "data_status": "AVAILABLE", "benchmark_ticker": "SPY",
            "benchmark_observed_at": "2026-10-08T20:00:00+00:00",
            "benchmark_reference_price": 500.0, "benchmark_observed_price": 505.0,
            "benchmark_return": None, "trading_sessions": ["2026-10-08"],
            "price_provenance": {"provider": "GOVERNED_FIXTURE", "instrument": ticker,
                                 "as_of": "2026-10-08T20:00:00+00:00",
                                 "retrieved_at": "2026-10-08T20:02:00+00:00", "currency": "USD",
                                 "session_status": "FINALIZED_REGULAR_CLOSE"}}})
    return {"schema_version": BUNDLE_SCHEMA, "activation_timestamp": ACTIVATION.isoformat(),
            "ledger_tip_before": ledger.verify(), "session_open_at": "2026-10-08T13:30:00+00:00",
            "session_close_at": CLOSE.isoformat(), "horizon_trading_days": 1, "records": records,
            "bundle_certified_at": "2026-10-08T20:03:00+00:00",
            "session_status": "FINALIZED_REGULAR_CLOSE", "trading_calendar_source": "XNYS",
            "trading_calendar_version": "2026.10",
            "provider_calls": 0, "reacquisition": "none", "customer_visible": False,
            "public_performance_claims_allowed": False}


def test_complete_mature_bundle_is_atomic_backed_up_and_idempotent(tmp_path):
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    payload = bundle(ledger)
    result = apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup",
                                      bundle=payload, now=CLOSE + timedelta(minutes=4))
    assert (result.appended, result.signal_count, result.session_date) == (2, 2, "2026-10-08")
    assert ProspectiveLedger(Path(result.backup_path)).verify() == result.ledger_tip
    payload["ledger_tip_before"] = ledger.verify()
    replay = apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup2",
                                      bundle=payload, now=CLOSE + timedelta(minutes=5))
    assert (replay.appended, replay.idempotent) == (0, 2)


def test_before_close_fails_without_mutating_ledger(tmp_path):
    ledger = ledger_with_signals(tmp_path / "ledger.sqlite3")
    tip = ledger.verify()
    with pytest.raises(ValueError, match="OBSERVATION_HORIZON_NOT_MATURE"):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=bundle(ledger),
                                 now=CLOSE - timedelta(seconds=1))
    assert ledger.verify() == tip and ledger.rows("OBSERVATION") == []


@pytest.mark.parametrize("mutation,error", [
    (lambda b: b["records"].pop(), "OBSERVATION_SIGNAL_COVERAGE_MISMATCH"),
    (lambda b: b.update(ledger_tip_before="wrong"), "OBSERVATION_LEDGER_TIP_MISMATCH"),
    (lambda b: b["records"][0]["observation"].update(corporate_action_status=""), "CORPORATE_ACTION_STATUS_REQUIRED"),
    (lambda b: b["records"][1]["observation"].update(benchmark_observed_at="2026-10-07T20:00:00+00:00"),
     "STOCK_BENCHMARK_BOUNDARIES_NOT_ALIGNED"),
])
def test_bundle_fails_closed(mutation, error, tmp_path):
    ledger = ledger_with_signals(tmp_path / "ledger.sqlite3")
    payload = bundle(ledger)
    mutation(payload)
    with pytest.raises(ValueError, match=error):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=payload,
                                 now=CLOSE + timedelta(minutes=4))
    assert ledger.rows("OBSERVATION") == []


def test_observation_workflow_is_manual_internal_and_zero_provider():
    source = Path(".github/workflows/atlas_internal_report_card_observation.yml").read_text()
    assert "  workflow_dispatch:" in source and "  schedule:" not in source
    assert "atlas-internal-report-card" in source
    assert "runs-on: [self-hosted, Linux, X64, atlas-worker-1]" in source
    assert "python3 scripts/run_internal_report_card_observations.py" in source
    assert "FINNHUB_API_KEY" not in source and "customer_visible'] is False" in source
    assert "REPORT_CARD_APPEND_ONCE:${{ inputs.bundle_sha256 }}" in source
    assert 'sha256sum "${bundles[0]}"' in source
    assert source.count("verify_report_card_closed_sentinel.py") == 2


def test_g4_candidate_is_inert_serial_ordered_and_fail_closed():
    import json
    contract = json.loads(Path("config/report_card_g4_schedule_candidate.json").read_text())
    assert contract["activation_authorized"] is False
    assert contract["schedule_registered"] is False
    assert contract["provider_retries"] == 0
    assert contract["catch_up"] == {
        "maximum_sessions_per_run": 5,
        "order": "OLDEST_FINALIZED_SESSION_FIRST",
        "parallelism": 1,
        "stop_on_first_failure": True,
    }
    assert contract["sentinel_required_before_and_after"] == "CLOSED"
    producer = Path(".github/workflows/atlas_report_card_observation_producer.yml").read_text()
    assert "  schedule:" not in producer


def test_finnhub_workflow_uses_only_governed_post_close_wakeups():
    source = Path(".github/workflows/atlas_daily_incremental_buy_now.yml").read_text()
    legacy = Path(".github/workflows/atlas_finnhub_full_universe_certification.yml").read_text()
    assert "  workflow_dispatch:" in source and "  schedule:" in source
    assert "5 22 * * 1-5" in source
    assert "5 23 * * 1-5" in source
    assert "coordinator:" in source
    for cron in ("15 4", "00 11", "00 16", "00 19", "00 23"):
        assert cron not in source
    assert "atlas_finnhub_incremental_acquisition.yml" in source
    assert "provider-free-end-to-end" in source
    assert "run_finnhub_full_universe.py" not in source
    assert "  schedule:" not in legacy


def test_backup_write_failure_rolls_back_entire_observation_batch(tmp_path, monkeypatch):
    import services.report_card_observation_activation as activation
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    original = ledger.verify()
    def failure(**_kwargs):
        raise OSError("INJECTED_BACKUP_FAILURE")
    monkeypatch.setattr(activation, "_write_verified_transaction_backup", failure)
    with pytest.raises(OSError, match="INJECTED_BACKUP_FAILURE"):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup",
                                 bundle=bundle(ledger), now=CLOSE + timedelta(minutes=4))
    assert ledger.verify() == original
    assert ledger.rows("OBSERVATION") == []


@pytest.mark.parametrize("failure_stage", ["file_fsync", "restore_verify", "directory_fsync"])
def test_snapshot_persistence_failures_cannot_commit_primary(tmp_path, monkeypatch, failure_stage):
    import services.report_card_observation_activation as activation
    import os
    import stat
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    original = ledger.verify()
    if failure_stage == "restore_verify":
        def failure(*args, **kwargs): raise ValueError("INJECTED_RESTORE_FAILURE")
        monkeypatch.setattr(activation, "_verify_transaction_snapshot", failure)
    else:
        real = os.fsync
        def failure(descriptor):
            directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
            if directory == (failure_stage == "directory_fsync"):
                raise OSError("INJECTED_FSYNC_FAILURE")
            real(descriptor)
        monkeypatch.setattr(activation.os, "fsync", failure)
    with pytest.raises((OSError, ValueError), match="INJECTED"):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup",
                                 bundle=bundle(ledger), now=CLOSE + timedelta(minutes=4))
    assert ledger.verify() == original and ledger.rows("OBSERVATION") == []


def test_identical_now_idempotent_replay_reuses_verified_backup(tmp_path):
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    now = CLOSE + timedelta(minutes=4)
    payload = bundle(ledger)
    first = apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=payload, now=now)
    before_bytes = Path(first.backup_path).read_bytes()
    payload["ledger_tip_before"] = ledger.verify()
    second = apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=payload, now=now)
    assert second.appended == 0 and second.idempotent == 2
    assert first.backup_path == second.backup_path
    assert Path(first.backup_path).read_bytes() == before_bytes


def test_locked_tip_guard_rejects_intervening_writer(tmp_path, monkeypatch):
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    payload = bundle(ledger)
    real = ledger.append_many
    def concurrent(records, **kwargs):
        ledger.append("AMENDMENT", "concurrent-writer", {"reason": "fixture"}, created_at=CLOSE)
        return real(records, **kwargs)
    monkeypatch.setattr(ledger, "append_many", concurrent)
    with pytest.raises(ValueError, match="LEDGER_TIP_CHANGED_BEFORE_APPEND"):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=payload,
                                 now=CLOSE + timedelta(minutes=4))
    assert ledger.rows("OBSERVATION") == []


def test_snapshot_memory_limit_rejects_without_primary_append(tmp_path, monkeypatch):
    import services.report_card_observation_activation as activation
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    before = ledger.verify()
    monkeypatch.setattr(activation, "MAX_TRANSACTION_BACKUP_BYTES", 0)
    with pytest.raises(ValueError, match="OBSERVATION_TRANSACTION_BACKUP_MEMORY_LIMIT"):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=bundle(ledger),
                                 now=CLOSE + timedelta(minutes=4))
    assert ledger.verify() == before and ledger.rows("OBSERVATION") == []


def test_sqlite_commit_failure_leaves_primary_unchanged(tmp_path, monkeypatch):
    import sqlite3
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    before = ledger.verify()
    class CommitFailure(sqlite3.Connection):
        def execute(self, statement, parameters=()):
            if statement == "COMMIT":
                raise sqlite3.OperationalError("INJECTED_COMMIT_FAILURE")
            return super().execute(statement, parameters)
    def connect():
        db = sqlite3.connect(ledger.path, isolation_level=None, factory=CommitFailure)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db
    monkeypatch.setattr(ledger, "_connect", connect)
    with pytest.raises(sqlite3.OperationalError, match="INJECTED_COMMIT_FAILURE"):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=bundle(ledger),
                                 now=CLOSE + timedelta(minutes=4))
    assert ledger.verify() == before and ledger.rows("OBSERVATION") == []


def test_corrupt_serialized_snapshot_rejected_before_commit(tmp_path, monkeypatch):
    import sqlite3
    import services.report_card_observation_activation as activation
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    before = ledger.verify()
    real = activation._verify_transaction_snapshot
    def corrupt(path, db):
        path.write_bytes(b"CORRUPTED_DISPOSABLE_FIXTURE")
        return real(path, db)
    monkeypatch.setattr(activation, "_verify_transaction_snapshot", corrupt)
    with pytest.raises(sqlite3.DatabaseError):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=bundle(ledger),
                                 now=CLOSE + timedelta(minutes=4))
    assert ledger.verify() == before and ledger.rows("OBSERVATION") == []
