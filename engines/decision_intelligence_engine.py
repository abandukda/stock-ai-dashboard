from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if value.lower() in {"", "n/a", "na", "none", "null", "nan", "unavailable", "—", "-"}:
                return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
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
            if key in source:
                value = source.get(key)
                if value not in (None, "", "N/A", "Unavailable", "—", "-"):
                    return value
    return default


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return default if text.lower() in {"", "none", "null", "nan", "n/a", "unavailable", "—"} else text


def ticker(row: Mapping[str, Any]) -> str:
    return _text(_pick(row, ["Ticker", "ticker", "symbol"]), "").upper()


def company(row: Mapping[str, Any]) -> str:
    return _text(_pick(row, ["Company", "company", "company_name", "name"]), ticker(row))


def _valid_headline(text: str) -> bool:
    low = text.lower().strip()
    return bool(low) and not any(low.startswith(x) for x in ("no recent", "no verified", "unavailable", "not available"))


def evidence_pack(row: Mapping[str, Any], max_items: int = 7) -> List[str]:
    candidates: List[Tuple[int, str]] = []
    rev = _pct(_pick(row, ["Revenue Growth", "revenue_growth", "Revenue Growth %"]))
    eps = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth", "eps_growth"]))
    gross = _pct(_pick(row, ["Gross Margin", "gross_margin", "grossMargins"]))
    opm = _pct(_pick(row, ["Operating Margin", "operating_margin", "operatingMargins"]))
    fcf = _num(_pick(row, ["Free Cash Flow", "free_cash_flow", "free_cashflow"]))
    cash = _num(_pick(row, ["Cash", "total_cash", "cash_and_equivalents"]))
    debt = _num(_pick(row, ["Total Debt", "total_debt"]))
    upside = _pct(_pick(row, ["Expected Return", "expected_return_pct", "expected_upside_pct", "Target Upside %"]))
    street_up = _pct(_pick(row, ["analyst_upside_pct", "Analyst Upside", "wall_street_upside_pct"]))
    rsi = _num(_pick(row, ["RSI", "rsi", "RSI 14"]))
    vol = _num(_pick(row, ["Volume Ratio", "relative_volume", "Relative Volume"]))
    eps_surprise = _pct(_pick(row, ["eps_surprise_pct", "EPS Surprise", "earnings_surprise"]))
    headline = _text(_pick(row, ["latest_news_headline", "Top News", "news_headline"]), "")
    policy = _text(_pick(row, ["political_support_summary", "political_support", "Political Signal"]), "")
    guidance = _text(_pick(row, ["guidance_summary", "management_guidance", "earnings_ai_summary", "earnings_summary"]), "")

    if rev is not None:
        candidates.append((90 if rev >= 15 else 70 if rev >= 5 else 35, f"Revenue is growing {rev:.1f}%, indicating {'strong' if rev >= 15 else 'positive' if rev >= 5 else 'limited'} demand momentum."))
    if eps is not None:
        candidates.append((88 if eps >= 15 else 68 if eps >= 5 else 30, f"Earnings growth is {eps:.1f}%, showing how effectively sales are converting into profit."))
    if opm is not None:
        candidates.append((84 if opm >= 20 else 62 if opm >= 10 else 35, f"Operating margin is {opm:.1f}%, providing evidence on execution quality and pricing power."))
    elif gross is not None:
        candidates.append((76 if gross >= 50 else 55, f"Gross margin is {gross:.1f}%, supporting the company's unit economics."))
    if fcf is not None:
        candidates.append((82 if fcf > 0 else 20, "Free cash flow is positive, supporting reinvestment, debt reduction, or shareholder returns." if fcf > 0 else "Free cash flow is negative, so the growth thesis depends on future cash conversion."))
    if cash is not None and debt is not None:
        candidates.append((72 if cash >= debt else 38, "Cash exceeds total debt, giving the company meaningful balance-sheet flexibility." if cash >= debt else "Debt exceeds cash, making balance-sheet discipline more important."))
    if eps_surprise is not None:
        candidates.append((93 if eps_surprise > 3 else 55, f"The latest EPS result was {eps_surprise:+.1f}% versus expectations, {'supporting' if eps_surprise > 0 else 'challenging'} the near-term thesis."))
    if guidance:
        candidates.append((91, f"Management/earnings evidence: {guidance[:180]}"))
    if _valid_headline(headline):
        candidates.append((94, f"Recent catalyst: {headline[:190]}"))
    if policy and "not detected" not in policy.lower() and "neutral" not in policy.lower():
        candidates.append((78, f"Policy or political context: {policy[:180]}"))
    if upside is not None:
        candidates.append((80 if 12 <= upside <= 45 else 50, f"Atlas Fair Value implies {upside:+.1f}% expected return; confidence depends on the underlying valuation inputs."))
    if street_up is not None:
        candidates.append((74, f"Wall Street consensus implies {street_up:+.1f}% upside, providing an independent market cross-check."))
    if rsi is not None:
        if 48 <= rsi <= 68:
            candidates.append((65, f"RSI is {rsi:.0f}, a constructive momentum range without obvious overextension."))
        elif rsi > 72:
            candidates.append((32, f"RSI is {rsi:.0f}, indicating the shares may be extended in the short term."))
    if vol is not None and vol >= 1.25:
        candidates.append((70, f"Trading volume is {vol:.1f}× normal, confirming stronger market participation."))

    unique, seen = [], set()
    for _, text in sorted(candidates, key=lambda x: x[0], reverse=True):
        key = text.lower()[:80]
        if key not in seen:
            seen.add(key); unique.append(text)
        if len(unique) >= max_items:
            break
    if not unique:
        unique.append("Atlas has limited company-specific evidence in the current snapshot; live research should be refreshed before acting.")
    return unique


