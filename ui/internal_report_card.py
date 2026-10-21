"""Admin-only read-only internal prospective Report Card UI."""
from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from services.report_card_dashboard import build_internal_report_card
from ui.report_card_overview import OVERVIEW_CSS, overview_html, render_signal_directory, horizon_coverage_html


REPORT_CARD_VIEW_OVERVIEW = "OVERVIEW"
REPORT_CARD_VIEW_DETAIL = "DETAIL"
REPORT_CARD_VIEW_KEY = "report_card_view_mode"
REPORT_CARD_SELECTED_SIGNAL_KEY = "report_card_selected_signal_id"
REPORT_CARD_LAST_TRANSITION_KEY = "report_card_last_transition"


def normalize_report_card_view_state(
    session_state: MutableMapping[str, Any], valid_signal_ids: Sequence[str]
) -> tuple[str, str | None]:
    """Normalize Report Card view ownership without inventing a detail target."""
    valid_ids = {str(item) for item in valid_signal_ids if item}
    mode = str(session_state.get(REPORT_CARD_VIEW_KEY) or "").upper()
    selected_id = session_state.get(REPORT_CARD_SELECTED_SIGNAL_KEY)
    selected_id = str(selected_id) if selected_id else None

    if mode == REPORT_CARD_VIEW_DETAIL and selected_id in valid_ids:
        session_state[REPORT_CARD_LAST_TRANSITION_KEY] = f"DETAIL_RENDERED:{selected_id}"
        return REPORT_CARD_VIEW_DETAIL, selected_id

    session_state[REPORT_CARD_VIEW_KEY] = REPORT_CARD_VIEW_OVERVIEW
    session_state.pop(REPORT_CARD_SELECTED_SIGNAL_KEY, None)
    session_state.setdefault(REPORT_CARD_LAST_TRANSITION_KEY, "OVERVIEW_ENTRY")
    return REPORT_CARD_VIEW_OVERVIEW, None


def open_report_card_overview(session_state: MutableMapping[str, Any]) -> None:
    session_state[REPORT_CARD_VIEW_KEY] = REPORT_CARD_VIEW_OVERVIEW
    session_state.pop(REPORT_CARD_SELECTED_SIGNAL_KEY, None)
    session_state[REPORT_CARD_LAST_TRANSITION_KEY] = "OVERVIEW_ENTRY"


def back_to_report_card_overview(session_state: MutableMapping[str, Any]) -> None:
    session_state[REPORT_CARD_VIEW_KEY] = REPORT_CARD_VIEW_OVERVIEW
    session_state.pop(REPORT_CARD_SELECTED_SIGNAL_KEY, None)
    session_state[REPORT_CARD_LAST_TRANSITION_KEY] = "BACK_TO_OVERVIEW"


def open_report_card_detail(session_state: MutableMapping[str, Any], signal_id: str) -> None:
    exact_id = str(signal_id or "").strip()
    if not exact_id:
        open_report_card_overview(session_state)
        return
    session_state[REPORT_CARD_SELECTED_SIGNAL_KEY] = exact_id
    session_state[REPORT_CARD_VIEW_KEY] = REPORT_CARD_VIEW_DETAIL
    session_state[REPORT_CARD_LAST_TRANSITION_KEY] = f"DETAIL_REQUESTED:{exact_id}"


def _percent(value: Any) -> str:
    return "Pending" if value is None else f"{float(value) * 100:.2f}%"


def _money(value: Any) -> str:
    return "Unavailable" if value is None else f"${float(value):,.2f}"


def _score(value: Any) -> str:
    return "Unavailable" if value is None else f"{float(value):.2f}"


