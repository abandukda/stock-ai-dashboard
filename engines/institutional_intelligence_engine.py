from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from engines.decision_intelligence_engine import (
    evidence_pack as base_evidence_pack,
    primary_risk as base_primary_risk,
    macro_interpretation as base_macro_interpretation,
)


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if value.lower() in {"", "n/a", "na", "none", "null", "nan", "unavailable", "—", "-"}:
                return default
        result = float(value)
        return default if math.isnan(result) or math.isinf(result) else result
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
            if key in source and source.get(key) not in (None, "", "N/A", "Unavailable", "—", "-"):
                return source.get(key)
    return default


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return default if text.lower() in {"", "none", "null", "nan", "n/a", "unavailable", "—"} else text


def _ticker(row: Mapping[str, Any]) -> str:
    return _text(_pick(row, ["Ticker", "ticker", "symbol"]), "").upper()


def _company(row: Mapping[str, Any]) -> str:
    return _text(_pick(row, ["Company", "company", "company_name", "name"]), _ticker(row))


def _score(row: Mapping[str, Any], keys: Sequence[str], default: float = 50.0) -> float:
    return max(0.0, min(100.0, _num(_pick(row, keys), default) or default))


def _meaningful(text: str) -> bool:
    low = text.lower().strip()
    return bool(low) and not any(x in low for x in ("no recent", "no verified", "not available", "unavailable", "not detected"))


def evidence_scorecard(row: Mapping[str, Any]) -> Dict[str, Any]:
    business = _score(row, ["Quality", "Quality Score", "quality_score", "financial_score"], 50)
    financial = _score(row, ["Financial Health", "Financial Health Score", "financial_health_score", "fundamentals_agent_score"], business)
    valuation = _score(row, ["Valuation Score", "valuation_agent_score", "valuation_score"], 50)
    technical = _score(row, ["Technical Score", "technical_agent_score", "technical_score"], 50)
    confidence = _score(row, ["Confidence", "Research Confidence", "confidence", "conviction_score"], 50)
    news_text = _text(_pick(row, ["latest_news_headline", "Top News", "news_headline"]), "")
    policy_text = _text(_pick(row, ["political_support_summary", "political_support", "Political Signal"]), "")
    earnings_text = _text(_pick(row, ["earnings_ai_summary", "earnings_summary", "guidance_summary", "management_guidance"]), "")
    news = _score(row, ["News Score", "news_score", "Catalyst Score", "catalyst_agent_score"], 50)
    if _meaningful(news_text): news = max(news, 68)
    if _meaningful(earnings_text): news = max(news, 72)
    macro_policy = _score(row, ["Macro Score", "macro_score", "Political Score", "political_score"], 50)
    if _meaningful(policy_text): macro_policy = max(macro_policy, 65)
    institutional = _score(row, ["Smart Money Score", "smart_money_score", "Institutional Score", "institutional_score"], 50)
    weighted = round(
        business * .23 + financial * .19 + valuation * .15 + technical * .15 +
        news * .10 + institutional * .08 + macro_policy * .05 + confidence * .05, 1
    )
    return {
        "Business": round(business, 1), "Financials": round(financial, 1),
        "Valuation": round(valuation, 1), "Technicals": round(technical, 1),
        "News & Catalysts": round(news, 1), "Institutional": round(institutional, 1),
        "Macro & Policy": round(macro_policy, 1), "Evidence Score": weighted,
    }


