from __future__ import annotations

import html
from typing import Any, Mapping

import streamlit as st

from ui.daily_opportunities import (
    render_today_opportunities,
    render_volume_momentum,
)
from ui.morning_brief import render_morning_brief
from engines.home_discovery import build_home_intelligence
from engines.home_market_data import fetch_home_market_tape
from engines.buy_now_synthesis import (
    build_buy_now_context,
    configured_openai_generator,
    evidence_fingerprint,
    implied_upside_pct,
    synthesize_buy_now,
)
from engines.research_engine import research_navigation_state
from ui.research_report_v104 import (
    inject_v104_polish_css,
    render_candidate_card,
    render_full_research_report,
)


def _avg(rows, key):
    values = []
    for row in rows:
        try:
            values.append(float(row.get(key)))
        except (TypeError, ValueError):
            continue
    return sum(values) / len(values) if values else 0.0


def _render_research_candidates(candidates):
    st.markdown("## Top Research Candidates")
    st.caption(
        "Each card uses individualized Opportunity and Confidence scoring. "
        "Open the full report for financials, earnings, analysts, news, "
        "political activity, ownership, technicals, valuation, and risk."
    )

    if not candidates:
        st.warning("No research candidates are available.")
        return

    f1, f2, f3 = st.columns([1.2, 1.2, 1])

    with f1:
        st.markdown(
            '<div class="atlas-filter-label">Committee verdict</div>',
            unsafe_allow_html=True,
        )
        verdict_filter = st.selectbox(
            "Committee verdict",
            ["All", "Buy Now", "Accumulate", "Monitor", "Avoid"],
            label_visibility="collapsed",
            key="v2_verdict_filter",
        )

    with f2:
        st.markdown(
            '<div class="atlas-filter-label">Opportunity tier</div>',
            unsafe_allow_html=True,
        )
        tier_filter = st.selectbox(
            "Opportunity tier",
            [
                "All",
                "Elite",
                "Exceptional",
                "High",
                "Good",
                "Average",
                "Weak",
            ],
            label_visibility="collapsed",
            key="v2_tier_filter",
        )

    with f3:
        st.markdown(
            '<div class="atlas-filter-label">Cards shown</div>',
            unsafe_allow_html=True,
        )
        count = st.selectbox(
            "Cards shown",
            [5, 8, 10, 12],
            index=2,
            label_visibility="collapsed",
            key="v2_card_count",
        )

    filtered = []
    for row in candidates:
        verdict = str(
            row.get("committee_verdict") or "MONITOR"
        ).replace("_", " ").title()
        tier = str(
            row.get("opportunity_tier") or "Incomplete"
        ).title()

        if verdict_filter != "All" and verdict != verdict_filter:
            continue
        if tier_filter != "All" and tier != tier_filter:
            continue
        filtered.append(row)

    if not filtered:
        st.info("No research candidates match the selected filters.")
        return

    for index, row in enumerate(
        filtered[: int(count)],
        start=1,
    ):
        render_candidate_card(
            row,
            key_prefix=f"v2_candidate_{index}",
        )


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "Unavailable"


def _raw_value(row: Mapping[str, Any], *keys: str):
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for source in (row, raw):
        for key in keys:
            value = source.get(key)
            if value not in (None, "", "Unavailable", "Under review"):
                return value
    return None


def _open_research(ticker: str, key: str) -> None:
    if st.button("Open Full Research →", key=key, use_container_width=True, type="primary"):
        for state_key, state_value in research_navigation_state(ticker).items():
            st.session_state[state_key] = state_value
        st.rerun()


@st.cache_data(ttl=120, show_spinner=False)
def _home_market_tape():
    import yfinance as yf
    return fetch_home_market_tape(yf.download)


def _render_market_tape() -> None:
    tape = _home_market_tape()
    st.markdown("### Live Market Tape")
    cols = st.columns(4)
    for index, row in enumerate(tape["rows"]):
        with cols[index % 4]:
            if row["status"] == "live":
                st.metric(row["label"], _money(row["price"]), _pct(row.get("change_pct")))
            else:
                st.metric(row["label"], "Unavailable")
    st.caption(
        f"Market data updated: {tape['market_data_as_of'] or 'Unavailable'} · delayed / near-real-time {tape['source']} · "
        f"{tape['available']}/{tape['requested']} instruments available. "
        "Live context is not used in persisted Atlas scores or recommendations."
    )


def _synthesis_for(row: Mapping[str, Any]) -> Mapping[str, Any]:
    context = build_buy_now_context(row)
    fingerprint = evidence_fingerprint(context)
    cache = st.session_state.setdefault("home_buy_now_synthesis_cache", {})
    if fingerprint not in cache:
        cache[fingerprint] = synthesize_buy_now(context, configured_openai_generator)
    return cache[fingerprint]


