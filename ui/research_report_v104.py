
from __future__ import annotations

from html import escape
from typing import Any, Mapping

import streamlit as st

from engines.individualized_scoring_v1052 import calculate_individualized_scores
from engines.trade_plan_v1052 import classify_horizon
from ui.research_report_v2 import render_atlas_research_v2
from utils.evidence_coverage_v1046 import calculate_evidence_coverage
from utils.validated_return_v1046 import calculate_validated_return


def _num(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "Under review"


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _verdict(value: Any) -> str:
    return str(value or "MONITOR").replace("_", " ").title()


def _analyst_target(row: Mapping[str, Any]) -> Any:
    analysts = row.get("analysts") or {}
    raw = row.get("raw") or row.get("Raw") or {}
    return (
        row.get("analyst_target_mean")
        or row.get("Analyst Target")
        or analysts.get("analyst_target_mean")
        or analysts.get("average_target")
        or raw.get("Analyst Target")
        or raw.get("targetMeanPrice")
    )


def inject_v104_polish_css() -> None:
    st.markdown(
        """
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
        .atlas-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin-bottom:16px}
        .atlas-metric{border:1px solid rgba(118,141,174,.21);border-radius:14px;background:rgba(4,13,26,.58);padding:12px}
        .atlas-label{color:#8f9caf;font-size:.72rem;margin-bottom:7px}
        .atlas-value{color:#f6f8fc;font-size:1.04rem;font-weight:820}
        .atlas-panels{display:grid;grid-template-columns:1fr 1fr;gap:12px}
        .atlas-panel{border:1px solid rgba(118,141,174,.18);border-radius:14px;background:rgba(5,15,29,.52);padding:14px 16px}
        .atlas-panel h4{color:#f3f6fb;margin:0 0 10px}
        .atlas-panel ul{color:#b8c3d2;line-height:1.55}
        @media(max-width:1050px){.atlas-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}}
        @media(max-width:700px){.atlas-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-panels{grid-template-columns:1fr}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_candidate_card(
    row: Mapping[str, Any],
    *,
    key_prefix: str,
) -> None:
    inject_v104_polish_css()

    ticker = str(row.get("ticker") or "UNKNOWN")
    evidence = calculate_evidence_coverage(row)
    validated = calculate_validated_return(row)
    individualized = calculate_individualized_scores(row)
    raw_horizon = classify_horizon(row).get("primary", "Research / Monitor")
    horizon = {
        "Swing": "Short-Term Setup",
        "Position": "3–12 Month View",
        "Long-Term": "Long-Term View",
        "Research / Monitor": "Research Monitor",
    }.get(raw_horizon, raw_horizon)

    positives = [
        str(item) for item in (row.get("positive_drivers") or [])
    ][:4] or ["Ranks highly relative to the reviewed universe."]
    waits = [
        str(item) for item in (row.get("reasons_to_wait") or [])
    ][:4] or ["No structured blocker is available."]

    positive_html = "".join(
        f"<li>{escape(item)}</li>" for item in positives
    )
    # Do not expose raw engineering diagnostics on customer cards.
    # Evidence gaps remain available in the internal audit and full report.
    risk_items = waits
    if evidence["coverage_pct"] < 70:
        risk_items.append(
            "Some supplemental evidence is still being validated; "
            "position sizing should remain conservative."
        )
    risk_html = "".join(
        f"<li>{escape(item)}</li>" for item in risk_items
    ) or "<li>No material structured blocker is currently identified.</li>"

    atlas_target = (
        row.get("validated_fair_value")
        or row.get("atlas_fair_value")
    )
    analyst_target = _analyst_target(row)

    st.markdown(
        f"""
        <div class="atlas-card">
          <div class="atlas-rank">#{escape(str(row.get("overall_rank") or "—"))}
          ranked opportunity of {escape(str(row.get("universe_count") or "—"))}</div>

          <div class="atlas-head">
            <div class="atlas-ticker">{escape(ticker)}</div>
            <div class="atlas-badge">{escape(_verdict(row.get("committee_verdict")))}</div>
            <div class="atlas-badge">{escape(str(horizon))}</div>
          </div>

          <div class="atlas-company">
            {escape(str(row.get("company") or ticker))} ·
            {escape(str(row.get("sector") or "Unknown"))}
          </div>

          <div class="atlas-metrics">
            <div class="atlas-metric">
              <div class="atlas-label">Opportunity</div>
              <div class="atlas-value">{_num(individualized.get("opportunity_score"))}</div>
            </div>
            <div class="atlas-metric">
              <div class="atlas-label">Confidence</div>
              <div class="atlas-value">{_pct(individualized.get("confidence_pct"))}</div>
            </div>
            <div class="atlas-metric">
              <div class="atlas-label">Validated Return</div>
              <div class="atlas-value">{escape(validated["label"])}</div>
            </div>
            <div class="atlas-metric">
              <div class="atlas-label">Evidence Coverage</div>
              <div class="atlas-value">{evidence["coverage_pct"]:.1f}%</div>
            </div>
            <div class="atlas-metric">
              <div class="atlas-label">Atlas Target</div>
              <div class="atlas-value">{_money(atlas_target)}</div>
            </div>
            <div class="atlas-metric">
              <div class="atlas-label">Analyst Average</div>
              <div class="atlas-value">{_money(analyst_target)}</div>
            </div>
          </div>

          <div class="atlas-panels">
            <div class="atlas-panel">
              <h4>Why Atlas selected it</h4>
              <ul>{positive_html}</ul>
            </div>
            <div class="atlas-panel">
              <h4>Key risks and considerations</h4>
              <ul>{risk_html}</ul>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        f"Open complete Atlas research — {ticker}",
        key=f"{key_prefix}_{ticker}_research",
        use_container_width=True,
        type="primary",
    ):
        st.session_state["v104_research_ticker"] = ticker
        st.query_params["research"] = ticker
        st.rerun()


def render_full_research_report(row: Mapping[str, Any]) -> None:
    render_atlas_research_v2(row)

    if st.button(
        "Close institutional research",
        key=f"close_{row.get('ticker')}",
        use_container_width=True,
    ):
        st.session_state.pop("v104_research_ticker", None)
        st.query_params.clear()
        st.rerun()


__all__ = [
    "inject_v104_polish_css",
    "render_candidate_card",
    "render_full_research_report",
]
