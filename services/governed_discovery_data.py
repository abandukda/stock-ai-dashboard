"""Governed Twelve discovery inputs: reference listings and daily OHLCV.

This module is deliberately limited to acquisition and normalization.  It does
not score, rank, value, or map an Action.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
import os
import re

import pandas as pd
import requests

from services.live_market.twelve_data_phase1 import REST_BASE, load_twelve_data_setting


PROVIDER_POLICY_VERSION = "GOVERNED_DISCOVERY_INPUTS_V3_TWELVE_ONLY"
SUPPORTED_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "NYSE AMERICAN", "ARCA", "BATS"}
OTC_EXCHANGES = {"OTC", "OTCQX", "OTCQB", "OTC PINK", "PINK", "GREY", "GREY MARKET"}
CLASS_SHARE_ROOTS = {"BRK", "BF", "BH"}
_US_EXCHANGE_ALIASES = {
    "NASDAQ": "NASDAQ", "NASDAQ GLOBAL SELECT": "NASDAQ", "NASDAQ GLOBAL MARKET": "NASDAQ",
    "NASDAQ CAPITAL MARKET": "NASDAQ", "NASDAQGS": "NASDAQ", "NASDAQGM": "NASDAQ", "NASDAQCM": "NASDAQ",
    "XNAS": "NASDAQ", "NYSE": "NYSE", "NEW YORK STOCK EXCHANGE": "NYSE", "NYQ": "NYSE", "XNYS": "NYSE",
    "NYSE AMERICAN": "NYSE AMERICAN", "NYSE MKT": "NYSE AMERICAN", "AMERICAN STOCK EXCHANGE": "NYSE AMERICAN",
    "AMEX": "AMEX", "XASE": "AMEX", "ARCA": "ARCA", "NYSE ARCA": "ARCA", "ARCX": "ARCA",
    "BATS": "BATS", "CBOE": "BATS", "CBOE BZX": "BATS", "BZX": "BATS", "BATS GLOBAL MARKETS": "BATS",
}
_FOREIGN_EXCHANGE_TOKENS = {
    "HKSE", "HONG KONG", "LSE", "LONDON", "JPX", "TOKYO", "XETRA", "FSX", "FRANKFURT",
    "TAI", "TAIWAN", "KLS", "KLSE", "BURSA MALAYSIA", "MIL", "MILAN", "EURONEXT", "TSX", "ASX",
}


def normalize_listing_exchange(row: Mapping[str, Any]) -> dict[str, str | None]:
    """Resolve a Twelve listing venue without inferring it from issuer country."""
    source = next((str(row.get(field)).strip() for field in (
        "exchangeShortName", "exchange", "exchangeFullName"
    ) if row.get(field) is not None and str(row.get(field)).strip()), "")
    upper = re.sub(r"\s+", " ", source.upper()).strip()
    if not upper:
        return {"source_exchange_value": None, "normalized_exchange": None,
                "exchange_resolution_status": "UNRESOLVED"}
    if upper in _US_EXCHANGE_ALIASES:
        return {"source_exchange_value": source, "normalized_exchange": _US_EXCHANGE_ALIASES[upper],
                "exchange_resolution_status": "RESOLVED_US"}
    if upper in OTC_EXCHANGES or upper.startswith("OTC"):
        return {"source_exchange_value": source, "normalized_exchange": upper,
                "exchange_resolution_status": "RESOLVED_OTC"}
    if any(token in upper for token in _FOREIGN_EXCHANGE_TOKENS):
        return {"source_exchange_value": source, "normalized_exchange": upper,
                "exchange_resolution_status": "RESOLVED_FOREIGN"}
    return {"source_exchange_value": source, "normalized_exchange": None,
            "exchange_resolution_status": "UNMAPPED"}


def canonical_security_ticker(symbol: str) -> str:
    """Normalize only traceable class-share punctuation; preserve all other identities."""
    value = str(symbol or "").upper().strip()
    match = re.fullmatch(r"([A-Z]{1,5})[-.]([A-Z])", value)
    return f"{match.group(1)}.{match.group(2)}" if match and match.group(1) in CLASS_SHARE_ROOTS else value


def twelve_symbol_route(symbol: str, *, exchange: str | None = None) -> dict[str, Any]:
    canonical = canonical_security_ticker(symbol)
    return {
        "canonical_ticker": canonical,
        "provider_ticker": canonical,
        "exchange": str(exchange or "").upper() or None,
        "security_identity": canonical,
        "mapping_version": "TWELVE_SYMBOL_IDENTITY_V1",
    }


def classify_listing(row: Mapping[str, Any], *, family: str) -> tuple[str, str | None]:
    """Return route and an explicit governed exclusion reason when applicable."""
    exchange_identity = normalize_listing_exchange(row)
    exchange = str(exchange_identity.get("normalized_exchange") or "")
    name = str(row.get("name") or row.get("companyName") or "").upper()
    declared = str(row.get("type") or row.get("securityType") or "").upper()
    combined = f"{declared} {name}"
    if row.get("isDelisted") is True:
        return "EXCLUDE", "DELISTED_LISTING"
    if row.get("isActivelyTrading") is False:
        return "EXCLUDE", "INACTIVE_LISTING"
    if exchange_identity["exchange_resolution_status"] == "UNRESOLVED" or exchange_identity["exchange_resolution_status"] == "UNMAPPED":
        return "EXCLUDE", "UNRESOLVED_LISTING_IDENTITY"
    if exchange_identity["exchange_resolution_status"] == "RESOLVED_OTC":
        return "EXCLUDE", "OTC_OUTSIDE_STOCK_POLICY"
    if exchange_identity["exchange_resolution_status"] != "RESOLVED_US" or exchange not in SUPPORTED_US_EXCHANGES:
        return "EXCLUDE", "NON_US_EXCHANGE_OUTSIDE_STOCK_POLICY"
    if family in {"etf-list", "etf-screener", "etf-reference"} or row.get("isEtf") is True or "EXCHANGE TRADED FUND" in combined:
        return "ETF", None
    if "WARRANT" in combined or declared in {"WARRANT", "WARRANTS"}:
        return "EXCLUDE", "WARRANT_SECURITY"
    if re.search(r"\bRIGHTS?\b", combined):
        return "EXCLUDE", "RIGHT_SECURITY"
    if re.search(r"\bUNITS?\b", combined):
        return "EXCLUDE", "UNIT_SECURITY"
    if "PREFERRED" in combined or "PREFERENCE" in combined:
        return "EXCLUDE", "PREFERRED_SECURITY"
    if "CLOSED-END" in combined or "CLOSED END" in combined:
        return "EXCLUDE", "CLOSED_END_FUND"
    if row.get("isFund") is True or declared in {"FUND", "MUTUAL FUND", "TRUST"}:
        return "EXCLUDE", "OTHER_NON_COMMON_SECURITY"
    explicitly_common = any(token in combined for token in (
        "COMMON STOCK", "COMMON EQUITY", "ADR", "ADS",
        "AMERICAN DEPOSITARY RECEIPT", "DEPOSITARY RECEIPT",
    ))
    if declared and not explicitly_common and declared not in {"STOCK", "EQUITY"}:
        return "EXCLUDE", "OTHER_NON_COMMON_SECURITY"
    return "STOCK", None


def _safe_provider_message(payload: Any, api_key: str) -> str | None:
    """Return a bounded provider diagnostic without leaking credentials."""
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("message") or payload.get("error") or payload.get("status")
    text = str(value).strip() if value not in (None, "") else ""
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    return text[:500] or None


def _failure_policy(http_status: int, message: str | None, *, partial: bool = False) -> tuple[str, bool]:
    text = str(message or "").lower()
    if partial:
        return "TRANSIENT_PARTIAL_RESPONSE", True
    if http_status == 429:
        return "TRANSIENT_RATE_LIMIT", True
    if http_status >= 500 or http_status == 0:
        return "TRANSIENT_PROVIDER_FAILURE", True
    if "not found" in text or "no data" in text or "symbol" in text and "invalid" in text:
        return "PERMANENT_SYMBOL_NOT_FOUND", False
    if http_status in {401, 403} or "entitlement" in text or "subscription" in text or "permission" in text:
        return "PERMANENT_ENTITLEMENT_DENIED", False
    if 400 <= http_status < 500:
        return "PERMANENT_HTTP_4XX", False
    return "TRANSIENT_PROVIDER_FAILURE", True


def _normalize_daily_values(values: Sequence[Mapping[str, Any]]) -> tuple[pd.DataFrame, int]:
    """Normalize one symbol without allowing duplicate dates to poison a batch."""
    frame = pd.DataFrame(values)
    if frame.empty or "datetime" not in frame or "close" not in frame:
        return pd.DataFrame(), 0
    frame = frame.loc[:, ~frame.columns.duplicated(keep="last")].copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["datetime"])
    duplicate_count = int(frame["datetime"].duplicated(keep=False).sum())
    frame = frame.sort_values("datetime", kind="stable")
    for name in ("open", "high", "low", "close", "volume"):
        if name in frame:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
    if duplicate_count:
        aggregations = {
            name: operation for name, operation in (
                ("open", "first"), ("high", "max"), ("low", "min"),
                ("close", "last"), ("volume", "max"),
            ) if name in frame
        }
        frame = frame.groupby("datetime", sort=True, as_index=False).agg(aggregations)
    frame = frame.set_index("datetime")
    frame = frame.rename(columns={name: name.title() for name in ("open", "high", "low", "close", "volume")})
    frame = frame.dropna(subset=["Close"])
    return frame, duplicate_count


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "items"):
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, Mapping)]
        result = payload.get("result")
        if isinstance(result, Mapping) and isinstance(result.get("list"), list):
            return [row for row in result["list"] if isinstance(row, Mapping)]
    return []


def load_governed_universe(
    *, api_key: str | None = None, get: Any = requests.get,
) -> dict[str, Any]:
    """Return the US-listed stock/ETF universe from Twelve reference data."""
    key = str(api_key if api_key is not None else load_twelve_data_setting("TWELVE_DATA_API_KEY") or "").strip()
    stock_symbols: set[str] = set()
    etf_symbols: set[str] = set()
    records: dict[str, dict[str, Any]] = {}
    exclusions: list[dict[str, Any]] = []
    mappings: dict[str, dict[str, Any]] = {}
    raw_symbols: set[str] = set()
    diagnostics: dict[str, Any] = {
        "provider": "TWELVE_DATA", "endpoint": "stocks",
        "source_strategy": "TWELVE_US_REFERENCE_DIRECTORY_V1",
        "calls": 0, "families": {},
    }
    observed_response_fields: set[str] = set()
    response_rows: list[Mapping[str, Any]] = []
    outcome = "AUTHORIZATION_OR_ENTITLEMENT_FAILURE" if not key else "NETWORK_FAILURE"
    http_status = None
    if key:
        diagnostics["calls"] = 1
        try:
            response = get(
                f"{REST_BASE}/stocks",
                params={"country": "United States", "format": "JSON", "show_plan": "false", "apikey": key},
                timeout=30,
            )
            http_status = int(getattr(response, "status_code", 0) or 0)
            payload = response.json()
            provider_error = isinstance(payload, Mapping) and str(payload.get("status") or "").lower() == "error"
            if 200 <= http_status < 300 and not provider_error:
                response_rows = _rows(payload)
                outcome = "SUCCESS" if response_rows else "AUTHORIZED_EMPTY"
            else:
                outcome = "PROVIDER_ERROR"
        except Exception:
            outcome = "TIMEOUT_OR_NETWORK_FAILURE"
    diagnostics["families"]["US_REFERENCE"] = {
        "outcome": outcome, "rows_returned": len(response_rows),
        "country_filter": "United States", "http_status": http_status,
    }
    for row in response_rows:
        observed_response_fields.update(str(field) for field in row)
        source_symbol = str(row.get("symbol") or "").upper().strip()
        symbol = canonical_security_ticker(source_symbol)
        if symbol:
            raw_symbols.add(symbol)
        exchange_identity = normalize_listing_exchange(row)
        exchange = exchange_identity.get("normalized_exchange")
        if not symbol or "/" in symbol or len(symbol) > 7:
            exclusions.append({"ticker": source_symbol, "canonical_ticker": symbol or None,
                               "reason": "INVALID_SYMBOL_IDENTITY"})
            continue
        declared_type = str(row.get("type") or row.get("securityType") or "").strip().upper()
        route, reason = classify_listing(row, family="etf-reference" if declared_type == "ETF" else "stock-reference")
        record = {
                "ticker": symbol,
                "source_ticker": source_symbol,
                "company_name": row.get("name") or row.get("companyName"),
                "exchange": exchange or None,
                **exchange_identity,
                "country": row.get("country"),
                "security_type": row.get("type") or row.get("securityType") or ("ETF" if route == "ETF" else "COMMON_STOCK"),
                "is_actively_trading": row.get("isActivelyTrading"),
                "is_delisted": row.get("isDelisted"),
                "route": route,
                "listing_source_endpoint": "stocks",
                "listing_source_country_filter": "United States",
        }
        records.setdefault(symbol, record)
        mappings[symbol] = {
                **twelve_symbol_route(symbol, exchange=exchange), "source_ticker": source_symbol,
                **exchange_identity,
                "listing_source_endpoint": "stocks",
                "listing_source_country_filter": "United States",
        }
        if reason:
            exclusions.append({**record, "reason": reason})
        elif route == "ETF":
            etf_symbols.add(symbol)
        else:
            stock_symbols.add(symbol)
    # A security can appear in both list families; the explicit ETF route wins.
    stock_symbols -= etf_symbols
    symbols = sorted(stock_symbols | etf_symbols)
    exclusion_counts: dict[str, int] = {}
    for item in exclusions:
        reason = str(item["reason"])
        exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
    stock_exchange_distribution: dict[str, int] = {}
    etf_exchange_distribution: dict[str, int] = {}
    for symbol in stock_symbols:
        exchange = str(records[symbol].get("normalized_exchange") or "UNRESOLVED")
        stock_exchange_distribution[exchange] = stock_exchange_distribution.get(exchange, 0) + 1
    for symbol in etf_symbols:
        exchange = str(records[symbol].get("normalized_exchange") or "UNRESOLVED")
        etf_exchange_distribution[exchange] = etf_exchange_distribution.get(exchange, 0) + 1
    unresolved = [item for item in exclusions if item.get("reason") == "UNRESOLVED_LISTING_IDENTITY"]
    foreign = [item for item in exclusions if item.get("reason") == "NON_US_EXCHANGE_OUTSIDE_STOCK_POLICY"]
    result = {
        "symbols": symbols,
        "stock_symbols": sorted(stock_symbols),
        "etf_symbols": sorted(etf_symbols),
        "records": records,
        "symbol_mappings": mappings,
        "exclusions": exclusions,
        "summary": {
            "raw_global_master_count": len(raw_symbols),
            "raw_universe_count": len(raw_symbols),
            "raw_returned_listing_rows": len(response_rows),
            "resolved_us_listing_count": len(stock_symbols | etf_symbols),
            "unresolved_listing_identity_count": len(unresolved),
            "foreign_listing_removed_count": len(foreign),
            "inactive_removed_count": exclusion_counts.get("INACTIVE_LISTING", 0),
            "otc_removed_count": exclusion_counts.get("OTC_OUTSIDE_STOCK_POLICY", 0),
            "non_common_removed_count": sum(exclusion_counts.get(reason, 0) for reason in (
                "WARRANT_SECURITY", "RIGHT_SECURITY", "UNIT_SECURITY", "PREFERRED_SECURITY",
                "OTHER_NON_COMMON_SECURITY", "CLOSED_END_FUND",
            )),
            "us_stock_universe_count": len(stock_symbols),
            "us_etf_universe_count": len(etf_symbols),
            "stock_exchange_distribution": stock_exchange_distribution,
            "etf_exchange_distribution": etf_exchange_distribution,
            "representative_unresolved_symbols": unresolved[:25],
            "representative_foreign_symbols": foreign[:25],
            "inactive_removed": exclusion_counts.get("INACTIVE_LISTING", 0),
            "delisted_removed": exclusion_counts.get("DELISTED_LISTING", 0),
            "otc_removed": exclusion_counts.get("OTC_OUTSIDE_STOCK_POLICY", 0),
            "warrant_removed": exclusion_counts.get("WARRANT_SECURITY", 0),
            "right_removed": exclusion_counts.get("RIGHT_SECURITY", 0),
            "unit_removed": exclusion_counts.get("UNIT_SECURITY", 0),
            "preferred_removed": exclusion_counts.get("PREFERRED_SECURITY", 0),
            "other_non_common_removed": (
                exclusion_counts.get("OTHER_NON_COMMON_SECURITY", 0)
                + exclusion_counts.get("CLOSED_END_FUND", 0)
            ),
            "investable_stock_universe_count": len(stock_symbols),
            "etf_routed_separately": len(etf_symbols),
            "exclusion_reason_counts": exclusion_counts,
        },
        "status": "AVAILABLE" if symbols else "DATA_UNAVAILABLE",
        "provider": "TWELVE_DATA",
        "policy_version": PROVIDER_POLICY_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "diagnostics": diagnostics,
    }
    result["diagnostics"]["observed_response_fields"] = sorted(observed_response_fields)
    assert_governed_stock_universe(result)
    return result


def assert_governed_stock_universe(result: Mapping[str, Any]) -> None:
    """Hard-stop before Twelve if any stock lacks an approved U.S. venue."""
    mappings = result.get("symbol_mappings") if isinstance(result.get("symbol_mappings"), Mapping) else {}
    invalid = []
    for symbol in result.get("stock_symbols") or []:
        mapping = mappings.get(symbol) if isinstance(mappings.get(symbol), Mapping) else {}
        exchange = mapping.get("normalized_exchange") or mapping.get("exchange")
        if mapping.get("exchange_resolution_status") != "RESOLVED_US" or exchange not in SUPPORTED_US_EXCHANGES:
            invalid.append({"ticker": symbol, "exchange": exchange,
                            "resolution": mapping.get("exchange_resolution_status")})
    if invalid:
        raise RuntimeError(f"GOVERNED_STOCK_EXCHANGE_ASSERTION_FAILED:{invalid[:25]}")


def fetch_twelve_daily_batch(
    symbols: Sequence[str], *, api_key: str | None = None, outputsize: int = 260,
    get: Any = requests.get,
) -> pd.DataFrame:
    """Fetch a bounded Twelve multi-symbol daily batch as ticker-first columns."""
    requested = [str(symbol).upper().strip() for symbol in symbols if str(symbol).strip()]
    key = str(api_key if api_key is not None else load_twelve_data_setting("TWELVE_DATA_API_KEY") or "").strip()
    if not requested or not key:
        return pd.DataFrame()
    response = get(
        f"{REST_BASE}/time_series",
        params={"symbol": ",".join(requested), "interval": "1day", "outputsize": outputsize,
                "order": "asc", "timezone": "UTC", "prepost": "false", "apikey": key},
        timeout=30,
    )
    http_status = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json()
    except Exception:
        payload = {}
    diagnostics: dict[str, Any] = {
        "market_history_attempted": len(requested), "market_history_success": 0,
        "market_history_unavailable": 0, "market_history_schema_failure": 0,
        "market_history_duplicate_index_failure": 0, "per_symbol": {},
        "per_symbol_records": {},
    }
    provider_message = _safe_provider_message(payload, key)
    if http_status != 200:
        failure_status, retryable = _failure_policy(http_status, provider_message)
        diagnostics["market_history_unavailable"] = len(requested)
        for symbol in requested:
            diagnostics["per_symbol"][symbol] = failure_status
            diagnostics["per_symbol_records"][symbol] = {
                "requested_twelve_symbol": symbol,
                "requested_exchange": None,
                "acquisition_status": failure_status,
                "retryable": retryable,
                "http_status": http_status or None,
                "provider_error_message": provider_message,
                "failure_stage": "HTTP_RESPONSE",
            }
        result = pd.DataFrame()
        result.attrs["governed_market_diagnostics"] = diagnostics
        return result
    bundles = payload if isinstance(payload, Mapping) else {}
    if len(requested) == 1 and isinstance(payload, Mapping) and "values" in payload:
        bundles = {requested[0]: payload}
    frames: dict[str, pd.DataFrame] = {}
    for symbol in requested:
        record = {
            "requested_twelve_symbol": symbol,
            "requested_exchange": None,
            "http_status": http_status,
            "provider_error_message": provider_message,
        }
        try:
            bundle = bundles.get(symbol) or bundles.get(symbol.replace("-", "."))
            values = bundle.get("values") if isinstance(bundle, Mapping) else None
            if not isinstance(values, list):
                diagnostics["market_history_unavailable"] += 1
                bundle_message = _safe_provider_message(bundle, key) if isinstance(bundle, Mapping) else None
                status, retryable = _failure_policy(http_status, bundle_message or provider_message, partial=len(requested) > 1 and bundle is None)
                diagnostics["per_symbol"][symbol] = status
                record.update(acquisition_status=status, retryable=retryable, failure_stage="PROVIDER_RESPONSE_MAPPING")
                if isinstance(bundle, Mapping):
                    record["provider_error_message"] = bundle_message or provider_message
                diagnostics["per_symbol_records"][symbol] = record
                continue
            frame, duplicate_count = _normalize_daily_values(values)
            if frame.empty:
                diagnostics["market_history_schema_failure"] += 1
                diagnostics["per_symbol"][symbol] = "SCHEMA_FAILURE"
                record.update(acquisition_status="SCHEMA_FAILURE", failure_stage="OHLCV_NORMALIZATION")
                record["retryable"] = False
                diagnostics["per_symbol_records"][symbol] = record
                continue
            if duplicate_count:
                diagnostics["market_history_duplicate_index_failure"] += 1
            frames[symbol] = frame
            diagnostics["market_history_success"] += 1
            diagnostics["per_symbol"][symbol] = "SUCCESS_DEDUPLICATED" if duplicate_count else "SUCCESS"
            record.update(
                acquisition_status=diagnostics["per_symbol"][symbol],
                failure_stage=None,
                provider_error_message=None,
                retryable=False,
            )
            diagnostics["per_symbol_records"][symbol] = record
        except Exception as exc:
            diagnostics["market_history_schema_failure"] += 1
            diagnostics["per_symbol"][symbol] = f"SCHEMA_FAILURE:{type(exc).__name__}"
            record.update(
                acquisition_status=diagnostics["per_symbol"][symbol],
                provider_error_message=type(exc).__name__,
                failure_stage="OHLCV_NORMALIZATION",
                retryable=False,
            )
            diagnostics["per_symbol_records"][symbol] = record
    result = pd.concat(frames, axis=1, sort=True) if frames else pd.DataFrame()
    result.attrs["governed_market_diagnostics"] = diagnostics
    return result


__all__ = [
    "PROVIDER_POLICY_VERSION", "SUPPORTED_US_EXCHANGES", "assert_governed_stock_universe",
    "canonical_security_ticker", "classify_listing", "fetch_twelve_daily_batch",
    "load_governed_universe", "normalize_listing_exchange", "twelve_symbol_route",
]
