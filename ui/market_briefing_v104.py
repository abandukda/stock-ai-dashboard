"""
Atlas V104.1 — Compact Market and Earnings Briefing

Drop-in replacement for ui/market_briefing_v104.py.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import streamlit as st


def render_v104_earnings_briefing(
    pipeline: Mapping[str, Any],
) -> None:
    rows = pipeline.get("ranked_candidates") or []

    earnings = [
        {
            "Ticker": row.get("ticker"),
            "Company": row.get("company"),
            "Next Earnings": row.get("next_earnings_date"),
            "Committee Verdict": str(
                row.get("committee_verdict") or "MONITOR"
            ).replace("_", " ").title(),
            "Opportunity": row.get("opportunity_score"),
            "Confidence": row.get("confidence_pct"),
        }
        for row in rows
        if row.get("next_earnings_date")
    ]

    with st.expander("Upcoming Earnings", expanded=False):
        if earnings:
            st.dataframe(
                pd.DataFrame(earnings[:20]),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Opportunity": st.column_config.NumberColumn(
                        format="%.1f"
                    ),
                    "Confidence": st.column_config.NumberColumn(
                        format="%.1f%%"
                    ),
                },
            )
        else:
            st.info(
                "No upcoming earnings dates were included in the saved scan."
            )


__all__ = ["render_v104_earnings_briefing"]
