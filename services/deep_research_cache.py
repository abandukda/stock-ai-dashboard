"""Small persistent cache for normalized post-ranking research evidence.

The cache contains only the same sanitized evidence dictionaries that Atlas
would persist in a research row. It never stores credentials, request URLs, or
raw provider responses.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


CACHE_SCHEMA_VERSION = "ATLAS_DEEP_RESEARCH_CACHE_V1"
CACHE_ROOT = Path(os.getenv("ATLAS_DEEP_RESEARCH_CACHE_DIR", ".atlas_research_cache/deep_v1"))


def _safe_token(value: str) -> str:
    return "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {"-", "_"})


def _path(symbol: str, family: str) -> Path:
    return CACHE_ROOT / f"{_safe_token(symbol)}__{_safe_token(family)}.json"


def _read(symbol: str, family: str) -> dict[str, Any] | None:
    path = _path(symbol, family)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(value, dict) or value.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None
    if value.get("symbol") != _safe_token(symbol) or value.get("family") != _safe_token(family):
        return None
    return value if isinstance(value.get("payload"), dict) else None


def _write(
    symbol: str,
    family: str,
    payload: dict[str, Any],
    fetched_epoch: float,
    *,
    source_version: str | None = None,
) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    path = _path(symbol, family)
    value = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "symbol": _safe_token(symbol),
        "family": _safe_token(family),
        "fetched_epoch": fetched_epoch,
        "fetched_at": datetime.fromtimestamp(fetched_epoch, tz=timezone.utc).isoformat(),
        "source_version": source_version,
        "payload": payload,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, default=str), encoding="utf-8")
    temporary.replace(path)


def cached_evidence(
    symbol: str,
    family: str,
    ttl_seconds: int,
    fetcher: Callable[[], dict[str, Any]],
    *,
    now_epoch: float | None = None,
    source_version: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return normalized evidence and explicit freshness metadata.

    An expired value is used only as a clearly marked stale fallback when the
    provider fetch fails. A cache read never changes the original fetched time.
    """
    now = float(time.time() if now_epoch is None else now_epoch)
    cached = _read(symbol, family)
    if cached and source_version is not None and cached.get("source_version") != source_version:
        cached = None
    cached_epoch = float((cached or {}).get("fetched_epoch") or 0)
    age = max(0.0, now - cached_epoch) if cached_epoch else None
    if cached and age is not None and age <= max(0, int(ttl_seconds)):
        return dict(cached["payload"]), {
            "status": "FRESH_CACHE",
            "fetched_at": cached.get("fetched_at"),
            "age_seconds": round(age, 3),
            "ttl_seconds": int(ttl_seconds),
        }

    try:
        fetched = fetcher()
    except Exception:
        fetched = {}
    if isinstance(fetched, dict) and fetched:
        _write(symbol, family, dict(fetched), now, source_version=source_version)
        return dict(fetched), {
            "status": "FETCHED",
            "fetched_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "age_seconds": 0.0,
            "ttl_seconds": int(ttl_seconds),
        }
    if cached:
        return dict(cached["payload"]), {
            "status": "STALE_FALLBACK",
            "fetched_at": cached.get("fetched_at"),
            "age_seconds": round(age or 0.0, 3),
            "ttl_seconds": int(ttl_seconds),
        }
    return {}, {
        "status": "TEMPORARILY_UNAVAILABLE",
        "fetched_at": None,
        "age_seconds": None,
        "ttl_seconds": int(ttl_seconds),
    }


__all__ = ["CACHE_SCHEMA_VERSION", "CACHE_ROOT", "cached_evidence"]