def _render_discovery_card(row: Mapping[str, Any], rank: int) -> None:
    ticker = str(row.get("ticker") or "UNKNOWN")
    company = str(_raw_value(row, "company", "company_name", "Company") or ticker)
    guidance = row.get("guidance_summary") or {}
    facts = guidance.get("supporting_facts") or []
    risks = guidance.get("key_risks") or []
    catalyst = guidance.get("next_catalyst") or {}
    label = row.get("discovery_label") or "BUY NOW DISCOVERY"
    entry = _raw_value(row, "entry_range", "Entry Range")
    if not entry:
        low = _raw_value(row, "entry_low", "Entry Low")
        high = _raw_value(row, "entry_high", "Entry High")
        entry = f"{_money(low)}–{_money(high)}" if low is not None and high is not None else "Unavailable"
    fair_value = _raw_value(row, "atlas_fair_value", "Atlas Fair Value")
    analyst = _raw_value(row, "analyst_target_mean", "Wall Street Consensus")
    price = _raw_value(row, "current_price", "price")
    atlas_upside = implied_upside_pct(fair_value, price)
    analyst_upside = implied_upside_pct(analyst, price)
    synthesis = _synthesis_for(row)

    with st.container(border=True):
        st.caption(f"#{rank} · {label}")
        st.markdown(f'<h3 class="atlas-card-title" title="{html.escape(company)}">{html.escape(ticker)} — {html.escape(company)}</h3>', unsafe_allow_html=True)
        st.markdown("## BUY NOW")
        st.caption(f"Evidence support: {row.get('headline_support_quality') or 'SUPPORTED WITH EVIDENCE GAPS'}")
        metric_html = (
            '<div class="atlas-compact-grid">'
            f'<div class="atlas-compact-metric"><small>Current</small><strong>{html.escape(_money(price))}</strong></div>'
            f'<div class="atlas-compact-metric"><small>Preferred Entry</small><strong>{html.escape(str(entry))}</strong></div>'
            f'<div class="atlas-compact-metric"><small>Atlas FV</small><strong>{html.escape(_money(fair_value))}</strong><em>{html.escape(_pct(atlas_upside) + " vs current" if atlas_upside is not None else "Canonical valuation unavailable")}</em></div>'
            f'<div class="atlas-compact-metric"><small>Wall Street</small><strong>{html.escape(_money(analyst))}</strong><em>{html.escape(_pct(analyst_upside) + " implied upside" if analyst_upside is not None else "Consensus unavailable")}</em></div>'
            '</div>'
        )
        st.markdown(metric_html, unsafe_allow_html=True)
        st.markdown(f"**What Atlas thinks:** {synthesis['what_atlas_thinks']}")
        st.markdown(f"**What to do now:** {synthesis['what_to_do_now']}")
        st.markdown("**WHY BUY NOW**")
        why_now = [str(item) for item in synthesis.get("why_now") or [] if item]
        if why_now:
            st.write(" ".join(why_now[:3]))
        else:
            st.write("Unavailable")
        st.caption(f"Position guidance: {row.get('position_size_range') or 'Unavailable'} · See Full Research for sizing context.")
        st.markdown("**Primary risk**")
        st.write((risks[0] or {}).get("risk") if risks else "Unavailable")
        st.markdown("**Next catalyst**")
        if catalyst.get("date"):
            st.write(f"{catalyst.get('event')} — {catalyst.get('date')}")
        else:
            st.write("Unavailable")
        action = guidance.get("action_now") or {}
        timing = "Buy within the existing preferred entry range." if entry != "Unavailable" else (action.get("entry_timing_context") or "Entry timing is unavailable.")
        st.markdown(f"**Atlas action:** {action.get('current_action') or 'BUY NOW'} · {timing}")
        st.caption(f"Signal as of: {row.get('signal_as_of') or 'Unavailable'}")
        changes = guidance.get("thesis_change_conditions") or {}
        strengthen = (changes.get("strengthen") or [None])[0]
        weaken = (changes.get("weaken") or [None])[0]
        if strengthen or weaken:
            with st.expander("What changes the thesis"):
                if strengthen:
                    st.write(f"**Strengthens if:** {strengthen}")
                if weaken:
                    st.write(f"**Weakens if:** {weaken}")
        _open_research(ticker, f"home_discovery_{rank}_{ticker}")


def _render_action_rows(title: str, rows, key_prefix: str) -> None:
    st.markdown(f"### {title}")
    if not rows:
        st.caption("No current names in this decision context require display.")
        return
    for index, row in enumerate(rows[:5], start=1):
        ticker = str(row.get("ticker") or "UNKNOWN")
        verdict = str(row.get("committee_verdict") or "MONITOR").replace("_", " ")
        guidance = row.get("guidance_summary") or {}
        if not guidance:
            from engines.guidance_summary import build_guidance_summary
            guidance = build_guidance_summary(row)
        facts = guidance.get("supporting_facts") or []
        reason = (facts[0] or {}).get("fact") if facts else "Evidence detail is unavailable."
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"**{ticker} — {verdict}**  \n{reason}")
        with c2:
            _open_research(ticker, f"{key_prefix}_{index}_{ticker}")


