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
ADMISSION_RECEIPT_SCHEMA = "ATLAS_RESEARCH_MARKET_ADMISSION_RECEIPT_V1"
ADMISSION_STATUS_CODES = frozenset({"AVAILABLE", "PARTIAL", "UNAVAILABLE", "QA_ONLY", "NOT_RECORDED"})
ADMISSION_REASON_CODES = frozenset({
    "INVALID_TICKER", "ROOTS_NOT_CONFIGURED", "FILE_NOT_FOUND", "FILE_UNREADABLE",
    "SCHEMA_OR_LINEAGE_REJECTED", "SOURCE_PIN_MISMATCH", "BUNDLE_PIN_MISMATCH",
    "BACKUP_AUTHORITY_REJECTED", "RECORD_HASH_MISMATCH", "NO_VERIFIED_FAMILIES",
    "CONTEXT_ADMITTED", "HISTORY_FAMILY_REJECTED", "HISTORY_FAMILY_MISSING",
    "QA_ENRICHMENT_USED", "ADMISSION_RECEIPT_UNAVAILABLE", "BUNDLE_ACCEPTED",
})


def public_admission_marker_values(receipt: Any) -> dict[str, Any]:
    """Only public enumerated codes may cross the rendered diagnostic boundary."""
    receipt = receipt if isinstance(receipt, Mapping) else {}
    status, reason = receipt.get("status"), receipt.get("reason")
    result = {
        "status": status if isinstance(status, str) and status in ADMISSION_STATUS_CODES else "NOT_RECORDED",
        "reason": reason if isinstance(reason, str) and reason in ADMISSION_REASON_CODES else "ADMISSION_RECEIPT_UNAVAILABLE",
    }
    for field in ("primary_configured", "backup_configured", "source_pin_configured", "bundle_pin_configured"):
        result[field] = receipt.get(field) is True
    for field in ("accepted_family_count", "rejected_family_count"):
        value = receipt.get(field)
        result[field] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
    history = receipt.get("history_status")
    result["history_status"] = history if isinstance(history, str) and history in {
        "ADMITTED", "REJECTED", "MISSING", "NOT_EVALUATED"
    } else "NOT_EVALUATED"
    result["history_reason"] = {
        "ADMITTED": "HISTORY_FAMILY_ADMITTED", "REJECTED": "HISTORY_FAMILY_REJECTED",
        "MISSING": "HISTORY_FAMILY_ABSENT", "NOT_EVALUATED": "HISTORY_NOT_EVALUATED",
    }[result["history_status"]]
    return result

