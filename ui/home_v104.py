from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from ui.daily_opportunities import (
    render_today_opportunities,
    render_volume_momentum,
)
from ui.morning_brief import render_morning_brief
from engines.home_discovery import build_home_intelligence
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

    with st.container(border=True):
        st.caption(f"#{rank} · {label}")
        st.markdown(f"### {ticker} — {company}")
        st.markdown("## BUY NOW")
        metrics = st.columns(4)
        metrics[0].metric("Current Price", _money(_raw_value(row, "current_price", "price")))
        metrics[1].metric("Preferred Entry", str(entry))
        metrics[2].metric("Expected Return", _pct(row.get("expected_return_pct")))
        metrics[3].metric("Atlas Fair Value", _money(fair_value))
        st.caption(f"Wall Street consensus: {_money(analyst)} · Position guidance: {row.get('position_size_range') or 'Unavailable'}")
        st.markdown("**Why now**")
        if facts:
            for item in facts[:3]:
                st.write(f"• {item.get('fact')}")
        else:
            st.write("Unavailable")
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

    st.markdown("# Atlas Morning Command Center")
    st.caption("What matters today, what Atlas would investigate now, and where deeper evidence is available.")

    st.markdown("## Atlas Morning View")
    st.info(home["morning_view"])

    st.markdown("## What To Do Today")
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
    st.markdown("## Top BUY NOW Discoveries")
    if len(discoveries) < 3:
        st.info(f"ATLAS found only {len(discoveries)} high-conviction BUY NOW opportunities today.")
    for index, row in enumerate(discoveries, start=1):
        _render_discovery_card(row, index)

    if home["portfolio_actions"]:
        _render_action_rows("Portfolio Actions", home["portfolio_actions"], "home_portfolio")
    else:
        st.caption("Portfolio actions will appear after holdings are added in Portfolio Intelligence.")
    _render_action_rows("Watchlist Actions", home["watchlist_actions"], "home_watchlist")

    st.markdown("## Today's Dated Evidence")
    st.caption(
        f"{counts['scheduled_earnings']} scheduled earnings dates from persisted provider evidence · "
        f"{counts['company_news_events']} current company-specific news events from the filtered news feed."
    )
    catalysts = home["catalysts"][:6]
    if not catalysts:
        st.caption("No verified dated company catalyst is available in the current research set.")
    for row in catalysts:
        catalyst = (row.get("guidance_summary") or {}).get("next_catalyst") or {}
        st.markdown(
            f"**{row.get('ticker')} · {catalyst.get('date')} · {row.get('catalyst_type')}** — "
            f"{catalyst.get('event')}  \n_Source: {row.get('catalyst_source')}_"
        )

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

    st.markdown("## Broader Opportunities")
    tabs = st.tabs(
        [
            "Morning Brief",
            "Today's Opportunities",
            "Volume & Momentum",
            "Research Candidates",
        ]
    )

    with tabs[0]:
        render_morning_brief(ranked)

    with tabs[1]:
        render_today_opportunities(ranked)

    with tabs[2]:
        render_volume_momentum(ranked)

    with tabs[3]:
        _render_research_candidates(candidates)


__all__ = ["render_v104_home"]
