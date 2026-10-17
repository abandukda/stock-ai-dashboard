"""Fail-before-claim preflight for protected BUY NOW operations."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from typing import Any, Sequence


def run_preflight(*, source_sha: str, checked_out_sha: str, raw_root: Path,
                  checkpoint_root: Path, required_labels: Sequence[str],
                  actual_labels: Sequence[str], endpoint_allowlist: Sequence[str],
                  request_ceiling: int, concurrency: int, initial_rpm: int,
                  automatic_retries: int, timeout_minutes: int,
                  require_credential: bool, credential_present: bool,
                  minimum_free_bytes: int = 1_000_000_000,
                  minimum_available_memory_bytes: int = 2_000_000_000,
                  reject_temporary_roots: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    if source_sha != checked_out_sha or len(source_sha) != 40:
        errors.append("SOURCE_IDENTITY_INVALID")
    if sys.version_info < (3, 11):
        errors.append("PYTHON_VERSION_UNSUPPORTED")
    if not set(required_labels).issubset(set(actual_labels)):
        errors.append("RUNNER_LABELS_MISSING")
    roots = [raw_root.resolve(), checkpoint_root.resolve()]
    if roots[0] == roots[1] or (reject_temporary_roots and
            any(str(path).startswith(("/tmp/", "/private/tmp/")) for path in roots)):
        errors.append("DURABLE_ROOTS_INVALID")
    for path in roots:
        if not path.exists() or not path.is_dir() or not os.access(path, os.W_OK):
            errors.append(f"STORAGE_NOT_WRITABLE:{path.name}")
        elif shutil.disk_usage(path).free < minimum_free_bytes:
            errors.append(f"STORAGE_CAPACITY_LOW:{path.name}")
    if require_credential and not credential_present:
        errors.append("PROVIDER_CREDENTIAL_MISSING")
    if tuple(endpoint_allowlist) != ("/stock/candle", "/stock/split", "/stock/dividend"):
        errors.append("ENDPOINT_ALLOWLIST_INVALID")
    if request_ceiling < 1 or concurrency != 1 or initial_rpm != 60 or automatic_retries != 0:
        errors.append("REQUEST_POLICY_INVALID")
    theoretical_minutes = request_ceiling / initial_rpm
    if timeout_minutes <= theoretical_minutes:
        errors.append("JOB_TIMEOUT_INSUFFICIENT")
    available_memory = None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        values = {line.split(":", 1)[0]: int(line.split()[1]) * 1024
                  for line in meminfo.read_text().splitlines() if ":" in line}
        available_memory = values.get("MemAvailable")
        if available_memory is not None and available_memory < minimum_available_memory_bytes:
            errors.append("MEMORY_HEADROOM_LOW")
    if errors:
        raise RuntimeError("BUY_NOW_PREFLIGHT_FAILED:" + ",".join(errors))
    return {
        "status": "PASS_BEFORE_CLAIM", "source_sha": source_sha,
        "request_ceiling": request_ceiling, "concurrency": concurrency,
        "initial_rpm": initial_rpm, "automatic_retries": automatic_retries,
        "theoretical_pacing_minutes": round(theoretical_minutes, 3),
        "credential_required": require_credential,
        "credential_present": bool(credential_present) if require_credential else None,
        "raw_root": str(roots[0]), "checkpoint_root": str(roots[1]),
        "available_memory_bytes": available_memory,
        "claim_consumed": False,
    }


__all__ = ["run_preflight"]
