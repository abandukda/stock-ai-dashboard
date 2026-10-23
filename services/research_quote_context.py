"""Provider-free quote review and a separate, non-scoring display projection.

The quote-only receipt below is an inert review format, not a registered live
executor or an acquisition/promotion approval. Hashes bind supplied bytes and
request claims; they do not prove provider authenticity or a trusted clock.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Any, Mapping

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.operations_gateway import CAPTURE_TIME_CONTRACT
from services.research_context_ingestion import _decode
from services.research_history_ingestion import _capture_instant, _verify_capture_window
from services.research_refresh_execution import validate_execution_plan

QUOTE_CAPTURE_SCHEMA = "ATLAS_RESEARCH_QUOTE_CAPTURE_REVIEW_V1"
QUOTE_MAX_AGE_SECONDS = 60
QUOTE_MAX_RAW_BYTES = 64 * 1024


def _canonical(value: Any) -> bytes:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def quote_identity(payload: Any, *, captured: datetime, checked: datetime) -> dict[str, Any] | None:
    """Validate provider quote values and freshness using its own source time.

    A 60-second quote policy is NOT a completed-session/EOD certification rule.
    A closed market can legitimately have an old last trade: show it as dated,
    never relabel it current merely because its response was captured recently.
    """
    if (not isinstance(payload, Mapping) or not isinstance(captured, datetime)
            or not isinstance(checked, datetime) or captured.tzinfo is None or checked.tzinfo is None
            or captured > checked):
        return None
    names = ("price", "open", "high", "low", "previous_close")
    if any(type(payload.get(key)) not in (int, float) for key in names):
        return None
    try:
        if any(not math.isfinite(payload[key]) or payload[key] <= 0 for key in names):
            return None
        if not payload["low"] <= payload["price"] <= payload["high"] or not payload["low"] <= payload["open"] <= payload["high"]:
            return None
        epoch = payload.get("provider_timestamp")
        if type(epoch) is not int or epoch <= 0:
            return None
        source_time = datetime.fromtimestamp(epoch, timezone.utc)
    except (OverflowError, ValueError, OSError, TypeError):
        return None
    if source_time > captured:
        return None
    age = (checked - source_time).total_seconds()
    return {
        "as_of": source_time.isoformat(), "source_age_seconds": age,
        "freshness": "RECENT_PROVIDER_TIMESTAMP" if age <= QUOTE_MAX_AGE_SECONDS else "DATED_PROVIDER_TIMESTAMP",
        "market_coverage": "PARTIAL_REALTIME", "classification": "CONTEXTUAL_NON_SCORING",
        "price_basis": "PROVIDER_QUOTE_NOT_CERTIFIED_CLOSE",
    }


def build_quote_review_from_capture(raw_response_bytes: bytes, *, plan: Mapping[str, Any],
        expected_source_sha: str, expected_package_sha256: str, ticker: str,
        metadata: Mapping[str, Any], run_summary: Mapping[str, Any], bundle_id: str,
        captured_at: datetime, checked_at: datetime, raw_evidence_id: str) -> dict[str, Any]:
    """Bind one quote to an explicitly pinned quote-only plan, with no I/O.

    Generic Research gateway/context allowlists are deliberately unchanged.
    This format does not register a transport or authorize publishing its bundle.
    Standard /quote has no ticker field: its identity is request-bound only.
    """
    requests = validate_execution_plan(plan)
    if (not re.fullmatch(r"[0-9a-f]{40}", str(expected_source_sha))
            or not re.fullmatch(r"[0-9a-f]{64}", str(expected_package_sha256))
            or plan.get("source_sha") != expected_source_sha
            or plan.get("package_sha256") != expected_package_sha256
            or type(ticker) is not str or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", ticker)
            or type(bundle_id) is not str or not bundle_id.strip()
            or type(raw_evidence_id) is not str or not raw_evidence_id.strip()):
        raise ValueError("QUOTE_REVIEW_SOURCE_OR_IDENTITY_INVALID")
    if (not 1 <= len(requests) <= 25
            or any(row.get("capability") != "live_quote" or row.get("endpoint") != "/quote"
                   or row.get("parameters") != {"symbol": row.get("ticker")} for row in requests)
            or len({row.get("ticker") for row in requests}) != len(requests)):
        raise ValueError("QUOTE_REVIEW_QUOTE_ONLY_SCOPE_REQUIRED")
    if (type(raw_response_bytes) is not bytes or not 0 < len(raw_response_bytes) <= QUOTE_MAX_RAW_BYTES
            or not isinstance(metadata, Mapping) or not isinstance(run_summary, Mapping)):
        raise ValueError("QUOTE_REVIEW_CAPTURE_INVALID")
    if (run_summary.get("contract") != QUOTE_CAPTURE_SCHEMA
            or run_summary.get("source_sha") != expected_source_sha
            or run_summary.get("package_sha256") != expected_package_sha256
            or run_summary.get("scope_sha256") != plan["scope_sha256"]
            or run_summary.get("status") != "PASS" or run_summary.get("failure_code") is not None
            or run_summary.get("automatic_redirects") is not False
            or type(run_summary.get("retry_count")) is not int or run_summary["retry_count"] != 0):
        raise ValueError("QUOTE_REVIEW_RUN_BINDING_INVALID")
    telemetry = run_summary.get("telemetry")
    counts = ("provider_calls", "max_provider_calls", "attempted_transport_calls", "responses_received")
    if (not isinstance(telemetry, list) or len(telemetry) != len(requests)
            or any(type(run_summary.get(key)) is not int for key in counts)
            or any(run_summary[key] != len(requests) for key in counts)):
        raise ValueError("QUOTE_REVIEW_RECEIPT_BUDGET_INVALID")
    for request, row in zip(requests, telemetry):
        if (not isinstance(row, Mapping) or type(row.get("ordinal")) is not int
                or row["ordinal"] != request["ordinal"] or row.get("request_sha256") != request["request_sha256"]
                or row.get("ticker") != request["ticker"] or row.get("endpoint") != "/quote"
                or row.get("parameters") != request["parameters"]
                or row.get("status") != "PASS" or row.get("failure_code") is not None
                or row.get("status_code") != 200 or row.get("raw_complete") is not True
                or row.get("raw_capture") != "COMPLETE" or type(row.get("attempt_count")) is not int
                or row["attempt_count"] != 1 or type(row.get("retry_count")) is not int or row["retry_count"] != 0):
            raise ValueError("QUOTE_REVIEW_REQUEST_BINDING_INVALID")
    _verify_capture_window(telemetry, run_summary, captured_at=captured_at, checked_at=checked_at)
    ordinal = metadata.get("ordinal")
    if (type(ordinal) is not int or not 1 <= ordinal <= len(telemetry)
            or telemetry[ordinal - 1] != dict(metadata) or metadata.get("ticker") != ticker
            or type(metadata.get("raw_bytes")) is not int or metadata["raw_bytes"] != len(raw_response_bytes)
            or metadata.get("raw_sha256") != hashlib.sha256(raw_response_bytes).hexdigest()):
        raise ValueError("QUOTE_REVIEW_RAW_BINDING_INVALID")
    response = _decode(raw_response_bytes)
    if not isinstance(response, Mapping) or any(key in response for key in ("error", "errors")):
        raise ValueError("QUOTE_REVIEW_RESPONSE_INVALID")
    if any(key in response and response[key] != ticker for key in ("ticker", "symbol")):
        raise ValueError("QUOTE_REVIEW_RESPONSE_TICKER_MISMATCH")
    payload = {name: response.get(key) for name, key in
               (("price", "c"), ("open", "o"), ("high", "h"), ("low", "l"),
                ("previous_close", "pc"), ("provider_timestamp", "t"))}
    completed = _capture_instant(metadata["response_completed_at"])
    if quote_identity(payload, captured=completed, checked=checked_at) is None:
        raise ValueError("QUOTE_REVIEW_VALUES_OR_SOURCE_TIME_INVALID")
    family = {"capability": "live_quote", "payload": payload,
        "payload_sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
        "provenance": {"ticker": ticker, "source": "FINNHUB_RETAINED_QUOTE_CONTEXT",
            "raw_evidence_id": raw_evidence_id, "capture_timestamp": completed.isoformat(),
            "raw_response_sha256": metadata["raw_sha256"], "raw_capture_binding": "EXACT_BYTES_VERIFIED",
            "contract_id": CONTRACT_ID, "contracted_endpoint": "/quote", "commercial_display_allowed": True,
            "raw_machine_readable_redistribution_allowed": False,
            "response_identity_binding": "REQUEST_BOUND_PROVIDER_RESPONSE_HAS_NO_REQUIRED_TICKER",
            "capture_time_binding": "RECEIPT_BOUND_NOT_CLOCK_CERTIFICATION",
            "quote_scope_sha256": plan["scope_sha256"], "quote_package_sha256": expected_package_sha256,
            "quote_code_source_sha": expected_source_sha}}
    from services.research_market_read_model import SCHEMA, seal_research_market_bundle
    bundle = seal_research_market_bundle({"schema": SCHEMA, "ticker": ticker, "source_sha": expected_source_sha,
        "bundle_id": bundle_id, "families": {"live_quote": family}})
    return {"status": "OWNER_REVIEW_ONLY_NOT_PUBLISHED", "bundle": bundle, "provider_calls": 0,
        "publication_writes": 0, "report_card_writes": 0,
        "financial_certification": "NONE_QUOTE_IS_NON_SCORING_CONTEXT",
        "provider_authenticity": "NOT_ESTABLISHED_BY_REVIEW", "live_transport": "NOT_REGISTERED"}


def project_quote_context(family: Any, *, ticker: str, checked_at: datetime | None = None,
                          profile: Any = None) -> dict[str, Any]:
    unavailable = {"status": "UNAVAILABLE", "classification": "CONTEXTUAL_NON_SCORING"}
    if not isinstance(family, Mapping) or not isinstance(family.get("quote_identity"), Mapping):
        return unavailable
    provenance = family.get("provenance")
    if (not isinstance(provenance, Mapping) or provenance.get("ticker") != ticker
            or provenance.get("contract_id") != CONTRACT_ID or provenance.get("contracted_endpoint") != "/quote"
            or provenance.get("commercial_display_allowed") is not True
            or provenance.get("raw_machine_readable_redistribution_allowed") is not False
            or type(provenance.get("raw_evidence_id")) is not str or not provenance["raw_evidence_id"].strip()):
        return unavailable
    try:
        captured = _capture_instant(provenance.get("capture_timestamp"))
    except ValueError:
        return unavailable
    identity = quote_identity(family.get("payload"), captured=captured,
        checked=checked_at or datetime.now(timezone.utc))
    if identity is None:
        return unavailable
    currency, currency_evidence = None, None
    if isinstance(profile, Mapping) and isinstance(profile.get("payload"), Mapping):
        own = profile.get("provenance")
        supplied = profile["payload"].get("currency")
        if (isinstance(own, Mapping) and own.get("ticker") == ticker
                and type(own.get("raw_evidence_id")) is str and own["raw_evidence_id"].strip()
                and own.get("contract_id") == CONTRACT_ID
                and own.get("contracted_endpoint") == "/stock/profile2"
                and own.get("commercial_display_allowed") is True
                and own.get("raw_machine_readable_redistribution_allowed") is False
                and type(supplied) is str and re.fullmatch(r"[A-Z]{3}", supplied)):
            currency, currency_evidence = supplied, own["raw_evidence_id"]
    return {"status": "AVAILABLE" if identity["freshness"] == "RECENT_PROVIDER_TIMESTAMP" else "DATED",
        **identity, "price": family["payload"]["price"], "currency": currency,
        "currency_evidence_id": currency_evidence, "captured_at": captured.isoformat(),
        "source": provenance.get("source"), "evidence_id": provenance["raw_evidence_id"],
        "identity_binding": provenance.get("response_identity_binding")}
