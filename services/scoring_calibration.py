"""
Atlas V63 scoring calibration.
Normalizes Top AI Ideas display fields so opportunity, quality, upside, and recommendations
are stock-specific instead of repeated placeholders.
"""

from __future__ import annotations

from typing import Any
import math
import pandas as pd

V63_SCORING_CALIBRATION_VERIFIED = True

_MISSING = {"", "nan", "none", "null", "n/a", "na", "—", "-"}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            text = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if text.lower() in _MISSING:
                return default
            value = text
        n = float(value)
        if math.isnan(n):
            return default
        return n
    except Exception:
        return default


def _pick(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in _MISSING:
            continue
        return value
    return default


def _pct(value: Any, default: float | None = None, cap_abs: float | None = 500) -> float | None:
    n = _num(value, default)
    if n is None:
        return default
    if abs(n) <= 2:
        n *= 100
    if abs(n) > 500:
        n /= 100
    if cap_abs is not None and abs(n) > cap_abs:
        return default
    return n


def _target_upside(row: dict[str, Any]) -> float:
    price = _num(_pick(row, "Price", "price", "current_price", "last_price"), 0) or 0
    target = _num(_pick(row, "Target", "AI Fair Value", "target", "target_mean_price", "analyst_target_mean", "target_high_price"), 0) or 0
    raw = _pct(_pick(row, "Target Upside %", "target_upside_pct", "expected_upside_pct", "upside", "analyst_upside_pct"), None, cap_abs=500)
    if price > 0 and target > 0:
        calc = ((target - price) / price) * 100
        if -90 <= calc <= 300 and (raw is None or abs(raw - 30.0) < 0.01):
            return calc
    if raw is not None:
        return raw
    if price > 0 and target > 0:
        return ((target - price) / price) * 100
    return 0.0


def _finance_metric(row: dict[str, Any], name: str) -> Any:
    mapping = {
        "revenue_growth": ["Revenue Growth", "Revenue Growth %", "Revenue QoQ %", "revenue_growth", "revenue_qoq_pct", "scan_revenue_growth_pct"],
        "gross_margin": ["Gross Margin", "gross_margin", "grossMargins", "gross_profit_margin", "grossProfitMarginTTM"],
        "operating_margin": ["Operating Margin", "operating_margin", "operatingMargins", "operating_profit_margin", "operatingProfitMarginTTM"],
        "net_margin": ["Net Margin", "profit_margin", "net_margin", "net_profit_margin", "profitMargins", "netProfitMarginTTM"],
        "free_cash_flow": ["Free Cash Flow", "free_cashflow", "free_cash_flow", "FCF"],
        "operating_cash_flow": ["Operating Cash Flow", "operating_cashflow", "operating_cash_flow", "Op. Cash Flow"],
        "current_ratio": ["Current Ratio", "current_ratio"],
        "debt_to_equity": ["Debt to Equity", "debt_to_equity", "Debt/Equity"],
        "cash": ["Cash", "cash_and_equivalents", "total_cash"],
        "debt": ["Total Debt", "total_debt"],
        "pe": ["P/E", "pe_ratio", "PE"],
        "forward_pe": ["Forward PE", "forward_pe"],
    }
    return _pick(row, *mapping.get(name, [name]), default=None)


def _quality_score(row: dict[str, Any]) -> int:
    existing = _num(_pick(row, "Quality", "Quality Score", "financial_score", "fundamentals_agent_score", "Finance Agent Score"), None)
    rev = _pct(_finance_metric(row, "revenue_growth"), None)
    gross = _pct(_finance_metric(row, "gross_margin"), None)
    opm = _pct(_finance_metric(row, "operating_margin"), None)
    net = _pct(_finance_metric(row, "net_margin"), None)
    fcf = _num(_finance_metric(row, "free_cash_flow"), None)
    ocf = _num(_finance_metric(row, "operating_cash_flow"), None)
    current = _num(_finance_metric(row, "current_ratio"), None)
    debt_eq = _num(_finance_metric(row, "debt_to_equity"), None)
    cash = _num(_finance_metric(row, "cash"), None)
    debt = _num(_finance_metric(row, "debt"), None)

    score = 48.0
    if existing is not None and existing > 0:
        score = score * 0.55 + existing * 0.45
    if rev is not None: score += 10 if rev >= 20 else 7 if rev >= 10 else 3 if rev >= 0 else -8
    if gross is not None: score += 10 if gross >= 60 else 7 if gross >= 40 else 4 if gross >= 25 else -4
    if opm is not None: score += 8 if opm >= 20 else 5 if opm >= 10 else 2 if opm >= 0 else -6
    if net is not None: score += 8 if net >= 15 else 5 if net >= 8 else 2 if net >= 0 else -6
    if fcf is not None: score += 7 if fcf > 0 else -7
    if ocf is not None: score += 5 if ocf > 0 else -5
    if current is not None: score += 5 if current >= 1.5 else 2 if current >= 1 else -6
    if debt_eq is not None: score += 5 if debt_eq <= 50 else 2 if debt_eq <= 150 else -6
    if cash is not None and debt is not None: score += 4 if cash >= debt else -3
    return int(round(max(20, min(100, score))))


def _analyst_score(row: dict[str, Any]) -> int:
    text = str(_pick(row, "Analyst Support", "Analyst View", "analyst_support_label", "recommendation", default="")).lower()
    explicit = _num(_pick(row, "analyst_support_score"), None)
    if explicit is not None:
        return int(max(0, min(100, explicit)))
    if "strong" in text or "bull" in text or "buy" in text:
        return 82
    if "positive" in text or "constructive" in text:
        return 70
    if "mixed" in text or "hold" in text:
        return 55
    if "weak" in text or "sell" in text:
        return 35
    return 50


def _opportunity_score(row: dict[str, Any], quality: int) -> int:
    base = _num(_pick(row, "Final Conviction", "conviction", "conviction_score", "ai_score", "Score", "score"), 60) or 60
    upside = _target_upside(row)
    rr = _num(_pick(row, "Risk/Reward", "risk_reward"), 0) or 0
    rsi = _num(_pick(row, "RSI", "rsi"), 50) or 50
    trend20 = _pct(_pick(row, "20D %", "twenty_day_pct", "return_1m_pct"), 0, cap_abs=300) or 0
    trend5 = _pct(_pick(row, "5D %", "five_day_pct"), 0, cap_abs=300) or 0
    volume = _num(_pick(row, "Volume Ratio", "volume_ratio"), 1) or 1
    analyst = _analyst_score(row)

    upside_score = max(0, min(100, 45 + upside * 0.9))
    rr_score = 50 + min(rr, 6) * 8 if rr else 50
    momentum = 50
    momentum += 20 if trend20 > 15 else 12 if trend20 > 5 else 5 if trend20 > 0 else -12 if trend20 < -10 else 0
    momentum += 8 if trend5 > 5 else 0
    momentum += 8 if 45 <= rsi <= 68 else -12 if rsi > 75 else 0
    momentum += 6 if volume >= 1.2 else 0

    score = base * 0.23 + upside_score * 0.27 + rr_score * 0.17 + momentum * 0.18 + analyst * 0.10 + quality * 0.05
    return int(round(max(20, min(100, score))))


def _recommendation(opp: int, quality: int, upside: float, rr: float) -> str:
    if opp >= 84 and quality >= 68 and upside >= 12 and (rr == 0 or rr >= 1.4):
        return "✅ BUY NOW"
    if opp >= 76 and upside >= 8:
        return "🟡 WATCHLIST"
    if opp >= 65:
        return "👀 MONITOR"
    return "🔴 AVOID"


def _classification(opp: int, quality: int, upside: float) -> str:
    if quality >= 88:
        return "🏆 Elite Quality"
    if quality >= 78:
        return "✅ Quality Growth"
    if upside >= 75:
        return "🚀 High Upside"
    if opp >= 85:
        return "⚡ High Opportunity"
    return "📌 Actionable Idea"


def calibrate_top_ai_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    out = df.copy()
    records = []
    for row in out.to_dict("records"):
        quality = _quality_score(row)
        opp = _opportunity_score(row, quality)
        upside = _target_upside(row)
        rr = _num(_pick(row, "Risk/Reward", "risk_reward"), 0) or 0
        row["Opportunity"] = opp
        row["Quality"] = quality
        row["Target Upside %"] = round(upside, 1)
        row["Upside"] = round(upside, 1)
        row["Recommendation"] = _recommendation(opp, quality, upside, rr)
        row["Classification"] = _classification(opp, quality, upside)
        records.append(row)

    calibrated = pd.DataFrame(records)
    sort_cols = [c for c in ["Opportunity", "Quality", "Target Upside %"] if c in calibrated.columns]
    if sort_cols:
        calibrated = calibrated.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return calibrated.reset_index(drop=True)