def primary_risk(row: Mapping[str, Any]) -> str:
    risks: List[Tuple[int, str]] = []
    pe = _num(_pick(row, ["Forward PE", "forward_pe", "forwardPE"]))
    debt_eq = _num(_pick(row, ["Debt to Equity", "debt_to_equity", "Debt/Equity"]))
    current = _num(_pick(row, ["Current Ratio", "current_ratio"]))
    rev = _pct(_pick(row, ["Revenue Growth", "revenue_growth"]))
    eps = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth"]))
    fcf = _num(_pick(row, ["Free Cash Flow", "free_cash_flow", "free_cashflow"]))
    rsi = _num(_pick(row, ["RSI", "rsi"]))
    atr = _pct(_pick(row, ["ATR %", "atr_pct"]))
    low_target = _num(_pick(row, ["Analyst Low", "analyst_target_low", "target_low_price"]))
    price = _num(_pick(row, ["Price", "price", "current_price"]))
    sector = _text(_pick(row, ["Sector", "sector"]), "").lower()
    industry = _text(_pick(row, ["Industry", "industry"]), "").lower()
    news_sent = _text(_pick(row, ["latest_news_sentiment", "News Sentiment"]), "").lower()

    if pe is not None and pe > 55: risks.append((95, f"Valuation risk is elevated at {pe:.1f}× forward earnings; even a modest execution miss could compress the multiple."))
    elif pe is not None and pe > 35: risks.append((78, f"The {pe:.1f}× forward earnings multiple leaves limited room for slower growth or weaker guidance."))
    if debt_eq is not None and debt_eq > 180: risks.append((92, f"Debt-to-equity is elevated at {debt_eq:.0f}, reducing financial flexibility if conditions weaken."))
    if current is not None and current > 0 and current < 1: risks.append((76, f"The current ratio is {current:.2f}, indicating tighter short-term liquidity coverage."))
    if rev is not None and rev < 0: risks.append((94, f"Revenue is declining {abs(rev):.1f}%, which directly challenges the growth thesis."))
    if eps is not None and eps < 0: risks.append((90, f"Earnings are declining {abs(eps):.1f}%, increasing the risk that valuation support weakens."))
    if fcf is not None and fcf < 0: risks.append((86, "Free cash flow is negative, increasing dependence on financing or future operating improvement."))
    if rsi is not None and rsi > 75: risks.append((72, f"RSI is {rsi:.0f}, so near-term entry risk is elevated after a potentially extended move."))
    if atr is not None and atr > 7: risks.append((74, f"ATR volatility is {atr:.1f}%, requiring smaller position sizing and wider risk controls."))
    if price and low_target and low_target < price * .9: risks.append((70, f"The low analyst target of ${low_target:,.2f} implies meaningful downside from the current price."))
    if news_sent == "negative": risks.append((88, "Recent news flow is negative and could pressure estimates or sentiment before fundamentals adjust."))
    if "biotech" in industry or "biotechnology" in industry: risks.append((84, "Clinical, regulatory, and product-concentration outcomes can create binary downside risk."))
    if "semiconductor" in industry: risks.append((73, "Semiconductor demand cycles, export controls, and customer concentration can rapidly change the earnings outlook."))
    if "consumer cyclical" in sector: risks.append((66, "Demand is sensitive to consumer spending, promotions, and macroeconomic conditions."))
    if "healthcare" in sector: risks.append((64, "Regulatory, reimbursement, and pipeline execution remain important sector-specific risks."))
    if not risks: risks.append((45, "The main risk is execution: management must deliver expected growth and margins while the market continues to support the current valuation."))
    return max(risks, key=lambda x: x[0])[1]


