
"""Investment scorecard section."""
from __future__ import annotations
from typing import Any
import streamlit as st
from ui.components import metric_card, section_header
from engines.report_sections.formatting import fmt_pct, fmt_score, safe_text

def render_investment_scorecard(row: dict[str, Any]) -> None:
    section_header("📊", "Atlas Scorecard™", "Quick view of the main decision drivers.")

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Atlas Conviction™", fmt_score(row.get("Opportunity") or row.get("Final Conviction") or row.get("Score")), "How attractive this setup looks today.")
    with c2:
        metric_card("Atlas Quality™", fmt_score(row.get("Quality") or row.get("Financial Health") or row.get("Finance Agent Score")), "Business and financial quality signal.")
    with c3:
        metric_card("Atlas Confidence™", fmt_score(row.get("Confidence") or row.get("Research Confidence") or row.get("AI Confidence")), "How aligned the evidence appears.")

    c4, c5, c6 = st.columns(3)
    with c4:
        metric_card("Modeled Upside", fmt_pct(row.get("Target Upside %") or row.get("Upside")), "Upside from current scan target.")
    with c5:
        metric_card("Risk / Reward", safe_text(row.get("Risk/Reward") or row.get("Risk Reward"), "N/A"), "Modeled reward compared with downside.")
    with c6:
        metric_card("Political Signal", safe_text(row.get("Political Signal"), "Coming soon"), "Supporting signal, not a primary driver.")
