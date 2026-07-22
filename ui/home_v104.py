
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd
import streamlit as st
from ui.research_report_v104 import inject_v104_polish_css, render_candidate_card, render_full_research_report

def _avg(rows, key):
    vals=[]
    for row in rows:
        try: vals.append(float(row.get(key)))
        except (TypeError, ValueError): pass
    return sum(vals)/len(vals) if vals else 0.0

def render_v104_home(pipeline: Mapping[str, Any]) -> None:
    inject_v104_polish_css()
    summary = pipeline.get("summary") or {}
    ranked = pipeline.get("ranked_candidates") or []
    candidates = pipeline.get("research_candidates") or []

    query = st.query_params.get("research")
    if query and not st.session_state.get("v104_research_ticker"):
        st.session_state["v104_research_ticker"] = query[0] if isinstance(query, list) else str(query)

    st.markdown("# Atlas V104.6 Stability Release")
    st.caption("Dynamic evidence, validated returns, reliable research navigation, and compact production diagnostics.")

    c=st.columns(4)
    c[0].metric("Universe Reviewed",summary.get("received",0)); c[1].metric("Research Candidates",summary.get("research_candidates",0))
    c[2].metric("Committee Ready",summary.get("committee_ready",0)); c[3].metric("BUY NOW",summary.get("buy_now",0))
    c=st.columns(4)
    c[0].metric("Accumulate",summary.get("accumulate",0)); c[1].metric("Monitor",summary.get("monitor",0))
    c[2].metric("Average Confidence",f"{_avg(ranked,'confidence_pct'):.1f}%"); c[3].metric("Average Opportunity",f"{_avg(ranked,'opportunity_score'):.1f}")

    selected_ticker=st.session_state.get("v104_research_ticker")
    if selected_ticker:
        selected=next((r for r in ranked if str(r.get("ticker"))==str(selected_ticker)),None)
        if selected:
            render_full_research_report(selected)
            st.markdown("---")
        else:
            st.warning(f"{selected_ticker} is not present in the current scan.")

    st.markdown("## Top Research Candidates")
    st.caption("Coverage varies by the evidence actually available. Extreme fair-value targets are not shown as validated returns.")

    if candidates:
        f1,f2,f3=st.columns([1.2,1.2,1])
        with f1:
            st.markdown('<div class="atlas-filter-label">Committee verdict</div>',unsafe_allow_html=True)
            vf=st.selectbox("Committee verdict",["All","Buy Now","Accumulate","Monitor","Avoid"],label_visibility="collapsed",key="v1046_v")
        with f2:
            st.markdown('<div class="atlas-filter-label">Opportunity tier</div>',unsafe_allow_html=True)
            tf=st.selectbox("Opportunity tier",["All","Elite","Exceptional","High","Good","Average","Weak"],label_visibility="collapsed",key="v1046_t")
        with f3:
            st.markdown('<div class="atlas-filter-label">Cards shown</div>',unsafe_allow_html=True)
            count=st.selectbox("Cards shown",[5,8,10,12],index=2,label_visibility="collapsed",key="v1046_c")

        filtered=[]
        for row in candidates:
            verdict=str(row.get("committee_verdict") or "MONITOR").replace("_"," ").title()
            tier=str(row.get("opportunity_tier") or "Incomplete").title()
            if vf!="All" and verdict!=vf: continue
            if tf!="All" and tier!=tf: continue
            filtered.append(row)
        for i,row in enumerate(filtered[:int(count)],1):
            render_candidate_card(row,key_prefix=f"v1046_{i}")
    else:
        st.warning("No research candidates are available.")

    st.markdown("## Methodology & Pipeline Health")
    show=st.toggle("Show methodology and pipeline health",value=False,key="v1046_methodology")
    if show:
        st.write("Research candidates are ranked by opportunity score and diversification. Committee verdicts also require confidence, dynamic evidence coverage, fundamental quality, technical confirmation, validated upside, and no critical blocker.")
        table=pd.DataFrame([
            {"Metric":"Universe reviewed","Value":summary.get("received",0)},
            {"Metric":"Eligible and scored","Value":summary.get("eligible",0)},
            {"Metric":"Research candidates","Value":summary.get("research_candidates",0)},
            {"Metric":"Committee ready","Value":summary.get("committee_ready",0)},
            {"Metric":"BUY NOW","Value":summary.get("buy_now",0)},
            {"Metric":"Accumulate","Value":summary.get("accumulate",0)},
            {"Metric":"Monitor","Value":summary.get("monitor",0)},
        ])
        st.dataframe(table,hide_index=True,use_container_width=True)

__all__=["render_v104_home"]
