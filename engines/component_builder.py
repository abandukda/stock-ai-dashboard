
"""Canonical Atlas component builder.

Initial rollout: Financial and Technical are fully canonical.
Existing analyst, institutional, political, insider, risk, macro, and legacy
scores are preserved as compatibility components without fabricated defaults.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
import math
import re

from engines.component_status import (
    ComponentResult,
    ComponentStatus,
    honest_absence_summary,
)


MISSING = {
    "",
    "none",
    "null",
    "nan",
    "n/a",
    "na",
    "unknown",
    "unavailable",
    "under review",
    "not reported",
    "—",
    "-",
}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in MISSING
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return True


def _num(value: Any, default=None):
    if not _present(value):
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = (
        str(value)
        .replace("$", "")
        .replace(",", "")
        .replace("%", "")
        .replace("x", "")
        .strip()
    )
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default
    try:
        number = float(match.group(0))
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default=""):
    return str(value).strip() if _present(value) else default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sources(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        source
        for source in (
            row,
            _mapping(row.get("raw")),
            _mapping(row.get("Raw")),
            _mapping(row.get("financials")),
            _mapping(row.get("technical")),
            _mapping(row.get("ownership")),
            _mapping(row.get("institutional")),
            _mapping(row.get("political")),
        )
        if source
    ]


def _first(row: Mapping[str, Any], *keys: str, default=None):
    for source in _sources(row):
        for key in keys:
            if key in source and _present(source.get(key)):
                return source.get(key)
    return default


def _clamp(value: float, low=0.0, high=100.0) -> float:
    return max(low, min(high, value))


def _metadata(row: Mapping[str, Any], prefix: str) -> tuple[str, str, str, str]:
    source = _text(
        _first(
            row,
            f"{prefix}_source",
            "source",
            default="Current Atlas scanner payload",
        ),
        "Current Atlas scanner payload",
    )
    as_of = _text(
        _first(
            row,
            f"{prefix}_as_of",
            f"{prefix}_updated_at",
            "updated_at",
            default="",
        )
    )
    retrieval = _text(
        _first(
            row,
            f"{prefix}_retrieval_status",
            f"{prefix}_fetch_status",
            default="scanner_payload",
        ),
        "scanner_payload",
    )
    cache = _text(
        _first(
            row,
            f"{prefix}_cache_status",
            default="unknown",
        ),
        "unknown",
    )
    return source, as_of, retrieval, cache


def _financial_component(row: Mapping[str, Any]) -> ComponentResult:
    data = {
        "revenue_growth_pct": _num(
            _first(
                row,
                "Revenue Growth",
                "Revenue Growth %",
                "revenue_growth",
                "revenue_growth_pct",
                "revenueGrowth",
                "Revenue QoQ %",
            )
        ),
        "eps_growth_pct": _num(
            _first(
                row,
                "EPS Growth",
                "EPS Growth %",
                "eps_growth",
                "eps_growth_pct",
                "earningsGrowth",
            )
        ),
        "gross_margin_pct": _num(
            _first(
                row,
                "Gross Margin",
                "Gross Margin %",
                "gross_margin",
                "gross_margin_pct",
                "grossMargins",
            )
        ),
        "operating_margin_pct": _num(
            _first(
                row,
                "Operating Margin",
                "Operating Margin %",
                "operating_margin",
                "operating_margin_pct",
                "operatingMargins",
            )
        ),
        "free_cash_flow": _num(
            _first(
                row,
                "Free Cash Flow",
                "free_cash_flow",
                "freeCashFlow",
                "freeCashflow",
            )
        ),
        "current_ratio": _num(
            _first(
                row,
                "Current Ratio",
                "current_ratio",
                "currentRatio",
            )
        ),
        "roe_pct": _num(
            _first(row, "ROE", "roe", "roe_pct", "returnOnEquity")
        ),
        "roic_pct": _num(
            _first(
                row,
                "ROIC",
                "roic",
                "roic_pct",
                "returnOnInvestedCapital",
            )
        ),
        "forward_pe": _num(
            _first(row, "Forward P/E", "forward_pe", "forwardPE")
        ),
    }

    required = (
        "revenue_growth_pct",
        "eps_growth_pct",
        "operating_margin_pct",
        "free_cash_flow",
        "current_ratio",
    )
    missing = [key for key in required if data.get(key) is None]
    populated = len(required) - len(missing)

    if populated == 0:
        status = ComponentStatus.NOT_LOADED
    elif populated < len(required):
        status = ComponentStatus.PARTIAL
    else:
        status = ComponentStatus.AVAILABLE

    parts: list[float] = []
    strengths: list[str] = []
    risks: list[str] = []

    revenue = data["revenue_growth_pct"]
    if revenue is not None:
        parts.append(_clamp(50 + revenue * 1.25))
        if revenue >= 10:
            strengths.append(f"Revenue growth is {revenue:.1f}%.")
        elif revenue < 0:
            risks.append(f"Revenue is contracting by {abs(revenue):.1f}%.")

    eps = data["eps_growth_pct"]
    if eps is not None:
        parts.append(_clamp(50 + eps * 1.0))
        if eps >= 10:
            strengths.append(f"EPS growth is {eps:.1f}%.")
        elif eps < 0:
            risks.append(f"EPS is declining by {abs(eps):.1f}%.")

    operating = data["operating_margin_pct"]
    if operating is not None:
        parts.append(_clamp(35 + operating * 1.5))
        if operating >= 20:
            strengths.append(
                f"Operating margin is strong at {operating:.1f}%."
            )
        elif operating < 8:
            risks.append(
                f"Operating margin is thin at {operating:.1f}%."
            )

    fcf = data["free_cash_flow"]
    if fcf is not None:
        parts.append(72.0 if fcf > 0 else 28.0)
        if fcf > 0:
            strengths.append("Free cash flow is positive.")
        else:
            risks.append("Free cash flow is negative.")

    current_ratio = data["current_ratio"]
    if current_ratio is not None:
        parts.append(_clamp(35 + min(current_ratio, 3.0) * 18))
        if current_ratio >= 1.5:
            strengths.append(
                f"Current ratio of {current_ratio:.2f} supports liquidity."
            )
        elif current_ratio < 1:
            risks.append(
                f"Current ratio of {current_ratio:.2f} indicates tighter liquidity."
            )

    score = round(sum(parts) / len(parts), 1) if parts else None
    source, as_of, retrieval, cache = _metadata(row, "financial")

    if status in {ComponentStatus.NOT_LOADED, ComponentStatus.PARTIAL}:
        summary = honest_absence_summary("financial", status)
    else:
        summary_parts = strengths[:2] + risks[:2]
        summary = (
            "Atlas financial assessment: " + " ".join(summary_parts)
            if summary_parts
            else "Financial data are available, but no strong directional signal was identified."
        )

    return ComponentResult(
        name="financial",
        status=status,
        score=score,
        data=data,
        summary=summary,
        strengths=strengths,
        risks=risks,
        source=source,
        as_of=as_of,
        missing_fields=missing,
        retrieval_status=retrieval,
        cache_status=cache,
    )


def _technical_component(row: Mapping[str, Any]) -> ComponentResult:
    data = {
        "rsi": _num(_first(row, "RSI", "rsi")),
        "twenty_day_pct": _num(
            _first(row, "20D %", "twenty_day_pct")
        ),
        "volume_ratio": _num(
            _first(row, "Volume Ratio", "volume_ratio")
        ),
        "sma20": _num(_first(row, "SMA20", "sma20")),
        "sma50": _num(_first(row, "SMA50", "sma50")),
        "sma200": _num(_first(row, "SMA200", "sma200")),
        "price": _num(
            _first(
                row,
                "Price",
                "Current Price",
                "current_price",
                "price",
                "last_price",
            )
        ),
        "atr": _num(_first(row, "ATR", "atr")),
        "support": _num(_first(row, "Support", "support")),
        "resistance": _num(
            _first(row, "Resistance", "resistance")
        ),
    }

    required = ("rsi", "twenty_day_pct", "volume_ratio", "price")
    missing = [key for key in required if data.get(key) is None]
    populated = len(required) - len(missing)

    if populated == 0:
        status = ComponentStatus.NOT_LOADED
    elif populated < len(required):
        status = ComponentStatus.PARTIAL
    else:
        status = ComponentStatus.AVAILABLE

    parts: list[float] = []
    strengths: list[str] = []
    risks: list[str] = []

    rsi = data["rsi"]
    if rsi is not None:
        parts.append(_clamp(100 - abs(rsi - 58) * 2.2))
        if 45 <= rsi <= 68:
            strengths.append(f"RSI of {rsi:.1f} is constructive.")
        elif rsi > 75:
            risks.append(f"RSI of {rsi:.1f} indicates an extended setup.")
        elif rsi < 35:
            risks.append(f"RSI of {rsi:.1f} indicates weak momentum.")

    trend = data["twenty_day_pct"]
    if trend is not None:
        parts.append(_clamp(50 + trend * 2.0))
        if trend > 0:
            strengths.append(
                f"Twenty-day price change is positive at {trend:.1f}%."
            )
        elif trend < -5:
            risks.append(
                f"Twenty-day price change is {trend:.1f}%."
            )

    volume = data["volume_ratio"]
    if volume is not None:
        parts.append(_clamp(45 + volume * 20))
        if volume >= 1.2:
            strengths.append(
                f"Volume ratio of {volume:.2f} confirms participation."
            )
        elif volume < 0.7:
            risks.append(
                f"Volume ratio of {volume:.2f} shows weak participation."
            )

    price = data["price"]
    sma50 = data["sma50"]
    sma200 = data["sma200"]
    if price is not None and sma50 is not None:
        parts.append(70.0 if price >= sma50 else 35.0)
        if price >= sma50:
            strengths.append("Price is above the 50-day moving average.")
        else:
            risks.append("Price is below the 50-day moving average.")
    if price is not None and sma200 is not None:
        parts.append(75.0 if price >= sma200 else 30.0)
        if price >= sma200:
            strengths.append("Price is above the 200-day moving average.")
        else:
            risks.append("Price is below the 200-day moving average.")

    score = round(sum(parts) / len(parts), 1) if parts else None
    source, as_of, retrieval, cache = _metadata(row, "technical")

    if status in {ComponentStatus.NOT_LOADED, ComponentStatus.PARTIAL}:
        summary = honest_absence_summary("technical", status)
    else:
        summary_parts = strengths[:2] + risks[:2]
        summary = (
            "Atlas technical assessment: " + " ".join(summary_parts)
            if summary_parts
            else "Technical data are available, but no strong directional signal was identified."
        )

    return ComponentResult(
        name="technical",
        status=status,
        score=score,
        data=data,
        summary=summary,
        strengths=strengths,
        risks=risks,
        source=source,
        as_of=as_of,
        missing_fields=missing,
        retrieval_status=retrieval,
        cache_status=cache,
    )


def _compatibility_component(
    row: Mapping[str, Any],
    *,
    name: str,
    keys: tuple[str, ...],
    agent_name: str = "",
) -> ComponentResult:
    score = _num(_first(row, *keys))
    if score is None and agent_name:
        committee = _first(
            row,
            "AI Committee",
            "ai_committee",
            default={},
        )
        if isinstance(committee, Mapping):
            item = committee.get(agent_name)
            if isinstance(item, Mapping):
                score = _num(item.get("score"))

    status = (
        ComponentStatus.AVAILABLE
        if score is not None
        else ComponentStatus.NOT_LOADED
    )
    source, as_of, retrieval, cache = _metadata(row, name)

    summary = (
        f"Atlas received a {name.replace('_', ' ')} score of {score:.1f} "
        "from the current scanner payload."
        if score is not None
        else honest_absence_summary(name, status)
    )

    return ComponentResult(
        name=name,
        status=status,
        score=score,
        data={"score": score},
        summary=summary,
        strengths=[],
        risks=[],
        source=source,
        as_of=as_of,
        missing_fields=[] if score is not None else ["score"],
        retrieval_status=retrieval,
        cache_status=cache,
    )


def build_components(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    financial = _financial_component(row)
    technical = _technical_component(row)

    compatibility = {
        "analyst": _compatibility_component(
            row,
            name="analyst",
            keys=(
                "Analyst Support Score",
                "analyst_support_score",
                "Analyst Support",
            ),
        ),
        "institutional": _compatibility_component(
            row,
            name="institutional",
            keys=(
                "Institutional Score",
                "institutional_score",
                "smart_money_score",
            ),
            agent_name="Institutional Agent",
        ),
        "political": _compatibility_component(
            row,
            name="political",
            keys=(
                "Political Buying Score",
                "political_buying_score",
                "policymaker_disclosure_score",
                "congressional_trading_score",
                "political_score",
            ),
        ),
        "insider": _compatibility_component(
            row,
            name="insider",
            keys=("Insider Score", "insider_score"),
        ),
        "macro": _compatibility_component(
            row,
            name="macro",
            keys=("Macro Score", "macro_score"),
        ),
        "risk": _compatibility_component(
            row,
            name="risk",
            keys=("Risk Support Score", "risk_support_score"),
        ),
        "legacy_conviction": _compatibility_component(
            row,
            name="legacy_conviction",
            keys=(
                "Final Conviction",
                "conviction",
                "conviction_score",
                "ai_score",
                "score",
            ),
        ),
    }

    results = {
        "fundamentals": financial.to_dict(),
        "technical": technical.to_dict(),
        **{
            key: value.to_dict()
            for key, value in compatibility.items()
        },
    }
    return results


def component_scores(
    components: Mapping[str, Mapping[str, Any]],
) -> dict[str, float | None]:
    return {
        name: _num(component.get("score"))
        for name, component in components.items()
    }


__all__ = ["build_components", "component_scores"]
