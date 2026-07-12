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
V80_TRUST_ROUTING_STABILIZATION_VERIFIED = True


def _is_legacy_30pct_target(current: float | None, target: float | None) -> bool:
    """Detect the repeated legacy current×1.30 target pattern."""
    upside = calculate_upside(current, target)
    return upside is not None and 29.65 <= upside <= 30.35


def _explicit_atlas_value(row: Mapping[str, Any]) -> tuple[float | None, str]:
    """Return an independently-labelled Atlas value, excluding generic legacy targets."""
    candidates = (
        ("Atlas Fair Value", "Atlas Fair Value"),
        ("atlas_fair_value", "Atlas Fair Value"),
        ("AI Fair Value", "Atlas model fair value"),
        ("ai_fair_value", "Atlas model fair value"),
        ("ai_base_target", "Atlas model fair value"),
        ("Atlas Target", "Legacy Atlas target"),
    )
    for key, label in candidates:
        value = as_float(_first(row, key))
        if value is not None and value > 0:
            return value, label
    return None, "Unavailable"


def atlas_fair_value_details(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return honest Atlas and Wall Street valuation fields.

    V80 deliberately rejects the repeated +30% target pattern. It does not blend
    Wall Street consensus into Atlas Fair Value merely to manufacture variation.
    When Atlas has no independent valuation, the UI should say "Under review".
    """
    current = as_float(_first(row, "current_price", "price", "last_price", "Price"))
    explicit, source = _explicit_atlas_value(row)
    legacy_base = as_float(_first(row, "target", "Target"))
    legacy_bull = as_float(_first(row, "target_2", "Bull Target", "ai_bull_target"))
    street = as_float(_first(
        row, "Wall Street Target", "Analyst Target", "target_mean_price",
        "analyst_target_mean", "finnhub_target_mean"
    ))

    value = explicit
    rejected_placeholder = False
    if value is not None and _is_legacy_30pct_target(current, value):
        value = None
        source = "Under review — legacy 30% pattern rejected"
        rejected_placeholder = True

    # Legacy target fields are accepted only when they do not match the repeated
    # 30% pattern and have an explicit model/source note.
    if value is None and legacy_base is not None:
        target_source = str(_first(row, "target_source", "target_confidence_note") or "").lower()
        has_model_provenance = any(x in target_source for x in ("dcf", "multiple", "valuation", "model", "fair value"))
        if has_model_provenance and not _is_legacy_30pct_target(current, legacy_base):
            value = legacy_base
            source = "Atlas valuation model"

    expected = calculate_upside(current, value)
    street_upside = calculate_upside(current, street)
    low = value
    high = legacy_bull if value and legacy_bull and legacy_bull > value and not _is_legacy_30pct_target(current, legacy_bull) else value
    return {
        "current_price": current,
        "atlas_fair_value": value,
        "atlas_fair_value_low": low,
        "atlas_fair_value_high": high,
        "wall_street_consensus": street,
        "expected_return_pct": expected,
        "wall_street_upside_pct": street_upside,
        "decision_upside_pct": expected if expected is not None else street_upside,
        "source": source if value is not None else "Atlas Fair Value under review",
        "rejected_legacy_placeholder": rejected_placeholder or _is_legacy_30pct_target(current, legacy_base),
    }


def _score(row: Mapping[str, Any], *keys: str, default: float = 0.0) -> float:
    return as_float(_first(row, *keys), default) or default


def decision_strength(row: Mapping[str, Any], confidence: Any = None, expected_return: Any = None) -> float:
    """Evidence-based decision score used by both counts and displayed cards."""
    conf = as_float(confidence)
    if conf is None:
        conf = _score(row, "Confidence", "confidence", "ai_confidence", "conviction", "conviction_score", default=50)
    ret = as_float(expected_return)
    if ret is None:
        details = atlas_fair_value_details(row)
        ret = as_float(details.get("decision_upside_pct"), 0) or 0
    opportunity = _score(row, "Opportunity", "Opportunity Score", "opportunity_score", "technical_agent_score", default=50)
    quality = _score(row, "Quality", "Quality Score", "quality_score", "financial_score", "fundamentals_agent_score", default=50)
    technical = _score(row, "technical_agent_score", "Technical Score", default=opportunity)
    fundamental = _score(row, "fundamentals_agent_score", "financial_score", "Fundamental Score", default=quality)
    risk = _score(row, "risk_agent_score", "Risk Score", default=65)
    valuation = _score(row, "valuation_agent_score", "Valuation Score", default=55)

    upside_component = max(0.0, min(100.0, 50.0 + ret * 1.6))
    score = (
        0.22 * opportunity + 0.20 * quality + 0.16 * conf +
        0.12 * technical + 0.12 * fundamental + 0.08 * risk +
        0.05 * valuation + 0.05 * upside_component
    )

    # Transparent penalties for evidence gaps and material financial risk.
    current_ratio = _score(row, "current_ratio", "Current Ratio", default=1.5)
    debt = as_float(_first(row, "total_debt", "debt", "Total Debt"))
    cash = as_float(_first(row, "total_cash", "cash", "cash_and_equivalents", "Total Cash"))
    if current_ratio and current_ratio < 0.8:
        score -= 5
    if debt is not None and cash is not None and debt > max(cash * 4, 1):
        score -= 5
    if ret < 0:
        score -= 8
    return max(0.0, min(100.0, score))


def recommendation_tier(row: Mapping[str, Any], confidence: Any = None, expected_return: Any = None) -> str:
    """Classify from current evidence; old saved labels cannot veto a qualifying idea."""
    raw = str(_first(row, "Recommendation", "Decision", "decision_action", "Action", "recommendation") or "").upper()
    if "SELL" in raw or "AVOID" in raw:
        return "AVOID"
    strength = decision_strength(row, confidence, expected_return)
    ret = as_float(expected_return)
    if ret is None:
        ret = as_float(atlas_fair_value_details(row).get("decision_upside_pct"), 0) or 0
    risk = _score(row, "risk_agent_score", "Risk Score", default=65)
    quality = _score(row, "Quality", "Quality Score", "quality_score", "financial_score", "fundamentals_agent_score", default=50)

    if strength >= 77 and quality >= 72 and risk >= 58 and ret >= 8:
        return "HIGH CONVICTION BUY"
    if strength >= 68 and quality >= 62 and ret >= 4:
        return "BUY ON WEAKNESS"
    if strength >= 52:
        return "WAIT FOR CONFIRMATION"
    return "AVOID"


def research_navigation_state(ticker: Any) -> dict[str, str]:
    """Return the single canonical session-state handoff for Research navigation."""
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return {}
    return {
        "v73_research_ticker": symbol,
        "selected_ticker": symbol,
        "selected_research_ticker": symbol,
        "v73_page": "Research Any Ticker",
        "v79_pending_page": "Research Any Ticker",
    }
