"""
Project Atlas Report Engine

Single reusable stock report renderer.
Goal: every page calls this same engine instead of duplicating report logic.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.components import (
    section_header,
    recommendation_card,
    metric_card,
    info_card,
    warning_card,
    bullet_list,
    divider,
)


def _safe_text(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return default
    return text


def _safe_num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace("%", "").replace(",", "").strip()
            if not value:
                return default
        return float(value)
    except Exception:
        return default


def _fmt_score(value: Any) -> str:
    score = _safe_num(value, 0)
    return f"{score:.0f}/100"


def _fmt_pct(value: Any) -> str:
    pct = _safe_num(value, 0)
    return f"{pct:.1f}%"


def _fmt_money(value: Any) -> str:
    num = _safe_num(value, 0)
    if num == 0:
        return "N/A"
    return f"${num:,.2f}"


def build_classification(row: dict[str, Any]) -> str:
    quality = _safe_num(
        row.get("Quality")
        or row.get("Quality Score")
        or row.get("Financial Health")
        or row.get("Financial Health Score")
        or row.get("Finance Agent Score")
    )
    upside = _safe_num(
        row.get("Upside")
        or row.get("Upside %")
        or row.get("Target Upside %")
        or row.get("Upside Potential %")
    )
    analyst = _safe_num(
        row.get("Analyst Score")
        or row.get("Analyst Support Score")
        or row.get("Wall Street Score")
        or row.get("Research Confidence")
    )

    if quality >= 85:
        return "🏆 Elite Quality"
    if quality >= 75:
        return "✅ Quality Growth"
    if upside >= 100:
        return "⚡ High Opportunity"
    if analyst >= 80:
        return "📈 Analyst Favorite"
    return "🔎 Research Candidate"


def build_recommendation(row: dict[str, Any]) -> str:
    raw = _safe_text(
        row.get("Recommendation")
        or row.get("Verdict")
        or row.get("Final Verdict")
        or row.get("Action"),
        "Review",
    )

    upper = raw.upper()

    if "BUY NOW" in upper or upper == "BUY" or "STRONG BUY" in upper:
        return "✅ BUY NOW"
    if "GRADUAL" in upper or "WEAKNESS" in upper:
        return "🟡 BUY GRADUALLY"
    if "AVOID" in upper or "SELL" in upper:
        return "🔴 AVOID"
    if "HOLD" in upper or "WATCH" in upper:
        return "⚪ WATCH"
    return raw


def build_why_we_like_it(row: dict[str, Any]) -> list[str]:
    bullets: list[str] = []

    quality = _safe_num(row.get("Quality") or row.get("Financial Health") or row.get("Finance Agent Score"))
    upside = _safe_num(row.get("Target Upside %") or row.get("Upside") or row.get("Upside %"))
    rr = _safe_num(row.get("Risk/Reward") or row.get("Risk Reward"))
    analyst = _safe_text(row.get("Analyst Support") or row.get("Analyst View"), "")

    if quality >= 75:
        bullets.append("Financial quality appears supportive of the investment case.")
    if upside >= 15:
        bullets.append("The current target framework suggests meaningful upside potential.")
    if rr >= 1.5:
        bullets.append("The risk/reward profile is favorable based on the latest scan.")
    if analyst and analyst != "N/A":
        bullets.append(f"Wall Street support appears constructive: {analyst}.")
    if _safe_num(row.get("RSI")) > 45:
        bullets.append("Technical momentum does not appear severely weak.")

    if not bullets:
        bullets.append("The stock has enough supporting signals to justify further review.")

    return bullets[:5]


def build_key_risks(row: dict[str, Any]) -> list[str]:
    risks: list[str] = []

    quality = _safe_num(row.get("Quality") or row.get("Financial Health") or row.get("Finance Agent Score"))
    upside = _safe_num(row.get("Target Upside %") or row.get("Upside") or row.get("Upside %"))
    atr = _safe_num(row.get("ATR %"))
    thesis_risk = _safe_text(row.get("Primary Risk") or row.get("Risk") or row.get("What Could Go Wrong"), "")

    if thesis_risk and thesis_risk != "N/A":
        risks.append(thesis_risk)
    if quality and quality < 70:
        risks.append("Financial quality is not yet strong enough to remove execution risk.")
    if upside >= 75:
        risks.append("Very high upside estimates can carry higher uncertainty.")
    if atr >= 6:
        risks.append("Volatility is elevated, so position sizing should be conservative.")

    risks.append("Market sentiment, earnings results, and analyst revisions can change the thesis.")

    return risks[:5]


def render_investment_scorecard(row: dict[str, Any]) -> None:
    section_header("📊", "Investment Scorecard", "Quick view of the main decision drivers.")

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Opportunity", _fmt_score(row.get("Opportunity") or row.get("Final Conviction") or row.get("Score")))
    with c2:
        metric_card("Quality", _fmt_score(row.get("Quality") or row.get("Financial Health") or row.get("Finance Agent Score")))
    with c3:
        metric_card("Confidence", _fmt_score(row.get("Confidence") or row.get("Research Confidence") or row.get("AI Confidence")))

    c4, c5, c6 = st.columns(3)
    with c4:
        metric_card("Upside", _fmt_pct(row.get("Target Upside %") or row.get("Upside")))
    with c5:
        metric_card("Risk / Reward", str(row.get("Risk/Reward") or row.get("Risk Reward") or "N/A"))
    with c6:
        metric_card("Political Signal", _safe_text(row.get("Political Signal"), "Coming soon"))


def render_entry_plan(row: dict[str, Any]) -> None:
    section_header("🎯", "Entry Plan", "Suggested trade structure from the latest scan.")

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Entry", _safe_text(row.get("Entry") or row.get("Entry Range") or row.get("Buy Zone"), "Review setup"))
    with c2:
        metric_card("Stop", _safe_text(row.get("Stop") or row.get("Stop Loss"), "Use risk controls"))
    with c3:
        metric_card("Target", _safe_text(row.get("Target") or _fmt_money(row.get("AI Fair Value")), "Review target"))


def render_supporting_research(row: dict[str, Any]) -> None:
    section_header("🔍", "Supporting Research", "Evidence is available for members who want to go deeper.")

    with st.expander("💰 Financial Strength", expanded=False):
        info_card(
            "AI Financial Summary",
            _safe_text(
                row.get("Finance Agent Bottom Line")
                or row.get("Financial Summary")
                or "Financial details are summarized from the latest scan data."
            ),
            icon="💰",
        )

    with st.expander("🏛 Wall Street Analyst Intelligence", expanded=False):
        info_card(
            "AI Analyst Summary",
            _safe_text(
                row.get("Analyst Summary")
                or row.get("Analyst Support")
                or "Analyst detail will be expanded in the Analyst Intelligence module."
            ),
            icon="🏛",
        )

    with st.expander("📈 Technical Setup", expanded=False):
        info_card(
            "AI Technical Summary",
            _safe_text(
                row.get("Technical Summary")
                or row.get("Chart Guidance")
                or "Technical setup is based on trend, momentum, volume, and risk/reward."
            ),
            icon="📈",
        )

    with st.expander("📰 News & Catalysts", expanded=False):
        info_card(
            "AI News Summary",
            _safe_text(
                row.get("News Summary")
                or row.get("Top News")
                or "No major news summary available from the latest scan."
            ),
            icon="📰",
        )

    with st.expander("🏛️ Political Intelligence", expanded=False):
        info_card(
            "Political Trading Summary",
            _safe_text(
                row.get("Political Summary")
                or "Political intelligence will show relevant House and Senate trading disclosures when available."
            ),
            icon="🏛️",
        )


def render_stock_report(row: dict[str, Any], source: str = "Latest AI Market Scan") -> None:
    ticker = _safe_text(row.get("Ticker") or row.get("ticker") or row.get("Symbol"), "Ticker")
    company = _safe_text(row.get("Company") or row.get("Name") or row.get("company"), "")

    recommendation = build_recommendation(row)
    classification = build_classification(row)
    confidence = _fmt_score(row.get("Confidence") or row.get("Research Confidence") or row.get("AI Confidence"))

    section_header("📌", f"{ticker} Research Report", company if company else source)

    recommendation_card(
        recommendation=recommendation,
        classification=classification,
        confidence=confidence,
    )

    info_card(
        "Executive Summary",
        _safe_text(
            row.get("Executive Summary")
            or row.get("Investment Thesis")
            or row.get("Research Summary")
            or f"{ticker} is being reviewed using the latest AI market scan. The report summarizes opportunity, quality, analyst support, risk, and supporting evidence in plain English."
        ),
        icon="🤖",
    )

    render_investment_scorecard(row)

    c1, c2 = st.columns(2)
    with c1:
        bullet_list("Why We Like It", build_why_we_like_it(row), icon="✅")
    with c2:
        bullet_list("Key Risks", build_key_risks(row), icon="⚠️")

    render_entry_plan(row)

    render_supporting_research(row)

    divider()

    info_card(
        "Bottom Line",
        _safe_text(
            row.get("Bottom Line")
            or f"{ticker} currently receives a {recommendation} rating based on the latest available scan data. Investors should review the supporting evidence, position sizing, and risk factors before making a decision."
        ),
        icon="🧭",
    )