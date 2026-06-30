"""
Atlas V60.3 Scoring Calibration.
Opportunity = setup/upside/timing.
Quality = business/financial strength.
Confidence = evidence/agent agreement.
"""

from __future__ import annotations

from typing import Any
import pandas as pd

_EMPTY = {"", "nan", "none", "null", "n/a", "na", "unavailable"}


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if text.lower() in _EMPTY:
        return default

    text = text.replace("%", "").replace("$", "").replace(",", "").replace("x", "").replace("X", "").strip()
    mult = 1.0
    upper = text.upper()

    if upper.endswith("B"):
        mult = 1_000_000_000.0
        text = text[:-1]
    elif upper.endswith("M"):
        mult = 1_000_000.0
        text = text[:-1]
    elif upper.endswith("K"):
        mult = 1_000.0
        text = text[:-1]

    try:
        return float(text) * mult
    except Exception:
        return default


def _pick(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if str(value).strip().lower() not in _EMPTY:
            return value
    return default


def _clip(value: float, low: float = 0, high: float = 100) -> int:
    return int(round(max(low, min(high, value))))


def _score_revenue_growth(value: Any) -> float:
    n = _num(value)
    if n >= 50:
        return 100
    if n >= 30:
        return 90
    if n >= 20:
        return 82
    if n >= 10:
        return 72
    if n >= 0:
        return 55
    return 35


def _score_margin(value: Any) -> float:
    n = _num(value)
    if n >= 70:
        return 96
    if n >= 55:
        return 88
    if n >= 40:
        return 78
    if n >= 25:
        return 65
    if n > 0:
        return 48
    return 35


def _score_debt_to_equity(value: Any) -> float:
    n = _num(value, default=999)
    if n <= 0.25:
        return 95
    if n <= 0.75:
        return 85
    if n <= 1.5:
        return 70
    if n <= 3:
        return 52
    return 35


def _score_current_ratio(value: Any) -> float:
    n = _num(value)
    if n >= 2.0:
        return 90
    if n >= 1.3:
        return 78
    if n >= 1.0:
        return 62
    if n > 0:
        return 42
    return 50


def _score_cashflow(value: Any) -> float:
    n = _num(value)
    if n > 1_000_000_000:
        return 94
    if n > 100_000_000:
        return 84
    if n > 0:
        return 70
    if n == 0:
        return 50
    return 35


def calculate_quality_score(row: dict[str, Any]) -> int:
    revenue_growth = _pick(row, "revenue_growth", "revenue_qoq_pct", "Revenue Growth")
    gross_margin = _pick(row, "gross_margin", "gross_profit_margin", "Gross Margin")
    operating_margin = _pick(row, "operating_margin", "operating_profit_margin", "Operating Margin")
    profit_margin = _pick(row, "profit_margin", "net_profit_margin", "Net Margin")
    debt_to_equity = _pick(row, "debt_to_equity", "Debt/Equity", "Debt / Equity")
    current_ratio = _pick(row, "current_ratio", "Current Ratio")
    fcf = _pick(row, "free_cashflow", "free_cash_flow", "Free Cash Flow", "FCF")
    roic = _pick(row, "roic", "ROIC")

    score = (
        0.20 * _score_revenue_growth(revenue_growth)
        + 0.18 * _score_margin(gross_margin)
        + 0.14 * _score_margin(operating_margin)
        + 0.12 * _score_margin(profit_margin)
        + 0.12 * _score_debt_to_equity(debt_to_equity)
        + 0.10 * _score_current_ratio(current_ratio)
        + 0.09 * _score_cashflow(fcf)
        + 0.05 * _score_margin(roic)
    )

    available = sum(v is not None and str(v).strip().lower() not in _EMPTY for v in [
        revenue_growth, gross_margin, operating_margin, profit_margin,
        debt_to_equity, current_ratio, fcf, roic
    ])

    if available <= 2:
        score = min(score, 58)
    elif available <= 4:
        score = min(score, 72)

    return _clip(score)


def calculate_opportunity_score(row: dict[str, Any]) -> int:
    upside = _num(_pick(row, "target_upside_pct", "expected_upside_pct", "analyst_upside_pct", "upside", "Upside"), 0)
    risk_reward = _num(_pick(row, "risk_reward", "Risk/Reward"), 1)
    rsi = _num(_pick(row, "rsi", "RSI"), 50)
    volume_ratio = _num(_pick(row, "volume_ratio", "Volume Ratio"), 1)
    analyst_score = _num(_pick(row, "analyst_support_score", "Analyst Score"), 60)
    technical_score = _num(_pick(row, "technical_agent_score", "setup_score", "Technical Score"), 60)

    upside_score = min(100, max(30, 45 + upside * 0.75))
    rr_score = min(100, max(35, 45 + risk_reward * 18))

    if 45 <= rsi <= 68:
        rsi_score = 88
    elif 35 <= rsi < 45 or 68 < rsi <= 75:
        rsi_score = 72
    elif rsi > 75:
        rsi_score = 55
    else:
        rsi_score = 48

    volume_score = min(95, max(45, 55 + (volume_ratio - 1) * 18))

    score = (
        0.34 * upside_score
        + 0.20 * rr_score
        + 0.14 * rsi_score
        + 0.12 * volume_score
        + 0.10 * analyst_score
        + 0.10 * technical_score
    )

    return _clip(score, 35, 98)


def calculate_confidence_score(row: dict[str, Any], opportunity: int, quality: int) -> int:
    evidence = _num(_pick(row, "evidence_confidence", "ai_confidence", "confidence"), 70)
    analyst_count = _num(_pick(row, "analyst_count", "finnhub_analyst_total"), 0)
    positive_agents = _num(_pick(row, "positive_agent_count"), 0)
    caution_agents = _num(_pick(row, "caution_agent_count"), 0)

    analyst_component = min(95, 55 + analyst_count * 3)
    agent_component = 65 + positive_agents * 5 - caution_agents * 7

    score = (
        0.35 * evidence
        + 0.25 * analyst_component
        + 0.20 * agent_component
        + 0.10 * opportunity
        + 0.10 * quality
    )

    return _clip(score, 45, 98)


def classification_from_scores(opportunity: int, quality: int) -> str:
    if opportunity >= 88 and quality >= 75:
        return "🚀 High Upside / Quality"
    if opportunity >= 88 and quality < 60:
        return "⚡ High Opportunity / Speculative"
    if opportunity >= 80:
        return "⚡ High Opportunity"
    if quality >= 85:
        return "🏆 Quality Compounder"
    if quality < 50:
        return "🧪 Speculative Setup"
    return "📌 Balanced Setup"


def rating_from_scores(opportunity: int, quality: int, confidence: int) -> str:
    final = round(0.45 * opportunity + 0.30 * quality + 0.25 * confidence)
    if final >= 92 and quality >= 70:
        return "🟢 Elite Buy"
    if final >= 88:
        return "🟢 High Conviction"
    if final >= 80:
        return "🔵 Buy"
    if final >= 70:
        return "🟡 Watchlist"
    if final >= 60:
        return "🟠 Speculative"
    return "🔴 Avoid"


def recalibrate_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)

    opportunity = calculate_opportunity_score(out)
    quality = calculate_quality_score(out)
    confidence = calculate_confidence_score(out, opportunity, quality)
    final = _clip(0.45 * opportunity + 0.30 * quality + 0.25 * confidence)

    out["Opportunity"] = opportunity
    out["Quality"] = quality
    out["Confidence"] = confidence
    out["Final Conviction"] = final
    out["classification"] = classification_from_scores(opportunity, quality)
    out["Classification"] = out["classification"]
    out["decision_rating"] = rating_from_scores(opportunity, quality, confidence)
    out["recommendation"] = "BUY NOW" if final >= 80 and opportunity >= 78 else ("WATCHLIST" if final >= 70 else "AVOID")
    out["Recommendation"] = out["recommendation"]

    return out


def calibrate_top_ai_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    rows = [recalibrate_row(row) for row in df.to_dict("records")]
    return pd.DataFrame(rows)


def calibrate_json_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [recalibrate_row(r) for r in records]
