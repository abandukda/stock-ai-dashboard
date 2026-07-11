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


V792_RESEARCH_FINANCIAL_CONTEXT_VERIFIED = True

def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            value = None
        if value is not None and str(value).strip().lower() not in _MISSING:
            return value
    return None

def target_details(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return clearly separated targets and the primary valuation reference."""
    current = as_float(_first(row, "current_price", "price", "last_price", "Price"))
    atlas = as_float(_first(row, "Atlas Target", "AI Fair Value", "ai_fair_value", "ai_base_target", "target", "target_2"))
    street = as_float(_first(row, "Wall Street Target", "Analyst Target", "target_mean_price", "analyst_target_mean"))
    primary = atlas or street
    source = "Atlas Target" if atlas else ("Wall Street Target" if street else "No validated target")
    return {
        "current_price": current,
        "atlas_target": atlas,
        "wall_street_target": street,
        "primary_target": primary,
        "primary_source": source,
        "atlas_upside_pct": calculate_upside(current, atlas),
        "wall_street_upside_pct": calculate_upside(current, street),
    }

def build_financial_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    """Pure financial context used by Research and the AI synthesis layer."""
    fields = {
        "market_cap": ("market_cap", "Market Cap"),
        "revenue_growth": ("revenue_growth", "Revenue Growth"),
        "earnings_growth": ("earnings_growth", "Earnings Growth"),
        "gross_margin": ("gross_margin", "Gross Margin"),
        "operating_margin": ("operating_margin", "Operating Margin"),
        "profit_margin": ("profit_margin", "Profit Margin"),
        "free_cash_flow": ("free_cashflow", "free_cash_flow", "Free Cash Flow"),
        "operating_cash_flow": ("operating_cashflow", "operating_cash_flow", "Operating Cash Flow"),
        "cash": ("total_cash", "cash", "Total Cash"),
        "debt": ("total_debt", "debt", "Total Debt"),
        "debt_to_equity": ("debt_to_equity", "Debt to Equity"),
        "current_ratio": ("current_ratio", "Current Ratio"),
        "pe": ("pe_ratio", "trailing_pe", "P/E"),
        "forward_pe": ("forward_pe", "Forward P/E"),
        "peg": ("peg_ratio", "PEG"),
        "price_to_sales": ("price_to_sales", "Price to Sales"),
        "price_to_book": ("price_to_book", "Price to Book"),
    }
    out = {}
    for name, keys in fields.items():
        out[name] = as_float(_first(row, *keys))
    cash, debt = out.get("cash"), out.get("debt")
    out["net_cash"] = (cash - debt) if cash is not None and debt is not None else None
    return out
