"""Fail-closed atomic sentinel and one-shot controls for Report Card G2."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
from typing import Iterator


BOUND_SOURCE_SHA = "2d0d8bd00b9168d2684845a7cc75b3a596d6a9c5"
BOUND_PLAN_SHA256 = "457aab35abd2c5e02f9d06dfeaffc2dd9ffa15e7083d601f2737b7a11b4829a3"
BOUND_PACKAGE_SHA256 = "7e52b221e7da843f68d52d5a71795d6f64c5db7951d041a4c582ef5e8e1fe83f"
BOUND_LEDGER_SHA256 = "1eb89d1d9e64e953480a6d151f10f3959f115ec25d75999dbe8c3313bf350325"
BOUND_BACKUP_SHA256 = "a16143fc69e19d621c46d48ac913a9443812edfd6bab838f577d08f145a376a5"
EXPECTED_OWNER = "atlasrunner"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_regular_protected_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError("G2_PROTECTED_FILE_MODE_INVALID")
    if pwd.getpwuid(info.st_uid).pw_name != EXPECTED_OWNER:
        raise PermissionError("G2_PROTECTED_FILE_OWNER_INVALID")


def verify_sentinel(path: Path, state: str) -> None:
    _verify_regular_protected_file(path)
    if path.read_bytes() != f"{state}\n".encode():
        raise PermissionError(f"G2_SENTINEL_NOT_{state}")


def atomic_sentinel(path: Path, state: str) -> None:
    if state not in {"OPEN", "CLOSED"}:
        raise ValueError("G2_SENTINEL_STATE_INVALID")
    path = path.absolute()
    if path.exists():
        _verify_regular_protected_file(path)
        owner_uid, owner_gid = path.stat().st_uid, path.stat().st_gid
    elif state == "CLOSED" and pwd.getpwuid(os.getuid()).pw_name == EXPECTED_OWNER:
        owner_uid, owner_gid = os.getuid(), os.getgid()
    else:
        raise PermissionError("G2_SENTINEL_REQUIRED")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pending")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, f"{state}\n".encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.chown(temporary, owner_uid, owner_gid)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        verify_sentinel(path, state)
    finally:
        temporary.unlink(missing_ok=True)


def claim_once(root: Path, execution_id: str) -> Path:
    if not execution_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in execution_id):
        raise ValueError("G2_EXECUTION_ID_INVALID")
    receipt = root / f".g2-acquisition-{BOUND_PLAN_SHA256}-{execution_id}.claim"
    descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, json.dumps({
            "execution_id": execution_id,
            "plan_sha256": BOUND_PLAN_SHA256,
            "source_sha": BOUND_SOURCE_SHA,
            "package_sha256": BOUND_PACKAGE_SHA256,
        }, sort_keys=True).encode() + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return receipt


@contextmanager
def protected_g2_window(*, sentinel: Path, ledger: Path, backup: Path,
                        execution_id: str) -> Iterator[Path]:
    """Open once and always close, while proving protected data invariance."""
    verify_sentinel(sentinel, "CLOSED")
    if sha256_file(ledger) != BOUND_LEDGER_SHA256:
        raise PermissionError("G2_LEDGER_IDENTITY_MISMATCH")
    if sha256_file(backup) != BOUND_BACKUP_SHA256:
        raise PermissionError("G2_BACKUP_IDENTITY_MISMATCH")
    receipt = claim_once(sentinel.parent, execution_id)
    ledger_before, backup_before = sha256_file(ledger), sha256_file(backup)
    opened = False
    try:
        atomic_sentinel(sentinel, "OPEN")
        opened = True
        yield receipt
    finally:
        # Cleanup is attempted even when opening or acquisition is interrupted.
        if opened or sentinel.exists():
            atomic_sentinel(sentinel, "CLOSED")
        verify_sentinel(sentinel, "CLOSED")
        if sha256_file(ledger) != ledger_before:
            raise RuntimeError("G2_LEDGER_CHANGED")
        if sha256_file(backup) != backup_before:
            raise RuntimeError("G2_BACKUP_CHANGED")
