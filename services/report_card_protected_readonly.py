"""Read-only protected storage audit and provider-free plan preparation."""
from __future__ import annotations
from datetime import datetime
import hashlib, json, os, pwd, sqlite3, stat, tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from services.prospective_report_card import ProspectiveLedger
from services.report_card_market_evidence_acquisition import PLAN_AUTHORIZATION_TOKEN, build_acquisition_plan
from services.report_card_operational_controls import digest, reconcile_publication


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_protected_validation(*, ledger_path: Path, backup_root: Path,
        calendar: Mapping[str, Any], source_sha: str,
        publication_rows: list[Mapping[str, Any]], workspace: Path | None = None,
        mount_probe: Callable[[Path], Mapping[str, Any]] | None = None,
        kill_switch_path: Path | None = None,
        owner_probe: Callable[[Path], str] | None = None) -> dict[str, Any]:
    ledger_path, backup_root = ledger_path.resolve(), backup_root.resolve()
    if not ledger_path.is_file() or not backup_root.is_dir():
        raise FileNotFoundError("PROTECTED_LEDGER_AND_BACKUP_ROOT_REQUIRED")
    if workspace and (ledger_path.is_relative_to(workspace.resolve()) or backup_root.is_relative_to(workspace.resolve())):
        raise ValueError("PROTECTED_STORAGE_INSIDE_GIT_WORKSPACE")
    before = _file_sha(ledger_path)
    mode = oct(stat.S_IMODE(ledger_path.stat().st_mode))
    if mode != "0o600":
        raise PermissionError("PROTECTED_LEDGER_MODE_MUST_BE_0600")
    probe = mount_probe or (lambda path: {"path": str(path), "device": path.stat().st_dev})
    primary_mount, backup_mount = dict(probe(ledger_path)), dict(probe(backup_root))
    if primary_mount.get("device") == backup_mount.get("device"):
        raise ValueError("PRIMARY_AND_BACKUP_NOT_ISOLATED")
    with tempfile.TemporaryDirectory(prefix="atlas-report-card-readonly-") as directory:
        snapshot_path = Path(directory) / "ledger.sqlite3"
        uri = f"file:{ledger_path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as source, sqlite3.connect(snapshot_path) as target:
            source.execute("PRAGMA query_only=ON")
            source.backup(target)
        snapshot = ProspectiveLedger(snapshot_path)
        tip = snapshot.verify()
        signals = [row["payload"] for row in snapshot.rows("SIGNAL")]
        plan = build_acquisition_plan(ledger=snapshot, calendar=calendar,
            authorization=PLAN_AUTHORIZATION_TOKEN, source_sha=source_sha)
    verified_backups = []
    for candidate in sorted(backup_root.glob("report-card-*.sqlite3")):
        sidecar = candidate.with_suffix(candidate.suffix + ".sha256")
        if sidecar.is_file() and sidecar.read_text().strip().split()[0] == _file_sha(candidate):
            verified_backups.append({"name": candidate.name, "sha256": _file_sha(candidate)})
    if not verified_backups:
        raise FileNotFoundError("SIDE_CAR_VERIFIED_BACKUP_REQUIRED")
    reconciliation = reconcile_publication(signals=signals, publication_rows=publication_rows)
    kill_switch = {"status":"NOT_PROVIDED","safe_for_live_calls":False}
    if kill_switch_path is not None:
        switch = kill_switch_path.resolve()
        if not switch.is_file():
            raise FileNotFoundError("KILL_SWITCH_EVIDENCE_REQUIRED")
        state = switch.read_text(encoding="utf-8").strip()
        if state not in {"OPEN", "CLOSED"}:
            raise ValueError("KILL_SWITCH_STATE_INVALID")
        switch_mode = oct(stat.S_IMODE(switch.stat().st_mode))
        if switch_mode != "0o600":
            raise PermissionError("KILL_SWITCH_MODE_MUST_BE_0600")
        identify_owner = owner_probe or (lambda path: pwd.getpwuid(path.stat().st_uid).pw_name)
        switch_owner = identify_owner(switch)
        if switch_owner != "atlasrunner":
            raise PermissionError("KILL_SWITCH_OWNER_MUST_BE_ATLASRUNNER")
        if state != "CLOSED":
            raise PermissionError("READONLY_VALIDATION_REQUIRES_ACQUISITION_DISABLED")
        kill_switch = {"path":str(switch),"state":state,"sha256":_file_sha(switch),
                       "mode":switch_mode,"owner":switch_owner,
                       "safe_for_live_calls":state == "OPEN"}
    after = _file_sha(ledger_path)
    if before != after:
        raise RuntimeError("PROTECTED_LEDGER_CHANGED_DURING_READONLY_AUDIT")
    result = {"schema_version":"ATLAS_REPORT_CARD_PROTECTED_READONLY_V1", "source_sha":source_sha,
        "ledger":{"path":str(ledger_path),"mode":mode,"sha256":before,"tip":tip},
        "backup_root":{"path":str(backup_root),"verified_backups":verified_backups},
        "mounts":{"primary":primary_mount,"backup":backup_mount,"isolated":True},
        "publication_reconciliation":reconciliation,
        "kill_switch_evidence":kill_switch,
        "canonical_plan":plan,"canonical_plan_sha256":plan["artifact_sha256"],
        "due_tickers":plan["due_tickers"],"target_sessions":plan["target_sessions"],
        "planned_calls":plan["provider_call_budget"],"provider_calls":0,"ledger_mutations":0,
        "dispatch_performed":False,"required_owner_token":"REPORT_CARD_PROTECTED_VALIDATE_ONCE"}
    result["package_sha256"] = digest(result)
    return result

__all__ = ["prepare_protected_validation"]
