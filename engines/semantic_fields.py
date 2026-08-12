"""Read-only semantic resolution for customer-facing Atlas research fields.

The helpers in this module do not calculate scores or change investment
methodology.  They keep canonical Atlas valuation, analyst consensus,
analyst-driven scenarios, and scanner trade levels from sharing aliases.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


_MISSING = {"", "none", "null", "nan", "n/a", "na", "unknown", "unavailable", "under review", "—", "-"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def sources(row: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return tuple(source for source in (row, _mapping(row.get("raw")), _mapping(row.get("Raw"))) if source)


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in _MISSING
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return bool(value)


def first_present(row: Mapping[str, Any], *keys: str) -> Any:
    for source in sources(row):
        for key in keys:
            if key in source and present(source.get(key)):
                return source.get(key)
    return None


def number(value: Any) -> float | None:
    if not present(value) or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def canonical_atlas_fair_value(row: Mapping[str, Any]) -> float | None:
    """Resolve only fields proven to be canonical Atlas valuation output."""
    return number(first_present(row, "atlas_fair_value", "Atlas Fair Value"))


def analyst_consensus(row: Mapping[str, Any]) -> dict[str, float | None]:
    return {
        "mean": number(first_present(row, "analyst_target_mean", "Analyst Target", "targetMeanPrice")),
        "high": number(first_present(row, "analyst_target_high", "Analyst Target High", "targetHighPrice")),
        "low": number(first_present(row, "analyst_target_low", "Analyst Target Low", "targetLowPrice")),
        "count": number(first_present(row, "analyst_count", "Analyst Count", "numberOfAnalystOpinions")),
    }


def analyst_scenarios(row: Mapping[str, Any]) -> dict[str, float | None]:
    return {
        "bear": number(first_present(row, "ai_bear_target")),
        "base": number(first_present(row, "ai_base_target")),
        "bull": number(first_present(row, "ai_bull_target")),
    }


def scanner_trade_plan(row: Mapping[str, Any]) -> dict[str, float | None]:
    """Resolve explicit scanner levels, with legacy target_1/target_2 compatibility."""
    return {
        "entry_low": number(first_present(row, "preferred_entry_low", "entry_low", "Entry Low")),
        "entry_high": number(first_present(row, "preferred_entry_high", "entry_high", "Entry High")),
        "stop_loss": number(first_present(row, "stop_loss", "stop", "Stop")),
        "trade_target_1": number(first_present(row, "trade_target_1", "target_1", "Target 1")),
        "trade_target_2": number(first_present(row, "trade_target_2", "target_2", "Target 2")),
        "risk_reward": number(first_present(row, "risk_reward", "Risk/Reward")),
    }


def valuation_families(row: Mapping[str, Any]) -> dict[str, Any]:
    price = number(first_present(row, "current_price", "price", "Price", "Current Price"))
    atlas = canonical_atlas_fair_value(row)
    analysts = analyst_consensus(row)
    scenarios = analyst_scenarios(row)
    atlas_return = ((atlas / price) - 1.0) * 100.0 if atlas is not None and price and price > 0 else None
    analyst_upside = (
        ((analysts["mean"] / price) - 1.0) * 100.0
        if analysts["mean"] is not None and price and price > 0
        else None
    )
    scenario_upside = (
        ((scenarios["base"] / price) - 1.0) * 100.0
        if scenarios["base"] is not None and price and price > 0
        else None
    )
    return {
        "current_price": price,
        "atlas_fair_value": atlas,
        "atlas_expected_return_pct": round(atlas_return, 1) if atlas_return is not None else None,
        "analyst_target_mean": analysts["mean"],
        "analyst_target_high": analysts["high"],
        "analyst_target_low": analysts["low"],
        "analyst_count": analysts["count"],
        "analyst_upside_pct": round(analyst_upside, 1) if analyst_upside is not None else None,
        "scenario_bear": scenarios["bear"],
        "scenario_base": scenarios["base"],
        "scenario_bull": scenarios["bull"],
        "scenario_base_upside_pct": round(scenario_upside, 1) if scenario_upside is not None else None,
    }


__all__ = [
    "analyst_consensus", "analyst_scenarios", "canonical_atlas_fair_value",
    "first_present", "number", "present", "scanner_trade_plan", "valuation_families",
]
