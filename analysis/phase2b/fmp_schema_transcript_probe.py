"""Five-request sanitized FMP schema and transcript diagnostic.

The probe is designed exclusively for a manually dispatched GitHub Actions
job. Provider payloads remain in memory and only field names, primitive type
names, presence flags, counts, and transcript-length metadata are persisted.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://financialmodelingprep.com/stable"
SYMBOL = "NVDA"
REQUEST_CAP = 5
TIMEOUT_SECONDS = 12.0
OUTPUT_PATH = Path("fmp_phase2b_schema_probe_summary.json")

FIXED_REQUESTS = (
    ("analyst_estimates", "analyst-estimates", {"symbol": SYMBOL, "period": "annual", "limit": 12}),
    ("ratios", "ratios", {"symbol": SYMBOL, "period": "quarter", "limit": 8}),
    ("fund_disclosure_holders", "funds/disclosure-holders-latest", {"symbol": SYMBOL, "limit": 20}),
    ("transcript_dates", "earning-call-transcript-dates", {"symbol": SYMBOL}),
)

SEMANTIC_ALIASES = {
    "analyst_estimates": {
        "eps_average": ("estimatedEpsAvg", "epsAvg", "epsEstimatedAvg", "epsEstimate"),
        "eps_high": ("estimatedEpsHigh", "epsHigh"),
        "eps_low": ("estimatedEpsLow", "epsLow"),
        "revenue_average": ("estimatedRevenueAvg", "revenueAvg", "revenueEstimatedAvg", "revenueEstimate", "estimatedRevenue"),
        "revenue_high": ("estimatedRevenueHigh", "revenueHigh"),
        "revenue_low": ("estimatedRevenueLow", "revenueLow"),
        "eps_analyst_count": ("numberAnalystsEstimatedEps", "numberAnalystsEstimatedEPS", "numAnalystsEps", "epsAnalysts"),
        "revenue_analyst_count": ("numberAnalystEstimatedRevenue", "numberAnalystsEstimatedRevenue", "numAnalystsRevenue", "revenueAnalysts", "numAnalysts"),
        "fiscal_period_or_date": ("date", "fiscalDateEnding", "period", "fiscalYear", "calendarYear"),
    },
    "ratios": {
        "return_on_equity": ("returnOnEquity", "returnOnEquityRatio", "returnOnEquityTTM", "roe"),
        "return_on_assets": ("returnOnAssets", "returnOnAssetsRatio", "returnOnAssetsTTM", "roa"),
        "current_ratio": ("currentRatio", "currentRatioTTM"),
        "gross_margin": ("grossProfitMargin", "grossProfitMarginTTM", "grossProfitRatio"),
        "operating_margin": ("operatingProfitMargin", "operatingProfitMarginTTM", "operatingIncomeRatio"),
        "net_margin": ("netProfitMargin", "netProfitMarginTTM", "netIncomeRatio"),
        "debt_to_equity": ("debtEquityRatio", "debtToEquity", "debtToEquityRatio"),
    },
    "fund_disclosure_holders": {
        "holder_or_fund_identity": ("holder", "holderName", "name", "fundName", "entityName", "cik"),
        "security_identity": ("symbol", "asset", "securityName", "securityCusip", "cusip", "isin"),
        "shares": ("shares", "sharesNumber", "numberOfShares"),
        "weight": ("weight", "weightPercentage", "portfolioWeight"),
        "value": ("marketValue", "value", "reportedValue"),
        "reporting_date": ("date", "reportingDate", "filingDate", "acceptedDate", "calendarYear", "quarter"),
    },
    "transcript_dates": {
        "date": ("date", "publishedDate", "transcriptDate"),
        "quarter": ("quarter", "fiscalQuarter"),
        "year": ("year", "fiscalYear", "calendarYear"),
        "symbol_or_identifier": ("symbol", "ticker", "cik", "id"),
    },
}

DATE_FIELD_TOKENS = ("date", "time", "year", "quarter", "period", "filed", "accepted")
TRANSCRIPT_CONTENT_FIELDS = ("content", "transcript", "text")
TRANSCRIPT_SPEAKER_FIELDS = ("speaker", "name", "title", "role")


class RequestBudget:
    def __init__(self, cap: int = REQUEST_CAP) -> None:
        self.cap = min(max(int(cap), 1), REQUEST_CAP)
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.cap:
            raise RuntimeError("REQUEST_CAP_REACHED")
        self.used += 1


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "items", "transcript"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        return [payload]
    return []


def _primitive_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number" if math.isfinite(value) else "non_finite_number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "other"


def _field_types(rows: list[Mapping[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, set[str]] = {}
    for row in rows:
        for field, value in row.items():
            result.setdefault(str(field), set()).add(_primitive_type(value))
    return {field: sorted(types) for field, types in sorted(result.items())}


def _presence(rows: list[Mapping[str, Any]], family: str) -> dict[str, dict[str, Any]]:
    fields = {str(field) for row in rows for field in row}
    return {
        semantic: {
            "present": any(alias in fields for alias in aliases),
            "matching_field_names": sorted(alias for alias in aliases if alias in fields),
        }
        for semantic, aliases in SEMANTIC_ALIASES.get(family, {}).items()
    }


def _request(path: str, params: Mapping[str, Any], key: str, budget: RequestBudget) -> tuple[int | None, Any, str | None]:
    budget.consume()
    request = Request(
        f"{BASE_URL}/{path}?{urlencode({**dict(params), 'apikey': key})}",
        headers={"User-Agent": "Atlas-FMP-Phase2B-Sanitized-Probe/1.0"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = int(response.status)
            body = response.read()
        try:
            return status, json.loads(body), None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return status, None, "NON_JSON_RESPONSE"
    except HTTPError as exc:
        return int(exc.code), None, "HTTP_ERROR"
    except (URLError, TimeoutError, socket.timeout):
        return None, None, "TIMEOUT_OR_NETWORK"
    except Exception:
        return None, None, "UNEXPECTED_ERROR"


def summarize_schema(family: str, status: int | None, payload: Any, error: str | None) -> dict[str, Any]:
    rows = _rows(payload)
    field_types = _field_types(rows)
    return {
        "endpoint_family": family,
        "symbol": SYMBOL,
        "provider_outcome": error or ("HTTP_SUCCESS" if status is not None and 200 <= status < 300 else "HTTP_FAILURE"),
        "http_status": status,
        "authorized": bool(status is not None and 200 <= status < 300),
        "schema_type": "LIST" if isinstance(payload, list) else "OBJECT" if isinstance(payload, Mapping) else "NONE",
        "row_count": len(rows),
        "top_level_field_names": list(field_types),
        "primitive_types_by_field": field_types,
        "date_or_period_field_names": [field for field in field_types if any(token in field.lower() for token in DATE_FIELD_TOKENS)],
        "semantic_field_presence": _presence(rows, family),
    }


def _int_value(row: Mapping[str, Any], aliases: tuple[str, ...]) -> int | None:
    for alias in aliases:
        try:
            value = int(row.get(alias))
        except (TypeError, ValueError):
            continue
        return value
    return None


def latest_transcript_period(payload: Any) -> tuple[int, int] | None:
    periods: list[tuple[int, int]] = []
    max_year = datetime.now(timezone.utc).year + 1
    for row in _rows(payload):
        year = _int_value(row, ("year", "fiscalYear", "calendarYear"))
        quarter = _int_value(row, ("quarter", "fiscalQuarter"))
        if year is not None and quarter is not None and 1900 <= year <= max_year and quarter in {1, 2, 3, 4}:
            periods.append((year, quarter))
    return max(periods) if periods else None


def historical_period_metadata(payload: Any) -> dict[str, Any]:
    periods = set()
    for row in _rows(payload):
        year = _int_value(row, ("year", "fiscalYear", "calendarYear"))
        quarter = _int_value(row, ("quarter", "fiscalQuarter"))
        if year is not None and quarter in {1, 2, 3, 4}:
            periods.add((year, quarter))
    return {
        "distinct_addressable_period_count": len(periods),
        "multiple_historical_quarters_appear_addressable": len(periods) > 1,
    }


def summarize_transcript(status: int | None, payload: Any, error: str | None) -> dict[str, Any]:
    rows = _rows(payload)
    fields = {str(field) for row in rows for field in row}
    total_chars = 0
    content_rows = 0
    for row in rows:
        row_has_content = False
        for field in TRANSCRIPT_CONTENT_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and value:
                total_chars += len(value)
                row_has_content = True
        if row_has_content:
            content_rows += 1
    return {
        "endpoint_family": "transcript_content",
        "symbol": SYMBOL,
        "provider_outcome": error or ("HTTP_SUCCESS" if status is not None and 200 <= status < 300 else "HTTP_FAILURE"),
        "http_status": status,
        "authorized": bool(status is not None and 200 <= status < 300),
        "schema_type": "LIST" if isinstance(payload, list) else "OBJECT" if isinstance(payload, Mapping) else "NONE",
        "row_or_segment_count": len(rows),
        "content_present": content_rows > 0,
        "content_row_or_segment_count": content_rows,
        "speaker_information_present": any(field in fields for field in TRANSCRIPT_SPEAKER_FIELDS),
        "date_present": any(field in fields for field in ("date", "publishedDate", "transcriptDate")),
        "year_present": any(field in fields for field in ("year", "fiscalYear", "calendarYear")),
        "quarter_present": any(field in fields for field in ("quarter", "fiscalQuarter")),
        "approximate_total_character_count": total_chars,
    }


def run(output_path: Path = OUTPUT_PATH) -> int:
    key = os.getenv("FMP_API_KEY", "").strip()
    budget = RequestBudget()
    schema_results: list[dict[str, Any]] = []

    if not key:
        output_path.write_text(json.dumps({
            "schema_version": "ATLAS_FMP_PHASE2B_SCHEMA_PROBE_V1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbol": SYMBOL,
            "request_cap": REQUEST_CAP,
            "requests_used": 0,
            "credential_configured": False,
            "schema_results": [],
            "transcript_result": {"provider_outcome": "NOT_TESTED_CREDENTIAL_NOT_CONFIGURED"},
        }, indent=2, sort_keys=True), encoding="utf-8")
        return 2

    transcript_dates_payload: Any = None
    for family, path, params in FIXED_REQUESTS:
        status, payload, error = _request(path, params, key, budget)
        schema_results.append(summarize_schema(family, status, payload, error))
        if family == "transcript_dates":
            transcript_dates_payload = payload

    period = latest_transcript_period(transcript_dates_payload)
    history = historical_period_metadata(transcript_dates_payload)
    if period is not None:
        year, quarter = period
        status, payload, error = _request(
            "earning-call-transcript",
            {"symbol": SYMBOL, "year": year, "quarter": quarter},
            key,
            budget,
        )
        transcript_result = summarize_transcript(status, payload, error)
        transcript_result["period_mapping_source"] = "LATEST_VALID_YEAR_QUARTER_FROM_TRANSCRIPT_DATES"
    else:
        transcript_result = {
            "endpoint_family": "transcript_content",
            "symbol": SYMBOL,
            "provider_outcome": "NOT_TESTED_NO_VALID_TRANSCRIPT_PERIOD",
            "http_status": None,
            "authorized": False,
            "schema_type": "NONE",
            "row_or_segment_count": 0,
            "content_present": False,
            "content_row_or_segment_count": 0,
            "speaker_information_present": False,
            "date_present": False,
            "year_present": False,
            "quarter_present": False,
            "approximate_total_character_count": 0,
            "period_mapping_source": "NO_VALID_YEAR_QUARTER_NO_REQUEST",
        }

    summary = {
        "schema_version": "ATLAS_FMP_PHASE2B_SCHEMA_PROBE_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": SYMBOL,
        "request_cap": REQUEST_CAP,
        "requests_used": budget.used,
        "credential_configured": True,
        "schema_results": schema_results,
        "transcript_date_conclusion": history,
        "transcript_result": transcript_result,
    }
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "kind": "phase2b_probe_complete",
        "requests_used": budget.used,
        "request_cap": REQUEST_CAP,
        "schema_result_count": len(schema_results),
        "transcript_request_made": period is not None,
        "output": output_path.name,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
