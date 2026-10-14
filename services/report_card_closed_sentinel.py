"""Atomic creation and verification of the Report Card CLOSED sentinel."""
from __future__ import annotations

import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import stat
from typing import Any


SENTINEL_NAME = "ACQUISITION_KILL_SWITCH"
SENTINEL_CONTENT = b"CLOSED\n"
SENTINEL_MODE = 0o600


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_closed_sentinel(path: Path, *, owner: str = "atlasrunner",
                           group: str = "atlasrunner") -> dict[str, Any]:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or path.is_symlink():
        raise ValueError("CLOSED_SENTINEL_MUST_BE_REGULAR_FILE")
    value = path.read_bytes()
    if value != SENTINEL_CONTENT:
        raise ValueError("CLOSED_SENTINEL_CONTENT_INVALID")
    if stat.S_IMODE(details.st_mode) != SENTINEL_MODE:
        raise PermissionError("CLOSED_SENTINEL_MODE_MUST_BE_0600")
    if pwd.getpwuid(details.st_uid).pw_name != owner:
        raise PermissionError("CLOSED_SENTINEL_OWNER_INVALID")
    if grp.getgrgid(details.st_gid).gr_name != group:
        raise PermissionError("CLOSED_SENTINEL_GROUP_INVALID")
    return {
        "path": str(path),
        "state": "CLOSED",
        "sha256": _sha256(value),
        "mode": "0600",
        "owner": owner,
        "group": group,
        "device": details.st_dev,
        "inode": details.st_ino,
    }


def create_closed_sentinel(*, durable_root: Path, owner: str = "atlasrunner",
                           group: str = "atlasrunner") -> dict[str, Any]:
    """Create the sentinel without exposing a partial file or replacing any file."""
    supplied_root = Path(durable_root)
    if supplied_root.is_symlink():
        raise ValueError("DURABLE_ROOT_SYMLINK_FORBIDDEN")
    root = supplied_root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError("DURABLE_ROOT_DIRECTORY_REQUIRED")
    target = root / SENTINEL_NAME
    if target.exists() or target.is_symlink():
        evidence = verify_closed_sentinel(target, owner=owner, group=group)
        evidence.update(created=False, idempotent=True)
        return evidence

    identity = pwd.getpwnam(owner)
    group_identity = grp.getgrnam(group)
    temporary = root / f".{SENTINEL_NAME}.{os.getpid()}.{secrets.token_hex(8)}.pending"
    descriptor = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, SENTINEL_MODE)
        os.fchmod(descriptor, SENTINEL_MODE)
        os.fchown(descriptor, identity.pw_uid, group_identity.gr_gid)
        os.write(descriptor, SENTINEL_CONTENT)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        # link() is an atomic no-replace publication on the same filesystem.
        os.link(temporary, target, follow_symlinks=False)
        temporary.unlink()
        directory = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        evidence = verify_closed_sentinel(target, owner=owner, group=group)
        evidence.update(created=False, idempotent=True)
        return evidence
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    evidence = verify_closed_sentinel(target, owner=owner, group=group)
    evidence.update(created=True, idempotent=False)
    return evidence


def canonical_evidence(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = ["SENTINEL_CONTENT", "SENTINEL_MODE", "SENTINEL_NAME",
           "canonical_evidence", "create_closed_sentinel", "verify_closed_sentinel"]
