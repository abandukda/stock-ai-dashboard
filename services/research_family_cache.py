"""Independent evidence-family cache contracts for RESEARCH_CONTEXT_V1."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Final, Mapping


RESEARCH_FAMILY_CACHE_VERSION: Final = "RESEARCH_FAMILY_CACHE_V1"

FAMILY_TTLS_SECONDS: Final[dict[str, int | None]] = {
    "profile": 7 * 86400,
    "peers": 7 * 86400,
    "financial_statements": 8 * 3600,
    "ratios_key_metrics": 8 * 3600,
    "growth_segments": 8 * 3600,
    "earnings_history": 8 * 3600,
    "analyst_estimates": 4 * 3600,
    "analyst_consensus_targets": 4 * 3600,
    "analyst_actions": 4 * 3600,
    "institutional_ownership": 12 * 3600,
    "holders_13f": 24 * 3600,
    "company_news": 3600,
    "press_releases": 3600,
    "sec_filings": 8 * 3600,
    "transcript_index": 24 * 3600,
    "transcript_intelligence": None,
    "etf_research": 24 * 3600,
}

DEFAULT_CACHE_ROOT: Final = Path(".atlas_research_cache/research_families_v1")


def family_ttl_seconds(family: str) -> int | None:
    if family not in FAMILY_TTLS_SECONDS:
        raise KeyError(f"unknown cache family: {family}")
    return FAMILY_TTLS_SECONDS[family]


def _safe(value: str) -> str:
    return "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {"-", "_"})


def cache_path(
    ticker: str,
    family: str,
    root: str | Path = DEFAULT_CACHE_ROOT,
    *,
    period_key: str | None = None,
) -> Path:
    if family == "transcript_intelligence":
        period = _safe(period_key or "")
        if not period:
            raise ValueError("transcript cache requires a symbol/year/quarter period_key")
        suffix = f"{period}.immutable"
    else:
        suffix = "latest"
    return Path(root) / family / f"{_safe(ticker)}.{suffix}.json"


def save_family_envelope(
    ticker: str,
    family: str,
    envelope: Mapping[str, Any],
    *,
    root: str | Path = DEFAULT_CACHE_ROOT,
    period_key: str | None = None,
) -> Path:
    path = cache_path(ticker, family, root, period_key=period_key)
    if family == "transcript_intelligence" and path.exists():
        raise FileExistsError("transcript content cache is immutable")
    payload = dict(envelope)
    payload["cache_version"] = RESEARCH_FAMILY_CACHE_VERSION
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)
    return path


def load_family_envelope(
    ticker: str,
    family: str,
    *,
    root: str | Path = DEFAULT_CACHE_ROOT,
    now_epoch: float | None = None,
    allow_stale: bool = True,
    period_key: str | None = None,
) -> dict[str, Any] | None:
    path = cache_path(ticker, family, root, period_key=period_key)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if payload.get("cache_version") != RESEARCH_FAMILY_CACHE_VERSION:
        return None
    fetched_at = payload.get("fetched_at")
    try:
        from datetime import datetime
        fetched_epoch = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None
    age = max(0.0, (time.time() if now_epoch is None else now_epoch) - fetched_epoch)
    ttl = family_ttl_seconds(family)
    stale = ttl is not None and age > ttl
    if stale and not allow_stale:
        return None
    payload["age_seconds"] = age
    payload["cache_status"] = "STALE_FALLBACK" if stale else "FRESH_CACHE"
    # fetched_at is deliberately preserved; cache access is not provider fetch.
    return payload


__all__ = [
    "DEFAULT_CACHE_ROOT", "FAMILY_TTLS_SECONDS", "RESEARCH_FAMILY_CACHE_VERSION",
    "cache_path", "family_ttl_seconds", "load_family_envelope", "save_family_envelope",
]
