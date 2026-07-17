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

def build_evidence(row: Mapping[str, Any]) -> Dict[str, Any]:
    """V87 compatibility layer built on the V85 evidence profile.

    Keeps build_evidence_profile available for V84/V85 tests and engines while
    exposing richer plain-language evidence and risk fields for newer UI code.
    """
    profile = build_evidence_profile(row)

    revenue = _pct(_pick(row, ["Revenue Growth", "revenue_growth", "revenueGrowth"]))
    earnings = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth", "earningsGrowth"]))
    operating = _pct(_pick(row, ["Operating Margin", "operating_margin", "operatingMargins"]))
    gross = _pct(_pick(row, ["Gross Margin", "gross_margin", "grossMargins"]))
    fcf = _num(_pick(row, ["Free Cash Flow", "free_cash_flow", "freeCashflow"]))
    current_ratio = _num(_pick(row, ["Current Ratio", "current_ratio", "currentRatio"]))
    debt_to_equity = _num(_pick(row, ["Debt to Equity", "debt_to_equity", "debtToEquity"]))
    rsi = _num(_pick(row, ["RSI", "rsi"]))
    relative_volume = _num(_pick(row, ["Relative Volume", "relative_volume", "relativeVolume"]))
    analyst_count = _num(_pick(row, ["Analyst Count", "analyst_count", "numberOfAnalystOpinions"]))
    latest_news = _text(_pick(row, ["latest_news_headline", "Top News", "news_headline"]), "")
    policy = _text(_pick(row, ["political_support_summary", "political_support", "Political Signal"]), "")
    earnings_summary = _text(
        _pick(row, ["earnings_ai_summary", "earnings_summary", "guidance_summary", "management_guidance"]),
        "",
    )

    evidence: list[str] = []
    risks: list[str] = []

    upside = profile.get("upside")
    analyst_upside = profile.get("analyst_upside")

    if upside is not None:
        if upside >= 20:
            evidence.append(f"Atlas Fair Value implies approximately {upside:.1f}% upside.")
        elif upside > 0:
            evidence.append(f"Atlas Fair Value remains {upside:.1f}% above the current price.")

    if analyst_upside is not None and analyst_upside > 0:
        evidence.append(f"Wall Street consensus implies approximately {analyst_upside:.1f}% upside.")

    if revenue is not None:
        if revenue >= 15:
            evidence.append(f"Revenue growth of {revenue:.1f}% indicates strong demand.")
        elif revenue > 0:
            evidence.append(f"Revenue continues growing at {revenue:.1f}%.")

    if earnings is not None and earnings > 0:
        evidence.append(f"Earnings growth of {earnings:.1f}% supports the operating thesis.")

    if operating is not None and operating >= 15:
        evidence.append(f"Operating margin of {operating:.1f}% demonstrates attractive profitability.")

    if gross is not None and gross >= 40:
        evidence.append(f"Gross margin of {gross:.1f}% supports healthy unit economics.")

    if fcf is not None and fcf > 0:
        if abs(fcf) >= 1_000_000_000:
            evidence.append(f"Free cash flow is positive at ${fcf / 1_000_000_000:.1f}B.")
        elif abs(fcf) >= 1_000_000:
            evidence.append(f"Free cash flow is positive at ${fcf / 1_000_000:.1f}M.")
        else:
            evidence.append("Free cash flow is positive.")

    if rsi is not None and 45 <= rsi <= 65:
        evidence.append(f"RSI of {rsi:.0f} shows constructive momentum without looking overheated.")

    if relative_volume is not None and relative_volume >= 1.0:
        evidence.append(f"Relative volume of {relative_volume:.2f}x provides healthy participation.")

    if analyst_count is not None and analyst_count >= 10:
        evidence.append(f"{int(analyst_count)} analysts contribute to the available consensus.")

    if latest_news:
        evidence.append(f"Latest verified catalyst: {latest_news}")

    if policy:
        evidence.append(f"Policy context: {policy}")

    if earnings_summary:
        evidence.append(f"Earnings and guidance context: {earnings_summary}")

    if current_ratio is not None and 0 < current_ratio < 1:
        risks.append(f"Current ratio of {current_ratio:.2f} indicates a tighter short-term liquidity cushion.")

    if debt_to_equity is not None and debt_to_equity > 200:
        risks.append(f"Debt-to-equity of {debt_to_equity:.0f}% increases balance-sheet sensitivity.")

    if rsi is not None and rsi >= 75:
        risks.append(f"RSI of {rsi:.0f} suggests the shares may be technically overheated.")

    if relative_volume is not None and relative_volume < 0.7:
        risks.append(f"Relative volume of {relative_volume:.2f}x shows limited confirmation behind the move.")

    if not latest_news:
        risks.append("No material recent company-specific catalyst was verified.")

    if not earnings_summary:
        risks.append("Recent earnings and management-guidance context is incomplete.")

    if not risks:
        risks.append("Execution may fall short of the growth assumptions embedded in the valuation.")

    score = float(profile.get("overall_score", 50.0) or 50.0)
    if score >= 84:
        decision = "High Conviction Buy"
    elif score >= 76:
        decision = "Buy Now"
    elif score >= 67:
        decision = "Buy on Weakness"
    elif score < 48:
        decision = "Avoid"
    else:
        decision = "Wait for Confirmation"

    return {
        **profile,
        "score": round(score, 1),
        "decision": decision,
        "why_atlas_likes_it": evidence[:8],
        "primary_risks": risks[:5],
        "summary": " ".join(evidence[:4]) if evidence else "Evidence remains incomplete and requires further verification.",
    }


__all__ = ["build_evidence_profile", "build_evidence"]

