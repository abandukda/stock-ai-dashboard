"""Provider-free Finnhub candle admission into the existing Research read model.

Input is retained source evidence, never a URL or credential. This producer
returns a reviewable bundle; it performs no acquisition, disk writes,
certification, deployment, or recommendation/publication promotion.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.report_card_exchange_calendar import build_xnys_calendar
from services.research_market_read_model import SCHEMA, seal_research_market_bundle


def build_history_bundle(
    response: Mapping[str, Any], *, ticker: str, source_sha: str, bundle_id: str,
    captured_at: datetime, checked_at: datetime, raw_evidence_id: str,
    adjustment_basis: str, adjustment_evidence_id: str,
) -> dict[str, Any]:
    """Admit complete, contiguous finalized sessions with explicit adjustment proof.

    The adjustment declaration must come from a separately verified retained
    source; this function never infers adjusted prices from numeric candles.
    """
    if (not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", ticker)
            or not re.fullmatch(r"[a-f0-9]{40}", source_sha)
            or not bundle_id or not raw_evidence_id or not adjustment_evidence_id
            or adjustment_basis not in {"SPLIT_ADJUSTED", "SPLIT_AND_DIVIDEND_ADJUSTED"}):
        raise ValueError("HISTORY_IDENTITY_OR_ADJUSTMENT_EVIDENCE_INVALID")
    if (captured_at.tzinfo is None or checked_at.tzinfo is None
            or captured_at > checked_at or response.get("s") != "ok"):
        raise ValueError("HISTORY_CAPTURE_OR_PROVIDER_STATUS_INVALID")
    names = {"t": "timestamps", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    if any(not isinstance(response.get(key), list) for key in names):
        raise ValueError("HISTORY_ARRAYS_INVALID")
    count = len(response["t"])
    if count < 1 or count > 10000 or any(len(response[key]) != count for key in names):
        raise ValueError("HISTORY_ARRAY_LENGTH_INVALID")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for key in names for value in response[key]):
        raise ValueError("HISTORY_NON_NUMERIC_OR_NONFINITE")
    epochs = response["t"]
    try:
        sessions = [datetime.fromtimestamp(value, timezone.utc).date().isoformat() for value in epochs]
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError("HISTORY_TIMESTAMP_INVALID") from exc
    if epochs != sorted(epochs) or len(set(sessions)) != count:
        raise ValueError("HISTORY_DUPLICATE_OR_UNORDERED_SESSION")
    for opened, high, low, close, volume in zip(*(response[key] for key in ("o", "h", "l", "c", "v"))):
        if min(opened, high, low, close) <= 0 or volume < 0 or not (low <= opened <= high and low <= close <= high):
            raise ValueError("HISTORY_OHLCV_INVALID")
    calendar = build_xnys_calendar(start_date=sessions[0], as_of=checked_at)
    capture_calendar = build_xnys_calendar(start_date=sessions[0], as_of=captured_at)
    if sessions[-1] != calendar["finalized_session"]:
        raise ValueError("HISTORY_NOT_CURRENT_FINALIZED_SESSION")
    if sessions != list(calendar["trading_sessions"]):
        raise ValueError("HISTORY_SESSION_CONTINUITY_FAILED")
    if sessions[-1] > capture_calendar["finalized_session"]:
        raise ValueError("HISTORY_CAPTURE_PRECEDES_FINALIZED_SESSION")
    payload = {name: list(response[key]) for key, name in names.items()}
    payload["completed_session_flags"] = [True] * count
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    family = {
        "capability": "historical_ohlcv", "payload": payload,
        "payload_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
        "provenance": {
            "ticker": ticker, "source": "FINNHUB_RETAINED_EVIDENCE",
            "raw_evidence_id": raw_evidence_id,
            "capture_timestamp": captured_at.astimezone(timezone.utc).isoformat(),
            "source_timestamp": datetime.fromtimestamp(epochs[-1], timezone.utc).isoformat(),
            "raw_response_sha256": hashlib.sha256(canonical(response)).hexdigest(),
            "contract_id": CONTRACT_ID, "contracted_endpoint": "/stock/candle",
            "commercial_display_allowed": True, "raw_machine_readable_redistribution_allowed": False,
            "corporate_action_adjustment_provenance": adjustment_basis,
            "adjustment_evidence_id": adjustment_evidence_id,
        },
    }
    return seal_research_market_bundle({
        "schema": SCHEMA, "ticker": ticker, "source_sha": source_sha, "bundle_id": bundle_id,
        "families": {"historical_ohlcv": family},
    })
