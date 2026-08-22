"""Sanitized, bounded FMP Phase 2A entitlement probe.

This module is for a manual GitHub Actions diagnostic only. It emits an
allowlisted metadata summary and never persists provider payloads, request
URLs, credentials, transcript text, article text, or financial values.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://financialmodelingprep.com/stable"
SYMBOLS = ("NVDA", "AAPL", "SPY")
REQUEST_CAP = 25
TIMEOUT_SECONDS = 12.0
OUTPUT_PATH = Path("fmp_entitlement_probe_summary.json")

CLASSIFICATIONS = {
    "PROVEN_AVAILABLE_AND_PLUMBED",
    "PROVEN_AVAILABLE_NOT_PLUMBED",
    "PROVEN_AVAILABLE_PARSING_GAP",
    "PROVEN_PLAN_RESTRICTION",
    "AUTHORIZED_BUT_EMPTY",
    "ENDPOINT_OR_SCHEMA_MISMATCH",
    "NOT_TESTED",
}

# Exactly 24 fixed requests. A single transcript-content request is derived
# from the documented transcript-date response, keeping the total at 25.
FIXED_PROBES = (
    # NVDA covers each corporate endpoint family once; entitlement is
    # account/endpoint based rather than symbol based.
    ("profile", "NVDA", "profile", {"symbol": "NVDA"}),
    ("income_statement", "NVDA", "income-statement", {"symbol": "NVDA", "period": "quarter", "limit": 8}),
    ("balance_sheet", "NVDA", "balance-sheet-statement", {"symbol": "NVDA", "period": "quarter", "limit": 8}),
    ("cash_flow", "NVDA", "cash-flow-statement", {"symbol": "NVDA", "period": "quarter", "limit": 8}),
    ("ratios", "NVDA", "ratios", {"symbol": "NVDA", "period": "quarter", "limit": 8}),
    ("key_metrics", "NVDA", "key-metrics", {"symbol": "NVDA", "period": "quarter", "limit": 8}),
    ("earnings", "NVDA", "earnings", {"symbol": "NVDA", "limit": 8}),
    ("analyst_estimates", "NVDA", "analyst-estimates", {"symbol": "NVDA", "period": "annual", "limit": 8}),
    ("grades_consensus", "NVDA", "grades-consensus", {"symbol": "NVDA"}),
    ("firm_grades", "NVDA", "grades", {"symbol": "NVDA", "limit": 20}),
    ("price_target_consensus", "NVDA", "price-target-consensus", {"symbol": "NVDA"}),
    ("price_target_summary", "NVDA", "price-target-summary", {"symbol": "NVDA"}),
    ("institutional_ownership", "NVDA", "institutional-ownership/symbol-positions-summary", {"symbol": "NVDA", "year": 2026, "quarter": 2}),
    ("fund_disclosure_holders", "NVDA", "funds/disclosure-holders-latest", {"symbol": "NVDA", "limit": 20}),
    ("stock_news", "NVDA", "news/stock", {"symbols": "NVDA", "limit": 10}),
    ("press_releases", "NVDA", "news/press-releases", {"symbols": "NVDA", "limit": 10}),
    ("transcript_dates", "NVDA", "earning-call-transcript-dates", {"symbol": "NVDA"}),
    # AAPL provides an independent estimate-schema check without duplicating
    # every account-level entitlement request.
    ("analyst_estimates", "AAPL", "analyst-estimates", {"symbol": "AAPL", "period": "annual", "limit": 8}),
    # SPY covers all currently documented ETF families requested by the audit.
    ("profile", "SPY", "profile", {"symbol": "SPY"}),
    ("etf_asset_exposure", "SPY", "etf/asset-exposure", {"symbol": "SPY"}),
    ("etf_profile", "SPY", "etf/info", {"symbol": "SPY"}),
    ("etf_holdings", "SPY", "etf/holdings", {"symbol": "SPY"}),
    ("etf_sector_weights", "SPY", "etf/sector-weightings", {"symbol": "SPY"}),
    ("etf_country_weights", "SPY", "etf/country-weightings", {"symbol": "SPY"}),
)

EXPECTED_FIELDS = {
    "profile": ({"symbol", "companyName", "price", "exchange"},),
    "income_statement": ({"date", "revenue", "operatingIncome", "eps"},),
    "balance_sheet": ({"date", "cashAndCashEquivalents", "totalDebt", "totalAssets"},),
    "cash_flow": ({"date", "operatingCashFlow", "freeCashFlow"},),
    "ratios": ({"date", "operatingProfitMargin", "returnOnEquity"},),
    "key_metrics": ({"date", "enterpriseValue", "returnOnInvestedCapital"},),
    "earnings": ({"date", "epsActual", "epsEstimated"},),
    "analyst_estimates": ({"date", "estimatedEpsAvg", "estimatedRevenueAvg"},),
    "grades_consensus": ({"strongBuy", "buy", "hold", "sell"},),
    "firm_grades": ({"date", "gradingCompany", "newGrade"},),
    "price_target_consensus": ({"targetHigh", "targetLow", "targetConsensus"},),
    "price_target_summary": ({"lastMonthAvgPriceTarget", "lastQuarterAvgPriceTarget"},),
    "institutional_ownership": ({"symbol", "investorsHolding", "ownershipPercent"},),
    "fund_disclosure_holders": ({"symbol", "holder", "shares"}, {"symbol", "name", "shares"}),
    "stock_news": ({"symbol", "publishedDate", "title", "url"},),
    "press_releases": ({"symbol", "date", "title", "url"}, {"symbol", "publishedDate", "title", "url"}),
    "transcript_dates": ({"date", "year", "quarter"}, {"symbol", "year", "quarter"}),
    "transcript_content": ({"symbol", "year", "quarter", "content"},),
    "etf_asset_exposure": ({"symbol", "weightPercentage"}, {"etfSymbol", "weightPercentage"}),
    "etf_profile": ({"symbol", "expenseRatio", "assetsUnderManagement"}, {"symbol", "expenseRatio", "aum"}),
    "etf_holdings": ({"asset", "weightPercentage"}, {"symbol", "weightPercentage"}),
    "etf_sector_weights": ({"sector", "weightPercentage"},),
    "etf_country_weights": ({"country", "weightPercentage"},),
}

ATLAS_STATUS = {
    "profile": "PRODUCTION_NORMALIZED_PERSISTED_CONSUMED",
    "income_statement": "PRODUCTION_NORMALIZED_PERSISTED_CONSUMED",
    "balance_sheet": "PRODUCTION_NORMALIZED_PERSISTED_CONSUMED",
    "cash_flow": "PRODUCTION_NORMALIZED_PERSISTED_CONSUMED",
    "ratios": "PRODUCTION_NORMALIZED_PERSISTED_CONSUMED",
    "key_metrics": "PRODUCTION_NORMALIZED_PERSISTED_CONSUMED",
    "earnings": "PRODUCTION_NORMALIZED_PERSISTED_CONSUMED",
    "analyst_estimates": "EXPLICIT_RESEARCH_ONLY_NOT_PERSISTED",
    "grades_consensus": "EXPLICIT_RESEARCH_ONLY_NOT_PERSISTED",
    "firm_grades": "EXPLICIT_RESEARCH_ONLY_NOT_PERSISTED",
    "price_target_consensus": "EXPLICIT_RESEARCH_ONLY_NOT_PERSISTED",
    "price_target_summary": "EXPLICIT_RESEARCH_ONLY_NOT_PERSISTED",
    "institutional_ownership": "EXPLICIT_RESEARCH_ONLY_NOT_PERSISTED",
    "fund_disclosure_holders": "EXPLICIT_RESEARCH_ONLY_NOT_PERSISTED",
    "stock_news": "EXPLICIT_RESEARCH_ONLY_NOT_PHASE9B_PERSISTED",
    "press_releases": "EXPLICIT_RESEARCH_ONLY_NOT_PHASE9B_PERSISTED",
    "transcript_dates": "FETCHED_EXPLICITLY_NOT_CANONICALLY_NORMALIZED",
    "transcript_content": "NOT_IMPLEMENTED_IN_ATLAS",
    "etf_asset_exposure": "EXPLICIT_RESEARCH_ONLY_NOT_ETF_HOLDINGS",
    "etf_profile": "NOT_IMPLEMENTED_IN_ATLAS",
    "etf_holdings": "NOT_IMPLEMENTED_IN_ATLAS",
    "etf_sector_weights": "NOT_IMPLEMENTED_IN_ATLAS",
    "etf_country_weights": "NOT_IMPLEMENTED_IN_ATLAS",
}


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
        for name in ("data", "results", "items", "holdings"):
            if isinstance(payload.get(name), list):
                return [row for row in payload[name] if isinstance(row, Mapping)]
        return [payload]
    return []


def _request(path: str, params: Mapping[str, Any], key: str, budget: RequestBudget) -> tuple[int | None, Any, str | None]:
    budget.consume()
    request_params = {**dict(params), "apikey": key}
    request = Request(
        f"{BASE_URL}/{path}?{urlencode(request_params)}",
        headers={"User-Agent": "Atlas-FMP-Phase2A-Sanitized-Probe/1.0"},
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


def _presence(rows: list[Mapping[str, Any]], family: str) -> dict[str, bool]:
    aliases = EXPECTED_FIELDS.get(family, ())
    all_fields = {str(field) for row in rows for field in row}
    flags: dict[str, bool] = {}
    for group in aliases:
        for field in sorted(group):
            flags[field] = field in all_fields
    return flags


def _normalizer_success(family: str, rows: list[Mapping[str, Any]]) -> bool:
    alternatives = EXPECTED_FIELDS.get(family, ())
    if not rows or not alternatives:
        return False
    fields = {str(field) for row in rows for field in row}
    return any(all(field in fields for field in group) for group in alternatives)


def _classification(status: int | None, rows: list[Mapping[str, Any]], family: str) -> str:
    if status in {401, 402, 403}:
        return "PROVEN_PLAN_RESTRICTION"
    if status is None or not 200 <= status < 300:
        return "ENDPOINT_OR_SCHEMA_MISMATCH"
    if not rows:
        return "AUTHORIZED_BUT_EMPTY"
    understood = _normalizer_success(family, rows)
    atlas = ATLAS_STATUS.get(family, "NOT_IMPLEMENTED_IN_ATLAS")
    if not understood:
        return "PROVEN_AVAILABLE_PARSING_GAP"
    if atlas.startswith("PRODUCTION_NORMALIZED"):
        return "PROVEN_AVAILABLE_AND_PLUMBED"
    return "PROVEN_AVAILABLE_NOT_PLUMBED"


def summarize(family: str, symbol: str, status: int | None, payload: Any, error: str | None) -> dict[str, Any]:
    rows = _rows(payload)
    fields = {str(field) for row in rows for field in row}
    date_present = any(any(token in field.lower() for token in ("date", "time", "year", "quarter", "filed", "accepted")) for field in fields)
    source_present = any(any(token in field.lower() for token in ("source", "site", "publisher", "url")) for field in fields)
    return {
        "endpoint_family": family,
        "symbol": symbol,
        "provider_outcome": error or ("HTTP_SUCCESS" if status is not None and 200 <= status < 300 else "HTTP_FAILURE"),
        "http_status": status,
        "entitlement_classification": _classification(status, rows, family),
        "schema_type": "LIST" if isinstance(payload, list) else "OBJECT" if isinstance(payload, Mapping) else "NONE",
        "row_count": len(rows),
        "semantic_field_presence": _presence(rows, family),
        "date_or_period_fields_present": date_present,
        "provenance_fields_present": source_present,
        "atlas_implementation_status": ATLAS_STATUS.get(family, "NOT_IMPLEMENTED_IN_ATLAS"),
        "existing_normalizer_success": _normalizer_success(family, rows),
    }


def _latest_transcript_period(payload: Any) -> tuple[int, int] | None:
    candidates: list[tuple[int, int]] = []
    for row in _rows(payload):
        try:
            year = int(row.get("year"))
            quarter = int(row.get("quarter"))
        except (TypeError, ValueError):
            continue
        if 1900 <= year <= datetime.now(timezone.utc).year + 1 and quarter in {1, 2, 3, 4}:
            candidates.append((year, quarter))
    return max(candidates) if candidates else None


def run(output_path: Path = OUTPUT_PATH) -> int:
    key = os.getenv("FMP_API_KEY", "").strip()
    budget = RequestBudget()
    results: list[dict[str, Any]] = []
    transcript_period: tuple[int, int] | None = None

    if not key:
        summary = {
            "schema_version": "ATLAS_FMP_ENTITLEMENT_PROBE_V1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbols": list(SYMBOLS),
            "request_cap": REQUEST_CAP,
            "requests_used": 0,
            "credential_configured": False,
            "results": [],
            "conclusions": {"probe_status": "CREDENTIAL_NOT_CONFIGURED"},
        }
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return 2

    for family, symbol, path, params in FIXED_PROBES:
        status, payload, error = _request(path, params, key, budget)
        results.append(summarize(family, symbol, status, payload, error))
        if family == "transcript_dates" and symbol == "NVDA":
            transcript_period = _latest_transcript_period(payload)

    if transcript_period and budget.used < budget.cap:
        year, quarter = transcript_period
        status, payload, error = _request(
            "earning-call-transcript",
            {"symbol": "NVDA", "year": year, "quarter": quarter},
            key,
            budget,
        )
        results.append(summarize("transcript_content", "NVDA", status, payload, error))
    else:
        results.append({
            "endpoint_family": "transcript_content",
            "symbol": "NVDA",
            "provider_outcome": "NOT_TESTED_NO_VALID_DOCUMENTED_PERIOD",
            "http_status": None,
            "entitlement_classification": "NOT_TESTED",
            "schema_type": "NONE",
            "row_count": 0,
            "semantic_field_presence": {},
            "date_or_period_fields_present": False,
            "provenance_fields_present": False,
            "atlas_implementation_status": ATLAS_STATUS["transcript_content"],
            "existing_normalizer_success": False,
        })

    by_family = {item["endpoint_family"]: item["entitlement_classification"] for item in results}
    summary = {
        "schema_version": "ATLAS_FMP_ENTITLEMENT_PROBE_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": list(SYMBOLS),
        "request_cap": REQUEST_CAP,
        "requests_used": budget.used,
        "credential_configured": True,
        "results": results,
        "conclusions": {
            "transcript_content": by_family.get("transcript_content", "NOT_TESTED"),
            "historical_transcripts": "NOT_TESTED",
            "company_news": by_family.get("stock_news", "NOT_TESTED"),
            "press_releases": by_family.get("press_releases", "NOT_TESTED"),
            "analyst_consensus": by_family.get("grades_consensus", "NOT_TESTED"),
            "price_targets": by_family.get("price_target_consensus", "NOT_TESTED"),
            "firm_actions": by_family.get("firm_grades", "NOT_TESTED"),
            "current_estimates": by_family.get("analyst_estimates", "NOT_TESTED"),
            "institutional_ownership": by_family.get("institutional_ownership", "NOT_TESTED"),
            "etf_holdings": by_family.get("etf_holdings", "NOT_TESTED"),
            "etf_profile": by_family.get("etf_profile", "NOT_TESTED"),
        },
    }
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "kind": "probe_complete",
        "request_cap": REQUEST_CAP,
        "requests_used": budget.used,
        "result_count": len(results),
        "output": output_path.name,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
