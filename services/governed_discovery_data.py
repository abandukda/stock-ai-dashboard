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
    if int(getattr(response, "status_code", 0) or 0) != 200:
        return pd.DataFrame()
    payload = response.json()
    bundles = payload if isinstance(payload, Mapping) else {}
    if len(requested) == 1 and isinstance(payload, Mapping) and "values" in payload:
        bundles = {requested[0]: payload}
    frames: dict[str, pd.DataFrame] = {}
    for symbol in requested:
        bundle = bundles.get(symbol) or bundles.get(symbol.replace("-", "."))
        values = bundle.get("values") if isinstance(bundle, Mapping) else None
        if not isinstance(values, list):
            continue
        frame = pd.DataFrame(values)
        if frame.empty or "close" not in frame:
            continue
        frame.index = pd.to_datetime(frame.pop("datetime"), errors="coerce", utc=True)
        frame = frame.rename(columns={name: name.title() for name in ("open", "high", "low", "close", "volume")})
        for column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frames[symbol] = frame
    return pd.concat(frames, axis=1) if frames else pd.DataFrame()


__all__ = ["PROVIDER_POLICY_VERSION", "fetch_twelve_daily_batch", "load_governed_universe"]
