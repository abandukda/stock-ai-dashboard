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
    normalized = str(value or "").strip().lower()
    availability_class = " atlas-home-guidance-unavailable" if normalized in {
        "unavailable", "data unavailable", "not applicable", "timestamp unavailable",
    } else ""
    return (
        f'<span class="atlas-home-guidance-metric{availability_class}">'
        f'<small>{html.escape(label)}</small><b>{html.escape(value)}</b></span>'
    )


def _evidence_value(value: Any, status: Any, *, money: bool = False) -> str:
    """Prefer the canonical value; otherwise retain its canonical availability."""
    if value is not None and value != "":
        return _money(value) if money else _display(value)
    normalized = str(status or "DATA_UNAVAILABLE").upper()
    if normalized == "NOT_APPLICABLE":
        return "Not applicable"
    return "Unavailable"


def _compact_number(value: Any) -> str:
    if value is None:
        return "Unavailable"
    try:
        amount = float(value)
        if abs(amount) >= 1_000_000_000:
            return f"{amount / 1_000_000_000:,.1f}B"
        if abs(amount) >= 1_000_000:
            return f"{amount / 1_000_000:,.1f}M"
        return f"{amount:,.1f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _available_snapshot(card: Mapping[str, Any]) -> str:
    technical = card.get("technical_evidence") or {}
    volume = card.get("volume_evidence") or {}
    fundamentals = card.get("fundamentals_evidence") or {}
    street = card.get("wall_street") or {}
    recovery = card.get("recovery") or {}
    price = technical.get("price")
    tech_bits = []
    if technical.get("rsi") is not None:
        tech_bits.append(f"RSI {_score(technical.get('rsi'))}")
    for label, key in (("SMA20", "sma20"), ("SMA50", "sma50"), ("SMA200", "sma200")):
        value = technical.get(key)
        if value is not None:
            relation = "above" if price is not None and price >= value else "below" if price is not None else "vs"
            tech_bits.append(f"Price {relation} {label} {_money(value)}")
    if technical.get("support") is not None or technical.get("resistance") is not None:
        tech_bits.append(f"Support {_money(technical.get('support'))} · Resistance {_money(technical.get('resistance'))}")
    volume_bits = []
    if volume.get("relative_volume") is not None:
        volume_bits.append(f"Relative volume {_score(volume.get('relative_volume'))}×")
    if volume.get("average_volume") is not None:
        volume_bits.append(f"20D avg volume {_compact_number(volume.get('average_volume'))}")
    if volume.get("average_dollar_volume") is not None:
        volume_bits.append(f"Avg dollar volume ${_compact_number(volume.get('average_dollar_volume'))}")
    fundamental_count = sum(value is not None for value in fundamentals.values())
    trade = card.get("trade_plan") or {}
    trade_bits = []
    if trade:
        trade_bits.extend((
            f"Entry {_money(trade.get('entry_low'))}–{_money(trade.get('entry_high'))}",
            f"Stop {_money(trade.get('stop') if trade.get('stop') is not None else trade.get('stop_loss'))}",
            f"Target {_money(trade.get('target_1') if trade.get('target_1') is not None else trade.get('target'))}",
        ))
    rows = (
        ("Valuation Evidence", f"Atlas FV {_evidence_value(card.get('atlas_fair_value'), card.get('atlas_valuation_status'), money=True)} ({_display(card.get('atlas_valuation_status'))}) · Expected Return {_score(card.get('atlas_expected_return'), suffix='%') if card.get('atlas_expected_return') is not None else _evidence_value(None, card.get('atlas_expected_return_status'))}"),
        ("Wall Street", f"{_display(street.get('rating'))} · {_score(street.get('analyst_count'))} analysts · Mean {_money(street.get('mean_target'))} · Range {_money(street.get('low_target'))}–{_money(street.get('high_target'))} · Implied {_score(street.get('implied_upside'), suffix='%')}"),
        ("Recovery", f"Score {_score(recovery.get('score'))} · {_display(recovery.get('state'))}"),
        ("Technical", f"State {_evidence_value(card.get('technical_state'), card.get('technical_status'))} · Evidence {' · '.join(tech_bits) or 'Unavailable'}"),
        ("Volume", f"State {_evidence_value(card.get('volume_state'), card.get('volume_status'))} · Evidence {' · '.join(volume_bits) or 'Unavailable'}"),
        ("Fundamentals", f"Canonical status {_display(card.get('fundamentals_status'))} · {fundamental_count} persisted fields available" if fundamental_count else _display(card.get("fundamentals_status"))),
        ("Trade Plan", " · ".join(trade_bits) or "Unavailable"),
        ("Evidence Health", f"Evaluation {_display(card.get('evidence_health'))} · Snapshot {_display(card.get('snapshot_evidence_health'))}"),
    )
    return '<div class="atlas-home-snapshot-lines" data-atlas-qa="home-guidance-available-evidence"><h4>Canonical evidence detail</h4>' + "".join(
        f'<p><b>{html.escape(label)}:</b> {html.escape(value)}</p>' for label, value in rows
    ) + "</div>"


