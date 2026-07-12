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


V793_DECISION_EXPERIENCE_ENGINE_VERIFIED = True

def _explicit_atlas_value(row: Mapping[str, Any]) -> float | None:
    return as_float(_first(
        row,
        "Atlas Fair Value", "AI Fair Value", "atlas_fair_value",
        "ai_fair_value", "ai_base_target", "Atlas Target",
    ))


def atlas_fair_value_details(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return an Atlas fair-value estimate without presenting legacy fixed-upside fields as precision.

    Priority:
    1. Explicit Atlas fair-value fields.
    2. A transparent blend of the legacy Atlas base target and Wall Street consensus.
    3. The legacy base target when no independent consensus exists.

    This preserves existing quant work while preventing a repeated 30% display from
    being mistaken for independently estimated upside across every company.
    """
    current = as_float(_first(row, "current_price", "price", "last_price", "Price"))
    explicit = _explicit_atlas_value(row)
    legacy_base = as_float(_first(row, "target", "Target"))
    legacy_bull = as_float(_first(row, "target_2", "Bull Target"))
    street = as_float(_first(row, "Wall Street Target", "Analyst Target", "target_mean_price", "analyst_target_mean"))

    value = explicit
    source = "Explicit Atlas Fair Value"

    if value is None and legacy_base is not None and street is not None:
        legacy_upside = calculate_upside(current, legacy_base)
        # Legacy target generation often lands exactly near +30%. Blend with an
        # independent analyst reference so the displayed fair value varies by name.
        if legacy_upside is not None and 29.5 <= legacy_upside <= 30.5:
            value = (0.55 * street) + (0.45 * legacy_base)
            source = "Atlas blended fair value"
        else:
            value = legacy_base
            source = "Atlas base valuation"
    elif value is None and legacy_base is not None:
        value = legacy_base
        source = "Atlas base valuation"
    elif value is None and street is not None:
        value = street
        source = "Wall Street fallback"

    # Keep a range for the full research report when a bull target exists.
    low = value
    high = legacy_bull if legacy_bull and value and legacy_bull > value else value
    return {
        "current_price": current,
        "atlas_fair_value": value,
        "atlas_fair_value_low": low,
        "atlas_fair_value_high": high,
        "wall_street_consensus": street,
        "expected_return_pct": calculate_upside(current, value),
        "source": source if value is not None else "Unavailable",
    }


def recommendation_tier(row: Mapping[str, Any], confidence: Any = None, expected_return: Any = None) -> str:
    """Return one clear customer-facing recommendation tier."""
    raw = str(_first(row, "Recommendation", "Decision", "decision_action", "Action", "recommendation") or "").upper()
    conf = as_float(confidence)
    if conf is None:
        conf = as_float(_first(row, "Confidence", "confidence", "conviction", "conviction_score", "score"), 0) or 0
    ret = as_float(expected_return)
    if "SELL" in raw or "AVOID" in raw:
        return "AVOID"
    if "BUY" in raw and conf >= 82 and (ret is None or ret >= 8):
        return "HIGH CONVICTION BUY"
    if conf >= 76 and (ret is None or ret >= 5):
        return "BUY ON WEAKNESS"
    if conf >= 58:
        return "WAIT FOR CONFIRMATION"
    return "AVOID"
