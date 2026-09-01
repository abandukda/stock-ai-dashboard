"""Decision-oriented Recovery VNext presentation."""
from __future__ import annotations

from html import escape
import os
from typing import Any, Callable, Final, Mapping

import pandas as pd
import streamlit as st

from engines.recovery_decision_story import build_recovery_decision_story
from services.fmp_phase1_intelligence import load_cached_phase1_families
from services.session_stability import emit_page_interactive


RECOVERY_VNEXT_VERSION: Final = "ATLAS_RECOVERY_VNEXT_V1"
RECOVERY_VNEXT_SECTIONS: Final = (
    "Recovery Snapshot", "Why It Fell", "Evidence of Recovery",
    "Financial & Earnings Direction", "Management / Analyst Intelligence",
    "Valuation Support", "Technical Confirmation", "Catalysts",
    "Primary Risks", "What Invalidates Recovery",
    "What ATLAS Is Watching Next", "Deep Evidence",
)


def _source_row(row: Any) -> dict[str, Any]:
    wrapper = dict(row) if hasattr(row, "items") else {}
    raw = wrapper.get("Raw")
    return dict(raw) if isinstance(raw, Mapping) else wrapper


def _display(value: Any, fallback: str = "Unavailable") -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return fallback
    text = str(value).strip()
    return text or fallback


def _number(value: Any, *, money: bool = False, pct: bool = False, signed: bool = False) -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return "Unavailable"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _display(value)
    if money:
        prefix = "-$" if number < 0 else "$"
        magnitude = abs(number)
        if magnitude >= 1_000_000_000:
            return f"{prefix}{magnitude / 1_000_000_000:,.2f}B"
        if magnitude >= 1_000_000:
            return f"{prefix}{magnitude / 1_000_000:,.2f}M"
        return f"{prefix}{magnitude:,.2f}"
    if pct:
        return f"{number:+.1f}%" if signed else f"{number:.1f}%"
    return f"{number:,.1f}"


def _growth_pct(value: Any) -> str:
    """Format persisted growth ratios without changing their underlying value."""
    try:
        return f"{float(value) * 100.0:+,.1f}%"
    except (TypeError, ValueError):
        return "Unavailable"


def _is_extreme_growth(value: Any) -> bool:
    try:
        return abs(float(value) * 100.0) >= 1_000
    except (TypeError, ValueError):
        return False


def _literal_currency_markdown(value: str) -> str:
    """Escape currency delimiters without changing customer-visible values."""
    return str(value).replace("$", r"\$")


_DEEP_FIELD_LABELS: Final = {
    "financials": {
        "revenue_growth": "Revenue growth", "earnings_growth": "Earnings growth",
        "operating_margin": "Operating margin", "gross_margin": "Gross margin",
        "free_cash_flow": "Free cash flow", "cash": "Cash", "total_cash": "Cash",
        "total_debt": "Total debt", "debt": "Total debt",
    },
    "ownership": {
        "institutional_ownership": "Institutional ownership",
        "institutional_ownership_pct": "Institutional ownership",
        "institutional_change": "Institutional change",
        "institutional_change_pct": "Institutional change",
    },
}


def _deep_mapping_rows(family: str, value: Mapping[str, Any]) -> list[dict[str, str]]:
    """Present approved canonical scalars; never dump raw mapping representations."""
    rows: list[dict[str, str]] = []
    for key, label in _DEEP_FIELD_LABELS.get(family, {}).items():
        if key not in value or value[key] is None or isinstance(value[key], (Mapping, list, tuple, set)):
            continue
        raw = value[key]
        if key in {"revenue_growth", "earnings_growth"}:
            display = _growth_pct(raw)
        elif "margin" in key or key.endswith("_pct"):
            display = _number(raw, pct=True, signed=key.endswith("change_pct"))
        elif key in {"free_cash_flow", "cash", "total_cash", "total_debt", "debt"}:
            display = _number(raw, money=True)
        else:
            display = _display(raw)
        rows.append({"Evidence": label, "Value": display})
    return rows