def render_v104_home(
    pipeline: Mapping[str, Any],
    *,
    portfolio_tickers=(),
    watchlist_tickers=(),
    signal_as_of=None,
) -> None:
    inject_v104_polish_css()
    st.markdown(
        """<style>
        [data-testid="stHorizontalBlock"] { align-items: stretch; }
        .stApp, [data-testid="stAppViewContainer"] { overflow-x: hidden; }
        @media (max-width: 900px) {
          [data-testid="column"] { min-width: 100% !important; width: 100% !important; }
          [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        }
        .atlas-card-title { margin:0; overflow-wrap:anywhere; line-height:1.18; }
        .atlas-compact-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.45rem .7rem; margin:.45rem 0 .8rem; }
        .atlas-compact-metric { border:1px solid rgba(148,163,184,.2); border-radius:12px; padding:.55rem .65rem; min-width:0; }
        .atlas-compact-metric small { display:block; color:#94A3B8; font-size:.68rem; font-weight:800; text-transform:uppercase; letter-spacing:.04em; }
        .atlas-compact-metric strong { display:block; overflow-wrap:anywhere; font-size:1rem; line-height:1.2; margin-top:.16rem; }
        .atlas-compact-metric em { display:block; color:#94A3B8; font-size:.72rem; font-style:normal; margin-top:.12rem; }
        @media (max-width: 430px) {
          .atlas-compact-grid { gap:.35rem; margin:.35rem 0 .6rem; }
          .atlas-compact-metric { padding:.45rem .5rem; border-radius:10px; }
          .atlas-card-title { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; font-size:1.25rem; }
        }
        </style>""",
        unsafe_allow_html=True,
    )

    ranked = pipeline.get("ranked_candidates") or []
    candidates = pipeline.get("research_candidates") or []
    home = build_home_intelligence(
        ranked,
        portfolio_tickers=portfolio_tickers,
        watchlist_tickers=watchlist_tickers,
    )

    query = st.query_params.get("research")
    if query and not st.session_state.get(
        "v104_research_ticker"
    ):
        st.session_state["v104_research_ticker"] = (
            query[0]
            if isinstance(query, list)
            else str(query)
        )

    st.markdown("# Atlas Morning Decision")
    st.caption("A concise decision dashboard built from the latest persisted Atlas research.")
    _render_market_tape()
    st.caption(f"Atlas signal as of {signal_as_of or 'Unavailable'} · Separate from live market context")

    st.markdown("## Atlas Morning View")
    st.info(home["morning_view"])

    st.markdown("## Decision Snapshot")
    counts = home["counts"]
    c = st.columns(4)
    c[0].metric("BUY NOW", counts["buy_now"], "Review highest-conviction entries")
    if counts["portfolio_actions"]:
        c[1].metric("Portfolio Actions", counts["portfolio_actions"])
    else:
        c[1].metric("Portfolio", "Not configured")
    c[2].metric("Scheduled Earnings", counts["scheduled_earnings"])
    c[3].metric("Watch", counts["monitor"])

    discoveries = home["discoveries"]["selected"]
    for discovery in discoveries:
        discovery["signal_as_of"] = signal_as_of
    st.markdown("## Top BUY NOW Discoveries")
    if len(discoveries) < 3:
        st.info(f"ATLAS found only {len(discoveries)} sufficiently supported headline BUY NOW ideas in the latest scan.")
    discovery_columns = st.columns(max(1, len(discoveries)))
    for index, row in enumerate(discoveries, start=1):
        with discovery_columns[index - 1]:
            _render_discovery_card(row, index)

    selected_ticker = st.session_state.get(
        "v104_research_ticker"
    )
    if selected_ticker:
        selected = next(
            (
                row
                for row in ranked
                if str(row.get("ticker", "")).upper()
                == str(selected_ticker).upper()
            ),
            None,
        )

        if selected:
            render_full_research_report(selected)
            st.markdown("---")
        else:
            st.warning(
                f"{selected_ticker} is not present "
                "in the current scan."
            )

    st.markdown("## More Decisions")
    tabs = st.tabs(["My Stocks", "More Opportunities", "Catalysts", "Calendar"])
    with tabs[0]:
        if home["portfolio_actions"]:
            _render_action_rows("Portfolio Actions", home["portfolio_actions"], "home_portfolio")
        else:
            st.caption("No holdings configured. Add holdings in Portfolio Intelligence.")
        _render_action_rows("Watchlist Actions", home["watchlist_actions"], "home_watchlist")
    with tabs[1]:
        render_today_opportunities(ranked)
    with tabs[2]:
        st.caption(f"{counts['scheduled_earnings']} scheduled earnings · {counts['company_news_events']} sourced company-news events")
        for item in home["catalysts"][:8]:
            catalyst = (item.get("guidance_summary") or {}).get("next_catalyst") or {}
            st.markdown(f"**{item.get('ticker')} · {catalyst.get('date')} · {item.get('catalyst_type')}** — {catalyst.get('event')}  \n_Source: {item.get('catalyst_source')}_")
    with tabs[3]:
        st.caption("Open Market & Economic Calendar below for the full verified calendar.")


__all__ = ["render_v104_home"]
