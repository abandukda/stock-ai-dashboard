"""Atlas V60.0 Scorecard Section."""
from __future__ import annotations

from typing import Any

import streamlit as st

from ui.components import metric_card, section_header
from engines.report_sections.formatting import fmt_pct, fmt_score, safe_text


def render_investment_scorecard(row: dict[str, Any]) -> None:
    section_header("📊", "Atlas Scorecard™", "Quick view of the main decision drivers.")

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card(
            "Atlas Conviction™",
            fmt_score(row.get("Opportunity") or row.get("opportunity") or row.get("Final Conviction") or row.get("final_agent_score") or row.get("score")),
            "How attractive this setup looks today.",
        )
    with c2:
        metric_card(
            "Atlas Quality™",
            fmt_score(row.get("Quality") or row.get("quality") or row.get("financial_score") or row.get("finance_agent_score") or row.get("fundamentals_agent_score")),
            "Business and financial quality signal.",
        )
    with c3:
        metric_card(
            "Atlas Confidence™",
            fmt_score(row.get("Confidence") or row.get("confidence") or row.get("ai_confidence") or row.get("evidence_confidence")),
            "How aligned the evidence appears.",
        )

    c4, c5, c6 = st.columns(3)
    with c4:
        metric_card(
            "Modeled Upside",
            fmt_pct(row.get("Target Upside %") or row.get("target_upside_pct") or row.get("expected_upside_pct") or row.get("upside")),
            "Upside from current scan target.",
        )
    with c5:
        metric_card(
            "Risk / Reward",
            safe_text(row.get("Risk/Reward") or row.get("risk_reward"), "Review"),
            "Modeled reward compared with downside.",
        )
    with c6:
        metric_card(
            "Political Signal",
            safe_text(row.get("Political Signal") or row.get("political_signal"), "Not detected"),
            "Supporting signal, not a primary driver.",
        )
