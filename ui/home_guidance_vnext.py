"""Guidance-first Home VNext presentation."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import streamlit as st

from engines.research_engine import begin_research_entry, research_interaction_contract
from ui.market_timestamp import format_market_timestamp_et


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


def _ratio(value: Any) -> str:
    """Preserve meaningful persisted ratio precision without inventing it."""
    if value is None:
        return "Unavailable"
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
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


def _atlas_score_presentation(value: Any) -> dict[str, Any]:
    """Map canonical Scan Conviction into display-only Home score treatment."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return {
            "available": False, "display": "Unavailable", "band": "Unavailable",
            "tone": "unavailable", "stars": "☆☆☆☆☆", "filled_stars": 0,
        }
    if not (-1_000_000 < score < 1_000_000):
        return {
            "available": False, "display": "Unavailable", "band": "Unavailable",
            "tone": "unavailable", "stars": "☆☆☆☆☆", "filled_stars": 0,
        }
    if score >= 90:
        band, tone, filled = "Exceptional", "exceptional", 5
    elif score >= 80:
        band, tone, filled = "Strong", "strong", 4
    elif score >= 70:
        band, tone, filled = "Constructive", "constructive", 3
    elif score >= 60:
        band, tone, filled = "Developing", "developing", 2
    else:
        band, tone, filled = "Weak", "weak", 1
    number = f"{score:,.1f}".rstrip("0").rstrip(".")
    return {
        "available": True, "display": f"{number} / 100", "band": band,
        "tone": tone, "stars": "★" * filled + "☆" * (5 - filled),
        "filled_stars": filled, "star_fill_percent": max(0.0, min(100.0, score)),
    }


def _atlas_score(card: Mapping[str, Any]) -> str:
    score = _atlas_score_presentation(card.get("scan_conviction"))
    limited = str(card.get("guidance") or "").upper() == "DATA_LIMITED"
    unavailable = str(card.get("actionability") or "").upper() == "UNAVAILABLE"
    sublabel = (
        f'{score["band"]} setup quality, but not yet actionable.'
        if score["available"] and (limited or unavailable)
        else "Setup quality is shown separately from Guidance and Actionability."
    )
    canonical_value = card.get("scan_conviction")
    return (
        f'<div class="atlas-home-atlas-score atlas-home-score-{score["tone"]}" '
        f'data-atlas-qa="home-atlas-score" data-atlas-score-source="SCAN_CONVICTION" '
        f'data-atlas-score-value="{html.escape(str(canonical_value if canonical_value is not None else "UNAVAILABLE"))}" '
        f'data-atlas-score-band="{html.escape(score["band"])}">'
        '<span class="atlas-home-score-label">ATLAS Setup Score</span>'
        f'<strong>{html.escape(score["display"])}</strong>'
        f'<span class="atlas-home-score-stars" aria-hidden="true" data-atlas-display-only="true" '
        f'style="--atlas-star-fill:{score.get("star_fill_percent", 0):.1f}%">★★★★★</span>'
        f'<b>{html.escape(score["band"] + " Setup" if score["available"] else score["band"])}</b>'
        f'<small>{html.escape(sublabel)}</small>'
        '</div>'
    )


def _market_evidence_badge(card: Mapping[str, Any]) -> str:
    evidence = card.get("market_evidence") if isinstance(card.get("market_evidence"), Mapping) else {}
    status = str(evidence.get("status") or "UNAVAILABLE").upper()
    if status == "LIVE":
        age = _score(evidence.get("freshness_age_seconds"), suffix=" seconds ago")
        label, detail, tone = "LIVE MARKET EVIDENCE", f"Updated {age}", "live"
    elif status in {"STALE", "LAST_KNOWN"}:
        session = str(evidence.get("market_session") or "UNKNOWN").replace("_", " ").title()
        timestamp = format_market_timestamp_et(evidence.get("provider_timestamp"))
        label = "LAST-KNOWN MARKET EVIDENCE" if status == "LAST_KNOWN" else "STALE MARKET EVIDENCE"
        detail, tone = f"{session} · {timestamp} · Current-price authority withheld", "stale"
    else:
        label, detail, tone = "MARKET EVIDENCE UNAVAILABLE", "Persisted evidence shown where available", "unavailable"
    quality = card.get("completed_bar_quality") if isinstance(card.get("completed_bar_quality"), Mapping) else {}
    quality_status = str(quality.get("status") or "").upper()
    quality_codes = tuple(str(code) for code in quality.get("reason_codes") or ())
    quality_copy = ""
    if quality_status == "DEGRADED":
        detail_text = "Regular-session gaps detected" if "REGULAR_SESSION_GAPS_PRESENT" in quality_codes else "Validated bar quality is degraded"
        quality_copy = f'<small>Data quality: Degraded — {html.escape(detail_text.lower())}</small>'
    return (
        f'<div class="atlas-home-market-badge atlas-home-market-{tone}" data-atlas-market-status="{status}" '
        f'data-atlas-market-source="{html.escape(str(evidence.get("source_type") or "UNAVAILABLE"))}">'
        f'<b>{label}</b><span>{html.escape(detail)}</span>{quality_copy}</div>'
    )