def institutional_evidence(row: Mapping[str, Any], max_items: int = 8) -> List[str]:
    items = list(base_evidence_pack(row, max_items=10))
    company = _company(row)
    revenue = _pct(_pick(row, ["Revenue Growth", "revenue_growth", "Revenue Growth %"]))
    earnings = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth", "eps_growth"]))
    roe = _pct(_pick(row, ["ROE", "return_on_equity", "returnOnEquity"]))
    target_high = _num(_pick(row, ["analyst_target_high", "Analyst High", "target_high_price"]))
    target_low = _num(_pick(row, ["analyst_target_low", "Analyst Low", "target_low_price"]))
    target_mean = _num(_pick(row, ["Analyst Target", "analyst_target_mean", "target_mean_price"]))
    analyst_count = _num(_pick(row, ["Analyst Count", "analyst_count", "numberOfAnalystOpinions"]))
    headline = _text(_pick(row, ["latest_news_headline", "Top News", "news_headline"]), "")
    guidance = _text(_pick(row, ["guidance_summary", "management_guidance", "earnings_ai_summary", "earnings_summary"]), "")
    policy = _text(_pick(row, ["political_support_summary", "political_support", "Political Signal"]), "")
    inst_change = _pct(_pick(row, ["Institutional Ownership Change", "institutional_ownership_change", "inst_change"]))

    extras: List[str] = []
    if revenue is not None and earnings is not None:
        extras.append(f"{company}'s revenue growth of {revenue:.1f}% and earnings growth of {earnings:.1f}% show whether expansion is translating into shareholder value.")
    if roe is not None and roe > 12:
        extras.append(f"Return on equity is {roe:.1f}%, evidence that management is generating productive returns on shareholder capital.")
    if target_mean and target_high and target_low:
        coverage = f" across {int(analyst_count)} analysts" if analyst_count else ""
        extras.append(f"Wall Street's target range is ${target_low:,.2f}–${target_high:,.2f}, with a ${target_mean:,.2f} consensus{coverage}; this provides a visible bull/base/bear cross-check.")
    if _meaningful(headline):
        extras.append(f"Latest verified catalyst: {headline[:220]}. Atlas treats this as supporting evidence only if it can affect demand, estimates, margins, regulation, or valuation.")
    if _meaningful(guidance):
        extras.append(f"Earnings and guidance read-through: {guidance[:240]}")
    if _meaningful(policy):
        extras.append(f"Policy context: {policy[:220]}")
    if inst_change is not None and abs(inst_change) >= .5:
        extras.append(f"Institutional ownership changed {inst_change:+.1f}%, a useful confirmation signal when aligned with fundamentals and price action.")

    seen, combined = set(), []
    for text in extras + items:
        key = text.lower()[:95]
        if key not in seen:
            seen.add(key); combined.append(text)
        if len(combined) >= max_items:
            break
    return combined


