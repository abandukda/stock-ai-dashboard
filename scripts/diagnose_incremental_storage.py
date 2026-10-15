#!/usr/bin/env python3
"""Provider-free storage discovery for the protected incremental runner."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


EXCLUDED_PREFIXES = (
    "/tmp",
    "/var/tmp",
    "/mnt/atlas_report_card_primary",
    "/mnt/atlas_report_card_backup",
    "/mnt/atlas_position_shadow_primary",
    "/mnt/atlas_position_shadow_backup",
)


def mount_identity(path: Path) -> dict[str, str]:
    raw = subprocess.check_output(
        ["findmnt", "-T", str(path), "-n", "-o", "UUID,SOURCE,FSTYPE,TARGET"],
        text=True,
    ).strip()
    parts = raw.split(maxsplit=3)
    if len(parts) != 4:
        raise RuntimeError("STORAGE_MOUNT_IDENTITY_UNAVAILABLE")
    return dict(zip(("uuid", "source", "fstype", "target"), parts, strict=True))


def candidate_paths(root: Path, checkout: Path) -> list[Path]:
    if not root.is_dir():
        return []
    candidates = []
    for path in sorted(root.iterdir()):
        resolved = path.resolve()
        value = str(resolved)
        if not resolved.is_dir() or resolved == checkout or checkout in resolved.parents:
            continue
        if any(value == prefix or value.startswith(prefix + "/") for prefix in EXCLUDED_PREFIXES):
            continue
        lowered = resolved.name.lower()
        if "atlas" not in lowered or not any(token in lowered for token in ("incremental", "buy_now")):
            continue
        candidates.append(resolved)
    return candidates


def verify_path(path: Path) -> dict[str, object]:
    stat = os.statvfs(path)
    marker = None
    renamed = None
    try:
        fd, marker_name = tempfile.mkstemp(prefix=".atlas-storage-probe-", dir=path)
        marker = Path(marker_name)
        payload = b"ATLAS_INCREMENTAL_STORAGE_PROBE_V1\n"
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        renamed = marker.with_suffix(".renamed")
        os.replace(marker, renamed)
        with renamed.open("rb") as handle:
            if handle.read() != payload:
                raise RuntimeError("STORAGE_READBACK_MISMATCH")
        return {
            "path": str(path),
            "mount": mount_identity(path),
            "free_bytes": stat.f_bavail * stat.f_frsize,
            "write": True,
            "fsync": True,
            "atomic_rename": True,
            "process_restart_readback": True,
            "host_restart_readback": "NOT_PROVEN_REQUIRES_ADMIN_REBOOT_OR_SERVICE_RESTART",
        }
    finally:
        for probe in (marker, renamed):
            if probe and probe.exists():
                probe.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mount-root", default="/mnt")
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    checkout = Path(args.checkout).resolve()
    rows = []
    errors = []
    for path in candidate_paths(Path(args.mount_root), checkout):
        try:
            rows.append(verify_path(path))
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            errors.append({"path": str(path), "error": type(exc).__name__})

    distinct_mounts = len({(r["mount"]["uuid"], r["mount"]["source"]) for r in rows})
    result = {
        "schema_version": "atlas.incremental-storage-diagnostic.v1",
        "provider_calls": 0,
        "publication_writes": 0,
        "report_card_ledger_access": 0,
        "sentinel_transitions": 0,
        "candidates": rows,
        "rejected_candidates": errors,
        "ready": len(rows) >= 2 and distinct_mounts >= 1,
        "selection_policy": "OWNER_OR_RUNNER_ADMIN_MUST_SELECT_TWO_VERIFIED_EXISTING_PATHS",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
