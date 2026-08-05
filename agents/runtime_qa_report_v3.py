"""Safe loader for Atlas Runtime QA v3 artifacts.

This module is intentionally dependency-free because it is imported by the
Streamlit application at startup. Importing it must never crash the dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_V3_REPORT_PATH = Path("audit_results/atlas_runtime_qa_v3.json")
LEGACY_REPORT_PATHS = (
    Path("audit_results/atlas_runtime_qa.json"),
    Path("audit_results/atlas_browser_audit.json"),
)


def _load_json_object(path: Path) -> dict[str, Any] | None:
    """Load a JSON object safely.

    Returns None when the file is missing, malformed, unreadable, or does not
    contain a JSON object. This function never raises during app startup.
    """
    try:
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def load_latest_runtime_qa_v3(
    path: str | Path = DEFAULT_V3_REPORT_PATH,
) -> dict[str, Any] | None:
    """Return the latest Runtime QA v3 report, or None when unavailable.

    The explicit path is checked first. When the default path is used, legacy
    filenames are checked as read-only fallbacks so Developer Center remains
    usable during upgrades.
    """
    requested = Path(path)
    report = _load_json_object(requested)
    if report is not None:
        return report

    if requested == DEFAULT_V3_REPORT_PATH:
        for fallback in LEGACY_REPORT_PATHS:
            report = _load_json_object(fallback)
            if report is not None:
                return report
    return None


def runtime_qa_v3_available(
    path: str | Path = DEFAULT_V3_REPORT_PATH,
) -> bool:
    """Return True when a readable QA report is available."""
    return load_latest_runtime_qa_v3(path) is not None


def summarize_runtime_qa_v3(
    report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Create a stable summary for Developer Center cards."""
    value = dict(report or {})
    counts = value.get("severity_counts")
    if not isinstance(counts, Mapping):
        counts = {}

    return {
        "version": value.get("version", "No report"),
        "status": value.get("status", "NOT_RUN"),
        "audit_valid": bool(value.get("audit_valid", False)),
        "health_score": int(value.get("health_score") or 0),
        "pages_inspected": int(value.get("pages_inspected") or 0),
        "duration_seconds": float(value.get("duration_seconds") or 0.0),
        "critical": int(counts.get("CRITICAL") or 0),
        "high": int(counts.get("HIGH") or 0),
        "medium": int(counts.get("MEDIUM") or 0),
        "low": int(counts.get("LOW") or 0),
    }


# Backward-compatible alias for older imports.
load_latest_runtime_qa = load_latest_runtime_qa_v3


__all__ = [
    "DEFAULT_V3_REPORT_PATH",
    "load_latest_runtime_qa_v3",
    "load_latest_runtime_qa",
    "runtime_qa_v3_available",
    "summarize_runtime_qa_v3",
]
