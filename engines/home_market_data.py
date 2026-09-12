"""Read-only live market context for Home.

This module never supplies investment inputs.  Quotes are presentation-only and
are deliberately kept separate from the persisted Atlas research timestamp.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, time, timezone
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from services.governed_discovery_data import fetch_twelve_daily_batch
from services.live_market.twelve_data_phase1 import load_twelve_data_setting


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
    try:
        frame = (downloader(
            list(requested), period="5d", interval="5m", progress=False,
            auto_adjust=True, threads=True, group_by="column",
        ) if downloader else fetch_twelve_daily_batch(requested, outputsize=5))
        batch_error = None if credential_available else "CREDENTIAL_UNAVAILABLE"
    except Exception as exc:  # presentation data must degrade independently
        frame = None
        name = type(exc).__name__.upper()
        batch_error = "RATE_LIMIT" if "RATE" in name else "PROVIDER_ERROR"

    rows = []
    quote_times = []
    for symbol, label in symbols.items():
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
    return {
        "rows": rows,
        "market_data_as_of": max(quote_times).isoformat().replace("+00:00", "Z") if quote_times else None,
        "market_data_requested_at": observed.isoformat().replace("+00:00", "Z"),
        "freshness": "LATEST_COMPLETED_REGULAR_SESSION" if quote_times else "TEMPORARILY_UNAVAILABLE",
        "source": "Twelve Data",
        "requested": len(requested),
        "available": sum(row["status"] == "available" for row in rows),
        "failure_reason": batch_error if not quote_times else None,
        "batch_error": batch_error,
    }


__all__ = ["HOME_MARKET_SYMBOLS", "fetch_home_market_tape"]
