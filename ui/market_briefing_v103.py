"""
Atlas V103 — Compact Market Briefing

Presentation-only UI for upcoming earnings and guidance.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import streamlit as st


def render_v103_earnings_briefing(
    pipeline: Mapping[str, Any],
) -> None:
    """Render V103 earnings and guidance intelligence."""
    rows = pipeline.get("ranked_candidates") or []

    earnings_rows = []
    guidance_rows = []

    for row in rows:
        if row.get("next_earnings_date"):
            earnings_rows.append(
                {
                    "Ticker": row.get("ticker"),
                    "Company": row.get("company"),
                    "Next Earnings": row.get(
                        "next_earnings_date"
                    ),
                    "Atlas Decision": row.get("action_code"),
                    "Confidence": row.get("confidence_pct"),
                }
            )

        if row.get("guidance"):
            guidance_rows.append(
                {
                    "Ticker": row.get("ticker"),
                    "Company": row.get("company"),
                    "Guidance": row.get("guidance"),
                }
            )

    st.markdown("## Upcoming Earnings")

    if earnings_rows:
        st.dataframe(
            pd.DataFrame(earnings_rows[:20]),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info(
            "No upcoming earnings dates were included in the saved scan."
        )

    with st.expander(
        "Earnings Guidance & Transcript Intelligence",
        expanded=False,
    ):
        if guidance_rows:
            st.dataframe(
                pd.DataFrame(guidance_rows[:20]),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info(
                "No structured earnings guidance was included "
                "in the saved scan."
            )


__all__ = ["render_v103_earnings_briefing"]
