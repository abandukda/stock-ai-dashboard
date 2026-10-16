"""Durable consume-once claims for protected incremental acquisitions."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLAIM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{15,127}$")


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def scope_payload(*, claim_id: str, source_sha: str, plan_sha256: str,
                  session: str, membership_count: int = 1298,
                  max_requests: int = 2746, retries: int = 0) -> dict[str, Any]:
    value = {
        "claim_id": claim_id, "source_sha": source_sha,
        "plan_sha256": plan_sha256, "finalized_session": session,
        "membership_count": membership_count,
        "max_requests": max_requests, "automatic_retries": retries,
    }
    value["claim_scope_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def authorization_token(scope: dict[str, Any]) -> str:
    return f"AUTHORIZE_ATLAS_INCREMENTAL_CLAIM:{scope['claim_id']}:{scope['claim_scope_sha256']}"


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def consume_claim(*, claims_root: Path, scope: dict[str, Any], token: str) -> Path:
    claim_id = str(scope.get("claim_id", ""))
    if not CLAIM_ID.fullmatch(claim_id):
        raise PermissionError("INCREMENTAL_CLAIM_ID_INVALID")
    expected = scope_payload(
        claim_id=claim_id, source_sha=str(scope.get("source_sha", "")),
        plan_sha256=str(scope.get("plan_sha256", "")),
        session=str(scope.get("finalized_session", "")),
        membership_count=int(scope.get("membership_count", 0)),
        max_requests=int(scope.get("max_requests", 0)),
        retries=int(scope.get("automatic_retries", -1)),
    )
    if expected != scope:
        raise PermissionError("INCREMENTAL_CLAIM_SCOPE_INVALID")
    if token != authorization_token(scope):
        raise PermissionError("INCREMENTAL_CLAIM_AUTHORIZATION_INVALID")
    if scope["membership_count"] != 1298 or scope["max_requests"] != 2746 or scope["automatic_retries"] != 0:
        raise PermissionError("INCREMENTAL_CLAIM_BOUNDS_INVALID")
    claims_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = claims_root / f"{claim_id}.json"
    record = {**scope, "state": "CONSUMED", "consumed_at": datetime.now(timezone.utc).isoformat()}
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise PermissionError("INCREMENTAL_CLAIM_ALREADY_CONSUMED") from exc
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(_canonical(record))
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_dir(claims_root)
    except BaseException:
        # Never remove a claim after O_EXCL succeeds. Ambiguous writes fail closed.
        raise
    return path


def finalize_claim(path: Path, *, outcome: str) -> None:
    current = json.loads(path.read_text())
    if current.get("state") != "CONSUMED":
        raise PermissionError("INCREMENTAL_CLAIM_NOT_CONSUMED")
    updated = {**current, "outcome": outcome,
               "finalized_at": datetime.now(timezone.utc).isoformat()}
    temp = path.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb", closefd=True) as handle:
        handle.write(_canonical(updated)); handle.flush(); os.fsync(handle.fileno())
    os.replace(temp, path)
    _fsync_dir(path.parent)
