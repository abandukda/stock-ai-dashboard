from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import streamlit as st

from ui.daily_opportunities import (
    render_today_opportunities,
    render_volume_momentum,
)
from ui.morning_brief import render_morning_brief
from engines.home_discovery import build_client_evidence_view, build_home_intelligence
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
    if st.button("Open Full Research →", key=key, width="stretch", type="primary"):
        for state_key, state_value in research_navigation_state(ticker).items():
            st.session_state[state_key] = state_value
        st.rerun()


@st.cache_data(ttl=120, show_spinner=False)
def _home_market_tape():
    import yfinance as yf
    return fetch_home_market_tape(yf.download)


def _render_market_tape() -> None:
    tape = _home_market_tape()
    items = []
    for row in tape["rows"]:
        label = str(row["label"]).split(" · ", 1)[0]
        if row["status"] != "live":
            items.append(f'<span><b>{html.escape(label)}</b> <em>—</em></span>')
            continue
        value = _money(row["price"])
        if row["symbol"] in {"SPY", "QQQ", "DIA", "IWM"}:
            value = _pct(row.get("change_pct"))
        items.append(f'<span><b>{html.escape(label)}</b> {html.escape(value)}</span>')
    st.markdown(f'<div class="atlas-market-strip">{"".join(items)}</div>', unsafe_allow_html=True)
    updated = ""
    try:
        stamp = datetime.fromisoformat(str(tape.get("market_data_as_of") or "").replace("Z", "+00:00"))
        updated = stamp.astimezone(ZoneInfo("America/New_York")).strftime("%-I:%M %p ET")
    except (TypeError, ValueError):
        pass
    st.caption(f"Delayed market context{f' · Updated {updated}' if updated else ''}")


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
    view = row.get("client_evidence_view") or build_client_evidence_view(row)
    low, high = view["preferred_entry_low"], view["preferred_entry_high"]
    entry = f"{_money(low)}–{_money(high)}" if low is not None and high is not None else "Entry range unavailable"
    fair_value, analyst = view["atlas_fair_value"], view["analyst_consensus"]
    price = view["presentation_price"]
    atlas_upside = implied_upside_pct(fair_value, price)
    analyst_upside = implied_upside_pct(analyst, price)
    synthesis = _synthesis_for(row)

    with st.container(border=True):
        st.caption(f"#{rank} · {label or 'TOP SUPPORTED IDEA'}")
        st.markdown(f'<h3 class="atlas-card-title" title="{html.escape(company)}">{html.escape(ticker)} — {html.escape(company)}</h3>', unsafe_allow_html=True)
        st.markdown("## BUY NOW")
        st.caption(f"Research support: {view['support_quality_client'].title()}")
        metric_html = (
            '<div class="atlas-compact-grid">'
            f'<div class="atlas-compact-metric"><small>Current Price</small><strong>{html.escape(_money(price))}</strong><em>At Atlas signal time</em></div>'
            f'<div class="atlas-compact-metric"><small>Preferred Entry</small><strong>{html.escape(str(entry))}</strong></div>'
            '</div>'
        )
        st.markdown(metric_html, unsafe_allow_html=True)
        status = view["entry_status"]
        icon = "✓" if status["code"] == "INSIDE" else "•"
        st.markdown(f'<div class="atlas-entry-status atlas-entry-{status["code"].lower()}"><b>{icon} {html.escape(status["label"])}</b>{f" · {html.escape(status["action"])}" if status.get("action") else ""}</div>', unsafe_allow_html=True)
        st.markdown("**WHY BUY NOW**")
        why_now = [str(item) for item in synthesis.get("why_now") or [] if item]
        if why_now:
            st.markdown(f'<p class="atlas-why-copy">{html.escape(" ".join(why_now[:3]))}</p>', unsafe_allow_html=True)
        else:
            st.write("Unavailable")
        valuation_html = []
        if fair_value is not None:
            valuation_html.append(f'<span><small>Atlas Fair Value</small><b>{html.escape(_money(fair_value))}</b><em>Atlas-FV Upside: {html.escape(_pct(atlas_upside))}</em></span>')
        if analyst is not None:
            valuation_html.append(f'<span><small>Wall Street Consensus</small><b>{html.escape(_money(analyst))}</b><em>Wall Street Implied Upside: {html.escape(_pct(analyst_upside))}</em></span>')
        if valuation_html:
            st.markdown(f'<div class="atlas-valuation-row">{"".join(valuation_html)}</div>', unsafe_allow_html=True)
        if view.get("valuation_limitation"):
            st.caption(view["valuation_limitation"])
        st.markdown("**Primary risk**")
        st.write((risks[0] or {}).get("risk") if risks else "Open Full Research for the current risk assessment.")
        if catalyst.get("date"):
            st.markdown("**Next catalyst**")
            st.write(f"{catalyst.get('event')} — {catalyst.get('date')}")
        else:
            st.caption("No near-term verified catalyst is currently identified.")
        st.caption(f"Position guidance: {row.get('position_size_range') or 'See Full Research'}")
        _open_research(ticker, f"home_discovery_{rank}_{ticker}")


