"""
Atlas V103 — Institutional Command Center

Presentation-only UI for the V103 integrated institutional pipeline.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import streamlit as st


def render_v103_command_center(
    pipeline: Mapping[str, Any],
) -> None:
    """Render the V103 institutional command center."""
    summary = pipeline.get("summary") or {}
    ranked = pipeline.get("ranked_candidates") or []
    selected = pipeline.get("selected_candidates") or []

    st.markdown("# Atlas V103 Institutional Command Center")
    st.caption(
        "Institutional scoring, calibrated confidence, political support, "
        "risk controls, and diversified opportunity selection."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Reviewed", int(summary.get("received", 0) or 0))
    c2.metric("Eligible & Scored", int(summary.get("eligible", 0) or 0))
    c3.metric(
        "Portfolio Candidates",
        int(summary.get("selected", 0) or 0),
    )
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
    c8.metric("Avg Confidence", f"{average_confidence:.1f}%")

    st.markdown("## Today’s Best Opportunities")

    if not selected:
        st.warning(
            "No stocks were selected. Open the diagnostics section below "
            "to review field coverage."
        )
    else:
        table_rows = []
        for row in selected:
            table_rows.append(
                {
                    "Rank": row.get("overall_rank"),
                    "Ticker": row.get("ticker"),
                    "Company": row.get("company"),
                    "Atlas Decision": row.get("action_code"),
                    "Opportunity": row.get("opportunity_score"),
                    "Confidence": row.get("confidence_pct"),
                    "Tier": row.get("opportunity_tier"),
                    "Market Position": row.get(
                        "top_percentile_text"
                    ),
                    "Price": row.get("current_price"),
                    "Fair Value": row.get(
                        "validated_fair_value"
                    ),
                    "Expected Return %": row.get(
                        "expected_return_pct"
                    ),
                    "Evidence Coverage %": row.get(
                        "component_coverage_pct"
                    ),
                }
            )

        st.dataframe(
            pd.DataFrame(table_rows),
            hide_index=True,
            use_container_width=True,
        )

    with st.expander("Opportunity Details", expanded=False):
        for row in selected[:8]:
            st.markdown(
                f"### {row.get('ticker')} — {row.get('company')}"
            )
            d1, d2, d3 = st.columns(3)
            d1.metric("Opportunity", row.get("opportunity_score"))
            d2.metric(
                "Confidence",
                f"{float(row.get('confidence_pct') or 0):.1f}%",
            )
            d3.metric("Decision", row.get("action_code"))

            if row.get("investment_thesis"):
                st.write(row["investment_thesis"])

            if row.get("primary_risk"):
                st.caption(
                    f"Primary risk: {row['primary_risk']}"
                )

            st.markdown("---")

    with st.expander(
        "V103 Pipeline Diagnostics · Admin",
        expanded=False,
    ):
        if ranked:
            diagnostic_rows = [
                {
                    "Ticker": row.get("ticker"),
                    "Coverage": row.get(
                        "component_coverage_pct"
                    ),
                    "Score": row.get("opportunity_score"),
                    "Confidence": row.get("confidence_pct"),
                }
                for row in ranked[:30]
            ]

            st.dataframe(
                pd.DataFrame(diagnostic_rows),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.write("No eligible rows were produced.")
            sample = pipeline.get("all_rows") or []
            if sample:
                st.json(sample[0])


__all__ = ["render_v103_command_center"]
