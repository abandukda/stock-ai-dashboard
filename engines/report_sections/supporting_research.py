
"""
Supporting research expandable sections.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.components import info_card, section_header
from engines.report_sections.formatting import safe_text
from engines.analyst_engine import render_analyst_intelligence
from engines.finance_engine import render_finance_agent


def render_supporting_research(row: dict[str, Any]) -> None:
    section_header("🔍", "Supporting Research", "Evidence is available for members who want to go deeper.")

    with st.expander("💰 Financial Strength", expanded=False):
        render_finance_agent(row)

    with st.expander("🏛 Wall Street Analyst Intelligence", expanded=False):
        render_analyst_intelligence(row)

    with st.expander("📞 Earnings Intelligence", expanded=False):
        info_card(
            "Earnings Summary",
            safe_text(
                row.get("Earnings Summary")
                or row.get("earnings_summary")
                or "Earnings transcript and guidance intelligence will appear here when available."
            ),
            icon="📞",
        )

    with st.expander("📈 Technical Setup", expanded=False):
        info_card(
            "AI Technical Summary",
            safe_text(
                row.get("Technical Summary")
                or row.get("technical_summary")
                or row.get("v42_chart_guidance")
                or "Technical setup is based on trend, momentum, volume, and risk/reward."
            ),
            icon="📈",
        )

    with st.expander("📰 News & Catalysts", expanded=False):
        info_card(
            "AI News Summary",
            safe_text(
                row.get("News Summary")
                or row.get("news_summary")
                or row.get("top_news_headline")
                or row.get("Top News")
                or "No major news summary available from the latest scan."
            ),
            icon="📰",
        )

    with st.expander("🏛️ Political Intelligence", expanded=False):
        info_card(
            "Political Trading Summary",
            safe_text(
                row.get("Political Summary")
                or row.get("political_summary")
                or "Political intelligence will show relevant House and Senate trading disclosures when available."
            ),
            icon="🏛️",
        )
