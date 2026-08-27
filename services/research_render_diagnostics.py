"""Sanitized, diagnostic-only checkpoints for explicit Research rendering."""

from __future__ import annotations

from contextvars import ContextVar
import hashlib
import os
from pathlib import Path
import subprocess
from types import TracebackType
from typing import Any


_STAGE: ContextVar[str] = ContextVar("atlas_research_render_stage", default="UNINITIALIZED")
_ATTEMPT: ContextVar[dict[str, str]] = ContextVar(
    "atlas_research_render_attempt", default={}
)


def deployment_source_sha(root: str | Path = ".") -> str:
    """Return a sanitized deployment revision without exposing environment data."""
    for name in ("ATLAS_SOURCE_SHA", "GITHUB_SHA", "COMMIT_SHA", "RENDER_GIT_COMMIT"):
        value = str(os.getenv(name) or "").strip().lower()
        if len(value) == 40 and all(character in "0123456789abcdef" for character in value):
            return value
    try:
        value = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(root), check=True,
            capture_output=True, text=True, timeout=2,
        ).stdout.strip().lower()
    except Exception:
        return "UNKNOWN"
    return value if len(value) == 40 and all(character in "0123456789abcdef" for character in value) else "UNKNOWN"


def begin_attempt(*, ticker: str, attempt_id: str, source_sha: str = "") -> dict[str, str]:
    """Create the safe diagnostic envelope before imports or acquisition begin."""
    envelope = {
        "ticker": str(ticker or "").upper()[:16],
        "attempt_id": str(attempt_id or "")[:80],
        "source_sha": str(source_sha or deployment_source_sha())[:40],
        "stage": "RESEARCH_ROUTE_INITIALIZING",
    }
    _ATTEMPT.set(envelope)
    checkpoint(envelope["stage"])
    return dict(envelope)


def checkpoint(stage: str) -> None:
    """Record a bounded static stage label; never evidence or provider data."""
    _STAGE.set(str(stage or "UNKNOWN")[:120])


def current_stage() -> str:
    return _STAGE.get()


def current_attempt() -> dict[str, str]:
    return dict(_ATTEMPT.get())


def _deepest_atlas_frame(traceback: TracebackType | None, root: Path) -> tuple[str, str, int]:
    selected = ("UNKNOWN", "UNKNOWN", 0)
    root = root.resolve()
    while traceback is not None:
        frame = traceback.tb_frame
        filename = Path(frame.f_code.co_filename).resolve()
        try:
            relative = filename.relative_to(root).as_posix()
        except ValueError:
            traceback = traceback.tb_next
            continue
        selected = (relative, frame.f_code.co_name, int(traceback.tb_lineno))
        traceback = traceback.tb_next
    return selected


def sanitized_exception_location(
    exc: BaseException,
    *,
    ticker: str,
    root: str | Path = ".",
) -> dict[str, Any]:
    """Return source identity only—never messages, arguments, locals, or traces."""
    filename, function, line = _deepest_atlas_frame(exc.__traceback__, Path(root))
    category = type(exc).__name__
    identity = f"{category}|{filename}|{function}|{line}"
    return {
        "category": category,
        "filename": filename,
        "function": function,
        "line": line,
        "fingerprint": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        "stage": current_stage(),
        "ticker": str(ticker or current_attempt().get("ticker") or "").upper(),
    }


def sanitized_failure_envelope(
    exc: BaseException, *, ticker: str, root: str | Path = ".",
) -> dict[str, Any]:
    """Combine safe source identity with the pre-import attempt envelope."""
    location = sanitized_exception_location(exc, ticker=ticker, root=root)
    attempt = current_attempt()
    return {
        **location,
        "attempt_id": attempt.get("attempt_id") or "",
        "source_sha": attempt.get("source_sha") or deployment_source_sha(root),
    }


__all__ = [
    "begin_attempt", "checkpoint", "current_attempt", "current_stage",
    "deployment_source_sha", "sanitized_exception_location", "sanitized_failure_envelope",
]
