"""
Atlas V102 Market / Earnings Briefing

Presentation-only UI for upcoming earnings, guidance, and transcript context
from the canonical V102 pipeline.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import streamlit as st


def render_v102_earnings_briefing(
    pipeline: Mapping[str, Any],
) -> None:
    """Render upcoming earnings and transcript/guidance intelligence."""
    rows = pipeline.get("canonical_rows") or []

    earnings_rows = []
    research_rows = []

    for row in rows:
        next_earnings = row.get("next_earnings_date")
        earnings_summary = row.get("earnings_summary")
        transcript_url = row.get("transcript_url")
        guidance = row.get("guidance")

        if next_earnings:
            earnings_rows.append(
                {
                    "Ticker": row.get("ticker"),
                    "Company": row.get("company"),
                    "Next Earnings": next_earnings,
                    "Atlas Action": row.get("action_code"),
                    "Confidence": row.get("confidence_pct"),
                }
            )

        if earnings_summary or transcript_url or guidance:
            research_rows.append(
                {
                    "Ticker": row.get("ticker"),
                    "Company": row.get("company"),
                    "Transcript": (
                        "Available" if transcript_url else "Not linked"
                    ),
                    "Earnings / Transcript Summary": (
                        earnings_summary
                        or "Not included in the current saved scan"
                    ),
                    "Guidance": (
                        guidance
                        or "Not included in the current saved scan"
                    ),
                }
            )

    st.markdown("## Upcoming Earnings")

    if earnings_rows:
        st.dataframe(
            pd.DataFrame(earnings_rows[:30]),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info(
            "No upcoming earnings dates were included in the current saved scan."
        )

    st.markdown("## Earnings, Guidance & Transcript Intelligence")

    if research_rows:
        st.dataframe(
            pd.DataFrame(research_rows[:30]),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info(
            "No transcript or structured guidance fields were included in "
            "the current saved scan. Existing live-research and earnings "
            "pages remain available elsewhere in Atlas."
        )


__all__ = ["render_v102_earnings_briefing"]
