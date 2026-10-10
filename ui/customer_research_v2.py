"""Customer-facing ATLAS Research V2 renderer."""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Mapping
from datetime import datetime
import math

import pandas as pd
import streamlit as st

from services.customer_research_v2 import build_customer_research_v2


def _six_pillar_frame(pillars: Mapping[str, Any]) -> pd.DataFrame:
    """Build a chart frame from the validated customer projection only."""
    rows = []
    for item in pillars.get("items") or ():
        score = item.get("certified_score")
        weight = item.get("weight")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
            continue
        if not 0.0 <= float(score) <= 100.0:
            continue
        if weight is not None and (
            isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(float(weight))
        ):
            weight = None
        weight_display = None
        if weight is not None:
            weight_display = float(weight) * 100.0 if item.get("weight_unit") == "FRACTION" else float(weight)
        rows.append(
            {
                "Pillar": str(item["pillar"]).replace("_", " ").title(),
                "Certified score": float(score),
                "Governed weight (%)": weight_display,
            }
        )
    return pd.DataFrame(rows).set_index("Pillar") if rows else pd.DataFrame(columns=["Certified score", "Governed weight (%)"])


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
    return f"Source: {str(source).replace('_', ' ').title()} · Evidence captured {_friendly_time(as_of)}"


def _dark_line_chart(frame: pd.DataFrame, *, height: int, y_title: str) -> None:
    data = frame.reset_index().rename(columns={frame.index.name or "index": "Date"}).melt("Date", var_name="Series", value_name="Value")
    st.vega_lite_chart(data, use_container_width=True, theme=None, spec={
        "height": height,
        "mark": {"type": "line", "strokeWidth": 2.2},
        "encoding": {
            "x": {"field": "Date", "type": "temporal", "axis": {"title": "Date", "format": "%b %Y", "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}},
            "y": {"field": "Value", "type": "quantitative", "axis": {"title": y_title, "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}},
            "color": {"field": "Series", "type": "nominal", "scale": {"range": ["#2dd4bf", "#60a5fa", "#f59e0b", "#a78bfa"]}, "legend": {"labelColor": "#cbd5e1", "titleColor": "#cbd5e1"}},
            "tooltip": [{"field": "Date", "type": "temporal", "format": "%b %d, %Y"}, {"field": "Series"}, {"field": "Value", "format": ",.2f"}],
        },
        "config": {"background": "#08111f", "view": {"stroke": "#243244"}, "axis": {"domainColor": "#334155", "tickColor": "#334155"}},
    })


def _friendly_time(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%b %-d, %Y · %-I:%M %p UTC")
    except (TypeError, ValueError):
        return "Date unavailable"


def _range_rows(frame: pd.DataFrame, selected: str) -> pd.DataFrame:
    """Return a display-only date window without altering retained values."""
    if frame.empty or selected == "1Y":
        return frame
    months = {"1M": 1, "3M": 3, "6M": 6}.get(selected)
    if months is None:
        return frame
    cutoff = frame.index.max() - pd.DateOffset(months=months)
    return frame.loc[frame.index >= cutoff]


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
    .atlas-r2-head{padding:.9rem 1rem;border:1px solid rgba(45,212,191,.25);border-radius:16px;background:linear-gradient(145deg,rgba(15,23,42,.96),rgba(18,39,51,.88));margin-bottom:.55rem}.atlas-r2-kicker{color:#61d8c3;font-size:.68rem;font-weight:800;letter-spacing:.13em}.atlas-r2-title{display:flex;align-items:baseline;justify-content:space-between;gap:.8rem;flex-wrap:wrap}.atlas-r2-head h1{margin:.18rem 0;font-size:1.55rem}.atlas-r2-action{color:#5eead4;font-size:.82rem;font-weight:850;letter-spacing:.07em}.atlas-r2-meta{color:#94a3b8;font-size:.76rem}.atlas-r2-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.55rem;margin:.65rem 0}.atlas-r2-metric{padding:.7rem .75rem;border:1px solid rgba(148,163,184,.18);border-radius:12px;background:#0f192b;min-width:0}.atlas-r2-metric small{display:block;color:#8ea1bb;font-size:.62rem;letter-spacing:.08em;text-transform:uppercase}.atlas-r2-metric strong{display:block;color:#f8fafc;font-size:1.15rem;line-height:1.15;margin-top:.25rem;overflow-wrap:anywhere}.atlas-r2-grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.atlas-r2-panel{padding:.9rem;border:1px solid rgba(148,163,184,.16);border-radius:14px;background:rgba(15,23,42,.55)}
    @media(max-width:700px){.atlas-r2-head h1{font-size:1.25rem}.atlas-r2-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-r2-metric strong{font-size:1rem}.atlas-r2-grid{grid-template-columns:1fr}.atlas-r2-panel{padding:.75rem}}
    </style>""", unsafe_allow_html=True)
    st.markdown(
        f'<section class="atlas-r2-head"><div class="atlas-r2-kicker">CERTIFIED ATLAS RESEARCH</div>'
        f'<div class="atlas-r2-title"><h1>{escape(ticker)} · {escape(str(page["company"]))}</h1><span class="atlas-r2-action">{escape(h["action"])}</span></div>'
        f'<div class="atlas-r2-meta">{escape(str(page.get("sector") or "Sector unavailable"))} · Last certified close {escape(str(h.get("evidence_as_of") or "Date unavailable"))}</div>'
        f'<div class="atlas-r2-metrics">'
        f'<div class="atlas-r2-metric"><small>Last Certified Close</small><strong>{escape(_money(h["price"]))}</strong></div>'
        f'<div class="atlas-r2-metric"><small>ATLAS Fair Value</small><strong>{escape(_money(h["fair_value"]))}</strong></div>'
        f'<div class="atlas-r2-metric"><small>Fair Value Gap</small><strong>{escape(_pct(h["fair_value_gap_pct"], signed=True))}</strong></div>'
        f'<div class="atlas-r2-metric"><small>Opportunity</small><strong>{float(h["opportunity"]):.2f}</strong></div>'
        f'<div class="atlas-r2-metric"><small>Evidence Confidence</small><strong>{escape(str(h.get("confidence_band") or "Unavailable"))} · {escape(confidence_score)}</strong></div>'
        f'</div></section>', unsafe_allow_html=True,
    )
    _marker(
        "stock-header", ticker,
        action=h["action"], fair_value=h["fair_value"],
        opportunity=h["opportunity"], confidence=h["confidence"],
        snapshot=page["identity"].get("evaluation_snapshot"),
    )
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
            selected_range = st.selectbox("Price range", ("1M", "3M", "6M", "1Y"), index=2, key=f"research-price-range-{ticker}")
            stock_rows = _range_rows(stock_rows, selected_range)
            fair_value = h.get("fair_value")
            price_frame = stock_rows.copy()
            if fair_value is not None:
                price_frame["ATLAS Fair Value — certified snapshot"] = float(fair_value)
            _dark_line_chart(price_frame, height=300, y_title="Price (USD/share)")
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
                        normalized = joined[[ticker, "SPY"]].divide(joined.iloc[0][[ticker, "SPY"]]).multiply(100.0)
                        _marker("spy-comparison-chart", ticker, status="AVAILABLE", unit="NORMALIZED_INDEX_100")
                        _dark_line_chart(normalized, height=320, y_title="Normalized performance (start = 100)")
                        st.caption(_provenance_caption(spy.get("provenance") or {}))
                    else:
                        _marker("spy-comparison-chart", ticker, status="UNAVAILABLE")
                        st.info("SPY comparison is unavailable because comparable completed-session dates do not overlap.")
                else:
                    _marker("spy-comparison-chart", ticker, status="UNAVAILABLE")
                    st.info("SPY comparison is unavailable because dated benchmark evidence is incomplete.")
            else:
                _marker("spy-comparison-chart", ticker, status=spy.get("status") or "UNAVAILABLE")
                st.caption("SPY comparison unavailable for this evidence bundle.")
            st.caption(_provenance_caption(chart.get("provenance") or {}))
            if chart.get("corporate_action_status") == "UNADJUSTED_CLOSE_NO_RETURN_CLAIM":
                st.caption("Historical closes are shown without an adjusted-return claim because corporate-action adjustment provenance is unavailable.")

            technical = chart.get("technical_indicators") or {}
            indicator_keys = [key for key in technical.get("keys") or () if key in rows]
            if technical.get("status") == "AVAILABLE" and indicator_keys:
                _marker("technical-indicators-chart", ticker, status="AVAILABLE", unit="USD_PER_SHARE_OR_INDEX")
                indicator_frame = rows.dropna(subset=[date_key]).set_index(date_key)[indicator_keys]
                _dark_line_chart(indicator_frame, height=260, y_title="Certified indicator value")
            else:
                _marker("technical-indicators-chart", ticker, status="UNAVAILABLE")
                st.info(technical.get("message") or "Certified technical-indicator history is unavailable for this snapshot.")
        else:
            st.info("Price history is unavailable under the governed display contract.")

    st.markdown("## AI Investment Brief")
    _marker("summary", ticker, classification="CERTIFIED_ATLAS")
    summary = page["summary"]
    st.markdown("**Verdict**")
    st.write(summary["verdict"])
    st.markdown("**Why this rating**")
    _list(summary["why_rating"] or ["The available certified evidence does not support additional explanatory claims."])
    if summary["risks"]:
        st.markdown("**Material risks**")
        _list(summary["risks"])
    if summary["watch_next"]:
        st.markdown("**What to watch**")
        _list(summary["watch_next"])

    pillars = page.get("six_pillars") or {}
    valid_count = len(pillars.get("items") or ())
    st.markdown(f"### Certified pillar coverage — {valid_count} of 6")
    _marker("six-pillar-profile", ticker, status=pillars.get("status") or "UNAVAILABLE")
    if pillars.get("status") in {"AVAILABLE", "PARTIAL"}:
        frame = _six_pillar_frame(pillars)
        if frame.empty:
            st.info(pillars.get("message") or "Certified six-pillar evidence is unavailable.")
        else:
            pillar_data = frame.reset_index()
            st.vega_lite_chart(pillar_data, use_container_width=True, theme=None, spec={
                "height": max(180, 42 * len(pillar_data)), "mark": {"type": "bar", "cornerRadiusEnd": 5, "color": "#2dd4bf"},
                "encoding": {"y": {"field": "Pillar", "type": "nominal", "sort": "-x", "axis": {"labelColor": "#cbd5e1", "title": None}}, "x": {"field": "Certified score", "type": "quantitative", "scale": {"domain": [0, 100]}, "axis": {"title": "Score", "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}}, "tooltip": [{"field": "Pillar"}, {"field": "Certified score", "format": ".1f"}]},
                "config": {"background": "#08111f", "view": {"stroke": "#243244"}},
            })
            weight_rows = frame.dropna(subset=["Governed weight (%)"])[["Governed weight (%)"]]
            if pillars.get("weights_status") == "AVAILABLE":
                st.dataframe(weight_rows.style.format("{:.1f}%"), use_container_width=True)
            else:
                st.caption("Governed pillar weights are unavailable in this snapshot; scores are shown without inferred weights.")
            if pillars.get("status") == "PARTIAL":
                st.caption(pillars.get("message") or "Some certified pillars are unavailable for customer display.")
    else:
        st.info(pillars.get("message") or "Certified six-pillar evidence is unavailable.")


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
        valuation_frame = pd.DataFrame([{"Reference": key, "USD/share": value} for key, value in valuation["values"].items()])
        st.vega_lite_chart(valuation_frame, use_container_width=True, theme=None, spec={
            "height": 240, "mark": {"type": "bar", "cornerRadiusEnd": 5},
            "encoding": {"x": {"field": "Reference", "type": "nominal", "axis": {"labelAngle": 0, "labelColor": "#cbd5e1", "title": None}}, "y": {"field": "USD/share", "type": "quantitative", "axis": {"title": "USD per share", "format": "$,.0f", "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}}, "color": {"field": "Reference", "type": "nominal", "scale": {"range": ["#60a5fa", "#2dd4bf", "#f59e0b"]}, "legend": None}, "tooltip": [{"field": "Reference"}, {"field": "USD/share", "format": "$,.2f"}]},
            "config": {"background": "#08111f", "view": {"stroke": "#243244"}},
        })
        st.caption(f'Valuation comparison as of {_friendly_time(valuation.get("as_of"))}. Wall Street context is non-scoring.')
    else:
        st.info(valuation.get("message") or "Comparable certified valuation points are unavailable.")

    _marker("section", ticker, section_name="Risk & Evidence")
    st.markdown("## Risk & Evidence")
    st.markdown("### Risks")
    _marker("risks", ticker)
    _marker("view-change-conditions", ticker)
    if summary["risks"]:
        _list(summary["risks"])

    _marker("what-changed", ticker, status=page["recent_changes"]["status"])
    if page["recent_changes"]["items"]:
        st.markdown("## What Changed Recently")
        for item in page["recent_changes"]["items"]:
            st.markdown(f'**{item.get("headline") or "Company update"}**  ')
            st.caption(f'{item.get("article_publisher") or "Source unavailable"} · {_friendly_time(item.get("article_timestamp"))}')

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
    _marker("financial-trend-chart", ticker, status=financial_trend.get("status") or "UNAVAILABLE")
    if financial_trend.get("status") == "AVAILABLE":
        st.markdown("### Earnings and financial trends")
        trend_frame = pd.DataFrame(financial_trend["series"], index=financial_trend["periods"])
        _dark_line_chart(trend_frame, height=280, y_title="Reported value")
        st.caption(_provenance_caption(financial_trend.get("provenance") or {}))

    _marker("section", ticker, section_name="Catalysts & Sentiment")
    _marker("catalysts", ticker, status=page["catalysts"]["status"])
    events = page["catalysts"].get("events") or []
    if events:
        st.markdown("## Catalysts & Sentiment")
        st.markdown("### Verified next events")
        for item in events:
            st.write(f'**Upcoming earnings** · {item.get("date") or "Date unavailable"}')

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
        unavailable = []
        if page["recent_changes"]["status"] != "AVAILABLE": unavailable.append("Recent changes")
        if financial_trend.get("status") != "AVAILABLE": unavailable.append("Financial trends")
        if page["catalysts"]["status"] != "AVAILABLE": unavailable.append("Catalysts")
        if chart.get("technical_indicators", {}).get("status") != "AVAILABLE": unavailable.append("Technical history")
        if unavailable:
            st.markdown("**Unavailable in this certified snapshot:** " + ", ".join(unavailable))
        st.caption("Contextual evidence is non-scoring and cannot change Action, Fair Value, Opportunity, or Confidence.")
    st.caption("Ask ATLAS remains grounded to this ticker and certified evaluation snapshot.")


__all__ = ["render_customer_research_v2"]