def _render_signal_detail(detail: Mapping[str, Any]) -> None:
    original = detail["original_signal"]
    current = detail["current_market_state"]
    profile = detail["company_profile"]
    ticker = html.escape(str(detail.get("ticker") or ""))
    company = html.escape(str(detail.get("company_name") or ticker))
    digest_sections = {str(item.get("title") or ""): item for item in detail.get("digest") or ()}
    contextual_available = any(item.get("status") == "AVAILABLE" for item in digest_sections.values())
    earnings_status = str((digest_sections.get("Earnings and management") or {}).get("status") or "UNAVAILABLE")
    news_status = "AVAILABLE" if contextual_available else "UNAVAILABLE"
    profile_status = "AVAILABLE" if profile.get("source") not in (None, "", "UNAVAILABLE") else "UNAVAILABLE"
    performance_status = "AVAILABLE" if any(item.get("status") == "AVAILABLE" for item in detail.get("performance") or ()) else "PENDING"
    st.markdown("""<style>
    .atlas-signal-detail{display:grid;gap:.8rem}.atlas-signal-detail-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;padding:1rem 1.1rem;border:1px solid rgba(94,234,212,.22);border-radius:16px;background:linear-gradient(145deg,rgba(15,23,42,.94),rgba(20,35,50,.88))}
    .atlas-signal-detail-head small,.atlas-detail-label{color:#77d7c4;letter-spacing:.1em;font-size:.68rem;font-weight:700}.atlas-signal-detail-head h2{margin:.18rem 0;font-size:1.45rem}.atlas-signal-detail-head p{margin:0;color:#9eabba;font-size:.8rem}.atlas-live-state{text-align:right}.atlas-live-state b{display:block;color:#e7edf5}.atlas-live-state span{font-size:.72rem;color:#8c9bad}
    .atlas-signal-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.45rem}.atlas-signal-metrics article{padding:.72rem;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:rgba(15,23,42,.7)}.atlas-signal-metrics small{display:block;color:#8998aa;font-size:.7rem}.atlas-signal-metrics b{display:block;margin-top:.18rem;color:#edf3f8;font-size:.95rem}
    .atlas-context-flag{display:inline-flex;padding:.2rem .42rem;border-radius:999px;background:rgba(148,163,184,.1);color:#91a1b3;font-size:.62rem;letter-spacing:.06em}.atlas-profile-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem}.atlas-profile-grid div{padding:.6rem;border-radius:10px;background:rgba(30,41,59,.45)}.atlas-profile-grid small,.atlas-profile-grid b{display:block}.atlas-profile-grid small{color:#8e9bad;font-size:.68rem}.atlas-profile-grid b{margin-top:.18rem;font-size:.86rem}
    @media(max-width:760px){.atlas-signal-detail-head{display:grid}.atlas-live-state{text-align:left}.atlas-signal-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-profile-grid{grid-template-columns:1fr}.atlas-signal-detail-head h2{font-size:1.25rem}}
    </style>""", unsafe_allow_html=True)
    st.markdown(
        f'<div class="atlas-signal-detail" data-atlas-qa="report-card-signal-detail" '
        f'data-atlas-report-card-view="{REPORT_CARD_VIEW_DETAIL}" '
        f'data-atlas-signal-id="{html.escape(str(detail.get("signal_id") or ""))}" '
        f'data-atlas-ticker="{ticker}" data-atlas-snapshot="{html.escape(str(original.get("evaluation_snapshot_id") or ""))}" '
        f'data-atlas-action="{html.escape(str(original.get("action") or ""))}" '
        f'data-atlas-fair-value="{html.escape(str(original.get("atlas_fair_value") or ""))}" '
        f'data-atlas-opportunity="{html.escape(str(original.get("opportunity") or ""))}" '
        f'data-atlas-confidence="{html.escape(str(original.get("confidence") or ""))}" '
        f'data-atlas-candidate-digest="{html.escape(str(original.get("candidate_digest") or ""))}" '
        f'data-atlas-publication-digest="{html.escape(str(original.get("publication_digest") or ""))}" '
        f'data-atlas-contextual-evidence="{news_status}" data-atlas-earnings-evidence="{earnings_status}" '
        f'data-atlas-company-profile="{profile_status}" data-atlas-performance-evidence="{performance_status}" '
        f'data-atlas-context-classification="{detail["context_classification"]}">'
        '<section class="atlas-signal-detail-head"><div><small>ORIGINAL CERTIFIED SIGNAL</small>'
        f'<h2>{ticker} · {company}</h2><p>{html.escape(str(original.get("timestamp") or "Unavailable"))}</p></div>'
        f'<div class="atlas-live-state"><small>CURRENT MARKET STATE</small><b>{_money(current.get("price"))}</b>'
        f'<span>{html.escape(str(current.get("status") or "UNAVAILABLE"))} · not a live quote</span>'
        f'<span>vs reference: {_percent(current.get("distance_to_reference_pct") / 100 if current.get("distance_to_reference_pct") is not None else None)} · '
        f'vs Fair Value: {_percent(current.get("distance_to_fair_value_pct") / 100 if current.get("distance_to_fair_value_pct") is not None else None)}</span></div></section>'
        '<section class="atlas-signal-metrics">'
        f'<article><small>Original Action</small><b>{html.escape(str(original.get("action") or "Unavailable"))}</b></article>'
        f'<article><small>Reference Price</small><b>{_money(original.get("reference_price"))}</b></article>'
        f'<article><small>ATLAS Fair Value</small><b>{_money(original.get("atlas_fair_value"))}</b></article>'
        f'<article><small>Opportunity</small><b>{_score(original.get("opportunity"))}</b></article>'
        f'<article><small>Confidence</small><b>{_score(original.get("confidence"))}</b></article>'
        f'<article><small>Observations</small><b>{sum(x["status"] == "AVAILABLE" for x in detail["performance"])}</b></article>'
        '</section></div>', unsafe_allow_html=True,
    )

    chart = detail.get("price_chart") or {}
    st.subheader("Verified price history")
    from services.atlas_explains import build_page_explanation
    from ui.atlas_explains import render_atlas_explains
    render_atlas_explains(build_page_explanation(
        "Charts", source_date=str(chart.get("as_of") or "Source date unavailable"),
    ))
    if chart.get("status") != "AVAILABLE":
        st.markdown('<span data-atlas-qa="report-card-chart-unavailable" '
                    f'data-atlas-chart-status="{html.escape(str(chart.get("status") or "UNAVAILABLE"))}" '
                    'aria-hidden="true" style="display:none">chart unavailable</span>', unsafe_allow_html=True)
        st.info(chart.get("message") or "Verified historical chart evidence is unavailable.")
    else:
        bars = chart["bars"]
        evidence_ids = chart.get("provenance", {}).get("evidence_ids") or ()
        st.markdown('<span data-atlas-qa="report-card-price-chart" data-atlas-chart-status="AVAILABLE" '
                    f'data-atlas-chart-as-of="{html.escape(str(chart["as_of"]))}" '
                    f'data-atlas-chart-evidence-count="{len(evidence_ids)}" '
                    'data-atlas-chart-classification="EDUCATIONAL_NON_SCORING" '
                    'aria-hidden="true" style="display:none">verified chart</span>', unsafe_allow_html=True)
        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True, vertical_spacing=.035,
            row_heights=[.56, .14, .15, .15],
            specs=[[{"secondary_y": True}], [{}], [{}], [{}]],
        )
        dates = [x["date"] for x in bars]
        indicators = chart["indicators"]
        if chart.get("candlestick_status") == "AVAILABLE":
            fig.add_trace(go.Candlestick(
                x=dates, open=[x["open"] for x in bars], high=[x["high"] for x in bars],
                low=[x["low"] for x in bars], close=[x["close"] for x in bars],
                name=f"{ticker} OHLC", increasing_line_color="#34d399", decreasing_line_color="#fb7185",
            ), row=1, col=1, secondary_y=False)
        else:
            fig.add_trace(go.Scatter(x=dates, y=[x["close"] for x in bars],
                                     name=f"{ticker} close", mode="lines",
                                     line={"color": "#5eead4", "width": 2}),
                          row=1, col=1, secondary_y=False)
        for key, label, color in (("sma20", "20-session average", "#38bdf8"),
                                  ("sma50", "50-session average", "#f59e0b")):
            fig.add_trace(go.Scatter(x=dates, y=indicators[key], name=label, mode="lines",
                                     line={"color": color, "width": 1.25}),
                          row=1, col=1, secondary_y=False)
        if chart.get("spy_comparison"):
            fig.add_trace(go.Scatter(x=[x["date"] for x in chart["spy_comparison"]],
                                     y=[x["indexed_close"] for x in chart["spy_comparison"]],
                                     name="SPY · indexed to 100", mode="lines",
                                     line={"color": "#a78bfa", "width": 1.5, "dash": "dot"}),
                          row=1, col=1, secondary_y=True)
        support, resistance = chart["support_zone"], chart["resistance_zone"]
        fig.add_hrect(y0=support[0], y1=support[1], fillcolor="rgba(34,197,94,.14)", line_width=0,
                      annotation_text="Support zone", row=1, col=1)
        fig.add_hrect(y0=resistance[0], y1=resistance[1], fillcolor="rgba(59,130,246,.14)", line_width=0,
                      annotation_text="Resistance zone", row=1, col=1)
        trend = chart.get("trendline")
        if trend:
            fig.add_trace(go.Scatter(x=[bars[0]["date"], bars[-1]["date"]], y=[trend["start"], trend["end"]],
                                     name="Descriptive trend", mode="lines",
                                     line={"color": "#fbbf24", "dash": "dash"}),
                          row=1, col=1, secondary_y=False)
        marker = chart.get("signal_marker")
        if marker:
            fig.add_trace(go.Scatter(x=[marker["date"]], y=[marker["price"]], name="Original ATLAS signal",
                                     mode="markers", marker={"size": 10, "symbol": "diamond", "color": "#ffffff"}),
                          row=1, col=1, secondary_y=False)
        observed = [item for item in detail.get("performance") or ()
                    if item.get("status") == "AVAILABLE" and item.get("observed_price") is not None]
        if observed:
            fig.add_trace(go.Scatter(
                x=[item["observed_at"] for item in observed], y=[item["observed_price"] for item in observed],
                text=[f'{item["horizon_sessions"]}-session measured outcome' for item in observed],
                name="Measured outcomes", mode="markers+text", textposition="top center",
                marker={"size": 9, "symbol": "circle", "color": "#c4b5fd"},
            ), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Bar(x=dates, y=[x["volume"] for x in bars], name="Volume",
                             marker_color="rgba(94,234,212,.42)"), row=2, col=1)
        fig.add_trace(go.Scatter(x=dates, y=indicators["rsi14"], name="RSI (14)", mode="lines",
                                 line={"color": "#22d3ee", "width": 1.4}), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="rgba(251,113,133,.7)", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="rgba(52,211,153,.7)", row=3, col=1)
        fig.add_trace(go.Bar(x=dates, y=indicators["macd_histogram"], name="MACD difference",
                             marker_color="rgba(167,139,250,.42)"), row=4, col=1)
        fig.add_trace(go.Scatter(x=dates, y=indicators["macd"], name="MACD", mode="lines",
                                 line={"color": "#a78bfa", "width": 1.3}), row=4, col=1)
        fig.add_trace(go.Scatter(x=dates, y=indicators["macd_signal"], name="MACD signal", mode="lines",
                                 line={"color": "#f59e0b", "width": 1.1}), row=4, col=1)
        range_specs = {
            "1M": {"count": 1, "label": "1M", "step": "month", "stepmode": "backward"},
            "3M": {"count": 3, "label": "3M", "step": "month", "stepmode": "backward"},
            "6M": {"count": 6, "label": "6M", "step": "month", "stepmode": "backward"},
            "1Y": {"count": 1, "label": "1Y", "step": "year", "stepmode": "backward"},
            "5Y": {"count": 5, "label": "5Y", "step": "year", "stepmode": "backward"},
        }
        visible_series = [ticker, "20/50-session averages", "Volume", "RSI (14)", "MACD"]
        if chart.get("spy_comparison"):
            visible_series.append("SPY indexed to 100")
        if trend:
            visible_series.append("OLS trend")
        if marker:
            visible_series.append("Original ATLAS signal")
        fig.update_layout(
            template="plotly_dark", height=720,
            margin={"l": 12, "r": 12, "t": 24, "b": 12},
            paper_bgcolor="#08111f", plot_bgcolor="#08111f",
            font={"color": "#e2e8f0", "family": "Inter, system-ui, sans-serif"},
            hovermode="x unified", showlegend=False,
            xaxis={
                "rangeselector": {
                    "buttons": [range_specs[label] for label in chart["ranges"]],
                    "bgcolor": "#1e3a5f", "activecolor": "#2563eb", "bordercolor": "#6a9eff",
                    "borderwidth": 1, "font": {"color": "#ffffff", "size": 11},
                },
                "gridcolor": "rgba(71,85,105,.35)", "zerolinecolor": "rgba(71,85,105,.45)",
            },
            yaxis={"title": "Price", "gridcolor": "rgba(71,85,105,.35)", "zerolinecolor": "rgba(71,85,105,.45)"},
            annotations=[{
                "xref": "paper", "yref": "paper", "x": 0, "y": -0.17,
                "xanchor": "left", "yanchor": "top", "showarrow": False,
                "text": "  •  ".join(visible_series),
                "font": {"color": "#e2e8f0", "size": 12},
            }],
        )
        fig.update_yaxes(title_text="SPY indexed", showgrid=False, row=1, col=1, secondary_y=True)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=3, col=1)
        fig.update_yaxes(title_text="MACD", row=4, col=1)
        fig.update_xaxes(rangeslider_visible=False)
        st.plotly_chart(
            fig,
            width="stretch",
            key=f"report-card-chart-{detail.get('signal_id')}",
            config={
                "displaylogo": False,
                "responsive": True,
                # Plotly's floating toolbar obscures the 1Y range selector at
                # 360px even after removing export. Native touch/mouse zoom,
                # hover and all governed timeframe buttons remain available.
                "displayModeBar": False,
            },
        )
        st.caption(f'Latest verified close {_money(chart["latest_price"])} · as of {chart["as_of"]}. '
                   f'{chart["methodology"]} Educational, non-scoring context.')
        st.info(
            "How to read this: candles show each completed session's open, high, low and close when all four values "
            "are verified. The 20- and 50-session averages smooth daily moves. RSI describes recent momentum on a "
            "0–100 scale, while MACD compares faster and slower price trends. These are historical descriptions, "
            "not predictions, recommendations or inputs to ATLAS scoring."
        )
        with st.expander("Indicator calculations and evidence limits", expanded=False):
            st.markdown("\n".join(f"- **{name.upper()}**: {text}" for name, text in indicators["methodology"].items()))
            if chart.get("candlestick_status") != "AVAILABLE":
                st.warning("Verified opening prices are incomplete, so the chart uses closing prices instead of inventing candles.")
            if chart.get("volume_status") != "AVAILABLE":
                st.warning("Some verified volume values are unavailable; gaps remain blank.")
            if chart.get("spy_status") != "AVAILABLE":
                st.warning("SPY comparison is unavailable because at least 20 aligned completed sessions are required.")
        with st.expander("Accessible chart data", expanded=False):
            st.write(f'{len(bars)} verified completed-session observations. Latest close '
                     f'{_money(chart["latest_price"])} as of {chart["as_of"]}. '
                     'Support and resistance are labeled zones; the dashed line is a descriptive OLS trend, not a forecast.')
            st.dataframe([{"Session": row["date"], "Open": row["open"], "Close": row["close"],
                           "High": row["high"], "Low": row["low"], "Volume": row["volume"]}
                          for row in bars], width="stretch", hide_index=True)

    st.subheader("Performance by registered horizon")
    st.caption("On a small screen, swipe the table sideways to see price and return columns.")
    st.dataframe([{
        "Horizon": f'{item["horizon_sessions"]} sessions',
        "Status": "Pending" if item["status"] == "PENDING" else item["status"],
        "Observed price": _money(item["observed_price"]) if item["observed_price"] is not None else "Pending",
        "Signal return": _percent(item["stock_return"]),
        "SPY return": _percent(item["spy_return"]),
        "Relative performance": _percent(item["excess_return"]),
        "Corporate action": item["corporate_action_status"],
    } for item in detail["performance"]], width="stretch", hide_index=True)

    st.subheader("ATLAS Signal Digest")
    for section in detail["digest"]:
        st.markdown(f'**{section["title"]}**  \n{section["text"]}')
        st.markdown(f'<span class="atlas-context-flag">{section["context_classification"]}</span>', unsafe_allow_html=True)

    st.subheader("Original thesis and view-change conditions")
    thesis = detail["original_thesis"]
    st.markdown("\n".join(f"- {item}" for item in thesis) if thesis else "No approved thesis narrative is available.")
    conditions = detail["view_change_conditions"]
    st.markdown("**Conditions that could change the view**")
    st.markdown("\n".join(f"- {item}" for item in conditions) if conditions else "No approved structured conditions are available.")

    with st.expander(f'About {detail.get("company_name") or detail.get("ticker")}', expanded=False):
        items = (
            ("Company", profile.get("company_name")), ("Sector", profile.get("sector")),
            ("Industry", profile.get("industry")), ("Market cap", _money(profile.get("market_cap"))),
            ("Leadership", profile.get("leadership")), ("Headquarters", profile.get("headquarters")),
            ("Founded", profile.get("founded")), ("Employees", profile.get("employees")),
            ("Source", profile.get("source")), ("Source timestamp", profile.get("source_timestamp")),
            ("Freshness", profile.get("freshness")),
        )
        st.markdown('<div class="atlas-profile-grid">' + "".join(
            f'<div><small>{html.escape(label)}</small><b>{html.escape(str(value if value not in (None, "") else "Unavailable"))}</b></div>'
            for label, value in items
        ) + '</div>', unsafe_allow_html=True)
    with st.expander("Event timeline", expanded=False):
        st.info(detail["event_timeline_status"])
    with st.expander("Evidence and audit identity", expanded=False):
        st.markdown(
            f'**Authority:** {detail["authority_status"]}  \n'
            f'**Candidate:** `{original.get("candidate_digest")}`  \n'
            f'**Publication:** `{original.get("publication_digest")}`  \n'
            f'**Evaluation snapshot:** `{original.get("evaluation_snapshot_id")}`  \n'
            f'**Generation:** {detail["generation_mode"]}  \n'
            f'**Context classification:** `{detail["context_classification"]}`'
        )
    st.subheader("Performance Context")
    st.info(detail["move_attribution"]["text"])
    st.markdown("**Positive drivers**")
    st.markdown("\n".join(f'- {item}' for item in detail["move_attribution"]["positive_drivers"]) or "- Not attributable from approved evidence.")
    st.markdown("**Negative drivers**")
    st.markdown("\n".join(f'- {item}' for item in detail["move_attribution"]["negative_drivers"]) or "- Not attributable from approved evidence.")
    st.markdown("**Uncertain / not attributable**")
    st.markdown("\n".join(f'- {item}' for item in detail["move_attribution"]["uncertain_or_not_attributable"]))


