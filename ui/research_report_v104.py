
from __future__ import annotations
from html import escape
from typing import Any, Mapping
import streamlit as st

from ui.research_report_v105 import render_v105_research_report
from utils.evidence_coverage_v1045 import calculate_evidence_coverage
from utils.validated_return_v1045 import calculate_validated_return

def _number(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"

def _percent(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "Under review"

def _verdict(value: Any) -> str:
    return str(value or "MONITOR").replace("_", " ").title()

def _verdict_class(value: Any) -> str:
    verdict = str(value or "MONITOR").upper()
    return {
        "BUY_NOW": "atlas-v1045-buy",
        "ACCUMULATE": "atlas-v1045-accumulate",
        "AVOID": "atlas-v1045-avoid",
    }.get(verdict, "atlas-v1045-monitor")

def _score_bar(label: str, value: Any) -> str:
    try:
        numeric = max(0.0, min(100.0, float(value)))
        width = f"{numeric:.0f}%"
        text = f"{numeric:.0f}"
    except (TypeError, ValueError):
        width = "0%"
        text = "—"
    return (
        '<div class="atlas-v1045-score-row">'
        f'<span>{escape(label)}</span>'
        '<div class="atlas-v1045-score-track">'
        f'<div class="atlas-v1045-score-fill" style="width:{width};"></div>'
        '</div>'
        f'<strong>{text}</strong>'
        '</div>'
    )

def inject_v104_polish_css() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stSelectbox"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stTextInput"] label,
        div[data-testid="stMultiSelect"] label,
        div[data-testid="stSelectbox"] label p,
        div[data-testid="stNumberInput"] label p,
        div[data-testid="stTextInput"] label p,
        div[data-testid="stMultiSelect"] label p {
            color: #eef4ff !important;
            font-weight: 750 !important;
            font-size: 0.92rem !important;
        }
        details summary, details summary p, details summary span,
        details[open] summary, details[open] summary p, details[open] summary span {
            color: #172033 !important;
            font-weight: 800 !important;
        }
        .atlas-v1045-filter-title {
            color: #f4f7fc; font-size: 0.86rem; font-weight: 800; margin-bottom: 7px;
        }
        .atlas-v1045-card {
            border: 1px solid rgba(120,145,185,.30);
            border-radius: 22px;
            padding: 22px 24px 20px;
            margin-bottom: 14px;
            background:
                radial-gradient(circle at top right, rgba(44,116,190,.14), transparent 35%),
                linear-gradient(145deg, rgba(12,25,42,.99), rgba(8,17,31,.99));
        }
        .atlas-v1045-head { display:flex; align-items:center; gap:13px; flex-wrap:wrap; margin-bottom:5px; }
        .atlas-v1045-rank { color:#91a4bd; font-size:.75rem; font-weight:850; letter-spacing:.13em; text-transform:uppercase; }
        .atlas-v1045-ticker { color:#f7f9fc; font-size:2rem; font-weight:900; }
        .atlas-v1045-verdict { border-radius:999px; padding:7px 12px; font-size:.74rem; font-weight:850; border:1px solid transparent; }
        .atlas-v1045-buy { color:#d8ffe9; background:rgba(24,150,83,.22); border-color:rgba(60,214,127,.45); }
        .atlas-v1045-accumulate { color:#e2f0ff; background:rgba(27,113,191,.24); border-color:rgba(71,157,236,.45); }
        .atlas-v1045-monitor { color:#fff1c4; background:rgba(179,127,20,.22); border-color:rgba(239,188,74,.45); }
        .atlas-v1045-avoid { color:#ffd8df; background:rgba(177,45,64,.22); border-color:rgba(238,85,108,.45); }
        .atlas-v1045-company { color:#aeb9c8; font-size:.98rem; margin-bottom:16px; }
        .atlas-v1045-metrics { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; margin-bottom:17px; }
        .atlas-v1045-metric { border:1px solid rgba(118,141,174,.21); border-radius:14px; background:rgba(4,13,26,.58); padding:12px 13px; }
        .atlas-v1045-label { color:#8f9caf; font-size:.72rem; margin-bottom:7px; }
        .atlas-v1045-value { color:#f6f8fc; font-size:1.04rem; font-weight:820; }
        .atlas-v1045-columns { display:grid; grid-template-columns:1.1fr .9fr; gap:12px; }
        .atlas-v1045-panel { border:1px solid rgba(118,141,174,.18); border-radius:14px; background:rgba(5,15,29,.52); padding:14px 16px; }
        .atlas-v1045-panel h4 { color:#f3f6fb; margin:0 0 10px; font-size:.84rem; }
        .atlas-v1045-panel ul { margin:0; padding-left:19px; color:#b8c3d2; line-height:1.55; font-size:.88rem; }
        .atlas-v1045-score-row { display:grid; grid-template-columns:112px 1fr 34px; gap:8px; align-items:center; margin:8px 0; color:#b8c3d2; font-size:.82rem; }
        .atlas-v1045-score-track { height:7px; border-radius:999px; background:rgba(120,145,185,.18); overflow:hidden; }
        .atlas-v1045-score-fill { height:100%; background:linear-gradient(90deg,#3c8ee8,#68c3ff); }
        @media (max-width:900px) {
            .atlas-v1045-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .atlas-v1045-columns { grid-template-columns:1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_candidate_card(row: Mapping[str, Any], *, key_prefix: str) -> None:
    inject_v104_polish_css()
    ticker = str(row.get("ticker") or "UNKNOWN")
    company = str(row.get("company") or ticker)
    sector = str(row.get("sector") or "Unknown")
    verdict = row.get("committee_verdict") or "MONITOR"
    rank = row.get("overall_rank") or "—"
    universe = row.get("universe_count") or "—"

    evidence = calculate_evidence_coverage(row)
    validated = calculate_validated_return(row)

    positives = [str(x) for x in (row.get("positive_drivers") or [])][:4] or ["Ranks highly relative to the reviewed universe."]
    waits = [str(x) for x in (row.get("reasons_to_wait") or [])][:4] or ["No structured blocker is currently available."]
    components = row.get("components") or {}

    positive_html = "".join(f"<li>{escape(x)}</li>" for x in positives)
    wait_html = "".join(f"<li>{escape(x)}</li>" for x in waits)
    missing_html = "".join(f"<li>{escape(x)}</li>" for x in evidence["missing"][:5]) or "<li>No major evidence gap identified.</li>"
    scorecard = "".join([
        _score_bar("Fundamental", components.get("fundamentals")),
        _score_bar("Technical", components.get("technical")),
        _score_bar("Valuation", components.get("valuation")),
        _score_bar("Institutional", components.get("institutional")),
        _score_bar("Political", components.get("political")),
        _score_bar("Risk", components.get("risk")),
    ])

    st.markdown(
        f"""
        <div class="atlas-v1045-card">
          <div class="atlas-v1045-rank">#{escape(str(rank))} ranked opportunity of {escape(str(universe))}</div>
          <div class="atlas-v1045-head">
            <div class="atlas-v1045-ticker">{escape(ticker)}</div>
            <div class="atlas-v1045-verdict {_verdict_class(verdict)}">{escape(_verdict(verdict))}</div>
          </div>
          <div class="atlas-v1045-company">{escape(company)} · {escape(sector)}</div>
          <div class="atlas-v1045-metrics">
            <div class="atlas-v1045-metric"><div class="atlas-v1045-label">Opportunity</div><div class="atlas-v1045-value">{_number(row.get("opportunity_score"))}</div></div>
            <div class="atlas-v1045-metric"><div class="atlas-v1045-label">Confidence</div><div class="atlas-v1045-value">{_percent(row.get("confidence_pct"))}</div></div>
            <div class="atlas-v1045-metric"><div class="atlas-v1045-label">Validated Return</div><div class="atlas-v1045-value">{escape(validated["label"])}</div></div>
            <div class="atlas-v1045-metric"><div class="atlas-v1045-label">Evidence Coverage</div><div class="atlas-v1045-value">{evidence["coverage_pct"]:.1f}%</div></div>
            <div class="atlas-v1045-metric"><div class="atlas-v1045-label">Suggested Allocation</div><div class="atlas-v1045-value">{escape(str(row.get("position_size_range") or "0–2%"))}</div></div>
          </div>
          <div class="atlas-v1045-columns">
            <div class="atlas-v1045-panel">
              <h4>Why Atlas selected it</h4><ul>{positive_html}</ul>
              <h4 style="margin-top:16px;">Committee scorecard</h4>{scorecard}
            </div>
            <div class="atlas-v1045-panel">
              <h4>What keeps it from a stronger rating</h4><ul>{wait_html}</ul>
              <h4 style="margin-top:16px;">Missing evidence</h4><ul>{missing_html}</ul>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        f"Open full institutional research — {ticker}",
        key=f"{key_prefix}_{ticker}_research",
        use_container_width=True,
        type="primary",
    ):
        st.session_state["v104_research_ticker"] = ticker
        st.query_params["research"] = ticker
        st.rerun()

def render_full_research_report(row: Mapping[str, Any]) -> None:
    render_v105_research_report(row)
    if st.button(
        "Close institutional research",
        use_container_width=True,
        key=f"close_v105_{row.get('ticker')}",
    ):
        st.session_state.pop("v104_research_ticker", None)
        if "research" in st.query_params:
            del st.query_params["research"]
        st.rerun()

__all__ = ["inject_v104_polish_css", "render_candidate_card", "render_full_research_report"]