def company_specific_risks(row: Mapping[str, Any], max_items: int = 4) -> List[str]:
    risks: List[Tuple[int, str]] = []
    sector = _text(_pick(row, ["Sector", "sector"]), "").lower()
    industry = _text(_pick(row, ["Industry", "industry"]), "").lower()
    pe = _num(_pick(row, ["Forward PE", "forward_pe", "forwardPE"]))
    revenue = _pct(_pick(row, ["Revenue Growth", "revenue_growth"]))
    earnings = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth"]))
    fcf = _num(_pick(row, ["Free Cash Flow", "free_cash_flow", "free_cashflow"]))
    debt = _num(_pick(row, ["Total Debt", "total_debt"]))
    cash = _num(_pick(row, ["Cash", "total_cash", "cash_and_equivalents"]))
    concentration = _text(_pick(row, ["customer_concentration", "product_concentration", "concentration_risk"]), "")
    news_sentiment = _text(_pick(row, ["latest_news_sentiment", "News Sentiment"]), "").lower()
    rsi = _num(_pick(row, ["RSI", "rsi"]))

    if pe is not None and pe > 45: risks.append((95, f"The {pe:.1f}× forward earnings multiple requires sustained growth; weaker guidance could trigger material multiple compression."))
    if revenue is not None and revenue < 5: risks.append((90, f"Revenue growth is only {revenue:.1f}%, so the valuation thesis depends on reacceleration rather than current momentum."))
    if earnings is not None and earnings < 0: risks.append((92, f"Earnings are declining {abs(earnings):.1f}%, which could weaken valuation support and investor confidence."))
    if fcf is not None and fcf < 0: risks.append((94, "Free cash flow is negative, increasing dependence on financing and future execution."))
    if debt is not None and cash is not None and debt > cash * 2: risks.append((82, "Debt is more than twice cash, reducing flexibility if operating conditions deteriorate."))
    if news_sentiment == "negative": risks.append((88, "Recent verified news flow is negative and may pressure estimates or sentiment before the financial impact is fully visible."))
    if concentration: risks.append((86, f"Concentration risk: {concentration[:180]}"))
    if rsi is not None and rsi > 72: risks.append((68, f"RSI is {rsi:.0f}; the business thesis may be intact, but the entry is vulnerable to a short-term reset."))

    if "semiconductor" in industry: risks.extend([(84, "Semiconductor demand cycles, export controls, and customer concentration can change earnings expectations quickly."), (78, "AI capital-spending growth could normalize after the current infrastructure buildout." )])
    elif "biotech" in industry or "biotechnology" in industry: risks.extend([(92, "Clinical-trial, regulatory, reimbursement, and product-concentration outcomes can create binary downside."), (80, "Pipeline timing and cash runway may matter more than near-term accounting metrics." )])
    elif "software" in industry: risks.extend([(82, "Enterprise budget scrutiny, competitive AI products, and slower seat expansion could pressure growth or pricing."), (70, "High recurring revenue can mask slowing new bookings until guidance is revised." )])
    elif "bank" in industry or "financial" in sector: risks.append((82, "Credit quality, deposit costs, regulation, and the yield curve can materially change earnings power."))
    elif "energy" in sector or "oil" in industry or "gas" in industry: risks.append((84, "Commodity prices, project execution, regulation, and geopolitical supply changes can overwhelm company-specific progress."))
    elif "consumer" in sector: risks.append((76, "Consumer demand, promotions, input costs, and discretionary spending sensitivity can pressure margins."))
    elif "health" in sector: risks.append((77, "Reimbursement, regulation, pipeline execution, and product concentration remain material sector risks."))

    base = base_primary_risk(row)
    if base and "0.00" not in base: risks.append((65, base))
    if not risks: risks.append((50, "The central risk is execution: the company must convert its growth narrative into durable revenue, margins, and cash flow."))
    output, seen = [], set()
    for _, text in sorted(risks, key=lambda x: x[0], reverse=True):
        key=text.lower()[:90]
        if key not in seen:
            seen.add(key); output.append(text)
        if len(output)>=max_items: break
    return output


def institutional_decision(row: Mapping[str, Any]) -> Dict[str, Any]:
    scorecard = evidence_scorecard(row)
    score = scorecard["Evidence Score"]
    quality = scorecard["Business"]
    valuation = scorecard["Valuation"]
    technical = scorecard["Technicals"]
    news = scorecard["News & Catalysts"]
    confidence = _score(row, ["Confidence", "Research Confidence", "confidence", "conviction_score"], 50)
    upside = _pct(_pick(row, ["Expected Return", "expected_return_pct", "expected_upside_pct", "Target Upside %"]))
    evidence_count = len(institutional_evidence(row, 8))

    # Require independent confirmation for the strongest labels; avoid upside-only recommendations.
    strong_pillars = sum(x >= 70 for x in (quality, valuation, technical, news, confidence))
    if score >= 82 and quality >= 70 and confidence >= 72 and strong_pillars >= 4 and evidence_count >= 5 and (upside is None or upside >= 8):
        label, action = "HIGH CONVICTION BUY", "Independent business, valuation, catalyst, and technical evidence align. Build exposure within position-size limits rather than chasing an extended price."
    elif score >= 73 and quality >= 62 and confidence >= 64 and strong_pillars >= 3 and (upside is None or upside >= 6):
        label, action = "BUY NOW", "The current risk/reward is favorable enough for an initial position, with remaining capital reserved for volatility or confirmation."
    elif score >= 64 and quality >= 55 and (upside is None or upside >= 5):
        label, action = "BUY ON WEAKNESS", "The thesis is attractive, but timing, valuation confidence, or catalyst confirmation is incomplete. Use a staged entry near support."
    elif score < 46 or quality < 42 or (upside is not None and upside < -8):
        label, action = "AVOID", "The available evidence does not support new exposure. Wait for stronger fundamentals, valuation, or trend evidence."
    else:
        label, action = "WAIT FOR CONFIRMATION", "The company may be investable, but Atlas still needs stronger evidence from earnings, valuation, catalysts, or price/volume confirmation."
    return {"label":label,"action":action,"score":score,"confidence":confidence,"upside":upside,"scorecard":scorecard}


