
"""Atlas daily opportunities and volume intelligence.

Uses the current pipeline payload only. It does not make live provider calls.
The engine ranks actionable names and unusual-volume setups while preserving
the committee verdict as the source of truth.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping
import math


VERDICT_PRIORITY = {
    "BUY_NOW": 4,
    "ACCUMULATE": 3,
    "MONITOR": 2,
    "AVOID": 1,
}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _first(row: Mapping[str, Any], *keys: str, default=None):
    raw = row.get("raw")
    raw = raw if isinstance(raw, Mapping) else {}
    legacy = row.get("Raw")
    legacy = legacy if isinstance(legacy, Mapping) else {}
    for source in (row, raw, legacy):
        for key in keys:
            value = source.get(key)
            if value not in (None, "", "Unknown", "Unavailable", "Under review"):
                return value
    return default


def _relative_volume(row: Mapping[str, Any]) -> float | None:
    technical = row.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    return _num(
        _first(
            row,
            "volume_ratio",
            "Volume Ratio",
            "relative_volume",
            "relative_volume_ratio",
            default=technical.get("volume_ratio"),
        )
    )


def _day_change(row: Mapping[str, Any]) -> float | None:
    return _num(
        _first(
            row,
            "change_pct",
            "day_change_pct",
            "percent_change",
            "regular_market_change_percent",
            "regularMarketChangePercent",
            "1D %",
        )
    )


def _dollar_volume(row: Mapping[str, Any]) -> float | None:
    explicit = _num(
        _first(row, "dollar_volume", "Dollar Volume")
    )
    if explicit is not None:
        return explicit
    price = _num(_first(row, "current_price", "Price", "price"))
    volume = _num(_first(row, "volume", "Volume", "today_volume"))
    if price is not None and volume is not None:
        return price * volume
    return None


def _volume_label(relative_volume: float | None, change: float | None) -> str:
    if relative_volume is None:
        return "Volume under review"
    if relative_volume >= 2:
        if change is not None and change >= 2:
            return "Potential accumulation"
        if change is not None and change <= -2:
            return "Potential distribution"
        return "Unusual volume"
    if relative_volume >= 1.25:
        return "Above-average participation"
    if relative_volume < 0.75:
        return "Light participation"
    return "Normal participation"


def _summary(row: Mapping[str, Any]) -> str:
    ticker = _text(row.get("ticker"), "This stock")
    verdict = _text(row.get("committee_verdict"), "MONITOR").replace("_", " ").title()
    relative_volume = _relative_volume(row)
    change = _day_change(row)
    expected_return = _num(row.get("expected_return_pct"))
    reasons = [
        _text(item)
        for item in (row.get("positive_drivers") or [])
        if _text(item)
    ]
    cautions = [
        _text(item)
        for item in (row.get("reasons_to_wait") or [])
        if _text(item)
    ]

    parts = [f"{ticker} is currently rated {verdict}."]
    if change is not None:
        parts.append(f"The stock is {change:+.1f}% in the loaded session data.")
    if relative_volume is not None:
        parts.append(f"Relative volume is {relative_volume:.2f}× normal.")
    if expected_return is not None:
        parts.append(f"Validated expected return is {expected_return:.1f}%.")
    if reasons:
        parts.append("Primary support: " + reasons[0])
    if cautions:
        parts.append("Primary caution: " + cautions[0])
    return " ".join(parts)


def build_today_opportunities(
    rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 15,
) -> list[dict[str, Any]]:
    candidates = []
    for raw in rows or []:
        if not isinstance(raw, Mapping):
            continue
        verdict = _text(raw.get("committee_verdict"), "MONITOR")
        if verdict not in {"BUY_NOW", "ACCUMULATE", "MONITOR"}:
            continue
        item = dict(raw)
        item["daily_ai_summary"] = _summary(item)
        item["relative_volume"] = _relative_volume(item)
        item["day_change_pct"] = _day_change(item)
        item["dollar_volume"] = _dollar_volume(item)
        candidates.append(item)

    candidates.sort(
        key=lambda row: (
            VERDICT_PRIORITY.get(_text(row.get("committee_verdict")), 0),
            _num(row.get("confidence_pct"), 0) or 0,
            _num(row.get("opportunity_score"), 0) or 0,
            _num(row.get("expected_return_pct"), -999) or -999,
        ),
        reverse=True,
    )
    return candidates[: max(1, int(limit))]


def build_volume_momentum(
    rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 15,
    minimum_relative_volume: float = 1.25,
) -> list[dict[str, Any]]:
    results = []
    for raw in rows or []:
        if not isinstance(raw, Mapping):
            continue
        relative_volume = _relative_volume(raw)
        if relative_volume is None or relative_volume < minimum_relative_volume:
            continue

        item = dict(raw)
        change = _day_change(item)
        dollar_volume = _dollar_volume(item)
        item.update(
            {
                "relative_volume": relative_volume,
                "day_change_pct": change,
                "dollar_volume": dollar_volume,
                "volume_signal": _volume_label(relative_volume, change),
                "daily_ai_summary": _summary(item),
            }
        )
        results.append(item)

    results.sort(
        key=lambda row: (
            _num(row.get("relative_volume"), 0) or 0,
            _num(row.get("dollar_volume"), 0) or 0,
            VERDICT_PRIORITY.get(_text(row.get("committee_verdict")), 0),
            abs(_num(row.get("day_change_pct"), 0) or 0),
        ),
        reverse=True,
    )
    return results[: max(1, int(limit))]


__all__ = [
    "build_today_opportunities",
    "build_volume_momentum",
]
