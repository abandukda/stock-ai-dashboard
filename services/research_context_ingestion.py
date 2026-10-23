"""Pure retained gateway captures to review-only non-scoring Research context.

No client is constructed, credential read, file written or evidence promoted.
Only the intersection of the existing gateway allowlist and signed display
inventory is eligible. The caller still needs separate certification/promotion.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from services.finnhub_enterprise_display_contract import CONTRACT_ID, display_authority
from services.finnhub_shadow_provider import FinnhubShadowAdapter
from services.operations_gateway import CAPTURE_TIME_CONTRACT, RESEARCH_ENDPOINTS
from services.research_history_ingestion import _capture_instant, _verify_capture_window
from services.research_market_read_model import SCHEMA, seal_research_market_bundle
from services.research_analyst_context import analyst_context_rejection

CAPABILITIES = frozenset({"company_profile", "recommendations", "price_targets",
    "earnings_calendar", "company_news", "stock_earnings", "financial_statements"})
MAX_RAW_BYTES = 8 * 1024 * 1024


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _decode(raw: bytes) -> dict | list:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("CONTEXT_RAW_JSON_INVALID")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("CONTEXT_RAW_JSON_INVALID")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("CONTEXT_RAW_JSON_INVALID") from None
    if not isinstance(value, (dict, list)):
        raise ValueError("CONTEXT_RAW_JSON_INVALID")
    # Reject overflow such as 1e999 too, including unknown raw fields that a
    # normalizer would otherwise silently discard. Bound recursive validation.
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > 32:
            raise ValueError("CONTEXT_RAW_JSON_INVALID")
        if type(item) in (int, float):
            try:
                finite = math.isfinite(item)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("CONTEXT_RAW_JSON_INVALID")
        if isinstance(item, Mapping):
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
    return value


def _day(value: Any, *, latest: date | None = None,
         provider_calendar_clock: bool = False) -> None:
    if type(value) is not str:
        raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            parsed = date.fromisoformat(value)
        elif provider_calendar_clock and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
            # Financials As Reported documents this native format without a
            # timezone. Validate its complete calendar/clock, compare day only,
            # retain native text and never manufacture a UTC source instant.
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").date()
        else:
            raise ValueError("invalid date shape")
    except ValueError:
        raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID") from None
    if latest is not None and parsed > latest:
        raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")


def _number(value: Any, *, optional: bool = True) -> None:
    if value is None and optional:
        return
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 10000 or any(not isinstance(x, Mapping) for x in value):
        raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
    return value


def _identity(row: Mapping[str, Any], ticker: str, *, field: str = "symbol") -> None:
    # Do not silently drop cross-company rows during normalization.
    if row.get(field) != ticker:
        raise ValueError("CONTEXT_RESPONSE_TICKER_MISMATCH")
    for key in ("ticker", "symbol"):
        if key in row and row[key] != ticker:
            raise ValueError("CONTEXT_RESPONSE_TICKER_MISMATCH")


def _validate_response(capability: str, response: dict | list, *, ticker: str, captured: datetime) -> None:
    """Validate shapes before the legacy normalizer can omit invalid rows."""
    if isinstance(response, Mapping) and any(key in response for key in ("error", "errors")):
        raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
    if capability in {"company_profile", "price_targets", "financial_statements"}:
        if not isinstance(response, Mapping):
            raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
        _identity(response, ticker, field="ticker" if capability == "company_profile" else "symbol")
    if capability == "company_profile":
        if not isinstance(response.get("name"), str) or not response["name"].strip():
            raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
        for key in ("shareOutstanding", "marketCapitalization"):
            _number(response.get(key))
            if response.get(key) is not None and response[key] < 0:
                raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
    elif capability == "recommendations":
        for row in _rows(response):
            _identity(row, ticker)
    elif capability == "stock_earnings":
        for row in _rows(response):
            _identity(row, ticker)
            _day(row.get("period"), latest=captured.date())
            for key in ("actual", "estimate", "surprise", "surprisePercent"):
                _number(row.get(key))
            if row.get("actual") is None and row.get("estimate") is None:
                raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
    elif capability == "earnings_calendar":
        if not isinstance(response, Mapping):
            raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
        for row in _rows(response.get("earningsCalendar")):
            _identity(row, ticker)
            _day(row.get("date"))
            for key in ("epsActual", "epsEstimate", "revenueActual", "revenueEstimate"):
                _number(row.get(key))
    elif capability == "company_news":
        for row in _rows(response):
            if any(key in row and row[key] != ticker for key in ("symbol", "ticker")):
                raise ValueError("CONTEXT_RESPONSE_TICKER_MISMATCH")
            related = row.get("related")
            if type(related) is not str or ticker not in {s.strip() for s in related.split(",")}:
                raise ValueError("CONTEXT_RESPONSE_TICKER_MISMATCH")
            for key in ("headline", "source", "url"):
                if type(row.get(key)) is not str or not row[key].strip():
                    raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
            try:
                url = urlsplit(row["url"])
            except ValueError:
                raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID") from None
            if url.scheme != "https" or not url.hostname or url.username or url.password or any(c.isspace() for c in row["url"]):
                raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
            _number(row.get("datetime"), optional=False)
            if not 0 < row["datetime"] <= captured.timestamp():
                raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
    elif capability == "financial_statements":
        for report in _rows(response.get("data")):
            if any(key in report and report[key] != ticker for key in ("symbol", "ticker")):
                raise ValueError("CONTEXT_RESPONSE_TICKER_MISMATCH")
            _day(report.get("endDate"), latest=captured.date(), provider_calendar_clock=True)
            if report.get("filedDate") is not None:
                _day(report["filedDate"], latest=captured.date(), provider_calendar_clock=True)
            statements = report.get("report")
            if not isinstance(statements, Mapping) or not statements:
                raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
            for values in statements.values():
                for fact in _rows(values):
                    if not (isinstance(fact.get("concept"), str) or isinstance(fact.get("label"), str)):
                        raise ValueError("CONTEXT_RESPONSE_SCHEMA_INVALID")
                    _number(fact.get("value"), optional=False)


def build_context_review_from_gateway_capture(
    raw_response_bytes: bytes, *, metadata: Mapping[str, Any], run_summary: Mapping[str, Any],
    capability: str, ticker: str, source_sha: str, scope_sha256: str, bundle_id: str,
    captured_at: datetime, checked_at: datetime, raw_evidence_id: str,
) -> dict[str, Any]:
    """Convert one exact retained response to an inert owner-review wrapper.

    Capture/parameter/hash consistency cannot prove provider authenticity,
    entitlement, an independently trusted clock, or financial certification.
    """
    if type(capability) is not str:
        raise ValueError("CONTEXT_CAPABILITY_UNSUPPORTED")
    authority = display_authority(capability)
    if (capability not in CAPABILITIES or authority is None or authority.endpoint not in RESEARCH_ENDPOINTS):
        raise ValueError("CONTEXT_CAPABILITY_UNSUPPORTED")
    if (type(raw_response_bytes) is not bytes or not 0 < len(raw_response_bytes) <= MAX_RAW_BYTES
            or not isinstance(metadata, Mapping) or not isinstance(run_summary, Mapping)):
        raise ValueError("CONTEXT_GATEWAY_CAPTURE_INVALID")
    if (type(ticker) is not str or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", ticker)
            or type(source_sha) is not str or not re.fullmatch(r"[a-f0-9]{40}", source_sha)
            or type(scope_sha256) is not str or not re.fullmatch(r"[a-f0-9]{64}", scope_sha256)
            or type(bundle_id) is not str or not bundle_id.strip()
            or type(raw_evidence_id) is not str or not raw_evidence_id.strip()):
        raise ValueError("CONTEXT_IDENTITY_INVALID")
    if (run_summary.get("contract") != "ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1"
            or run_summary.get("source_sha") != source_sha or run_summary.get("scope_sha256") != scope_sha256
            or run_summary.get("status") != "PASS" or run_summary.get("failure_code") is not None
            or run_summary.get("automatic_redirects") is not False
            or type(run_summary.get("retry_count")) is not int or run_summary["retry_count"] != 0):
        raise ValueError("CONTEXT_GATEWAY_RUN_BINDING_INVALID")
    telemetry = run_summary.get("telemetry")
    counts = ("provider_calls", "max_provider_calls", "attempted_transport_calls", "responses_received")
    if (not isinstance(telemetry, list) or not 1 <= len(telemetry) <= 225
            or any(type(run_summary.get(k)) is not int for k in counts)
            or not len(telemetry) == run_summary["provider_calls"] <= run_summary["max_provider_calls"] <= 225
            or run_summary["attempted_transport_calls"] != len(telemetry)
            or run_summary["responses_received"] != len(telemetry)):
        raise ValueError("CONTEXT_GATEWAY_ATTEMPT_RECEIPT_INVALID")
    if any(not isinstance(row, Mapping) or type(row.get("ordinal")) is not int or row["ordinal"] != index
           or row.get("status") != "PASS" or row.get("failure_code") is not None or row.get("raw_complete") is not True
           or type(row.get("attempt_count")) is not int or row["attempt_count"] != 1
           or type(row.get("retry_count")) is not int or row["retry_count"] != 0
           for index, row in enumerate(telemetry, 1)):
        raise ValueError("CONTEXT_GATEWAY_ATTEMPT_RECEIPT_INVALID")
    # Reuse the exact versioned UTC window checks already used by history.
    _verify_capture_window(telemetry, run_summary, captured_at=captured_at, checked_at=checked_at)
    ordinal = metadata.get("ordinal")
    if (type(ordinal) is not int or not 1 <= ordinal <= len(telemetry)
            or telemetry[ordinal - 1] != dict(metadata)
            or metadata.get("ticker") != ticker or metadata.get("endpoint") != authority.endpoint
            or not isinstance(metadata.get("parameters"), Mapping) or metadata["parameters"].get("symbol") != ticker
            or metadata.get("status_code") != 200 or metadata.get("raw_capture") != "COMPLETE"
            or type(metadata.get("raw_bytes")) is not int or metadata["raw_bytes"] != len(raw_response_bytes)
            or metadata.get("raw_sha256") != hashlib.sha256(raw_response_bytes).hexdigest()):
        raise ValueError("CONTEXT_GATEWAY_RAW_BINDING_INVALID")
    response_completed = _capture_instant(metadata["response_completed_at"])
    response = _decode(raw_response_bytes)
    _validate_response(capability, response, ticker=ticker, captured=response_completed)
    try:
        payload = dict(FinnhubShadowAdapter._normalize(capability, response,
            capture_timestamp=response_completed.isoformat()))
    except (TypeError, ValueError, OverflowError, KeyError):
        raise ValueError("CONTEXT_RESPONSE_NORMALIZATION_INVALID") from None
    if capability == "company_news":
        # The existing adapter retains native epochs; the customer projector
        # requires dated attributed licensed display items. Identity and epoch
        # were checked above, so make that transformation explicit, not guessed.
        payload["articles"] = [{**article, "ticker": ticker,
            "commercial_display_allowed": True,
            "provider_article_timestamp_epoch": article["article_timestamp"],
            "article_timestamp": datetime.fromtimestamp(article["article_timestamp"], timezone.utc).isoformat(),
        } for article in payload["articles"]]
    reason = analyst_context_rejection(capability, payload, ticker=ticker, now=response_completed)
    if reason:
        raise ValueError("CONTEXT_ANALYST_PAYLOAD_INVALID")
    try:
        payload_bytes = _canonical(payload)
        normalized_response_bytes = _canonical(response)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("CONTEXT_RESPONSE_NORMALIZATION_INVALID") from None
    family = {"capability": capability, "payload": payload,
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "provenance": {"ticker": ticker, "source": "FINNHUB_RETAINED_EVIDENCE",
            "raw_evidence_id": raw_evidence_id, "capture_timestamp": response_completed.isoformat(),
            "raw_response_sha256": metadata["raw_sha256"],
            "normalized_response_sha256": hashlib.sha256(normalized_response_bytes).hexdigest(),
            "raw_capture_binding": "EXACT_BYTES_VERIFIED", "contract_id": CONTRACT_ID,
            "contracted_endpoint": authority.endpoint, "commercial_display_allowed": True,
            "raw_machine_readable_redistribution_allowed": False,
            "gateway_capture_time_contract": CAPTURE_TIME_CONTRACT,
            "gateway_code_source_sha": source_sha, "gateway_scope_sha256": scope_sha256,
            "gateway_request_ordinal": ordinal,
            "gateway_attempt_started_at": metadata["attempt_started_at"],
            "gateway_response_completed_at": metadata["response_completed_at"],
            "gateway_run_capture_completed_at": run_summary["capture_completed_at"],
            "capture_time_binding": "GATEWAY_RECEIPT_BOUND_NOT_CLOCK_CERTIFICATION",
            "response_identity_binding": "REQUEST_AND_RESPONSE_TICKER_VERIFIED",
        }}
    if capability == "financial_statements":
        family["provenance"]["source_date_semantics"] = "PROVIDER_CALENDAR_DATES_TIMEZONE_UNATTESTED"
    elif capability == "price_targets":
        updated = payload["last_updated"]  # Validated by the shared analyst boundary above.
        family["provenance"]["source_update_value"] = updated
        family["provenance"]["source_date_semantics"] = (
            "PROVIDER_CALENDAR_DATE_TIMEZONE_UNATTESTED"
            if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", updated)
            else "PROVIDER_CALENDAR_DATE_ONLY" if len(updated) == 10
            else "PROVIDER_TIMESTAMP_EXPLICIT_TIMEZONE"
        )
    bundle = seal_research_market_bundle({"schema": SCHEMA, "ticker": ticker,
        "source_sha": source_sha, "bundle_id": bundle_id, "families": {capability: family}})
    return {"status": "OWNER_REVIEW_ONLY_NOT_PUBLISHED", "bundle": bundle,
        "source_sha": source_sha, "scope_sha256": scope_sha256,
        "raw_sha256": metadata["raw_sha256"], "raw_bytes": len(raw_response_bytes),
        "provider_calls": 0, "publication_writes": 0, "report_card_writes": 0,
        "financial_certification": "SEPARATE_GOVERNED_REVIEW_REQUIRED",
        "capture_time_binding": "GATEWAY_RECEIPT_BOUND_NOT_CLOCK_CERTIFICATION"}


__all__ = ["CAPABILITIES", "build_context_review_from_gateway_capture"]