def _full_evidence(card: Mapping[str, Any]) -> str:
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
    entry = f"{_money(trade.get('entry_low'))}–{_money(trade.get('entry_high'))}"
    stop = _money(trade.get("stop") if trade.get("stop") is not None else trade.get("stop_loss"))
    target = _money(trade.get("target_1") if trade.get("target_1") is not None else trade.get("target"))
    expected_return = (
        _score(card.get("atlas_expected_return"), suffix="%")
        if card.get("atlas_expected_return") is not None
        else _evidence_value(None, card.get("atlas_expected_return_status"))
    )
    why = "".join(
        f"<li>{html.escape(str(reason))}</li>"
        for reason in card.get("why_atlas") or ("Required canonical confirmation is unavailable.",)
    )
    changes = "".join(
        f"<li>{html.escape(str(checkpoint))}</li>"
        for checkpoint in card.get("what_changes_guidance") or ("Required canonical confirmation must be published.",)
    )
    reason_codes = " · ".join(str(code) for code in card.get("reason_codes") or ()) or "Unavailable"
    return (
        '<div class="atlas-home-full-evidence" data-atlas-qa="home-guidance-full-evidence">'
        '<section><h4>Decision Evidence</h4><div class="atlas-home-full-metrics">'
        + _metric("Opportunity", _score(card.get("opportunity")))
        + _metric("Decision Confidence", _score(card.get("decision_confidence"), suffix="%"))
        + _metric("Evidence Health", _display(card.get("evidence_health")))
        + '</div><p class="atlas-home-full-note">Snapshot evidence health: '
        + html.escape(_display(card.get("snapshot_evidence_health"))) + "</p></section>"
        '<section><h4>Valuation</h4>'
        f'<p><b>Atlas FV:</b> {html.escape(_evidence_value(card.get("atlas_fair_value"), card.get("atlas_valuation_status"), money=True))} '
        f'<small>({html.escape(_display(card.get("atlas_valuation_status")))})</small></p>'
        f'<p><b>Atlas Expected Return:</b> {html.escape(expected_return)} '
        f'<small>({html.escape(_display(card.get("atlas_expected_return_status")))})</small></p></section>'
        '<section><h4>Technical &amp; Volume</h4>'
        f'<p><b>Technical State:</b> {html.escape(_evidence_value(card.get("technical_state"), card.get("technical_status")))}</p>'
        f'<p><b>Technical Evidence:</b> {html.escape(" · ".join(tech_bits) or "Unavailable")}</p>'
        f'<p><b>Volume State:</b> {html.escape(_evidence_value(card.get("volume_state"), card.get("volume_status")))}</p>'
        f'<p><b>Volume Evidence:</b> {html.escape(" · ".join(volume_bits) or "Unavailable")}</p></section>'
        '<section><h4>External Context</h4>'
        f'<p><b>Wall Street:</b> {html.escape(_display(street.get("rating")))} · {_score(street.get("analyst_count"))} analysts · Mean {html.escape(_money(street.get("mean_target")))} · Range {html.escape(_money(street.get("low_target")))}–{html.escape(_money(street.get("high_target")))} · Implied {_score(street.get("implied_upside"), suffix="%")}</p>'
        f'<p><b>Recovery:</b> Score {_score(recovery.get("score"))} · {html.escape(_display(recovery.get("state")))}</p>'
        f'<p><b>Fundamentals:</b> {html.escape(_display(card.get("fundamentals_status")))} · {fundamental_count} persisted fields available</p></section>'
        '<section class="atlas-home-trade"><h4>Trade Plan</h4><div class="atlas-home-trade-row">'
        f'<span data-atlas-trade-segment="entry"><b>Entry</b> {html.escape(entry)}</span>'
        f'<span data-atlas-trade-segment="stop"><b>Stop</b> {html.escape(stop)}</span>'
        f'<span data-atlas-trade-segment="target"><b>Target</b> {html.escape(target)}</span>'
        '</div></section><section><h4>Why ATLAS / What Changes Guidance</h4>'
        f'<div class="atlas-home-full-reasons"><div><b>Why ATLAS</b><ul>{why}</ul></div>'
        f'<div><b>What changes Guidance</b><ul>{changes}</ul></div></div>'
        f'<p class="atlas-home-reason-codes">Canonical reason codes: {html.escape(reason_codes)}</p></section></div>'
    )