def _section(name: str) -> None:
    section_id = name.lower().replace("&", "and").replace("/", "-")
    section_id = "-".join(section_id.split())
    st.markdown(
        f'<span data-atlas-recovery-section="{escape(section_id)}" style="display:none"></span>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<h3 class="atlas-recovery-section-title">{escape(name)}</h3>', unsafe_allow_html=True)


def _bullets(items: Any, *, fallback: str) -> None:
    rows = list(items or ())
    if not rows:
        st.caption(fallback)
        return
    for item in rows:
        text = item.get("text") if isinstance(item, Mapping) else item
        if text:
            st.markdown(f"- {_display(text)}")


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        body:has([data-atlas-recovery-version]) [data-testid="stAppViewContainer"] { overflow-x:hidden; }
        body:has([data-atlas-recovery-version]) [data-testid="stMainBlockContainer"] {
          padding-bottom:max(6rem, calc(1rem + env(safe-area-inset-bottom))) !important;
        }
        .atlas-recovery-summary {
          border:1px solid rgba(148,163,184,.24); border-radius:1rem;
          padding:.9rem 1rem; margin:.25rem 0 .8rem; background:rgba(15,23,42,.38);
        }
        .atlas-recovery-summary strong { font-size:1.05rem; }
        .atlas-recovery-metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.5rem; margin:.2rem 0 .45rem; }
        .atlas-recovery-metric { border:1px solid rgba(148,163,184,.18); border-radius:.65rem; padding:.5rem .6rem; min-width:0; }
        .atlas-recovery-metric-label { color:#94a3b8; font-size:.78rem; }
        .atlas-recovery-metric-value { font-size:1rem; font-weight:650; overflow-wrap:anywhere; }
        .atlas-recovery-section-title { margin:1.15rem 0 .45rem; }
        @media (max-width:700px) {
          body:has([data-atlas-recovery-version]) [data-testid="stRadio"]:has([role="radiogroup"]) {
            position:sticky !important; top:3.75rem !important; z-index:990 !important;
            margin-top:3rem !important; background:var(--background-color, #0e1117);
            padding:.15rem 0 .2rem !important;
          }
          body:has([data-atlas-recovery-version]) [data-testid="stRadio"] [role="radiogroup"] {
            flex-wrap:nowrap !important; overflow-x:auto !important; padding-bottom:.2rem;
            scrollbar-width:thin;
          }
          body:has([data-atlas-recovery-version]) [data-testid="stRadio"] [role="radiogroup"] label {
            flex:0 0 auto !important; white-space:nowrap; padding:.28rem .52rem !important;
            min-height:30px !important;
          }
          body:has([data-atlas-recovery-version]) [data-testid="stMainBlockContainer"] { padding-top:.2rem !important; }
          body:has([data-atlas-recovery-version]) [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
            gap:.35rem !important;
          }
          body:has([data-atlas-recovery-version]) h1 { margin:.1rem 0 .1rem !important; line-height:1.12 !important; font-size:1.65rem !important; }
          body:has([data-atlas-recovery-version]) [data-testid="stSelectbox"] { margin-bottom:0 !important; }
          .atlas-recovery-section-title { margin:.35rem 0 .2rem !important; line-height:1.18; }
          .atlas-recovery-metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:.35rem; }
          body:has([data-atlas-recovery-version]) [data-testid="stHorizontalBlock"] { gap:.45rem !important; }
          body:has([data-atlas-recovery-version]) [data-testid="stMetric"] { min-width:0 !important; }
          body:has([data-atlas-recovery-version]) [data-testid="stButton"] { margin-right:5.25rem; }
          .atlas-recovery-summary { margin-right:4.75rem; padding:.7rem .75rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _story_for_row(row: Any) -> dict[str, Any]:
    source = _source_row(row)
    ticker = str(source.get("ticker") or source.get("Ticker") or source.get("symbol") or "").upper()
    security_type = str(source.get("security_type") or source.get("quote_type") or "EQUITY")
    cached = load_cached_phase1_families(ticker, security_type=security_type)
    return build_recovery_decision_story(source, evidence_families=cached)


def _render_snapshot(story: Mapping[str, Any], open_research: Callable[[str], Any]) -> None:
    snapshot = story["recovery_snapshot"]
    decision = story["production_decision"]
    recommendation = (
        _display(decision.get("recommendation"))
        if decision.get("semantic_status") == "AVAILABLE" and decision.get("recommendation")
        else "Unavailable — no actionable recommendation published"
    )
    st.markdown(
        f'<span data-atlas-recovery-ticker="{escape(story["ticker"])}" '
        f'data-atlas-recovery-score="{escape(_display(snapshot.get("recovery_score"), ""))}" '
        f'data-atlas-recovery-label="{escape(_display(snapshot.get("recovery_label"), ""))}" '
        f'data-atlas-recovery-evidence="{escape(_display(snapshot.get("evidence_completeness"), ""))}" '
        f'data-atlas-recovery-decision-status="{escape(_display(decision.get("semantic_status"), ""))}" '
        f'data-atlas-recovery-recommendation="{escape(_display(decision.get("recommendation"), ""))}" '
        'style="display:none"></span>',
        unsafe_allow_html=True,
    )
    st.markdown(f"## {story['ticker']} · {_display(story.get('company'))}")
    st.markdown(
        '<div class="atlas-recovery-summary">'
        f'<strong>{escape(_display(snapshot.get("recovery_label"), "Recovery state unavailable"))}</strong><br>'
        f'Recovery score: {escape(_number(snapshot.get("recovery_score")))}/100 · '
        f'{escape(_display(snapshot.get("evidence_completeness")))}'
        '</div>',
        unsafe_allow_html=True,
    )
    primary_metrics = (
        ("ATLAS state", recommendation),
        ("Recovery score", _number(snapshot.get("recovery_score"))),
        ("Drawdown", _number(snapshot.get("drawdown_pct"), pct=True, signed=True)),
        ("Current price", _number(snapshot.get("current_price"), money=True)),
    )
    metric_html = "".join(
        '<div class="atlas-recovery-metric">'
        f'<div class="atlas-recovery-metric-label">{escape(label)}</div>'
        f'<div class="atlas-recovery-metric-value">{escape(value)}</div></div>'
        for label, value in primary_metrics
    )
    st.markdown(f'<div class="atlas-recovery-metric-grid">{metric_html}</div>', unsafe_allow_html=True)
    interaction_id = f"recovery-vnext-research-{story['ticker'].lower()}"
    st.markdown(
        f'<span data-atlas-interaction-id="{escape(interaction_id)}" data-atlas-interaction-type="DRILL_DOWN" '
        'data-atlas-source-page="recovery" data-atlas-expected-page="research-any-ticker" '
        f'data-atlas-expected-ticker="{escape(story["ticker"])}" style="display:none"></span>',
        unsafe_allow_html=True,
    )
    if st.button(f"View Investment Case — {story['ticker']}", key=interaction_id, width="stretch"):
        open_research(story["ticker"])
    cols = st.columns(3)
    cols[0].metric("Expected Return", _number(snapshot.get("expected_return"), pct=True, signed=True))
    cols[1].metric("Opportunity", _number(snapshot.get("opportunity")))
    cols[2].metric("Confidence", _number(snapshot.get("confidence"), pct=True))


def _render_phase1_controls(story: Mapping[str, Any]) -> None:
    ticker = story["ticker"]
    api_key = os.getenv("FMP_API_KEY", "")
    if st.button("Refresh analyst targets & insider evidence", key=f"recovery-phase1-refresh-{ticker}", disabled=not bool(api_key)):
        from services.fmp_phase1_intelligence import refresh_post_shell_evidence
        refresh_post_shell_evidence(ticker, api_key=api_key, security_type=story.get("security_type", "EQUITY"))
        st.rerun()
    if st.button("Load latest management transcript", key=f"recovery-phase1-transcript-{ticker}", disabled=not bool(api_key)):
        from services.fmp_phase1_intelligence import acquire_latest_transcript_intelligence
        acquire_latest_transcript_intelligence(ticker, api_key=api_key)
        st.rerun()


def render_recovery_vnext(recovery_df: Any, *, open_research: Callable[[str], Any]) -> None:
    """Render Recovery from persisted rows and cache reads only."""
    st.markdown(
        f'<span data-atlas-recovery-version="{RECOVERY_VNEXT_VERSION}" style="display:none">recovery-vnext</span>',
        unsafe_allow_html=True,
    )
    _inject_css()
    st.title("Recovery Intelligence")
    st.caption("Why it fell, what recovery evidence exists, what remains unconfirmed, and what changes next.")
    if recovery_df is None or getattr(recovery_df, "empty", True):
        st.info("No securities currently meet the persisted Recovery methodology.")
        emit_page_interactive(st, "Recovery")
        return

    options: list[tuple[str, Any]] = []
    for index, row in recovery_df.iterrows():
        source = _source_row(row)
        ticker = str(source.get("ticker") or source.get("Ticker") or source.get("symbol") or "").upper().strip()
        company = str(source.get("company") or source.get("company_name") or source.get("name") or ticker).strip()
        if ticker:
            options.append((f"{ticker} · {company}", index))
    if not options:
        st.info("Recovery candidates are unavailable in the current persisted scan.")
        emit_page_interactive(st, "Recovery")
        return
    labels = [item[0] for item in options]
    selected_label = st.selectbox("Recovery candidate", labels, key="recovery_vnext_candidate")
    selected_index = options[labels.index(selected_label)][1]
    story = _story_for_row(recovery_df.loc[selected_index])

    _section("Recovery Snapshot")
    _render_snapshot(story, open_research)
    emit_page_interactive(st, "Recovery")

    _section("Why It Fell")
    decline = story["decline_evidence"]
    st.write(decline["summary"])
    if decline.get("persisted_reason"):
        st.caption("Persisted Recovery context: " + decline["persisted_reason"])
    st.caption("Price evidence describes pressure; ATLAS does not infer a causal event without dated supporting evidence.")

    _section("Evidence of Recovery")
    recovery = story["recovery_evidence"]
    columns = st.columns(3)
    with columns[0]:
        st.markdown("**Confirmed evidence**")
        _bullets(recovery["confirmed"], fallback="No confirmed recovery evidence is published.")
    with columns[1]:
        st.markdown("**Early signals**")
        _bullets(recovery["early_signals"], fallback="No early recovery signal is available.")
    with columns[2]:
        st.markdown("**Missing confirmation**")
        _bullets(recovery["missing_confirmation"], fallback="No additional missing confirmation was identified.")

    _section("Financial & Earnings Direction")
    with st.expander("Financial direction", expanded=True):
        financial = story["financial_direction"]
        cols = st.columns(4)
        cols[0].metric("Revenue growth", _growth_pct(financial.get("revenue_growth")))
        cols[1].metric("Earnings growth", _growth_pct(financial.get("earnings_growth")))
        cols[2].metric("Free cash flow", _number(financial.get("free_cash_flow"), money=True))
        cols[3].metric("Total debt", _number(financial.get("total_debt"), money=True))
        extreme = [
            label for label, value in (("Revenue growth", financial.get("revenue_growth")), ("Earnings growth", financial.get("earnings_growth")))
            if _is_extreme_growth(value)
        ]
        if extreme:
            st.caption("Very large year-over-year change; interpret against the prior-period base.")
        st.caption("Unavailable metrics remain unavailable; partial evidence is expected outside deep finalists.")
    with st.expander("Latest earnings direction", expanded=False):
        earnings = story["earnings_direction"]
        cols = st.columns(3)
        cols[0].metric("EPS actual", _number(earnings.get("eps_actual")))
        cols[1].metric("EPS surprise", _number(earnings.get("eps_surprise_pct"), pct=True, signed=True))
        cols[2].metric("Revenue surprise", _number(earnings.get("revenue_surprise_pct"), pct=True, signed=True))
        st.caption(_display(earnings.get("estimate_history_status")))

    _section("Management / Analyst Intelligence")
    with st.expander("Management transcript and analyst detail", expanded=False):
        context = story["management_analyst_context"]
        transcript = context["transcript"]
        st.markdown("**What management emphasized**")
        _bullets(transcript.get("management_themes"), fallback="Transcript intelligence has not been loaded for this ticker.")
        st.markdown("**Supported opportunities**")
        _bullets(transcript.get("supported_opportunities"), fallback="No transcript-supported opportunity is available.")
        st.markdown("**Supported risks**")
        _bullets(transcript.get("supported_risks"), fallback="No transcript-supported risk is available.")
        consensus = context["analyst_consensus"]
        st.markdown("**Wall Street consensus**")
        st.markdown(_literal_currency_markdown(
            f"Mean {_number(consensus.get('mean'), money=True)} · "
            f"Range {_number(consensus.get('low'), money=True)}–{_number(consensus.get('high'), money=True)} · "
            f"Coverage {_number(consensus.get('count'))}"
        ))
        if context.get("target_actions"):
            st.dataframe(pd.DataFrame(context["target_actions"]), hide_index=True, use_container_width=True)
            st.caption(context["prior_target_limitation"])
        else:
            st.caption("Individual analyst target-action evidence is unavailable.")
        st.caption(_display(context.get("estimate_history_status")))
        _render_phase1_controls(story)

    _section("Valuation Support")
    valuation = story["valuation_context"]
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Atlas**")
        st.metric("Atlas FV", _number(valuation.get("atlas_fair_value"), money=True))
        st.metric("Expected Return", _number(valuation.get("expected_return"), pct=True, signed=True))
    with cols[1]:
        st.markdown("**Wall Street**")
        st.metric("Consensus target", _number(valuation.get("wall_street_mean"), money=True))
        target_range = (
            f"Range: {_number(valuation.get('wall_street_low'), money=True)}–"
            f"{_number(valuation.get('wall_street_high'), money=True)}"
        )
        st.caption(_literal_currency_markdown(target_range))
    st.caption("Wall Street consensus is contextual and remains separate from Atlas FV.")

    _section("Technical Confirmation")
    technical = story["technical_confirmation"]
    st.info(f"Recovery confirmation: {_display(technical.get('confirmation'))}")
    cols = st.columns(4)
    cols[0].metric("Technical state", _display(technical.get("state"), "State not published"))
    cols[1].metric("RSI", _number(technical.get("rsi")))
    cols[2].metric("ATR", _number(technical.get("atr_pct"), pct=True))
    cols[3].metric("Support", _number(technical.get("support"), money=True))
    trade_boundary = (
        f"Entry {_number(technical.get('entry_low'), money=True)}–{_number(technical.get('entry_high'), money=True)} · "
        f"Stop {_number(technical.get('stop'), money=True)} · Targets {_number(technical.get('target_1'), money=True)} / {_number(technical.get('target_2'), money=True)}"
    )
    st.caption(_literal_currency_markdown(trade_boundary))

    _section("Catalysts")
    _bullets(story["catalysts"], fallback="No verified Recovery catalyst is currently available.")
    _section("Primary Risks")
    _bullets(story["primary_risks"], fallback="No specific Recovery risk is published beyond evidence limitations.")
    _section("What Invalidates Recovery")
    _bullets(story["invalidation_conditions"], fallback="Explicit Recovery invalidation evidence is unavailable.")
    _section("What ATLAS Is Watching Next")
    _bullets(story["watch_next"], fallback="No grounded monitoring checkpoint is available.")

    _section("Deep Evidence")
    with st.expander("Price, earnings, financial, ownership, and provenance", expanded=False):
        deep = story["deep_evidence"]
        for label, key in (
            ("Price history", "price_history"), ("Earnings history", "earnings_history"),
            ("Financials", "financials"), ("Analyst target actions", "analyst_target_actions"),
            ("Insider transactions · contextual/non-scoring", "insider_transactions"),
            ("Ownership", "ownership"), ("News", "news"),
            ("Political context · non-scoring", "political"),
        ):
            st.markdown(f"**{label}**")
            value = deep.get(key)
            if isinstance(value, Mapping):
                rows = _deep_mapping_rows(key, value)
                if rows:
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                else:
                    st.caption("Unavailable")
            elif value:
                st.dataframe(pd.DataFrame(value), hide_index=True, use_container_width=True)
            else:
                st.caption("Unavailable")
        provenance = story["provenance"]
        st.caption("Evidence IDs: " + (", ".join(provenance["evidence_ids"]) or "Unavailable"))
        for limitation in provenance["limitations"]:
            st.caption(limitation)


__all__ = ["RECOVERY_VNEXT_SECTIONS", "RECOVERY_VNEXT_VERSION", "render_recovery_vnext"]
