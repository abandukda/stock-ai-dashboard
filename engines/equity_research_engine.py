"""Atlas V86 single-file equity research engine.

Drop into: engines/equity_research_engine.py

It accepts a dict-like stock row and returns a structured research report.
Missing values remain missing; they are never converted to fake zeroes.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
import math
import re


MISSING = {"", "n/a", "na", "none", "null", "nan", "unavailable", "under review", "-", "—"}


def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in MISSING:
            continue
        return value
    return default


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = float(value)
        return None if math.isnan(value) or math.isinf(value) else value
    text = str(value).replace(",", "").replace("$", "").replace("%", "").strip()
    if text.lower() in MISSING:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return default if text.lower() in MISSING else text


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [x.strip(" -•\t") for x in re.split(r"[\n|•]+", value) if x.strip(" -•\t")]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        out = []
        for item in value:
            if isinstance(item, Mapping):
                item = _first(item, "headline", "title", "summary", "text")
            if item:
                out.append(_text(item))
        return out
    return [_text(value)] if _text(value) else []


def _dedupe(items: list[str], limit: int = 8) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = re.sub(r"\s+", " ", item.lower()).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
        if len(out) >= limit:
            break
    return out


def _pct(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1f}%"


def _money(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.2f}"


def _upside(price: float | None, target: float | None) -> float | None:
    if price is None or target is None or price <= 0:
        return None
    return (target / price - 1) * 100


def _score(value: float) -> int:
    return max(0, min(100, round(value)))


def _bool(row: Mapping[str, Any], *keys: str) -> bool | None:
    value = _first(row, *keys)
    if isinstance(value, bool):
        return value
    number = _num(value)
    if number is not None:
        return number > 0
    text = _text(value).lower()
    if text in {"true", "yes", "above", "bullish"}:
        return True
    if text in {"false", "no", "below", "bearish"}:
        return False
    return None


def build_equity_research_report(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = _text(_first(row, "Ticker", "ticker", "symbol"), "UNKNOWN").upper()
    company = _text(_first(row, "Company", "company", "Name", "longName"), ticker)
    sector = _text(_first(row, "Sector", "sector", "Industry", "industry"), "its industry")

    price = _num(_first(row, "Current Price", "current_price", "Price", "Close"))
    fair_value = _num(_first(row, "Atlas Fair Value", "atlas_fair_value", "fair_value", "AI Target"))
    analyst_target = _num(_first(row, "Wall Street Consensus", "analyst_target", "targetMeanPrice"))
    analyst_high = _num(_first(row, "Analyst High Target", "analyst_high", "targetHighPrice"))
    analyst_low = _num(_first(row, "Analyst Low Target", "analyst_low", "targetLowPrice"))
    analyst_count = _num(_first(row, "Analyst Count", "analyst_count", "numberOfAnalystOpinions"))

    quality = _num(_first(row, "Quality", "Quality Score", "quality_score"))
    confidence = _num(_first(row, "Confidence", "confidence", "conviction_score"))
    revenue_growth = _num(_first(row, "Revenue Growth", "revenue_growth", "revenueGrowth"))
    eps_growth = _num(_first(row, "EPS Growth", "eps_growth", "earningsGrowth"))
    operating_margin = _num(_first(row, "Operating Margin", "operating_margin", "operatingMargins"))
    gross_margin = _num(_first(row, "Gross Margin", "gross_margin", "grossMargins"))
    fcf = _num(_first(row, "Free Cash Flow", "free_cash_flow", "freeCashflow"))
    current_ratio = _num(_first(row, "Current Ratio", "current_ratio", "currentRatio"))
    debt_to_equity = _num(_first(row, "Debt to Equity", "debt_to_equity", "debtToEquity"))
    forward_pe = _num(_first(row, "Forward P/E", "forward_pe", "forwardPE"))
    peg = _num(_first(row, "PEG Ratio", "peg", "pegRatio"))
    rsi = _num(_first(row, "RSI", "rsi"))
    rel_volume = _num(_first(row, "Relative Volume", "relative_volume", "relativeVolume"))
    above_50 = _bool(row, "Above 50DMA", "above_50dma", "price_above_sma50")
    above_200 = _bool(row, "Above 200DMA", "above_200dma", "price_above_sma200")

    news = _dedupe(_list(_first(row, "news_items", "latest_news", "news", "headlines")), 5)
    policy = _dedupe(_list(_first(row, "political_support", "political_context", "policy_context")), 4)
    institutional = _dedupe(_list(_first(row, "institutional_summary", "institutional_activity", "smart_money")), 4)
    earnings = _dedupe(_list(_first(row, "earnings_summary", "last_earnings_summary", "transcript_summary")), 4)
    guidance = _dedupe(_list(_first(row, "guidance_summary", "management_guidance")), 3)

    fv_upside = _upside(price, fair_value)
    ws_upside = _upside(price, analyst_target)

    business = 50
    if revenue_growth is not None:
        business += 18 if revenue_growth >= 15 else 8 if revenue_growth > 5 else -8
    if eps_growth is not None:
        business += 14 if eps_growth >= 15 else 6 if eps_growth > 0 else -8
    if gross_margin is not None:
        business += 8 if gross_margin >= 50 else 4 if gross_margin >= 30 else -4

    financials = 50
    if operating_margin is not None:
        financials += 18 if operating_margin >= 20 else 8 if operating_margin > 5 else -10
    if fcf is not None:
        financials += 15 if fcf > 0 else -20
    if current_ratio is not None and current_ratio > 0:
        financials += 8 if current_ratio >= 1.5 else 3 if current_ratio >= 1 else -8
    if debt_to_equity is not None:
        financials += 6 if debt_to_equity < 100 else -8 if debt_to_equity > 200 else 0

    valuation = 50
    if fv_upside is not None:
        valuation += 22 if 15 <= fv_upside <= 60 else 10 if fv_upside > 0 else -10
    if ws_upside is not None:
        valuation += 10 if ws_upside >= 15 else 5 if ws_upside > 0 else -5
    if forward_pe is not None:
        valuation += 6 if 0 < forward_pe <= 25 else -6 if forward_pe > 45 else 0
    if peg is not None:
        valuation += 6 if 0 < peg <= 2 else -5 if peg > 3 else 0

    technicals = 50
    technicals += 12 if above_50 is True else -10 if above_50 is False else 0
    technicals += 14 if above_200 is True else -14 if above_200 is False else 0
    if rsi is not None:
        technicals += 8 if 45 <= rsi <= 65 else -8 if rsi >= 75 else 1
    if rel_volume is not None:
        technicals += 6 if rel_volume >= 1.2 else -3 if rel_volume < 0.7 else 0

    scores = {
        "business": _score(business),
        "financials": _score(financials),
        "valuation": _score(valuation),
        "technicals": _score(technicals),
        "news": _score(50 + min(len(news) * 8, 30)),
        "institutional": _score(50 + min(len(institutional) * 8, 30)),
        "macro_policy": _score(50 + min(len(policy) * 7, 28)),
        "earnings": _score(50 + min((len(earnings) + len(guidance)) * 7, 35)),
    }

    overall = _score(
        scores["business"] * .18 +
        scores["financials"] * .18 +
        scores["valuation"] * .17 +
        scores["technicals"] * .17 +
        scores["news"] * .08 +
        scores["institutional"] * .07 +
        scores["macro_policy"] * .06 +
        scores["earnings"] * .09
    )
    if quality is not None:
        overall = _score(overall * .85 + quality * .15)
    if confidence is not None:
        overall = _score(overall * .90 + confidence * .10)

    support_upside = max([x for x in (fv_upside, ws_upside) if x is not None], default=None)
    if overall >= 84 and support_upside is not None and support_upside >= 15:
        decision = "High Conviction Buy"
    elif overall >= 76 and support_upside is not None and support_upside >= 10:
        decision = "Buy Now"
    elif overall >= 67 and support_upside is not None and support_upside > 0:
        decision = "Buy on Weakness"
    elif overall < 48:
        decision = "Avoid"
    else:
        decision = "Wait for Confirmation"

    bull = []
    if revenue_growth is not None and revenue_growth > 10:
        bull.append(f"Revenue growth of {_pct(revenue_growth)} supports continued expansion.")
    if eps_growth is not None and eps_growth > 10:
        bull.append(f"EPS growth of {_pct(eps_growth)} shows operating progress reaching shareholders.")
    if operating_margin is not None and operating_margin >= 15:
        bull.append(f"Operating margin of {_pct(operating_margin)} demonstrates attractive profitability.")
    if fcf is not None and fcf > 0:
        bull.append(f"Positive free cash flow of {_money(fcf)} supports reinvestment and capital returns.")
    if fv_upside is not None and fv_upside > 10:
        bull.append(f"Atlas Fair Value implies approximately {_pct(fv_upside)} upside.")
    if ws_upside is not None and ws_upside > 5:
        bull.append(f"Wall Street consensus implies approximately {_pct(ws_upside)} upside.")
    if scores["technicals"] >= 65:
        bull.append("Technical evidence is constructive rather than dependent on valuation alone.")
    if news:
        bull.append(f"Recent catalyst: {news[0]}")
    if policy:
        bull.append(f"Policy support: {policy[0]}")
    bull = _dedupe(bull, 8) or ["Additional verified evidence is needed to strengthen the bull case."]

    risks = []
    if quality is not None and quality < 65:
        risks.append(f"Quality score of {quality:.0f}/100 indicates a speculative profile.")
    if forward_pe is not None and forward_pe > 45:
        risks.append(f"Forward valuation of {forward_pe:.1f}x leaves little room for execution mistakes.")
    if current_ratio is not None and 0 < current_ratio < 1:
        risks.append(f"Current ratio of {current_ratio:.2f} indicates tighter short-term liquidity.")
    if debt_to_equity is not None and debt_to_equity > 200:
        risks.append(f"Debt-to-equity of {debt_to_equity:.0f}% raises balance-sheet sensitivity.")
    if above_50 is False:
        risks.append("Price remains below the 50-day trend, so momentum has not confirmed the thesis.")
    if above_200 is False:
        risks.append("Price remains below the 200-day trend, weakening the long-term setup.")
    if rel_volume is not None and rel_volume < .7:
        risks.append(f"Relative volume of {rel_volume:.2f}x shows limited participation.")
    if not news:
        risks.append("No material recent catalyst was verified, so upside may take longer to emerge.")
    if not earnings and not guidance:
        risks.append("Recent earnings and guidance context is incomplete, reducing forward confidence.")
    risks = _dedupe(risks, 6) or ["Execution may fall short of the growth assumptions embedded in the valuation."]

    verified = sum([
        revenue_growth is not None or eps_growth is not None,
        operating_margin is not None or fcf is not None,
        fair_value is not None or analyst_target is not None,
        rsi is not None or above_50 is not None or above_200 is not None,
        bool(news), bool(institutional), bool(policy), bool(earnings or guidance)
    ])
    report_confidence = _score(overall * .75 + verified / 8 * 25)

    strengths = []
    if scores["business"] >= 65: strengths.append("supportive business growth")
    if scores["financials"] >= 65: strengths.append("healthy financial quality")
    if scores["valuation"] >= 65: strengths.append("attractive valuation")
    if scores["technicals"] >= 65: strengths.append("constructive technical confirmation")
    if news: strengths.append("a current catalyst")
    if institutional: strengths.append("supportive institutional evidence")
    if policy: strengths.append("relevant policy context")
    strength_text = ", ".join(strengths[:5]) or "a mixed evidence set"

    executive_thesis = (
        f"Atlas rates {company} ({ticker}) as {decision}. "
        f"The case is supported by {strength_text}. "
        f"Atlas combines business quality, cash generation, valuation, technical trend, Wall Street expectations, "
        f"recent catalysts, institutional activity, earnings evidence, and policy context rather than relying on one metric. "
        f"The primary risk is: {risks[0]}"
    )

    valuation_summary = []
    if fair_value is not None:
        valuation_summary.append(f"Atlas Fair Value is {_money(fair_value)}, implying {_pct(fv_upside)} upside.")
    if analyst_target is not None:
        valuation_summary.append(f"Wall Street consensus is {_money(analyst_target)}, implying {_pct(ws_upside)} upside.")
    if analyst_low is not None or analyst_high is not None:
        valuation_summary.append(f"Analyst range: {_money(analyst_low)} to {_money(analyst_high)}.")
    if forward_pe is not None:
        valuation_summary.append(f"Forward P/E is {forward_pe:.1f}x.")
    if peg is not None:
        valuation_summary.append(f"PEG ratio is {peg:.2f}.")

    technical_summary = []
    if above_50 is not None:
        technical_summary.append("above the 50-day trend" if above_50 else "below the 50-day trend")
    if above_200 is not None:
        technical_summary.append("above the 200-day trend" if above_200 else "below the 200-day trend")
    if rsi is not None:
        technical_summary.append(f"RSI is {rsi:.1f}")
    if rel_volume is not None:
        technical_summary.append(f"relative volume is {rel_volume:.2f}x")

    return {
        "ticker": ticker,
        "company": company,
        "executive_thesis": executive_thesis,
        "decision": decision,
        "overall_score": overall,
        "confidence": report_confidence,
        "risk_level": "High" if overall < 50 else "Moderate" if overall < 72 else "Low to Moderate",
        "time_horizon": "12–18 months",
        "expected_return_pct": fv_upside,
        "analyst_upside_pct": ws_upside,
        "evidence_scorecard": scores,
        "research_completeness": {"verified_pillars": verified, "total_pillars": 8, "percent": round(verified / 8 * 100)},
        "business_summary": (
            f"{company} operates in {sector}. "
            + (f"Revenue growth is {_pct(revenue_growth)}. " if revenue_growth is not None else "")
            + (f"EPS growth is {_pct(eps_growth)}." if eps_growth is not None else "")
        ).strip(),
        "quality_summary": (
            (f"Atlas Quality Score is {quality:.0f}/100. " if quality is not None else "")
            + (f"Operating margin is {_pct(operating_margin)}. " if operating_margin is not None else "")
            + (f"Free cash flow is {_money(fcf)}." if fcf is not None else "")
        ).strip() or "Verified financial-quality fields were limited.",
        "valuation_summary": " ".join(valuation_summary) or "Verified valuation fields were unavailable.",
        "technical_summary": "; ".join(technical_summary) + "." if technical_summary else "Technical confirmation fields were limited.",
        "wall_street_summary": (
            (f"{int(analyst_count)} analysts contribute to consensus. " if analyst_count is not None else "")
            + (f"Average target is {_money(analyst_target)}." if analyst_target is not None else "")
        ).strip() or "Wall Street coverage data is limited.",
        "institutional_summary": " ".join(institutional[:3]) if institutional else "No verified recent institutional change was supplied.",
        "management_summary": " ".join((guidance + earnings)[:3]) if guidance or earnings else "No verified management-guidance or transcript summary was supplied.",
        "macro_policy_summary": " ".join(policy[:3]) if policy else "No verified company-specific policy catalyst was supplied.",
        "news_summary": " ".join(news[:4]) if news else "No recent high-confidence company-specific catalyst was supplied.",
        "bull_case": bull,
        "bear_case": risks,
        "primary_risks": risks[:3],
        "catalyst_timeline": {
            "next_30_days": _dedupe(news[:2] + guidance[:1] + earnings[:1], 3) or ["No verified near-term catalyst was supplied."],
            "next_3_to_6_months": ["Next earnings report and estimate revisions.", "Progress against management guidance.", "Technical confirmation or loss of support."],
            "next_6_to_12_months": ["Durability of revenue and EPS growth.", "Margin and free-cash-flow progression.", "Convergence toward Atlas Fair Value."],
        },
        "thesis_invalidation": [
            "Revenue or earnings growth turns negative for multiple periods.",
            "Operating margins or free cash flow deteriorate materially.",
            "The stock loses long-term technical support.",
            "Management guidance weakens or analysts cut estimates substantially.",
            "Atlas Fair Value falls below the market price after refreshed fundamentals.",
        ],
        "ai_verdict": {
            "rating": decision,
            "probability": report_confidence,
            "time_horizon": "12–18 months",
            "risk": "High" if overall < 50 else "Moderate" if overall < 72 else "Low to Moderate",
            "expected_return_pct": fv_upside,
            "reason": bull[0],
        },
        "bottom_line": (
            f"{ticker} is a {decision} with an Atlas evidence score of {overall}/100 and confidence of {report_confidence}%. "
            + (f"Modeled upside is {_pct(fv_upside)}." if fv_upside is not None else "Atlas Fair Value upside is unavailable.")
        ),
    }


build_research_report = build_equity_research_report
generate_equity_research = build_equity_research_report