def _clean_checkpoint(value: Any) -> str:
    cleaned = str(value or "").strip().rstrip(".")
    for suffix in (" is required", " must be published"):
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    return cleaned


def _atlas_observations(card: Mapping[str, Any]) -> tuple[str, ...]:
    """Select at most four sourced observations without promoting authority."""
    technical = card.get("technical_evidence") or {}
    volume = card.get("volume_evidence") or {}
    recovery = card.get("recovery") or {}
    trade = card.get("trade_plan") or {}
    price = card.get("display_price")
    items: list[str] = []
    low, high = trade.get("entry_low"), trade.get("entry_high")
    relationship = str(card.get("entry_relationship") or "")
    if price is not None and low is not None and high is not None:
        relation = {
            "WITHIN_ENTRY_RANGE": "remains within",
            "BELOW_ENTRY_RANGE": "is below",
            "ABOVE_ENTRY_RANGE": "is above",
        }.get(relationship, "is measured against")
        items.append(f'{card.get("display_price_label") or "Price"} {_money(price)} {relation} the {_money(low)}–{_money(high)} entry range')
    above = []
    below = []
    persisted_price = technical.get("price")
    for label, key in (("SMA20", "sma20"), ("SMA50", "sma50"), ("SMA200", "sma200")):
        average = technical.get(key)
        if persisted_price is not None and average is not None:
            (above if persisted_price >= average else below).append(label)
    if above or below:
        structure = []
        if above: structure.append("above " + " / ".join(above))
        if below: structure.append("below " + " / ".join(below))
        items.append("Persisted price structure is " + " and ".join(structure))
    if recovery.get("score") is not None:
        state = str(recovery.get("state") or "").replace("🟢", "").replace("🟡", "").strip()
        items.append(f"Recovery Score is {_score(recovery.get('score'))}" + (f" — {state}" if state else ""))
    if volume.get("relative_volume") is not None:
        items.append(f"Persisted contextual relative volume is {_ratio(volume.get('relative_volume'))}×")
    return tuple(items[:4])


def _quick_known(card: Mapping[str, Any]) -> tuple[str, ...]:
    """Compatibility alias for the bounded sourced-observation contract."""
    return _atlas_observations(card)


def _quick_needs(card: Mapping[str, Any]) -> tuple[str, ...]:
    labels = {
        "CURRENT_MARKET_EVIDENCE_UNAVAILABLE": "Fresh exact-symbol current-price authority",
        "TECHNICAL_STRUCTURE_UNAVAILABLE": "Canonical technical state",
        "PRICE_EVIDENCE_UNAVAILABLE": "Valid approved price evidence",
        "BASIC_FUNDAMENTALS_UNAVAILABLE": "Canonical fundamental evidence",
        "RISK_EVIDENCE_UNAVAILABLE": "Canonical risk evidence",
        "BREAKOUT_VOLUME_NOT_CONFIRMED": "Approved breakout-volume confirmation",
        "VOLUME_CONFIRMATION_UNAVAILABLE": "Approved volume-confirmation authority",
        "VALUATION_CONFIRMATION_UNAVAILABLE": "Published canonical valuation confirmation",
        "TRADE_PLAN_INCOMPLETE": "Complete canonical trade plan",
    }
    codes = tuple(str(code) for code in card.get("reason_codes") or ())
    if codes:
        return tuple(labels[code] if code in labels else code.replace("_", " ").title() for code in codes)[:3]
    values = card.get("what_changes_guidance") or ()
    return tuple(_clean_checkpoint(value) for value in values if _clean_checkpoint(value))[:3]


