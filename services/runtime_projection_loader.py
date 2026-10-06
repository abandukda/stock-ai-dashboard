"""Fail-closed loader for versioned customer runtime projections.

This module is deliberately isolated from Home presentation imports. Streamlit
may retain already-imported presentation modules across a Community Cloud
deployment; a versioned loader module prevents a new app revision from asking a
stale presentation module for a symbol that did not exist in the prior revision.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def load_exact_customer_inventory_with_status(
    path: Path, manifest: Mapping[str, Any],
) -> tuple[Any, bool, tuple[str, ...]]:
    """Load the projection only when its governed contract validates."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("runtime_projection_contract"):
            from services.runtime_projection_contract import validate_runtime_projection

            valid, failures = validate_runtime_projection(
                payload, manifest, artifact_name=path.name,
            )
        else:
            expected = dict(manifest.get("artifact_hashes") or {}).get(path.name)
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), default=str,
            ).encode()
            valid = bool(expected and hashlib.sha256(canonical).hexdigest() == expected)
            failures = () if valid else ("LEGACY_ARTIFACT_DIGEST_MISMATCH",)
        return (payload if valid else []), valid, failures
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return [], False, ("RUNTIME_PROJECTION_UNREADABLE",)


__all__ = ["load_exact_customer_inventory_with_status"]
