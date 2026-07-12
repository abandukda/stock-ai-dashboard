"""
Atlas AI Synthesis Layer.

Design principle:
- Deterministic scoring remains the source of truth.
- LLMs synthesize and explain facts; they do not invent numbers.
- If OPENAI_API_KEY is not configured, Atlas falls back to deterministic narrative.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

V78_AI_SYNTHESIS_LAYER_VERIFIED = True
V79_AI_COMMITTEE_SYNTHESIS_VERIFIED = True

_MISSING = {"", "nan", "none", "null", "n/a", "na", "—", "-"}


def _clean(value: Any, default: str = "Unavailable") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if text.lower() in _MISSING:
        return default
    return " ".join(text.split())


def _pick(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            value = None
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in _MISSING:
            return value
    return default


def _num(value: Any, default: float | None = None) -> float | None:
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


def _fmt_money(value: Any) -> str:
    n = _num(value)
    if n is None:
        return "Unavailable"
    if abs(n) >= 1_000_000_000:
        return f"${n/1_000_000_000:.1f}B"
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.1f}M"
    return f"${n:,.2f}"


def _fmt_pct(value: Any) -> str:
    n = _num(value)
    if n is None:
        return "Unavailable"
    return f"{n:.1f}%"


def llm_is_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def build_ticker_context(row: Mapping[str, Any]) -> dict[str, Any]:
    """Create a compact, auditable context object for AI synthesis."""
    price = _pick(row, "Price", "price", "current_price", "last_price")
    fair_value = _pick(row, "AI Fair Value", "Target", "ai_fair_value", "target", "ai_base_target")
    analyst_target = _pick(row, "Analyst Target", "target_mean_price", "analyst_target_mean")
    return {
        "ticker": _clean(_pick(row, "Ticker", "ticker", default="Unknown")),
        "company": _clean(_pick(row, "Company", "company", "Name", "name", default=""), default=""),
        "decision": _clean(_pick(row, "Recommendation", "Decision", "Action", "recommendation", default="Review")),
        "conviction": _clean(_pick(row, "Final Conviction", "Conviction", "AI Score", "Score", default="Unavailable")),
        "opportunity": _clean(_pick(row, "Opportunity", "Opportunity Score", "opportunity_score", default="Unavailable")),
        "quality": _clean(_pick(row, "Quality", "Quality Score", "quality_score", default="Unavailable")),
        "current_price": _fmt_money(price),
        "atlas_fair_value": _fmt_money(fair_value),
        "analyst_target": _fmt_money(analyst_target),
        "upside": _fmt_pct(_pick(row, "Target Upside %", "upside", "expected_upside_pct", "analyst_upside_pct")),
        "risk_reward": _clean(_pick(row, "Risk/Reward", "risk_reward", default="Unavailable")),
        "financial_summary": _clean(_pick(row, "Financial Summary", "financial_summary", "finance_agent_bottom_line", default=""), default=""),
        "technical_summary": _clean(_pick(row, "Technical Summary", "technical_summary", "v42_chart_guidance", default=""), default=""),
        "earnings_summary": _clean(_pick(row, "Earnings Summary", "earnings_summary", default=""), default=""),
        "political_summary": _clean(_pick(row, "Political Summary", "political_summary", default=""), default=""),
        "news_summary": _clean(_pick(row, "News Summary", "news_summary", "Top News", default=""), default=""),
        "primary_risk": _clean(_pick(row, "Primary Risk", "primary_risk", "Risk", default=""), default=""),
        "investment_thesis": _clean(_pick(row, "Investment Thesis", "AI Thesis", "ai_thesis", default=""), default=""),
        "committee_conclusion": _clean(_pick(row, "Committee Conclusion", "committee_conclusion", default=""), default=""),
        "revenue_growth": _fmt_pct(_pick(row, "revenue_growth", "Revenue Growth")),
        "earnings_growth": _fmt_pct(_pick(row, "earnings_growth", "Earnings Growth")),
        "gross_margin": _fmt_pct(_pick(row, "gross_margin", "Gross Margin")),
        "operating_margin": _fmt_pct(_pick(row, "operating_margin", "Operating Margin")),
        "profit_margin": _fmt_pct(_pick(row, "profit_margin", "Profit Margin")),
        "free_cash_flow": _fmt_money(_pick(row, "free_cashflow", "free_cash_flow", "Free Cash Flow")),
        "operating_cash_flow": _fmt_money(_pick(row, "operating_cashflow", "operating_cash_flow", "Operating Cash Flow")),
        "cash": _fmt_money(_pick(row, "total_cash", "cash", "Total Cash")),
        "debt": _fmt_money(_pick(row, "total_debt", "debt", "Total Debt")),
        "pe": _clean(_pick(row, "pe_ratio", "trailing_pe", "P/E", default="Unavailable")),
        "forward_pe": _clean(_pick(row, "forward_pe", "Forward P/E", default="Unavailable")),
        "peg": _clean(_pick(row, "peg_ratio", "PEG", default="Unavailable")),
        "rsi": _clean(_pick(row, "rsi", "RSI", default="Unavailable")),
        "volume_ratio": _clean(_pick(row, "volume_ratio", "Relative Volume", default="Unavailable")),
    }


def _agent_line(agent: Any, fallback: str = "Needs review") -> str:
    if isinstance(agent, Mapping):
        verdict = _clean(agent.get("verdict"), default="Review")
        bottom = _clean(agent.get("bottom"), default="")
        return f"{verdict}: {bottom}" if bottom else verdict
    return _clean(agent, default=fallback)


def deterministic_ticker_answer(question: str, context: Mapping[str, Any]) -> str:
    ticker = context.get("ticker", "This ticker")
    company = context.get("company", "")
    name = f"{ticker} ({company})" if company else str(ticker)
    parts = [
        f"### Atlas view on {name}",
        f"**Decision:** {context.get('decision', context.get('committee_decision', 'Review'))}",
        f"**Conviction:** {context.get('conviction', 'Unavailable')} | **Opportunity:** {context.get('opportunity', context.get('opportunity_score', 'Unavailable'))} | **Quality:** {context.get('quality', context.get('quality_score', 'Unavailable'))}",
        f"**Current price:** {context.get('current_price')} | **Atlas fair value:** {context.get('atlas_fair_value')} | **Wall Street target:** {context.get('analyst_target')} | **Upside:** {context.get('upside')}",
    ]
    thesis = context.get("investment_thesis") or context.get("committee_conclusion")
    if thesis:
        parts.append(f"\n**Why Atlas is interested:** {thesis}")
    if context.get("financial_summary"):
        parts.append(f"\n**Financial read-through:** {context['financial_summary']}")
    if context.get("technical_summary"):
        parts.append(f"\n**Technical read-through:** {context['technical_summary']}")
    if context.get("earnings_summary"):
        parts.append(f"\n**Earnings read-through:** {context['earnings_summary']}")
    if context.get("political_summary"):
        parts.append(f"\n**Political context:** {context['political_summary']}")
    if context.get("primary_risk"):
        parts.append(f"\n**Main risk:** {context['primary_risk']}")
    parts.append("\n**What would change the rating:** a material guidance cut, valuation moving well above Atlas fair value, weakening technical trend, or a negative catalyst that changes the investment thesis.")
    parts.append("\n*Note: This response is grounded in the latest saved Atlas scan. Configure OPENAI_API_KEY to enable full LLM synthesis on top of these facts.*")
    return "\n".join(parts)


def deterministic_committee_summary(context: Mapping[str, Any]) -> str:
    ticker = context.get("ticker", "This ticker")
    company = context.get("company", "")
    name = f"{ticker} — {company}" if company else str(ticker)
    decision = context.get("committee_decision") or context.get("decision") or "Review"
    classification = context.get("classification") or "Needs full review"
    return "\n".join([
        f"**CIO View:** {decision} — {classification}",
        "",
        f"Atlas reviewed {name} using financial quality, Wall Street support, smart-money context, technical timing, news/catalysts, and risk controls.",
        "",
        "**Agent evidence:**",
        f"- Fundamental Analyst: {_agent_line(context.get('financial_agent'))}",
        f"- Wall Street Analyst: {_agent_line(context.get('wall_street_agent'))}",
        f"- Smart Money Analyst: {_agent_line(context.get('smart_money_agent'))}",
        f"- Technical Analyst: {_agent_line(context.get('technical_agent'))}",
        f"- News & Catalyst Analyst: {_agent_line(context.get('news_agent'))}",
        "",
        "**Bottom line:** Use the committee verdict as a research prioritization signal, not an automatic trade. Confirm target quality, earnings timing, liquidity, and downside controls before sizing a position.",
    ])


def _llm_prompt(question: str, context: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are Atlas AI, an investment research synthesis assistant. "
                "Use only the supplied structured facts. Do not invent figures, targets, dates, news, or filings. "
                "If a fact is unavailable, say so plainly. Write in clear, professional language for retail investors. "
                "Separate facts from interpretation. Do not provide personalized financial advice or tell the user they must trade."
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nStructured Atlas facts:\n{dict(context)}\n\nProvide: decision summary, why it matters, risks, what would change the view, and a plain-English bottom line.",
        },
    ]


def _committee_prompt(context: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the Atlas Chief Investment Officer. Produce a concise investment committee synthesis. "
                "Use only the supplied deterministic agent outputs and numerical fields. Do not invent missing metrics. "
                "Label uncertainty clearly. Avoid personalized financial advice."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Structured Atlas committee facts:\n{dict(context)}\n\n"
                "Write sections: CIO View, Bull Case, Bear Case, Key Risks, What Would Change Our Mind, Bottom Line. "
                "Keep it concise and institutional but understandable to retail investors."
            ),
        },
    ]


def _call_llm(messages: list[dict[str, str]], fallback: str, max_tokens: int = 800) -> str:
    if not llm_is_configured():
        return fallback
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        model = os.getenv("ATLAS_LLM_MODEL", "gpt-4o-mini")
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens,
        )
        text = completion.choices[0].message.content or ""
        return text.strip() or fallback
    except Exception:
        return fallback


def answer_ticker_question(question: str, context: Mapping[str, Any]) -> str:
    """Answer using LLM if configured, otherwise use deterministic fallback."""
    fallback = deterministic_ticker_answer(question, context)
    return _call_llm(_llm_prompt(question, context), fallback, max_tokens=700)


def generate_investment_committee(context: Mapping[str, Any]) -> str:
    """Generate a single CIO synthesis from deterministic agent outputs."""
    fallback = deterministic_committee_summary(context)
    return _call_llm(_committee_prompt(context), fallback, max_tokens=900)


V792_HOME_DECISION_SUMMARY_VERIFIED = True

def _pct_plain(value: Any) -> str | None:
    n = _num(value)
    if n is None:
        return None
    if abs(n) <= 1:
        n *= 100
    return f"{n:.1f}%"

def build_home_decision_summary(row: Mapping[str, Any], decision: str) -> str:
    """Create a concise evidence-based home-card explanation without an API call."""
    ticker = _clean(_pick(row, "Ticker", "ticker", "symbol", default="This company"))
    positives = []
    rev = _pct_plain(_pick(row, "revenue_growth", "Revenue Growth"))
    margin = _pct_plain(_pick(row, "profit_margin", "Profit Margin"))
    fcf = _fmt_money(_pick(row, "free_cashflow", "free_cash_flow", "Free Cash Flow"))
    cash = _num(_pick(row, "total_cash", "cash")); debt = _num(_pick(row, "total_debt", "debt"))
    rsi = _num(_pick(row, "rsi", "RSI"))
    if rev: positives.append(f"revenue growth is {rev}")
    if margin: positives.append(f"profit margin is {margin}")
    if fcf != "Unavailable": positives.append(f"free cash flow is {fcf}")
    if cash is not None and debt is not None and cash > debt: positives.append("cash exceeds debt")
    if rsi is not None: positives.append(f"RSI is {rsi:.0f}, indicating {'constructive momentum' if 45 <= rsi <= 70 else 'a setup that needs timing discipline'}")
    evidence = "; ".join(positives[:3]) if positives else _clean(_pick(row, "what_looks_good", "financial_summary", default="the combined Atlas signals warrant deeper review"), default="the combined Atlas signals warrant deeper review")
    risk = _clean(_pick(row, "what_could_go_wrong", "Primary Risk", "primary_risk", default="earnings, valuation, and entry timing still require review"), default="earnings, valuation, and entry timing still require review")
    if "BUY" in str(decision).upper():
        lead = "qualifies as a current buy candidate"
    elif "ACCUMULATE" in str(decision).upper():
        lead = "is attractive, but Atlas favors staged buying or a better entry"
    else:
        lead = "remains on watch because the evidence is not yet strong enough for an immediate purchase"
    return f"{ticker} {lead}: {evidence}. The main watch item is {risk}."


V793_AI_DECISION_SUMMARY_VERIFIED = True
V80_COMPANY_SPECIFIC_REASONING_VERIFIED = True


def _simple_pct(value: Any) -> float | None:
    n = _num(value)
    if n is None:
        return None
    return n * 100 if abs(n) <= 1 else n


def _first_sentence(value: Any) -> str:
    text = _clean(value, default="")
    if not text:
        return ""
    for sep in (";", ". ", "\n"):
        if sep in text:
            text = text.split(sep, 1)[0]
            break
    return text.strip().rstrip(".")


def _parse_news_date(value: Any):
    if not value:
        return None
    try:
        from datetime import datetime
        text = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def _fresh_news_reason(row: Mapping[str, Any]) -> tuple[float, str] | None:
    """Return a recent, company-specific positive catalyst only when freshness is verifiable."""
    from datetime import date
    headline = _clean(_pick(row, "latest_news_headline", "top_news_headline", "Top News", default=""), default="")
    published = _pick(row, "latest_news_date", "top_news_date", "News Date", "news_date")
    source = _clean(_pick(row, "latest_news_source", "top_news_source", "News Source", default=""), default="")
    sentiment = _clean(_pick(row, "latest_news_sentiment", "news_status", "v42_news_status", default=""), default="").lower()
    d = _parse_news_date(published)
    if not headline or d is None:
        return None
    age = (date.today() - d).days
    if age < 0 or age > 10:
        return None
    positive_terms = ("beat", "raise", "raised", "upgrade", "record", "contract", "partnership", "launch", "expand", "growth", "guidance", "approval", "award", "investment")
    negative_terms = ("miss", "cut", "downgrade", "lawsuit", "probe", "investigation", "warning", "decline", "layoff", "loss")
    low = headline.lower()
    if any(term in low for term in negative_terms):
        return None
    if "positive" not in sentiment and not any(term in low for term in positive_terms):
        return None
    clean_headline = headline.rstrip(" .")
    suffix = f" ({source}, {d.isoformat()})" if source else f" ({d.isoformat()})"
    return 96 - min(age, 10) * 0.8, f"Recent catalyst: {clean_headline}.{suffix}"


def _political_support_reason(row: Mapping[str, Any]) -> tuple[float, str] | None:
    """Highlight policy or disclosure support only when the saved evidence is positive and specific."""
    signal = _clean(_pick(row, "Political Signal", "political_signal", "political_status", default=""), default="")
    summary = _first_sentence(_pick(row, "Political Summary", "political_summary", "policy_summary", "policy_catalyst", default=""))
    buys = _num(_pick(row, "Political Buys", "political_buys", "congress_buys")) or 0
    sells = _num(_pick(row, "Political Sells", "political_sells", "congress_sells")) or 0
    last_trade = _pick(row, "Political Last Trade Date", "political_last_trade_date", "last_political_trade")
    low = f"{signal} {summary}".lower()
    negative = any(x in low for x in ("negative", "bearish", "risk", "opposition", "restriction", "investigation"))
    positive = any(x in low for x in ("positive", "support", "benefit", "tailwind", "funding", "subsid", "contract", "incentive", "approval"))
    if summary and positive and not negative:
        return 83, f"Policy support: {summary.rstrip('.')} ."
    # Congressional trades are delayed and may only be a secondary supporting signal.
    if buys > sells and buys >= 2 and last_trade:
        return 68, f"Political disclosure support is positive with {int(buys)} reported buys versus {int(sells)} sells; disclosures are delayed and remain secondary evidence."
    return None


def build_plain_english_reasons(row: Mapping[str, Any], atlas_fair_value: float | None = None, current_price: float | None = None) -> list[str]:
    """Rank distinctive company evidence and return three concise, quantified reasons."""
    candidates: list[tuple[float, str, str]] = []
    rev = _simple_pct(_pick(row, "revenue_growth", "revenue_qoq_pct", "Revenue Growth"))
    earn = _simple_pct(_pick(row, "earnings_growth", "EPS Growth", "earnings_growth_pct"))
    gross = _simple_pct(_pick(row, "gross_margin", "gross_profit_margin", "Gross Margin"))
    operating = _simple_pct(_pick(row, "operating_margin", "operating_profit_margin", "Operating Margin"))
    margin = _simple_pct(_pick(row, "profit_margin", "net_profit_margin", "Profit Margin"))
    fcf = _num(_pick(row, "free_cashflow", "free_cash_flow", "Free Cash Flow"))
    cash = _num(_pick(row, "total_cash", "cash", "cash_and_equivalents", "Total Cash"))
    debt = _num(_pick(row, "total_debt", "debt", "Total Debt"))
    roic = _simple_pct(_pick(row, "roic", "ROIC"))
    forward_pe = _num(_pick(row, "forward_pe", "Forward P/E"))
    rsi = _num(_pick(row, "rsi", "RSI"))
    twenty = _simple_pct(_pick(row, "twenty_day_pct", "20 Day Return"))
    analyst = _clean(_pick(row, "recommendation", "recommendation_key", "Analyst View", default=""), default="").lower()

    fresh_news = _fresh_news_reason(row)
    if fresh_news:
        candidates.append((fresh_news[0], "fresh_news", fresh_news[1]))
    political_support = _political_support_reason(row)
    if political_support:
        candidates.append((political_support[0], "political_support", political_support[1]))

    if rev is not None:
        if rev >= 20:
            candidates.append((95 + min(rev, 50) / 10, "growth", f"Revenue growth is strong at {rev:.1f}%."))
        elif rev >= 10:
            candidates.append((82 + rev / 20, "growth", f"Revenue is growing at a healthy {rev:.1f}%."))
        elif rev > 0:
            candidates.append((58 + rev / 10, "growth", f"Revenue is still growing, but at a more measured {rev:.1f}% pace."))
    if earn is not None and earn > 8:
        candidates.append((88 + min(earn, 40) / 10, "earnings", f"Earnings are growing {earn:.1f}%, supporting the investment case."))
    if operating is not None and operating >= 20:
        candidates.append((89 + min(operating, 50) / 20, "profitability", f"Operating margin is a strong {operating:.1f}%."))
    elif margin is not None and margin >= 12:
        candidates.append((78 + margin / 20, "profitability", f"The company keeps {margin:.1f}% of sales as profit."))
    elif gross is not None and gross >= 55:
        candidates.append((76 + gross / 50, "profitability", f"Gross margin of {gross:.1f}% shows attractive unit economics."))
    if roic is not None and roic >= 12:
        candidates.append((87 + min(roic, 40) / 20, "returns", f"Return on invested capital is strong at {roic:.1f}%."))
    if fcf is not None and fcf > 0:
        scale = abs(fcf)
        amount = _fmt_money(fcf)
        candidates.append((70 + min(18, max(0, len(str(int(scale))) - 6) * 2), "cashflow", f"Free cash flow is positive at {amount}."))
    if cash is not None and debt is not None and cash > debt * 1.25:
        candidates.append((86, "balance_sheet", "Cash exceeds debt, giving the company financial flexibility."))
    if current_price and atlas_fair_value and atlas_fair_value > current_price:
        upside = ((atlas_fair_value - current_price) / current_price) * 100
        candidates.append((84 + min(upside, 40) / 20, "valuation", f"Shares trade about {upside:.1f}% below Atlas Fair Value."))
    elif forward_pe is not None and 0 < forward_pe <= 18:
        candidates.append((77, "valuation", f"Forward P/E of {forward_pe:.1f} is relatively undemanding."))
    if rsi is not None:
        if 45 <= rsi <= 62:
            candidates.append((72 + (62-rsi)/20, "momentum", f"RSI of {rsi:.0f} shows constructive momentum without looking overheated."))
        elif rsi < 40:
            candidates.append((64, "momentum", f"RSI of {rsi:.0f} suggests the stock may be stabilizing after weakness."))
    if twenty is not None and 3 <= twenty <= 15:
        candidates.append((71 + twenty/10, "trend", f"The stock has gained {twenty:.1f}% over the last month, confirming improving demand."))
    if "strong buy" in analyst or analyst == "buy":
        candidates.append((73, "analyst", "Wall Street sentiment is supportive rather than broadly cautious."))

    # Use company-specific saved evidence when it contains more than generic boilerplate.
    saved = _first_sentence(_pick(row, "what_looks_good", "why_ranked_high", "financial_summary", "recovery_catalyst", default=""))
    if saved and len(saved) >= 18 and not any(x in saved.lower() for x in ("high-priority research", "good candidate", "review full report")):
        candidates.append((80, "saved_evidence", saved + "."))

    candidates.sort(key=lambda x: x[0], reverse=True)
    reasons: list[str] = []
    used: set[str] = set()
    for _, category, text in candidates:
        if category in used or text in reasons:
            continue
        used.add(category)
        reasons.append(text)
        if len(reasons) == 4:
            break
    if not reasons:
        reasons.append("The available evidence is mixed, so Atlas recommends completing the full research review first.")
    return reasons


def build_primary_risk_sentence(row: Mapping[str, Any]) -> str:
    """Score actual company risks and return the single most material complete sentence."""
    risks: list[tuple[float, str]] = []
    cash = _num(_pick(row, "total_cash", "cash", "cash_and_equivalents", "Total Cash"))
    debt = _num(_pick(row, "total_debt", "debt", "Total Debt"))
    current_ratio = _num(_pick(row, "current_ratio", "Current Ratio"))
    forward_pe = _num(_pick(row, "forward_pe", "Forward P/E"))
    ps = _num(_pick(row, "price_to_sales", "ev_to_sales", "Price to Sales"))
    margin = _simple_pct(_pick(row, "profit_margin", "net_profit_margin", "Profit Margin"))
    rsi = _num(_pick(row, "rsi", "RSI"))
    atr_pct = _simple_pct(_pick(row, "atr_pct", "ATR %"))
    beta = _num(_pick(row, "beta", "Beta"))
    sector = _clean(_pick(row, "sector", "Sector", default=""), default="").lower()
    earnings_date = _pick(row, "earnings_date", "Earnings Date", "next_earnings_date")
    try:
        from datetime import date, datetime
        parsed = datetime.fromisoformat(str(earnings_date)[:10]).date()
        days = (parsed - date.today()).days
        if 0 <= days <= 7:
            risks.append((98, f"Earnings are due in {days} day{'s' if days != 1 else ''}, so near-term price swings could be sharp."))
        elif 8 <= days <= 21:
            risks.append((85, f"Earnings are due in {days} days and could change the investment case quickly."))
    except Exception:
        pass

    if debt is not None and cash is not None and debt > max(cash * 3, 1):
        ratio = debt / max(cash, 1)
        risks.append((95 + min(ratio, 10), f"Debt is about {ratio:.1f} times cash, which reduces financial flexibility."))
    elif debt is not None and cash is not None and debt > cash * 1.5:
        risks.append((82, "Debt is meaningfully higher than cash and deserves monitoring."))
    if current_ratio is not None and current_ratio < 0.8:
        risks.append((94, f"A current ratio of {current_ratio:.2f} signals tight short-term liquidity."))
    elif current_ratio is not None and current_ratio < 1.0:
        risks.append((84, f"A current ratio of {current_ratio:.2f} leaves less short-term liquidity cushion than preferred."))
    if forward_pe is not None and forward_pe >= 45:
        risks.append((91 + min(forward_pe-45, 30)/10, f"A forward P/E of {forward_pe:.1f} leaves little room for an earnings disappointment."))
    elif ps is not None and ps >= 10:
        risks.append((88, f"A price-to-sales multiple of {ps:.1f} reflects aggressive growth expectations."))
    if margin is not None and margin < 0:
        risks.append((93, f"The company remains unprofitable, with a net margin of {margin:.1f}%."))
    if rsi is not None and rsi >= 72:
        risks.append((86 + min(rsi-72, 15)/5, f"RSI of {rsi:.0f} suggests the stock may be overextended near term."))
    if atr_pct is not None and atr_pct >= 5:
        risks.append((80 + min(atr_pct, 12), f"Daily volatility is elevated, with ATR near {atr_pct:.1f}% of the share price."))
    if beta is not None and beta >= 1.7:
        risks.append((79 + min(beta, 3), f"A beta of {beta:.1f} means the stock may swing more sharply than the market."))
    if any(x in sector for x in ("energy", "materials", "gold", "mining", "semiconductor")):
        risks.append((72, "Results are sensitive to an industry cycle that can change quickly."))

    raw = _first_sentence(_pick(row, "what_could_go_wrong", "Primary Risk", "primary_risk", "risk_tags", default=""))
    if raw and not any(x in raw.lower() for x in ("earnings can create gap risk", "avoid oversized positions before the report")):
        raw = raw[:1].upper() + raw[1:]
        risks.append((76, raw + "."))

    if not risks:
        return "The main risk is that execution falls short of the growth already reflected in the share price."
    risks.sort(key=lambda x: x[0], reverse=True)
    return risks[0][1]
