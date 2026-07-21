"""
Atlas V104 — Compact Market and Earnings Briefing
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
            "Committee Verdict": row.get("committee_verdict"),
            "Confidence": row.get("confidence_pct"),
        }
        for row in rows
        if row.get("next_earnings_date")
    ]

    st.markdown("## Upcoming Earnings")
    if earnings:
        st.dataframe(
            pd.DataFrame(earnings[:20]),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No upcoming earnings dates were included in the saved scan.")


__all__ = ["render_v104_earnings_briefing"]
