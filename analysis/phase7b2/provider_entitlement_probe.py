"""Sanitized, bounded Phase 7B.2 provider entitlement probe.

This diagnostic is designed for a manually dispatched GitHub Actions job. It
never emits request URLs, credentials, raw payloads, or financial values. Only
allowlisted schema/depth metadata is written to stdout.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
import json
import os
import re
import socket
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TICKERS = ("NVDA", "AVGO")
OBSERVATION_DATES = (
    "2025-03-31", "2025-06-30", "2025-09-30",
    "2025-12-31", "2026-03-31", "2026-06-30",
)
DEFAULT_REQUEST_CAP = 48
DEFAULT_TIMEOUT_SECONDS = 12.0

FMP_ENDPOINTS = (
    ("analyst_estimates", "https://financialmodelingprep.com/stable/analyst-estimates", {"period": "annual", "page": 0, "limit": 100}),
    ("as_reported_income", "https://financialmodelingprep.com/stable/income-statement-as-reported", {"period": "quarter", "limit": 100}),
    ("income_statements", "https://financialmodelingprep.com/stable/income-statement", {"period": "quarter", "limit": 100}),
    ("balance_sheets", "https://financialmodelingprep.com/stable/balance-sheet-statement", {"period": "quarter", "limit": 100}),
    ("cash_flow_statements", "https://financialmodelingprep.com/stable/cash-flow-statement", {"period": "quarter", "limit": 100}),
    ("ratios", "https://financialmodelingprep.com/stable/ratios", {"period": "quarter", "limit": 100}),
    ("key_metrics", "https://financialmodelingprep.com/stable/key-metrics", {"period": "quarter", "limit": 100}),
    ("enterprise_values", "https://financialmodelingprep.com/stable/enterprise-values", {"period": "quarter", "limit": 100}),
    ("stock_peers", "https://financialmodelingprep.com/stable/stock-peers", {}),
)

DATE_NAME = re.compile(r"(?:date|time|year|period|accepted|filed|published|effective|updated|asof|vintage)", re.I)
FISCAL_NAME = re.compile(r"(?:fiscal|period|calendarYear|quarter|year)", re.I)
REVISION_NAME = re.compile(r"(?:revision|vintage|asof|as_of|effective|updated|accepted|filing|filed|published|lastModified)", re.I)
ANALYST_NAME = re.compile(r"(?:analyst|numberOfAnalysts|numAnalysts|analystCount)", re.I)
SENSITIVE_NAME = re.compile(r"(?:api.?key|token|secret|authorization|credential|password)", re.I)

DOMAIN_PATTERNS = {
    "revenue": re.compile(r"(?:^revenue$|revenueAvg|totalRevenue)", re.I),
    "operating_income_margin": re.compile(r"(?:operatingIncome|operatingMargin|operatingProfitMargin)", re.I),
    "eps": re.compile(r"(?:^eps$|estimatedEps|epsAvg|epsEstimate|epsDiluted)", re.I),
    "free_cash_flow": re.compile(r"(?:freeCashFlow|free_cash_flow)", re.I),
    "roic_key_metrics": re.compile(r"(?:returnOnInvestedCapital|roic)", re.I),
    "debt_cash": re.compile(r"(?:totalDebt|netDebt|cashAndCashEquivalents|cashAndShortTermInvestments)", re.I),
    "market_cap": re.compile(r"(?:marketCapitalization|marketCap)", re.I),
    "enterprise_value": re.compile(r"(?:enterpriseValue|enterprise_value)", re.I),
    "peer_membership": re.compile(r"(?:peer|peers|symbol)", re.I),
}


class RequestBudget:
    def __init__(self, cap: int) -> None:
        self.cap = min(max(int(cap), 1), DEFAULT_REQUEST_CAP)
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.cap:
            raise RuntimeError("REQUEST_CAP_REACHED")
        self.used += 1


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "estimates", "peers"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        return [payload]
    return []


def _safe_field_names(rows: list[Mapping[str, Any]]) -> list[str]:
    return sorted({str(key) for row in rows for key in row if not SENSITIVE_NAME.search(str(key))})


def _iso_dates(rows: list[Mapping[str, Any]], fields: list[str]) -> list[str]:
    values: list[str] = []
    for row in rows:
        for field in fields:
            value = row.get(field)
            text = str(value or "")[:32]
            match = re.search(r"\d{4}-\d{2}-\d{2}", text)
            if match:
                try:
                    datetime.fromisoformat(match.group(0))
                    values.append(match.group(0))
                except ValueError:
                    pass
    return sorted(set(values))


def _revision_evidence(rows: list[Mapping[str, Any]], fiscal_fields: list[str], revision_fields: list[str]) -> bool:
    if not fiscal_fields or not revision_fields:
        return False
    versions: dict[tuple[str, ...], set[tuple[str, ...]]] = defaultdict(set)
    for row in rows:
        fiscal = tuple(str(row.get(field)) for field in fiscal_fields)
        revision = tuple(str(row.get(field)) for field in revision_fields)
        versions[fiscal].add(revision)
    return any(len(items) > 1 for items in versions.values())


def _domain_depth(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    output: dict[str, int] = {}
    for domain, pattern in DOMAIN_PATTERNS.items():
        output[domain] = sum(
            any(pattern.search(str(key)) and value not in (None, "", [], {}) for key, value in row.items())
            for row in rows
        )
    return output


def _estimate_signature(rows: list[Mapping[str, Any]]) -> str:
    # The digest can compare responses without printing estimates or payloads.
    selected = []
    for row in rows:
        item = {
            str(key): value for key, value in row.items()
            if re.search(r"(?:eps|estimate|analyst|period|quarter|year|date)", str(key), re.I)
            and not SENSITIVE_NAME.search(str(key))
        }
        selected.append(item)
    encoded = json.dumps(selected, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _http_json(url: str, params: Mapping[str, Any], *, budget: RequestBudget, timeout: float) -> tuple[int | None, Any, str | None]:
    budget.consume()
    request = Request(f"{url}?{urlencode(dict(params))}", headers={"User-Agent": "Atlas-Phase7B2-Sanitized-Probe/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read()
        try:
            return status, json.loads(raw), None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return status, None, "NON_JSON_RESPONSE"
    except HTTPError as exc:
        return int(exc.code), None, "HTTP_ERROR"
    except (URLError, TimeoutError, socket.timeout):
        return None, None, "NETWORK_ERROR"
    except Exception:
        # Deliberately omit exception text because it can include the request URL.
        return None, None, "UNEXPECTED_ERROR"


def summarize(provider: str, family: str, ticker: str, status: int | None, payload: Any, error: str | None) -> dict[str, Any]:
    rows = _rows(payload)
    fields = _safe_field_names(rows)
    date_fields = [field for field in fields if DATE_NAME.search(field)]
    fiscal_fields = [field for field in fields if FISCAL_NAME.search(field)]
    revision_fields = [field for field in fields if REVISION_NAME.search(field)]
    analyst_fields = [field for field in fields if ANALYST_NAME.search(field)]
    dates = _iso_dates(rows, date_fields)
    revisions_preserved = _revision_evidence(rows, fiscal_fields, revision_fields)
    is_estimate = family in {"analyst_estimates", "eps_estimates"}
    statement_like = family in {"as_reported_income", "income_statements", "balance_sheets", "cash_flow_statements"}
    pit_suitable = revisions_preserved if is_estimate else (bool(revision_fields) if statement_like else False)
    return {
        "kind": "endpoint_metadata",
        "provider": provider,
        "endpoint_family": family,
        "ticker": ticker,
        "http_status": status,
        "authorized": bool(status is not None and 200 <= status < 300),
        "error_category": error,
        "row_count": len(rows),
        "earliest_date": dates[0] if dates else None,
        "latest_date": dates[-1] if dates else None,
        "date_field_names": date_fields,
        "fiscal_period_fields": fiscal_fields,
        "revision_vintage_field_names": revision_fields,
        "analyst_count_field_names": analyst_fields,
        "historical_revisions_appear_preserved": revisions_preserved,
        "observation_date_filter_tested": False,
        "observation_date_filter_effective": False,
        "point_in_time_suitable": pit_suitable,
        "domain_observation_counts": _domain_depth(rows),
    }


def _emit(value: Mapping[str, Any]) -> None:
    # Every caller constructs an allowlisted metadata object. No raw payloads
    # or request data are accepted here.
    print(json.dumps(dict(value), sort_keys=True, separators=(",", ":")))


def _observation_date_probe(
    provider: str,
    family: str,
    ticker: str,
    url: str,
    base_params: Mapping[str, Any],
    *,
    budget: RequestBudget,
    timeout: float,
) -> dict[str, Any]:
    statuses: list[int | None] = []
    signatures: list[str] = []
    row_counts: list[int] = []
    requested_date_evidence: list[bool] = []
    for date in OBSERVATION_DATES:
        params = dict(base_params)
        # Both providers are tested with an explicit observation-date request.
        # Unsupported/ignored parameters are detected by status/signature
        # equality and must not be interpreted as fiscal-period vintages.
        params["date"] = date
        status, payload, _ = _http_json(url, params, budget=budget, timeout=timeout)
        rows = _rows(payload)
        fields = _safe_field_names(rows)
        revision_fields = [field for field in fields if REVISION_NAME.search(field)]
        revision_dates = _iso_dates(rows, revision_fields)
        statuses.append(status)
        row_counts.append(len(rows))
        signatures.append(_estimate_signature(rows))
        requested_date_evidence.append(date in revision_dates)
    successful = all(status is not None and 200 <= status < 300 for status in statuses)
    distinct = len(set(signatures)) if signatures else 0
    # Different responses alone are insufficient: a provider update during the
    # probe could also alter a digest. Require an explicit revision/vintage
    # field tied to every requested observation date.
    effective = successful and distinct > 1 and all(requested_date_evidence)
    return {
        "kind": "observation_date_probe",
        "provider": provider,
        "endpoint_family": family,
        "ticker": ticker,
        "requested_observation_dates": list(OBSERVATION_DATES),
        "http_statuses": statuses,
        "row_counts": row_counts,
        "distinct_sanitized_result_signatures": distinct,
        "results_changed_across_requested_dates": distinct > 1,
        "requested_dates_confirmed_by_revision_fields": requested_date_evidence,
        "observation_date_filter_effective": effective,
        "historical_point_in_time_snapshots_proven": effective,
        "interpretation": (
            "POINT_IN_TIME_FILTER_EVIDENCE_REQUIRES_SCHEMA_REVIEW"
            if effective else "NO_PROOF_OF_HISTORICAL_ESTIMATE_VINTAGES"
        ),
    }


def run() -> int:
    fmp_key = os.getenv("FMP_API_KEY", "").strip()
    finnhub_key = os.getenv("FINNHUB_API_KEY", "").strip()
    cap = int(os.getenv("PHASE7B2_REQUEST_CAP", str(DEFAULT_REQUEST_CAP)))
    timeout = min(float(os.getenv("PHASE7B2_HTTP_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))), DEFAULT_TIMEOUT_SECONDS)
    budget = RequestBudget(cap)

    _emit({
        "kind": "probe_start",
        "tickers": list(TICKERS),
        "planned_request_count": 44,
        "hard_request_cap": budget.cap,
        "timeout_seconds": timeout,
        "fmp_credential_configured": bool(fmp_key),
        "finnhub_credential_configured": bool(finnhub_key),
    })

    try:
        for family, url, defaults in FMP_ENDPOINTS:
            for ticker in TICKERS:
                if not fmp_key:
                    _emit(summarize("FMP", family, ticker, None, None, "CREDENTIAL_NOT_CONFIGURED"))
                    continue
                params = {**defaults, "symbol": ticker, "apikey": fmp_key}
                status, payload, error = _http_json(url, params, budget=budget, timeout=timeout)
                _emit(summarize("FMP", family, ticker, status, payload, error))

        for ticker in TICKERS:
            if not finnhub_key:
                _emit(summarize("FINNHUB", "eps_estimates", ticker, None, None, "CREDENTIAL_NOT_CONFIGURED"))
                continue
            params = {"symbol": ticker, "freq": "annual", "token": finnhub_key}
            status, payload, error = _http_json(
                "https://finnhub.io/api/v1/stock/eps-estimate", params, budget=budget, timeout=timeout,
            )
            _emit(summarize("FINNHUB", "eps_estimates", ticker, status, payload, error))

        if fmp_key:
            for ticker in TICKERS:
                _emit(_observation_date_probe(
                    "FMP", "analyst_estimates", ticker,
                    "https://financialmodelingprep.com/stable/analyst-estimates",
                    {"symbol": ticker, "period": "annual", "page": 0, "limit": 100, "apikey": fmp_key},
                    budget=budget, timeout=timeout,
                ))
        if finnhub_key:
            for ticker in TICKERS:
                _emit(_observation_date_probe(
                    "FINNHUB", "eps_estimates", ticker,
                    "https://finnhub.io/api/v1/stock/eps-estimate",
                    {"symbol": ticker, "freq": "annual", "token": finnhub_key},
                    budget=budget, timeout=timeout,
                ))
    except RuntimeError as exc:
        _emit({"kind": "probe_stop", "reason": str(exc), "requests_used": budget.used, "hard_request_cap": budget.cap})
        return 2

    _emit({"kind": "probe_complete", "requests_used": budget.used, "hard_request_cap": budget.cap})
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
