"""Project Atlas Report Engine.

Orchestrates the reusable Atlas Research Report.
Section-specific logic lives in engines/report_sections/.
"""
from __future__ import annotations
from typing import Any
import streamlit as st
from ui.components import bullet_list, divider, recommendation_card, section_header
from engines.report_sections.formatting import fmt_score, safe_text
from engines.report_sections.recommendation import (
    build_classification,
    build_key_risks,
    build_recommendation,
    build_why_we_like_it,
)
from engines.report_sections.summary import render_bottom_line, render_executive_summary
from engines.report_sections.scorecard import render_investment_scorecard
from engines.report_sections.entry_plan import render_entry_plan
from engines.report_sections.supporting_research import render_supporting_research

def render_stock_report(row: dict[str, Any], source: str = "Latest AI Market Scan") -> None:
    """Render the standard Atlas stock research report."""
    ticker = safe_text(row.get("Ticker") or row.get("ticker") or row.get("Symbol"), "Ticker")
    company = safe_text(row.get("Company") or row.get("Name") or row.get("company"), "")
    recommendation = build_recommendation(row)
    classification = build_classification(row)
    confidence = fmt_score(row.get("Confidence") or row.get("Research Confidence") or row.get("AI Confidence"))

    section_header("🔎", f"Atlas Research Report: {ticker}", company if company else source)

    recommendation_card(
        recommendation=recommendation,
        classification=classification,
        confidence=confidence,
    )

    render_executive_summary(
        row=row,
        ticker=ticker,
        recommendation=recommendation,
        classification=classification,
    )

    render_entry_plan(row)
    render_investment_scorecard(row)

    c1, c2 = st.columns(2)
    with c1:
        bullet_list("Why Atlas Likes It", build_why_we_like_it(row), icon="✅")
    with c2:
        bullet_list("Key Risks", build_key_risks(row), icon="⚠️")

    render_supporting_research(row)
    divider()
    render_bottom_line(row, ticker, recommendation)
