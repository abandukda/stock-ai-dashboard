
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

    query = st.query_params.get("research")
    if query and not st.session_state.get("v104_research_ticker"):
        st.session_state["v104_research_ticker"] = (
            query[0] if isinstance(query, list) else str(query)
        )

    st.markdown("# Atlas V2 Institutional Intelligence")
    st.caption(
        "Individualized scoring, complete research dossiers, valuation, "
        "risk-managed trade planning, and clear AI interpretation."
    )

    c = st.columns(4)
    c[0].metric("BUY NOW", summary.get("buy_now", 0))
    c[1].metric("Research Candidates", summary.get("research_candidates", 0))
    c[2].metric("Committee Ready", summary.get("committee_ready", 0))
    c[3].metric("Universe Reviewed", summary.get("received", 0))

    c = st.columns(4)
    c[0].metric("Accumulate", summary.get("accumulate", 0))
    c[1].metric("Monitor", summary.get("monitor", 0))
    c[2].metric(
        "Average Confidence",
        f"{_avg(ranked, 'confidence_pct'):.1f}%",
    )
    c[3].metric(
        "Average Opportunity",
        f"{_avg(ranked, 'opportunity_score'):.1f}",
    )

    selected_ticker = st.session_state.get("v104_research_ticker")
    if selected_ticker:
        selected = next(
            (
                row
                for row in ranked
                if str(row.get("ticker", "")).upper()
                == str(selected_ticker).upper()
            ),
            None,
        )

        if selected:
            render_full_research_report(selected)
            st.markdown("---")
        else:
            st.warning(
                f"{selected_ticker} is not present in the current scan."
            )

    st.markdown("## Top Research Candidates")
    st.caption(
        "Each card uses individualized Opportunity and Confidence scoring. "
        "Open the full report for financials, earnings, analysts, news, "
        "political activity, ownership, technicals, valuation, and risk."
    )

    if not candidates:
        st.warning("No research candidates are available.")
        return

    f1, f2, f3 = st.columns([1.2, 1.2, 1])

    with f1:
        st.markdown(
            '<div class="atlas-filter-label">Committee verdict</div>',
            unsafe_allow_html=True,
        )
        verdict_filter = st.selectbox(
            "Committee verdict",
            ["All", "Buy Now", "Accumulate", "Monitor", "Avoid"],
            label_visibility="collapsed",
            key="v2_verdict_filter",
        )

    with f2:
        st.markdown(
            '<div class="atlas-filter-label">Opportunity tier</div>',
            unsafe_allow_html=True,
        )
        tier_filter = st.selectbox(
            "Opportunity tier",
            [
                "All",
                "Elite",
                "Exceptional",
                "High",
                "Good",
                "Average",
                "Weak",
            ],
            label_visibility="collapsed",
            key="v2_tier_filter",
        )

    with f3:
        st.markdown(
            '<div class="atlas-filter-label">Cards shown</div>',
            unsafe_allow_html=True,
        )
        count = st.selectbox(
            "Cards shown",
            [5, 8, 10, 12],
            index=2,
            label_visibility="collapsed",
            key="v2_card_count",
        )

    filtered = []
    for row in candidates:
        verdict = str(
            row.get("committee_verdict") or "MONITOR"
        ).replace("_", " ").title()
        tier = str(
            row.get("opportunity_tier") or "Incomplete"
        ).title()

        if verdict_filter != "All" and verdict != verdict_filter:
            continue
        if tier_filter != "All" and tier != tier_filter:
            continue
        filtered.append(row)

    if not filtered:
        st.info("No research candidates match the selected filters.")
        return

    for index, row in enumerate(filtered[: int(count)], start=1):
        render_candidate_card(
            row,
            key_prefix=f"v2_candidate_{index}",
        )


__all__ = ["render_v104_home"]
