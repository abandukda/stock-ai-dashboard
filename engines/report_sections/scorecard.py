"""Investment scorecard section."""
from __future__ import annotations
from typing import Any
import streamlit as st
from ui.components import metric_card, section_header
from engines.report_sections.formatting import fmt_pct, fmt_score, safe_text

def render_investment_scorecard(row: dict[str, Any]) -> None:
    section_header("📊", "Investment Scorecard", "Quick view of the main decision drivers.")
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Opportunity", fmt_score(row.get("Opportunity") or row.get("Final Conviction") or row.get("Score")))
    with c2:
        metric_card("Quality", fmt_score(row.get("Quality") or row.get("Financial Health") or row.get("Finance Agent Score")))
    with c3:
        metric_card("Confidence", fmt_score(row.get("Confidence") or row.get("Research Confidence") or row.get("AI Confidence")))
    c4, c5, c6 = st.columns(3)
    with c4:
        metric_card("Modeled Upside", fmt_pct(row.get("Target Upside %") or row.get("Upside")))
    with c5:
        metric_card("Risk / Reward", safe_text(row.get("Risk/Reward") or row.get("Risk Reward"), "N/A"))
    with c6:
        metric_card("Political Signal", safe_text(row.get("Political Signal"), "Coming soon"))
