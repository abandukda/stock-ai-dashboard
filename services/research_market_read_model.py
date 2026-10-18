"""Read-only, cache-first market evidence for customer Research.

This module deliberately has no provider adapter. It can only project a
content-addressed retained bundle whose display rights and provenance have
already been recorded. The resulting context is educational/non-scoring and
cannot replace certified recommendation or publication authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from services.finnhub_enterprise_display_contract import display_authority
from services.report_card_exchange_calendar import build_xnys_calendar


SCHEMA = "ATLAS_RESEARCH_MARKET_READ_MODEL_V1"
CLASSIFICATION = "CONTEXTUAL_NON_SCORING"
FAMILY_MAX_AGE_SECONDS = {
    "historical_ohlcv": 7 * 86400,
    "financial_statements": 32 * 86400,
    "basic_financials": 8 * 3600,
    "stock_earnings": 8 * 3600,
    "earnings_calendar": 8 * 3600,
    "company_profile": 7 * 86400,
    "recommendations": 4 * 3600,
    "price_targets": 4 * 3600,
    "company_news": 3600,
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _safe_ticker(value: str) -> str:
    return "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {"-", "."})


def _market_identity(payload: Any, *, captured: datetime, checked: datetime) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    timestamps = list(payload.get("timestamps") or ())
    closes = list(payload.get("close") or ())
    flags = list(payload.get("completed_session_flags") or ())
    required = ("open", "high", "low", "volume")
    arrays = {name: list(payload.get(name) or ()) for name in required}
    if (
        not timestamps
        or len(timestamps) != len(closes)
        or len(flags) != len(timestamps)
        or any(len(values) != len(timestamps) for values in arrays.values())
    ):
        return None
    if any(flag is not True for flag in flags):
        return None
    try:
        epoch_values = [float(value) for value in timestamps]
        parsed = [datetime.fromtimestamp(value, tz=timezone.utc) for value in epoch_values]
        sessions = [value.date().isoformat() for value in parsed]
        numeric = {
            "open": [float(value) for value in arrays["open"]],
            "high": [float(value) for value in arrays["high"]],
            "low": [float(value) for value in arrays["low"]],
            "close": [float(value) for value in closes],
            "volume": [float(value) for value in arrays["volume"]],
        }
    except (TypeError, ValueError, OSError):
        return None
    if epoch_values != sorted(epoch_values) or len(sessions) != len(set(sessions)):
        return None
    if any(not math.isfinite(value) for values in numeric.values() for value in values):
        return None
    for opened, high, low, close, volume in zip(
        numeric["open"], numeric["high"], numeric["low"], numeric["close"], numeric["volume"]
    ):
        if min(opened, high, low, close) <= 0 or volume < 0 or low > high or not (low <= opened <= high and low <= close <= high):
            return None
    try:
        capture_calendar = build_xnys_calendar(start_date=sessions[0], as_of=captured)
        current_calendar = build_xnys_calendar(start_date=sessions[0], as_of=checked)
    except (ValueError, KeyError):
        return None
    governed_sessions = set(capture_calendar["trading_sessions"])
    if any(session not in governed_sessions for session in sessions):
        return None
    latest_session = sessions[-1]
    current = latest_session == current_calendar["finalized_session"]
    return {
        "latest_verified_close": numeric["close"][-1],
        "latest_completed_session": latest_session,
        "latest_finalized_session": current_calendar["finalized_session"],
        "session_freshness": "CURRENT_FINALIZED_SESSION" if current else "STALE_FINALIZED_SESSION",
        "price_basis": "END_OF_DAY_COMPLETED_SESSION",
        "is_real_time": False,
        "is_delayed_intraday": False,
    }


def _family(envelope: Any, *, ticker: str, now: datetime) -> dict[str, Any] | None:
    if not isinstance(envelope, Mapping):
        return None
    item = dict(envelope)
    capability = str(item.get("capability") or "")
    authority = display_authority(capability)
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    payload = item.get("payload")
    captured = _instant(provenance.get("capture_timestamp"))
    evidence_id = str(provenance.get("raw_evidence_id") or "").strip()
    payload_sha = str(item.get("payload_sha256") or "").strip()
    if (
        authority is None
        or not isinstance(payload, (Mapping, list))
        or not captured
        or not evidence_id
        or captured.timestamp() > now.timestamp() + 300
        or str(provenance.get("ticker") or "").upper() != ticker
        or provenance.get("commercial_display_allowed") is not True
        or provenance.get("raw_machine_readable_redistribution_allowed") is not False
        or str(provenance.get("contract_id") or "") != authority.contract_id
        or str(provenance.get("contracted_endpoint") or "") != authority.endpoint
        or payload_sha != hashlib.sha256(_canonical(payload)).hexdigest()
    ):
        return None
    age = max(0.0, (now - captured).total_seconds())
    max_age = FAMILY_MAX_AGE_SECONDS.get(capability)
    status = "FRESH_CACHE" if max_age is None or age <= max_age else "STALE_RETAINED"
    result = {
        "payload": payload,
        "provenance": {**dict(provenance), "source": provenance.get("source") or "FINNHUB_RETAINED_EVIDENCE"},
        "cache_status": status,
        "age_seconds": age,
        "classification": CLASSIFICATION,
    }
    if capability == "historical_ohlcv":
        identity = _market_identity(payload, captured=captured, checked=now)
        if identity is None:
            return None
        result["market_identity"] = identity
    return result


def load_research_market_context(
    ticker: str, root: str | Path | None, *, now: datetime | None = None,
    backup_root: str | Path | None = None,
    expected_source_sha: str | None = None,
    expected_bundle_id: str | None = None,
) -> dict[str, Any]:
    """Load a verified retained bundle without network access or mutation."""
    symbol = _safe_ticker(ticker)
    if not symbol or (root in (None, "") and backup_root in (None, "")):
        return {}
    document = None
    supplied = ""
    cache_source = ""
    for label, candidate in (("PRIMARY", root), ("BACKUP", backup_root)):
        if candidate in (None, ""):
            continue
        try:
            proposed = json.loads((Path(candidate) / f"{symbol}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        proposed_hash = str(proposed.pop("record_sha256", ""))
        lineage = {
            "ticker": proposed.get("ticker"), "source_sha": proposed.get("source_sha"),
            "bundle_id": proposed.get("bundle_id"),
            "family_payload_sha256": sorted(
                str(item.get("payload_sha256") or "")
                for item in (proposed.get("families") or {}).values()
                if isinstance(item, Mapping)
            ),
        }
        lineage_sha = hashlib.sha256(_canonical(lineage)).hexdigest()
        backup = proposed.get("backup_provenance") if isinstance(proposed.get("backup_provenance"), Mapping) else {}
        if (
            proposed.get("schema") == SCHEMA
            and str(proposed.get("ticker") or "").upper() == symbol
            and proposed.get("source_sha")
            and proposed.get("lineage_sha256") == lineage_sha
            and (not expected_source_sha or proposed.get("source_sha") == expected_source_sha)
            and (not expected_bundle_id or proposed.get("bundle_id") == expected_bundle_id)
            and (label != "BACKUP" or (
                backup.get("independent_copy") is True
                and backup.get("lineage_sha256") == lineage_sha
            ))
            and proposed_hash == hashlib.sha256(_canonical(proposed)).hexdigest()
        ):
            document, supplied, cache_source = proposed, proposed_hash, label
            break
    if document is None:
        return {}
    checked = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    modules: dict[str, Any] = {}
    for key, envelope in (document.get("families") or {}).items():
        verified = _family(envelope, ticker=symbol, now=checked)
        if verified:
            modules[str(key)] = verified
    if not modules:
        return {}
    modules["__atlas_ticker__"] = symbol
    modules["__read_model__"] = {
        "schema": SCHEMA,
        "source_sha": document["source_sha"],
        "bundle_id": document.get("bundle_id"),
        "record_sha256": supplied,
        "classification": CLASSIFICATION,
        "provider_calls": 0,
        "serving_request_budget": 0,
        "refresh_authority": "NOT_AUTHORIZED_BY_READ_MODEL",
        "cache_source": cache_source,
        "rating_authority": "UNCHANGED",
        "publication_authority": "UNCHANGED",
    }
    market = modules.get("historical_ohlcv") or {}
    if market.get("market_identity"):
        modules["__read_model__"]["market_identity"] = dict(market["market_identity"])
    return modules


def seal_research_market_bundle(document: Mapping[str, Any]) -> dict[str, Any]:
    """Test/producer helper: attach the deterministic top-level self hash."""
    payload = dict(document)
    payload.pop("record_sha256", None)
    lineage = {
        "ticker": payload.get("ticker"), "source_sha": payload.get("source_sha"),
        "bundle_id": payload.get("bundle_id"),
        "family_payload_sha256": sorted(
            str(item.get("payload_sha256") or "")
            for item in (payload.get("families") or {}).values()
            if isinstance(item, Mapping)
        ),
    }
    payload["lineage_sha256"] = hashlib.sha256(_canonical(lineage)).hexdigest()
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return payload


__all__ = [
    "CLASSIFICATION", "FAMILY_MAX_AGE_SECONDS", "SCHEMA",
    "load_research_market_context", "seal_research_market_bundle",
]
