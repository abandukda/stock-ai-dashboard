"""Supporting research expandable sections."""
from __future__ import annotations
from typing import Any
import streamlit as st
from ui.components import info_card, section_header
from engines.report_sections.formatting import safe_text

def render_supporting_research(row: dict[str, Any]) -> None:
    section_header("🔍", "Supporting Research", "Evidence is available for members who want to go deeper.")
    with st.expander("💰 Financial Strength", expanded=False):
        info_card("AI Financial Summary", safe_text(row.get("Finance Agent Bottom Line") or row.get("Financial Summary") or "Financial details are summarized from the latest scan data."), icon="💰")
    with st.expander("🏛 Wall Street Analyst Intelligence", expanded=False):
        info_card("AI Analyst Summary", safe_text(row.get("Analyst Summary") or row.get("Analyst Support") or "Analyst detail will be expanded in the Analyst Intelligence module."), icon="🏛")
    with st.expander("📈 Technical Setup", expanded=False):
        info_card("AI Technical Summary", safe_text(row.get("Technical Summary") or row.get("Chart Guidance") or "Technical setup is based on trend, momentum, volume, and risk/reward."), icon="📈")
    with st.expander("📰 News & Catalysts", expanded=False):
        info_card("AI News Summary", safe_text(row.get("News Summary") or row.get("Top News") or "No major news summary available from the latest scan."), icon="📰")
    with st.expander("🏛️ Political Intelligence", expanded=False):
        info_card("Political Trading Summary", safe_text(row.get("Political Summary") or "Political intelligence will show relevant House and Senate trading disclosures when available."), icon="🏛️")
    with st.expander("📞 Earnings Intelligence", expanded=False):
        info_card("Earnings Summary", safe_text(row.get("Earnings Summary") or "Earnings transcript and guidance intelligence will appear here when available."), icon="📞")
