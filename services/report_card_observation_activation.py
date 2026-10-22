"""Governed, zero-provider activation of prospective Report Card observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from typing import Any, Mapping, Sequence

from services.prospective_report_card import ProspectiveLedger, _utc, _digest, append_observations_atomic


BUNDLE_SCHEMA = "ATLAS_REPORT_CARD_OBSERVATION_BUNDLE_V1"
FINALIZED_SESSION_STATUS = "FINALIZED_REGULAR_CLOSE"
ALLOWED_PRICE_SOURCES = frozenset({"GOVERNED_OFFICIAL_DAILY_CLOSE", "GOVERNED_ADJUSTED_DAILY_CLOSE"})
ALLOWED_CORPORATE_ACTION_STATUS = frozenset({"NONE", "SPLIT_ADJUSTED", "DIVIDEND_ADJUSTED", "MERGER_PENDING_GOVERNED_TREATMENT"})


@dataclass(frozen=True)
class ObservationResult:
    status: str
    appended: int
    idempotent: int
    signal_count: int
    horizon: int
    session_date: str
    ledger_tip: str
    backup_path: str



# Serialization is bounded independently of host RAM. No production invocation
# is authorized by this helper or by its disposable-ledger tests.
MAX_TRANSACTION_BACKUP_BYTES = 64 * 1024 * 1024


def _verify_transaction_snapshot(path: Path, db: sqlite3.Connection) -> str:
    """Read only the complete serialized database, without creating WAL/SHM."""
    expected_tip = db.execute("SELECT record_digest FROM records ORDER BY sequence DESC LIMIT 1").fetchone()[0]
    expected_count = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    expected_metadata = [tuple(row) for row in db.execute("SELECT key,value FROM metadata ORDER BY key")]
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as restored:
        restored.row_factory = sqlite3.Row
        if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("OBSERVATION_BACKUP_SQLITE_INTEGRITY_FAILURE")
        if [tuple(row) for row in restored.execute("SELECT key,value FROM metadata ORDER BY key")] != expected_metadata:
            raise ValueError("OBSERVATION_BACKUP_METADATA_MISMATCH")
        previous, count = "GENESIS", 0
        for row in restored.execute("SELECT * FROM records ORDER BY sequence"):
            payload = json.loads(row["payload_json"])
            expected = _digest({"type": row["record_type"], "id": row["record_id"], "parent": row["parent_id"],
                                "created_at": row["created_at"], "payload": payload, "previous_digest": previous})
            if row["previous_digest"] != previous or row["record_digest"] != expected:
                raise ValueError("OBSERVATION_BACKUP_RESTORE_FAILED")
            previous = expected
            count += 1
        if previous != expected_tip or count != expected_count:
            raise ValueError("OBSERVATION_BACKUP_RESTORE_FAILED")
    return str(expected_tip)


def _write_verified_transaction_backup(*, ledger: ProspectiveLedger, db: sqlite3.Connection,
                                       backup_root: Path, now: datetime) -> Path:
    """Durably verify post-append state BEFORE primary transaction commit.

    A snapshot left by a rolled-back attempt is not promotion authority: its tip
    must equal a separately verified primary tip. Existing backup files are never
    overwritten. This does not establish an independent physical backup domain.
    """
    root = Path(backup_root).resolve()
    if root == ledger.path.parent or root.is_relative_to(ledger.path.parent):
        raise ValueError("BACKUP_MUST_USE_SEPARATE_DURABLE_ROOT")
    byte_count = db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0]
    if byte_count > MAX_TRANSACTION_BACKUP_BYTES:
        raise ValueError("OBSERVATION_TRANSACTION_BACKUP_MEMORY_LIMIT")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".observation-pending-", suffix=".sqlite3", dir=root, delete=False) as stream:
            pending = Path(stream.name)
            stream.write(db.serialize())
            stream.flush()
            os.fsync(stream.fileno())
        tip = _verify_transaction_snapshot(pending, db)
        digest = hashlib.sha256(pending.read_bytes()).hexdigest()
        target = root / f"report-card-{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{tip[:16]}.sqlite3"
        try:
            os.link(pending, target)
        except FileExistsError:
            if target.is_symlink():
                raise ValueError("OBSERVATION_IMMUTABLE_BACKUP_CONFLICT")
            _verify_transaction_snapshot(target, db)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
        sidecar = target.with_suffix(target.suffix + ".sha256")
        try:
            with sidecar.open("x", encoding="utf-8") as stream:
                os.chmod(sidecar, 0o600)
                stream.write(digest + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if sidecar.is_symlink() or sidecar.read_text().strip() != digest:
                raise ValueError("OBSERVATION_BACKUP_DIGEST_CONFLICT")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return target
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def apply_observation_bundle(*, ledger: ProspectiveLedger, backup_root: Path,
                             bundle: Mapping[str, Any], now: datetime) -> ObservationResult:
    """Append one complete matured horizon bundle; never acquire market data."""
    if bundle.get("schema_version") != BUNDLE_SCHEMA:
        raise ValueError("OBSERVATION_BUNDLE_SCHEMA_INVALID")
    activation = ledger.activation_timestamp()
    expected_activation = _utc(bundle.get("activation_timestamp"), "BUNDLE_ACTIVATION")
    if expected_activation != activation:
        raise ValueError("OBSERVATION_ACTIVATION_MISMATCH")
    if str(bundle.get("ledger_tip_before") or "") != ledger.verify():
        raise ValueError("OBSERVATION_LEDGER_TIP_MISMATCH")
    if bundle.get("customer_visible") is not False or bundle.get("public_performance_claims_allowed") is not False:
        raise ValueError("OBSERVATION_INTERNAL_ONLY_CONTRACT_REQUIRED")
    if int(bundle.get("provider_calls", -1)) != 0 or bundle.get("reacquisition") != "none":
        raise ValueError("OBSERVATION_WORKFLOW_MUST_BE_ZERO_PROVIDER")

    opened = _utc(bundle.get("session_open_at"), "SESSION_OPEN")
    closed = _utc(bundle.get("session_close_at"), "SESSION_CLOSE")
    certified_at = _utc(bundle.get("bundle_certified_at"), "BUNDLE_CERTIFIED")
    current = now.astimezone(timezone.utc)
    if (bundle.get("session_status") != FINALIZED_SESSION_STATUS or
            not bundle.get("trading_calendar_source") or not bundle.get("trading_calendar_version") or
            opened <= activation or closed <= opened or certified_at < closed or current < certified_at):
        raise ValueError("OBSERVATION_HORIZON_NOT_MATURE")

    horizon = int(bundle.get("horizon_trading_days", 0))
    records = list(bundle.get("records") or ())
    signals = ledger.rows("SIGNAL")
    expected_ids = {row["record_id"] for row in signals}
    actual_ids = [str(row.get("signal_id") or "") for row in records]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise ValueError("OBSERVATION_SIGNAL_COVERAGE_MISMATCH")

    signal_by_id = {row["record_id"]: row["payload"] for row in signals}
    prepared = []
    session_date = closed.date().isoformat()
    for record in records:
        signal_id = str(record["signal_id"])
        observation = dict(record.get("observation") or {})
        sessions: Sequence[str] = observation.get("trading_sessions") or ()
        if len(sessions) != horizon or str(sessions[-1]) != session_date:
            raise ValueError("OBSERVATION_SESSION_CONTRACT_MISMATCH")
        if observation.get("corporate_action_status") not in ALLOWED_CORPORATE_ACTION_STATUS:
            raise ValueError("CORPORATE_ACTION_STATUS_REQUIRED")
        if observation.get("price_source") not in ALLOWED_PRICE_SOURCES:
            raise ValueError("OBSERVATION_PRICE_AUTHORITY_INVALID")
        provenance = observation.get("price_provenance")
        if not isinstance(provenance, Mapping) or not all(provenance.get(key) for key in ("provider", "instrument", "as_of", "retrieved_at", "currency")):
            raise ValueError("OBSERVATION_PRICE_PROVENANCE_REQUIRED")
        if provenance.get("session_status") != FINALIZED_SESSION_STATUS:
            raise ValueError("OBSERVATION_PRICE_NOT_FINALIZED")
        if observation.get("data_status") == "AVAILABLE":
            reference = float(signal_by_id[signal_id]["reference_price"])
            observed = float(observation["observed_price"])
            spy_reference = float(observation.pop("benchmark_reference_price"))
            spy_observed = float(observation.pop("benchmark_observed_price"))
            stock_return = observed / reference - 1.0
            benchmark_return = spy_observed / spy_reference - 1.0
            observation.update(stock_return=stock_return, benchmark_return=benchmark_return,
                               excess_return=stock_return - benchmark_return)
        elif not observation.get("unavailable_reason"):
            raise ValueError("OBSERVATION_UNAVAILABLE_REASON_REQUIRED")
        prepared.append((signal_id, observation))

    backups: list[Path] = []
    def verified_backup_before_commit(db: sqlite3.Connection) -> None:
        backups.append(_write_verified_transaction_backup(
            ledger=ledger, db=db, backup_root=backup_root, now=current,
        ))

    appended, idempotent = append_observations_atomic(
        ledger, horizon=horizon, observations=prepared, now=current,
        expected_tip=str(bundle["ledger_tip_before"]), before_commit=verified_backup_before_commit,
    )
    tip = ledger.verify()
    backup = backups[0]
    return ObservationResult("OBSERVATIONS_RECORDED", appended, idempotent, len(signals), horizon,
                             session_date, tip, str(backup))


__all__ = ["ALLOWED_CORPORATE_ACTION_STATUS", "ALLOWED_PRICE_SOURCES", "BUNDLE_SCHEMA",
           "FINALIZED_SESSION_STATUS", "ObservationResult", "apply_observation_bundle"]
