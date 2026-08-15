
"""Streamlit UI for Today's Opportunities and Volume & Momentum."""

from __future__ import annotations

from html import escape
from typing import Any, Mapping, Sequence

import streamlit as st

from engines.daily_opportunities_engine import (
    build_today_opportunities,
    build_volume_momentum,
)
from engines.semantic_fields import canonical_atlas_fair_value


def _money(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "—"
    if abs(number) >= 1_000_000_000:
        return f"${number / 1_000_000_000:.1f}B"
    if abs(number) >= 1_000_000:
        return f"${number / 1_000_000:.1f}M"
    return f"${number:,.2f}"


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


def _open_research(ticker: str, key: str) -> None:
    if st.button(
        f"Open complete Atlas research — {ticker}",
        key=key,
        use_container_width=True,
        type="primary",
    ):
        st.session_state["v104_research_ticker"] = ticker
        st.query_params["research"] = ticker
        st.rerun()


def _card(row: Mapping[str, Any], *, key_prefix: str, volume_mode: bool = False) -> None:
    ticker = str(row.get("ticker") or "UNKNOWN")
    verdict = str(row.get("committee_verdict") or "MONITOR").replace("_", " ").title()

    with st.container(border=True):
        head = st.columns([1.2, 1, 1, 1])
        head[0].markdown(f"### {escape(ticker)}")
        head[1].metric("Atlas Rating", verdict)
        head[2].metric("Opportunity", _num(row.get("opportunity_score")))
        head[3].metric("Confidence", _pct(row.get("confidence_pct")))

        metrics = st.columns(5)
        metrics[0].metric("Today's Move", _pct(row.get("day_change_pct"), signed=True))
        metrics[1].metric("Relative Volume", (
            f"{float(row.get('relative_volume')):.2f}×"
            if row.get("relative_volume") is not None
            else "Under review"
        ))
        metrics[2].metric("Dollar Volume", _money(row.get("dollar_volume")))
        decision_return = row.get("decision_expected_return_pct")
        if decision_return is None:
            decision_return = row.get("expected_return_pct")
        target_source = str(row.get("decision_target_source") or "").lower()
        upside_label = (
            "Wall Street Implied Upside"
            if "analyst" in target_source or "wall_street" in target_source
            else "Decision-Target Implied Upside"
        )
        metrics[3].metric(upside_label, _pct(decision_return, signed=True))
        metrics[4].metric("Atlas Fair Value", _money(canonical_atlas_fair_value(row)))

        if volume_mode:
            st.markdown(
                f"**Volume interpretation:** "
                f"{escape(str(row.get('volume_signal') or 'Under review'))}"
            )

        st.markdown("#### Atlas Perspective")
        st.write(
            row.get("daily_ai_summary")
            or "Atlas does not yet have enough normalized evidence for a daily summary."
        )

        guidance = row.get("guidance_summary") or {}
        reasons = guidance.get("supporting_facts") or []
        cautions = guidance.get("key_risks") or []
        left, right = st.columns(2)
        with left:
            st.markdown("**Why it is interesting**")
            for item in reasons[:3]:
                st.success(f"{item.get('fact')} {item.get('why_it_matters')}")
        with right:
            st.markdown("**What Atlas is watching**")
            for item in cautions[:3]:
                st.warning(f"{item.get('risk')} {item.get('consequence')}")
            if not cautions:
                st.info("No concrete adverse evidence is populated; Atlas is monitoring the stated thesis conditions.")

        _open_research(ticker, f"{key_prefix}_{ticker}")


def render_today_opportunities(rows: Sequence[Mapping[str, Any]]) -> None:
    st.markdown("## Today's Opportunities")
    st.caption(
        "Actionable BUY NOW, ACCUMULATE, and MONITOR names ranked by verdict, "
        "confidence, opportunity, and validated return."
    )

    count = st.selectbox(
        "Opportunities shown",
        [5, 10, 15],
        index=1,
        key="today_opportunities_count",
    )
    items = build_today_opportunities(rows, limit=int(count))
    if not items:
        st.info("No actionable Atlas opportunities are available in the current scan.")
        return

    for index, row in enumerate(items, start=1):
        _card(row, key_prefix=f"today_opportunity_{index}")


def render_volume_momentum(rows: Sequence[Mapping[str, Any]]) -> None:
    st.markdown("## Volume & Momentum")
    st.caption(
        "Highlights stocks trading on meaningful relative volume. "
        "High volume alone never creates a BUY NOW rating."
    )

    c1, c2 = st.columns(2)
    with c1:
        threshold = st.selectbox(
            "Minimum relative volume",
            [1.25, 1.5, 2.0, 3.0],
            index=0,
            format_func=lambda value: f"{value:.2f}×",
            key="volume_threshold",
        )
    with c2:
        count = st.selectbox(
            "Volume cards shown",
            [5, 10, 15],
            index=1,
            key="volume_card_count",
        )

    items = build_volume_momentum(
        rows,
        limit=int(count),
        minimum_relative_volume=float(threshold),
    )
    if not items:
        st.info(
            "No stocks meet the selected relative-volume threshold in the current scan. "
            "This may also mean intraday volume data were not loaded."
        )
        return

    signal_filter = st.radio(
        "Volume interpretation",
        [
            "All",
            "Potential accumulation",
            "Potential distribution",
            "Unusual volume",
            "Above-average participation",
        ],
        horizontal=True,
        key="volume_signal_filter",
    )
    if signal_filter != "All":
        items = [
            item
            for item in items
            if item.get("volume_signal") == signal_filter
        ]

    if not items:
        st.info("No volume setups match the selected interpretation.")
        return

    for index, row in enumerate(items, start=1):
        _card(
            row,
            key_prefix=f"volume_momentum_{index}",
            volume_mode=True,
        )


__all__ = [
    "render_today_opportunities",
    "render_volume_momentum",
]
