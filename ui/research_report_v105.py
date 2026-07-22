
from __future__ import annotations
from html import escape
from typing import Any, Mapping
import pandas as pd
import streamlit as st
from engines.research_engine_v105 import build_institutional_research

def _money(value):
    try: return f"${float(value):,.2f}"
    except (TypeError, ValueError): return "Under review"

def _percent(value, signed=False):
    try:
        number = float(value)
        return f"{'+' if signed and number > 0 else ''}{number:.1f}%"
    except (TypeError, ValueError):
        return "Under review"

def _score(value):
    try: return f"{float(value):.1f}"
    except (TypeError, ValueError): return "Under review"

def _verdict(value):
    return str(value or "MONITOR").replace("_", " ").title()

def inject_v105_css():
    st.markdown("""
    <style>
    .atlas-v105-hero{border-radius:24px;padding:26px;border:1px solid rgba(95,159,226,.32);
    background:radial-gradient(circle at top right,rgba(43,128,213,.18),transparent 38%),
    linear-gradient(145deg,rgba(14,39,65,.98),rgba(7,18,34,.98));margin-bottom:18px}
    .atlas-v105-kicker{color:#8fa8c4;font-size:.75rem;font-weight:850;letter-spacing:.14em;text-transform:uppercase}
    .atlas-v105-title{color:#f8faff;font-size:2.5rem;font-weight:900;line-height:1;margin-top:8px}
    .atlas-v105-subtitle{color:#aebbd0;font-size:1rem;margin-top:9px}
    .atlas-v105-summary{border-left:4px solid #4ea4f2;border-radius:12px;padding:15px 17px;
    background:rgba(13,35,59,.62);color:#dce4ef;line-height:1.62;margin:8px 0 18px}
    </style>
    """, unsafe_allow_html=True)

def _render_scorecard(report):
    visible = [(n, v) for n, v in (report.get("component_scorecard") or {}).items() if v is not None]
    if not visible:
        st.info("No component-level scorecard is available.")
        return
    for name, value in visible:
        try: numeric = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError): continue
        st.progress(numeric / 100.0, text=f"{name.replace('_',' ').title()}: {numeric:.1f}")

def render_v105_research_report(row: Mapping[str, Any]) -> None:
    inject_v105_css()
    report = build_institutional_research(row)

    st.markdown(f"""
    <div class="atlas-v105-hero">
      <div class="atlas-v105-kicker">Atlas V105 Institutional Research</div>
      <div class="atlas-v105-title">{escape(str(report.get("ticker") or "UNKNOWN"))}</div>
      <div class="atlas-v105-subtitle">{escape(str(report.get("company") or ""))} ·
      {escape(str(report.get("sector") or "Unknown"))} · {_verdict(report.get("committee_verdict"))}</div>
    </div>
    """, unsafe_allow_html=True)

    c = st.columns(4)
    c[0].metric("Committee Verdict", _verdict(report.get("committee_verdict")))
    c[1].metric("Opportunity", _score(report.get("opportunity_score")))
    c[2].metric("Confidence", _percent(report.get("confidence_pct")))
    c[3].metric("Suggested Position", report.get("position_size_range"))
    c = st.columns(4)
    c[0].metric("Current Price", _money(report.get("current_price")))
    c[1].metric("Validated Fair Value", _money(report.get("validated_fair_value")))
    c[2].metric("Expected Return", _percent(report.get("expected_return_pct"), signed=True))
    c[3].metric("Primary Blocker", report.get("primary_blocker"))

    st.markdown("## Executive Summary")
    st.markdown(f'<div class="atlas-v105-summary">{escape(str(report.get("executive_summary") or ""))}</div>', unsafe_allow_html=True)

    tabs = st.tabs(["Investment Thesis","Earnings & Transcript","Wall Street","Ownership & Political","Fair Value","Risk","Buy Checklist"])

    with tabs[0]:
        st.markdown("### Investment Thesis")
        st.write(report.get("investment_thesis"))
        bull, bear = st.columns(2)
        with bull:
            st.markdown("### Bull Case")
            items = report.get("bull_case") or []
            if items:
                for item in items: st.success(str(item))
            else: st.info("No structured bull-case drivers are available.")
        with bear:
            st.markdown("### Bear Case")
            items = report.get("bear_case") or []
            if items:
                for item in items: st.warning(str(item))
            else: st.info("No structured bear-case items are available.")
        st.markdown("### Institutional Scorecard")
        _render_scorecard(report)

    with tabs[1]:
        earnings = report.get("earnings_intelligence") or {}
        c = st.columns(4)
        c[0].metric("EPS Surprise", _percent(earnings.get("eps_surprise_pct"), signed=True))
        c[1].metric("Revenue Surprise", _percent(earnings.get("revenue_surprise_pct"), signed=True))
        c[2].metric("Atlas Interpretation", earnings.get("interpretation"))
        c[3].metric("Confidence Impact", f"{_score(earnings.get('confidence_impact_points'))} pts")
        st.markdown("### Guidance"); st.write(earnings.get("guidance"))
        st.markdown("### Transcript Summary"); st.write(earnings.get("transcript_summary"))

    with tabs[2]:
        ws = report.get("wall_street") or {}
        c = st.columns(3)
        c[0].metric("Buy Ratings", ws.get("buy_count") if ws.get("buy_count") is not None else "Under review")
        c[1].metric("Hold Ratings", ws.get("hold_count") if ws.get("hold_count") is not None else "Under review")
        c[2].metric("Sell Ratings", ws.get("sell_count") if ws.get("sell_count") is not None else "Under review")
        c = st.columns(3)
        c[0].metric("Average Target", _money(ws.get("average_target")))
        c[1].metric("High Target", _money(ws.get("high_target")))
        c[2].metric("Low Target", _money(ws.get("low_target")))
        st.info(ws.get("atlas_alignment"))

    with tabs[3]:
        c = st.columns(3)
        c[0].metric("Institutional Support", _score(report.get("institutional_score")))
        c[1].metric("Insider Support", _score(report.get("insider_score")))
        c[2].metric("Political Support", _score(report.get("political_score")))

    with tabs[4]:
        cases = report.get("fair_value_cases") or []
        for col, case in zip(st.columns(3), cases):
            with col:
                st.markdown(f"### {case.get('label')} Case")
                st.metric("Fair Value", _money(case.get("fair_value")))
                st.metric("Expected Return", _percent(case.get("expected_return_pct"), signed=True))
                st.caption(f"Probability: {_percent(case.get('probability_pct'))}")

    with tabs[5]:
        st.dataframe(pd.DataFrame(report.get("risk_matrix") or []), hide_index=True, use_container_width=True)

    with tabs[6]:
        for item in report.get("buy_checklist") or []:
            text = f"{item.get('label')}: {_score(item.get('value'))} (threshold {_score(item.get('threshold'))})"
            if item.get("status") == "Passed": st.success(text)
            elif item.get("status") == "Missing": st.info(text)
            else: st.warning(text)

__all__ = ["inject_v105_css", "render_v105_research_report"]
