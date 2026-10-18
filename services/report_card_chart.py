"""Deterministic, non-scoring Report Card chart projection."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Iterable, Mapping

MIN_LEVEL_BARS = 20
RANGE_DAYS = {"1M": 31, "3M": 93, "6M": 186, "1Y": 366, "5Y": 1830}


def _timestamp(value: Any) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def normalize_price_history(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate, order and deduplicate completed EOD bars; never fills missing values."""
    by_day: dict[str, dict[str, Any]] = {}
    for row in rows:
        ts = _timestamp(row.get("timestamp") or row.get("date") or row.get("t"))
        # A missing completion flag is not proof of a finalized exchange
        # session.  The chart is permitted to omit an unverifiable bar, but it
        # must never display it as completed market history.
        if ts is None or row.get("completed") is not True:
            continue
        try:
            close = float(row.get("adjusted_close", row.get("close", row.get("c"))))
            high = float(row.get("high", row.get("h", close)))
            low = float(row.get("low", row.get("l", close)))
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(x) for x in (close, high, low)) or min(close, high, low) <= 0 or low > high or not (low <= close <= high):
            continue
        volume = row.get("volume", row.get("v"))
        if volume not in (None, ""):
            try:
                volume = float(volume)
            except (TypeError, ValueError):
                volume = None
            if volume is not None and (not math.isfinite(volume) or volume < 0):
                volume = None
        else:
            volume = None
        open_value = row.get("open", row.get("o"))
        if open_value not in (None, ""):
            try:
                open_value = float(open_value)
            except (TypeError, ValueError):
                open_value = None
            if (open_value is not None and
                    (not math.isfinite(open_value) or open_value <= 0 or not low <= open_value <= high)):
                open_value = None
        else:
            open_value = None
        day = ts.astimezone(timezone.utc).date().isoformat()
        if day in by_day:
            raise ValueError(f"DUPLICATE_CHART_SESSION:{day}")
        by_day[day] = {"date": day, "open": open_value, "close": close, "high": high, "low": low,
                       "volume": volume}
    return [by_day[key] for key in sorted(by_day)]


def slice_timeframe(rows: list[dict[str, Any]], timeframe: str) -> list[dict[str, Any]]:
    if not rows or timeframe not in RANGE_DAYS:
        return list(rows)
    latest = datetime.fromisoformat(rows[-1]["date"]).date()
    cutoff = latest.toordinal() - RANGE_DAYS[timeframe]
    return [row for row in rows if datetime.fromisoformat(row["date"]).date().toordinal() >= cutoff]


