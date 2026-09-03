"""Guidance-first Home VNext presentation."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import streamlit as st

from engines.research_engine import begin_research_entry, research_interaction_contract


def _display(value: Any) -> str:
    if value is None or value == "":
        return "Unavailable"
    return str(value).replace("_", " ").title()


def _score(value: Any, *, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    try:
        number = float(value)
        return f"{number:,.1f}{suffix}"
    except (TypeError, ValueError):
        return "Unavailable"


def _money(value: Any) -> str:
    if value is None:
        return "Unavailable"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _timestamp(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(ZoneInfo("America/New_York")).strftime("%b %-d, %Y · %-I:%M %p ET")
    except (TypeError, ValueError):
        return "Timestamp unavailable"


def _open_research(ticker: str, key: str) -> None:
    contract = research_interaction_contract(ticker, key)
    st.markdown(
        f'<span data-atlas-qa="home-guidance-research-cta" data-atlas-ticker="{html.escape(ticker)}" '
        f'data-atlas-interaction-id="{html.escape(contract["interaction_id"])}" '
        f'data-atlas-expected-page="{html.escape(contract["expected_page"])}" '
        f'data-atlas-expected-ticker="{html.escape(contract["expected_ticker"])}" aria-hidden="true" '
        'style="display:none">home-guidance-research-cta</span>', unsafe_allow_html=True,
    )
    if st.button(f"View Investment Case — {ticker}", key=key, type="primary", width="stretch"):
        begin_research_entry(
            st.session_state, ticker, source="HOME_GUIDANCE_VNEXT",
            interaction_id=contract["interaction_id"],
        )
        st.rerun()


def _metric(label: str, value: str) -> str:
    return (
        '<span class="atlas-home-guidance-metric">'
        f'<small>{html.escape(label)}</small><b>{html.escape(value)}</b></span>'
    )


def _card(card: Mapping[str, Any], *, key: str, first: bool = False) -> None:
    ticker = str(card.get("ticker") or "UNKNOWN")
    guidance = _display(card.get("guidance"))
    actionability = _display(card.get("actionability"))
    st.markdown(
        f'<div class="atlas-home-guidance-card-marker" data-atlas-qa="home-guidance-card" '
        f'data-atlas-first="{str(first).lower()}" data-atlas-ticker="{html.escape(ticker)}" '
        f'data-atlas-production-rank="{int(card.get("production_rank") or 0)}" '
        f'data-atlas-guidance="{html.escape(str(card.get("guidance") or "DATA_LIMITED"))}" '
        f'data-atlas-actionability="{html.escape(str(card.get("actionability") or "UNAVAILABLE"))}" '
        f'data-atlas-opportunity="{html.escape(str(card.get("opportunity") if card.get("opportunity") is not None else "UNAVAILABLE"))}" '
        f'data-atlas-decision-confidence="{html.escape(str(card.get("decision_confidence") if card.get("decision_confidence") is not None else "UNAVAILABLE"))}" '
        f'data-atlas-scan-conviction="{html.escape(str(card.get("scan_conviction") if card.get("scan_conviction") is not None else "UNAVAILABLE"))}" '
        'aria-hidden="true"></div>', unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.caption(f'PRODUCTION RANK #{card.get("production_rank")} · {card.get("market_customer_label")}')
        st.markdown(f'### {ticker} — {html.escape(str(card.get("company") or ticker))}')
        st.markdown(
            '<div class="atlas-home-guidance-primary">'
            f'<span><small>{"ATLAS GUIDANCE" if card.get("presentation_mode") == "ACTIVE" else "FOUNDER GUIDANCE PREVIEW"}</small><strong>{html.escape(guidance.upper())}</strong></span>'
            f'<span><small>ACTIONABILITY</small><strong>{html.escape(actionability.upper())}</strong></span>'
            '</div>', unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="atlas-home-guidance-core">'
            + _metric("Opportunity", _score(card.get("opportunity")))
            + _metric("Decision Confidence", _score(card.get("decision_confidence"), suffix="%"))
            + _metric("Scan Conviction", _score(card.get("scan_conviction"), suffix="%"))
            + '</div>', unsafe_allow_html=True,
        )
        _open_research(ticker, f"home_guidance_{key}_{ticker}")
        with st.expander("Evidence, reasons, and what changes Guidance", expanded=False):
            st.markdown(
                '<div class="atlas-home-guidance-evidence">'
                + _metric("Atlas FV", _money(card.get("atlas_fair_value")))
                + _metric("Valuation Status", _display(card.get("atlas_valuation_status")))
                + _metric("Atlas Expected Return", _score(card.get("atlas_expected_return"), suffix="%"))
                + _metric("Expected Return Status", _display(card.get("atlas_expected_return_status")))
                + _metric("Technical", _display(card.get("technical_state")))
                + _metric("Volume", _display(card.get("volume_state")))
                + _metric("Risk Evidence", _display(card.get("risk_status")))
                + _metric("Evidence Health", _display(card.get("evidence_health")))
                + '</div>', unsafe_allow_html=True,
            )
            st.markdown("**Why ATLAS**")
            for reason in card.get("why_atlas") or ("Required canonical confirmation is unavailable.",):
                st.markdown(f"- {reason}")
            st.markdown("**What changes Guidance**")
            for checkpoint in card.get("what_changes_guidance") or ("Required canonical confirmation must be published.",):
                st.markdown(f"- {checkpoint}")
            plan = card.get("trade_plan") or {}
            st.caption(
                "Trade-plan evidence · "
                f"Entry {_money(plan.get('entry_low'))}–{_money(plan.get('entry_high'))} · "
                f"Stop {_money(plan.get('stop') if plan.get('stop') is not None else plan.get('stop_loss'))} · "
                f"Target {_money(plan.get('target_1') if plan.get('target_1') is not None else plan.get('target'))}"
            )


def _section_marker(name: str) -> None:
    st.markdown(
        f'<span data-atlas-qa="home-guidance-section" data-atlas-section="{html.escape(name)}" '
        'aria-hidden="true" style="display:none">home-guidance-section</span>', unsafe_allow_html=True,
    )


def _render_groups(story: Mapping[str, Any], *, emit_interactive) -> None:
    first_rendered = False
    emitted = False
    groups = list(story.get("groups") or ())
    nonempty_counts = [f'{group.get("title")}: {len(group.get("cards") or ())}' for group in groups if group.get("cards")]
    counts = " · ".join(nonempty_counts) or "No candidates currently available"
    st.caption(counts)
    # Preview snapshots can legitimately be entirely DATA_LIMITED. Put the
    # first populated group first so empty categories never displace the first
    # usable investment card from the initial viewport.
    populated = [group for group in groups if group.get("cards")]
    empty = [group for group in groups if not group.get("cards")]
    for group in populated + empty:
        cards = list(group.get("cards") or ())
        _section_marker(str(group.get("title")))
        st.markdown(f'## {group.get("title")}')
        if not cards:
            st.caption("No candidates currently meet this canonical Guidance state.")
            continue
        visible_cards = cards[:6]
        for index, card in enumerate(visible_cards):
            _card(card, key=f'{str(group.get("title")).lower().replace(" ", "_")}_{index}', first=not first_rendered)
            first_rendered = True
            if not emitted:
                emit_interactive()
                emitted = True
        if len(cards) > len(visible_cards):
            st.caption(f"{len(cards) - len(visible_cards)} additional {group.get('title')} candidates remain available in Full Ranked Scan.")
    if not emitted:
        st.info("No persisted Home candidates are available.")
        emit_interactive()


def _comparison(card: Mapping[str, Any]) -> None:
    street = card.get("wall_street") or {}
    atlas, wall = st.columns(2)
    with atlas:
        st.markdown("#### ATLAS")
        st.write(f"Guidance: **{_display(card.get('guidance'))}**")
        st.write(f"Actionability: **{_display(card.get('actionability'))}**")
        st.write(f"Opportunity: **{_score(card.get('opportunity'))}**")
        st.write(f"Decision Confidence: **{_score(card.get('decision_confidence'), suffix='%')}**")
        st.write(f"Atlas FV: **{_money(card.get('atlas_fair_value'))}**")
        st.write(f"Technical / Volume: **{_display(card.get('technical_state'))} / {_display(card.get('volume_state'))}**")
    with wall:
        st.markdown("#### Wall Street")
        st.write(f"Consensus: **{_display(street.get('rating'))}**")
        st.write(f"Analyst count: **{_score(street.get('analyst_count'))}**")
        st.write(f"Mean target: **{_money(street.get('mean_target'))}**")
        st.write(f"Range: **{_money(street.get('low_target'))}–{_money(street.get('high_target'))}**")
        st.write(f"Implied upside: **{_score(street.get('implied_upside'), suffix='%')}**")
    st.caption("Wall Street evidence is contextual. It cannot create ATLAS Guidance or populate Atlas Fair Value.")


def _inject_css() -> None:
    st.markdown("""<style>
    .atlas-home-guidance-hero{padding:.45rem 0 .7rem}.atlas-home-guidance-badge{display:inline-block;border:1px solid rgba(59,130,246,.5);border-radius:999px;padding:.25rem .6rem;font-size:.72rem;font-weight:800}
    .atlas-home-guidance-primary{display:grid;grid-template-columns:1.35fr 1fr;gap:.5rem;margin:.35rem 0 .55rem}.atlas-home-guidance-primary span{padding:.55rem .65rem;border-radius:12px;background:rgba(37,99,235,.12);border:1px solid rgba(96,165,250,.3)}
    .atlas-home-guidance-primary small,.atlas-home-guidance-primary strong,.atlas-home-guidance-metric small,.atlas-home-guidance-metric b{display:block}.atlas-home-guidance-primary small,.atlas-home-guidance-metric small{font-size:.65rem;letter-spacing:.04em;color:#94a3b8}.atlas-home-guidance-primary strong{font-size:1.12rem;margin-top:.12rem}
    .atlas-home-guidance-core,.atlas-home-guidance-evidence{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.38rem;margin:.4rem 0 .55rem}.atlas-home-guidance-evidence{grid-template-columns:repeat(4,minmax(0,1fr))}.atlas-home-guidance-metric{padding:.42rem .5rem;border-left:2px solid rgba(148,163,184,.35);min-width:0}.atlas-home-guidance-metric b{overflow-wrap:anywhere}
    .atlas-home-guidance-card-marker{height:0}.stApp,[data-testid="stAppViewContainer"]{overflow-x:hidden}
    body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:.65rem}
    body:has([data-atlas-qa="home-guidance-vnext"]) h1,body:has([data-atlas-qa="home-guidance-vnext"]) h2,body:has([data-atlas-qa="home-guidance-vnext"]) h3{margin-top:.35rem;margin-bottom:.25rem}
    @media(max-width:700px){body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"]:has([role="radiogroup"]){position:sticky!important;top:3.75rem!important;z-index:990!important;margin-top:.35rem!important;background:var(--background-color,#0e1117);padding:.15rem 0 .2rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"] [role="radiogroup"]{flex-wrap:nowrap!important;overflow-x:auto!important;padding-bottom:.2rem;scrollbar-width:thin}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"] [role="radiogroup"] label{flex:0 0 auto!important;white-space:nowrap;padding:.28rem .52rem!important;min-height:30px!important}}
    @media(max-width:480px){body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]{padding-top:.2rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:.28rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stElementContainer"]:has([data-atlas-qa][aria-hidden="true"]){display:none!important}.atlas-home-guidance-hero{padding:.05rem 0 .15rem}.atlas-home-guidance-hero h1{font-size:1.5rem;line-height:1.08;margin:.02rem 0 .12rem}.atlas-home-guidance-hero p{margin:.12rem 0}.atlas-home-guidance-primary{grid-template-columns:1fr 1fr}.atlas-home-guidance-core{grid-template-columns:repeat(3,minmax(0,1fr));gap:.15rem}.atlas-home-guidance-core .atlas-home-guidance-metric{padding:.25rem .2rem}.atlas-home-guidance-evidence{grid-template-columns:repeat(2,minmax(0,1fr))}h2{margin:.25rem 0!important;font-size:1.25rem!important;line-height:1.12!important}h3{font-size:1.1rem!important;line-height:1.12!important;margin:.1rem 0!important}.atlas-home-guidance-card-marker+div [data-testid="stVerticalBlock"]{gap:.25rem}}
    </style>""", unsafe_allow_html=True)


def render_home_guidance_vnext(story: Mapping[str, Any], *, emit_interactive=None) -> None:
    """Render persisted Guidance shell; optional context occurs after interactivity."""
    if emit_interactive is None:
        from services.session_stability import emit_page_interactive as emit
        emit_interactive = lambda: emit(st, "Home")
    _inject_css()
    st.markdown(
        f'<span data-atlas-qa="home-guidance-vnext" data-atlas-version="{html.escape(str(story.get("version")))}" '
        f'data-atlas-mode="{html.escape(str(story.get("mode")))}" aria-hidden="true" style="display:none">home-guidance-vnext</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="atlas-home-guidance-hero">'
        '<h1>ATLAS Today</h1>'
        f'<span class="atlas-home-guidance-badge">{html.escape(str(story.get("status_label")))}</span>'
        f'<p>{html.escape(str(story.get("freshness_label")))}</p>'
        f'<small>Production scan: {html.escape(_timestamp(story.get("scan_timestamp")))} · {int(story.get("candidate_count", 0))} candidates</small>'
        '</div>', unsafe_allow_html=True,
    )
    st.markdown("## Primary ATLAS Guidance")
    _render_groups(story, emit_interactive=emit_interactive)

    _section_marker("atlas-vs-wall-street")
    st.markdown("## ATLAS vs Wall Street")
    for card in list(story.get("cards") or ())[:3]:
        with st.expander(f'{card.get("ticker")} authority comparison', expanded=False):
            _comparison(card)

    _section_marker("technical-opportunities")
    st.markdown("## Technical Opportunities")
    technical = list(story.get("technical_cards") or ())
    if not technical:
        st.caption("Canonical technical state is unavailable for this snapshot. Raw indicators are not promoted into a technical state.")
    else:
        for card in technical[:5]:
            st.write(f'**{card.get("ticker")}** · {_display(card.get("technical_state"))} · Volume {_display(card.get("volume_state"))}')

    _section_marker("recovery-opportunities")
    st.markdown("## Recovery Opportunities")
    recovery = list(story.get("recovery_cards") or ())
    if not recovery:
        st.caption("No canonical Recovery evidence is available for current Home candidates.")
    for card in recovery[:5]:
        score = (card.get("recovery") or {}).get("score")
        st.write(f'**{card.get("ticker")}** · Recovery Score {_score(score)} · Guidance Preview {_display(card.get("guidance"))}')
        _open_research(str(card.get("ticker")), f'home_recovery_{card.get("ticker")}')

    _section_marker("what-changed")
    st.markdown("## What Changed")
    st.caption((story.get("what_changed") or {}).get("message"))

    _section_marker("watchlist-follow-up")
    st.markdown("## Watchlist / Follow-up")
    watchlist = list(story.get("watchlist_cards") or ())
    if not watchlist:
        st.caption("No current watchlist names are present in the persisted Full Scan snapshot.")
    for card in watchlist[:5]:
        needed = next(iter(card.get("what_changes_guidance") or ()), "Canonical confirmation is required.")
        st.write(f'**{card.get("ticker")}** · {_display(card.get("guidance"))} · {needed}')
        _open_research(str(card.get("ticker")), f'home_watch_{card.get("ticker")}')

    _section_marker("market-news-context")
    st.markdown("## Market & News Context")
    st.caption("Secondary context is available in Research and the dedicated market-intelligence pages. It does not determine Home Guidance.")

    _section_marker("deeper-evidence")
    st.markdown("## Deeper Evidence / Calendar")
    with st.expander("Open methodology and provenance", expanded=False):
        st.write("Founder Guidance V1 uses canonical evidence only. Snapshot preview does not claim live-market authority.")
        st.caption(" · ".join(sorted(set(str(card.get("methodology_version") or "UNAVAILABLE") for card in story.get("cards") or ()))))


__all__ = ["render_home_guidance_vnext"]