def _render_all_buy_now(rows: list[Mapping[str, Any]], expected_count: int) -> None:
    if len(rows) != expected_count:
        st.error("BUY NOW ideas are temporarily unavailable. Please open Daily Opportunities.")
        return
    with st.expander(f"View all {expected_count} BUY NOW →", expanded=False):
        for index, row in enumerate(rows, start=1):
            view = row.get("client_evidence_view") or build_client_evidence_view(row)
            price = _money(view["presentation_price"])
            low, high = view["preferred_entry_low"], view["preferred_entry_high"]
            entry = f"{_money(low)}–{_money(high)}" if low is not None and high is not None else "Entry range unavailable"
            status = view["entry_status"]
            c1, c2 = st.columns([4, 1])
            c1.markdown(
                f"**{view['ticker']} — {view['company']} · BUY NOW**  \n"
                f"Current price **{price}** · Preferred entry **{entry}** · **{status['label']}**  \n"
                f"_{view['support_quality_client'].title()}_ · {view['primary_thesis']}"
            )
            with c2:
                _open_research(view["ticker"], f"home_all_buy_now_{index}_{view['ticker']}")


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
        .atlas-market-strip { display:flex; flex-wrap:wrap; gap:.35rem 1rem; padding:.55rem .75rem; border:1px solid rgba(148,163,184,.2); border-radius:12px; font-size:.86rem; }
        .atlas-market-strip span { white-space:nowrap; }
        .atlas-market-strip em { color:#94A3B8; font-style:normal; }
        .atlas-entry-status { margin:-.25rem 0 .75rem; padding:.38rem .55rem; border-radius:8px; font-size:.82rem; background:rgba(148,163,184,.10); }
        .atlas-why-copy { line-height:1.45; margin:.2rem 0 .65rem; }
        .atlas-entry-inside { color:#34D399; }
        .atlas-entry-above { color:#FBBF24; }
        .atlas-valuation-row { display:flex; flex-wrap:wrap; gap:.45rem; margin:.65rem 0; }
        .atlas-valuation-row span { flex:1 1 9rem; padding:.45rem .55rem; border-left:2px solid rgba(148,163,184,.35); }
        .atlas-valuation-row small,.atlas-valuation-row b,.atlas-valuation-row em { display:block; }
        .atlas-valuation-row em { color:#94A3B8; font-size:.72rem; font-style:normal; }
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
    _render_market_tape()

    st.markdown("## Atlas Morning View")
    st.info(home["morning_view"])

    counts = home["counts"]
    st.markdown(f"## {counts['buy_now']} BUY NOW Today")

    discoveries = home["discoveries"]["selected"]
    for discovery in discoveries:
        discovery["signal_as_of"] = signal_as_of
    st.markdown("### Top Supported Ideas")
    if not discoveries and counts["buy_now"]:
        st.info(
            f"{counts['buy_now']} BUY NOW signals were identified, but Atlas does not currently have enough "
            "supporting research evidence to designate a flagship idea."
        )
    elif len(discoveries) < 3:
        st.caption(f"{len(discoveries)} ideas currently meet the stricter flagship research standard.")
    if discoveries:
        discovery_columns = st.columns(len(discoveries))
        for index, row in enumerate(discoveries, start=1):
            with discovery_columns[index - 1]:
                _render_discovery_card(row, index)
    _render_all_buy_now(home["all_buy_now"], counts["buy_now"])

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
        st.caption(f"{counts['scheduled_earnings']} scheduled earnings · {counts['company_news_events']} company-news events")
        for item in home["catalysts"][:8]:
            catalyst = (item.get("guidance_summary") or {}).get("next_catalyst") or {}
            st.markdown(f"**{item.get('ticker')} · {catalyst.get('date')} · {item.get('catalyst_type')}** — {catalyst.get('event')}")
    with tabs[3]:
        st.caption("Open Market & Economic Calendar below for the full verified calendar.")


__all__ = ["render_v104_home"]
