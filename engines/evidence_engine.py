from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Sequence

_MISSING = {"", "none", "null", "nan", "n/a", "na", "unavailable", "not available", "—", "-"}


def _text(value: Any, default: str = "") -> str:
    t = str(value or "").strip()
    return default if t.lower() in _MISSING else t


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if value.lower() in _MISSING:
                return default
        n = float(value)
        return default if math.isnan(n) or math.isinf(n) else n
    except Exception:
        return default


def _pct(value: Any) -> Optional[float]:
    n = _num(value)
    if n is None:
        return None
    return n * 100 if -2 <= n <= 2 else n


def _pick(row: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    raw = row.get("Raw") if isinstance(row.get("Raw"), dict) else {}
    for source in (row, raw):
        for key in keys:
            value = source.get(key)
            if value is not None and _text(value, ""):
                return value
    return default


def build_evidence_profile(row: Mapping[str, Any]) -> Dict[str, Any]:
    revenue = _pct(_pick(row, ["Revenue Growth", "revenue_growth", "revenueGrowth"]))
    earnings = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth", "earningsGrowth"]))
    operating = _pct(_pick(row, ["Operating Margin", "operating_margin", "operatingMargins"]))
    fcf = _num(_pick(row, ["Free Cash Flow", "free_cash_flow", "freeCashflow"]))
    current_ratio = _num(_pick(row, ["Current Ratio", "current_ratio", "currentRatio"]))
    fair = _num(_pick(row, ["Atlas Fair Value", "atlas_fair_value", "fair_value", "ai_target"]))
    price = _num(_pick(row, ["Current Price", "current_price", "Price", "Close"]))
    analyst = _num(_pick(row, ["Analyst Target", "analyst_target_mean", "targetMeanPrice"]))
    technical = _num(_pick(row, ["Technical Score", "technical_score", "technical_agent_score"]))
    confidence = _num(_pick(row, ["Confidence", "confidence", "ai_confidence", "conviction_score"]))
    institutional = _num(_pick(row, ["Smart Money Score", "smart_money_score", "Institutional Score", "institutional_score"]))
    news = _text(_pick(row, ["latest_news_headline", "Top News", "news_headline"]), "")
    policy = _text(_pick(row, ["political_support_summary", "political_support", "Political Signal"]), "")
    earnings_summary = _text(_pick(row, ["earnings_ai_summary", "earnings_summary", "guidance_summary", "management_guidance"]), "")

    upside = None if fair is None or not price else (fair / price - 1) * 100
    analyst_upside = None if analyst is None or not price else (analyst / price - 1) * 100

    pillars: Dict[str, Dict[str, Any]] = {}

    business_score = 50.0
    if revenue is not None:
        business_score += max(-20, min(25, revenue * 0.8))
    if earnings is not None:
        business_score += max(-15, min(20, earnings * 0.5))
    pillars["Business"] = {"score": max(0, min(100, business_score)), "available": revenue is not None or earnings is not None}

    financial_score = 50.0
    if operating is not None:
        financial_score += max(-20, min(25, operating * 0.8))
    if fcf is not None:
        financial_score += 15 if fcf > 0 else -20
    if current_ratio is not None and current_ratio > 0:
        financial_score += 10 if current_ratio >= 1.2 else -8 if current_ratio < 0.8 else 0
    pillars["Financials"] = {"score": max(0, min(100, financial_score)), "available": any(x is not None for x in (operating, fcf, current_ratio))}

    valuation_score = 50.0
    if upside is not None:
        valuation_score += max(-25, min(35, upside * 0.55))
    if analyst_upside is not None:
        valuation_score += max(-10, min(15, analyst_upside * 0.25))
    pillars["Valuation"] = {"score": max(0, min(100, valuation_score)), "available": fair is not None or analyst is not None}

    technical_score = technical if technical is not None else 50.0
    pillars["Technicals"] = {"score": max(0, min(100, technical_score)), "available": technical is not None}

    news_score = 65.0 if news else 50.0
    pillars["News"] = {"score": news_score, "available": bool(news)}

    inst_score = institutional if institutional is not None else 50.0
    pillars["Institutional"] = {"score": max(0, min(100, inst_score)), "available": institutional is not None}

    policy_score = 60.0 if policy else 50.0
    pillars["Macro & Policy"] = {"score": policy_score, "available": bool(policy)}

    earnings_score = 65.0 if earnings_summary else 50.0
    pillars["Earnings"] = {"score": earnings_score, "available": bool(earnings_summary)}

    weights = {
        "Business": 0.20,
        "Financials": 0.20,
        "Valuation": 0.17,
        "Technicals": 0.15,
        "News": 0.08,
        "Institutional": 0.07,
        "Macro & Policy": 0.05,
        "Earnings": 0.08,
    }
    weighted = sum(pillars[k]["score"] * weights[k] for k in weights)
    if confidence is not None:
        weighted = weighted * 0.85 + confidence * 0.15

    available = sum(1 for p in pillars.values() if p["available"])
    agreement = sum(1 for p in pillars.values() if p["available"] and p["score"] >= 60)
    disagreements = [k for k, p in pillars.items() if p["available"] and p["score"] < 50]

    return {
        "pillars": pillars,
        "overall_score": round(max(0, min(100, weighted)), 1),
        "overall_10": round(max(0, min(10, weighted / 10)), 1),
        "available_pillars": available,
        "agreeing_pillars": agreement,
        "disagreements": disagreements,
        "upside": upside,
        "analyst_upside": analyst_upside,
    }
