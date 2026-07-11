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

def _simple_pct(value: Any) -> float | None:
    n = _num(value)
    if n is None:
        return None
    return n * 100 if abs(n) <= 1 else n


def build_plain_english_reasons(row: Mapping[str, Any], atlas_fair_value: float | None = None, current_price: float | None = None) -> list[str]:
    """Return up to four short reasons a newer investor can understand."""
    reasons: list[str] = []
    rev = _simple_pct(_pick(row, "revenue_growth", "Revenue Growth"))
    margin = _simple_pct(_pick(row, "profit_margin", "Profit Margin"))
    fcf = _num(_pick(row, "free_cashflow", "free_cash_flow", "Free Cash Flow"))
    cash = _num(_pick(row, "total_cash", "cash", "Total Cash"))
    debt = _num(_pick(row, "total_debt", "debt", "Total Debt"))
    rsi = _num(_pick(row, "rsi", "RSI"))

    if rev is not None:
        if rev >= 15:
            reasons.append("Revenue is growing at a strong pace.")
        elif rev > 0:
            reasons.append("Revenue is still moving in the right direction.")
    if margin is not None and margin >= 10:
        reasons.append("The business is converting sales into healthy profits.")
    if fcf is not None and fcf > 0:
        reasons.append("The company is generating positive free cash flow.")
    if cash is not None and debt is not None:
        if cash > debt:
            reasons.append("Cash exceeds debt, giving the company financial flexibility.")
        elif debt > cash * 2:
            reasons.append("Growth remains attractive, but debt deserves attention.")
    if current_price and atlas_fair_value and atlas_fair_value > current_price:
        reasons.append("Shares trade below Atlas Fair Value.")
    if rsi is not None and 45 <= rsi <= 68:
        reasons.append("Price momentum is constructive without looking overheated.")

    if not reasons:
        reasons.append("The combined financial and market evidence warrants further research.")
    return reasons[:4]


def build_primary_risk_sentence(row: Mapping[str, Any]) -> str:
    """Convert verbose scan risk text into one complete, actionable sentence."""
    raw = _clean(_pick(row, "what_could_go_wrong", "Primary Risk", "primary_risk", "risk_tags", default=""), default="")
    low = raw.lower()
    if "earnings" in low or "gap risk" in low:
        return "Upcoming earnings could create sharp price swings."
    if "debt" in low and "cash" in low:
        return "Debt is high relative to cash and could limit financial flexibility."
    if "current ratio" in low or "liquidity" in low:
        return "Short-term liquidity is weaker than preferred."
    if "valuation" in low or "expensive" in low or "multiple" in low:
        return "The current valuation leaves less room for execution mistakes."
    if "momentum" in low or "technical" in low or "trend" in low:
        return "Price momentum has not yet confirmed a durable uptrend."
    if raw:
        first = raw.split(";")[0].strip().rstrip(".")
        if first:
            return first[:1].upper() + first[1:] + "."
    return "The investment case still depends on execution, earnings, and entry timing."
