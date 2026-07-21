"""
Atlas V104 — Research Candidate Home Experience
"""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from ui.research_report_v104 import (
    render_candidate_card,
    render_full_research_report,
)


def render_v104_home(pipeline: Mapping[str, Any]) -> None:
    summary = pipeline.get("summary") or {}
    ranked = pipeline.get("ranked_candidates") or []
    candidates = pipeline.get("research_candidates") or []

    st.markdown("# Atlas V104 Investment Committee")
    st.caption(
        "Discovery identifies the best research candidates. "
        "The investment committee then assigns the final verdict."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Reviewed", summary.get("received", 0))
    c2.metric("Eligible & Scored", summary.get("eligible", 0))
    c3.metric(
        "Top Research Candidates",
        summary.get("research_candidates", 0),
    )
    c4.metric("Committee Ready", summary.get("committee_ready", 0))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("BUY NOW", summary.get("buy_now", 0))
    c6.metric("Accumulate", summary.get("accumulate", 0))
    c7.metric("Monitor", summary.get("monitor", 0))
    average_confidence = (
        sum(float(row.get("confidence_pct") or 0) for row in ranked)
        / len(ranked)
        if ranked
        else 0
    )
    c8.metric("Avg Confidence", f"{average_confidence:.1f}%")

    st.markdown("## Top Research Candidates")
    st.caption(
        "These are the highest-priority ideas for full research. "
        "A research candidate is not automatically a BUY NOW."
    )

    if not candidates:
        st.warning("No research candidates are available.")
    else:
        for index, row in enumerate(candidates[:10], start=1):
            render_candidate_card(
                row,
                key_prefix=f"candidate_{index}",
            )

    selected_ticker = st.session_state.get("v104_research_ticker")
    if selected_ticker:
        selected = next(
            (
                row
                for row in ranked
                if row.get("ticker") == selected_ticker
            ),
            None,
        )
        if selected:
            render_full_research_report(selected)

    with st.expander("V104 Pipeline Diagnostics · Admin", expanded=False):
        st.json(summary)


__all__ = ["render_v104_home"]
