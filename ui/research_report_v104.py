"""
Atlas V104 — Institutional Research Candidate Cards and Report
"""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st


def _metric_value(value, suffix=""):
    if value is None:
        return "Under review"
    return f"{value}{suffix}"


def render_candidate_card(
    row: Mapping[str, Any],
    *,
    key_prefix: str,
) -> None:
    ticker = row.get("ticker") or "UNKNOWN"
    company = row.get("company") or ticker
    verdict = row.get("committee_verdict") or "MONITOR"

    with st.container(border=True):
        top_left, top_right = st.columns([4, 1])
        with top_left:
            st.markdown(f"### {ticker} — {company}")
            st.caption(
                f"{row.get('sector', 'Unknown')} · "
                f"{row.get('top_percentile_text', 'Under review')}"
            )
        with top_right:
            st.markdown(f"**{verdict.replace('_', ' ')}**")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Opportunity", _metric_value(row.get("opportunity_score")))
        m2.metric(
            "Confidence",
            _metric_value(row.get("confidence_pct"), "%"),
        )
        m3.metric(
            "Expected Return",
            _metric_value(row.get("expected_return_pct"), "%"),
        )
        m4.metric(
            "Position Range",
            row.get("position_size_range") or "0–2%",
        )

        positives = row.get("positive_drivers") or []
        waits = row.get("reasons_to_wait") or []

        left, right = st.columns(2)
        with left:
            st.markdown("**Why Atlas selected it**")
            for item in positives[:3]:
                st.write(f"• {item}")
        with right:
            st.markdown("**Why the committee may wait**")
            for item in waits[:3]:
                st.write(f"• {item}")

        if st.button(
            f"Open Full Research — {ticker}",
            key=f"{key_prefix}_{ticker}",
            use_container_width=True,
        ):
            st.session_state["v104_research_ticker"] = ticker
            st.rerun()


def render_full_research_report(
    row: Mapping[str, Any],
) -> None:
    ticker = row.get("ticker") or "UNKNOWN"
    company = row.get("company") or ticker

    st.markdown("---")
    st.markdown(f"# Full Research: {ticker}")
    st.caption(company)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Committee Verdict", row.get("committee_verdict"))
    c2.metric("Opportunity", row.get("opportunity_score"))
    c3.metric("Confidence", f"{row.get('confidence_pct', 0):.1f}%")
    c4.metric("Position Range", row.get("position_size_range"))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Current Price", row.get("current_price"))
    c6.metric("Fair Value", row.get("validated_fair_value"))
    c7.metric("Expected Return", _metric_value(row.get("expected_return_pct"), "%"))
    c8.metric("Evidence Coverage", _metric_value(row.get("component_coverage_pct"), "%"))

    st.markdown("## Investment Committee Thesis")
    if row.get("investment_thesis"):
        st.write(row["investment_thesis"])
    else:
        st.info("A structured investment thesis was not included in the saved scan.")

    left, right = st.columns(2)
    with left:
        st.markdown("### Bull Case")
        for item in row.get("positive_drivers") or []:
            st.write(f"• {item}")

    with right:
        st.markdown("### Bear Case / Reasons to Wait")
        for item in row.get("reasons_to_wait") or []:
            st.write(f"• {item}")

    st.markdown("## Evidence Scorecard")
    components = row.get("components") or {}
    if components:
        for name, value in components.items():
            if value is not None:
                st.progress(
                    max(0.0, min(1.0, float(value) / 100.0)),
                    text=f"{name.replace('_', ' ').title()}: {float(value):.1f}",
                )

    if st.button("Close Full Research", use_container_width=True):
        st.session_state.pop("v104_research_ticker", None)
        st.rerun()


__all__ = [
    "render_candidate_card",
    "render_full_research_report",
]