def institutional_summary(row: Mapping[str, Any]) -> Dict[str, Any]:
    decision = institutional_decision(row)
    evidence = institutional_evidence(row, 8)
    risks = company_specific_risks(row, 4)
    ticker, company = _ticker(row), _company(row)
    headline = _text(_pick(row,["latest_news_headline","Top News","news_headline"]),"")
    policy = _text(_pick(row,["political_support_summary","political_support","Political Signal"]),"")
    earnings = _text(_pick(row,["earnings_ai_summary","earnings_summary","guidance_summary","management_guidance"]),"")
    evidence_text = " ".join(evidence[:4])
    thesis = f"{company} ({ticker}) is rated {decision['label']} with an evidence score of {decision['score']:.0f}/100. {evidence_text}"
    bull = evidence[:5]
    bear = risks
    catalyst = headline if _meaningful(headline) else earnings if _meaningful(earnings) else "No material verified near-term catalyst is included in the current snapshot."
    policy_read = policy if _meaningful(policy) else "No verified company-specific policy tailwind or headwind is included; Atlas treats policy as neutral."
    counter = "Atlas would reduce conviction if guidance weakens, growth or cash conversion deteriorates, the primary risk intensifies, or price moves materially beyond evidence-supported fair value."
    return {
        "ticker":ticker,"company":company,"decision":decision,"scorecard":decision["scorecard"],
        "evidence":evidence,"risks":risks,"investment_thesis":thesis,"bull_case":bull,
        "bear_case":bear,"latest_catalyst":catalyst,"policy_read":policy_read,
        "earnings_read":earnings or "No verified earnings summary was included in this snapshot.",
        "counter_thesis":counter,
    }


def home_guidance(row: Mapping[str, Any]) -> Dict[str, Any]:
    summary = institutional_summary(row)
    move_old = _num(row.get("prior_rank")); move_new = _num(row.get("dynamic_rank"))
    if move_old and move_new:
        direction = "improved" if move_old > move_new else "fell" if move_old < move_new else "held"
        movement = f"Rank {direction}: #{int(move_old)} → #{int(move_new)}"
    elif row.get("is_new_discovery"):
        movement = "New today: first appearance in the qualified ranking history"
    else:
        movement = _text(row.get("movement_note"), "Current qualified ranking")
    why = " ".join(summary["evidence"][:3])
    return {
        "movement": movement,
        "why_today": why,
        "guidance": summary["decision"]["action"],
        "primary_risk": summary["risks"][0],
        "decision": summary["decision"]["label"],
        "evidence_score": summary["decision"]["score"],
    }


def market_calendar_intelligence(event: str, actual: Any=None, estimate: Any=None, previous: Any=None) -> Dict[str, Any]:
    base = base_macro_interpretation(event, actual, estimate, previous)
    a, e = _num(actual), _num(estimate)
    surprise = None if a is None or e is None else a-e
    magnitude = 0 if surprise is None else abs(surprise) / max(abs(e), 1) * 100
    confidence = "High" if a is not None and e is not None else "Low"
    impact_score = min(10.0, 4.5 + magnitude * .25) if surprise is not None else 4.0
    simple = base["summary"]
    if surprise is not None:
        simple += f" The result was {'above' if surprise>0 else 'below' if surprise<0 else 'in line with'} consensus by {abs(surprise):g}."
    return {**base,"confidence":confidence,"impact_score":round(impact_score,1),"surprise":surprise,"plain_language":simple}
