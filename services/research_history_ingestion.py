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


def _decode_raw_capture(raw: bytes) -> dict[str, Any]:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate source key")
            result[key] = value
        return result
    def reject_constant(_value):
        raise ValueError("nonfinite source constant")
    value = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("source object required")
    return value


def build_history_bundle(
    response: Mapping[str, Any], *, ticker: str, source_sha: str, bundle_id: str,
    captured_at: datetime, checked_at: datetime, raw_evidence_id: str,
    adjustment_basis: str, adjustment_evidence_id: str,
    raw_response_bytes: bytes | None = None,
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
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    raw_digest = None
    if raw_response_bytes is not None:
        if type(raw_response_bytes) is not bytes or not 0 < len(raw_response_bytes) <= 8 * 1024 * 1024:
            raise ValueError("HISTORY_RAW_CAPTURE_SIZE_OR_TYPE_INVALID")
        try:
            decoded = _decode_raw_capture(raw_response_bytes)
            if not isinstance(decoded, dict) or canonical(decoded) != canonical(response):
                raise ValueError("HISTORY_RAW_CAPTURE_PAYLOAD_MISMATCH")
        except (UnicodeError, ValueError, TypeError):
            raise ValueError("HISTORY_RAW_CAPTURE_PAYLOAD_MISMATCH") from None
        raw_digest = hashlib.sha256(raw_response_bytes).hexdigest()
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
    family = {
        "capability": "historical_ohlcv", "payload": payload,
        "payload_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
        "provenance": {
            "ticker": ticker, "source": "FINNHUB_RETAINED_EVIDENCE",
            "raw_evidence_id": raw_evidence_id,
            "capture_timestamp": captured_at.astimezone(timezone.utc).isoformat(),
            "source_timestamp": datetime.fromtimestamp(epochs[-1], timezone.utc).isoformat(),
            # A normalized-object digest cannot attest the captured response bytes.
            "normalized_response_sha256": hashlib.sha256(canonical(response)).hexdigest(),
            "raw_response_sha256": raw_digest,
            "raw_capture_binding": "EXACT_BYTES_VERIFIED" if raw_digest else "NOT_SUPPLIED",
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


def build_history_review_from_gateway_capture(
    raw_response_bytes: bytes, *, metadata: Mapping[str, Any], run_summary: Mapping[str, Any],
    ticker: str, source_sha: str, scope_sha256: str, bundle_id: str,
    captured_at: datetime, checked_at: datetime, raw_evidence_id: str,
    adjustment_basis: str, adjustment_evidence_id: str,
) -> dict[str, Any]:
    """Bind a complete raw gateway record to a provider-free review candidate.

    Hash consistency is not source certification or execution authorization.
    The review wrapper is intentionally not an admissible read-model document.
    No files, ledgers, credentials, transport or production state are accessed.
    """
    if (type(raw_response_bytes) is not bytes or not 0 < len(raw_response_bytes) <= 8 * 1024 * 1024
            or not isinstance(metadata, Mapping) or not isinstance(run_summary, Mapping)):
        raise ValueError("HISTORY_GATEWAY_CAPTURE_INVALID")
    if (not re.fullmatch(r"[a-f0-9]{64}", scope_sha256)
            or run_summary.get("contract") != "ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1"
            or run_summary.get("source_sha") != source_sha
            or run_summary.get("scope_sha256") != scope_sha256
            or run_summary.get("status") != "PASS" or run_summary.get("failure_code") is not None
            or run_summary.get("automatic_redirects") is not False
            or type(run_summary.get("retry_count")) is not int or run_summary["retry_count"] != 0):
        raise ValueError("HISTORY_GATEWAY_RUN_BINDING_INVALID")
    telemetry = run_summary.get("telemetry")
    if (not isinstance(telemetry, list) or not 1 <= len(telemetry) <= 225
            or type(run_summary.get("provider_calls")) is not int
            or type(run_summary.get("max_provider_calls")) is not int
            or not len(telemetry) == run_summary["provider_calls"] <= run_summary["max_provider_calls"] <= 225
            or type(run_summary.get("attempted_transport_calls")) is not int
            or run_summary["attempted_transport_calls"] != run_summary["provider_calls"]
            or type(run_summary.get("responses_received")) is not int
            or run_summary.get("responses_received") != len(telemetry)):
        raise ValueError("HISTORY_GATEWAY_ATTEMPT_RECEIPT_INVALID")
    if any(not isinstance(row, Mapping) or type(row.get("ordinal")) is not int or row["ordinal"] != index
           or row.get("status") != "PASS" or row.get("raw_complete") is not True
           or type(row.get("attempt_count")) is not int or row["attempt_count"] != 1
           or type(row.get("retry_count")) is not int or row["retry_count"] != 0
           for index, row in enumerate(telemetry, 1)):
        raise ValueError("HISTORY_GATEWAY_ATTEMPT_RECEIPT_INVALID")
    ordinal = metadata.get("ordinal")
    if (type(ordinal) is not int or not 1 <= ordinal <= len(telemetry)
            or telemetry[ordinal - 1] != dict(metadata)
            or metadata.get("ticker") != ticker or metadata.get("endpoint") != "/stock/candle"
            or not isinstance(metadata.get("parameters"), Mapping)
            or metadata["parameters"].get("symbol") != ticker
            or metadata.get("status") != "PASS" or metadata.get("raw_complete") is not True
            or metadata.get("status_code") != 200 or metadata.get("attempt_count") != 1
            or metadata.get("retry_count") != 0
            or metadata.get("raw_capture") != "COMPLETE"
            or metadata.get("raw_bytes") != len(raw_response_bytes)
            or metadata.get("raw_sha256") != hashlib.sha256(raw_response_bytes).hexdigest()):
        raise ValueError("HISTORY_GATEWAY_RAW_BINDING_INVALID")
    try:
        response = _decode_raw_capture(raw_response_bytes)
    except (UnicodeError, ValueError):
        raise ValueError("HISTORY_GATEWAY_RAW_JSON_INVALID") from None
    bundle = build_history_bundle(
        response, ticker=ticker, source_sha=source_sha, bundle_id=bundle_id,
        captured_at=captured_at, checked_at=checked_at, raw_evidence_id=raw_evidence_id,
        adjustment_basis=adjustment_basis, adjustment_evidence_id=adjustment_evidence_id,
        raw_response_bytes=raw_response_bytes,
    )
    return {
        "status": "OWNER_REVIEW_ONLY_NOT_PUBLISHED", "bundle": bundle,
        "source_sha": source_sha, "scope_sha256": scope_sha256,
        "raw_sha256": metadata["raw_sha256"], "raw_bytes": len(raw_response_bytes),
        "provider_calls": 0, "publication_writes": 0, "report_card_writes": 0,
        "financial_certification": "SEPARATE_GOVERNED_REVIEW_REQUIRED",
    }
