from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from engines.evidence_engine import build_evidence_profile

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


def _ticker(row: Mapping[str, Any]) -> str:
    return _text(_pick(row, ["Ticker", "ticker", "symbol"]), "UNKNOWN").upper()


def _company(row: Mapping[str, Any]) -> str:
    return _text(_pick(row, ["Company", "company", "company_name", "name"]), _ticker(row))


def _money(value: Any) -> str:
    n = _num(value)
    if n is None:
        return "unavailable"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1e12:
        return f"{sign}${n/1e12:.1f}T"
    if n >= 1e9:
        return f"{sign}${n/1e9:.1f}B"
    if n >= 1e6:
        return f"{sign}${n/1e6:.1f}M"
    return f"{sign}${n:,.2f}"


def _unique(items: List[str], limit: int = 8) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        clean = " ".join(str(item).split()).strip(" .")
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean + ".")
        if len(out) >= limit:
            break
    return out


def build_investment_thesis(row: Mapping[str, Any], supporting_report: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    evidence = build_evidence_profile(row)
    ticker = _ticker(row)
    company = _company(row)
    revenue = _pct(_pick(row, ["Revenue Growth", "revenue_growth", "revenueGrowth"]))
    earnings = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth", "earningsGrowth"]))
    operating = _pct(_pick(row, ["Operating Margin", "operating_margin", "operatingMargins"]))
    fcf = _num(_pick(row, ["Free Cash Flow", "free_cash_flow", "freeCashflow"]))
    price = _num(_pick(row, ["Current Price", "current_price", "Price", "Close"]))
    fair = _num(_pick(row, ["Atlas Fair Value", "atlas_fair_value", "fair_value", "ai_target"]))
    analyst = _num(_pick(row, ["Analyst Target", "analyst_target_mean", "targetMeanPrice"]))
    rsi = _num(_pick(row, ["RSI", "rsi"]))
    relvol = _num(_pick(row, ["Relative Volume", "relative_volume", "rel_volume", "volume_ratio"]))
    news = _text(_pick(row, ["latest_news_headline", "Top News", "news_headline"]), "")
    news_summary = _text(_pick(row, ["catalyst_summary", "news_ai_summary", "latest_news_summary"]), "")
    policy = _text(_pick(row, ["political_support_summary", "political_support", "Political Signal", "policy_summary"]), "")
    earnings_summary = _text(_pick(row, ["earnings_ai_summary", "earnings_summary", "guidance_summary", "management_guidance"]), "")
    institutional = _pct(_pick(row, ["Institutional Ownership", "institutional_ownership", "heldPercentInstitutions"]))
    inst_change = _pct(_pick(row, ["Institutional Ownership Change", "institutional_ownership_change", "inst_change"]))
    current_ratio = _num(_pick(row, ["Current Ratio", "current_ratio", "currentRatio"]))
    forward_pe = _num(_pick(row, ["Forward PE", "forward_pe", "forwardPE"]))
    sector = _text(_pick(row, ["Sector", "sector"]), "")

    upside = None if fair is None or not price else (fair / price - 1) * 100
    analyst_upside = None if analyst is None or not price else (analyst / price - 1) * 100

    bull: List[str] = []
    if revenue is not None:
        bull.append(f"Revenue is {'growing' if revenue >= 0 else 'contracting'} {abs(revenue):.1f}% year over year")
    if earnings is not None and earnings > 0:
        bull.append(f"Earnings are expanding {earnings:.1f}%, supporting future cash-flow growth")
    if operating is not None:
        bull.append(f"Operating margin of {operating:.1f}% shows {'strong' if operating >= 20 else 'developing'} profitability")
    if fcf is not None and fcf > 0:
        bull.append(f"Free cash flow of {_money(fcf)} provides internal funding for reinvestment and shareholder returns")
    if upside is not None and upside > 0:
        bull.append(f"Atlas Fair Value indicates approximately {upside:.1f}% modeled upside")
    if analyst_upside is not None and analyst_upside > 0:
        bull.append(f"Wall Street consensus implies approximately {analyst_upside:.1f}% upside")
    if rsi is not None and 35 <= rsi <= 68:
        bull.append(f"RSI of {rsi:.0f} shows constructive momentum without an extreme overbought reading")
    if relvol is not None and relvol >= 1:
        bull.append(f"Relative volume of {relvol:.2f}× normal provides stronger participation confirmation")
    if institutional is not None:
        bull.append(f"Institutional ownership is approximately {institutional:.1f}%")
    if inst_change is not None and inst_change > 0:
        bull.append(f"Reported institutional ownership increased {inst_change:.1f}% in the available period")
    if news:
        bull.append(f"Recent verified catalyst: {news_summary or news}")
    if policy:
        bull.append(f"Policy context: {policy}")
    if earnings_summary:
        bull.append(f"Earnings and guidance evidence: {earnings_summary}")
    bull = _unique(bull, 8)

    risks: List[str] = []
    if supporting_report and supporting_report.get("risks"):
        risks.extend(str(x) for x in supporting_report.get("risks", []))
    if forward_pe is not None and forward_pe >= 35:
        risks.append(f"A forward P/E of {forward_pe:.1f}× leaves the stock sensitive to slower growth or multiple compression")
    if revenue is not None and revenue < 5:
        risks.append("Revenue growth is modest, so execution must improve to justify meaningful upside")
    if fcf is not None and fcf < 0:
        risks.append("Negative free cash flow increases dependence on external financing or future operating improvement")
    if current_ratio is not None and 0 < current_ratio < 1:
        risks.append(f"A current ratio of {current_ratio:.2f} indicates a tighter short-term liquidity cushion")
    if rsi is not None and rsi >= 72:
        risks.append("Momentum is stretched and the entry may be vulnerable to a near-term pullback")
    if relvol is not None and relvol < 0.7:
        risks.append("Volume confirmation is light, reducing confidence in the current price move")
    if upside is not None and upside > 100:
        risks.append("Very large modeled upside increases model-risk and requires stronger fundamental confirmation")
    if sector:
        risks.append(f"The company remains exposed to sector-specific demand, competition, and regulatory risks within {sector}")
    risks = _unique(risks, 5)
    if not risks:
        risks = ["The thesis depends on continued execution, stable demand, and valuation support; deterioration in any of these would reduce conviction."]

    score = evidence["overall_score"]
    available = evidence["available_pillars"]
    agreeing = evidence["agreeing_pillars"]
    if score >= 86 and available >= 5 and agreeing >= 4:
        recommendation = "High Conviction Buy"
    elif score >= 78 and available >= 4:
        recommendation = "Buy Now"
    elif score >= 68:
        recommendation = "Buy on Weakness"
    elif score >= 55:
        recommendation = "Wait for Confirmation"
    else:
        recommendation = "Avoid"

    confidence = min(98.0, max(35.0, score * 0.72 + (available / 8 * 100) * 0.28))
    thesis_strength = "Very Strong" if score >= 85 else "Strong" if score >= 72 else "Developing" if score >= 58 else "Limited"

    changed: List[str] = []
    rank_delta = _num(_pick(row, ["Rank Delta", "rank_delta", "Movement", "rank_change"]))
    score_delta = _num(_pick(row, ["Score Delta", "score_delta", "home_score_delta"]))
    if rank_delta is not None and rank_delta != 0:
        changed.append(f"Rank changed by {abs(int(rank_delta))} positions")
    if score_delta is not None and score_delta != 0:
        changed.append(f"Atlas score changed {score_delta:+.1f} points")
    if news:
        changed.append("A verified company-specific catalyst is present in the latest snapshot")
    if inst_change is not None and inst_change != 0:
        changed.append(f"Institutional ownership changed {inst_change:+.1f}% in the available period")
    if not changed:
        changed.append("No material verified change was detected; the current view is driven by the latest available fundamentals, valuation, and technical evidence")

    invalidate = []
    if revenue is not None:
        invalidate.append("revenue growth decelerates materially below the current trend")
    if operating is not None:
        invalidate.append("operating margins deteriorate without a credible reinvestment payoff")
    if fcf is not None:
        invalidate.append("free cash flow weakens or turns persistently negative")
    invalidate.append("analyst estimates and management guidance are revised materially lower")
    invalidate.append("price loses major technical support while the fundamental thesis also weakens")
    invalidate = _unique(invalidate, 5)

    opening = f"{company} currently screens as {recommendation.lower()} with an evidence score of {score:.1f}/100."
    support_sentence = " ".join(bull[:3]) if bull else "The available evidence is incomplete, so Atlas is keeping conviction measured."
    balance_sentence = f"The strongest counterpoint is: {risks[0]}"
    executive_summary = f"{opening} {support_sentence} {balance_sentence}"

    return {
        "ticker": ticker,
        "company": company,
        "recommendation": recommendation,
        "confidence": round(confidence, 1),
        "evidence": evidence,
        "thesis_strength": thesis_strength,
        "executive_summary": executive_summary,
        "bull_case": bull,
        "bear_case": risks,
        "whats_changed": _unique(changed, 5),
        "invalidation": invalidate,
        "expected_return": upside,
        "analyst_upside": analyst_upside,
        "time_horizon": "12–24 months" if recommendation in {"High Conviction Buy", "Buy Now"} else "6–18 months",
        "bottom_line": (
            f"Atlas rates {ticker} {recommendation}. {agreeing} of {available} populated evidence pillars are supportive. "
            "Position sizing should still reflect valuation risk, volatility, and the possibility that the thesis changes."
        ),
    }
