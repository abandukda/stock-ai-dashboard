"""Atlas Morning Brief engine.

Builds a concise daily briefing from the current Atlas pipeline payload.
This initial release does not make live external API calls and does not alter
committee verdicts, rankings, confidence, or opportunity scores.
"""

from __future__ import annotations

from collections import Counter
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


def _rank_key(row: Mapping[str, Any]) -> tuple:
    return (
        VERDICT_PRIORITY.get(_text(row.get("committee_verdict")), 0),
        _num(row.get("confidence_pct"), 0) or 0,
        _num(row.get("opportunity_score"), 0) or 0,
        _num(row.get("expected_return_pct"), -999) or -999,
    )


def _market_bias(rows: list[Mapping[str, Any]]) -> tuple[str, str]:
    actionable = sum(
        row.get("committee_verdict") in {"BUY_NOW", "ACCUMULATE"}
        for row in rows
    )
    avoid = sum(
        row.get("committee_verdict") == "AVOID"
        for row in rows
    )
    monitor = sum(
        row.get("committee_verdict") == "MONITOR"
        for row in rows
    )

    if actionable >= max(3, avoid * 1.5):
        return (
            "Constructive",
            "Atlas currently sees more actionable opportunities than confirmed avoid setups.",
        )
    if avoid > actionable and avoid >= monitor:
        return (
            "Defensive",
            "Confirmed weak setups currently outnumber actionable opportunities.",
        )
    return (
        "Selective",
        "Atlas sees a mixed environment where stock selection matters more than broad risk-taking.",
    )


def _themes(rows: list[Mapping[str, Any]]) -> list[str]:
    sectors = Counter(
        _text(row.get("sector"), "Unknown")
        for row in rows
        if row.get("committee_verdict") in {"BUY_NOW", "ACCUMULATE"}
    )
    return [
        sector
        for sector, _ in sectors.most_common(4)
        if sector != "Unknown"
    ]


def build_morning_brief(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    normalized = [
        dict(row)
        for row in (rows or [])
        if isinstance(row, Mapping)
    ]
    ranked = sorted(normalized, key=_rank_key, reverse=True)

    top_opportunities = [
        row
        for row in ranked
        if row.get("committee_verdict") in {"BUY_NOW", "ACCUMULATE"}
    ][:5]

    monitor_list = [
        row
        for row in ranked
        if row.get("committee_verdict") == "MONITOR"
    ][:5]

    top_risks = sorted(
        [
            row
            for row in normalized
            if row.get("committee_verdict") == "AVOID"
        ],
        key=lambda row: (
            _num(row.get("opportunity_score"), 100) or 100,
            _num(row.get("confidence_pct"), 100) or 100,
        ),
    )[:5]

    bias, bias_reason = _market_bias(normalized)
    themes = _themes(normalized)

    buy_now_count = sum(
        row.get("committee_verdict") == "BUY_NOW"
        for row in normalized
    )
    accumulate_count = sum(
        row.get("committee_verdict") == "ACCUMULATE"
        for row in normalized
    )

    summary = (
        f"Atlas reviewed {len(normalized)} eligible opportunities. "
        f"The current research set contains {buy_now_count} Buy Now and "
        f"{accumulate_count} Accumulate ideas. "
        f"Market posture is {bias.lower()}: {bias_reason}"
    )

    return {
        "market_bias": bias,
        "market_bias_reason": bias_reason,
        "summary": summary,
        "top_themes": themes,
        "top_opportunities": top_opportunities,
        "monitor_list": monitor_list,
        "top_risks": top_risks,
        "counts": {
            "buy_now": buy_now_count,
            "accumulate": accumulate_count,
            "monitor": sum(
                row.get("committee_verdict") == "MONITOR"
                for row in normalized
            ),
            "avoid": sum(
                row.get("committee_verdict") == "AVOID"
                for row in normalized
            ),
        },
    }


__all__ = ["build_morning_brief"]
