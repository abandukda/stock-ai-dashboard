
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd
import streamlit as st

from ui.research_report_v104 import inject_v104_polish_css, render_candidate_card, render_full_research_report

def _avg(rows, key):
    values = []
    for row in rows:
        try:
            values.append(float(row.get(key)))
        except (TypeError, ValueError):
            continue
    return sum(values) / len(values) if values else 0.0

def _query_research_ticker():
    value = st.query_params.get("research")
    if isinstance(value, list):
        return value[0] if value else None
    return str(value) if value else None

def render_v104_home(pipeline: Mapping[str, Any]) -> None:
    inject_v104_polish_css()
    summary = pipeline.get("summary") or {}
    ranked = pipeline.get("ranked_candidates") or []
    candidates = pipeline.get("research_candidates") or []

    query_ticker = _query_research_ticker()
    if query_ticker and not st.session_state.get("v104_research_ticker"):
        st.session_state["v104_research_ticker"] = query_ticker

    st.markdown("# Atlas V104.5 Investment Committee")
    st.caption("Review the market, prioritize research, open the full institutional report, and act only after the committee verdict is supported.")

    cols = st.columns(4)
    cols[0].metric("Universe Reviewed", int(summary.get("received", 0) or 0))
    cols[1].metric("Research Candidates", int(summary.get("research_candidates", 0) or 0))
    cols[2].metric("Committee Ready", int(summary.get("committee_ready", 0) or 0))
    cols[3].metric("BUY NOW", int(summary.get("buy_now", 0) or 0))
    cols = st.columns(4)
    cols[0].metric("Accumulate", int(summary.get("accumulate", 0) or 0))
    cols[1].metric("Monitor", int(summary.get("monitor", 0) or 0))
    cols[2].metric("Average Confidence", f"{_avg(ranked, 'confidence_pct'):.1f}%")
    cols[3].metric("Average Opportunity", f"{_avg(ranked, 'opportunity_score'):.1f}")

    selected_ticker = st.session_state.get("v104_research_ticker")
    if selected_ticker:
        selected = next((row for row in ranked if str(row.get("ticker")) == str(selected_ticker)), None)
        if selected:
            render_full_research_report(selected)
            st.markdown("---")
        else:
            st.warning(f"Research candidate {selected_ticker} is not present in the current saved scan.")

    st.markdown("## Top Research Candidates")
    st.caption("Evidence coverage is calculated from the data actually available for each company. Validated return excludes extreme targets.")

    if not candidates:
        st.warning("No research candidates are available.")
        return

    f1, f2, f3 = st.columns([1.2, 1.2, 1])
    with f1:
        st.markdown('<div class="atlas-v1045-filter-title">Committee verdict</div>', unsafe_allow_html=True)
        verdict_filter = st.selectbox("Committee verdict", ["All", "Buy Now", "Accumulate", "Monitor", "Avoid"], key="v1045_verdict_filter", label_visibility="collapsed")
    with f2:
        st.markdown('<div class="atlas-v1045-filter-title">Opportunity tier</div>', unsafe_allow_html=True)
        tier_filter = st.selectbox("Opportunity tier", ["All", "Elite", "Exceptional", "High", "Good", "Average", "Weak"], key="v1045_tier_filter", label_visibility="collapsed")
    with f3:
        st.markdown('<div class="atlas-v1045-filter-title">Cards shown</div>', unsafe_allow_html=True)
        display_count = st.selectbox("Cards shown", [5, 8, 10, 12], index=2, key="v1045_card_count", label_visibility="collapsed")

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
            render_candidate_card(row, key_prefix=f"v1045_candidate_{index}")

    with st.expander("Methodology & pipeline health", expanded=False):
        st.write("Research candidates are ranked by opportunity score and sector diversification. Committee verdicts also require confidence, dynamic evidence coverage, fundamental quality, technical confirmation, validated upside, and no critical blocker.")
        health = pd.DataFrame([
            {"Metric": "Universe reviewed", "Value": summary.get("received", 0)},
            {"Metric": "Eligible and scored", "Value": summary.get("eligible", 0)},
            {"Metric": "Research candidates", "Value": summary.get("research_candidates", 0)},
            {"Metric": "Committee ready", "Value": summary.get("committee_ready", 0)},
            {"Metric": "BUY NOW", "Value": summary.get("buy_now", 0)},
            {"Metric": "Accumulate", "Value": summary.get("accumulate", 0)},
            {"Metric": "Monitor", "Value": summary.get("monitor", 0)},
        ])
        st.dataframe(health, hide_index=True, use_container_width=True)

__all__ = ["render_v104_home"]
