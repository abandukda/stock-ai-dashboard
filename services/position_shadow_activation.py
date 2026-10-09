"""Fail-closed activation contract for prospective Position Management shadow ledgers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Mapping

from services.position_management import load_methodology
from services.position_management_ledgers import ShadowPositionLedger, _digest
from services.position_universe_validation import UniverseValidationLedger


HANDOFF_SCHEMA = "ATLAS_POSITION_SHADOW_HANDOFF_V1"
ACTIVATION_BOUNDARY = "2026-10-08T00:00:00+00:00"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_storage_roots(*, primary: Path, backup: Path, report_primary: Path | None = None,
                           report_backup: Path | None = None) -> dict[str, Any]:
    roots = [Path(primary).resolve(), Path(backup).resolve()]
    report_roots = {Path(item).resolve() for item in (report_primary, report_backup) if item}
    if roots[0] == roots[1] or any(root in report_roots for root in roots):
        raise ValueError("POSITION_SHADOW_STORAGE_SEPARATION_REQUIRED")
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"POSITION_SHADOW_STORAGE_ROOT_MISSING:{root}")
        if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
            raise ValueError(f"POSITION_SHADOW_STORAGE_PERMISSION_DENIED:{root}")
        if shutil.disk_usage(root).free < 100 * 1024 * 1024:
            raise ValueError(f"POSITION_SHADOW_STORAGE_SPACE_INSUFFICIENT:{root}")
    unexpected = [item.name for item in roots[0].iterdir()
                  if item.name not in {"manifests", "certification"}]
    if unexpected:
        raise ValueError("POSITION_SHADOW_STORAGE_NOT_PRISTINE:" + ",".join(sorted(unexpected)))
    return {"status": "PASS", "primary": str(roots[0]), "backup": str(roots[1]),
            "separate_from_report_card": True}


def validate_handoff(handoff: Mapping[str, Any]) -> dict[str, Any]:
    cfg = load_methodology()
    required = {"schema_version", "source_run_id", "source_sha", "candidate_digest",
                "publication_digest", "evaluation_snapshot", "scan_timestamp",
                "methodology_version", "rule_table_version", "signals", "universe",
                "provider_calls", "reacquisition", "customer_visible"}
    missing = sorted(required - set(handoff))
    if missing:
        raise ValueError("POSITION_SHADOW_HANDOFF_INCOMPLETE:" + ",".join(missing))
    if handoff["schema_version"] != HANDOFF_SCHEMA:
        raise ValueError("POSITION_SHADOW_HANDOFF_SCHEMA_INVALID")
    if handoff["methodology_version"] != cfg["methodology_version"]:
        raise ValueError("POSITION_SHADOW_HANDOFF_METHODOLOGY_MISMATCH")
    if handoff["rule_table_version"] != cfg["rule_table_version"]:
        raise ValueError("POSITION_SHADOW_HANDOFF_RULE_TABLE_MISMATCH")
    timestamp = datetime.fromisoformat(str(handoff["scan_timestamp"]).replace("Z", "+00:00"))
    boundary = datetime.fromisoformat(ACTIVATION_BOUNDARY)
    if timestamp.tzinfo is None or timestamp.astimezone(timezone.utc) < boundary:
        raise ValueError("POSITION_SHADOW_HANDOFF_NOT_PROSPECTIVE")
    if handoff["provider_calls"] != 0 or handoff["reacquisition"] != "none":
        raise ValueError("POSITION_SHADOW_ZERO_PROVIDER_REQUIRED")
    if handoff["customer_visible"] is not False:
        raise ValueError("POSITION_SHADOW_CUSTOMER_VISIBILITY_MUST_REMAIN_OFF")
    identities = ("source_sha", "candidate_digest", "publication_digest", "evaluation_snapshot")
    if any(not str(handoff.get(key) or "").strip() for key in identities):
        raise ValueError("POSITION_SHADOW_HANDOFF_IDENTITY_REQUIRED")
    signals = list(handoff["signals"] or ())
    universe = list(handoff["universe"] or ())
    if not signals or not universe:
        raise ValueError("POSITION_SHADOW_HANDOFF_POPULATION_REQUIRED")
    signal_ids = [str(row.get("signal_id") or "") for row in signals]
    universe_ids = [str(row.get("ticker") or "") for row in universe]
    if "" in signal_ids or len(signal_ids) != len(set(signal_ids)):
        raise ValueError("POSITION_SHADOW_SIGNAL_ID_INVALID")
    if "" in universe_ids or len(universe_ids) != len(set(universe_ids)):
        raise ValueError("POSITION_SHADOW_UNIVERSE_ID_INVALID")
    for row in (*signals, *universe):
        for key in identities:
            if row.get(key) != handoff[key]:
                raise ValueError(f"POSITION_SHADOW_HANDOFF_{key.upper()}_MISMATCH")
        if row.get("methodology_version") != cfg["methodology_version"] or row.get("rule_table_version") != cfg["rule_table_version"]:
            raise ValueError("POSITION_SHADOW_ROW_VERSION_MISMATCH")
        if row.get("scan_timestamp") != handoff["scan_timestamp"]:
            raise ValueError("POSITION_SHADOW_ROW_SNAPSHOT_MISMATCH")
        if row.get("customer_visible") is not False:
            raise ValueError("POSITION_SHADOW_ROW_CUSTOMER_VISIBLE")
    if any(row.get("publication_eligible") is not True or row.get("original_action") != "BUY_NOW" for row in signals):
        raise ValueError("POSITION_SHADOW_SIGNAL_POPULATION_NOT_PUBLISHABLE_BUY_NOW")
    return dict(handoff)


def build_dry_run(handoff: Mapping[str, Any]) -> dict[str, Any]:
    data = validate_handoff(handoff)
    signal_rows = sorted((dict(row) for row in data["signals"]), key=lambda row: row["signal_id"])
    universe_rows = sorted((dict(row) for row in data["universe"]), key=lambda row: row["ticker"])
    signal_digests = [_digest(row) for row in signal_rows]
    universe_digests = [_digest(row) for row in universe_rows]
    proposed_tip = _digest({"handoff": {key: data[key] for key in (
        "source_run_id", "source_sha", "candidate_digest", "publication_digest",
        "evaluation_snapshot", "scan_timestamp", "methodology_version", "rule_table_version")},
        "signal_digests": signal_digests, "universe_digests": universe_digests})
    return {"schema_version": HANDOFF_SCHEMA, "status": "DRY_RUN_PASS",
            "signal_count": len(signal_rows), "universe_count": len(universe_rows),
            "signal_ids": [row["signal_id"] for row in signal_rows],
            "tickers": [row["ticker"] for row in universe_rows],
            "signal_rows": signal_rows, "universe_rows": universe_rows,
            "signal_row_digests": signal_digests, "universe_row_digests": universe_digests,
            "proposed_ledger_tip": proposed_tip, "provider_calls": 0,
            "report_card_mutation": "NONE", "customer_visible": False}


def certify_two_dry_runs(handoff: Mapping[str, Any]) -> dict[str, Any]:
    first = build_dry_run(json.loads(_canonical(handoff)))
    second = build_dry_run(json.loads(_canonical(handoff)))
    if _canonical(first) != _canonical(second):
        raise ValueError("POSITION_SHADOW_DRY_RUN_NONDETERMINISTIC")
    return {"status": "POSITION_SHADOW_FIRST_WRITE_READY", "dry_run_1": first,
            "dry_run_2": second, "deterministic": True,
            "certification_digest": hashlib.sha256(_canonical(first)).hexdigest()}


def _sqlite_row_count(path: Path) -> int:
    with sqlite3.connect(path) as db:
        return int(db.execute("SELECT COUNT(*) FROM state_records").fetchone()[0])


def activate(*, handoff: Mapping[str, Any], primary: Path, backup: Path,
             report_primary: Path | None = None, report_backup: Path | None = None,
             allow_first_append: bool = False) -> dict[str, Any]:
    storage = validate_storage_roots(primary=primary, backup=backup,
                                     report_primary=report_primary, report_backup=report_backup)
    certification = certify_two_dry_runs(handoff)
    if not allow_first_append:
        return {"status": "POSITION_SHADOW_FIRST_WRITE_READY", "storage": storage,
                "certification": certification, "durable_append_performed": False}
    primary = Path(primary).resolve(); backup = Path(backup).resolve()
    signal = ShadowPositionLedger(primary / "signal-ledger.sqlite3", activation_timestamp=ACTIVATION_BOUNDARY)
    universe = UniverseValidationLedger(primary / "universe-ledger.sqlite3", activation_timestamp=ACTIVATION_BOUNDARY)
    appended_signal = sum(signal.append_evaluation(row) for row in certification["dry_run_1"]["signal_rows"])
    appended_universe = sum(universe.append_state(row) for row in certification["dry_run_1"]["universe_rows"])
    signal_tip, universe_tip = signal.verify(), universe.verify()
    idempotent_signal = sum(signal.append_evaluation(row) for row in certification["dry_run_1"]["signal_rows"])
    idempotent_universe = sum(universe.append_state(row) for row in certification["dry_run_1"]["universe_rows"])
    if idempotent_signal or idempotent_universe:
        raise ValueError("POSITION_SHADOW_IDEMPOTENCY_FAILURE")
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = str(handoff["scan_timestamp"]).replace(":", "").replace("+", "_")
    manifest = {"signal": {}, "universe": {}}
    for name, ledger, tip in (("signal", signal, signal_tip), ("universe", universe, universe_tip)):
        destination = backup / f"{name}-ledger-{stamp}.sqlite3"
        with sqlite3.connect(ledger.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)
        os.chmod(destination, 0o600)
        with tempfile.TemporaryDirectory(prefix="atlas-position-shadow-restore-") as directory:
            restored_path = Path(directory) / destination.name
            shutil.copy2(destination, restored_path)
            restored = (ShadowPositionLedger(restored_path, activation_timestamp=ACTIVATION_BOUNDARY)
                        if name == "signal" else UniverseValidationLedger(restored_path, activation_timestamp=ACTIVATION_BOUNDARY))
            if restored.verify() != tip or _sqlite_row_count(restored_path) != _sqlite_row_count(ledger.path):
                raise ValueError("POSITION_SHADOW_BACKUP_RESTORE_FAILED")
        manifest[name] = {"path": str(destination), "sha256": _sha256(destination),
                          "rows": _sqlite_row_count(destination), "tip": tip}
    health = {"status": "ATLAS_POSITION_MANAGEMENT_V1_1_SHADOW_ACTIVE",
              "primary_root": str(primary), "backup_root": str(backup),
              "signal_ledger_row_count": _sqlite_row_count(signal.path),
              "universe_ledger_row_count": _sqlite_row_count(universe.path),
              "last_write": handoff["scan_timestamp"], "last_certified_source_run": handoff["source_run_id"],
              "candidate_digest": handoff["candidate_digest"], "publication_digest": handoff["publication_digest"],
              "methodology_version": handoff["methodology_version"], "rule_table_version": handoff["rule_table_version"],
              "ledger_integrity": "PASS", "backup_integrity": "PASS", "provider_calls": 0,
              "customer_visible": False, "report_card_mutation": "NONE", "backups": manifest}
    certification_dir = primary / "certification"; certification_dir.mkdir(mode=0o700, exist_ok=True)
    (certification_dir / "position_shadow_health.json").write_bytes(_canonical(health) + b"\n")
    return health


__all__ = ["ACTIVATION_BOUNDARY", "HANDOFF_SCHEMA", "activate", "build_dry_run",
           "certify_two_dry_runs", "validate_handoff", "validate_storage_roots"]
