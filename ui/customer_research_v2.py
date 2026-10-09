"""Customer-facing ATLAS Research V2 renderer."""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Mapping

import pandas as pd
import streamlit as st

from services.customer_research_v2 import build_customer_research_v2


def _money(value: Any) -> str:
    return "Unavailable" if value is None else f"${float(value):,.2f}"


def _pct(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "Pending"
    return f"{float(value):+,.2f}%" if signed else f"{float(value):,.2f}%"


def _marker(name: str, ticker: str, **attrs: Any) -> None:
    attributes = " ".join(
        f'data-atlas-{escape(str(key).replace("_", "-"))}="{escape(str(value))}"'
        for key, value in attrs.items()
    )
    st.markdown(
        f'<span data-atlas-qa="research-v2-{escape(name)}" data-atlas-ticker="{escape(ticker)}" '
        f'{attributes} aria-hidden="true" style="display:none">research-v2-{escape(name)}</span>',
        unsafe_allow_html=True,
    )


def _list(items: list[str]) -> None:
    st.markdown("\n".join(f"- {item}" for item in items))


def render_customer_research_v2(report: Mapping[str, Any], *, ask_cta: Callable[[Mapping[str, Any]], None]) -> None:
    page = build_customer_research_v2(report)
    ticker = str(page.get("ticker") or "UNKNOWN")
    if page.get("status") != "AVAILABLE":
        _marker("terminal", ticker, state="RATING_NOT_PUBLISHED")
        st.warning("ATLAS does not have a customer-publishable certified view for this security.")
        return
    h = page["header"]
    _marker("root", ticker, version=page["version"], authority="certified_customer_evaluation")
    st.markdown("""<style>
    .atlas-r2-head{padding:1rem 1.1rem;border:1px solid rgba(45,212,191,.25);border-radius:18px;background:linear-gradient(145deg,rgba(15,23,42,.96),rgba(18,39,51,.88));margin-bottom:.7rem}.atlas-r2-kicker{color:#61d8c3;font-size:.7rem;font-weight:800;letter-spacing:.13em}.atlas-r2-head h1{margin:.2rem 0;font-size:1.8rem}.atlas-r2-meta{color:#94a3b8;font-size:.78rem}.atlas-r2-grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.atlas-r2-panel{padding:.9rem;border:1px solid rgba(148,163,184,.16);border-radius:14px;background:rgba(15,23,42,.55)}
    @media(max-width:700px){.atlas-r2-head h1{font-size:1.35rem}.atlas-r2-grid{grid-template-columns:1fr}[data-testid="stMetric"]{padding-right:.25rem!important}.atlas-r2-panel{padding:.75rem}}
    </style>""", unsafe_allow_html=True)
    st.markdown(
        f'<section class="atlas-r2-head"><div class="atlas-r2-kicker">CERTIFIED ATLAS RESEARCH</div>'
        f'<h1>{escape(ticker)} · {escape(str(page["company"]))}</h1>'
        f'<div class="atlas-r2-meta">Price as of {escape(str(h.get("price_timestamp") or "Unavailable"))} · '
        f'{escape(str(h.get("market_freshness") or "Unavailable"))}</div></section>', unsafe_allow_html=True,
    )
    _marker(
        "stock-header", ticker,
        action=h["action"], fair_value=h["fair_value"],
        opportunity=h["opportunity"], confidence=h["confidence"],
        snapshot=page["identity"].get("evaluation_snapshot"),
    )
    cols = st.columns(6)
    cols[0].metric("Current Price", _money(h["price"]))
    cols[1].metric("Action", h["action"])
    cols[2].metric("ATLAS Fair Value", _money(h["fair_value"]))
    cols[3].metric("Fair Value gap", _pct(h["fair_value_gap_pct"], signed=True))
    cols[4].metric("Opportunity", f'{float(h["opportunity"]):.2f}')
    cols[5].metric("Confidence", _pct(h["confidence"]))
    if h["fair_value_gap_pct"] is not None:
        direction = "above" if h["fair_value_gap_pct"] >= 0 else "below"
        st.caption(f'ATLAS Fair Value is {abs(float(h["fair_value_gap_pct"])):.2f}% {direction} current price. This is not a guaranteed return.')
    if h["action"] not in {"BUY NOW", "BUILD A POSITION"}:
        st.caption("Not currently actionable — continue monitoring the certified evidence.")

    st.markdown("## Since ATLAS Flagged It")
    _marker("since-signal", ticker, status=page["signal"]["status"])
    signal = page["signal"]
    if signal["status"] != "AVAILABLE":
        st.info("No customer-published signal episode is available for this security.")
    else:
        s = st.columns(5)
        s[0].metric("Action at issuance", signal["action"])
        s[1].metric("Reference price", _money(signal["reference_price"]))
        s[2].metric("Return since signal", _pct(signal["stock_return"], signed=True))
        s[3].metric("SPY same period", _pct(signal["spy_return"], signed=True))
        s[4].metric("Excess vs SPY", _pct(signal["excess_return"], signed=True))
        st.caption(f'Signal date: {signal.get("signal_date") or "Unavailable"}')

    st.markdown("## Price / Performance")
    _marker("chart-root", ticker, status=page["chart"]["status"])
    chart = page["chart"]
    if chart["status"] != "AVAILABLE":
        st.info(chart["message"])
    else:
        rows = pd.DataFrame(chart["series"])
        date_key = next((key for key in ("date", "timestamp", "datetime") if key in rows), None)
        close_key = next((key for key in ("adjusted_close", "close", "price") if key in rows), None)
        if date_key and close_key:
            rows[date_key] = pd.to_datetime(rows[date_key], errors="coerce")
            st.line_chart(rows.dropna(subset=[date_key, close_key]).set_index(date_key)[close_key], height=300)
        else:
            st.info("Price history is unavailable under the governed display contract.")
        spy = chart.get("spy_comparison") or {}
        if spy.get("status") == "AVAILABLE":
            st.caption("Normalized SPY comparison is available in this governed licensed QA experience.")
        else:
            st.caption("SPY comparison unavailable for this evidence bundle.")

    st.markdown("## ATLAS Research Summary")
    _marker("summary", ticker, classification="CERTIFIED_ATLAS")
    summary = page["summary"]
    st.markdown("**BOTTOM LINE**")
    st.write(summary["bottom_line"])
    st.markdown("**WHY ATLAS LIKES / DISLIKES IT**")
    _list(summary["why"])
    st.markdown('<div class="atlas-r2-grid">', unsafe_allow_html=True)
    st.markdown("**WHY ATLAS MIGHT BE WRONG**")
    _list(summary["why_might_be_wrong"])
    st.markdown("**WATCH NEXT**")
    _list(summary["watch_next"])
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("## ATLAS vs Wall Street")
    _marker("analyst-module", ticker, status=page["wall_street"]["status"])
    wall = page["wall_street"]
    if wall["status"] == "UNAVAILABLE" or wall["status"] == "DISABLED":
        st.info("Wall Street context is unavailable for this evidence bundle.")
    else:
        a = st.columns(4)
        a[0].metric("Consensus", wall.get("consensus") or "Unavailable")
        a[1].metric("Buy", wall.get("buy_count") if wall.get("buy_count") is not None else "Unavailable")
        a[2].metric("Hold", wall.get("hold_count") if wall.get("hold_count") is not None else "Unavailable")
        a[3].metric("Sell", wall.get("sell_count") if wall.get("sell_count") is not None else "Unavailable")
        b = st.columns(5)
        b[0].metric("Current Price", _money(h["price"]))
        b[1].metric("Wall St. Low", _money(wall.get("target_low")))
        b[2].metric("Wall St. Average", _money(wall.get("target_average")))
        b[3].metric("Wall St. High", _money(wall.get("target_high")))
        b[4].metric("ATLAS Fair Value", _money(h["fair_value"]))
        st.caption(f'{wall.get("analyst_count") or "Unavailable"} analysts · as of {wall.get("as_of") or "Unavailable"} · contextual and non-scoring')

    st.markdown("## Risks / What Would Change the View")
    _marker("risks", ticker)
    _marker("view-change-conditions", ticker)
    left, right = st.columns(2)
    with left:
        st.markdown("### What Could Go Wrong")
        _list(summary["risks"])
    with right:
        st.markdown("### What Would Change the ATLAS View")
        _list(summary["view_changes"])

    st.markdown("## What Changed Recently")
    _marker("what-changed", ticker, status=page["recent_changes"]["status"])
    if page["recent_changes"]["items"]:
        for item in page["recent_changes"]["items"]:
            st.markdown(f'**{item.get("headline") or "Company update"}**  ')
            st.caption(f'{item.get("article_publisher") or "Source unavailable"} · {item.get("article_timestamp") or "Date unavailable"}')
    else:
        st.info("Not enough evidence")

    st.markdown("## Fundamentals Snapshot")
    _marker("fundamentals", ticker, count=len(page["fundamentals"]))
    if page["fundamentals"]:
        for fact in page["fundamentals"][:6]:
            st.metric(fact["fact_name"], fact["display_value"])
    else:
        fundamentals = page.get("qa_fundamentals") or {}
        metrics = [
            ("Revenue growth", fundamentals.get("revenue_growth_ttm_yoy"), "%"),
            ("Operating margin", fundamentals.get("operating_margin_ttm"), "%"),
            ("Forward P/E", fundamentals.get("pe_ttm"), "×"),
            ("Market cap", fundamentals.get("market_capitalization"), "$"),
        ]
        visible = [(label, value, unit) for label, value, unit in metrics if value is not None]
        if visible:
            cols = st.columns(len(visible))
            for col, (label, value, unit) in zip(cols, visible):
                display = f'${float(value)/1_000_000_000:,.1f}B' if unit == "$" else f'{float(value):,.2f}{unit}'
                col.metric(label, display)
        else:
            st.info("Not enough evidence")

    st.markdown("## Catalysts / Next Events")
    _marker("catalysts", ticker, status=page["catalysts"]["status"])
    events = page["catalysts"].get("events") or []
    if events:
        for item in events:
            st.write(f'**Earnings** · {item.get("date") or "Date unavailable"}')
    elif not page["catalysts"].get("items"):
        st.info("Not enough evidence")

    st.markdown("## About the Company")
    _marker("about-company", ticker, status=page["about"]["status"])
    profile = page["about"].get("profile") or {}
    st.write(f'{page["about"].get("company") or page["company"]} · {page["about"].get("industry") or page["about"].get("sector") or "Industry unavailable"}')
    details = [str(value) for value in (profile.get("exchange"), profile.get("country"), profile.get("ipo_date")) if value]
    st.caption(" · ".join(details) if details else "Additional governed company details are unavailable for this snapshot.")

    _marker("evidence-methodology", ticker)
    with st.expander("Evidence & Methodology", expanded=False):
        evidence = page["evidence"]
        st.markdown(f'**Evaluation snapshot:** `{evidence.get("evaluation_snapshot_id") or "Unavailable"}`  ')
        st.markdown(f'**Candidate:** `{evidence.get("candidate_digest") or "Unavailable"}`  ')
        st.markdown(f'**Publication:** `{evidence.get("publication_digest") or "Unavailable"}`  ')
        st.markdown(f'**Methodology:** `{evidence["methodology_version"]}`')
        st.caption("Contextual evidence is non-scoring and cannot change Action, Fair Value, Opportunity, or Confidence.")
    ask_cta(report)


__all__ = ["render_customer_research_v2"]