CLASSIFICATION = "CONTEXTUAL_NON_SCORING"
FAMILY_MAX_AGE_SECONDS = {
    "historical_ohlcv": 7 * 86400,
    "financial_statements": 32 * 86400,
    "basic_financials": 8 * 3600,
    "stock_earnings": 8 * 3600,
    "earnings_calendar": 8 * 3600,
    "company_profile": 7 * 86400,
    "live_quote": 60,
    "revenue_estimates": 8 * 3600,
    "eps_estimates": 8 * 3600,
    "recommendations": 4 * 3600,
    "price_targets": 4 * 3600,
    "analyst_actions": 4 * 3600,
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
    required = ("open", "high", "low", "volume")
    all_fields = ("timestamps", "close", "completed_session_flags", *required)
    if any(not isinstance(payload.get(name), (list, tuple)) for name in all_fields):
        return None
    timestamps = list(payload["timestamps"])
    closes = list(payload["close"])
    flags = list(payload["completed_session_flags"])
    arrays = {name: list(payload[name]) for name in required}
    if any(isinstance(value, bool) for name in ("timestamps", "close", *required) for value in payload[name]):
        return None
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
        if any(not math.isfinite(value) for value in epoch_values):
            return None
        parsed = [datetime.fromtimestamp(value, tz=timezone.utc) for value in epoch_values]
        sessions = [value.date().isoformat() for value in parsed]
        numeric = {
            "open": [float(value) for value in arrays["open"]],
            "high": [float(value) for value in arrays["high"]],
            "low": [float(value) for value in arrays["low"]],
            "close": [float(value) for value in closes],
            "volume": [float(value) for value in arrays["volume"]],
        }
    except (TypeError, ValueError, OSError, OverflowError):
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
    admission_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load retained context; optional diagnostic output never grants authority.

    The receipt contains public reason codes, booleans and counts only. Failed
    enrichment remains an empty dictionary; no path, exception or source value
    is copied into the receipt, and existing admission/fallback gates remain.
    """
    receipt = admission_receipt if admission_receipt is not None else {}
    receipt.clear()
    receipt.update({
        "schema": ADMISSION_RECEIPT_SCHEMA, "status": "UNAVAILABLE",
        "reason": "ROOTS_NOT_CONFIGURED",
        "primary_configured": root not in (None, ""),
        "backup_configured": backup_root not in (None, ""),
        "source_pin_configured": bool(expected_source_sha),
        "bundle_pin_configured": bool(expected_bundle_id),
        "attempts": [], "accepted_family_count": 0, "rejected_family_count": 0,
        "history_status": "NOT_EVALUATED", "history_reason": "HISTORY_NOT_EVALUATED",
    })
    symbol = _safe_ticker(ticker)
    if not symbol:
        receipt["reason"] = "INVALID_TICKER"
        return {}
    if root in (None, "") and backup_root in (None, ""):
        return {}
    document = None
    supplied = ""
    cache_source = ""
    for label, candidate in (("PRIMARY", root), ("BACKUP", backup_root)):
        if candidate in (None, ""):
            continue
        try:
            proposed = json.loads((Path(candidate) / f"{symbol}.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            receipt["attempts"].append({"source": label, "reason": "FILE_NOT_FOUND"})
            continue
        except (OSError, ValueError, TypeError):
            receipt["attempts"].append({"source": label, "reason": "FILE_UNREADABLE"})
            continue
        if not isinstance(proposed, dict) or not isinstance(proposed.get("families"), Mapping):
            receipt["attempts"].append({"source": label, "reason": "SCHEMA_OR_LINEAGE_REJECTED"})
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
        rejection = None
        if (proposed.get("schema") != SCHEMA
                or str(proposed.get("ticker") or "").upper() != symbol
                or not proposed.get("source_sha")
                or proposed.get("lineage_sha256") != lineage_sha):
            rejection = "SCHEMA_OR_LINEAGE_REJECTED"
        elif expected_source_sha and proposed.get("source_sha") != expected_source_sha:
            rejection = "SOURCE_PIN_MISMATCH"
        elif expected_bundle_id and proposed.get("bundle_id") != expected_bundle_id:
            rejection = "BUNDLE_PIN_MISMATCH"
        elif label == "BACKUP" and not (
            backup.get("independent_copy") is True and backup.get("lineage_sha256") == lineage_sha
        ):
            rejection = "BACKUP_AUTHORITY_REJECTED"
        elif proposed_hash != hashlib.sha256(_canonical(proposed)).hexdigest():
            rejection = "RECORD_HASH_MISMATCH"
        receipt["attempts"].append({"source": label, "reason": rejection or "BUNDLE_ACCEPTED"})
        if rejection is None:
            document, supplied, cache_source = proposed, proposed_hash, label
            break
    if document is None:
        reasons = [attempt["reason"] for attempt in receipt["attempts"]]
        # Keep a rejected primary pin/hash visible when its optional backup is
        # merely absent; all candidate outcomes remain in the safe receipt.
        receipt["reason"] = next((reason for reason in reasons if reason != "FILE_NOT_FOUND"), "FILE_NOT_FOUND")
        return {}
    checked = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    modules: dict[str, Any] = {}
    for key, envelope in (document.get("families") or {}).items():
        if not isinstance(envelope, Mapping) or envelope.get("capability") != key:
            receipt["rejected_family_count"] += 1
            continue
        verified = _family(envelope, ticker=symbol, now=checked)
        if verified:
            modules[str(key)] = verified
        else:
            receipt["rejected_family_count"] += 1
    receipt["accepted_family_count"] = len(modules)
    receipt["history_status"] = (
        "ADMITTED" if "historical_ohlcv" in modules else
        "REJECTED" if "historical_ohlcv" in document["families"] else "MISSING"
    )
    receipt["history_reason"] = {
        "ADMITTED": "HISTORY_FAMILY_ADMITTED", "REJECTED": "HISTORY_FAMILY_REJECTED",
        "MISSING": "HISTORY_FAMILY_ABSENT",
    }[receipt["history_status"]]
    if not modules:
        receipt["reason"] = "NO_VERIFIED_FAMILIES"
        return {}
    receipt["status"] = "AVAILABLE" if receipt["history_status"] == "ADMITTED" else "PARTIAL"
    receipt["reason"] = (
        "CONTEXT_ADMITTED" if receipt["history_status"] == "ADMITTED" else
        "HISTORY_FAMILY_REJECTED" if receipt["history_status"] == "REJECTED" else "HISTORY_FAMILY_MISSING"
    )
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
    "CLASSIFICATION", "FAMILY_MAX_AGE_SECONDS", "SCHEMA", "ADMISSION_RECEIPT_SCHEMA",
    "public_admission_marker_values",
    "load_research_market_context", "seal_research_market_bundle",
]
