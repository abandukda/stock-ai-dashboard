
from __future__ import annotations
from html import escape
from typing import Any, Mapping
import streamlit as st
from ui.research_report_v105 import render_v105_research_report
from utils.evidence_coverage_v1046 import calculate_evidence_coverage
from utils.validated_return_v1046 import calculate_validated_return

def _num(value):
    try: return f"{float(value):.1f}"
    except (TypeError, ValueError): return "—"

def _pct(value):
    try: return f"{float(value):.1f}%"
    except (TypeError, ValueError): return "Under review"

def _verdict(value):
    return str(value or "MONITOR").replace("_", " ").title()

def inject_v104_polish_css():
    st.markdown("""
    <style>
    .atlas-filter-label{color:#f3f7ff!important;font-size:.92rem;font-weight:800;margin-bottom:7px}
    .atlas-card{border:1px solid rgba(120,145,185,.30);border-radius:22px;padding:22px 24px 20px;margin-bottom:14px;
    background:radial-gradient(circle at top right,rgba(44,116,190,.14),transparent 35%),
    linear-gradient(145deg,rgba(12,25,42,.99),rgba(8,17,31,.99))}
    .atlas-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
    .atlas-rank{color:#91a4bd;font-size:.75rem;font-weight:850;letter-spacing:.13em;text-transform:uppercase}
    .atlas-ticker{color:#f7f9fc;font-size:2rem;font-weight:900}
    .atlas-badge{border-radius:999px;padding:7px 12px;font-size:.74rem;font-weight:850;border:1px solid rgba(80,170,235,.45);color:#e7f4ff;background:rgba(27,113,191,.24)}
    .atlas-company{color:#aeb9c8;margin:7px 0 16px}
    .atlas-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:16px}
    .atlas-metric{border:1px solid rgba(118,141,174,.21);border-radius:14px;background:rgba(4,13,26,.58);padding:12px}
    .atlas-label{color:#8f9caf;font-size:.72rem;margin-bottom:7px}.atlas-value{color:#f6f8fc;font-size:1.04rem;font-weight:820}
    .atlas-panels{display:grid;grid-template-columns:1fr 1fr;gap:12px}.atlas-panel{border:1px solid rgba(118,141,174,.18);border-radius:14px;background:rgba(5,15,29,.52);padding:14px 16px}
    .atlas-panel h4{color:#f3f6fb;margin:0 0 10px}.atlas-panel ul{color:#b8c3d2;line-height:1.55}
    @media(max-width:900px){.atlas-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-panels{grid-template-columns:1fr}}
    </style>
    """, unsafe_allow_html=True)

def render_candidate_card(row: Mapping[str, Any], *, key_prefix: str) -> None:
    inject_v104_polish_css()
    ticker = str(row.get("ticker") or "UNKNOWN")
    evidence = calculate_evidence_coverage(row)
    validated = calculate_validated_return(row)
    positives = [str(x) for x in (row.get("positive_drivers") or [])][:4] or ["Ranks highly relative to the reviewed universe."]
    waits = [str(x) for x in (row.get("reasons_to_wait") or [])][:4] or ["No structured blocker is available."]
    positive_html = "".join(f"<li>{escape(x)}</li>" for x in positives)
    wait_html = "".join(f"<li>{escape(x)}</li>" for x in waits)
    missing_html = "".join(f"<li>{escape(x)}</li>" for x in evidence["missing"][:5]) or "<li>No material evidence gap.</li>"

    st.markdown(f"""
    <div class="atlas-card">
      <div class="atlas-rank">#{escape(str(row.get("overall_rank") or "—"))} ranked opportunity of {escape(str(row.get("universe_count") or "—"))}</div>
      <div class="atlas-head"><div class="atlas-ticker">{escape(ticker)}</div><div class="atlas-badge">{escape(_verdict(row.get("committee_verdict")))}</div></div>
      <div class="atlas-company">{escape(str(row.get("company") or ticker))} · {escape(str(row.get("sector") or "Unknown"))}</div>
      <div class="atlas-metrics">
        <div class="atlas-metric"><div class="atlas-label">Opportunity</div><div class="atlas-value">{_num(row.get("opportunity_score"))}</div></div>
        <div class="atlas-metric"><div class="atlas-label">Confidence</div><div class="atlas-value">{_pct(row.get("confidence_pct"))}</div></div>
        <div class="atlas-metric"><div class="atlas-label">Validated Return</div><div class="atlas-value">{escape(validated["label"])}</div></div>
        <div class="atlas-metric"><div class="atlas-label">Evidence Coverage</div><div class="atlas-value">{evidence["coverage_pct"]:.1f}%</div></div>
        <div class="atlas-metric"><div class="atlas-label">Suggested Allocation</div><div class="atlas-value">{escape(str(row.get("position_size_range") or "0–2%"))}</div></div>
      </div>
      <div class="atlas-panels">
        <div class="atlas-panel"><h4>Why Atlas selected it</h4><ul>{positive_html}</ul></div>
        <div class="atlas-panel"><h4>Risks and missing evidence</h4><ul>{wait_html}{missing_html}</ul></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button(f"Open full institutional research — {ticker}", key=f"{key_prefix}_{ticker}_research", use_container_width=True, type="primary"):
        st.session_state["v104_research_ticker"] = ticker
        st.query_params["research"] = ticker
        st.rerun()

def render_full_research_report(row: Mapping[str, Any]) -> None:
    render_v105_research_report(row)
    if st.button("Close institutional research", key=f"close_{row.get('ticker')}", use_container_width=True):
        st.session_state.pop("v104_research_ticker", None)
        st.query_params.clear()
        st.rerun()

__all__ = ["inject_v104_polish_css","render_candidate_card","render_full_research_report"]
