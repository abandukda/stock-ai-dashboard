"""Internal-only prospective Report Card capture and durable ledger.

This module consumes already-certified publication rows.  It never acquires
provider data, changes an ATLAS decision, backfills a signal, or enables a
customer-facing Report Card.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from services.report_card import HORIZONS, SignalRecord, build_signal_record, internal_report
from services.report_card_governance import public_report_allowed


SCHEMA_VERSION = "ATLAS_INTERNAL_PROSPECTIVE_LEDGER_V1"
CAPTURE_VERSION = "ATLAS_CERTIFIED_PUBLICATION_CAPTURE_V1"
ELIGIBLE_ACTIONS = frozenset({"BUY_NOW"})
DEFAULT_MAX_EVIDENCE_AGE = timedelta(hours=36)


def _utc(value: Any, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name}_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def _manifest_identity(manifest: Mapping[str, Any]) -> dict[str, str]:
    candidate = dict(manifest.get("executor_candidate_identity") or {})
    release = dict(manifest.get("release_certification") or {})
    promotion = dict(manifest.get("promotion_governance") or {})
    handoff = dict(manifest.get("report_card_capture_authority") or {})
    if handoff and (handoff.get("status") != "PASS" or
                    handoff.get("classification") != "FINNHUB_FULL_UNIVERSE_CERTIFICATION_CLOSED_GREEN"):
        raise ValueError("REPORT_CARD_CAPTURE_AUTHORITY_INVALID")
    identity = {
        "candidate_digest": str(candidate.get("candidate_digest") or release.get("candidate_digest") or ""),
        "publication_digest": str(release.get("publication_digest") or promotion.get("publication_digest") or handoff.get("publication_digest") or ""),
        "source_sha": str(candidate.get("source_sha") or release.get("source_sha") or ""),
        "methodology_version": str(candidate.get("methodology_version") or manifest.get("methodology_version") or ""),
        "provider_authority_version": str(candidate.get("provider_authority_version") or manifest.get("provider_authority_version") or ""),
    }
    if manifest.get("publication_gate_status") != "PASS" or manifest.get("artifact_lineage_status") != "COHERENT":
        raise ValueError("PUBLICATION_NOT_CERTIFIED")
    if any(not value for value in identity.values()):
        raise ValueError("PUBLICATION_IDENTITY_INCOMPLETE")
    return identity


def _field(evaluation: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    result = (evaluation.get("fields") or {}).get(name)
    return result if isinstance(result, Mapping) else {}


def _all_evidence_ids(row: Mapping[str, Any], evaluation: Mapping[str, Any]) -> tuple[str, ...]:
    values: set[str] = set()
    for item in (row.get("professional_evidence_lineage") or {}).get("evidence_ids") or ():
        if item:
            values.add(str(item))
    for field in (evaluation.get("fields") or {}).values():
        if isinstance(field, Mapping):
            values.update(str(item) for item in field.get("evidence_ids") or () if item)
    return tuple(sorted(values))


@dataclass(frozen=True)
class CaptureResult:
    status: str
    captured: int
    idempotent: int
    rejected: int
    signal_ids: tuple[str, ...]
    reasons: tuple[str, ...]


class ProspectiveLedger:
    """SQLite append-only ledger with hash chaining and verified backups."""

    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                  record_type TEXT NOT NULL,
                  record_id TEXT NOT NULL UNIQUE,
                  parent_id TEXT,
                  created_at TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  previous_digest TEXT NOT NULL,
                  record_digest TEXT NOT NULL UNIQUE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS signal_semantic_identity
                  ON records(json_extract(payload_json, '$.semantic_identity'))
                  WHERE record_type = 'SIGNAL';
                CREATE TRIGGER IF NOT EXISTS records_no_update BEFORE UPDATE ON records
                  BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_UPDATE_FORBIDDEN'); END;
                CREATE TRIGGER IF NOT EXISTS records_no_delete BEFORE DELETE ON records
                  BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_DELETE_FORBIDDEN'); END;
                COMMIT;
                """
            )
            db.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES('schema_version',?)", (SCHEMA_VERSION,))
        os.chmod(self.path, 0o600)

    def activate(self, *, activation_timestamp: str, now: datetime, maximum_clock_skew_seconds: int = 300) -> str:
        self.initialize()
        with self._connect() as db:
            existing = db.execute("SELECT value FROM metadata WHERE key='activation_timestamp'").fetchone()
        if existing:
            return str(existing[0])
        activation = _utc(activation_timestamp, "ACTIVATION")
        current = now.astimezone(timezone.utc)
        if abs((current - activation).total_seconds()) > maximum_clock_skew_seconds:
            raise ValueError("ACTIVATION_TIMESTAMP_MUST_BE_CURRENT_NOT_BACKDATED")
        normalized = activation.isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT value FROM metadata WHERE key='activation_timestamp'").fetchone()
            if existing:
                db.execute("COMMIT")
                return str(existing[0])
            db.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES('activation_timestamp',?)", (normalized,))
            db.execute("COMMIT")
        return normalized

    def activation_timestamp(self) -> datetime:
        with self._connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='activation_timestamp'").fetchone()
        if not row:
            raise PermissionError("INTERNAL_PROSPECTIVE_TRACKING_NOT_ACTIVATED")
        return _utc(row[0], "ACTIVATION")

    def append(self, record_type: str, record_id: str, payload: Mapping[str, Any], *, created_at: datetime,
               parent_id: str | None = None) -> bool:
        self.initialize()
        encoded = _canonical(payload)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload_json,record_type,parent_id FROM records WHERE record_id=?", (record_id,)).fetchone()
            if existing:
                if existing[0] != encoded or existing[1] != record_type or existing[2] != parent_id:
                    db.execute("ROLLBACK")
                    raise ValueError("IMMUTABLE_RECORD_CONFLICT")
                db.execute("COMMIT")
                return False
            previous = db.execute("SELECT record_digest FROM records ORDER BY sequence DESC LIMIT 1").fetchone()
            previous_digest = str(previous[0]) if previous else "GENESIS"
            digest = _digest({"type": record_type, "id": record_id, "parent": parent_id,
                              "created_at": created_at.astimezone(timezone.utc).isoformat(),
                              "payload": payload, "previous_digest": previous_digest})
            db.execute(
                "INSERT INTO records(record_type,record_id,parent_id,created_at,payload_json,previous_digest,record_digest) VALUES(?,?,?,?,?,?,?)",
                (record_type, record_id, parent_id, created_at.astimezone(timezone.utc).isoformat(), encoded,
                 previous_digest, digest),
            )
            db.execute("COMMIT")
        return True

    def rows(self, record_type: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            query = "SELECT * FROM records" + (" WHERE record_type=?" if record_type else "") + " ORDER BY sequence"
            rows = db.execute(query, (record_type,) if record_type else ()).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def verify(self) -> str:
        previous = "GENESIS"
        for row in self.rows():
            payload = row["payload"]
            expected = _digest({"type": row["record_type"], "id": row["record_id"], "parent": row["parent_id"],
                                "created_at": row["created_at"], "payload": payload, "previous_digest": previous})
            if row["previous_digest"] != previous or row["record_digest"] != expected:
                raise ValueError("LEDGER_INTEGRITY_FAILURE")
            previous = expected
        return previous

    def backup(self, backup_directory: Path, *, now: datetime) -> Path:
        self.verify()
        destination_root = Path(backup_directory).resolve()
        if destination_root == self.path.parent or destination_root.is_relative_to(self.path.parent):
            raise ValueError("BACKUP_MUST_USE_SEPARATE_DURABLE_ROOT")
        destination_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = destination_root / f"report-card-{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
        with self._connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
        os.chmod(destination, 0o600)
        restored = ProspectiveLedger(destination)
        if restored.verify() != self.verify():
            destination.unlink(missing_ok=True)
            raise ValueError("BACKUP_RESTORE_INTEGRITY_FAILURE")
        digest_path = destination.with_suffix(destination.suffix + ".sha256")
        digest_path.write_text(hashlib.sha256(destination.read_bytes()).hexdigest() + "\n", encoding="utf-8")
        os.chmod(digest_path, 0o600)
        return destination


def capture_certified_publication(*, ledger: ProspectiveLedger, manifest: Mapping[str, Any],
                                  rows: Sequence[Mapping[str, Any]], observed_at: datetime,
                                  maximum_evidence_age: timedelta = DEFAULT_MAX_EVIDENCE_AGE) -> CaptureResult:
    identity = _manifest_identity(manifest)
    activation = ledger.activation_timestamp()
    now = observed_at.astimezone(timezone.utc)
    if now < activation:
        raise ValueError("OBSERVATION_PRECEDES_ACTIVATION")
    captured = idempotent = rejected = 0
    signal_ids: list[str] = []
    reasons: list[str] = []
    existing_signals = {item["record_id"]: item["payload"] for item in ledger.rows("SIGNAL")}
    for row in rows:
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
        certification = row.get("publication_certification") or {}
        evaluation = row.get("certified_customer_evaluation") or {}
        decision = evaluation.get("decision") or {}
        fields = evaluation.get("fields") or {}
        action = str(decision.get("action") or "")
        reason = None
        if not ticker or row.get("security_type") not in {"COMMON_STOCK", "ADR", "ADS"}:
            reason = "INVALID_SECURITY"
        elif not certification.get("customer_publication_allowed") or not evaluation.get("customer_publication_allowed"):
            reason = "WITHHELD_OR_NOT_CUSTOMER_PUBLISHABLE"
        elif action not in ELIGIBLE_ACTIONS:
            reason = "ACTION_NOT_ELIGIBLE"
        elif row.get("candidate_digest") != identity["candidate_digest"] or row.get("source_sha") != identity["source_sha"]:
            reason = "ROW_PUBLICATION_IDENTITY_MISMATCH"
        evidence_at_raw = row.get("professional_evidence_as_of") or row.get("evidence_snapshot_at")
        try:
            evidence_at = _utc(evidence_at_raw, "EVIDENCE")
        except ValueError:
            evidence_at = None
            reason = reason or "EVIDENCE_TIMESTAMP_INVALID"
        if evidence_at and (now - evidence_at > maximum_evidence_age or evidence_at > now):
            reason = reason or "STALE_OR_FUTURE_EVIDENCE"
        evidence_ids = _all_evidence_ids(row, evaluation)
        fair_value = _field(evaluation, "atlas_fair_value")
        upside = _field(evaluation, "atlas_upside_pct")
        price = _field(evaluation, "certified_market_price") or _field(evaluation, "current_price")
        reference_price = price.get("value") if price else row.get("current_price") or row.get("price")
        price_at_raw = price.get("as_of") if price else (certification.get("components", {}).get("market", {}).get("lineage", {}).get("as_of"))
        try:
            price_at = _utc(price_at_raw, "REFERENCE_PRICE")
        except ValueError:
            price_at = None
            reason = reason or "REFERENCE_PRICE_PROVENANCE_INVALID"
        if not evidence_ids:
            reason = reason or "EVIDENCE_IDS_REQUIRED"
        if reference_price in (None, ""):
            reason = reason or "REFERENCE_PRICE_REQUIRED"
        if reason:
            rejected += 1
            reasons.append(f"{ticker or 'UNKNOWN'}:{reason}")
            continue
        snapshot_id = str((evaluation.get("digests") or {}).get("evaluation_snapshot_id") or "")
        decision_digest = str((evaluation.get("digests") or {}).get("decision_digest") or decision.get("decision_digest") or "")
        if not snapshot_id or not decision_digest:
            rejected += 1; reasons.append(f"{ticker}:CERTIFIED_DECISION_IDENTITY_REQUIRED"); continue
        semantic_identity = _digest({"ticker": ticker, "candidate": identity["candidate_digest"],
                                     "publication": identity["publication_digest"], "snapshot": snapshot_id,
                                     "decision": decision_digest, "action": action})
        first_seen_at = str(existing_signals.get(semantic_identity, {}).get("first_seen_at") or now.isoformat())
        payload = {
            "schema_version": SCHEMA_VERSION, "capture_version": CAPTURE_VERSION,
            "semantic_identity": semantic_identity, "signal_id": semantic_identity, "ticker": ticker,
            "security_identity": f"{ticker}:{row.get('security_type')}", "first_seen_at": first_seen_at,
            "publication_timestamp": _utc(certification.get("certified_at"), "PUBLICATION").isoformat(),
            "evidence_as_of": evidence_at.isoformat(), "source_sha": identity["source_sha"],
            "publication_digest": identity["publication_digest"], "candidate_digest": identity["candidate_digest"],
            "evaluation_snapshot_id": snapshot_id, "decision_digest": decision_digest,
            "canonical_recommendation": action, "opportunity": float(decision["opportunity"]),
            "decision_confidence": float(decision["decision_confidence"]),
            "atlas_fair_value": fair_value.get("value"), "expected_return": upside.get("value"),
            "entry": (evaluation.get("trade_plan") or {}).get("preferred_entry"),
            "target": (evaluation.get("trade_plan") or {}).get("target"),
            "stop": (evaluation.get("trade_plan") or {}).get("stop_loss"),
            "reference_price": float(reference_price), "reference_price_timestamp": price_at.isoformat(),
            "evidence_ids": list(evidence_ids), "eligibility_status": "LIVE_PROSPECTIVE_SIGNAL",
            "withholding_status": "CUSTOMER_PUBLISHABLE", "methodology_version": identity["methodology_version"],
            "provider_authority_version": identity["provider_authority_version"],
        }
        # Reuse the existing prospective-only record validator before persistence.
        build_signal_record({
            "ticker": ticker, "canonical_action": action,
            "publication_timestamp": payload["publication_timestamp"],
            "executable_reference_timestamp": now.isoformat(), "certified_reference_price": reference_price,
            "fair_value": payload["atlas_fair_value"], "expected_potential": payload["expected_return"],
            "opportunity": payload["opportunity"], "decision_confidence": payload["decision_confidence"],
            "methodology_version": identity["methodology_version"],
            "provider_authority_version": identity["provider_authority_version"],
            "candidate_digest": identity["candidate_digest"], "evidence_ids": evidence_ids,
            "eligibility_state": "LIVE_PROSPECTIVE_SIGNAL", "signal_id": semantic_identity,
        }, activation_authorized=True)
        inserted = ledger.append("SIGNAL", semantic_identity, payload, created_at=now)
        captured += int(inserted); idempotent += int(not inserted); signal_ids.append(semantic_identity)
    status = "CAPTURED" if captured else ("IDEMPOTENT_NO_CHANGE" if idempotent else "NO_ELIGIBLE_SIGNAL")
    return CaptureResult(status, captured, idempotent, rejected, tuple(signal_ids), tuple(sorted(reasons)))


def append_amendment(ledger: ProspectiveLedger, *, signal_id: str, amendment: Mapping[str, Any], now: datetime) -> str:
    if not any(row["record_id"] == signal_id for row in ledger.rows("SIGNAL")):
        raise ValueError("AMENDMENT_PARENT_SIGNAL_NOT_FOUND")
    amendment_id = _digest({"parent": signal_id, "amendment": amendment, "at": now.astimezone(timezone.utc).isoformat()})
    ledger.append("AMENDMENT", amendment_id, {"schema_version": SCHEMA_VERSION, **dict(amendment)},
                  created_at=now, parent_id=signal_id)
    return amendment_id


def append_observation(ledger: ProspectiveLedger, *, signal_id: str, horizon: int,
                       observation: Mapping[str, Any], now: datetime) -> str:
    if horizon not in HORIZONS:
        raise ValueError("UNREGISTERED_REPORT_CARD_HORIZON")
    if not any(row["record_id"] == signal_id for row in ledger.rows("SIGNAL")):
        raise ValueError("OBSERVATION_SIGNAL_NOT_FOUND")
    required = ("observed_price", "observed_at", "price_source", "corporate_action_status",
                "data_status", "benchmark_ticker", "benchmark_return", "benchmark_observed_at",
                "trading_sessions")
    missing = [key for key in required if key not in observation]
    if missing:
        raise ValueError("OBSERVATION_FIELDS_MISSING:" + ",".join(missing))
    status_value = str(observation["data_status"])
    allowed_status = {"AVAILABLE", "FUTURE_DATA_UNAVAILABLE", "MISSING_PRICE", "STALE_PRICE",
                      "DELISTED", "MERGER_PENDING_GOVERNED_TREATMENT"}
    if status_value not in allowed_status:
        raise ValueError("OBSERVATION_DATA_STATUS_UNREGISTERED")
    sessions = tuple(str(item) for item in observation["trading_sessions"])
    if status_value == "AVAILABLE":
        if observation["observed_price"] is None or len(sessions) != horizon or len(set(sessions)) != horizon:
            raise ValueError("OBSERVATION_TRADING_CALENDAR_INCOMPLETE")
        observed = _utc(observation["observed_at"], "OBSERVED")
        benchmark_observed = _utc(observation["benchmark_observed_at"], "BENCHMARK_OBSERVED")
        if observed.date().isoformat() != sessions[-1] or benchmark_observed.date() != observed.date():
            raise ValueError("STOCK_BENCHMARK_BOUNDARIES_NOT_ALIGNED")
        if str(observation["benchmark_ticker"]).upper() != "SPY":
            raise ValueError("REPORT_CARD_BENCHMARK_MUST_BE_SPY")
        if observation.get("stock_return") is None or observation.get("benchmark_return") is None or observation.get("excess_return") is None:
            raise ValueError("AVAILABLE_OBSERVATION_RETURNS_REQUIRED")
    elif observation.get("observed_price") is not None and status_value in {"MISSING_PRICE", "FUTURE_DATA_UNAVAILABLE"}:
        raise ValueError("UNAVAILABLE_OBSERVATION_MUST_NOT_INVENT_PRICE")
    if observation.get("target_and_stop_same_daily_bar") and not observation.get("intraday_path_evidence"):
        status = "AMBIGUOUS_DAILY_BAR_NO_ORDER_INFERRED"
    else:
        status = str(observation.get("target_stop_status") or "NOT_EVALUATED")
    payload = {"schema_version": SCHEMA_VERSION, "signal_id": signal_id, "horizon_trading_days": horizon,
               **dict(observation), "target_stop_status": status}
    observation_id = _digest({"signal": signal_id, "horizon": horizon, "observed_at": observation["observed_at"]})
    ledger.append("OBSERVATION", observation_id, payload, created_at=now, parent_id=signal_id)
    return observation_id


def internal_dashboard(ledger: ProspectiveLedger, *, authorized: bool) -> dict[str, Any]:
    if not authorized:
        raise PermissionError("INTERNAL_REPORT_CARD_ACCESS_REQUIRED")
    if public_report_allowed():
        raise PermissionError("PUBLIC_REPORT_CARD_MUST_REMAIN_OFF")
    signals = [row["payload"] for row in ledger.rows("SIGNAL")]
    observations = [row["payload"] for row in ledger.rows("OBSERVATION")]
    returns = [float(item["stock_return"]) for item in observations
               if item.get("data_status") == "AVAILABLE" and item.get("stock_return") is not None]
    excess = [float(item["excess_return"]) for item in observations
              if item.get("data_status") == "AVAILABLE" and item.get("excess_return") is not None]
    return {
        "classification": "INTERNAL_ONLY_PROSPECTIVE_REPORT_CARD",
        "customer_visible": False, "public_performance_claims_allowed": False,
        "activation_timestamp": ledger.activation_timestamp().isoformat(), "ledger_tip_digest": ledger.verify(),
        "active_signal_count": len(signals), "observation_count": len(observations),
        "signal_start_dates": {item["ticker"]: item["first_seen_at"] for item in signals},
        "observation_coverage": {str(h): sum(item.get("horizon_trading_days") == h for item in observations) for h in HORIZONS},
        "mean_return": sum(returns) / len(returns) if returns else None,
        "median_return": sorted(returns)[len(returns) // 2] if returns else None,
        "mean_excess_return": sum(excess) / len(excess) if excess else None,
        "winner_count": sum(value > 0 for value in returns), "loser_count": sum(value < 0 for value in returns),
        "unavailable_outcomes": sum(item.get("data_status") != "AVAILABLE" for item in observations),
        "limitations": ["PROSPECTIVE_ONLY", "INTERNAL_NOT_CUSTOMER_FACING",
                        "NO_CONCLUSION_WHILE_SAMPLE_IS_INSUFFICIENT"],
        "sample_size_warning": "INSUFFICIENT_SAMPLE_FOR_CONCLUSIONS" if len(signals) < 20 else None,
    }


__all__ = ["CAPTURE_VERSION", "CaptureResult", "DEFAULT_MAX_EVIDENCE_AGE", "ProspectiveLedger",
           "SCHEMA_VERSION", "append_amendment", "append_observation", "capture_certified_publication",
           "internal_dashboard"]
