"""Read-only live market context for Home.

This module never supplies investment inputs.  Quotes are presentation-only and
are deliberately kept separate from the persisted Atlas research timestamp.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import requests

from services.live_market.models import classify_market_session
from services.live_market.twelve_data_phase1 import (
    TwelveDataPhase1Adapter,
    build_phase1_bundle,
    load_twelve_data_setting,
)


HOME_MARKET_SYMBOLS = {
    "SPY": "S&P 500 · SPY",
    "QQQ": "Nasdaq 100 · QQQ",
    "DIA": "Dow · DIA",
    "IWM": "Russell 2000 · IWM",
}
ET = ZoneInfo("America/New_York")


def _regular_close_timestamp(value: Any) -> datetime | None:
    """Represent a completed daily bar at the U.S. regular-session close."""
    try:
        stamp = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
        if not isinstance(stamp, datetime):
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        local = stamp.astimezone(ET)
        # Twelve daily bars are date observations (normally midnight UTC), not
        # intraday ticks.  Preserve that date while presenting its completed
        # regular-session close semantics.
        bar_date = stamp.date() if stamp.hour == stamp.minute == stamp.second == 0 else local.date()
        return datetime.combine(bar_date, time(16, 0), tzinfo=ET)
    except (TypeError, ValueError, OverflowError):
        return None


def _series(frame: Any, symbol: str):
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        close = frame["Close"]
        if getattr(close, "ndim", 1) > 1:
            if symbol in close:
                close = close[symbol]
            elif len(close.columns) == 1:
                close = close.iloc[:, 0]
            else:
                return None
        close = close.dropna()
        return close if len(close) else None
    except (KeyError, TypeError, AttributeError):
        return None


def fetch_home_market_tape(
    downloader: Callable[..., Any] | None = None,
    *,
    symbols: Mapping[str, str] = HOME_MARKET_SYMBOLS,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Fetch governed market context in one batch and preserve partial failures."""
    requested = tuple(symbols)
    observed = (now or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)
    credential_available = bool(load_twelve_data_setting("TWELVE_DATA_API_KEY")) if downloader is None else True
    failure_reasons: dict[str, str] = {}
    shared_rows: list[dict[str, Any]] | None = None
    try:
        if downloader is not None:
            frame = downloader(
            list(requested), period="5d", interval="5m", progress=False,
            auto_adjust=True, threads=True, group_by="column",
            )
        else:
            if not credential_available:
                raise RuntimeError("CREDENTIAL_UNAVAILABLE")
            adapter = TwelveDataPhase1Adapter(
                load_twelve_data_setting("TWELVE_DATA_API_KEY"), enabled=True, get=requests.get,
            )
            shared_rows = []
            session = classify_market_session(observed).value
            for symbol, label in symbols.items():
                try:
                    daily = adapter.fetch_time_series(symbol, interval="1day", outputsize=260, prepost=False)
                    intraday = adapter.fetch_time_series(symbol) if session == "REGULAR" else {}
                    bundle = build_phase1_bundle(
                        symbol, websocket_event={}, time_series_payload=intraday,
                        daily_time_series_payload=daily, received_timestamp=observed, now=observed,
                    )
                    daily_bars = tuple((bundle.get("canonical_technical_history") or {}).get("bars") or ())
                    completed = dict((bundle.get("completed_bars") or {}).get("latest_completed_bar") or {})
                    latest = completed or (dict(daily_bars[-1]) if daily_bars else {})
                    previous = (
                        dict(daily_bars[-1]) if completed and daily_bars
                        else dict(daily_bars[-2]) if len(daily_bars) > 1 else {}
                    )
                    if not latest or latest.get("close") is None:
                        failure_reasons[symbol] = "NO_COMPLETED_BAR"
                        shared_rows.append({"symbol": symbol, "label": label, "status": "unavailable"})
                        continue
                    price = float(latest["close"])
                    prior = float(previous.get("close", price))
                    point_change = price - prior
                    is_live = bool(completed and session == "REGULAR")
                    latest_stamp = datetime.fromisoformat(str(latest.get("timestamp") or "").replace("Z", "+00:00"))
                    if observed - latest_stamp.astimezone(timezone.utc) > timedelta(days=7):
                        failure_reasons[symbol] = "STALE_BEYOND_POLICY"
                        shared_rows.append({"symbol": symbol, "label": label, "status": "unavailable"})
                        continue
                    source_contract = bundle.get("completed_bars") if is_live else bundle.get("canonical_technical_history")
                    shared_rows.append({
                        "symbol": symbol, "label": label, "status": "available", "price": price,
                        "previous_close": prior, "point_change": point_change,
                        "change_pct": point_change / prior * 100 if prior else None,
                        "direction": "UP" if point_change > 0 else "DOWN" if point_change < 0 else "FLAT",
                        "as_of": latest.get("timestamp"), "provider_timestamp": latest.get("timestamp"),
                        "market_session": "LIVE" if is_live else "LATEST_REGULAR_CLOSE",
                        "source": "TWELVE_DATA", "evidence_id": (source_contract or {}).get("evidence_id"),
                        "freshness_status": "CURRENT_SESSION" if is_live else "LATEST_COMPLETED_REGULAR_SESSION",
                    })
                except requests.HTTPError as exc:
                    status = getattr(exc.response, "status_code", None)
                    failure_reasons[symbol] = "RATE_LIMIT" if status == 429 else "SYMBOL_UNSUPPORTED" if status == 404 else "PROVIDER_ERROR"
                    shared_rows.append({"symbol": symbol, "label": label, "status": "unavailable"})
                except (KeyError, TypeError, ValueError):
                    failure_reasons[symbol] = "NORMALIZATION_FAILURE"
                    shared_rows.append({"symbol": symbol, "label": label, "status": "unavailable"})
                except Exception:
                    failure_reasons[symbol] = "PROVIDER_ERROR"
                    shared_rows.append({"symbol": symbol, "label": label, "status": "unavailable"})
            frame = None
        batch_error = None if credential_available else "CREDENTIAL_UNAVAILABLE"
    except Exception as exc:  # presentation data must degrade independently
        frame = None
        name = type(exc).__name__.upper()
        batch_error = "CREDENTIAL_UNAVAILABLE" if not credential_available else "RATE_LIMIT" if "RATE" in name else "PROVIDER_ERROR"

    rows = list(shared_rows or [])
    quote_times = []
    for symbol, label in (() if shared_rows is not None else symbols.items()):
        close = _series(frame, symbol)
        if close is None:
            rows.append({"symbol": symbol, "label": label, "status": "unavailable"})
            continue
        last = float(close.iloc[-1])
        previous = float(close.iloc[-2]) if len(close) > 1 else last
        stamp = None
        try:
            stamp = _regular_close_timestamp(close.index[-1])
            if stamp is not None:
                quote_times.append(stamp.astimezone(timezone.utc))
        except (AttributeError, IndexError, TypeError):
            pass
        point_change=last-previous
        as_of=stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if stamp is not None else None
        evidence_id="TD-MARKET-" + hashlib.sha256(f"{symbol}|{as_of}|{last}".encode()).hexdigest()[:20]
        rows.append({
            "symbol": symbol,
            "label": label,
            "status": "available",
            "price": last,
            "previous_close": previous,
            "point_change": point_change,
            "change_pct": ((last - previous) / previous * 100) if previous else None,
            "direction": "UP" if point_change > 0 else "DOWN" if point_change < 0 else "FLAT",
            "as_of": as_of,
            "provider_timestamp": as_of,
            "market_session": "LATEST_REGULAR_CLOSE",
            "source": "TWELVE_DATA",
            "freshness_status": "LATEST_COMPLETED_REGULAR_SESSION",
            "evidence_id": evidence_id,
        })
    for row in rows:
        stamp = row.get("provider_timestamp")
        if stamp:
            try:
                quote_times.append(datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(timezone.utc))
            except (TypeError, ValueError):
                failure_reasons[str(row.get("symbol"))] = "NORMALIZATION_FAILURE"
    available_symbols = [str(row["symbol"]) for row in rows if row.get("status") == "available"]
    unavailable_symbols = [symbol for symbol in requested if symbol not in available_symbols]
    latest_timestamp = max(quote_times).isoformat().replace("+00:00", "Z") if quote_times else None
    health = {
        "provider": "TWELVE_DATA", "credential_present": credential_available,
        "symbols_requested": list(requested), "symbols_available": available_symbols,
        "symbols_unavailable": unavailable_symbols, "latest_timestamp": latest_timestamp,
        "freshness_status": "LATEST_COMPLETED_REGULAR_SESSION" if quote_times else "TEMPORARILY_UNAVAILABLE",
        "failure_reasons": failure_reasons or ({symbol: batch_error for symbol in unavailable_symbols} if batch_error else {}),
        "last_successful_fetch_at": observed.isoformat().replace("+00:00", "Z") if quote_times else None,
    }
    return {
        "rows": rows,
        "market_data_as_of": latest_timestamp,
        "market_data_requested_at": observed.isoformat().replace("+00:00", "Z"),
        "freshness": "LATEST_COMPLETED_REGULAR_SESSION" if quote_times else "TEMPORARILY_UNAVAILABLE",
        "source": "Twelve Data",
        "requested": len(requested),
        "available": sum(row["status"] == "available" for row in rows),
        "failure_reason": batch_error if not quote_times else None,
        "batch_error": batch_error,
        "home_market_runtime_health": health,
    }


__all__ = ["HOME_MARKET_SYMBOLS", "fetch_home_market_tape"]
