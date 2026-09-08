"""Governed discovery inputs: FMP listings/profile and Twelve daily OHLCV.

This module is deliberately limited to acquisition and normalization.  It does
not score, rank, value, or map an Action.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
import os

import pandas as pd
import requests

from services.fmp_stable_client import FMPStableClient, SUCCESS
from services.live_market.twelve_data_phase1 import REST_BASE, load_twelve_data_setting


PROVIDER_POLICY_VERSION = "GOVERNED_DISCOVERY_INPUTS_V1"


def _safe_provider_message(payload: Any, api_key: str) -> str | None:
    """Return a bounded provider diagnostic without leaking credentials."""
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("message") or payload.get("error") or payload.get("status")
    text = str(value).strip() if value not in (None, "") else ""
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    return text[:500] or None


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
    return []


def load_governed_universe(*, fmp_key: str | None = None, client: FMPStableClient | None = None) -> dict[str, Any]:
    """Return current US equities/ETFs from FMP's governed listing endpoints."""
    key = str(fmp_key if fmp_key is not None else os.getenv("FMP_API_KEY", "")).strip()
    client = client or FMPStableClient(key, timeout_seconds=30, retries=1)
    symbols: set[str] = set()
    diagnostics: dict[str, Any] = {"provider": "FMP", "calls": 0, "families": {}}
    for family in ("stock-list", "etf-list"):
        response = client.get(family, {})
        diagnostics["calls"] += response.attempts
        diagnostics["families"][family] = response.outcome
        if response.outcome != SUCCESS:
            continue
        for row in _rows(response.payload):
            symbol = str(row.get("symbol") or "").upper().strip()
            exchange = str(row.get("exchangeShortName") or row.get("exchange") or "").upper()
            active = row.get("isActivelyTrading")
            if symbol and "." not in symbol and "/" not in symbol and len(symbol) <= 7:
                if active is not False and (not exchange or exchange in {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"}):
                    symbols.add(symbol)
    return {
        "symbols": sorted(symbols),
        "status": "AVAILABLE" if symbols else "DATA_UNAVAILABLE",
        "provider": "FMP",
        "policy_version": PROVIDER_POLICY_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "diagnostics": diagnostics,
    }


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
        diagnostics["market_history_unavailable"] = len(requested)
        for symbol in requested:
            diagnostics["per_symbol"][symbol] = "HTTP_FAILURE"
            diagnostics["per_symbol_records"][symbol] = {
                "requested_twelve_symbol": symbol,
                "requested_exchange": None,
                "acquisition_status": "HTTP_FAILURE",
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
                diagnostics["per_symbol"][symbol] = "UNAVAILABLE"
                record.update(acquisition_status="UNAVAILABLE", failure_stage="PROVIDER_RESPONSE_MAPPING")
                if isinstance(bundle, Mapping):
                    record["provider_error_message"] = _safe_provider_message(bundle, key) or provider_message
                diagnostics["per_symbol_records"][symbol] = record
                continue
            frame, duplicate_count = _normalize_daily_values(values)
            if frame.empty:
                diagnostics["market_history_schema_failure"] += 1
                diagnostics["per_symbol"][symbol] = "SCHEMA_FAILURE"
                record.update(acquisition_status="SCHEMA_FAILURE", failure_stage="OHLCV_NORMALIZATION")
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
            )
            diagnostics["per_symbol_records"][symbol] = record
        except Exception as exc:
            diagnostics["market_history_schema_failure"] += 1
            diagnostics["per_symbol"][symbol] = f"SCHEMA_FAILURE:{type(exc).__name__}"
            record.update(
                acquisition_status=diagnostics["per_symbol"][symbol],
                provider_error_message=type(exc).__name__,
                failure_stage="OHLCV_NORMALIZATION",
            )
            diagnostics["per_symbol_records"][symbol] = record
    result = pd.concat(frames, axis=1, sort=True) if frames else pd.DataFrame()
    result.attrs["governed_market_diagnostics"] = diagnostics
    return result


__all__ = ["PROVIDER_POLICY_VERSION", "fetch_twelve_daily_batch", "load_governed_universe"]