def _clean_checkpoint(value: Any) -> str:
    cleaned = str(value or "").strip().rstrip(".")
    for suffix in (" is required", " must be published"):
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    return cleaned


def _quick_known(card: Mapping[str, Any]) -> tuple[str, ...]:
    """Select bounded factual evidence without promoting it into a canonical state."""
    technical = card.get("technical_evidence") or {}
    volume = card.get("volume_evidence") or {}
    recovery = card.get("recovery") or {}
    price = technical.get("price")
    items: list[str] = []
    if technical.get("rsi") is not None:
        items.append(f"RSI {_score(technical.get('rsi'))}")
    above = []
    below = []
    for label, key in (("SMA20", "sma20"), ("SMA50", "sma50"), ("SMA200", "sma200")):
        average = technical.get(key)
        if price is not None and average is not None:
            (above if price >= average else below).append(label)
    if above:
        items.append("Above " + " / ".join(above))
    if below:
        items.append("Below " + " / ".join(below))
    if volume.get("relative_volume") is not None:
        items.append(f"Relative volume {_score(volume.get('relative_volume'))}×")
    if recovery.get("score") is not None:
        items.append(f"Recovery Score {_score(recovery.get('score'))}")
    if card.get("trade_plan"):
        items.append("Trade plan available")
    return tuple(items[:5]) or ("Persisted snapshot evidence available",)


def _quick_needs(card: Mapping[str, Any]) -> tuple[str, ...]:
    values = card.get("what_changes_guidance") or ("Required canonical confirmation",)
    return tuple(_clean_checkpoint(value) for value in values if _clean_checkpoint(value))[:3]


def _atlas_summary(card: Mapping[str, Any]) -> str:
    guidance = str(card.get("guidance") or "DATA_LIMITED").upper()
    if guidance == "DATA_LIMITED":
        needs = _quick_needs(card)[:2]
        if needs:
            joined = " and ".join(item[:1].lower() + item[1:] for item in needs)
            verb = "is" if len(needs) == 1 else "are"
            return f"ATLAS has useful snapshot evidence, but {joined} {verb} still required."
        return "ATLAS has useful snapshot evidence, but current canonical confirmation is incomplete."
    return f"ATLAS has published {_display(guidance)} guidance from the approved canonical evaluation."


def _quick_evidence(card: Mapping[str, Any]) -> str:
    known = "".join(f'<li>{html.escape(item)}</li>' for item in _quick_known(card))
    needed = "".join(f'<li>{html.escape(item)}</li>' for item in _quick_needs(card))
    return (
        '<div class="atlas-home-guidance-quick" data-atlas-qa="home-guidance-quick-evidence">'
        f'<section><h4>What ATLAS knows</h4><ul>{known}</ul></section>'
        f'<section><h4>What ATLAS needs</h4><ul>{needed}</ul></section>'
        '</div>'
    )