def render_internal_report_card(ledger_path: Path, *, authorized: bool) -> Mapping[str, Any]:
    authority_root = Path(os.getenv("ATLAS_REPORT_CARD_CHART_EVIDENCE_ROOT", "."))
    report = build_internal_report_card(ledger_path, authorized=authorized, authority_root=authority_root)
    st.markdown('<span data-atlas-qa="internal-report-card" data-atlas-customer-visible="false" '
                'aria-hidden="true" style="display:none">internal-report-card</span>', unsafe_allow_html=True)
    st.markdown(
        '<div class="atlas-report-card-hero"><div class="atlas-kicker">INTERNAL ONLY · access controlled</div>'
        '<h1>Prospective Report Card</h1><p>Immutable signal observations measured against SPY. '
        'Signal tracking only — tracked recommendations are not funded model-portfolio purchases. '
        'Descriptive research operations only — Not a public performance claim.</p></div>',
        unsafe_allow_html=True,
    )
    view_mode, selected_id = normalize_report_card_view_state(
        st.session_state,
        [item["signal_id"] for item in report["signal_details"]],
    )
    st.markdown(
        f'<span data-atlas-qa="report-card-state" '
        f'data-atlas-view="{html.escape(view_mode)}" '
        f'data-atlas-selected-signal="{html.escape(selected_id or "")}" '
        'data-atlas-route="internal-report-card" '
        f'data-atlas-last-transition="{html.escape(str(st.session_state.get(REPORT_CARD_LAST_TRANSITION_KEY) or ""))}" '
        'aria-hidden="true" '
        'style="display:none">report-card-state</span>',
        unsafe_allow_html=True,
    )
    selected = next((item for item in report["signal_details"] if item["signal_id"] == selected_id), None)
    if view_mode == REPORT_CARD_VIEW_DETAIL and selected is not None:
        st.button(
            "← Back to Report Card",
            key="report_card_back_to_overview",
            on_click=back_to_report_card_overview,
            args=(st.session_state,),
        )
        _render_signal_detail(selected)
        return report

    st.markdown(OVERVIEW_CSS + overview_html(report), unsafe_allow_html=True)
    st.markdown(
        f'<span data-atlas-qa="report-card-overview" '
        f'data-atlas-report-card-view="{REPORT_CARD_VIEW_OVERVIEW}" '
        f'data-atlas-signal-count="{int(report["signal_count"])}" '
        f'data-atlas-observation-count="{int(report["observation_count"])}" '
        f'data-atlas-open-signal-count="{int(report["open_signal_count"])}" '
        f'data-atlas-spy-comparison-count="{int(report["spy_comparison_count"])}" '
        f'data-atlas-ledger-integrity="{html.escape(str(report["integrity"]))}" '
        f'data-atlas-backup-status="{html.escape(str(report["last_backup_status"]))}" '
        f'data-atlas-activation-timestamp="{html.escape(str(report["activation_timestamp"] or ""))}" '
        f'data-atlas-next-observation="{html.escape(str(report["next_eligible_observation"]))}" '
        'aria-hidden="true" style="display:none">report-card-overview</span>',
        unsafe_allow_html=True,
    )
    render_signal_directory(report["signals"], on_open=open_report_card_detail)
    st.markdown(
        '<div class="atlas-source-chips"><span class="atlas-certification-chip">Append-only ledger</span>'
        f'<span class="atlas-source-chip">Activated {report["activation_timestamp"]}</span>'
        f'<span class="atlas-source-chip">Ledger {report["ledger_tip_digest"][:12]}…</span>'
        f'<span class="atlas-source-chip">Backup {report["last_backup_status"]}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(f'Next eligible observation: {report["next_eligible_observation"]}')
    st.markdown(f'**Ledger integrity:** {report["integrity"]} · **Admission integrity:** '
                f'{report["admission_integrity"]} · **Backup status:** {report["last_backup_status"]}')
    if report["admission_defects"]:
        st.error("Signal-admission QA failed: " + ", ".join(report["admission_defects"]))
    st.subheader("Matured horizon coverage")
    st.markdown(horizon_coverage_html(report["coverage"]), unsafe_allow_html=True)
    st.subheader("Signal admission and observation detail")
    for signal in report["signals"]:
        with st.expander(f'{signal["ticker"]} · {signal["original_action"]} · {signal["observation_count"]} observations'):
            st.markdown(
                f'**Signal ID:** `{signal["signal_id"]}`  \n'
                f'**First seen:** {signal["signal_timestamp"]}  \n'
                f'**Reference price:** {signal["reference_price"]} · {signal["reference_price_timestamp"]}  \n'
                f'**Admission:** {signal["admission_reason"]} · publication eligible: '
                f'{signal["customer_publication_eligible_at_issuance"]}  \n'
                f'**Candidate:** `{signal["candidate_digest"]}`  \n'
                f'**Publication:** `{signal["publication_digest"]}`  \n'
                f'**Evaluation snapshot:** `{signal["evaluation_snapshot_id"]}`  \n'
                f'**Horizons:** {", ".join(str(item) for item in signal["registered_horizons"])} sessions · '
                f'next: {signal["next_eligible_horizon"] if signal["next_eligible_horizon"] is not None else "Complete"}  \n'
                f'**Corporate action:** {signal["corporate_action_state"]}'
            )
            rows = []
            for item in report["rows"]:
                if item["signal_id"] != signal["signal_id"]:
                    continue
                rows.append({
                    "Horizon": f'{item["horizon_sessions"]} sessions',
                    "Status": "Pending" if item["status"] == "NOT_MATURED_OR_NOT_OBSERVED" else item["status"],
                    "Observed price": (f'${float(item["observed_price"]):,.2f}'
                                       if item["observed_price"] is not None else "Not yet observed"),
                    "Signal return": _percent(item["stock_return"]), "SPY return": _percent(item["spy_return"]),
                    "Relative performance": _percent(item["excess_return"]),
                    "Observed at": item["observed_at"] or "Not yet observed",
                })
            st.dataframe(rows, width="stretch", hide_index=True)
            st.button(
                "View Signal Digest →",
                key=f'report_card_signal_{signal["signal_id"]}',
                on_click=open_report_card_detail,
                args=(st.session_state, signal["signal_id"]),
            )
    st.caption("Sample sizes are shown per horizon. Missing and not-yet-matured observations remain explicit.")
    return report


__all__ = [
    "REPORT_CARD_LAST_TRANSITION_KEY", "REPORT_CARD_SELECTED_SIGNAL_KEY", "REPORT_CARD_VIEW_DETAIL", "REPORT_CARD_VIEW_KEY",
    "REPORT_CARD_VIEW_OVERVIEW", "normalize_report_card_view_state", "open_report_card_detail",
    "open_report_card_overview", "back_to_report_card_overview", "render_internal_report_card",
]
