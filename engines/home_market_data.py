"""Read-only live market context for Home.

This module never supplies investment inputs.  Quotes are presentation-only and
are deliberately kept separate from the persisted Atlas research timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping


HOME_MARKET_SYMBOLS = {
    "SPY": "S&P 500 · SPY",
    "QQQ": "Nasdaq 100 · QQQ",
    "DIA": "Dow · DIA",
    "IWM": "Russell 2000 · IWM",
    "^VIX": "VIX",
    "GC=F": "Gold",
    "CL=F": "Oil",
    "BTC-USD": "Bitcoin",
}


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
    downloader: Callable[..., Any],
    *,
    symbols: Mapping[str, str] = HOME_MARKET_SYMBOLS,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Fetch the tape in one Yahoo batch and preserve partial failures."""
    requested = tuple(symbols)
    observed = (now or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)
    try:
        frame = downloader(
            list(requested), period="5d", interval="5m", progress=False,
            auto_adjust=True, threads=True, group_by="column",
        )
        batch_error = None
    except Exception as exc:  # presentation data must degrade independently
        frame, batch_error = None, type(exc).__name__

    rows = []
    quote_times = []
    for symbol, label in symbols.items():
        close = _series(frame, symbol)
        if close is None:
            rows.append({"symbol": symbol, "label": label, "status": "unavailable"})
            continue
        last = float(close.iloc[-1])
        previous = float(close.iloc[-2]) if len(close) > 1 else last
        try:
            stamp = close.index[-1].to_pydatetime()
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            quote_times.append(stamp.astimezone(timezone.utc))
        except (AttributeError, IndexError, TypeError):
            pass
        rows.append({
            "symbol": symbol,
            "label": label,
            "status": "live",
            "price": last,
            "change_pct": ((last - previous) / previous * 100) if previous else None,
        })
    return {
        "rows": rows,
        "market_data_as_of": max(quote_times).isoformat().replace("+00:00", "Z") if quote_times else None,
        "market_data_requested_at": observed.isoformat().replace("+00:00", "Z"),
        "freshness": "delayed_or_near_real_time" if quote_times else "unavailable",
        "source": "Yahoo Finance",
        "requested": len(requested),
        "available": sum(row["status"] == "live" for row in rows),
        "batch_error": batch_error,
    }


__all__ = ["HOME_MARKET_SYMBOLS", "fetch_home_market_tape"]