def _guidance_explanation(card: Mapping[str, Any]) -> str:
    needs = _quick_needs(card)
    if not needs:
        return "The governed Guidance state has no additional published blocker."
    readable = [value[:1].lower() + value[1:] for value in needs]
    if len(readable) == 1:
        return f"ATLAS lacks {readable[0]}."
    return "ATLAS lacks " + ", ".join(readable[:-1]) + f" and {readable[-1]}."


def _what_changes_call(card: Mapping[str, Any]) -> str:
    needs = _quick_needs(card)
    if not needs:
        return "Guidance will change only when an existing canonical gate produces a different governed result."
    readable = [value[:1].lower() + value[1:] for value in needs]
    conditions = readable[0] if len(readable) == 1 else ", ".join(readable[:-1]) + f" and {readable[-1]}"
    return f"Guidance can advance only after {conditions} are available; remaining confirmation gates would then be evaluated normally."


def _atlas_summary(card: Mapping[str, Any]) -> str:
    ticker = str(card.get("ticker") or "This candidate")
    rank = card.get("production_rank")
    score = _atlas_score_presentation(card.get("scan_conviction"))
    first = f"{ticker} ranks #{rank} with an ATLAS Setup Score of {score['display']}" if rank else f"{ticker} has an ATLAS Setup Score of {score['display']}"
    observations = list(_atlas_observations(card))
    constructive = observations[:3]
    second = "; ".join(constructive) if constructive else "Approved setup evidence is limited"
    risks = []
    rvol = (card.get("volume_evidence") or {}).get("relative_volume")
    if rvol is not None and float(rvol) < 1:
        risks.append(f"persisted participation is {_ratio(rvol)}×")
    quality = card.get("completed_bar_quality") or {}
    if str(quality.get("status") or "").upper() == "DEGRADED":
        risks.append("the current bar stream is degraded by regular-session gaps" if "REGULAR_SESSION_GAPS_PRESENT" in tuple(quality.get("reason_codes") or ()) else "the current bar stream is degraded")
    guidance = _display(card.get("guidance"))
    constraint = " and ".join(risks) if risks else _guidance_explanation(card).rstrip(".")
    return f"{first}. {second}. {constraint[:1].upper() + constraint[1:]}, so governed Guidance remains {guidance}."


def _quick_evidence(card: Mapping[str, Any]) -> str:
    known = "".join(f'<li>{html.escape(item)}</li>' for item in _atlas_observations(card))
    needed = "".join(f'<li>{html.escape(item)}</li>' for item in _quick_needs(card))
    return (
        '<div class="atlas-home-guidance-quick" data-atlas-qa="home-guidance-quick-evidence">'
        f'<section><h4>What ATLAS sees</h4><ul>{known}</ul></section>'
        f'<section><h4>What ATLAS needs</h4><ul>{needed}</ul></section>'
        '</div>'
    )


def _key_numbers(card: Mapping[str, Any]) -> str:
    technical, volume = card.get("technical_evidence") or {}, card.get("volume_evidence") or {}
    recovery, trade = card.get("recovery") or {}, card.get("trade_plan") or {}
    values: list[tuple[str, str]] = []
    if card.get("display_price") is not None:
        values.append((str(card.get("display_price_label") or "Price"), _money(card.get("display_price"))))
    if trade.get("entry_low") is not None and trade.get("entry_high") is not None:
        values.append(("Entry Range", f'{_money(trade.get("entry_low"))}–{_money(trade.get("entry_high"))}'))
    if technical.get("rsi") is not None: values.append(("RSI", _score(technical.get("rsi"))))
    if recovery.get("score") is not None: values.append(("Recovery", _score(recovery.get("score"))))
    if volume.get("relative_volume") is not None: values.append(("Contextual RVOL", _ratio(volume.get("relative_volume")) + "×"))
    if technical.get("resistance") is not None: values.append(("Resistance", _money(technical.get("resistance"))))
    stop = trade.get("stop") if trade.get("stop") is not None else trade.get("stop_loss")
    target = trade.get("target_1") if trade.get("target_1") is not None else trade.get("target")
    if stop is not None or target is not None:
        values.append(("Stop / Target 1", f'{_money(stop)} / {_money(target)}'))
    if card.get("atlas_fair_value") is not None and str(card.get("atlas_valuation_status") or "").upper() == "PUBLISHED":
        values.append(("Atlas FV", _money(card.get("atlas_fair_value"))))
    cells = "".join(_metric(label, value) for label, value in values[:7])
    return f'<div class="atlas-home-key-numbers" data-atlas-qa="home-key-numbers">{cells}</div>'


