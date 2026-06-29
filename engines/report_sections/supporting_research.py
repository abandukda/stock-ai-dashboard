"""
Atlas V60.0 Supporting Research.
Keeps all intelligence inside report_sections architecture.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.components import info_card, metric_card, section_header
from engines.report_sections.formatting import safe_num, safe_text
from engines.analyst_engine import render_analyst_intelligence


def _pick(row: dict[str, Any], *keys: str, default=None):
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "null", "n/a", "na"}:
            return value
    return default


def _has(value) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() not in {"", "nan", "none", "null", "n/a", "na"}



def _clean_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in {"", "na", "n/a", "none", "null", "unavailable"}:
        return None
    mult = 1
    text = text.replace("$","").replace(",","").replace("%","").replace("x","")
    if text.endswith("B"):
        mult=1_000_000_000
        text=text[:-1]
    elif text.endswith("M"):
        mult=1_000_000
        text=text[:-1]
    elif text.endswith("K"):
        mult=1_000
        text=text[:-1]
    try:
        return float(text)*mult
    except Exception:
        return None

def _fmt_ratio(value) -> str:
    n=_clean_number(value)
    return "—" if n is None else f"{n:.2f}"

def _fmt_pct(value) -> str:
    n=_clean_number(value)
    return "—" if n is None else f"{n:.1f}%"

def _fmt_money(value) -> str:
    n=_clean_number(value)
    if n is None:
        return "—"
    if abs(n)>=1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    if abs(n)>=1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n)>=1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:,.2f}"


def _finance_label(score) -> str:
    n = safe_num(score, 0)
    if n >= 85:
        return "Elite"
    if n >= 75:
        return "Strong"
    if n >= 65:
        return "Constructive"
    if n >= 50:
        return "Speculative"
    if n > 0:
        return "Weak"
    return "Unavailable"


def _render_finance_agent(row: dict[str, Any]) -> None:
    section_header(
        "💰",
        "Finance Agent — Deep Financial Execution",
        "Cross-checks revenue, EPS, liquidity, debt, margins, cash flow, valuation, and execution quality.",
    )

    score = _pick(row, "finance_agent_score", "financial_score", "fundamentals_agent_score")
    score_text = f"{safe_num(score):.0f}/100" if _has(score) else "Unavailable"
    label = _finance_label(score)

    rev = _pick(row, "revenue_qoq_pct", "revenue_growth")
    gross = _pick(row, "gross_profit_margin", "gross_margin")
    op_margin = _pick(row, "operating_profit_margin", "operating_margin")
    net_margin = _pick(row, "net_profit_margin", "profit_margin")
    debt_eq = _pick(row, "debt_to_equity")
    current = _pick(row, "current_ratio")
    roic = _pick(row, "roic")
    fcf = _pick(row, "free_cash_flow", "free_cashflow")
    ocf = _pick(row, "operating_cash_flow", "operating_cashflow")
    ev_sales = _pick(row, "ev_to_sales", "price_to_sales")
    eps = _pick(row, "latest_eps")
    beats = _pick(row, "eps_beats_last4")
    misses = _pick(row, "eps_misses_last4")

    summary = _pick(row, "finance_agent_bottom_line", "financial_summary")
    if not _has(summary):
        summary_parts = [f"Atlas rates the financial profile as {label} based on the latest completed scan."]
        if _has(rev):
            summary_parts.append(f"Revenue growth shows {safe_num(rev):.1f}% momentum.")
        if _has(gross):
            summary_parts.append(f"Gross margin is {_fmt_pct(gross)}.")
        if _has(fcf):
            summary_parts.append(f"Free cash flow is {_fmt_money(fcf)}.")
        summary = " ".join(summary_parts)

    info_card("Financial Quality Summary", safe_text(summary), icon="💰")

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Finance Score", score_text, f"Status: {label}")
    with c2:
        metric_card("Revenue Growth", _fmt_pct(rev), "QoQ or latest scan growth field")
    with c3:
        metric_card("Latest EPS", "—" if not _has(eps) else str(eps), "Latest reported EPS when available")

    c4, c5, c6 = st.columns(3)
    with c4:
        metric_card("Gross Margin", _fmt_pct(gross), "Gross profitability")
    with c5:
        metric_card("Operating Margin", _fmt_pct(op_margin), "Operating execution")
    with c6:
        metric_card("Net Margin", _fmt_pct(net_margin), "Bottom-line profitability")

    c7, c8, c9 = st.columns(3)
    with c7:
        metric_card("Debt / Equity", _fmt_ratio(debt_eq), "Balance sheet leverage")
    with c8:
        metric_card("Current Ratio", _fmt_ratio(current), "Short-term liquidity")
    with c9:
        metric_card("ROIC", _fmt_pct(roic), "Return on invested capital")

    c10, c11, c12 = st.columns(3)
    with c10:
        beat_text = "Unavailable" if not _has(beats) and not _has(misses) else f"{safe_num(beats):.0f}/{safe_num(misses):.0f}"
        metric_card("EPS Beats / Misses", beat_text, "Last 4 reported quarters")
    with c11:
        metric_card("Free Cash Flow", _fmt_money(fcf), "Cash generation")
    with c12:
        metric_card("Operating Cash Flow", _fmt_money(ocf), "Operating cash engine")

    c13, c14, c15 = st.columns(3)
    with c13:
        metric_card("EV / Sales", _fmt_ratio(ev_sales), "Valuation multiple")
    with c14:
        metric_card("Total Debt", _fmt_money(_pick(row, "total_debt")), "Debt load")
    with c15:
        metric_card("Cash", _fmt_money(_pick(row, "cash_and_equivalents", "total_cash")), "Cash position")

    findings = _pick(row, "finance_agent_findings", "what_looks_good")
    risks = _pick(row, "finance_agent_risks", "what_could_go_wrong")
    if _has(findings):
        info_card("What Looks Good", safe_text(findings), icon="✅")
    if _has(risks):
        info_card("What Could Go Wrong", safe_text(risks), icon="⚠️")


def render_supporting_research(row: dict[str, Any]) -> None:
    section_header("🔍", "Supporting Research", "Evidence is available for members who want to go deeper.")

    with st.expander("💰 Financial Strength", expanded=False):
        _render_finance_agent(row)

    with st.expander("🏛 Wall Street Analyst Intelligence", expanded=False):
        render_analyst_intelligence(row)

    with st.expander("📞 Earnings Intelligence", expanded=False):
        info_card(
            "Earnings Summary",
            safe_text(row.get("Earnings Summary") or row.get("earnings_summary") or "Earnings transcript and guidance intelligence will appear here when available."),
            icon="📞",
        )

    with st.expander("📈 Technical Setup", expanded=False):
        info_card(
            "AI Technical Summary",
            safe_text(row.get("Technical Summary") or row.get("technical_summary") or row.get("v42_chart_guidance") or "Technical setup is based on trend, momentum, volume, and risk/reward."),
            icon="📈",
        )

    with st.expander("📰 News & Catalysts", expanded=False):
        info_card(
            "AI News Summary",
            safe_text(row.get("News Summary") or row.get("news_summary") or row.get("top_news_headline") or row.get("Top News") or "No major news summary available from the latest scan."),
            icon="📰",
        )

    with st.expander("🏛️ Political Intelligence", expanded=False):
        info_card(
            "Political Trading Summary",
            safe_text(row.get("Political Summary") or row.get("political_summary") or "Political intelligence will show relevant House and Senate trading disclosures when available."),
            icon="🏛️",
        )