def _card(card: Mapping[str, Any], *, key: str, first: bool = False) -> None:
    ticker = str(card.get("ticker") or "UNKNOWN")
    guidance = _display(card.get("guidance"))
    actionability = _display(card.get("actionability"))
    guidance_tone = " atlas-home-guidance-state-data-limited" if str(card.get("guidance") or "").upper() == "DATA_LIMITED" else ""
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
        st.caption(f'PRODUCTION RANK #{card.get("production_rank")}')
        st.markdown(f'### {ticker} — {html.escape(str(card.get("company") or ticker))}')
        st.markdown(
            '<div class="atlas-home-guidance-identity">'
            f'<strong>{html.escape(_money(card.get("last_known_price")))}</strong>'
            f'<span>{html.escape(str(card.get("market_customer_label") or "Last-known Price"))}</span>'
            f'<em>{"ATLAS Guidance" if card.get("presentation_mode") == "ACTIVE" else "Founder Guidance Preview"}</em>'
            '</div>', unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="atlas-home-guidance-primary{guidance_tone}">'
            f'<span><small>{"ATLAS GUIDANCE" if card.get("presentation_mode") == "ACTIVE" else "FOUNDER GUIDANCE PREVIEW"}</small><strong>{html.escape(guidance.upper())}</strong></span>'
            f'<span><small>ACTIONABILITY</small><strong>{html.escape(actionability.upper())}</strong></span>'
            '</div>', unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="atlas-home-guidance-core">'
            + _metric("Scan Conviction", _score(card.get("scan_conviction"), suffix="%"))
            + _metric("Atlas FV", _evidence_value(card.get("atlas_fair_value"), card.get("atlas_valuation_status"), money=True))
            + _metric("Wall Street Target", _money((card.get("wall_street") or {}).get("mean_target")))
            + '</div>', unsafe_allow_html=True,
        )
        st.markdown(
            f'<p class="atlas-home-guidance-summary" data-atlas-qa="home-guidance-summary">{html.escape(_atlas_summary(card))}</p>',
            unsafe_allow_html=True,
        )
        st.markdown(_quick_evidence(card), unsafe_allow_html=True)
        _open_research(ticker, f"home_guidance_{key}_{ticker}")
        with st.expander("Full Evidence", expanded=False):
            st.markdown(
                '<div class="atlas-home-guidance-evidence">'
                + _metric("Opportunity", _score(card.get("opportunity")))
                + _metric("Decision Confidence", _score(card.get("decision_confidence"), suffix="%"))
                + _metric("Valuation Status", _display(card.get("atlas_valuation_status")))
                + _metric("Atlas Expected Return", _score(card.get("atlas_expected_return"), suffix="%"))
                + _metric("Expected Return Status", _display(card.get("atlas_expected_return_status")))
                + _metric("Evidence Health", _display(card.get("evidence_health")))
                + '</div>', unsafe_allow_html=True,
            )
            st.markdown(_available_snapshot(card), unsafe_allow_html=True)
            st.markdown("**Why ATLAS**")
            for reason in card.get("why_atlas") or ("Required canonical confirmation is unavailable.",):
                st.markdown(f"- {reason}")
            st.markdown("**What changes Guidance**")
            for checkpoint in card.get("what_changes_guidance") or ("Required canonical confirmation must be published.",):
                st.markdown(f"- {checkpoint}")
            reason_codes = card.get("reason_codes") or ()
            st.caption("Canonical reason codes: " + (" · ".join(str(code) for code in reason_codes) or "Unavailable"))
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
    .atlas-home-guidance-primary{display:grid;grid-template-columns:1.35fr 1fr;gap:.3rem;margin:.06rem 0 .14rem}.atlas-home-guidance-primary span{padding:.28rem .46rem;border-radius:10px;background:rgba(37,99,235,.12);border:1px solid rgba(96,165,250,.3)}
    .atlas-home-guidance-state-data-limited span:first-child{background:linear-gradient(135deg,rgba(245,158,11,.13),rgba(120,53,15,.08));border-color:rgba(245,158,11,.34)}
    .atlas-home-guidance-identity{display:flex;align-items:baseline;flex-wrap:wrap;gap:.25rem .55rem;margin:.02rem 0 .12rem;color:#cbd5e1}.atlas-home-guidance-identity strong{font-size:1.12rem;color:#f8fafc}.atlas-home-guidance-identity span{font-size:.82rem;color:#94a3b8}.atlas-home-guidance-identity em{margin-left:auto;padding:.16rem .48rem;border:1px solid rgba(96,165,250,.28);border-radius:999px;font-size:.72rem;font-style:normal;color:#bfdbfe;background:rgba(37,99,235,.07)}
    .atlas-home-guidance-primary small,.atlas-home-guidance-primary strong,.atlas-home-guidance-metric small,.atlas-home-guidance-metric b{display:block}.atlas-home-guidance-primary small{font-size:.62rem;letter-spacing:.035em;color:#94a3b8}.atlas-home-guidance-metric small{font-size:.82rem;letter-spacing:.025em;color:#94a3b8;line-height:1.25}.atlas-home-guidance-primary strong{font-size:1.05rem;margin-top:.06rem;line-height:1.08}
    .atlas-home-guidance-core,.atlas-home-guidance-evidence{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.1rem;margin:.06rem 0 .12rem}.atlas-home-guidance-core{padding:.03rem 0;background:rgba(15,23,42,.3);border-radius:8px}.atlas-home-guidance-core .atlas-home-guidance-metric b{font-size:1.15rem;line-height:1.25}.atlas-home-guidance-evidence{grid-template-columns:repeat(4,minmax(0,1fr))}.atlas-home-guidance-metric{padding:.24rem .36rem;border-left:2px solid rgba(148,163,184,.35);min-width:0}.atlas-home-guidance-metric b{overflow-wrap:anywhere;line-height:1.25}.atlas-home-guidance-unavailable b{color:#7f8b9d!important;font-weight:600}.atlas-home-guidance-unavailable small{color:#64748b!important}
    .atlas-home-guidance-summary{margin:.08rem 0 .12rem!important;font-size:.9rem;line-height:1.42;color:#dbeafe;font-weight:500}.atlas-home-guidance-quick{display:grid;grid-template-columns:1fr 1fr;gap:.55rem;margin:.06rem 0 .14rem}.atlas-home-guidance-quick section{padding:.42rem .55rem;border:1px solid rgba(148,163,184,.18);border-radius:9px;background:rgba(15,23,42,.22)}.atlas-home-guidance-quick h4{margin:0 0 .22rem;font-size:.95rem;line-height:1.3;font-weight:650}.atlas-home-guidance-quick section:first-child h4{color:#bfdbfe}.atlas-home-guidance-quick section:last-child h4{color:#fcd38d}.atlas-home-guidance-quick ul{margin:0;padding-left:1.05rem}.atlas-home-guidance-quick li{margin:.08rem 0;font-size:.86rem;line-height:1.35;color:#cbd5e1}
    .atlas-home-guidance-status{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.08rem;margin:.02rem 0 .08rem;padding:.08rem .06rem;border-top:1px solid rgba(148,163,184,.18);border-bottom:1px solid rgba(148,163,184,.18)}.atlas-home-guidance-status .atlas-home-guidance-metric{padding:.18rem .28rem;border-left:0}.atlas-home-guidance-status .atlas-home-guidance-metric:nth-child(2){border-left:2px solid rgba(59,130,246,.35);background:rgba(37,99,235,.045)}.atlas-home-guidance-status .atlas-home-guidance-metric:nth-child(3){border-left:2px solid rgba(168,85,247,.35);background:rgba(126,34,206,.045)}.atlas-home-guidance-status small{font-size:.8rem}.atlas-home-guidance-status b{font-size:.92rem;line-height:1.3}
    .atlas-home-snapshot-lines{display:grid;grid-template-columns:1fr 1fr;gap:.18rem .65rem;margin:.08rem 0 .12rem}.atlas-home-snapshot-lines h4{grid-column:1/-1;margin:0;font-size:.98rem;font-weight:600;line-height:1.35;color:#dbeafe}.atlas-home-snapshot-lines p{margin:0;font-size:.875rem;line-height:1.42;color:#cbd5e1}.atlas-home-snapshot-lines b{color:#a8b3c4}.atlas-home-guidance-limited{display:grid;grid-template-columns:1fr 1fr;gap:.45rem;margin:.08rem 0 .12rem;padding:.42rem .5rem;border-radius:8px;background:linear-gradient(135deg,rgba(245,158,11,.075),rgba(15,23,42,.12));border:1px solid rgba(245,158,11,.22)}.atlas-home-guidance-limited>span+span{border-left:1px solid rgba(148,163,184,.18);padding-left:.45rem}.atlas-home-guidance-limited b,.atlas-home-guidance-limited small{display:block}.atlas-home-guidance-limited b{font-size:.95rem;font-weight:600;line-height:1.35;color:#fcd38d}.atlas-home-guidance-limited small{font-size:.85rem;line-height:1.4;margin-top:.12rem;color:#c6cfdd}.atlas-home-guidance-limited code{font-size:.78rem;line-height:1.35;color:#a8b3c4;overflow-wrap:anywhere}
    .atlas-home-guidance-card-marker{height:0}
    body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMarkdownContainer"]{margin-bottom:0!important}
    body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:.3rem}
    body:has([data-atlas-qa="home-guidance-vnext"]) h1,body:has([data-atlas-qa="home-guidance-vnext"]) h2,body:has([data-atlas-qa="home-guidance-vnext"]) h3{margin-top:.35rem;margin-bottom:.25rem;padding:.18rem 0!important}
    body:has([data-atlas-qa="home-guidance-vnext"]) .atlas-home-guidance-hero h1{font-size:2.1rem;line-height:1.06}
    body:has([data-atlas-qa="home-guidance-vnext"]) h2{font-size:1.55rem;line-height:1.1}
    body:has([data-atlas-qa="home-guidance-vnext"]) .stButton>button[kind="primary"]{min-height:2.05rem;padding:.2rem .7rem}
    body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stExpander"] details summary{min-height:2.1rem!important;padding:.12rem .65rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stExpander"] details summary p{font-size:.82rem;margin:0}
    @media(min-width:481px){body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stLayoutWrapper"]>[data-testid="stVerticalBlock"]{gap:.1rem}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stLayoutWrapper"] h3{font-size:1.35rem!important;line-height:1.08!important;padding:.1rem 0!important;margin:0!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stLayoutWrapper"] [data-testid="stElementContainer"]{margin-top:0!important;margin-bottom:0!important}}
    @media(max-width:700px){body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"]:has([role="radiogroup"]){position:sticky!important;top:3.75rem!important;z-index:990!important;margin-top:.35rem!important;background:var(--background-color,#0e1117);padding:.15rem 0 .2rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"] [role="radiogroup"]{flex-wrap:nowrap!important;overflow-x:auto!important;padding-bottom:.2rem;scrollbar-width:thin}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"] [role="radiogroup"] label{flex:0 0 auto!important;white-space:nowrap;padding:.28rem .52rem!important;min-height:30px!important}}
    @media(max-width:480px){body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]{padding-top:.2rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:.24rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stElementContainer"]:has([data-atlas-qa][aria-hidden="true"]){display:none!important}.atlas-home-guidance-hero{padding:.04rem 0 .11rem}.atlas-home-guidance-hero h1{font-size:1.5rem;line-height:1.16;margin:.02rem 0 .08rem}.atlas-home-guidance-hero p{margin:.08rem 0}.atlas-home-guidance-primary{grid-template-columns:1fr 1fr;gap:.18rem;margin:.01rem 0 .06rem}.atlas-home-guidance-primary span{padding:.2rem .3rem}.atlas-home-guidance-primary small{font-size:.68rem}.atlas-home-guidance-primary strong{font-size:.92rem;line-height:1.22}.atlas-home-guidance-core{grid-template-columns:repeat(3,minmax(0,1fr));gap:.06rem;margin:.04rem 0 .08rem}.atlas-home-guidance-core .atlas-home-guidance-metric{padding:.14rem .12rem}.atlas-home-guidance-core small{font-size:.8125rem;line-height:1.25}.atlas-home-guidance-core .atlas-home-guidance-metric b{font-size:1.125rem;line-height:1.25}.atlas-home-guidance-status{grid-template-columns:repeat(2,minmax(0,1fr));gap:.1rem;margin:.02rem 0 .08rem;padding:.1rem .05rem}.atlas-home-guidance-status .atlas-home-guidance-metric{padding:.15rem .16rem}.atlas-home-guidance-status small{font-size:.8125rem}.atlas-home-guidance-status b{font-size:.88rem;line-height:1.3}.atlas-home-guidance-evidence{grid-template-columns:repeat(2,minmax(0,1fr))}h2{margin:.2rem 0!important;font-size:1.25rem!important;line-height:1.2!important}h3{font-size:1rem!important;line-height:1.2!important;margin:.04rem 0!important;padding:.05rem 0!important}.atlas-home-guidance-card-marker+div [data-testid="stVerticalBlock"]{gap:.14rem}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stExpander"] details summary{min-height:1.9rem!important;padding:.08rem .5rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stExpander"] details summary p{font-size:.82rem;white-space:normal;line-height:1.3}}
    @media(max-width:480px){body:has([data-atlas-qa="home-guidance-vnext"]) h2{margin:.1rem 0!important;padding:.02rem 0!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:.2rem!important}.atlas-home-snapshot-lines{grid-template-columns:1fr;gap:.14rem;margin:.08rem 0 .12rem}.atlas-home-snapshot-lines h4{font-size:.95rem;line-height:1.35}.atlas-home-snapshot-lines p{font-size:.825rem;line-height:1.4}.atlas-home-guidance-limited{grid-template-columns:1fr;padding:.3rem .36rem;gap:.22rem;margin:.08rem 0 .12rem}.atlas-home-guidance-limited>span+span{border-left:0;border-top:1px solid rgba(148,163,184,.18);padding-left:0;padding-top:.22rem}.atlas-home-guidance-limited b{font-size:.92rem}.atlas-home-guidance-limited small{font-size:.8125rem;line-height:1.4}.atlas-home-guidance-limited code{font-size:.75rem;line-height:1.35;overflow-wrap:anywhere}}
    @media(max-width:480px){.atlas-home-guidance-identity{gap:.2rem .42rem;margin:.02rem 0 .1rem}.atlas-home-guidance-identity strong{font-size:1rem}.atlas-home-guidance-identity span{font-size:.8rem}.atlas-home-guidance-identity em{width:100%;margin-left:0;font-size:.72rem}.atlas-home-guidance-summary{font-size:.84rem;line-height:1.4;margin:.08rem 0 .12rem!important}.atlas-home-guidance-quick{grid-template-columns:1fr;gap:.28rem;margin:.06rem 0 .14rem}.atlas-home-guidance-quick section{padding:.36rem .46rem}.atlas-home-guidance-quick h4{font-size:.92rem}.atlas-home-guidance-quick li{font-size:.825rem;line-height:1.38}}
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
        if card.get("snapshot_membership") == "CURRENT_RECOVERY_ONLY":
            st.write(f'**{card.get("ticker")}** · Recovery candidate · Recovery Score {_score(score)}')
            st.caption(f'Recovery snapshot: {_timestamp((card.get("recovery") or {}).get("snapshot_timestamp"))} · No current Full Scan Production Rank')
        else:
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