def decision(row: Mapping[str, Any]) -> Dict[str, Any]:
    quality = _num(_pick(row, ["Quality", "Quality Score", "quality_score", "financial_score"]), 50) or 50
    opportunity = _num(_pick(row, ["Opportunity", "Opportunity Score", "opportunity_score", "Final Conviction", "conviction_score"]), 50) or 50
    confidence = _num(_pick(row, ["Research Confidence", "Confidence", "confidence", "research_confidence"]), 50) or 50
    upside = _pct(_pick(row, ["Expected Return", "expected_return_pct", "expected_upside_pct", "Target Upside %"]))
    technical = _num(_pick(row, ["Technical Score", "technical_score", "technical_agent_score"]), opportunity) or opportunity
    catalyst = _num(_pick(row, ["Catalyst Score", "dynamic_catalyst_score", "news_score"]), 45) or 45
    fair = _num(_pick(row, ["Atlas Fair Value", "atlas_fair_value", "AI Fair Value"]))
    price = _num(_pick(row, ["Price", "price", "current_price"]))
    fcf = _num(_pick(row, ["Free Cash Flow", "free_cash_flow", "free_cashflow"]))
    rev = _pct(_pick(row, ["Revenue Growth", "revenue_growth"]))
    valuation_valid = bool(fair and price and fair > 0 and price > 0 and upside is not None)
    evidence_count = sum(x is not None for x in (fcf, rev, fair, upside))

    if valuation_valid and quality >= 78 and opportunity >= 80 and confidence >= 78 and 10 <= upside <= 45 and technical >= 60 and evidence_count >= 3:
        label = "HIGH CONVICTION BUY" if catalyst >= 55 or technical >= 72 else "BUY NOW"
        action = "The evidence supports initiating or adding a measured position, subject to portfolio fit and normal risk controls."
    elif valuation_valid and quality >= 70 and opportunity >= 70 and confidence >= 68 and upside >= 8:
        label = "BUY ON WEAKNESS"
        action = "The long-term case is constructive, but entry quality improves on a pullback or stronger technical confirmation."
    elif quality < 50 or (upside is not None and upside < -5):
        label = "AVOID"
        action = "Current evidence does not justify new exposure; wait for materially better fundamentals, valuation, or trend evidence."
    else:
        label = "WAIT FOR CONFIRMATION"
        action = "The thesis has support, but one or more required signals—valuation, fundamentals, catalyst, or technical confirmation—remain incomplete."
    return {"label": label, "action": action, "quality": quality, "opportunity": opportunity, "confidence": confidence, "upside": upside}


