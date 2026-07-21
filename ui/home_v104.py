"""
Atlas V104.1 — Polished Investment Committee Home

Drop-in replacement for ui/home_v104.py.
"""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from ui.research_report_v104 import (
    inject_v104_polish_css,
    render_candidate_card,
    render_full_research_report,
)


def _avg(rows, key):
    values = []
    for row in rows:
        try:
            values.append(float(row.get(key)))
        except (TypeError, ValueError):
            continue
    return sum(values) / len(values) if values else 0.0


def render_v104_home(pipeline: Mapping[str, Any]) -> None:
    inject_v104_polish_css()

    summary = pipeline.get("summary") or {}
    ranked = pipeline.get("ranked_candidates") or []
    candidates = pipeline.get("research_candidates") or []

    st.markdown("# Atlas V104.1 Investment Committee")
    st.caption(
        "A focused institutional workflow: review the market, prioritize "
        "research, open a full report, then act on the committee verdict."
    )

    buy_now = int(summary.get("buy_now", 0) or 0)
    committee_ready = int(summary.get("committee_ready", 0) or 0)
    average_confidence = _avg(ranked, "confidence_pct")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Universe Reviewed", int(summary.get("received", 0) or 0))
    k2.metric("Research Candidates", int(summary.get("research_candidates", 0) or 0))
    k3.metric("Committee Ready", committee_ready)
    k4.metric("BUY NOW", buy_now)

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Accumulate", int(summary.get("accumulate", 0) or 0))
    k6.metric("Monitor", int(summary.get("monitor", 0) or 0))
    k7.metric("Average Confidence", f"{average_confidence:.1f}%")
    k8.metric("Average Opportunity", f"{_avg(ranked, 'opportunity_score'):.1f}")

    if buy_now == 0:
        st.info(
            "No company currently clears every BUY NOW condition. "
            "Atlas is still surfacing the strongest research priorities below."
        )
    else:
        st.success(
            f"{buy_now} company or companies currently clear the BUY NOW "
            "investment-committee conditions."
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
            st.markdown("---")

    st.markdown("## Top Research Candidates")
    st.caption(
        "The cards below explain why each company deserves deeper research "
        "and what prevents a stronger verdict."
    )

    if not candidates:
        st.warning("No research candidates are available.")
    else:
        verdict_options = ["All", "Buy Now", "Accumulate", "Monitor", "Avoid"]
        tier_options = ["All", "Elite", "Exceptional", "High", "Good", "Average", "Weak"]

        f1, f2, f3 = st.columns([1.25, 1.25, 1])
        with f1:
            verdict_filter = st.selectbox(
                "Committee verdict",
                verdict_options,
                key="v104_verdict_filter",
            )
        with f2:
            tier_filter = st.selectbox(
                "Opportunity tier",
                tier_options,
                key="v104_tier_filter",
            )
        with f3:
            display_count = st.selectbox(
                "Cards shown",
                [5, 8, 10, 12],
                index=2,
                key="v104_card_count",
            )

        filtered = []
        for row in candidates:
            verdict = str(row.get("committee_verdict") or "MONITOR").replace("_", " ").title()
            tier = str(row.get("opportunity_tier") or "Incomplete").title()
            if verdict_filter != "All" and verdict != verdict_filter:
                continue
            if tier_filter != "All" and tier != tier_filter:
                continue
            filtered.append(row)

        if not filtered:
            st.info("No research candidates match the selected filters.")
        else:
            for index, row in enumerate(filtered[: int(display_count)], start=1):
                render_candidate_card(
                    row,
                    key_prefix=f"v104_1_candidate_{index}",
                )

    with st.expander("Methodology and pipeline health", expanded=False):
        st.write(
            "Research candidates are selected by relative opportunity score "
            "and sector diversification. The final committee verdict also "
            "requires confidence, evidence coverage, fundamental quality, "
            "technical confirmation, validated upside, and no critical blocker."
        )
        st.json(summary)


__all__ = ["render_v104_home"]
