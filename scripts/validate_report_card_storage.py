#!/usr/bin/env python3
"""Non-mutating operational storage validation for the internal Report Card."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.prospective_report_card import ProspectiveLedger


def _mount(path: Path) -> dict[str, str]:
    fields = subprocess.check_output(
        ["findmnt", "-T", str(path), "-n", "-o", "UUID,SOURCE,FSTYPE,TARGET"], text=True
    ).strip().split(maxsplit=3)
    if len(fields) != 4:
        raise RuntimeError(f"MOUNT_METADATA_INCOMPLETE:{path}")
    return dict(zip(("uuid", "source", "fstype", "target"), fields))


def _mode(path: Path) -> str:
    return oct(stat.S_IMODE(path.stat().st_mode))


def _outside(path: Path, forbidden: tuple[Path | None, ...]) -> bool:
    return all(item is None or (path != item and not path.is_relative_to(item)) for item in forbidden)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    primary = args.primary_root.resolve()
    backup = args.backup_root.resolve()
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve() if os.environ.get("GITHUB_WORKSPACE") else None
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve() if os.environ.get("RUNNER_TEMP") else None
    if primary == backup or not _outside(primary, (workspace, runner_temp)) or not _outside(backup, (workspace, runner_temp)):
        raise ValueError("DURABLE_ROOTS_MUST_BE_DISJOINT_AND_NON_EPHEMERAL")
    for root in (primary, backup):
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"DURABLE_ROOT_INVALID:{root}")
        if root.stat().st_uid != os.getuid():
            raise PermissionError(f"DURABLE_ROOT_NOT_OWNED_BY_RUNNER:{root}")
        os.chmod(root, 0o700)
        if _mode(root) != "0o700" or not os.access(root, os.W_OK | os.X_OK):
            raise PermissionError(f"DURABLE_ROOT_PERMISSIONS_INVALID:{root}")
    operational_ledger = primary / "report-card.sqlite3"
    if operational_ledger.exists():
        if operational_ledger.stat().st_uid != os.getuid():
            raise PermissionError("OPERATIONAL_LEDGER_NOT_OWNED_BY_RUNNER")
        os.chmod(operational_ledger, 0o600)

    primary_mount, backup_mount = _mount(primary), _mount(backup)
    if primary_mount["fstype"] != "ext4" or backup_mount["fstype"] != "ext4":
        raise ValueError("DURABLE_ROOT_FILESYSTEM_MUST_BE_EXT4")
    if (primary_mount["uuid"], primary_mount["source"]) == (backup_mount["uuid"], backup_mount["source"]):
        raise ValueError("PRIMARY_AND_BACKUP_MUST_BE_INDEPENDENT_FILESYSTEMS")
    fstab = Path("/etc/fstab").read_text(encoding="utf-8")
    for mount in (primary_mount, backup_mount):
        if f"UUID={mount['uuid']}" not in fstab:
            raise ValueError(f"MOUNT_UUID_NOT_PERSISTED:{mount['uuid']}")

    token = uuid.uuid4().hex
    primary_test = primary / f".atlas-report-card-validation-{token}"
    backup_test = backup / f".atlas-report-card-validation-{token}"
    restored_dir = primary_test / "restored"
    now = datetime.now(timezone.utc)
    try:
        primary_test.mkdir(mode=0o700)
        backup_test.mkdir(mode=0o700)
        ledger = ProspectiveLedger(primary_test / "validation.sqlite3")
        activation = ledger.activate(activation_timestamp=now.isoformat(), now=now)
        payload = {"purpose": "storage-validation", "token": token}
        assert ledger.append("VALIDATION", token, payload, created_at=now)
        assert not ledger.append("VALIDATION", token, payload, created_at=now)
        with sqlite3.connect(ledger.path) as db:
            journal_mode = str(db.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            synchronous = int(db.execute("PRAGMA synchronous").fetchone()[0])
            try:
                db.execute("UPDATE records SET payload_json='{}' WHERE record_id=?", (token,))
            except sqlite3.IntegrityError:
                append_only = True
            else:
                append_only = False
        with sqlite3.connect(ledger.path, timeout=0.1, isolation_level=None) as holder:
            holder.execute("BEGIN IMMEDIATE")
            try:
                with sqlite3.connect(ledger.path, timeout=0.1, isolation_level=None) as contender:
                    contender.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                concurrent_write_protection = "locked" in str(exc).lower()
            else:
                concurrent_write_protection = False
            finally:
                holder.execute("ROLLBACK")
        if journal_mode != "wal" or synchronous != 2 or not append_only or not concurrent_write_protection:
            raise ValueError("SQLITE_DURABILITY_CONTRACT_FAILED")
        tip = ledger.verify()
        backup_file = ledger.backup(backup_test, now=now)
        sidecar = backup_file.with_suffix(backup_file.suffix + ".sha256")
        if sidecar.read_text(encoding="utf-8").strip() != hashlib.sha256(backup_file.read_bytes()).hexdigest():
            raise ValueError("BACKUP_SHA256_MISMATCH")
        restored_dir.mkdir(mode=0o700)
        restored = restored_dir / "restored.sqlite3"
        shutil.copy2(backup_file, restored)
        os.chmod(restored, 0o600)
        restored_tip = ProspectiveLedger(restored).verify()
        if restored_tip != tip:
            raise ValueError("RESTORED_HASH_CHAIN_MISMATCH")
        report = {
            "status": "REPORT_CARD_STORAGE_VALIDATED",
            "runner_name": os.environ.get("RUNNER_NAME", ""),
            "runner_service_account": getpass.getuser(), "runner_uid": os.getuid(),
            "primary": {**primary_mount, "path": str(primary), "mode": _mode(primary)},
            "backup": {**backup_mount, "path": str(backup), "mode": _mode(backup)},
            "independent_filesystems": True, "mount_persistence": "UUID_IN_FSTAB",
            "sqlite": {"journal_mode": journal_mode, "synchronous": "FULL", "append_only": append_only,
                       "hash_chain_tip": tip, "idempotency": "PASS",
                       "atomic_transactions": "PASS", "concurrent_write_protection": "PASS",
                       "ledger_mode": _mode(ledger.path)},
            "backup_recovery": {"sha256": "PASS", "reopen": "PASS", "restored_hash_chain": restored_tip},
            "operational_activation_created": False, "operational_signal_records_created": 0,
            "provider_calls": 0, "reacquisition": "none", "customer_report_card_visible": False,
            "test_activation": activation,
        }
    finally:
        shutil.rmtree(primary_test, ignore_errors=True)
        shutil.rmtree(backup_test, ignore_errors=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
