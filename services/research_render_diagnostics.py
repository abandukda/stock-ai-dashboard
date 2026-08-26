"""Sanitized, diagnostic-only checkpoints for explicit Research rendering."""

from __future__ import annotations

from contextvars import ContextVar
import hashlib
from pathlib import Path
from types import TracebackType
from typing import Any


_STAGE: ContextVar[str] = ContextVar("atlas_research_render_stage", default="UNINITIALIZED")


def checkpoint(stage: str) -> None:
    """Record a bounded static stage label; never evidence or provider data."""
    _STAGE.set(str(stage or "UNKNOWN")[:120])


def current_stage() -> str:
    return _STAGE.get()


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
        "ticker": str(ticker or "").upper(),
    }


__all__ = ["checkpoint", "current_stage", "sanitized_exception_location"]
