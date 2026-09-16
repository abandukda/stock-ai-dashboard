"""Optional post-shell FMP intelligence acquisition for Phase 1.

This module is intentionally absent from the synchronous explicit-Research
acquisition graph. Ordinary callers only read its independent caches.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Final, Mapping

from engines.fmp_normalization import (
    latest_valid_transcript_period,
    normalize_insider_transaction,
    normalize_price_target_action,
    normalize_transcript_content,
    normalize_transcript_period,
)
from engines.research_context import evidence_envelope, stable_evidence_id
from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE, NOT_APPLICABLE
from engines.transcript_intelligence import TRANSCRIPT_SYNTHESIS_VERSION, derive_transcript_intelligence
from services.analyst_estimate_snapshot_store import revision_summary
from services.fmp_stable_client import FMPStableClient
from services.research_family_cache import DEFAULT_CACHE_ROOT, load_family_envelope, save_family_envelope


PHASE1_INTELLIGENCE_VERSION: Final = "OPTIONAL_CONTEXT_RETIRED_V2"
POST_SHELL_REQUEST_CEILING: Final = 2
MAX_TARGET_ACTIONS: Final = 25
MAX_INSIDER_TRANSACTIONS: Final = 50


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        return [payload] if payload else []
    return []


def _unavailable(ticker: str, family: str, limitation: str, *, status: str = DATA_UNAVAILABLE) -> dict[str, Any]:
    return evidence_envelope(
        ticker=ticker, family=family, semantic_status=status,
        cache_status="NOT_APPLICABLE" if status == NOT_APPLICABLE else "TEMPORARILY_UNAVAILABLE",
        limitations=(limitation,),
    )


def _load_bounded(ticker: str, family: str, *, cache_root: str | Path, max_age: int | None = None) -> dict[str, Any] | None:
    if family == "transcript_intelligence":
        try:
            value = json.loads((Path(cache_root) / family / f"{ticker}.latest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            value = None
    else:
        value = load_family_envelope(ticker, family, root=cache_root, allow_stale=True)
    if value and max_age is not None and float(value.get("age_seconds") or 0) > max_age:
        return None
    return value


def load_cached_phase1_families(
    ticker: str, *, security_type: str = "EQUITY", cache_root: str | Path = DEFAULT_CACHE_ROOT,
) -> dict[str, dict[str, Any]]:
    symbol = str(ticker or "").strip().upper()
    families = (
        "transcript_index", "transcript_intelligence",
        "analyst_price_target_actions", "insider_transactions",
        "institutional_ownership", "analyst_estimate_snapshots",
    )
    limitation = "This optional evidence family is unavailable because its former provider has been retired."
    if str(security_type).upper() in {"ETF", "FUND", "MUTUALFUND"}:
        result = {family: _unavailable(symbol, family, "Corporate evidence does not apply to ETFs.", status=NOT_APPLICABLE) for family in families}
    else:
        result = {family: _unavailable(symbol, family, limitation) for family in families}
    return result


def refresh_post_shell_evidence(
    ticker: str, *, api_key: str, security_type: str = "EQUITY",
    cache_root: str | Path = DEFAULT_CACHE_ROOT, client: FMPStableClient | None = None,
) -> dict[str, Any]:
    """Return explicit unavailability; the former context provider is retired."""
    symbol = str(ticker or "").strip().upper()
    return {"provider_calls": 0, "families": load_cached_phase1_families(symbol, security_type=security_type, cache_root=cache_root)}


def acquire_latest_transcript_intelligence(
    ticker: str, *, api_key: str, cache_root: str | Path = DEFAULT_CACHE_ROOT,
    client: FMPStableClient | None = None,
) -> dict[str, Any]:
    """Return unavailable until a separately governed transcript source exists."""
    symbol = str(ticker or "").upper()
    return {"provider_calls": 0, "family": _unavailable(symbol, "transcript_intelligence", "Transcript evidence is unavailable for this snapshot."), "operation_metadata": _transcript_operation_metadata(symbol, None, None, 0, "UNAVAILABLE", None)}


def _transcript_operation_metadata(
    ticker: str, year: int | None, quarter: int | None, provider_calls: int,
    cache_status: str, evidence_id: str | None,
) -> dict[str, Any]:
    """Sanitized operation evidence; never includes transcript/provider payloads."""
    return {
        "ticker": str(ticker or "").strip().upper(),
        "selected_year": year,
        "selected_quarter": quarter,
        "transcript_evidence_id": evidence_id,
        "cache_status": cache_status,
        "provider_call_count": provider_calls,
        "synthesis_version": TRANSCRIPT_SYNTHESIS_VERSION,
    }


def acquire_transcript_index(
    ticker: str, *, api_key: str, cache_root: str | Path = DEFAULT_CACHE_ROOT,
    client: FMPStableClient | None = None,
) -> dict[str, Any]:
    """Return unavailable; transcript acquisition is retired."""
    symbol = str(ticker or "").strip().upper()
    return {"provider_calls": 0, "family": _unavailable(symbol, "transcript_index", "Transcript evidence is unavailable for this snapshot.")}


def acquire_transcript_intelligence(
    ticker: str, *, year: int, quarter: int, api_key: str,
    cache_root: str | Path = DEFAULT_CACHE_ROOT, client: FMPStableClient | None = None,
    _index_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return unavailable; transcript acquisition is retired."""
    symbol = str(ticker or "").strip().upper()
    if quarter not in {1, 2, 3, 4}:
        raise ValueError("quarter must be one of 1, 2, 3, 4")
    family = _unavailable(symbol, "transcript_intelligence", "Transcript commentary unavailable for this quarter.")
    metadata = _transcript_operation_metadata(symbol, year, quarter, 0, "UNAVAILABLE", None)
    return {"provider_calls": 0, "family": family, "period": f"{year}-Q{quarter}", "operation_metadata": metadata}


__all__ = [
    "MAX_INSIDER_TRANSACTIONS", "MAX_TARGET_ACTIONS", "PHASE1_INTELLIGENCE_VERSION",
    "POST_SHELL_REQUEST_CEILING", "acquire_latest_transcript_intelligence",
    "acquire_transcript_index", "acquire_transcript_intelligence",
    "load_cached_phase1_families", "refresh_post_shell_evidence",
]
