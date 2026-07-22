"""
Atlas V104.2 / V105 Bridge

Preserves V104 card exports while routing full research to the new
V105 Institutional Research Report.
"""

from __future__ import annotations

from html import escape
from typing import Any, Mapping

import streamlit as st

from ui.research_report_v105 import render_v105_research_report


def _number(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _percent(value: Any, signed: bool = False) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Under review"
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.1f}%"


def _verdict(value: Any) -> str:
    return str(value or "MONITOR").replace("_", " ").title()


def inject_v104_polish_css() -> None:
    st.markdown(
        """
        <style>
        .atlas-v105-bridge-card {
            border: 1px solid rgba(120, 145, 185, 0.28);
            border-radius: 22px;
            padding: 22px 24px 18px 24px;
            margin-bottom: 18px;
            background:
                radial-gradient(circle at top right,
                    rgba(44, 116, 190, 0.12), transparent 36%),
                linear-gradient(145deg,
                    rgba(12, 25, 42, 0.98),
                    rgba(8, 17, 31, 0.98));
        }
        .atlas-v105-bridge-rank {
            color: #91a4bd;
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.13em;
            text-transform: uppercase;
        }
        .atlas-v105-bridge-title {
            color: #f7f9fc;
            font-size: 1.85rem;
            font-weight: 900;
            margin-top: 6px;
        }
        .atlas-v105-bridge-meta {
            color: #aeb9c8;
            margin-top: 6px;
        }
        .atlas-v105-bridge-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 10px;
            margin-top: 17px;
        }
        .atlas-v105-bridge-metric {
            border: 1px solid rgba(118, 141, 174, 0.20);
            border-radius: 14px;
            background: rgba(4, 13, 26, 0.58);
            padding: 12px 13px;
        }
        .atlas-v105-bridge-label {
            color: #8f9caf;
            font-size: 0.72rem;
            margin-bottom: 7px;
        }
        .atlas-v105-bridge-value {
            color: #f6f8fc;
            font-size: 1rem;
            font-weight: 820;
        }
        @media (max-width: 900px) {
            .atlas-v105-bridge-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
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
    company = str(row.get("company") or ticker)
    rank = row.get("overall_rank") or "—"
    universe = row.get("universe_count") or "—"

    st.markdown(
        f"""
        <div class="atlas-v105-bridge-card">
          <div class="atlas-v105-bridge-rank">
            Research priority #{escape(str(rank))} of {escape(str(universe))}
          </div>
          <div class="atlas-v105-bridge-title">
            {escape(ticker)} — {escape(company)}
          </div>
          <div class="atlas-v105-bridge-meta">
            {escape(str(row.get("sector") or "Unknown"))}
            · {_verdict(row.get("committee_verdict"))}
            · {escape(str(row.get("top_percentile_text") or "Rank under review"))}
          </div>
          <div class="atlas-v105-bridge-grid">
            <div class="atlas-v105-bridge-metric">
              <div class="atlas-v105-bridge-label">Opportunity</div>
              <div class="atlas-v105-bridge-value">{_number(row.get("opportunity_score"))}</div>
            </div>
            <div class="atlas-v105-bridge-metric">
              <div class="atlas-v105-bridge-label">Confidence</div>
              <div class="atlas-v105-bridge-value">{_percent(row.get("confidence_pct"))}</div>
            </div>
            <div class="atlas-v105-bridge-metric">
              <div class="atlas-v105-bridge-label">Expected Return</div>
              <div class="atlas-v105-bridge-value">{_percent(row.get("expected_return_pct"), signed=True)}</div>
            </div>
            <div class="atlas-v105-bridge-metric">
              <div class="atlas-v105-bridge-label">Evidence Coverage</div>
              <div class="atlas-v105-bridge-value">{_percent(row.get("component_coverage_pct"))}</div>
            </div>
            <div class="atlas-v105-bridge-metric">
              <div class="atlas-v105-bridge-label">Position Range</div>
              <div class="atlas-v105-bridge-value">{escape(str(row.get("position_size_range") or "0–2%"))}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        f"Open V105 institutional research — {ticker}",
        key=f"{key_prefix}_{ticker}_v105",
        use_container_width=True,
        type="primary",
    ):
        st.session_state["v104_research_ticker"] = ticker
        st.rerun()


def render_full_research_report(
    row: Mapping[str, Any],
) -> None:
    render_v105_research_report(row)

    if st.button(
        "Close institutional research",
        use_container_width=True,
        key=f"close_v105_{row.get('ticker')}",
    ):
        st.session_state.pop("v104_research_ticker", None)
        st.rerun()


__all__ = [
    "inject_v104_polish_css",
    "render_candidate_card",
    "render_full_research_report",
]
