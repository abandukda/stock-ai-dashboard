"""Fail-closed provider-free planning for repairing BUY NOW history gaps."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "ATLAS_BUY_NOW_HISTORY_BACKFILL_V1"
CAPABILITIES = ("historical_ohlcv", "splits", "dividends")
ENDPOINTS = {
    "historical_ohlcv": "/stock/candle",
    "splits": "/stock/split",
    "dividends": "/stock/dividend",
}

UNAVAILABLE_REASONS = {
    "FINNHUB_NO_DATA",
    "FINNHUB_PARTIAL_SESSION_COVERAGE",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_history_backfill_plan(
    *, source_sha: str, symbols: Sequence[str], missing_sessions: Sequence[str],
    membership_identity: Mapping[str, Any], retained_history_identity: Mapping[str, Any],
) -> dict[str, Any]:
    governed = sorted({str(value).strip().upper() for value in symbols if str(value).strip()})
    sessions = [str(value) for value in missing_sessions]
    if len(source_sha) != 40:
        raise ValueError("BUY_NOW_BACKFILL_SOURCE_SHA_INVALID")
    if len(governed) != 1298:
        raise ValueError(f"BUY_NOW_BACKFILL_MEMBERSHIP_COUNT_INVALID:{len(governed)}")
    if sessions != sorted(set(sessions)) or not sessions:
        raise ValueError("BUY_NOW_BACKFILL_SESSIONS_NOT_ORDERED_UNIQUE")
    if membership_identity.get("membership_count") != 1298:
        raise ValueError("BUY_NOW_BACKFILL_MEMBERSHIP_IDENTITY_INVALID")
    if membership_identity.get("membership_sha256") != _digest(governed):
        raise ValueError("BUY_NOW_BACKFILL_MEMBERSHIP_DIGEST_MISMATCH")
    retained_end = str(retained_history_identity.get("last_contiguous_session") or "")
    retained_digest = str(retained_history_identity.get("artifact_set_sha256") or "")
    if not retained_end or len(retained_digest) != 64:
        raise ValueError("BUY_NOW_BACKFILL_RETAINED_IDENTITY_INVALID")
    if retained_end >= sessions[0]:
        raise ValueError("BUY_NOW_BACKFILL_OVERLAPS_RETAINED_HISTORY")

    # One range request per capability and ticker repairs every missing session;
    # request count does not multiply by observation horizon or session.
    requests = [
        {
            "ticker": ticker,
            "capability": capability,
            "endpoint": ENDPOINTS[capability],
            "from_session": sessions[0],
            "to_session": sessions[-1],
        }
        for ticker in governed for capability in CAPABILITIES
    ]
    first_date = date.fromisoformat(sessions[0])
    last_date = date.fromisoformat(sessions[-1])
    candle_from = int(datetime.combine(first_date, time.min, tzinfo=timezone.utc).timestamp())
    candle_to = int(
        datetime.combine(last_date + timedelta(days=1), time.min, tzinfo=timezone.utc).timestamp()
    ) - 1
    gateway_requests = []
    for ordinal, item in enumerate(requests, 1):
        parameters: dict[str, Any] = {
            "symbol": item["ticker"],
            "from": sessions[0],
            "to": sessions[-1],
        }
        if item["capability"] == "historical_ohlcv":
            parameters.update({"resolution": "D", "from": candle_from, "to": candle_to})
        gateway_requests.append({
            "ordinal": ordinal,
            "method": "GET",
            "endpoint": item["endpoint"],
            "ticker": item["ticker"],
            "capability": item["capability"],
            "parameters": parameters,
        })
    request_keys = [
        f"{item['ticker']}:{item['capability']}:{sessions[0]}:{sessions[-1]}"
        for item in requests
    ]
    if len(request_keys) != len(set(request_keys)):
        raise ValueError("BUY_NOW_BACKFILL_REQUEST_DEDUPLICATION_FAILED")
    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "PROVIDER_FREE_PLAN",
        "source_sha": source_sha,
        "provider_calls": 0,
        "automatic_retries": 0,
        "publication_writes": 0,
        "customer_symbol_count": len(governed),
        "missing_sessions": sessions,
        "missing_session_count": len(sessions),
        "range_start": sessions[0],
        "range_end": sessions[-1],
        "capabilities": list(CAPABILITIES),
        "endpoint_allowlist": [ENDPOINTS[value] for value in CAPABILITIES],
        "request_count": len(requests),
        "absolute_request_ceiling": len(requests),
        "request_keys": request_keys,
        "requests": gateway_requests,
        "execution_policy": {
            "concurrency": 1,
            "rate_limit_rpm": 60,
            "retry_count": 0,
            "raw_persistence_before_inspection": True,
            "stop_on_http_429": True,
            "stop_on_entitlement_error": True,
            "stop_on_schema_error": True,
        },
        "membership_identity": dict(membership_identity),
        "retained_history_identity": dict(retained_history_identity),
        "acceptance_contract": {
            "required_session_count_per_ticker": len(sessions),
            "require_ohlcv_and_volume": True,
            "require_strict_session_order": True,
            "reject_partial_ticker": True,
            "reject_duplicate_session": True,
            "reject_unexpected_session": True,
            "corporate_action_consistency_required": True,
            "partial_certification_forbidden": True,
        },
    }
    plan["plan_sha256"] = _digest(plan)
    return plan


def validate_backfill_observation_set(
    *, plan: Mapping[str, Any], observations: Mapping[str, Sequence[Mapping[str, Any]]],
    unavailable: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    expected_sessions = list(plan.get("missing_sessions") or [])
    expected_tickers = sorted({key.split(":", 1)[0] for key in plan.get("request_keys") or []})
    unavailable = dict(unavailable or {})
    if set(observations) & set(unavailable):
        raise ValueError("BUY_NOW_BACKFILL_AVAILABILITY_PARTITION_OVERLAP")
    if sorted(set(observations) | set(unavailable)) != expected_tickers:
        raise ValueError("BUY_NOW_BACKFILL_OBSERVATION_TICKERS_INCOMPLETE")
    unavailable_inventory = []
    for ticker in sorted(unavailable):
        record = unavailable[ticker]
        if record.get("reason") not in UNAVAILABLE_REASONS:
            raise ValueError(f"BUY_NOW_BACKFILL_UNAVAILABLE_REASON_INVALID:{ticker}")
        if record.get("requested_sessions") != expected_sessions:
            raise ValueError(f"BUY_NOW_BACKFILL_UNAVAILABLE_SESSION_SCOPE_INVALID:{ticker}")
        if len(str(record.get("raw_response_sha256") or "")) != 64:
            raise ValueError(f"BUY_NOW_BACKFILL_UNAVAILABLE_LINEAGE_INVALID:{ticker}")
        unavailable_inventory.append({
            "ticker": ticker,
            "reason": record["reason"],
            "raw_response_sha256": record["raw_response_sha256"],
            **({"missing_sessions": list(record.get("missing_sessions") or [])}
               if record["reason"] == "FINNHUB_PARTIAL_SESSION_COVERAGE" else {}),
        })
    for ticker in sorted(observations):
        rows = list(observations[ticker])
        sessions = [str(row.get("session") or "") for row in rows]
        if sessions != expected_sessions:
            raise ValueError(f"BUY_NOW_BACKFILL_SESSION_SEQUENCE_INVALID:{ticker}")
        for row in rows:
            if any(row.get(field) is None for field in ("open", "high", "low", "close", "volume")):
                raise ValueError(f"BUY_NOW_BACKFILL_OHLCV_INCOMPLETE:{ticker}:{row.get('session')}")
            if not row.get("raw_response_sha256") or not row.get("corporate_action_status"):
                raise ValueError(f"BUY_NOW_BACKFILL_LINEAGE_INCOMPLETE:{ticker}:{row.get('session')}")
    result = {
        "status": "COMPLETE",
        "ticker_count": len(expected_tickers),
        "available_ticker_count": len(observations),
        "unavailable_ticker_count": len(unavailable_inventory),
        "unavailable_inventory": unavailable_inventory,
        "session_count": len(expected_sessions),
        "observation_count": len(observations) * len(expected_sessions),
        "provider_calls": 0,
        "publication_writes": 0,
        "plan_sha256": plan.get("plan_sha256"),
    }
    result["result_sha256"] = _digest(result)
    return result


__all__ = ["build_history_backfill_plan", "validate_backfill_observation_set"]
