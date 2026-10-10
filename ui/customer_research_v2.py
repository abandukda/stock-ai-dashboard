"""Customer-facing ATLAS Research V2 renderer."""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Mapping
from datetime import datetime

import pandas as pd
import streamlit as st

from services.customer_research_v2 import build_customer_research_v2


def _money(value: Any) -> str:
    return "Unavailable" if value is None else f"${float(value):,.2f}"


def _pct(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "Pending"
    return f"{float(value):+,.2f}%" if signed else f"{float(value):,.2f}%"


def _escape_markdown_currency(value: Any) -> str:
    """Preserve governed text while preventing Markdown dollar-math parsing."""
    return str(value).replace("$", "\\$")


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
    # Streamlit Markdown treats dollar-delimited text as math. Escape currency
    # so governed debt/cash values remain readable and numerically unchanged.
    st.markdown("\n".join(f"- {_escape_markdown_currency(item)}" for item in items))


def _dates(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().all():
        return pd.to_datetime(numeric, unit="s", utc=True, errors="coerce")
    return pd.to_datetime(values, utc=True, errors="coerce")


def _provenance_caption(provenance: Mapping[str, Any]) -> str:
    source = provenance.get("source") or provenance.get("provider") or "Governed source"
    as_of = provenance.get("capture_timestamp") or provenance.get("as_of") or "timestamp unavailable"
    return f"Source: {source} · Evidence captured {as_of}"


def _friendly_time(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%b %-d, %Y · %-I:%M %p UTC")
    except (TypeError, ValueError):
        return "Date unavailable"


def render_customer_research_v2(report: Mapping[str, Any], *, ask_cta: Callable[[Mapping[str, Any]], None]) -> None:
    page = build_customer_research_v2(report)
    ticker = str(page.get("ticker") or "UNKNOWN")
    if page.get("status") != "AVAILABLE":
        _marker("terminal", ticker, state="RATING_NOT_PUBLISHED")
        st.warning("ATLAS does not have a customer-publishable certified view for this security.")
        return
    h = page["header"]
    confidence_score = f'{float(h["confidence"]):.0f}/100'
    _marker("root", ticker, version=page["version"], authority="certified_customer_evaluation", section_count=5)
    st.markdown("""<style>
    .atlas-r2-head{padding:1rem 1.1rem;border:1px solid rgba(45,212,191,.25);border-radius:18px;background:linear-gradient(145deg,rgba(15,23,42,.96),rgba(18,39,51,.88));margin-bottom:.7rem}.atlas-r2-kicker{color:#61d8c3;font-size:.7rem;font-weight:800;letter-spacing:.13em}.atlas-r2-head h1{margin:.2rem 0;font-size:1.8rem}.atlas-r2-meta{color:#94a3b8;font-size:.78rem}.atlas-r2-grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.atlas-r2-panel{padding:.9rem;border:1px solid rgba(148,163,184,.16);border-radius:14px;background:rgba(15,23,42,.55)}
    @media(max-width:700px){.atlas-r2-head h1{font-size:1.35rem}.atlas-r2-grid{grid-template-columns:1fr}[data-testid="stMetric"]{padding-right:.25rem!important}.atlas-r2-panel{padding:.75rem}}
    </style>""", unsafe_allow_html=True)
    st.markdown(
        f'<section class="atlas-r2-head"><div class="atlas-r2-kicker">CERTIFIED ATLAS RESEARCH</div>'
        f'<h1>{escape(ticker)} · {escape(str(page["company"]))}</h1>'
        f'<div class="atlas-r2-meta">Evidence as of {escape(str(h.get("evidence_as_of") or "Date unavailable"))} · '
        f'Evidence confidence: {escape(str(h.get("confidence_band") or "Unavailable"))} '
        f'({escape(confidence_score)})</div></section>', unsafe_allow_html=True,
    )
    _marker(
        "stock-header", ticker,
        action=h["action"], fair_value=h["fair_value"],
        opportunity=h["opportunity"], confidence=h["confidence"],
        snapshot=page["identity"].get("evaluation_snapshot"),
    )
    cols = st.columns(6)
    cols[0].metric(h.get("price_label") or "Last Certified Close", _money(h["price"]))
    cols[1].metric("Action", h["action"])
    cols[2].metric("ATLAS Fair Value", _money(h["fair_value"]))
    cols[3].metric("Fair Value gap", _pct(h["fair_value_gap_pct"], signed=True))
    cols[4].metric("Opportunity", f'{float(h["opportunity"]):.2f}')
    cols[5].metric("Evidence confidence", f'{h["confidence_band"]} ({float(h["confidence"]):.0f}/100)')
    if h["fair_value_gap_pct"] is not None:
        direction = "above" if h["fair_value_gap_pct"] >= 0 else "below"
        st.caption(f'ATLAS Fair Value is {abs(float(h["fair_value_gap_pct"])):.2f}% {direction} the last certified close. This is not a guaranteed return.')
    if h["action"] not in {"BUY NOW", "BUILD A POSITION"}:
        st.caption("Not currently actionable — continue monitoring the certified evidence.")
    ask_cta(report)

    _marker("section", ticker, section_name="Decision")
    st.markdown("## Decision")
    st.markdown("### Since ATLAS Flagged It")
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

    _marker("section", ticker, section_name="Technical & Trade State")
    st.markdown("## Technical & Trade State")
    st.markdown("### Price history and SPY comparison")
    _marker("chart-root", ticker, status=page["chart"]["status"])
    chart = page["chart"]
    if chart["status"] != "AVAILABLE":
        st.info(chart["message"])
    else:
        rows = pd.DataFrame(chart["series"])
        date_key = next((key for key in ("date", "timestamp", "datetime") if key in rows), None)
        close_key = next((key for key in ("adjusted_close", "close", "price") if key in rows), None)
        if date_key and close_key:
            rows[date_key] = _dates(rows[date_key])
            stock_rows = rows.dropna(subset=[date_key, close_key]).set_index(date_key)[[close_key]].rename(columns={close_key: ticker})
            spy = chart.get("spy_comparison") or {}
            spy_rows = pd.DataFrame(spy.get("series") or [])
            if spy.get("status") == "AVAILABLE" and not spy_rows.empty:
                spy_date = next((key for key in ("date", "timestamp", "datetime") if key in spy_rows), None)
                spy_close = next((key for key in ("adjusted_close", "close", "price") if key in spy_rows), None)
                if spy_date and spy_close:
                    spy_rows[spy_date] = _dates(spy_rows[spy_date])
                    spy_rows = spy_rows.dropna(subset=[spy_date, spy_close]).set_index(spy_date)[[spy_close]].rename(columns={spy_close: "SPY"})
                    joined = stock_rows.join(spy_rows, how="inner").dropna()
                    if not joined.empty and float(joined.iloc[0][ticker]) and float(joined.iloc[0]["SPY"]):
                        normalized = joined.divide(joined.iloc[0]).multiply(100.0)
                        _marker("spy-comparison-chart", ticker, status="AVAILABLE", unit="NORMALIZED_INDEX_100")
                        st.line_chart(normalized, height=320, y_label="Normalized performance (start = 100)", x_label="Date")
                        st.caption(_provenance_caption(spy.get("provenance") or {}))
                    else:
                        _marker("spy-comparison-chart", ticker, status="UNAVAILABLE")
                        st.info("SPY comparison is unavailable because comparable completed-session dates do not overlap.")
                else:
                    _marker("spy-comparison-chart", ticker, status="UNAVAILABLE")
                    st.info("SPY comparison is unavailable because dated benchmark evidence is incomplete.")
            else:
                _marker("spy-comparison-chart", ticker, status=spy.get("status") or "UNAVAILABLE")
                st.line_chart(stock_rows, height=300, y_label="Price (USD/share)", x_label="Date")
                st.caption("SPY comparison unavailable for this evidence bundle.")
            st.caption(_provenance_caption(chart.get("provenance") or {}))

            technical = chart.get("technical_indicators") or {}
            indicator_keys = [key for key in technical.get("keys") or () if key in rows]
            if technical.get("status") == "AVAILABLE" and indicator_keys:
                _marker("technical-indicators-chart", ticker, status="AVAILABLE", unit="USD_PER_SHARE_OR_INDEX")
                indicator_frame = rows.dropna(subset=[date_key]).set_index(date_key)[indicator_keys]
                st.line_chart(indicator_frame, height=260, y_label="Certified indicator value", x_label="Date")
            else:
                _marker("technical-indicators-chart", ticker, status="UNAVAILABLE")
                st.info(technical.get("message") or "Certified technical-indicator history is unavailable for this snapshot.")
        else:
            st.info("Price history is unavailable under the governed display contract.")

    st.markdown("## AI Investment Brief")
    _marker("summary", ticker, classification="CERTIFIED_ATLAS")
    summary = page["summary"]
    st.markdown("**Bottom line**")
    st.write(summary["bottom_line"])
    st.markdown("**Why this rating**")
    _list(summary["why_rating"])
    st.markdown("**What's strong**")
    _list(summary["strengths"])
    st.markdown("**What could go wrong**")
    _list(summary["risks"])
    st.markdown("**What to watch**")
    _list(summary["watch_next"])

    _marker("section", ticker, section_name="Fundamentals & Valuation")
    st.markdown("## Fundamentals & Valuation")
    st.markdown("### ATLAS vs Wall Street")
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

    valuation = page.get("valuation_chart") or {}
    _marker("valuation-comparison-chart", ticker, status=valuation.get("status") or "UNAVAILABLE", unit=valuation.get("unit") or "")
    if valuation.get("status") == "AVAILABLE":
        valuation_frame = pd.DataFrame.from_dict(valuation["values"], orient="index", columns=["Value ($/share)"])
        st.bar_chart(valuation_frame, height=260, y_label="USD per share", x_label="Valuation reference")
        st.caption(f'Valuation comparison as of {valuation.get("as_of") or "Unavailable"}. Wall Street context is non-scoring.')
    else:
        st.info(valuation.get("message") or "Comparable certified valuation points are unavailable.")

    _marker("section", ticker, section_name="Risk & Evidence")
    st.markdown("## Risk & Evidence")
    st.markdown("### Risks / What Would Change the View")
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
            st.caption(f'{item.get("article_publisher") or "Source unavailable"} · {_friendly_time(item.get("article_timestamp"))}')
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
            ("TTM P/E", fundamentals.get("pe_ttm"), "×"),
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

    financial_trend = page.get("financial_trend") or {}
    st.markdown("### Earnings and financial trends")
    _marker("financial-trend-chart", ticker, status=financial_trend.get("status") or "UNAVAILABLE")
    if financial_trend.get("status") == "AVAILABLE":
        trend_frame = pd.DataFrame(financial_trend["series"], index=financial_trend["periods"])
        st.line_chart(trend_frame, height=280, x_label="Fiscal period", y_label="Reported value")
        st.caption(_provenance_caption(financial_trend.get("provenance") or {}))
    else:
        st.info(financial_trend.get("message") or "Certified multi-period earnings and financial history is unavailable for this snapshot.")

    _marker("section", ticker, section_name="Catalysts & Sentiment")
    st.markdown("## Catalysts & Sentiment")
    st.markdown("### Catalysts / Next Events")
    _marker("catalysts", ticker, status=page["catalysts"]["status"])
    events = page["catalysts"].get("events") or []
    if events:
        for item in events:
            st.write(f'**Upcoming earnings** · {item.get("date") or "Date unavailable"}')
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
    st.caption("Ask ATLAS remains grounded to this ticker and certified evaluation snapshot.")


__all__ = ["render_customer_research_v2"]