def _card(card: Mapping[str, Any], *, key: str, first: bool = False) -> None:
    ticker = str(card.get("ticker") or "UNKNOWN")
    guidance = _display(card.get("guidance"))
    actionability = _display(card.get("actionability"))
    evidence_status = (
        "DATA LIMITED"
        if str(card.get("guidance_status") or "").upper() == "DATA_UNAVAILABLE"
        else _display(card.get("evidence_health")).upper()
    )
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
            f'<strong>{html.escape(_money(card.get("display_price")))}</strong>'
            f'<span>{html.escape(str(card.get("display_price_label") or "Price unavailable"))}</span>'
            f'<em>{"ATLAS Guidance" if card.get("presentation_mode") == "ACTIVE" else "Founder Guidance Preview"}</em>'
            '</div>', unsafe_allow_html=True,
        )
        st.markdown(_market_evidence_badge(card), unsafe_allow_html=True)
        st.markdown(
            _atlas_score(card), unsafe_allow_html=True,
        )
        st.markdown("#### ATLAS View")
        st.markdown(
            f'<p class="atlas-home-guidance-summary" data-atlas-qa="home-guidance-summary">{html.escape(_atlas_summary(card))}</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="atlas-home-guidance-primary{guidance_tone}">'
            f'<span><small>{"ATLAS GUIDANCE" if card.get("presentation_mode") == "ACTIVE" else "FOUNDER GUIDANCE PREVIEW"}</small><strong>{html.escape(guidance.upper())}</strong></span>'
            f'<span><small>ACTIONABILITY</small><strong>{html.escape(actionability.upper())}</strong></span>'
            '</div>'
            f'<p class="atlas-home-guidance-explanation">{html.escape(_guidance_explanation(card))}</p>', unsafe_allow_html=True,
        )
        st.markdown(
            f'<span class="atlas-home-evidence-status" data-atlas-qa="home-evidence-status">'
            f'<small>EVIDENCE STATUS</small><b>{html.escape(evidence_status)}</b></span>',
            unsafe_allow_html=True,
        )
        st.markdown("#### Key Numbers")
        st.markdown(_key_numbers(card), unsafe_allow_html=True)
        st.markdown(_quick_evidence(card), unsafe_allow_html=True)
        st.markdown(
            '<div class="atlas-home-change-call" data-atlas-qa="home-change-call">'
            '<b>What changes the call</b>'
            f'<span>{html.escape(_what_changes_call(card))}</span></div>',
            unsafe_allow_html=True,
        )
        _open_research(ticker, f"home_guidance_{key}_{ticker}")
        with st.expander("Full Evidence", expanded=False):
            st.markdown(_full_evidence(card), unsafe_allow_html=True)


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
    .atlas-home-guidance-identity{display:flex;align-items:baseline;flex-wrap:wrap;gap:.22rem .48rem;margin:.02rem 0 .12rem;color:#cbd5e1}.atlas-home-guidance-identity strong{font-size:1.12rem;color:#f8fafc}.atlas-home-guidance-identity span{font-size:.76rem;font-weight:400;color:#7f8b9d}.atlas-home-guidance-identity em{padding:.16rem .48rem;border:1px solid rgba(96,165,250,.28);border-radius:999px;font-size:.72rem;font-style:normal;color:#bfdbfe;background:rgba(37,99,235,.07)}
    .atlas-home-market-badge{display:flex;align-items:center;flex-wrap:wrap;gap:.18rem .5rem;margin:.02rem 0 .14rem;padding:.25rem .48rem;border-radius:8px;border:1px solid rgba(100,116,139,.3);background:rgba(15,23,42,.32)}.atlas-home-market-badge b{font-size:.7rem;letter-spacing:.06em}.atlas-home-market-badge span{font-size:.75rem;color:#94a3b8}.atlas-home-market-badge small{flex-basis:100%;font-size:.72rem;color:#fbbf24}.atlas-home-market-live{border-color:rgba(20,184,166,.42)}.atlas-home-market-live b{color:#2dd4bf}.atlas-home-market-stale b{color:#f59e0b}.atlas-home-market-unavailable b{color:#94a3b8}
    .atlas-home-atlas-score{--score-accent:#14b8a6;display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:.12rem .58rem;margin:.04rem 0 .18rem;padding:.48rem .62rem;border:1px solid color-mix(in srgb,var(--score-accent) 42%,transparent);border-radius:12px;background:linear-gradient(110deg,color-mix(in srgb,var(--score-accent) 16%,transparent),rgba(15,23,42,.18));box-shadow:inset 3px 0 0 var(--score-accent)}.atlas-home-score-label{font-size:.74rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#cbd5e1}.atlas-home-atlas-score strong{font-size:1.42rem;line-height:1;color:#f8fafc;white-space:nowrap}.atlas-home-score-stars{font-size:1rem;letter-spacing:.06em;white-space:nowrap;background:linear-gradient(90deg,var(--score-accent) 0 var(--atlas-star-fill,0%),rgba(148,163,184,.28) var(--atlas-star-fill,0%) 100%);background-clip:text;-webkit-background-clip:text;color:transparent}.atlas-home-atlas-score b{font-size:.82rem;line-height:1.2;color:var(--score-accent);text-transform:uppercase;letter-spacing:.045em}.atlas-home-atlas-score small{grid-column:2/-1;font-size:.78rem;line-height:1.3;color:#cbd5e1}.atlas-home-score-exceptional{--score-accent:#14b8a6}.atlas-home-score-strong{--score-accent:#3b82f6}.atlas-home-score-constructive{--score-accent:#eab308}.atlas-home-score-developing{--score-accent:#f97316}.atlas-home-score-weak{--score-accent:#c96a70}.atlas-home-score-unavailable{--score-accent:#64748b}
    .atlas-home-guidance-primary small,.atlas-home-guidance-primary strong,.atlas-home-guidance-metric small,.atlas-home-guidance-metric b{display:block}.atlas-home-guidance-primary small{font-size:.62rem;letter-spacing:.035em;color:#94a3b8}.atlas-home-guidance-metric small{font-size:.82rem;letter-spacing:.025em;color:#94a3b8;line-height:1.25}.atlas-home-guidance-primary strong{font-size:1.05rem;margin-top:.06rem;line-height:1.08}
    .atlas-home-guidance-core,.atlas-home-guidance-evidence{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.1rem;margin:.06rem 0 .12rem}.atlas-home-guidance-core{padding:.03rem 0;background:rgba(15,23,42,.3);border-radius:8px}.atlas-home-guidance-core .atlas-home-guidance-metric b{font-size:1.15rem;line-height:1.25}.atlas-home-guidance-evidence{grid-template-columns:repeat(4,minmax(0,1fr))}.atlas-home-guidance-metric{padding:.24rem .36rem;border-left:2px solid rgba(148,163,184,.35);min-width:0}.atlas-home-guidance-metric b{overflow-wrap:anywhere;line-height:1.25}.atlas-home-guidance-unavailable b{color:#7f8b9d!important;font-weight:600}.atlas-home-guidance-unavailable small{color:#64748b!important}
    .atlas-home-key-numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:.18rem;margin:.02rem 0 .14rem;padding:.24rem;border:1px solid rgba(96,165,250,.18);border-radius:10px;background:rgba(15,23,42,.24)}.atlas-home-key-numbers .atlas-home-guidance-metric{border-left-color:rgba(96,165,250,.42)}
    .atlas-home-evidence-status{display:inline-flex;align-items:center;gap:.4rem;margin:.02rem 0 .12rem;padding:.16rem .42rem;border:1px solid rgba(245,158,11,.24);border-radius:999px;background:rgba(120,53,15,.08);color:#a8b3c4}.atlas-home-evidence-status small{font-size:.65rem;letter-spacing:.06em}.atlas-home-evidence-status b{font-size:.72rem;color:#fcd38d}
    .atlas-home-guidance-explanation{margin:.02rem 0 .08rem!important;font-size:.8rem;color:#a8b3c4}.atlas-home-change-call{display:grid;gap:.12rem;margin:.04rem 0 .14rem;padding:.4rem .52rem;border-left:3px solid rgba(245,158,11,.5);background:rgba(120,53,15,.07)}.atlas-home-change-call b{font-size:.8rem;color:#fcd38d}.atlas-home-change-call span{font-size:.84rem;line-height:1.4;color:#cbd5e1}
    .atlas-home-guidance-summary{margin:.08rem 0 .12rem!important;font-size:.9rem;line-height:1.42;color:#dbeafe;font-weight:500}.atlas-home-guidance-quick{display:grid;grid-template-columns:1fr 1fr;gap:.55rem;margin:.06rem 0 .14rem}.atlas-home-guidance-quick section{padding:.42rem .55rem;border:1px solid rgba(148,163,184,.18);border-radius:9px;background:rgba(15,23,42,.22)}.atlas-home-guidance-quick h4{margin:0 0 .22rem;font-size:.95rem;line-height:1.3;font-weight:650}.atlas-home-guidance-quick section:first-child h4{color:#bfdbfe}.atlas-home-guidance-quick section:last-child h4{color:#fcd38d}.atlas-home-guidance-quick ul{margin:0;padding-left:1.05rem}.atlas-home-guidance-quick li{margin:.08rem 0;font-size:.86rem;line-height:1.35;color:#cbd5e1}
    .atlas-home-full-evidence{display:block;margin:0;color:#cbd5e1}.atlas-home-full-evidence section{display:block;padding:.72rem 0;border-top:1px solid rgba(148,163,184,.18)}.atlas-home-full-evidence section:first-child{padding-top:0;border-top:0}.atlas-home-full-evidence h4{margin:0 0 .4rem;font-size:1rem;line-height:1.35;font-weight:650;color:#dbeafe}.atlas-home-full-evidence p{margin:.22rem 0;font-size:.875rem;line-height:1.48}.atlas-home-full-evidence p>b,.atlas-home-full-reasons b,.atlas-home-trade-row b{color:#a8b3c4}.atlas-home-full-evidence small{color:#8793a6}.atlas-home-full-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.3rem}.atlas-home-full-metrics .atlas-home-guidance-metric{padding:.32rem .42rem}.atlas-home-full-note{color:#8793a6}.atlas-home-full-reasons{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}.atlas-home-full-reasons ul{margin:.22rem 0 0;padding-left:1.05rem}.atlas-home-full-reasons li{margin:.16rem 0;font-size:.875rem;line-height:1.48}.atlas-home-reason-codes{font-size:.76rem!important;line-height:1.4!important;color:#718096!important;overflow-wrap:anywhere}.atlas-home-trade-row{display:flex;flex-wrap:wrap;align-items:baseline;gap:.2rem .48rem;font-size:.9rem;line-height:1.5}.atlas-home-trade-row span{white-space:nowrap}.atlas-home-trade-row span+span::before{content:"·";margin-right:.48rem;color:#718096}
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
    @media(max-width:480px){.atlas-home-guidance-identity{gap:.18rem .38rem;margin:.02rem 0 .1rem}.atlas-home-guidance-identity strong{font-size:1rem}.atlas-home-guidance-identity span{font-size:.74rem}.atlas-home-guidance-identity em{font-size:.72rem}.atlas-home-atlas-score{grid-template-columns:auto 1fr auto;gap:.1rem .42rem;padding:.4rem .48rem;margin:.03rem 0 .12rem}.atlas-home-score-label{font-size:.7rem}.atlas-home-atlas-score strong{font-size:1.25rem}.atlas-home-score-stars{grid-row:2;grid-column:1/3;font-size:.88rem}.atlas-home-atlas-score b{grid-row:1;grid-column:3}.atlas-home-atlas-score small{grid-row:3;grid-column:1/-1;font-size:.76rem}.atlas-home-guidance-summary{font-size:.84rem;line-height:1.4;margin:.08rem 0 .12rem!important}.atlas-home-guidance-quick{grid-template-columns:1fr;gap:.28rem;margin:.06rem 0 .14rem}.atlas-home-guidance-quick section{padding:.36rem .46rem}.atlas-home-guidance-quick h4{font-size:.92rem}.atlas-home-guidance-quick li{font-size:.825rem;line-height:1.38}.atlas-home-key-numbers{grid-template-columns:repeat(2,minmax(0,1fr));gap:.12rem;padding:.18rem}.atlas-home-key-numbers .atlas-home-guidance-metric{padding:.18rem .22rem}.atlas-home-full-evidence section{padding:.58rem 0}.atlas-home-full-evidence h4{font-size:.95rem;margin-bottom:.32rem}.atlas-home-full-evidence p,.atlas-home-full-reasons li{font-size:.825rem;line-height:1.45}.atlas-home-full-metrics{grid-template-columns:1fr;gap:.18rem}.atlas-home-full-reasons{grid-template-columns:1fr;gap:.55rem}.atlas-home-trade-row{gap:.16rem .38rem;font-size:.84rem}.atlas-home-trade-row span+span::before{margin-right:.38rem}}
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
