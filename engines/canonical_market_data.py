
"""Canonical Atlas market-data history service.

Narrow first release:
- historical OHLCV only;
- Yahoo/yfinance primary;
- FMP historical-price-full fallback;
- 30-minute in-memory TTL;
- last-known-good fallback;
- explicit provenance.

No recommendation, opportunity, confidence, or committee logic is changed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Mapping
import os
import time

import pandas as pd
import requests
import yfinance as yf


HISTORY_TTL_SECONDS = 1800
_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_LAST_GOOD: dict[str, dict[str, Any]] = {}
_LOCK = RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_history_frame(hist: Any, ticker: str) -> pd.DataFrame:
    """Return flat single-ticker OHLCV columns."""
    if hist is None or not isinstance(hist, pd.DataFrame) or hist.empty:
        return pd.DataFrame()

    frame = hist.copy()
    symbol = str(ticker or "").upper().strip()

    if isinstance(frame.columns, pd.MultiIndex):
        sliced = None
        for level in range(frame.columns.nlevels):
            values = {
                str(value).upper()
                for value in frame.columns.get_level_values(level)
            }
            if symbol and symbol in values:
                try:
                    sliced = frame.xs(
                        symbol,
                        axis=1,
                        level=level,
                        drop_level=True,
                    )
                    break
                except Exception:
                    pass
        if isinstance(sliced, pd.DataFrame) and not sliced.empty:
            frame = sliced
        else:
            field_names = {
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "ADJ CLOSE",
                "VOLUME",
            }
            best_level = 0
            best_hits = -1
            for level in range(frame.columns.nlevels):
                values = [
                    str(value).upper()
                    for value in frame.columns.get_level_values(level)
                ]
                hits = sum(value in field_names for value in values)
                if hits > best_hits:
                    best_level = level
                    best_hits = hits
            frame.columns = [
                str(value)
                for value in frame.columns.get_level_values(best_level)
            ]

    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [
            next(
                (
                    str(part)
                    for part in column
                    if str(part).upper()
                    in {
                        "OPEN",
                        "HIGH",
                        "LOW",
                        "CLOSE",
                        "ADJ CLOSE",
                        "VOLUME",
                    }
                ),
                str(column[-1]),
            )
            for column in frame.columns
        ]
    else:
        frame.columns = [str(column) for column in frame.columns]

    aliases = {}
    for column in frame.columns:
        key = column.strip().lower().replace("_", " ")
        if key == "open":
            aliases[column] = "Open"
        elif key == "high":
            aliases[column] = "High"
        elif key == "low":
            aliases[column] = "Low"
        elif key in {"close", "closing price", "last"}:
            aliases[column] = "Close"
        elif key in {"adj close", "adjusted close"}:
            aliases[column] = "Adj Close"
        elif key == "volume":
            aliases[column] = "Volume"

    frame = frame.rename(columns=aliases)
    if "Close" not in frame.columns and "Adj Close" in frame.columns:
        frame["Close"] = frame["Adj Close"]
    frame = frame.loc[:, ~frame.columns.duplicated()]
    return frame


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty or "Close" not in frame.columns:
        return []

    output = frame.copy()
    output = output.reset_index()
    date_column = output.columns[0]

    records: list[dict[str, Any]] = []
    for _, row in output.iterrows():
        date_value = pd.to_datetime(
            row.get(date_column),
            errors="coerce",
            utc=True,
        )
        close = pd.to_numeric(
            pd.Series([row.get("Close")]),
            errors="coerce",
        ).iloc[0]
        if pd.isna(date_value) or pd.isna(close):
            continue

        def number(name: str):
            value = pd.to_numeric(
                pd.Series([row.get(name)]),
                errors="coerce",
            ).iloc[0]
            return None if pd.isna(value) else float(value)

        records.append(
            {
                "date": date_value.date().isoformat(),
                "open": number("Open"),
                "high": number("High"),
                "low": number("Low"),
                "close": float(close),
                "volume": number("Volume"),
            }
        )

    return records


def _fetch_yahoo_history(
    ticker: str,
    period: str,
    interval: str,
) -> tuple[list[dict[str, Any]], str]:
    errors = []
    try:
        raw = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
            group_by="column",
        )
        records = _frame_to_records(
            _normalize_history_frame(raw, ticker)
        )
        if records:
            return records, ""
    except Exception as exc:
        errors.append(str(exc))

    try:
        raw = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            auto_adjust=True,
        )
        records = _frame_to_records(
            _normalize_history_frame(raw, ticker)
        )
        if records:
            return records, ""
    except Exception as exc:
        errors.append(str(exc))

    return [], "; ".join(error for error in errors if error)


def _fetch_fmp_history(
    ticker: str,
    period: str,
) -> tuple[list[dict[str, Any]], str]:
    api_key = os.getenv("FMP_API_KEY", "").strip()
    if not api_key:
        return [], "FMP_API_KEY is not configured"

    days_by_period = {
        "6mo": 190,
        "1y": 370,
        "2y": 740,
        "5y": 1850,
    }
    days = days_by_period.get(period, 740)
    end = datetime.now(timezone.utc).date()
    start = end.fromordinal(max(1, end.toordinal() - days))

    try:
        response = requests.get(
            f"https://financialmodelingprep.com/api/v3/"
            f"historical-price-full/{ticker}",
            params={
                "from": start.isoformat(),
                "to": end.isoformat(),
                "apikey": api_key,
            },
            timeout=12,
        )
        if response.status_code != 200:
            return [], f"FMP returned HTTP {response.status_code}"
        payload = response.json()
        items = (
            payload.get("historical")
            if isinstance(payload, Mapping)
            else []
        )
        records = []
        for item in items or []:
            if not isinstance(item, Mapping):
                continue
            close = item.get("close")
            if close is None:
                continue
            records.append(
                {
                    "date": str(item.get("date") or ""),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": close,
                    "volume": item.get("volume"),
                }
            )
        records.sort(key=lambda item: item.get("date") or "")
        return records, ""
    except Exception as exc:
        return [], str(exc)


def _result(
    *,
    ticker: str,
    status: str,
    records: list[dict[str, Any]],
    source: str,
    provider_called: bool,
    provider_success: bool,
    mapping_success: bool,
    retrieval_status: str,
    cache_status: str,
    error: str = "",
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "status": status,
        "records": records,
        "records_found": len(records),
        "source": source,
        "as_of": _now_iso(),
        "provider_called": provider_called,
        "provider_success": provider_success,
        "mapping_success": mapping_success,
        "retrieval_status": retrieval_status,
        "cache_status": cache_status,
        "error": error,
    }


def load_price_history(
    ticker: str,
    *,
    period: str = "2y",
    interval: str = "1d",
    force_refresh: bool = False,
    yahoo_fetcher: Callable[
        [str, str, str],
        tuple[list[dict[str, Any]], str],
    ] | None = None,
    fmp_fetcher: Callable[
        [str, str],
        tuple[list[dict[str, Any]], str],
    ] | None = None,
) -> dict[str, Any]:
    """Load canonical price history with explicit provenance."""
    symbol = str(ticker or "").upper().strip()
    if not symbol:
        return _result(
            ticker="",
            status="NOT_LOADED",
            records=[],
            source="",
            provider_called=False,
            provider_success=False,
            mapping_success=False,
            retrieval_status="invalid_ticker",
            cache_status="none",
            error="Ticker is required",
        )

    cache_key = (symbol, period, interval)
    now = time.time()
    with _LOCK:
        cached = _CACHE.get(cache_key)
        if (
            cached
            and not force_refresh
            and now - cached[0] < HISTORY_TTL_SECONDS
        ):
            result = dict(cached[1])
            result["cache_status"] = "fresh"
            return result

    yahoo_fetcher = yahoo_fetcher or _fetch_yahoo_history
    fmp_fetcher = fmp_fetcher or _fetch_fmp_history

    yahoo_records, yahoo_error = yahoo_fetcher(
        symbol,
        period,
        interval,
    )
    if yahoo_records:
        result = _result(
            ticker=symbol,
            status="AVAILABLE",
            records=yahoo_records,
            source="Yahoo/yfinance",
            provider_called=True,
            provider_success=True,
            mapping_success=True,
            retrieval_status="provider_success",
            cache_status="refreshed",
        )
        with _LOCK:
            _CACHE[cache_key] = (now, result)
            _LAST_GOOD[symbol] = result
        return result

    fmp_records, fmp_error = fmp_fetcher(symbol, period)
    if fmp_records:
        result = _result(
            ticker=symbol,
            status="AVAILABLE",
            records=fmp_records,
            source="FMP historical-price-full",
            provider_called=True,
            provider_success=True,
            mapping_success=True,
            retrieval_status="fallback_success",
            cache_status="refreshed",
        )
        with _LOCK:
            _CACHE[cache_key] = (now, result)
            _LAST_GOOD[symbol] = result
        return result

    with _LOCK:
        last_good = _LAST_GOOD.get(symbol)
    if last_good:
        result = dict(last_good)
        result.update(
            {
                "status": "STALE",
                "cache_status": "last_known_good",
                "retrieval_status": "provider_error_cache_fallback",
                "error": "; ".join(
                    value
                    for value in (yahoo_error, fmp_error)
                    if value
                ),
            }
        )
        return result

    combined_error = "; ".join(
        value for value in (yahoo_error, fmp_error) if value
    )
    return _result(
        ticker=symbol,
        status="PROVIDER_ERROR",
        records=[],
        source="Yahoo/yfinance + FMP",
        provider_called=True,
        provider_success=False,
        mapping_success=False,
        retrieval_status="provider_error",
        cache_status="none",
        error=combined_error or "No history records were returned",
    )


def attach_price_history(
    row: Mapping[str, Any],
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Attach canonical history only when usable history is absent."""
    output = dict(row)
    existing = (
        output.get("price_history")
        or output.get("historical_prices")
        or output.get("chart_data")
        or output.get("historical_data")
    )
    if isinstance(existing, list) and existing:
        output["price_history"] = existing
        output["history_provenance"] = {
            "status": "AVAILABLE",
            "provider_called": False,
            "provider_success": True,
            "records_found": len(existing),
            "mapping_success": True,
            "source": "Existing Atlas row",
            "as_of": str(
                output.get("history_as_of")
                or output.get("updated_at")
                or ""
            ),
            "retrieval_status": "existing_payload",
            "cache_status": "row_payload",
            "error": "",
        }
        return output

    ticker = (
        output.get("ticker")
        or output.get("Ticker")
        or output.get("symbol")
    )
    result = load_price_history(
        str(ticker or ""),
        force_refresh=force_refresh,
    )
    output["history_provenance"] = {
        key: value
        for key, value in result.items()
        if key != "records"
    }
    if result.get("records"):
        output["price_history"] = result["records"]
    return output


__all__ = [
    "HISTORY_TTL_SECONDS",
    "attach_price_history",
    "load_price_history",
]
