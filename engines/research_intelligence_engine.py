from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from engines.investment_thesis_engine import build_investment_thesis

from engines.institutional_intelligence_engine import (
    institutional_summary,
    evidence_scorecard,
    company_specific_risks,
)

_MISSING = {"", "none", "null", "nan", "n/a", "na", "unavailable", "not available", "—", "-"}


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


def _text(value: Any, default: str = "") -> str:
    t = str(value or "").strip()
    return default if t.lower() in _MISSING else t


def _pick(row: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    raw = row.get("Raw") if isinstance(row.get("Raw"), dict) else {}
    for source in (row, raw):
        for key in keys:
            value = source.get(key)
            if value is not None and _text(value, ""):
                return value
    return default


def _ticker(row: Mapping[str, Any]) -> str:
    return _text(_pick(row, ["Ticker", "ticker", "symbol"]), "UNKNOWN").upper()


def _company(row: Mapping[str, Any]) -> str:
    return _text(_pick(row, ["Company", "company", "company_name", "name"]), _ticker(row))


def _money(value: Any) -> str:
    n = _num(value)
    if n is None:
        return "Unavailable"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1e12:
        return f"{sign}${n/1e12:.1f}T"
    if n >= 1e9:
        return f"{sign}${n/1e9:.1f}B"
    if n >= 1e6:
        return f"{sign}${n/1e6:.1f}M"
    return f"{sign}${n:,.2f}"


def _meaningful(value: Any) -> bool:
    t = _text(value, "").lower()
    return bool(t) and not any(x in t for x in ("no recent", "no verified", "not returned", "not detected", "link unavailable"))


def analyst_intelligence(row: Mapping[str, Any]) -> Dict[str, Any]:
    mean = _num(_pick(row, ["Analyst Target", "analyst_target_mean", "target_mean_price", "targetMeanPrice"]))
    high = _num(_pick(row, ["Analyst High", "analyst_target_high", "target_high_price", "targetHighPrice"]))
    low = _num(_pick(row, ["Analyst Low", "analyst_target_low", "target_low_price", "targetLowPrice"]))
    median = _num(_pick(row, ["Analyst Median", "analyst_target_median", "target_median_price", "targetMedianPrice"]))
    count = _num(_pick(row, ["Analyst Count", "analyst_count", "numberOfAnalystOpinions"]))
    current = _num(_pick(row, ["Current Price", "current_price", "Price", "Close"]))
    rating = _text(_pick(row, ["Analyst Rating", "recommendationKey", "analyst_consensus", "Wall Street Consensus"]), "Unavailable")
    strong_buy = _num(_pick(row, ["strong_buy_count", "Strong Buy Count"]))
    buy = _num(_pick(row, ["buy_count", "Buy Count"]))
    hold = _num(_pick(row, ["hold_count", "Hold Count"]))
    sell = _num(_pick(row, ["sell_count", "Sell Count"]))
    upside = None if mean is None or not current else (mean / current - 1) * 100
    spread = None if high is None or low is None or not mean else (high - low) / mean * 100
    if mean is None:
        read = "Analyst target data is unavailable in this snapshot; Atlas does not infer missing Wall Street coverage."
    else:
        read = f"Wall Street's consensus target is ${mean:,.2f}"
        if upside is not None:
            read += f", implying {upside:+.1f}% from the current price"
        if high is not None and low is not None:
            read += f". The published range is ${low:,.2f}–${high:,.2f}"
        if count:
            read += f" across {int(count)} covering analysts"
        read += "."
    return {
        "consensus": mean, "high": high, "low": low, "median": median or mean,
        "count": int(count) if count else None, "rating": rating, "upside": upside,
        "spread_pct": spread,
        "ratings": {"Strong Buy": strong_buy, "Buy": buy, "Hold": hold, "Sell": sell},
        "summary": read,
    }


def financial_intelligence(row: Mapping[str, Any]) -> Dict[str, Any]:
    revenue = _pct(_pick(row, ["Revenue Growth", "revenue_growth", "revenueGrowth"]))
    earnings = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth", "earningsGrowth"]))
    gross = _pct(_pick(row, ["Gross Margin", "gross_margin", "grossMargins"]))
    operating = _pct(_pick(row, ["Operating Margin", "operating_margin", "operatingMargins"]))
    fcf = _num(_pick(row, ["Free Cash Flow", "free_cash_flow", "freeCashflow"]))
    current_ratio = _num(_pick(row, ["Current Ratio", "current_ratio", "currentRatio"]))
    roe = _pct(_pick(row, ["ROE", "return_on_equity", "returnOnEquity"]))
    debt = _num(_pick(row, ["Total Debt", "total_debt", "totalDebt"]))
    cash = _num(_pick(row, ["Cash", "total_cash", "totalCash"]))
    bullets: List[str] = []
    if revenue is not None:
        bullets.append(f"Revenue is {'growing' if revenue >= 0 else 'contracting'} {abs(revenue):.1f}% year over year.")
    if earnings is not None:
        bullets.append(f"Earnings are {'growing' if earnings >= 0 else 'declining'} {abs(earnings):.1f}%, showing {'positive' if earnings >= 0 else 'negative'} operating leverage.")
    if operating is not None:
        bullets.append(f"Operating margin is {operating:.1f}%, which indicates {'strong' if operating >= 20 else 'moderate' if operating >= 10 else 'thin'} profitability.")
    elif gross is not None:
        bullets.append(f"Gross margin is {gross:.1f}%, providing a view of unit economics before operating expenses.")
    if fcf is not None:
        bullets.append(f"Free cash flow is {_money(fcf)}, {'supporting internal reinvestment and capital returns' if fcf > 0 else 'which raises financing and execution risk'}.")
    if roe is not None:
        bullets.append(f"Return on equity is {roe:.1f}%, a measure of how effectively shareholder capital is being used.")
    if current_ratio is not None and current_ratio > 0:
        bullets.append(f"Current ratio is {current_ratio:.2f}, indicating {'comfortable' if current_ratio >= 1.5 else 'adequate' if current_ratio >= 1 else 'tight'} near-term liquidity.")
    if debt is not None and cash is not None:
        bullets.append(f"Balance-sheet context: {_money(cash)} cash versus {_money(debt)} debt.")
    if not bullets:
        bullets.append("Verified financial provider fields were unavailable; Atlas treats missing data as unknown rather than zero or negative evidence.")
    strength = "Strong" if sum(x is not None and x > 0 for x in (revenue, earnings, fcf)) >= 2 else "Mixed"
    return {"bullets": bullets[:7], "strength": strength}


def technical_intelligence(row: Mapping[str, Any]) -> Dict[str, Any]:
    price = _num(_pick(row, ["Current Price", "current_price", "Price", "Close"]))
    sma20 = _num(_pick(row, ["SMA20", "sma20", "20DMA"]))
    sma50 = _num(_pick(row, ["SMA50", "sma50", "50DMA"]))
    sma200 = _num(_pick(row, ["SMA200", "sma200", "200DMA"]))
    rsi = _num(_pick(row, ["RSI", "rsi"]))
    relvol = _num(_pick(row, ["Relative Volume", "relative_volume", "rel_volume", "volume_ratio"]))
    atr = _pct(_pick(row, ["ATR %", "atr_pct", "ATR Percent"]))
    support = _num(_pick(row, ["Support", "support", "support_level", "Ideal Entry"]))
    resistance = _num(_pick(row, ["Resistance", "resistance", "resistance_level", "Base Target"]))
    trend_parts = []
    if price is not None:
        if sma20 is not None: trend_parts.append(f"{'above' if price >= sma20 else 'below'} the 20-day average")
        if sma50 is not None: trend_parts.append(f"{'above' if price >= sma50 else 'below'} the 50-day average")
        if sma200 is not None: trend_parts.append(f"{'above' if price >= sma200 else 'below'} the 200-day average")
    trend = ", ".join(trend_parts) if trend_parts else "moving-average confirmation is unavailable"
    bullets = [f"Price is {trend}."]
    if rsi is not None:
        zone = "overbought" if rsi >= 70 else "oversold" if rsi <= 30 else "constructive and balanced"
        bullets.append(f"RSI is {rsi:.0f}, which is {zone}.")
    if relvol is not None:
        bullets.append(f"Relative volume is {relvol:.2f}× normal; {'participation confirms the move' if relvol >= 1 else 'participation is light and reduces conviction'}.")
    if atr is not None:
        bullets.append(f"ATR is approximately {atr:.1f}% of price, useful for sizing the position and setting a realistic stop.")
    if support is not None: bullets.append(f"Initial support or entry context is near ${support:,.2f}.")
    if resistance is not None: bullets.append(f"Initial resistance or upside reference is near ${resistance:,.2f}.")
    return {"bullets": bullets, "trend": trend}


def news_intelligence(row: Mapping[str, Any]) -> Dict[str, Any]:
    headline = _text(_pick(row, ["latest_news_headline", "Top News", "news_headline"]), "")
    date = _text(_pick(row, ["latest_news_date", "news_date", "Top News Date"]), "")
    source = _text(_pick(row, ["latest_news_source", "news_source", "Top News Source"]), "")
    sentiment = _text(_pick(row, ["latest_news_sentiment", "News Sentiment", "news_sentiment"]), "Neutral")
    catalyst = _text(_pick(row, ["catalyst_summary", "news_ai_summary", "latest_news_summary"]), "")
    if _meaningful(headline):
        summary = f"{headline}"
        meta = " · ".join(x for x in (source, date) if x)
        if meta: summary += f" ({meta})"
        explanation = catalyst if _meaningful(catalyst) else "Atlas classifies the headline as supporting evidence only when it can change demand, estimates, margins, regulation, financing, or valuation."
        return {"available": True, "headline": summary, "sentiment": sentiment.title(), "interpretation": explanation}
    return {"available": False, "headline": "No verified company-specific headline was included in the current refresh.", "sentiment": "Neutral", "interpretation": "The absence of verified news is neutral, not bullish or bearish."}


def policy_intelligence(row: Mapping[str, Any]) -> Dict[str, Any]:
    summary = _text(_pick(row, ["political_support_summary", "political_support", "Political Signal", "policy_summary"]), "")
    score = _num(_pick(row, ["Political Score", "political_score", "policy_score"]))
    label = "Neutral" if score is None else "Positive" if score >= 65 else "Negative" if score < 40 else "Neutral"
    if not _meaningful(summary):
        summary = "No verified company-specific political or policy catalyst was included. Atlas treats the evidence as neutral rather than inventing a tailwind."
    return {"label": label, "score": score, "summary": summary}


def institutional_activity(row: Mapping[str, Any]) -> Dict[str, Any]:
    ownership = _pct(_pick(row, ["Institutional Ownership", "institutional_ownership", "heldPercentInstitutions"]))
    change = _pct(_pick(row, ["Institutional Ownership Change", "institutional_ownership_change", "inst_change"]))
    insider = _text(_pick(row, ["insider_activity_summary", "Insider Activity", "insider_summary"]), "")
    smart = _num(_pick(row, ["Smart Money Score", "smart_money_score", "Institutional Score", "institutional_score"]))
    bullets = []
    if ownership is not None: bullets.append(f"Institutional ownership is approximately {ownership:.1f}%.")
    if change is not None: bullets.append(f"Reported institutional ownership changed {change:+.1f}% in the available period.")
    if _meaningful(insider): bullets.append(f"Insider activity: {insider}")
    if smart is not None: bullets.append(f"Atlas smart-money score is {smart:.0f}/100; it is a confirmation layer, not a standalone reason to buy.")
    if not bullets: bullets.append("Verified ownership-change or insider-activity detail was unavailable in this snapshot; Atlas does not fabricate fund activity.")
    return {"bullets": bullets}


def valuation_intelligence(row: Mapping[str, Any]) -> Dict[str, Any]:
    price = _num(_pick(row, ["Current Price", "current_price", "Price", "Close"]))
    fair = _num(_pick(row, ["Atlas Fair Value", "atlas_fair_value", "fair_value", "ai_target"]))
    low = _num(_pick(row, ["atlas_fair_value_low", "Atlas Fair Value Low", "bear_target"]))
    high = _num(_pick(row, ["atlas_fair_value_high", "Atlas Fair Value High", "bull_target"]))
    upside = None if fair is None or not price else round((fair / price - 1) * 100, 1)
    pe = _num(_pick(row, ["Forward PE", "forward_pe", "forwardPE"]))
    peg = _num(_pick(row, ["PEG Ratio", "peg_ratio", "pegRatio"]))
    methods = []
    for label, keys in (
        ("discounted cash flow", ["dcf_value", "DCF Value"]),
        ("growth and earnings", ["Earnings Growth", "earnings_growth"]),
        ("relative valuation", ["Forward PE", "forward_pe", "PEG Ratio"]),
        ("Wall Street cross-check", ["Analyst Target", "analyst_target_mean"]),
        ("technical/risk adjustment", ["Technical Score", "Risk Score"]),
    ):
        if _pick(row, keys) is not None: methods.append(label)
    if not methods: methods = ["multi-factor model using available growth, valuation, analyst, trend, volume, and risk fields"]
    summary = "Atlas Fair Value is unavailable because the snapshot did not contain enough verified inputs."
    if fair is not None:
        summary = f"Atlas Fair Value is ${fair:,.2f}"
        if upside is not None: summary += f", implying {upside:+.1f}% from ${price:,.2f}"
        if low is not None and high is not None: summary += f" within a modeled range of ${low:,.2f}–${high:,.2f}"
        summary += f". The estimate uses {', '.join(methods)}."
    if pe is not None: summary += f" Forward P/E is {pe:.1f}×."
    if peg is not None: summary += f" PEG is {peg:.2f}."
    return {"fair_value": fair, "low": low, "high": high, "upside": upside, "methods": methods, "summary": summary}


def research_completeness(row: Mapping[str, Any]) -> Dict[str, Any]:
    checks = {
        "Financials": any(_pick(row, [k]) is not None for k in ["Revenue Growth", "revenue_growth", "Free Cash Flow", "free_cash_flow", "Operating Margin"]),
        "Technicals": any(_pick(row, [k]) is not None for k in ["RSI", "rsi", "Technical Score", "SMA50"]),
        "Valuation": any(_pick(row, [k]) is not None for k in ["Atlas Fair Value", "atlas_fair_value", "Forward PE"]),
        "Analysts": any(_pick(row, [k]) is not None for k in ["Analyst Target", "analyst_target_mean", "Analyst Count"]),
        "News": _meaningful(_pick(row, ["latest_news_headline", "Top News", "news_headline"])),
        "Policy": _meaningful(_pick(row, ["political_support_summary", "political_support", "Political Signal"])),
        "Institutional": any(_pick(row, [k]) is not None for k in ["Institutional Ownership", "Smart Money Score", "insider_activity_summary"]),
        "Earnings": _meaningful(_pick(row, ["earnings_ai_summary", "earnings_summary", "guidance_summary", "management_guidance"])),
    }
    count = sum(checks.values())
    return {"checks": checks, "count": count, "total": len(checks), "pct": round(count / len(checks) * 100)}


def build_research_report(row: Mapping[str, Any]) -> Dict[str, Any]:
    base = institutional_summary(row)
    financial = financial_intelligence(row)
    technical = technical_intelligence(row)
    analysts = analyst_intelligence(row)
    news = news_intelligence(row)
    policy = policy_intelligence(row)
    institutional = institutional_activity(row)
    valuation = valuation_intelligence(row)
    completeness = research_completeness(row)
    risks = company_specific_risks(row, 5)
    scorecard = evidence_scorecard(row)
    decision = base["decision"]
    evidence_sources = [name for name, ok in completeness["checks"].items() if ok]
    evidence_strength = round((decision["score"] * .7 + completeness["pct"] * .3) / 10, 1)
    thesis_strength = "Very Strong" if evidence_strength >= 8.5 else "Strong" if evidence_strength >= 7 else "Developing" if evidence_strength >= 5 else "Limited"
    thesis = (
        f"{_company(row)} is rated {decision['label']} with {decision['score']:.0f}/100 evidence and "
        f"{completeness['count']}/{completeness['total']} research pillars populated. "
        f"{financial['bullets'][0]} {valuation['summary']} {news['interpretation']}"
    )
    thesis = build_investment_thesis(row, {"risks": risks})
    return {
        **base,
        "thesis": thesis,
        "financial": financial,
        "technical": technical,
        "analysts": analysts,
        "news": news,
        "policy": policy,
        "institutional_activity": institutional,
        "valuation": valuation,
        "completeness": completeness,
        "risks": risks,
        "evidence_strength": evidence_strength,
        "thesis_strength": thesis_strength,
        "evidence_sources": evidence_sources,
        "executive_summary": thesis,
        "scorecard": scorecard,
    }
