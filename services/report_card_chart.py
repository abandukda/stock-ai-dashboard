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
        if ts is None or row.get("completed", True) is not True:
            continue
        try:
            close = float(row.get("adjusted_close", row.get("close", row.get("c"))))
            high = float(row.get("high", row.get("h", close)))
            low = float(row.get("low", row.get("l", close)))
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(x) for x in (close, high, low)) or min(close, high, low) <= 0 or low > high or not (low <= close <= high):
            continue
        day = ts.astimezone(timezone.utc).date().isoformat()
        if day in by_day:
            raise ValueError(f"DUPLICATE_CHART_SESSION:{day}")
        by_day[day] = {"date": day, "close": close, "high": high, "low": low,
                       "volume": row.get("volume", row.get("v"))}
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
    projection = {
        "status": "AVAILABLE", "bars": history, "bar_count": len(history),
        "ranges": [label for label, sessions in {"1M": 23, "3M": 66, "6M": 132, "1Y": 260, "5Y": 1260}.items()
                   if len(history) >= sessions],
        "latest_price": history[-1]["close"], "as_of": history[-1]["date"],
        "support_zone": [supports[max(0, len(supports)//10-1)] - band, supports[len(supports)//10] + band],
        "resistance_zone": [resistances[-len(resistances)//10-1] - band, resistances[-len(resistances)//10] + band],
        "trendline": _linear_trend(history), "provenance": dict(provenance),
        "signal_marker": {"date": str(signal_date), "price": float(signal_price)} if signal_date and signal_price else None,
        "spy_bars": normalize_price_history(spy_rows), "classification": "EDUCATIONAL_NON_SCORING",
        "volume_status": "AVAILABLE" if all(row.get("volume") is not None for row in history) else "INCOMPLETE_NON_SCORING",
        "methodology": "Zones use the 10th/90th percentiles of verified 60-session lows/highs; trend is OLS close by session.",
    }
    return projection


__all__ = ["build_chart_projection", "normalize_price_history", "slice_timeframe"]