def _linear_trend(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(rows) < MIN_LEVEL_BARS:
        return None
    ys = [row["close"] for row in rows]
    n = len(ys)
    x_mean = (n - 1) / 2
    y_mean = sum(ys) / n
    denominator = sum((x - x_mean) ** 2 for x in range(n))
    slope = sum((x - x_mean) * (y - y_mean) for x, y in enumerate(ys)) / denominator
    fitted = [y_mean + slope * (x - x_mean) for x in range(n)]
    ss_total = sum((y - y_mean) ** 2 for y in ys)
    if not ss_total:
        return None
    r2 = 1 - sum((y - fit) ** 2 for y, fit in zip(ys, fitted)) / ss_total
    return {"start": fitted[0], "end": fitted[-1], "slope_per_session": slope,
            "r_squared": r2, "method": "OLS_CLOSE_BY_SESSION"}


def _normalized_spy(stock: list[dict[str, Any]], spy: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stock_days = {row["date"] for row in stock}
    aligned = [row for row in spy if row["date"] in stock_days]
    if len(aligned) < MIN_LEVEL_BARS:
        return []
    base = aligned[0]["close"]
    return [{"date": row["date"], "indexed_close": row["close"] / base * 100.0} for row in aligned]


def _sma(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        result.append(running / window if index + 1 >= window else None)
    return result


def _ema(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (window + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def _rsi(values: list[float], window: int = 14) -> list[float | None]:
    """Wilder RSI, emitted only after a complete lookback window."""
    result: list[float | None] = [None] * len(values)
    if len(values) <= window:
        return result
    gains = [max(values[index] - values[index - 1], 0.0) for index in range(1, len(values))]
    losses = [max(values[index - 1] - values[index], 0.0) for index in range(1, len(values))]
    average_gain = sum(gains[:window]) / window
    average_loss = sum(losses[:window]) / window

    def value() -> float:
        if average_gain == 0 and average_loss == 0:
            return 50.0
        if average_loss == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + average_gain / average_loss)

    result[window] = value()
    for index in range(window + 1, len(values)):
        average_gain = (average_gain * (window - 1) + gains[index - 1]) / window
        average_loss = (average_loss * (window - 1) + losses[index - 1]) / window
        result[index] = value()
    return result


def _technical_indicators(history: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(row["close"]) for row in history]
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = [fast - slow for fast, slow in zip(ema12, ema26)]
    signal = _ema(macd, 9)
    return {
        "sma20": _sma(closes, 20),
        "sma50": _sma(closes, 50),
        "rsi14": _rsi(closes, 14),
        "macd": macd,
        "macd_signal": signal,
        "macd_histogram": [line - reference for line, reference in zip(macd, signal)],
        "methodology": {
            "sma": "Arithmetic mean of the prior 20 or 50 verified completed-session closes.",
            "rsi": "14-session Wilder RSI; unavailable until the full lookback exists.",
            "macd": "12/26-session EMA difference with a 9-session EMA signal; EMAs begin at the first verified close.",
        },
    }


def _signal_marker(signal_date: Any, signal_price: Any) -> dict[str, Any] | None:
    timestamp = _timestamp(signal_date)
    try:
        price = float(signal_price)
    except (TypeError, ValueError):
        return None
    if timestamp is None or not math.isfinite(price) or price <= 0:
        return None
    return {"date": timestamp.date().isoformat(), "price": price}


def build_chart_projection(rows: Iterable[Mapping[str, Any]], provenance: Mapping[str, Any], *,
                           signal_date: Any = None, signal_price: Any = None,
                           spy_rows: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    try:
        history = normalize_price_history(rows)
    except ValueError as exc:
        return {"status": "INVALID", "message": str(exc)}
    source = provenance.get("source") or provenance.get("provider")
    evidence = provenance.get("evidence_ids") or provenance.get("raw_evidence_id")
    if not source or not evidence:
        return {"status": "UNAVAILABLE", "message": "Price history is unavailable under the governed display contract."}
    if provenance.get("adjustment") not in {"SPLIT_ADJUSTED", "ADJUSTED", "NONE_NO_SPLITS"}:
        return {"status": "INCOMPLETE", "message": "Corporate-action adjustment provenance is incomplete."}
    if provenance.get("unhandled_split_discontinuity"):
        return {"status": "INCOMPLETE", "message": "Unhandled split discontinuity; levels omitted."}
    if len(history) < MIN_LEVEL_BARS:
        return {"status": "INCOMPLETE", "message": "Insufficient verified history for technical levels.",
                "bars": history, "bar_count": len(history)}
    recent = history[-min(60, len(history)):]
    supports = sorted(row["low"] for row in recent)
    resistances = sorted(row["high"] for row in recent)
    band = max(history[-1]["close"] * .0025, .01)
    normalized_spy = normalize_price_history(spy_rows)
    spy_comparison = _normalized_spy(history, normalized_spy)
    projection = {
        "status": "AVAILABLE", "bars": history, "bar_count": len(history),
        "ranges": [label for label, sessions in {"1M": 23, "3M": 66, "6M": 132, "1Y": 260, "5Y": 1260}.items()
                   if len(history) >= sessions],
        "latest_price": history[-1]["close"], "as_of": history[-1]["date"],
        "support_zone": [max(0.0, supports[max(0, len(supports)//10-1)] - band), supports[len(supports)//10] + band],
        "resistance_zone": [resistances[-len(resistances)//10-1] - band, resistances[-len(resistances)//10] + band],
        "trendline": _linear_trend(history), "provenance": dict(provenance),
        "signal_marker": _signal_marker(signal_date, signal_price),
        "spy_comparison": spy_comparison,
        "spy_status": "AVAILABLE" if spy_comparison else "UNAVAILABLE",
        "candlestick_status": "AVAILABLE" if all(row.get("open") is not None for row in history) else "INCOMPLETE",
        "indicators": _technical_indicators(history),
        "classification": "EDUCATIONAL_NON_SCORING",
        "volume_status": "AVAILABLE" if all(row.get("volume") is not None for row in history) else "INCOMPLETE_NON_SCORING",
        "methodology": "Zones use the 10th/90th percentiles of verified 60-session lows/highs; trend is OLS close by session.",
    }
    return projection


__all__ = ["build_chart_projection", "normalize_price_history", "slice_timeframe"]
