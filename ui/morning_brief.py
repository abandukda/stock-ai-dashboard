"""Streamlit UI for the Atlas Morning Brief."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import streamlit as st

from engines.morning_brief_engine import build_morning_brief
from engines.guidance_summary import build_guidance_summary


def _pct(value: Any, *, signed: bool = False) -> str:
    try:
        number = float(value)
    except Exception:
        return "Under review"
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.1f}%"


def _num(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except Exception:
        return "—"


def _research_button(ticker: str, key: str) -> None:
    if st.button(
        f"Open complete Atlas research — {ticker}",
        key=key,
        use_container_width=True,
    ):
        st.session_state["v104_research_ticker"] = ticker
        st.query_params["research"] = ticker
        st.rerun()


def _opportunity_card(
    row: Mapping[str, Any],
    *,
    key_prefix: str,
) -> None:
    ticker = str(row.get("ticker") or "UNKNOWN")
    verdict = str(
        row.get("committee_verdict") or "MONITOR"
    ).replace("_", " ").title()

    with st.container(border=True):
        heading = st.columns([1.2, 1, 1, 1])
        heading[0].markdown(f"### {ticker}")
        heading[1].metric("Atlas Rating", verdict)
        heading[2].metric(
            "Opportunity",
            _num(row.get("opportunity_score")),
        )
        heading[3].metric(
            "Confidence",
            _pct(row.get("confidence_pct")),
        )

        details = st.columns(3)
        details[0].metric(
            "Expected Return",
            _pct(row.get("expected_return_pct"), signed=True),
        )
        details[1].metric(
            "Evidence Coverage",
            _pct(row.get("component_coverage_pct")),
        )
        details[2].metric(
            "Suggested Position",
            row.get("position_size_range") or "Under review",
        )

        guidance = build_guidance_summary(row)
        positives = guidance.get("supporting_facts") or []
        cautions = guidance.get("key_risks") or []

        left, right = st.columns(2)
        with left:
            st.markdown("**Why Atlas is interested**")
            for item in positives[:3]:
                st.success(f"{item.get('fact')} {item.get('why_it_matters')}")
        with right:
            st.markdown("**What Atlas is watching**")
            for item in cautions[:3]:
                st.warning(f"{item.get('risk')} {item.get('consequence')}")
            if not cautions:
                st.info("No concrete adverse evidence is populated; Atlas is monitoring the stated thesis conditions.")

        _research_button(
            ticker,
            f"{key_prefix}_{ticker}",
        )


def render_morning_brief(
    rows: Sequence[Mapping[str, Any]],
) -> None:
    brief = build_morning_brief(rows)

    st.markdown("## Morning Brief")
    st.caption(
        "A concise overview derived from the current Atlas research universe. "
        "Live futures and economic-calendar data are not included in this initial release."
    )

    metrics = st.columns(5)
    metrics[0].metric("Market Posture", brief["market_bias"])
    metrics[1].metric("BUY NOW", brief["counts"]["buy_now"])
    metrics[2].metric(
        "Accumulate",
        brief["counts"]["accumulate"],
    )
    metrics[3].metric("Monitor", brief["counts"]["monitor"])
    metrics[4].metric("Avoid", brief["counts"]["avoid"])

    st.info(brief["summary"])

    st.markdown("### Leading Themes")
    themes = brief.get("top_themes") or []
    if themes:
        st.write(" · ".join(themes))
    else:
        st.caption(
            "No clear sector concentration is present among the actionable ideas."
        )

    st.markdown("### Highest-Conviction Opportunities")
    opportunities = brief.get("top_opportunities") or []
    if opportunities:
        for index, row in enumerate(opportunities, start=1):
            _opportunity_card(
                row,
                key_prefix=f"morning_opportunity_{index}",
            )
    else:
        st.info(
            "No Buy Now or Accumulate opportunities are available in the current scan."
        )

    with st.expander("Research Monitor List"):
        monitor_list = brief.get("monitor_list") or []
        if monitor_list:
            for row in monitor_list:
                ticker = row.get("ticker") or "UNKNOWN"
                st.write(
                    f"**{ticker}** — Opportunity "
                    f"{_num(row.get('opportunity_score'))}; "
                    f"Confidence {_pct(row.get('confidence_pct'))}"
                )
        else:
            st.caption("No Monitor names are available.")

    with st.expander("Confirmed Avoid Setups"):
        risks = brief.get("top_risks") or []
        if risks:
            for row in risks:
                ticker = row.get("ticker") or "UNKNOWN"
                blocker = (
                    row.get("primary_blocker")
                    or "The current Atlas thesis is materially weak."
                )
                st.warning(f"{ticker}: {blocker}")
        else:
            st.caption(
                "No confirmed Avoid setups are present in the current research universe."
            )


__all__ = ["render_morning_brief"]
