"""Decision-oriented Earnings Intelligence presentation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from typing import Any, Callable, Final, Mapping

import pandas as pd
import streamlit as st

from engines.earnings_decision_story import build_earnings_decision_story
from services.session_stability import emit_page_interactive


EARNINGS_VNEXT_VERSION: Final = "ATLAS_EARNINGS_VNEXT_V1"
EARNINGS_VNEXT_SECTIONS: Final = (
    "Earnings Snapshot", "What Happened", "Why It Matters",
    "Guidance & Estimate Changes", "Market Reaction",
    "ATLAS Decision After Earnings", "What Changes the Thesis",
    "What ATLAS Is Watching Next", "Deep Evidence",
)


def _display(value: Any, fallback: str = "Unavailable") -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set)) or (isinstance(value, str) and not value.strip()):
        return fallback
    return str(value)


def _metric(value: Any, *, pct: bool = False, money: bool = False) -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return "Unavailable"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _display(value)
    if pct:
        return f"{number:+.1f}%"
    if money:
        magnitude = abs(number)
        if magnitude >= 1_000_000_000:
            return f"${number / 1_000_000_000:,.2f}B"
        if magnitude >= 1_000_000:
            return f"${number / 1_000_000:,.2f}M"
        return f"${number:,.2f}"
    return f"{number:,.2f}"


def _unsigned_pct(value: Any) -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return "Unavailable"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return _display(value)


def _markdown_money(value: Any) -> str:
    return _metric(value, money=True).replace("$", r"\$")


def _customer_date(value: Any) -> str:
    """Format an evidence date for display without changing its source value."""
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return _display(value)
    parsed: datetime | None = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            seconds = float(value)
            if abs(seconds) >= 100_000_000_000:
                seconds /= 1_000
            parsed = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            parsed = None
    elif isinstance(value, str):
        text = value.strip()
        try:
            if text and text.replace(".", "", 1).lstrip("-").isdigit():
                seconds = float(text)
                if abs(seconds) >= 100_000_000_000:
                    seconds /= 1_000
                parsed = datetime.fromtimestamp(seconds, tz=timezone.utc)
            elif text:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (OverflowError, OSError, ValueError):
            parsed = None
    if parsed is None:
        return _display(value)
    return parsed.strftime("%b %d, %Y").replace(" 0", " ")


def _analyst_actions_for_display(actions: Any) -> list[dict[str, Any]]:
    """Return presentation copies; preserve canonical rows and their ordering."""
    if not isinstance(actions, (list, tuple)):
        return []
    displayed: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, Mapping):
            continue
        row = dict(action)
        for key in ("date", "action_date", "published_at", "timestamp"):
            if key in row:
                row[key] = _customer_date(row[key])
        displayed.append(row)
    return displayed


def _row_payload(row: Any) -> dict[str, Any]:
    # Preserve the wrapper boundary. The story builder reads canonical
    # decision authority from Raw while merging evidence separately.
    return dict(row) if hasattr(row, "items") else {}


def _inject_earnings_css() -> None:
    st.markdown(
        """
        <style>
        body:has([data-atlas-earnings-version]) .stApp,
        body:has([data-atlas-earnings-version]) [data-testid="stAppViewContainer"] { overflow-x:hidden; }
        body:has([data-atlas-earnings-version]) [data-testid="stMainBlockContainer"] {
          padding-bottom:max(6rem, calc(1rem + env(safe-area-inset-bottom))) !important;
        }
        body:has([data-atlas-earnings-version])
        [data-testid="stVerticalBlockBorderWrapper"]:has(.atlas-earnings-card-anchor)
        [data-testid="stButton"] { margin-right:5.5rem; }
        .atlas-earnings-mobile-snapshot { display:none; }
        @media (max-width:700px) {
          body:has([data-atlas-earnings-version])
          [data-testid="stElementContainer"]:has(style),
          body:has([data-atlas-earnings-version])
          [data-testid="stElementContainer"]:has([data-atlas-qa][aria-hidden="true"]) {
            display:none !important;
          }
          body:has([data-atlas-earnings-version]) [data-testid="stRadio"]:has([role="radiogroup"]) {
            position:sticky !important; top:3.75rem !important; z-index:990 !important;
            margin-top:3rem !important;
            background:var(--background-color, #0e1117); padding:.15rem 0 .2rem !important;
          }
          body:has([data-atlas-earnings-version]) [data-testid="stRadio"] [role="radiogroup"] {
            flex-wrap:nowrap !important; overflow-x:auto !important;
            padding-bottom:.2rem; scrollbar-width:thin;
          }
          body:has([data-atlas-earnings-version]) [data-testid="stRadio"] [role="radiogroup"] label {
            flex:0 0 auto !important; white-space:nowrap; padding:.28rem .52rem !important;
            min-height:30px !important;
          }
          body:has([data-atlas-earnings-version]) [data-testid="stMainBlockContainer"] {
            padding-bottom:max(6.5rem, calc(1rem + env(safe-area-inset-bottom))) !important;
          }
          body:has([data-atlas-earnings-version]) [data-testid="stMetric"] { padding-right:6.25rem !important; }
          body:has([data-atlas-earnings-version])
          [data-testid="stVerticalBlockBorderWrapper"]:has(.atlas-earnings-card-anchor)
          [data-testid="stButton"] { margin-right:7rem; }
          body:has([data-atlas-earnings-version]) h1 {
            font-size:2.1rem !important; line-height:1.08 !important; margin:.2rem 0 .15rem !important;
          }
          body:has([data-atlas-earnings-version]) h2#recently-reported {
            font-size:1.6rem !important; line-height:1.15 !important; margin:.45rem 0 .2rem !important;
          }
          body:has([data-atlas-earnings-version])
          [data-testid="stVerticalBlockBorderWrapper"]:has(.atlas-earnings-card-anchor) h3 {
            font-size:1.35rem !important; line-height:1.15 !important; margin:.15rem 0 !important;
          }
          .atlas-earnings-mobile-snapshot {
            display:grid; gap:.18rem; margin:.15rem 0 .35rem; padding:.55rem .65rem;
            border:1px solid rgba(148,163,184,.22); border-radius:.7rem;
            background:rgba(15,23,42,.42); font-size:.82rem; line-height:1.25;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _stories(full_df: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if full_df is None or getattr(full_df, "empty", True):
        return [], []
    reported, upcoming = [], []
    seen = set()
    for _, row in full_df.iterrows():
        payload = _row_payload(row)
        ticker_hint = str(payload.get("ticker") or payload.get("Ticker") or "").upper()
        from services.fmp_phase1_intelligence import load_cached_phase1_families
        context = dict(payload.get("research_context") or {})
        families = dict(context.get("evidence_families") or {})
        families.update(load_cached_phase1_families(ticker_hint, security_type=str(payload.get("security_type") or "EQUITY")))
        context["evidence_families"] = families
        payload["research_context"] = context
        story = build_earnings_decision_story(payload)
        ticker = story["ticker"]
        if ticker in seen or story.get("security_type") == "ETF":
            continue
        seen.add(ticker)
        identity = story["event_identity"]
        if story.get("latest_quarter"):
            reported.append(story)
        next_date = identity.get("next_event_date")
        if next_date and next_date > date.today().isoformat():
            upcoming.append(story)
    reported.sort(key=lambda item: item["event_identity"].get("report_date") or "", reverse=True)
    upcoming.sort(key=lambda item: item["event_identity"].get("next_event_date") or "9999")
    return reported, upcoming


def _decision_label(story: Mapping[str, Any]) -> str:
    decision = story.get("production_decision") or {}
    if decision.get("semantic_status") != "AVAILABLE" or not decision.get("recommendation"):
        return "Unavailable — no actionable recommendation published"
    return str(decision["recommendation"])


def _open_button(story: Mapping[str, Any], open_research: Callable[[str], Any], suffix: str) -> None:
    ticker = story["ticker"]
    interaction_id = f"earnings-vnext-research-{ticker.lower()}-{suffix}"
    st.markdown(
        f'<span data-atlas-interaction-id="{escape(interaction_id)}" data-atlas-interaction-type="DRILL_DOWN" '
        f'data-atlas-source-page="earnings-intelligence" data-atlas-expected-page="research-any-ticker" '
        f'data-atlas-expected-ticker="{escape(ticker)}" aria-hidden="true" style="display:none">earnings-research-link</span>',
        unsafe_allow_html=True,
    )
    if st.button(f"View Investment Case — {ticker}", key=interaction_id, width="stretch"):
        st.session_state["v79_research_focus"] = "earnings"
        open_research(ticker)


def _render_transcript_intelligence(story: Mapping[str, Any], *, suffix: str) -> None:
    """Render/load derived transcript evidence without exposing transcript bodies."""
    transcript = story.get("transcript_intelligence") or {}
    data = transcript.get("data") if isinstance(transcript.get("data"), Mapping) else transcript
    st.markdown("#### What management emphasized")
    if transcript.get("semantic_status") == "AVAILABLE":
        for label, key in (
            ("Management themes", "management_themes"),
            ("Supported opportunities", "supported_opportunities"),
            ("Supported risks", "supported_risks"),
            ("Verified guidance", "verified_guidance_statements"),
            ("What to watch next", "monitoring_items"),
        ):
            items = data.get(key) if isinstance(data, Mapping) else None
            if items:
                st.markdown(f"**{label}**")
                for item in list(items)[:4]:
                    st.markdown(f"- {_display(item.get('text') if isinstance(item, Mapping) else item)}")
        evidence_ids = transcript.get("evidence_ids") or (data.get("source_evidence_ids") if isinstance(data, Mapping) else []) or []
        if evidence_ids:
            st.caption("Transcript evidence: " + ", ".join(str(item) for item in evidence_ids))
    else:
        st.caption("Transcript commentary unavailable for this quarter.")

    import os
    api_key = os.getenv("FMP_API_KEY", "")
    index = story.get("transcript_index") or {}
    periods = ((index.get("data") or {}).get("periods") or []) if isinstance(index.get("data"), Mapping) else []
    periods = [item for item in periods if isinstance(item, Mapping) and item.get("fiscal_year") and item.get("fiscal_quarter")]
    if not periods:
        if st.button("Load earnings-call insight", key=f"earnings-transcript-latest-{suffix}", disabled=not bool(api_key)):
            from services.fmp_phase1_intelligence import acquire_latest_transcript_intelligence
            acquire_latest_transcript_intelligence(story["ticker"], api_key=api_key)
            st.rerun()
    else:
        labels = [f"Q{int(item['fiscal_quarter'])} {int(item['fiscal_year'])}" for item in periods]
        selected = st.selectbox("Earnings-call period", labels, key=f"earnings-transcript-period-{suffix}")
        period = periods[labels.index(selected)]
        if st.button("Load earnings-call insight", key=f"earnings-transcript-load-{suffix}", disabled=not bool(api_key)):
            from services.fmp_phase1_intelligence import acquire_transcript_intelligence
            acquire_transcript_intelligence(
                story["ticker"], year=int(period["fiscal_year"]),
                quarter=int(period["fiscal_quarter"]), api_key=api_key,
            )
            st.rerun()
    operation = transcript.get("operation_metadata") if isinstance(transcript, Mapping) else {}
    if isinstance(operation, Mapping) and operation:
        st.markdown(
            '<span data-atlas-transcript-year="{year}" data-atlas-transcript-quarter="{quarter}" '
            'data-atlas-transcript-cache-status="{status}" data-atlas-transcript-provider-calls="{calls}" '
            'data-atlas-transcript-evidence-id="{evidence}" style="display:none"></span>'.format(
                year=_display(operation.get("selected_year"), ""), quarter=_display(operation.get("selected_quarter"), ""),
                status=_display(operation.get("cache_status"), "UNAVAILABLE"), calls=_display(operation.get("provider_call_count"), "0"),
                evidence=_display(operation.get("transcript_evidence_id"), ""),
            ), unsafe_allow_html=True,
        )


def _reported_card(story: Mapping[str, Any], open_research: Callable[[str], Any], index: int) -> None:
    latest = story.get("latest_quarter") or {}
    st.markdown('<span class="atlas-earnings-card-anchor" aria-hidden="true"></span>', unsafe_allow_html=True)
    st.markdown(f"### {story['ticker']} · {_display(story.get('company'))}")
    st.caption(f"Reported · {_display(story['event_identity'].get('report_date'))} · {_display(story['event_identity'].get('fiscal_period'))}")
    st.markdown(
        '<div class="atlas-earnings-mobile-snapshot">'
        f'<div><strong>Quarter:</strong> {escape(_display(story.get("event_result")))}</div>'
        f'<div><strong>EPS:</strong> {escape(_metric(latest.get("eps_actual")))} vs '
        f'{escape(_metric(latest.get("eps_estimate")))} ({escape(_metric(latest.get("eps_surprise_pct"), pct=True))})</div>'
        f'<div><strong>Revenue:</strong> {escape(_metric(latest.get("revenue_actual"), money=True))} vs '
        f'{escape(_metric(latest.get("revenue_estimate"), money=True))} ({escape(_metric(latest.get("revenue_surprise_pct"), pct=True))})</div>'
        f'<div><strong>ATLAS:</strong> {escape(_decision_label(story))}</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    cols[0].metric("Quarter", _display(story.get("event_result")))
    cols[1].metric("EPS actual", _metric(latest.get("eps_actual")))
    cols[2].metric("EPS estimate", _metric(latest.get("eps_estimate")))
    cols[3].metric("EPS surprise", _metric(latest.get("eps_surprise_pct"), pct=True))
    cols = st.columns(4)
    cols[0].metric("Revenue actual", _metric(latest.get("revenue_actual"), money=True))
    cols[1].metric("Revenue estimate", _metric(latest.get("revenue_estimate"), money=True))
    cols[2].metric("Revenue surprise", _metric(latest.get("revenue_surprise_pct"), pct=True))
    cols[3].metric("ATLAS state", _decision_label(story))
    st.markdown("#### What Happened")
    st.write(_display(story.get("what_happened"), "Reported-quarter evidence is incomplete."))
    st.markdown("#### Why It Matters")
    for item in story.get("why_it_matters") or ["No additional grounded implication is available."]:
        st.markdown(f"- {item}")
    _render_transcript_intelligence(story, suffix=f"reported-{index}-{story['ticker']}")
    with st.expander("Guidance & Estimate Changes"):
        guidance = story.get("management_guidance") or {}
        st.write(guidance.get("status_detail") if guidance.get("semantic_status") != "AVAILABLE" else guidance)
        st.info("Estimate revision direction cannot be verified from the available point-in-time evidence.")
        snapshot = (story.get("analyst_estimate_snapshots") or {})
        st.caption(snapshot.get("status_detail") or "Estimate revision history is still being accumulated.")
        actions = story.get("analyst_actions") or []
        if actions:
            st.dataframe(pd.DataFrame(actions), width="stretch", hide_index=True)
        else:
            st.caption("No dated analyst actions are available in this persisted evidence row.")
    with st.expander("Market Reaction"):
        st.info("Event-aligned market reaction: Unavailable")
    with st.expander("ATLAS Decision After Earnings"):
        decision = story.get("production_decision") or {}
        cols = st.columns(3)
        cols[0].metric("Recommendation", _decision_label(story))
        cols[1].metric("Opportunity", _display(decision.get("opportunity")))
        cols[2].metric("Confidence", _display(decision.get("confidence")))
        cols = st.columns(3)
        cols[0].metric("Atlas FV", _metric(decision.get("atlas_fair_value"), money=True))
        cols[1].metric("Expected Return", _metric(decision.get("decision_expected_return"), pct=True))
        cols[2].metric("Technical state", _display(story.get("technical_state"), "State not published"))
        st.caption(f"Wall Street consensus: {_metric(story.get('wall_street_consensus'), money=True)} · separate from Atlas FV")
    with st.expander("What Changes the Thesis"):
        for label, key in (("Strengthens", "thesis_strengtheners"), ("Weakens", "thesis_weakeners"), ("Invalidates", "thesis_invalidators")):
            st.markdown(f"**{label}**")
            items = story.get(key) or []
            st.write(" · ".join(items) if items else "No grounded condition published.")
    with st.expander("What ATLAS Is Watching Next"):
        for item in story.get("watch_next") or ["Next reported EPS and revenue evidence."]:
            st.markdown(f"- {item}")
    with st.expander("Deep Evidence"):
        history = story.get("history") or []
        if history:
            st.dataframe(pd.DataFrame(history), width="stretch", hide_index=True)
        deep = story.get("deep_evidence") or {}
        analyst = deep.get("analyst") or {}
        st.markdown("**Analyst evidence**")
        if analyst.get("semantic_status") == "AVAILABLE":
            consensus = analyst.get("consensus") or {}
            st.write(
                f"Consensus target: {_markdown_money(consensus.get('mean_target'))} · "
                f"Range: {_markdown_money(consensus.get('low_target'))}–{_markdown_money(consensus.get('high_target'))} · "
                f"Analysts: {_display(consensus.get('analyst_count'))}"
            )
            if analyst.get("actions"):
                with st.expander("Dated analyst actions"):
                    st.dataframe(pd.DataFrame(_analyst_actions_for_display(analyst["actions"])), width="stretch", hide_index=True)
        else:
            st.caption("Analyst actions and consensus are unavailable.")
        target_actions = deep.get("price_target_actions") or {}
        st.markdown("**Individual price-target actions**")
        if target_actions.get("semantic_status") == "AVAILABLE":
            st.dataframe(pd.DataFrame(target_actions.get("actions") or []), width="stretch", hide_index=True)
            st.caption("Prior target was not provided by the source, so ATLAS does not calculate an individual target change.")
        else:
            st.caption("Individual price-target actions are unavailable.")
        news = deep.get("news") or {}
        st.markdown("**Relevant company news**")
        if news.get("semantic_status") == "AVAILABLE":
            with st.expander("Sourced company news"):
                st.dataframe(pd.DataFrame(news.get("items") or []), width="stretch", hide_index=True)
        else:
            st.caption("No verified relevant company news is available.")
        ownership = deep.get("ownership") or {}
        st.markdown("**Ownership**")
        if ownership.get("semantic_status") == "AVAILABLE":
            st.write(
                f"Institutional ownership: {_unsigned_pct(ownership.get('institutional_ownership_pct'))} · "
                f"Insider ownership: {_unsigned_pct(ownership.get('insider_ownership_pct'))}"
            )
            if ownership.get("major_holders"):
                with st.expander("Authoritative holder detail"):
                    st.dataframe(pd.DataFrame(ownership["major_holders"]), width="stretch", hide_index=True)
        else:
            st.caption("Authoritative ownership evidence is unavailable.")
        insider = deep.get("insider_transactions") or {}
        st.markdown("**Insider transactions · contextual only**")
        if insider.get("semantic_status") == "AVAILABLE":
            st.dataframe(pd.DataFrame(insider.get("transactions") or []), width="stretch", hide_index=True)
        else:
            st.caption("Verified insider transaction evidence is unavailable.")
        political = deep.get("political") or {}
        st.markdown("**Political context · non-scoring**")
        if political.get("semantic_status") == "AVAILABLE":
            with st.expander("Verified contextual transactions"):
                st.dataframe(pd.DataFrame(political.get("transactions") or []), width="stretch", hide_index=True)
        else:
            st.caption("No verified company-specific political transactions are available.")
        transcript = story.get("transcript_intelligence") or {}
        st.write("Transcript: " + ("Derived intelligence available" if transcript.get("semantic_status") == "AVAILABLE" else "Transcript commentary unavailable for this quarter."))
        st.write("Limitations: " + " ".join(story.get("limitations") or []))
        st.caption(f"Evidence IDs: {', '.join(story.get('evidence_ids') or []) or 'Unavailable'} · As of: {_display(story.get('as_of'))}")
    _open_button(story, open_research, f"reported-{index}")


def _upcoming_card(story: Mapping[str, Any], open_research: Callable[[str], Any], index: int) -> None:
    st.markdown('<span class="atlas-earnings-card-anchor" aria-hidden="true"></span>', unsafe_allow_html=True)
    st.markdown(f"### {story['ticker']} · {_display(story.get('company'))}")
    st.caption(f"Upcoming · {_display(story['event_identity'].get('next_event_date'))}")
    st.metric("ATLAS state", _decision_label(story))
    st.info("Actual EPS, actual revenue, quarter classification, and post-event thesis impact are not available before the report.")
    st.write("**What ATLAS is watching:** " + " · ".join(story.get("watch_next") or ["The reported EPS and revenue result."]))
    _open_button(story, open_research, f"upcoming-{index}")


def render_earnings_vnext(full_df: Any, *, open_research: Callable[[str], Any]) -> None:
    st.markdown('<span data-atlas-earnings-version="ATLAS_EARNINGS_VNEXT_V1" style="display:none">earnings-vnext</span>', unsafe_allow_html=True)
    _inject_earnings_css()
    st.title("Earnings Intelligence")
    st.caption("What happened, why it matters, what remains unverified, and the current canonical ATLAS decision.")
    emit_page_interactive(st, "Earnings Intelligence")
    reported, upcoming = _stories(full_df)
    st.markdown("## Recently Reported")
    if not reported:
        st.info("No normalized reported-quarter evidence is available in the current persisted universe.")
    for index, story in enumerate(reported[:8]):
        with st.container(border=True):
            _reported_card(story, open_research, index)
    if len(reported) > 8:
        with st.expander(f"More recently reported companies ({len(reported) - 8})"):
            for index, story in enumerate(reported[8:20], 8):
                _reported_card(story, open_research, index)
    st.markdown("## Upcoming Earnings")
    if not upcoming:
        st.info("No upcoming earnings events are verified in the current persisted universe.")
    for index, story in enumerate(upcoming[:8]):
        with st.container(border=True):
            _upcoming_card(story, open_research, index)


__all__ = ["EARNINGS_VNEXT_SECTIONS", "EARNINGS_VNEXT_VERSION", "render_earnings_vnext"]
