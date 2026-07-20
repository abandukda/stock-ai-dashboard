"""
Atlas V102 Canonical Command Center

Presentation-only UI for the canonical V102 pipeline.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import streamlit as st


def render_v102_command_center(pipeline: Mapping[str, Any]) -> None:
    """Render the subscriber-facing V102 command center."""
    summary = pipeline.get("summary") or {}
    ranked = pipeline.get("ranked_candidates") or []
    selected = pipeline.get("selected_candidates") or []

    st.markdown("## Atlas V102 Canonical Command Center")
    st.caption(
        "Scanner → canonical adapter → ranking → calibrated confidence "
        "→ diversified opportunity selection."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Received", int(summary.get("received", 0) or 0))
    c2.metric("Eligible & Complete", int(summary.get("eligible", 0) or 0))
    c3.metric("Portfolio Candidates", int(summary.get("selected", 0) or 0))
    c4.metric("Atlas Buy Now", int(summary.get("buy_now", 0) or 0))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Accumulate", int(summary.get("accumulate", 0) or 0))
    c6.metric("Monitor", int(summary.get("monitor", 0) or 0))
    c7.metric(
        "Incomplete / Excluded",
        int(summary.get("excluded_or_incomplete", 0) or 0),
    )

    average_confidence = (
        sum(float(row.get("confidence_pct") or 0) for row in ranked)
        / len(ranked)
        if ranked
        else 0.0
    )
    c8.metric("Avg Calibrated Confidence", f"{average_confidence:.1f}%")

    st.markdown("### Today’s Best Opportunities")

    if not selected:
        st.warning(
            "No candidates passed the canonical completeness and "
            "portfolio-selection filters."
        )
    else:
        opportunity_rows = []
        for row in selected:
            opportunity_rows.append(
                {
                    "Rank": row.get("overall_rank"),
                    "Ticker": row.get("ticker"),
                    "Company": row.get("company"),
                    "Atlas Action": row.get("action_code"),
                    "Opportunity": row.get("opportunity_score"),
                    "Confidence": row.get("confidence_pct"),
                    "Tier": row.get("opportunity_tier"),
                    "Market Position": row.get("top_percentile_text"),
                    "Price": row.get("current_price"),
                    "Validated Fair Value": row.get("atlas_fair_value"),
                    "Expected Return %": row.get("expected_return_pct"),
                    "Research %": row.get("research_completeness_pct"),
                }
            )

        st.dataframe(
            pd.DataFrame(opportunity_rows),
            hide_index=True,
            use_container_width=True,
        )

    st.markdown("### Sector Leadership")

    sector_scores: dict[str, list[float]] = {}
    for row in ranked:
        sector = str(row.get("sector") or "Unknown")
        score = row.get("opportunity_score")
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            continue
        sector_scores.setdefault(sector, []).append(score_value)

    sector_table = [
        {
            "Sector": sector,
            "Average Opportunity": round(sum(scores) / len(scores), 1),
            "Candidates": len(scores),
        }
        for sector, scores in sector_scores.items()
        if scores
    ]
    sector_table.sort(
        key=lambda item: item["Average Opportunity"],
        reverse=True,
    )

    if sector_table:
        st.dataframe(
            pd.DataFrame(sector_table),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No complete sector-ranking data is available yet.")


__all__ = ["render_v102_command_center"]
