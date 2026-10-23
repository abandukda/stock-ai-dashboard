"""Display-only reported EPS from admitted retained evidence; never earnings scoring."""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
import re
from typing import Any, Mapping

from services.finnhub_enterprise_display_contract import display_authority

CONTRACT = "ATLAS_RETAINED_REPORTED_EPS_CONTEXT_V1"
DISCLOSURES = (
    "Retained evidence does not establish the latest earnings release.",
    "Period end is not a report, announcement or publication date.",
    "EPS currency, basic/diluted basis, adjustment basis and reporting frequency are unverified.",
    "Actual and estimate are shown independently; comparability and beat/miss are not established.",
    "This context does not establish transcript or AI-analysis availability.",
)


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def _hash(value: Any, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None


def _number(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def build_retained_earnings_context(context: Any, *, ticker: str, now: datetime | None = None) -> dict:
    """Validate all rows before displaying any; do not infer fiscal basis or returns."""
    result = dict(contract=CONTRACT, status="UNAVAILABLE", records=[], source=None,
        latest_retained_period=None, cache_status="UNAVAILABLE", classification="CONTEXTUAL_NON_SCORING",
        rating_authority="UNCHANGED", publication_authority="UNCHANGED", provider_calls=0,
        comparison_allowed=False, disclosures=list(DISCLOSURES), reason="RETAINED_EARNINGS_NOT_ADMITTED")
    if not isinstance(context, Mapping) or not isinstance(ticker, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", ticker):
        return result
    family = context.get("stock_earnings")
    model = context.get("__read_model__")
    if not isinstance(family, Mapping) or not isinstance(model, Mapping):
        return result
    result["reason"] = "RETAINED_EARNINGS_LINEAGE_UNVERIFIED"
    if (context.get("__atlas_ticker__") != ticker or model.get("schema") != "ATLAS_RESEARCH_MARKET_READ_MODEL_V1"
        or not _hash(model.get("source_sha"), 40) or not _hash(model.get("record_sha256"), 64)
        or not isinstance(model.get("bundle_id"), str) or not model["bundle_id"].strip()
        or type(model.get("provider_calls")) is not int or model.get("provider_calls") != 0
        or type(model.get("serving_request_budget")) is not int or model.get("serving_request_budget") != 0
        or model.get("classification") != "CONTEXTUAL_NON_SCORING"
        or model.get("refresh_authority") != "NOT_AUTHORIZED_BY_READ_MODEL"
        or model.get("rating_authority") != "UNCHANGED" or model.get("publication_authority") != "UNCHANGED"):
        return result
    provenance = family.get("provenance")
    authority = display_authority("stock_earnings")
    if (not isinstance(provenance, Mapping) or provenance.get("ticker") != ticker
        or provenance.get("contract_id") != authority.contract_id
        or provenance.get("contracted_endpoint") != authority.endpoint
        or provenance.get("commercial_display_allowed") is not True
        or provenance.get("raw_machine_readable_redistribution_allowed") is not False
        or provenance.get("source") != "FINNHUB_RETAINED_EVIDENCE"
        or provenance.get("raw_capture_binding") != "EXACT_BYTES_VERIFIED"
        or not _hash(provenance.get("raw_response_sha256"), 64)
        or not isinstance(provenance.get("raw_evidence_id"), str) or not provenance["raw_evidence_id"].strip()):
        return result
    result["reason"] = "RETAINED_EARNINGS_CAPTURE_INVALID"
    captured = _instant(provenance.get("capture_timestamp"))
    checked = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(checked, datetime) or checked.tzinfo is None or captured is None or captured > checked:
        return result
    payload = family.get("payload")
    rows = payload.get("records") if isinstance(payload, Mapping) else None
    result["reason"] = "RETAINED_EARNINGS_RECORDS_INVALID"
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        return result
    records, periods = [], set()
    for row in rows:
        if not isinstance(row, Mapping) or row.get("symbol") != ticker or row.get("ticker", ticker) != ticker:
            return result
        period = row.get("period")
        try:
            if not isinstance(period, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
                return result
            parsed = date.fromisoformat(period)
        except ValueError:
            return result
        if period in periods or parsed > min(captured, checked).date():
            return result
        periods.add(period)
        actual, estimate = row.get("actual"), row.get("estimate")
        if (actual is None and estimate is None) or any(value is not None and not _number(value) for value in (actual, estimate)):
            return result
        records.append(dict(period_end=period, eps_actual=actual, eps_estimate=estimate,
            eps_currency=None, eps_basis="UNVERIFIED", periodicity="UNVERIFIED", comparison_allowed=False))
    records.sort(key=lambda item: item["period_end"], reverse=True)
    result.update(status="PARTIAL" if any(r["eps_actual"] is None or r["eps_estimate"] is None for r in records) else "AVAILABLE",
        reason="RETAINED_EARNINGS_CONTEXT_AVAILABLE", records=records[:8], latest_retained_period=records[0]["period_end"],
        cache_status=family.get("cache_status", "UNAVAILABLE"),
        source=dict(provider="FINNHUB_RETAINED_EVIDENCE", endpoint=authority.endpoint,
            captured_at=provenance["capture_timestamp"], raw_evidence_id=provenance["raw_evidence_id"],
            raw_response_sha256=provenance["raw_response_sha256"], source_sha=model["source_sha"],
            bundle_id=model["bundle_id"], record_sha256=model["record_sha256"]))
    return result
