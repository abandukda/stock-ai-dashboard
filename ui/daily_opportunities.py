
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
from engines.research_engine import research_navigation_state


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
    interaction_id = "opportunities-research-" + "".join(
        character.lower() if character.isalnum() else "-" for character in f"{key}-{ticker}"
    ).strip("-")
    st.markdown(
        f'<span data-atlas-interaction-id="{escape(interaction_id)}" '
        f'data-atlas-interaction-type="DRILL_DOWN" data-atlas-source-page="today-s-opportunities" '
        f'data-atlas-expected-page="research-any-ticker" data-atlas-expected-ticker="{escape(ticker)}" '
        'aria-hidden="true" style="display:none">opportunity-research-link</span>',
        unsafe_allow_html=True,
    )
    if st.button(
        f"Open complete Atlas research — {ticker}",
        key=key,
        use_container_width=True,
        type="primary",
    ):
        for state_key, state_value in research_navigation_state(ticker).items():
            st.session_state[state_key] = state_value
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
    st.markdown("## Volume Screener")
    st.caption(
        "High volume identifies unusual market participation. ATLAS then evaluates whether the underlying investment case is attractive."
    )
    from services.volume_screener import build_volume_screener
    items=build_volume_screener(rows)
    sort=st.selectbox("Sort by",("Volume intensity","Action","Opportunity","Expected return","Confidence"),key="volume_screener_sort")
    key={"Volume intensity":"relative_volume","Action":"action","Opportunity":"opportunity","Expected return":"expected_return","Confidence":"confidence"}[sort]
    items=sorted(items,key=lambda x:(x.get(key) is None,x.get(key) if isinstance(x.get(key),str) else -(float(x.get(key) or 0))))
    from services.session_stability import emit_page_interactive
    emit_page_interactive(st, "Volume Intelligence")

    if not items:
        st.info("No completed-session unusual-volume candidates are present in this scan.")
        return
    for index,item in enumerate(items[:30],1):
        with st.container(border=True):
            st.markdown(f"### {escape(str(item['ticker']))} — {escape(str(item.get('company') or item['ticker']))}")
            primary=st.columns(2)
            primary[0].metric("Volume State",str(item['volume_state']).replace("_"," ").title())
            primary[1].metric("Completed-Daily RVOL",f"{float(item['relative_volume']):.2f}×")
            secondary=st.columns(3)
            stars={5.0:"★★★★★",4.5:"★★★★½",4.0:"★★★★",3.5:"★★★½",2.5:"★★½",1.0:"★"}.get(item.get('action_stars'),"")
            secondary[0].metric("ATLAS Action",f"{stars} {str(item.get('action') or 'WATCH').replace('_',' ').title()}".strip())
            secondary[1].metric("Price",_money(item.get('price')))
            secondary[2].metric("ATLAS Base FV",_money(item.get('base_fair_value')))
            st.caption(f"Technical: {str(item.get('technical_state') or 'Not published').replace('_',' ').title()} · Opportunity thesis: {str(item.get('opportunity_thesis') or 'Not published').replace('_',' ').title()} · As of {item.get('as_of') or 'not published'}")
            entry=(f"{_money(item.get('entry_low'))}–{_money(item.get('entry_high'))}" if item.get('entry_low') is not None and item.get('entry_high') is not None else "Not published")
            st.write(f"Expected return: {_pct(item.get('expected_return'),signed=True)} · Preferred entry: {entry} · Opportunity: {_num(item.get('opportunity'))} · Confidence: {_pct(item.get('confidence'))}")
            st.caption(f"Average dollar volume: {_money(item.get('dollar_volume'))} · Primary risk: {escape(str(item.get('primary_risk') or 'No additional published risk context'))}")
            catalyst=item.get("latest_catalyst")
            if catalyst:
                label=catalyst.get("headline") if isinstance(catalyst,Mapping) else catalyst
                st.caption(f"Latest sourced catalyst: {escape(str(label))}")
            _open_research(str(item['ticker']),f"volume_screener_{index}")


__all__ = [
    "render_today_opportunities",
    "render_volume_momentum",
]