def movement_explanation(row: Mapping[str, Any]) -> Dict[str, str]:
    old = _num(row.get("prior_rank"))
    new = _num(row.get("dynamic_rank"))
    change = _num(row.get("rank_change"))
    if old and new:
        direction = "improved" if old > new else "fell" if old < new else "was unchanged"
        label = f"Rank {direction}: #{int(old)} → #{int(new)}"
    elif row.get("is_new_discovery"):
        label = "New to today's qualified discovery list"
    else:
        label = _text(row.get("movement_note"), "Baseline ranking while history accumulates")
    reasons = row.get("why_today") or evidence_pack(row, 3)
    if isinstance(reasons, str): reasons = [reasons]
    summary = " ".join(str(x) for x in reasons[:3])
    return {"label": label, "summary": summary, "direction": "up" if (change or 0) > 0 else "down" if (change or 0) < 0 else "flat"}


def macro_interpretation(event: str, actual: Any = None, estimate: Any = None, previous: Any = None) -> Dict[str, str]:
    e = _text(event).lower()
    a, est = _num(actual), _num(estimate)
    surprise = None if a is None or est is None else a - est
    impact, summary, supports, pressures = "Neutral / unclear", "The release requires context before drawing a market conclusion.", "Broad market", "None identified"
    if any(x in e for x in ("cpi", "ppi", "pce", "inflation")):
        if surprise is not None and surprise < 0:
            impact="Generally bullish for duration assets"; summary="Inflation came in below consensus, which can reduce yield pressure and improve the case for future rate cuts."; supports="Growth stocks, bonds, rate-sensitive sectors"; pressures="Banks if yields fall sharply"
        elif surprise is not None and surprise > 0:
            impact="Generally hawkish / risk-negative"; summary="Inflation exceeded consensus, increasing the risk of higher-for-longer rates and valuation pressure."; supports="Banks, dollar, selected value sectors"; pressures="Long-duration growth, bonds, REITs"
        else: summary="Inflation was in line or the surprise could not be measured; markets will focus on trend and underlying components."
    elif any(x in e for x in ("jobless", "unemployment", "payroll", "employment", "jolts", "jobs")):
        inverse = "jobless" in e or "unemployment" in e
        strong = surprise is not None and ((surprise < 0) if inverse else (surprise > 0))
        weak = surprise is not None and ((surprise > 0) if inverse else (surprise < 0))
        if strong:
            impact="Growth-positive but potentially hawkish"; summary="Labor data was stronger than expected, reducing recession concern but potentially delaying rate cuts."; supports="Consumer, industrials, banks"; pressures="Bonds and rate-sensitive growth if yields rise"
        elif weak:
            impact="Dovish but growth-cautious"; summary="Labor data was weaker than expected, improving the rate-cut case while raising questions about economic momentum."; supports="Bonds and rate-sensitive sectors"; pressures="Cyclicals and consumer names if weakness persists"
        else: summary="Labor data was close to expectations or lacked a usable consensus comparison."
    elif any(x in e for x in ("retail sales", "consumer confidence")):
        if surprise is not None and surprise > 0:
            impact="Growth-positive"; summary="Consumer demand exceeded expectations, supporting the near-term growth outlook."; supports="Consumer discretionary, payments, travel"; pressures="Rate-sensitive assets if yields rise"
        elif surprise is not None and surprise < 0:
            impact="Growth-cautious"; summary="Consumer demand missed expectations, increasing slowdown risk."; supports="Defensives and bonds"; pressures="Consumer cyclicals"
    elif any(x in e for x in ("pmi", "ism", "manufacturing", "services")):
        if a is not None:
            expansion = a >= 50
            impact="Expansion signal" if expansion else "Contraction signal"; summary=f"The index is {'above' if expansion else 'below'} 50, indicating {'expanding' if expansion else 'contracting'} business activity."; supports="Industrials and cyclicals" if expansion else "Defensives and bonds"; pressures="Bonds if growth reaccelerates" if expansion else "Cyclicals"
    elif any(x in e for x in ("fed", "fomc")):
        impact="Rate-expectation catalyst"; summary="Federal Reserve communication can rapidly change yield expectations, equity multiples, and sector leadership."; supports="Depends on dovish versus hawkish tone"; pressures="Rate-sensitive assets under hawkish guidance"
    return {"impact": impact, "summary": summary, "supports": supports, "pressures": pressures}
