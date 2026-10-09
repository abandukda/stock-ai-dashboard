"""Append-only prospective ledgers for shadow position-management validation."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from services.position_management import (
    DataCertainty, PositionInstruction, ReasonCode, TechnicalState, ThesisState,
    ValuationState, load_methodology,
)


SHADOW_SCHEMA_VERSION = "ATLAS_POSITION_MANAGEMENT_SHADOW_LEDGER_V1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


class AppendOnlyStateLedger:
    """Hash-chained SQLite ledger that cannot update or delete observations."""

    def __init__(self, path: Path, *, schema_version: str, activation_timestamp: str):
        self.path = Path(path).resolve()
        self.schema_version = schema_version
        self.activation = _timestamp(activation_timestamp)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state_records (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL UNIQUE,
                    record_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    record_digest TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS state_records_no_update BEFORE UPDATE ON state_records
                  BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SHADOW_UPDATE_FORBIDDEN'); END;
                CREATE TRIGGER IF NOT EXISTS state_records_no_delete BEFORE DELETE ON state_records
                  BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SHADOW_DELETE_FORBIDDEN'); END;
                COMMIT;
            """)
            values = {"schema_version": self.schema_version,
                      "activation_timestamp": self.activation.isoformat(), "customer_visible": "false"}
            for key, value in values.items():
                existing = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
                if existing and existing[0] != value:
                    raise ValueError(f"LEDGER_METADATA_CONFLICT:{key}")
                db.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES(?,?)", (key, value))
        os.chmod(self.path, 0o600)

    def append(self, *, record_id: str, record_type: str, created_at: str,
               payload: Mapping[str, Any]) -> bool:
        timestamp = _timestamp(created_at)
        if timestamp < self.activation:
            raise ValueError("PROSPECTIVE_ONLY_NO_BACKFILL")
        if payload.get("customer_visible") is not False:
            raise ValueError("CUSTOMER_VISIBILITY_MUST_REMAIN_OFF")
        encoded = _canonical(payload)
        self.initialize()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload_json,record_type,created_at FROM state_records WHERE record_id=?",
                                  (record_id,)).fetchone()
            if existing:
                if (existing[0], existing[1], existing[2]) != (encoded, record_type, timestamp.isoformat()):
                    db.execute("ROLLBACK")
                    raise ValueError("IMMUTABLE_SHADOW_RECORD_CONFLICT")
                db.execute("COMMIT")
                return False
            prior = db.execute("SELECT record_digest FROM state_records ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = prior[0] if prior else "GENESIS"
            digest = _digest({"record_id": record_id, "record_type": record_type,
                              "created_at": timestamp.isoformat(), "payload": payload,
                              "previous_digest": previous})
            db.execute("INSERT INTO state_records(record_id,record_type,created_at,payload_json,previous_digest,record_digest) "
                       "VALUES(?,?,?,?,?,?)", (record_id, record_type, timestamp.isoformat(), encoded, previous, digest))
            db.execute("COMMIT")
        return True

    def rows(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM state_records ORDER BY sequence").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def verify(self) -> str:
        previous = "GENESIS"
        for row in self.rows():
            expected = _digest({"record_id": row["record_id"], "record_type": row["record_type"],
                                "created_at": row["created_at"], "payload": row["payload"],
                                "previous_digest": previous})
            if row["previous_digest"] != previous or row["record_digest"] != expected:
                raise ValueError("SHADOW_LEDGER_INTEGRITY_FAILURE")
            previous = expected
        return previous


SHADOW_REQUIRED = {
    "signal_id", "ticker", "scan_timestamp", "methodology_version", "candidate_digest",
    "publication_digest", "evaluation_snapshot", "source_sha", "thesis_state", "valuation_state",
    "technical_state", "data_certainty", "position_instruction", "add_eligible", "review_required",
    "review_reason_codes", "reason_codes", "price", "certified_fair_value", "valuation_confidence",
    "fair_value_band", "inputs_digest", "rule_table_version", "customer_visible",
}


class ShadowPositionLedger(AppendOnlyStateLedger):
    def __init__(self, path: Path, *, activation_timestamp: str):
        super().__init__(path, schema_version=SHADOW_SCHEMA_VERSION, activation_timestamp=activation_timestamp)

    def append_evaluation(self, payload: Mapping[str, Any]) -> bool:
        missing = sorted(SHADOW_REQUIRED - set(payload))
        if missing:
            raise ValueError("SHADOW_RECORD_INCOMPLETE:" + ",".join(missing))
        cfg = load_methodology()
        for name in ("signal_id", "ticker", "candidate_digest", "publication_digest",
                     "evaluation_snapshot", "source_sha", "inputs_digest"):
            if not str(payload.get(name) or "").strip():
                raise ValueError(f"SHADOW_IDENTITY_INVALID:{name}")
        if payload["methodology_version"] != cfg["methodology_version"]:
            raise ValueError("SHADOW_METHODOLOGY_VERSION_NOT_ACTIVE")
        if payload["rule_table_version"] != cfg["rule_table_version"]:
            raise ValueError("SHADOW_RULE_TABLE_VERSION_NOT_ACTIVE")
        enum_fields = {
            "thesis_state": ThesisState, "valuation_state": ValuationState,
            "technical_state": TechnicalState, "data_certainty": DataCertainty,
            "position_instruction": PositionInstruction,
        }
        for name, enum_type in enum_fields.items():
            try:
                enum_type(str(payload[name]))
            except ValueError as exc:
                raise ValueError(f"SHADOW_ENUM_INVALID:{name}") from exc
        reasons = payload.get("reason_codes")
        if not isinstance(reasons, (list, tuple)) or not reasons:
            raise ValueError("SHADOW_REASON_CODES_REQUIRED")
        for code in (*reasons, *(payload.get("review_reason_codes") or ())):
            try:
                ReasonCode(str(code))
            except ValueError as exc:
                raise ValueError("SHADOW_REASON_CODE_INVALID") from exc
        _timestamp(str(payload["scan_timestamp"]))
        identity = {key: payload[key] for key in ("signal_id", "scan_timestamp", "methodology_version",
                                                   "evaluation_snapshot", "inputs_digest")}
        return self.append(record_id="shadow:" + _digest(identity), record_type="POSITION_STATE",
                           created_at=str(payload["scan_timestamp"]), payload=payload)


__all__ = ["AppendOnlyStateLedger", "SHADOW_SCHEMA_VERSION", "ShadowPositionLedger", "_digest"]
