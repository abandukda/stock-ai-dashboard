"""Atlas V79 research engine helpers.

This module begins the extraction of research business logic out of app.py.
It intentionally contains pure helpers with no Streamlit dependency so the same
logic can later power a React/FastAPI frontend.
"""
from __future__ import annotations

from typing import Any, Mapping

V79_RESEARCH_ENGINE_EXTRACTION_VERIFIED = True

_MISSING = {"", "nan", "none", "null", "n/a", "na", "—", "-"}


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if value.lower() in _MISSING:
                return default
        return float(value)
    except Exception:
        return default


def calculate_upside(current_price: Any, target_price: Any) -> float | None:
    """Return uncapped upside percentage, or None when inputs are invalid."""
    current = as_float(current_price)
    target = as_float(target_price)
    if current is None or target is None or current <= 0:
        return None
    return ((target - current) / current) * 100.0


def validated_target(row: Mapping[str, Any]) -> float | None:
    """Pick the best available target from explicit Atlas/analyst fields."""
    keys = (
        "AI Fair Value", "Atlas Fair Value", "Atlas Target", "Target",
        "Analyst Target", "target_mean_price", "analyst_target_mean",
        "ai_fair_value", "target", "ai_base_target",
    )
    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            value = None
        n = as_float(value)
        if n is not None and n > 0:
            return n
    return None


def build_research_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    """Build a pure-data research snapshot for rendering or AI synthesis."""
    ticker = str(row.get("Ticker") or row.get("ticker") or "").strip().upper()
    company = str(row.get("Company") or row.get("company") or row.get("Name") or "").strip()
    current = as_float(row.get("Price") or row.get("price") or row.get("current_price"))
    target = validated_target(row)
    upside = calculate_upside(current, target)
    return {
        "ticker": ticker,
        "company": company,
        "current_price": current,
        "target_price": target,
        "upside_pct": upside,
        "has_valid_target": target is not None,
    }
