"""Customer-facing ATLAS Research V2 renderer."""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Mapping
from datetime import datetime
import hashlib
import json
import math

import pandas as pd
import streamlit as st

from services.customer_research_view import Availability, build_customer_research_view


def _six_pillar_display_rows(pillars: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Create one immutable, ticker-bound source for both chart and table."""
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
    return tuple(rows)


def _six_pillar_frame(pillars: Mapping[str, Any]) -> pd.DataFrame:
    rows = _six_pillar_display_rows(pillars)
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


def _render_production_authority_marker(page: Mapping[str, Any]) -> bool:
    """Emit authority only from the final ticker-bound customer projection."""
    ticker = str(page.get("ticker") or "").strip().upper()
    identity = page.get("identity") if isinstance(page.get("identity"), Mapping) else {}
    authority = page.get("authority") if isinstance(page.get("authority"), Mapping) else {}
    evidence = page.get("evidence") if isinstance(page.get("evidence"), Mapping) else {}
    snapshot = str(identity.get("evaluation_snapshot") or "")
    candidate = str(identity.get("candidate_digest") or "")
    publication = str(identity.get("publication_digest") or "")
    source_sha = str(identity.get("source_sha") or "")
    if (
        not ticker
        or str(identity.get("ticker") or "").strip().upper() != ticker
        or not snapshot
        or snapshot != str(evidence.get("evaluation_snapshot_id") or "")
        or not candidate or candidate != str(evidence.get("candidate_digest") or "")
        or not publication or publication != str(evidence.get("publication_digest") or "")
        or not source_sha or source_sha != str(evidence.get("source_sha") or "")
    ):
        return False
    st.markdown(
        f'<span data-atlas-qa="research-production-authority" data-atlas-ticker="{escape(ticker)}" '
        f'data-atlas-action="{escape(str(authority.get("action") or ""))}" '
        f'data-atlas-fair-value="{escape(str(authority.get("fair_value") or ""))}" '
        f'data-atlas-opportunity="{escape(str(authority.get("opportunity") or ""))}" '
        f'data-atlas-confidence="{escape(str(authority.get("confidence") or ""))}" '
        f'data-atlas-evaluation-snapshot="{escape(snapshot)}" '
        f'data-atlas-candidate-digest="{escape(candidate)}" '
        f'data-atlas-publication-digest="{escape(publication)}" '
        f'data-atlas-source-sha="{escape(source_sha)}" '
        'aria-hidden="true" style="display:none">research-production-authority</span>',
        unsafe_allow_html=True,
    )
    return True


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


def _dark_line_chart(frame: pd.DataFrame, *, height: int, y_title: str, key: str) -> None:
    series = [str(column) for column in frame.columns]
    palette = ["#2dd4bf", "#60a5fa", "#f59e0b", "#a78bfa"]
    data = frame.reset_index().rename(columns={frame.index.name or "index": "Date"}).melt("Date", var_name="Series", value_name="Value")
    st.vega_lite_chart(data, use_container_width=True, theme=None, key=key, spec={
        "height": height,
        "mark": {"type": "line", "strokeWidth": 2.2},
        "encoding": {
            "x": {"field": "Date", "type": "temporal", "axis": {"title": "Date", "format": "%b %Y", "tickCount": 6, "labelOverlap": "greedy", "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}},
            "y": {"field": "Value", "type": "quantitative", "scale": {"zero": False, "nice": True}, "axis": {"title": y_title, "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}},
            "color": {"field": "Series", "type": "nominal", "scale": {"domain": series, "range": palette[:len(series)]}, "legend": {"title": None, "orient": "bottom", "direction": "horizontal", "columns": 2, "labelLimit": 180, "labelColor": "#cbd5e1", "titleColor": "#cbd5e1"}},
            "tooltip": [{"field": "Date", "type": "temporal", "format": "%b %d, %Y"}, {"field": "Series"}, {"field": "Value", "format": ",.2f"}],
        },
        "config": {"background": "#08111f", "view": {"stroke": "#243244"}, "axis": {"domainColor": "#334155", "tickColor": "#334155"}},
    })


def _friendly_time(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%b %-d, %Y · %-I:%M %p UTC")
    except (TypeError, ValueError):
        return "Date unavailable"


def _financial_value(value: Any, unit: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unavailable"
    if unit == "PERCENT":
        return f"{number:,.1f}%"
    if unit == "USD_PER_SHARE":
        return f"${number:,.2f}"
    if unit == "USD":
        if abs(number) >= 1_000_000_000_000:
            return f"${number / 1_000_000_000_000:,.2f}T"
        if abs(number) >= 1_000_000_000:
            return f"${number / 1_000_000_000:,.2f}B"
        if abs(number) >= 1_000_000:
            return f"${number / 1_000_000:,.2f}M"
        return f"${number:,.2f}"
    return f"{number:,.2f}"


def _range_rows(frame: pd.DataFrame, selected: str) -> pd.DataFrame:
    """Return a display-only date window without altering retained values."""
    if frame.empty or selected == "1Y":
        return frame
    months = {"1M": 1, "3M": 3, "6M": 6}.get(selected)
    if months is None:
        return frame
    cutoff = frame.index.max() - pd.DateOffset(months=months)
    return frame.loc[frame.index >= cutoff]


def render_customer_research_first_screen(report: Mapping[str, Any]) -> dict[str, Any]:
    """Render the settled ticker's customer-safe summary before search controls."""
    customer_view = build_customer_research_view(report)
    page = customer_view.as_mapping()
    ticker = str(page.get("ticker") or "UNKNOWN")
    if page.get("status") != "AVAILABLE":
        _marker("terminal", ticker, state="RATING_NOT_PUBLISHED")
        company = str(page.get("company") or ticker)
        identity = ticker if company.upper() == ticker else f"{ticker} · {company}"
        disposition = str(page.get("withheld_disposition") or "RATING_NOT_PUBLISHED")
        reason = (
            "ATLAS does not currently publish an investment rating for this security under its certified model."
            if disposition != "HUMAN_REVIEW_QUEUED"
            else "ATLAS has not published a rating while an authorized review is pending."
        )
        st.markdown(
            '<section data-atlas-qa="research-withheld-message" '
            f'data-atlas-ticker="{escape(ticker)}" role="status" '
            'style="padding:.9rem 1rem;border:1px solid rgba(251,191,36,.35);'
            'border-radius:12px;background:rgba(120,53,15,.18);color:#f8fafc;'
            'font-size:1rem;line-height:1.5;margin:.5rem 0 1rem">'
            f'<strong>{escape(identity)}</strong><br>'
            f'A certified ATLAS rating is not available for {escape(ticker)}.<br>'
            f'{escape(reason)}'
            '</section>',
            unsafe_allow_html=True,
        )
        return page
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
    if customer_view.availability.get("certified_close") == Availability.CERTIFIED_DATED.value:
        st.warning("This Research uses a dated certified close. Review the displayed as-of date before acting.")
    if h["action"] not in {"BUY NOW", "BUILD A POSITION"}:
        st.caption("Not currently actionable — continue monitoring the certified evidence.")
    return page


def render_customer_research_v2(report: Mapping[str, Any], *, ask_cta: Callable[[Mapping[str, Any]], None]) -> bool:
    customer_view = build_customer_research_view(report)
    page = customer_view.as_mapping()
    ticker = str(page.get("ticker") or "UNKNOWN")
    first_screen_rendered = st.session_state.pop("_atlas_research_first_screen_rendered", "") == ticker
    if page.get("status") != "AVAILABLE":
        if not first_screen_rendered:
            render_customer_research_first_screen(report)
        return True
    if not first_screen_rendered:
        page = render_customer_research_first_screen(report)
    if not _render_production_authority_marker(page):
        st.error("Certified Research identity could not be reconciled for this ticker.")
        return False
    header = page["header"]
    ask_cta(report)

    summary = page["summary"]
    _marker("section", ticker, section_name="Decision")
    st.markdown("## ATLAS Investment Summary")
    st.write(summary["verdict"])
    st.caption(
        "ATLAS Fair Value is an evidence-based estimate under the certified ATLAS method, "
        "not a guaranteed future price. Opportunity measures relative attractiveness inside "
        "that method. Confidence measures the completeness and consistency of the evidence, "
        "not the chance that the stock will rise."
    )
    if summary["why_rating"]:
        st.markdown("**Why the stock may be attractive**")
        _list(summary["why_rating"])
    if summary["risks"]:
        st.markdown("**Biggest verified risks**")
        _list(summary["risks"])
    _marker("since-signal", ticker, status=page["signal"]["status"])
    signal = page["signal"]
    if signal["status"] == "AVAILABLE":
        st.markdown("### Since ATLAS Flagged It")
        s = st.columns(5)
        s[0].metric("Action at issuance", signal["action"])
        s[1].metric("Reference price", _money(signal["reference_price"]))
        s[2].metric("Return since signal", _pct(signal["stock_return"], signed=True))
        s[3].metric("SPY same period", _pct(signal["spy_return"], signed=True))
        s[4].metric("Excess vs SPY", _pct(signal["excess_return"], signed=True))
        st.caption(f'Signal date: {signal.get("signal_date") or "Unavailable"}')

    _marker("section", ticker, section_name="Technical & Trade State")
    st.markdown("## Technical & Trade State")
    st.markdown("### Price history")
    _marker("chart-root", ticker, status=page["chart"]["status"])
    chart = page["chart"]
    ownership = chart.get("ownership") or {}
    owner_values = {
        str(ownership.get(name) or "").strip().upper()
        for name in (
            "requested_ticker", "source_report_ticker", "certified_authority_ticker",
            "chart_payload_ticker", "displayed_ticker",
        )
    }
    ownership_valid = owner_values == {ticker}
    _marker("chart-ownership", ticker, status="PASS" if ownership_valid else "FAIL", **ownership)
    if not ownership_valid:
        st.error("Research chart ownership could not be certified for this ticker.")
        return
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
            # The chart is rendered after the first-screen helper has returned,
            # so its local ``h`` binding is intentionally unavailable here.
            # Use the already-certified projection carried by this page.
            price_frame = stock_rows.copy()
            _dark_line_chart(price_frame, height=300, y_title="Price (USD/share)", key=f"research-price-chart-{ticker}")
            fair_value = header.get("fair_value")
            if fair_value is not None:
                st.caption(
                    f"ATLAS Fair Value: {_money(fair_value)} per share, compared with the last certified "
                    f"close of {_money(header.get('price'))}. It is shown separately so it does not compress "
                    "the historical price chart."
                )
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
                        st.markdown("### Stock performance compared with SPY")
                        _dark_line_chart(normalized, height=320, y_title="Normalized performance (start = 100)", key=f"research-spy-chart-{ticker}")
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
                _dark_line_chart(indicator_frame, height=260, y_title="Certified indicator value", key=f"research-technical-chart-{ticker}")
            else:
                _marker("technical-indicators-chart", ticker, status="UNAVAILABLE")
        else:
            st.info("Price history is unavailable under the governed display contract.")

    _marker("summary", ticker, classification="CERTIFIED_ATLAS")
    weakest = summary.get("weakest_pillar") or {}
    if weakest:
        st.caption(
            f'Weakest certified pillar: {weakest["name"]} · {float(weakest["score"]):.1f} out of 100. '
            'A lower pillar score identifies an area where the certified investment case is less supportive.'
        )
    condition_labels = {"strengthen": "Strengthens the case", "weaken": "Weakens the case", "invalidate": "Invalidates the case"}
    for key, label in condition_labels.items():
        items = list((summary.get("watch_conditions") or {}).get(key) or ())
        if items:
            st.markdown(f"**{label}**")
            _list(items)

    pillars = page.get("six_pillars") or {}
    valid_count = len(pillars.get("items") or ())
    st.markdown(f"### Certified pillar coverage — {valid_count} of 6")
    pillar_identity = [
        {
            "pillar": item.get("pillar"), "score": item.get("certified_score"),
            "weight": item.get("weight"), "snapshot": item.get("snapshot_identity"),
        }
        for item in pillars.get("items") or ()
    ]
    pillar_digest = hashlib.sha256(
        json.dumps(pillar_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _marker(
        "six-pillar-profile", ticker, status=pillars.get("status") or "UNAVAILABLE",
        count=valid_count, digest=pillar_digest,
    )
    if pillars.get("status") in {"AVAILABLE", "PARTIAL"}:
        display_rows = _six_pillar_display_rows(pillars)
        frame = pd.DataFrame(display_rows).set_index("Pillar") if display_rows else pd.DataFrame()
        if frame.empty:
            st.info(pillars.get("message") or "Certified six-pillar evidence is unavailable.")
        else:
            chart_rows = []
            table_markers = []
            for row in display_rows:
                label = escape(str(row["Pillar"]))
                slug = str(row["Pillar"]).lower().replace(" ", "-")
                score = float(row["Certified score"])
                weight = row["Governed weight (%)"]
                weight_attr = "" if weight is None else f"{float(weight):.10g}"
                chart_rows.append(
                    f'<div class="atlas-pillar-row" data-atlas-qa="research-v2-pillar-chart-row" '
                    f'data-atlas-ticker="{escape(ticker)}" data-atlas-pillar="{escape(slug)}" '
                    f'data-atlas-score="{score:.10g}" data-atlas-weight="{weight_attr}">'
                    f'<div class="atlas-pillar-label"><span>{label}</span><strong>{score:.1f}</strong></div>'
                    f'<div class="atlas-pillar-track"><span style="width:{score:.6f}%"></span></div></div>'
                )
                table_markers.append(
                    f'<span data-atlas-qa="research-v2-pillar-table-row" data-atlas-ticker="{escape(ticker)}" '
                    f'data-atlas-pillar="{escape(slug)}" data-atlas-score="{score:.10g}" '
                    f'data-atlas-weight="{weight_attr}" aria-hidden="true" style="display:none"></span>'
                )
            st.markdown(
                '<style>.atlas-pillar-chart{padding:.8rem;border:1px solid #243244;border-radius:12px;'
                'background:#08111f}.atlas-pillar-row{margin:.55rem 0}.atlas-pillar-label{display:flex;'
                'justify-content:space-between;color:#cbd5e1;font-size:.82rem}.atlas-pillar-label strong{color:#f8fafc}'
                '.atlas-pillar-track{height:13px;margin-top:.25rem;border-radius:7px;background:#172337;overflow:hidden}'
                '.atlas-pillar-track span{display:block;height:100%;border-radius:7px;background:#2dd4bf}</style>'
                f'<div class="atlas-pillar-chart" data-atlas-ticker="{escape(ticker)}">'
                + "".join(chart_rows) + "</div>" + "".join(table_markers),
                unsafe_allow_html=True,
            )
            st.dataframe(
                frame[["Certified score"]].style.format("{:.1f}"),
                use_container_width=True,
                key=f"research-pillar-scores-{ticker}",
            )
            weight_rows = frame.dropna(subset=["Governed weight (%)"])[["Governed weight (%)"]]
            if pillars.get("weights_status") == "AVAILABLE":
                st.dataframe(
                    weight_rows.style.format("{:.1f}%"),
                    use_container_width=True,
                    key=f"research-pillar-weights-{ticker}",
                )
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
        b[0].metric("Current Price", _money(header["price"]))
        b[1].metric("Wall St. Low", _money(wall.get("target_low")))
        b[2].metric("Wall St. Average", _money(wall.get("target_average")))
        b[3].metric("Wall St. High", _money(wall.get("target_high")))
        b[4].metric("ATLAS Fair Value", _money(header["fair_value"]))
        st.caption(f'{wall.get("analyst_count") or "Unavailable"} analysts · as of {_friendly_time(wall.get("as_of"))} · contextual and non-scoring')

    valuation = page.get("valuation_chart") or {}
    _marker("valuation-comparison-chart", ticker, status=valuation.get("status") or "UNAVAILABLE", unit=valuation.get("unit") or "")
    if valuation.get("status") == "AVAILABLE":
        valuation_frame = pd.DataFrame([{"Reference": key, "USD/share": value} for key, value in valuation["values"].items()])
        st.vega_lite_chart(valuation_frame, use_container_width=True, theme=None, key=f"research-valuation-chart-{ticker}", spec={
            "height": 240, "mark": {"type": "bar", "cornerRadiusEnd": 5},
            "encoding": {"x": {"field": "Reference", "type": "nominal", "axis": {"labelAngle": 0, "labelColor": "#cbd5e1", "title": None}}, "y": {"field": "USD/share", "type": "quantitative", "axis": {"title": "USD per share", "format": "$,.0f", "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}}, "color": {"field": "Reference", "type": "nominal", "scale": {"range": ["#60a5fa", "#2dd4bf", "#f59e0b"]}, "legend": None}, "tooltip": [{"field": "Reference"}, {"field": "USD/share", "format": "$,.2f"}]},
            "config": {"background": "#08111f", "view": {"stroke": "#243244"}},
        })
        st.caption(f'Valuation comparison as of {_friendly_time(valuation.get("as_of"))}. Wall Street context is non-scoring.')
    else:
        st.info(valuation.get("message") or "Comparable certified valuation points are unavailable.")

    _marker("risks", ticker)
    _marker("view-change-conditions", ticker)
    conditions_present = any((summary.get("watch_conditions") or {}).get(key) for key in ("strengthen", "weaken", "invalidate"))
    _marker("section", ticker, section_name="Risk & Evidence")
    if summary["risks"] or conditions_present:
        st.markdown("## Risk & Evidence")
    if summary["risks"]:
        st.markdown("### Risks in plain language")
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

    financial_snapshot = page.get("financial_snapshot") or {}
    _marker("financial-snapshot", ticker, status=financial_snapshot.get("status") or "UNAVAILABLE",
            count=len(financial_snapshot.get("items") or ()))
    if financial_snapshot.get("status") == "AVAILABLE":
        st.markdown("### Certified financial evidence")
        items = list(financial_snapshot.get("items") or ())
        for start in range(0, len(items), 4):
            group = items[start:start + 4]
            cols = st.columns(len(group))
            for col, item in zip(cols, group):
                period = _friendly_time(item.get("period") or item.get("as_of"))
                analyst_note = f' · {item["analyst_count"]} analysts' if item.get("analyst_count") else ""
                col.metric(
                    str(item.get("label") or item.get("field") or "Financial evidence"),
                    _financial_value(item.get("value"), str(item.get("unit") or "")),
                    help=f'{period} · {item.get("provider") or "Certified source"}{analyst_note}',
                )
        with st.expander("Financial evidence periods and provenance", expanded=False):
            evidence_rows = [{
                "Metric": item.get("label"),
                "Value": _financial_value(item.get("value"), str(item.get("unit") or "")),
                "Fiscal period / as of": _friendly_time(item.get("period") or item.get("as_of")),
                "Source": item.get("provider") or "Certified source",
                "Evidence ID": item.get("evidence_id"),
            } for item in items]
            st.dataframe(pd.DataFrame(evidence_rows), hide_index=True, use_container_width=True)
        st.markdown("### What this means")
        st.caption(
            "Revenue shows how much the company sells. Operating margin shows how much operating profit "
            "it keeps from each $100 of revenue. Free cash flow is cash left after operating costs and major "
            "investments; it can support growth, debt repayment, or shareholder returns. Debt reduces financial "
            "flexibility when it is large relative to cash and earnings. A single period describes the current "
            "snapshot but does not prove that the business is improving or weakening."
        )
    else:
        st.info(financial_snapshot.get("message") or "Certified financial evidence is unavailable for this snapshot.")

    financial_trend = page.get("financial_trend") or {}
    _marker("financial-trend-chart", ticker, status=financial_trend.get("status") or "UNAVAILABLE")
    if financial_trend.get("status") == "AVAILABLE":
        st.markdown("### Earnings and financial trends")
        all_series = financial_trend["series"]
        units = financial_trend.get("units") or {}
        for unit, title in (("USD", "Reported financial value (USD)"), ("USD_PER_SHARE", "Reported value (USD/share)"), ("PERCENT", "Reported margin (%)")):
            selected = {name: values for name, values in all_series.items() if units.get(name) == unit}
            if selected:
                trend_frame = pd.DataFrame(selected, index=financial_trend["periods"])
                _dark_line_chart(trend_frame, height=280, y_title=title,
                                 key=f"research-financial-trend-{ticker}-{unit.lower()}")
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
    return True


__all__ = ["render_customer_research_first_screen", "render_customer_research_v2"]
