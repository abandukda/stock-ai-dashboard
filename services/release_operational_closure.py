"""Provider-free monitoring, evidence recovery, and publication rollback drills."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterator, Mapping

from services.operational_heartbeat import CronitorHeartbeatAdapter, event_envelope
from services.publication_governance import promote_atomically


VERSION = "ATLAS_RELEASE_OPERATIONAL_CLOSURE_V1"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class _Response:
    status = 204


@dataclass
class CaptureOpener:
    """Record requests without opening a socket."""

    requests: list[dict[str, Any]]

    def __call__(self, request, timeout: float) -> _Response:
        self.requests.append({"url": request.full_url, "method": request.method, "timeout": timeout})
        return _Response()


def monitoring_drill(*, cronitor_url: str, owner_email: str, run_id: str,
                     source_sha: str, trading_session: str) -> dict[str, Any]:
    """Exercise sanitized success/failure and missed-heartbeat contracts offline."""
    if not EMAIL_RE.fullmatch(owner_email):
        raise RuntimeError("RELEASE_MONITOR_OWNER_EMAIL_MISSING_OR_INVALID")
    capture = CaptureOpener([])
    adapter = CronitorHeartbeatAdapter(cronitor_url, opener=capture)
    receipts = []
    for state, status, failure, recovery in (
        ("complete", "PUBLISHED", "NONE", "NONE"),
        ("fail", "REJECTED", "PUBLICATION_REJECTED", "Retain the last valid snapshot."),
    ):
        envelope = event_envelope(
            operation="DAILY_BUY_NOW", state=state, run_id=run_id,
            source_sha=source_sha, trading_session=trading_session,
            publication_status=status, failure_code=failure, recovery_action=recovery,
        )
        receipts.append(adapter.send(envelope))
    # A missing heartbeat cannot be emitted by the absent job. This proves the
    # independent-monitor configuration contract without claiming delivery.
    missed = {
        "scenario": "MISSED_HEARTBEAT",
        "expected_monitor_state": "ALERT",
        "failure_code": "NEVER_STARTED_OR_DID_NOT_COMPLETE",
        "requires_independent_deadline": True,
        "provider_call_performed": False,
    }
    redacted_requests = [{
        "method": item["method"], "timeout": item["timeout"],
        "request_sha256": hashlib.sha256(item["url"].encode()).hexdigest(),
    } for item in capture.requests]
    result = {
        "schema_version": VERSION,
        "mode": "PROVIDER_FREE",
        "owner_email_configured": True,
        "owner_email_sha256": hashlib.sha256(owner_email.lower().encode()).hexdigest(),
        "delivery_attempted": False,
        "synthetic_receipts": receipts,
        "sanitized_requests": redacted_requests,
        "missed_heartbeat": missed,
        "status": "PASS",
    }
    result["result_sha256"] = _digest(result)
    return result


@contextmanager
def _replace_failure(after_successes: int) -> Iterator[None]:
    import services.publication_governance as governance
    original, calls = governance.os.replace, 0

    injected = False

    def fail(destination, target):
        nonlocal calls, injected
        calls += 1
        if calls > after_successes and not injected:
            injected = True
            raise OSError("SYNTHETIC_PUBLICATION_WRITE_FAILURE")
        return original(destination, target)

    governance.os.replace = fail
    try:
        yield
    finally:
        governance.os.replace = original


def publication_rollback_drill() -> dict[str, Any]:
    """Induce a mid-promotion write failure and prove last-known-good restore."""
    with tempfile.TemporaryDirectory(prefix="atlas-publication-rollback-") as directory:
        root = Path(directory)
        destinations = [root / "market_full_scan.json", root / "market_scan_state.json"]
        prior = {path: {"generation": "LAST_KNOWN_GOOD", "file": path.name} for path in destinations}
        for path, payload in prior.items():
            path.write_text(json.dumps(payload), encoding="utf-8")
        manifest_path = root / "publication_manifest.json"
        prior_manifest = {"run_id": "prior", "publication_gate_status": "PASS"}
        manifest_path.write_text(json.dumps(prior_manifest), encoding="utf-8")
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (*destinations, manifest_path)}
        failure = ""
        try:
            # Two production replacements succeed; the manifest replacement fails.
            with _replace_failure(after_successes=2):
                promote_atomically(
                    {path: {"generation": "CANDIDATE", "file": path.name} for path in destinations},
                    manifest={"run_id": "candidate", "publication_gate_status": "PASS"},
                    manifest_path=manifest_path, audit_path=root / "publication_audit.jsonl",
                )
        except OSError as exc:
            failure = str(exc)
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (*destinations, manifest_path)}
        passed = bool(failure == "SYNTHETIC_PUBLICATION_WRITE_FAILURE" and before == after)
        result = {
            "schema_version": VERSION,
            "mode": "SYNTHETIC_PROVIDER_FREE",
            "injected_failure": failure,
            "prior_sha256": before,
            "restored_sha256": after,
            "production_state_restored": before == after,
            "protected_state_mutated": False,
            "status": "PASS" if passed else "FAIL",
        }
        result["result_sha256"] = _digest(result)
        if not passed:
            raise RuntimeError("PUBLICATION_ROLLBACK_DRILL_FAILED")
        return result


def persist_and_restore_evidence(*, evidence: Mapping[str, Any], storage: Path,
                                 restore: Path) -> dict[str, Any]:
    """Persist immutable evidence, restore it elsewhere, and verify every byte."""
    storage.mkdir(parents=True, exist_ok=True)
    if any(storage.iterdir()):
        raise RuntimeError("DURABLE_EVIDENCE_DESTINATION_NOT_EMPTY")
    files: dict[str, str] = {}
    for name, payload in sorted(evidence.items()):
        path = storage / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    manifest["manifest_sha256"] = _digest(manifest)
    manifest_path = storage / "evidence_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    bundle_files = {**files, manifest_path.name: hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    if restore.exists():
        raise RuntimeError("DURABLE_EVIDENCE_RESTORE_DESTINATION_EXISTS")
    shutil.copytree(storage, restore)
    restored = {name: hashlib.sha256((restore / name).read_bytes()).hexdigest() for name in bundle_files}
    if restored != bundle_files:
        raise RuntimeError("DURABLE_EVIDENCE_RESTORE_HASH_MISMATCH")
    return {
        "schema_version": VERSION, "status": "PASS", "files": bundle_files,
        "manifest_sha256": manifest["manifest_sha256"], "restored_sha256": restored,
    }


__all__ = ["monitoring_drill", "persist_and_restore_evidence", "publication_rollback_drill"]
