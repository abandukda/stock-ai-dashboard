
"""
Atlas V2 Phase 1 — Unified Institutional Research Report
"""

from __future__ import annotations

from html import escape
from typing import Any, Mapping
import re

import pandas as pd
import streamlit as st

from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines.ask_atlas_engine import ask_atlas


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _pct(value: Any, signed: bool = False) -> str:
    try:
        number = float(value)
        prefix = "+" if signed and number > 0 else ""
        return f"{prefix}{number:.1f}%"
    except (TypeError, ValueError):
        return "Unavailable"


def _score(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _clean_prose(value: Any) -> str:
    """Normalize generated prose so Markdown cannot create accidental code pills."""
    text = str(value or "").replace("`", "")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return text.strip()


def _render_consistent_prose(value: Any, *, qa_name: str) -> None:
    """Render ordinary prose as escaped HTML with one consistent typography style."""
    text = _clean_prose(value)
    if not text:
        text = "No grounded narrative is currently available."
    st.markdown(
        (
            f'<div class="atlas-prose" data-atlas-qa="narrative" '
            f'data-atlas-qa-name="{escape(qa_name)}">{escape(text)}</div>'
        ),
        unsafe_allow_html=True,
    )


def _inject_visual_standards() -> None:
    """Install defensive CSS for research cards and narrative typography."""
    st.markdown(
        """
        <style>
        .atlas-prose {
            color: inherit;
            font-family: inherit;
            font-size: 1.08rem;
            font-weight: 400;
            line-height: 1.62;
            letter-spacing: normal;
            white-space: normal;
            overflow-wrap: normal;
            word-break: normal;
            hyphens: none;
            margin: 0.35rem 0 1.2rem 0;
        }
        .atlas-prose code,
        .atlas-prose pre {
            all: unset !important;
            color: inherit !important;
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            padding: 0 !important;
            font: inherit !important;
            white-space: inherit !important;
        }
        .atlas-trade-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(150px, 1fr));
            gap: 1rem;
            width: 100%;
            margin: 0.6rem 0 1.1rem 0;
        }
        .atlas-trade-card {
            min-width: 0;
            min-height: 128px;
            padding: 1.35rem 1.45rem;
            border: 1px solid rgba(120, 155, 205, 0.28);
            border-radius: 24px;
            background: linear-gradient(
                145deg,
                rgba(20, 30, 51, 0.98),
                rgba(13, 23, 42, 0.98)
            );
            display: flex;
            flex-direction: column;
            justify-content: center;
            box-sizing: border-box;
            overflow: hidden;
        }
        .atlas-trade-label {
            color: #c4cce0;
            font-family: inherit;
            font-size: 1rem;
            font-weight: 500;
            line-height: 1.25;
            margin-bottom: 0.55rem;
            white-space: nowrap;
        }
        .atlas-trade-value {
            color: #f7f9ff;
            font-family: inherit;
            font-size: clamp(1.55rem, 2.2vw, 2.2rem);
            font-weight: 800;
            line-height: 1.08;
            letter-spacing: -0.035em;
            white-space: nowrap;
            word-break: keep-all;
            overflow-wrap: normal;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        @media (max-width: 1150px) {
            .atlas-trade-grid {
                grid-template-columns: repeat(3, minmax(150px, 1fr));
            }
        }
        @media (max-width: 760px) {
            .atlas-trade-grid {
                grid-template-columns: repeat(2, minmax(135px, 1fr));
            }
            .atlas-trade-card {
                min-height: 112px;
                padding: 1rem;
            }
        }
        @media (max-width: 460px) {
            .atlas-trade-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _trade_card(label: str, value: Any, *, qa_name: str) -> str:
    return (
        f'<div class="atlas-trade-card" data-atlas-qa="trade-card" '
        f'data-atlas-qa-name="{escape(qa_name)}">'
        f'<div class="atlas-trade-label">{escape(label)}</div>'
        f'<div class="atlas-trade-value">{escape(str(value))}</div>'
        "</div>"
    )


def _render_trade_card_grid(items: list[tuple[str, Any, str]]) -> None:
    cards = "".join(_trade_card(label, value, qa_name=name) for label, value, name in items)
    st.markdown(f'<div class="atlas-trade-grid">{cards}</div>', unsafe_allow_html=True)


def _meta(section: Mapping[str, Any]) -> None:
    st.caption(
        f"Status: {section.get('status', 'unavailable')} · "
        f"Completeness: {_pct(section.get('completeness_pct'))} · "
        f"Source: {section.get('source', 'Unknown')} · "
        f"As of: {section.get('as_of', 'Unknown')}"
    )


def _metric_grid(
    data: Mapping[str, Any],
    *,
    money_keys: set[str] | None = None,
    pct_keys: set[str] | None = None,
) -> None:
    money_keys = money_keys or set()
    pct_keys = pct_keys or set()
    scalar = [
        (key, value)
        for key, value in data.items()
        if not isinstance(value, (list, dict)) and value not in (None, "")
    ]
    if not scalar:
        st.info("No populated metrics are available for this section.")
        return

    for start in range(0, len(scalar), 4):
        cols = st.columns(4)
        for col, (key, value) in zip(cols, scalar[start : start + 4]):
            label = key.replace("_", " ").title()
            if key in money_keys:
                display = _money(value)
            elif key in pct_keys:
                display = _pct(value)
            else:
                display = value
            col.metric(label, display)


def _render_interpretation(text: str) -> None:
    st.markdown("#### Atlas Interpretation")
    st.info(text or "Atlas does not yet have enough structured evidence to provide a reliable interpretation.")


def _render_price_chart(report: Mapping[str, Any]) -> None:
    section = report["sections"]["technical"]
    history = section.get("history") or []
    if not history:
        provenance = section.get("history_provenance") or {}
        status = provenance.get("status") or "NOT_LOADED"
        if status == "PROVIDER_ERROR":
            st.warning(
                "Historical price data could not be retrieved from the connected "
                "market-data providers. Atlas did not infer chart values."
            )
        elif status == "NO_RECORDS":
            st.info(
                "The market-data provider completed successfully but returned no "
                "historical price records for this ticker."
            )
        elif status == "STALE":
            st.warning(
                "Only stale historical data are available. Atlas has not rendered "
                "the chart until usable records are present."
            )
        else:
            st.info(
                "Historical price data were not loaded for this report. "
                "No conclusion should be drawn from the missing chart."
            )
        if provenance:
            st.caption(
                f"History status: {status} · "
                f"Source: {provenance.get('source', 'Unknown')} · "
                f"Records: {provenance.get('records_found', 0)} · "
                f"Retrieval: {provenance.get('retrieval_status', 'Unknown')}"
            )
        return

    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception:
        st.dataframe(pd.DataFrame(history), hide_index=True, use_container_width=True)
        return

    frame = pd.DataFrame(history)
    date_col = next((key for key in ("date", "datetime", "timestamp", "time") if key in frame.columns), None)
    close_col = next((key for key in ("close", "price", "Close", "adjClose") if key in frame.columns), None)
    volume_col = next((key for key in ("volume", "Volume") if key in frame.columns), None)

    if not date_col or not close_col:
        st.info("Historical data are present but do not contain recognizable date and close fields.")
        st.dataframe(frame, hide_index=True, use_container_width=True)
        return

    frame = frame.copy()
    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
    frame[close_col] = pd.to_numeric(frame[close_col], errors="coerce")
    frame = frame.dropna(subset=[date_col, close_col]).sort_values(date_col)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.06,
    )
    fig.add_trace(
        go.Scatter(
            x=frame[date_col],
            y=frame[close_col],
            mode="lines",
            name="Price",
        ),
        row=1,
        col=1,
    )

    technical = section.get("data") or {}
    lines = [
        ("Atlas Fair Value", report.get("validated_fair_value"), "dash"),
        (
            "Wall Street Average",
            (report["sections"]["analysts"].get("data") or {}).get("average_target"),
            "dot",
        ),
        ("SMA 50", technical.get("sma50"), "dashdot"),
        ("SMA 200", technical.get("sma200"), "longdash"),
        ("Support", technical.get("support"), "dot"),
        ("Resistance", technical.get("resistance"), "dot"),
    ]
    plan = report.get("trade_plan") or {}
    lines.extend(
        [
            ("Entry Low", plan.get("entry_low"), "dash"),
            ("Entry High", plan.get("entry_high"), "dash"),
            ("Stop", plan.get("stop_loss"), "dot"),
            ("Target 1", plan.get("target_1"), "dashdot"),
            ("Target 2", plan.get("target_2"), "dashdot"),
        ]
    )

    for name, value, dash in lines:
        if value is None:
            continue
        fig.add_hline(
            y=float(value),
            line_dash=dash,
            annotation_text=name,
            row=1,
            col=1,
        )

    if volume_col:
        frame[volume_col] = pd.to_numeric(frame[volume_col], errors="coerce")
        fig.add_trace(
            go.Bar(
                x=frame[date_col],
                y=frame[volume_col],
                name="Volume",
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        height=650,
        margin=dict(l=10, r=10, t=30, b=10),
        legend_orientation="h",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    provenance = section.get("history_provenance") or {}
    if provenance:
        st.caption(
            f"History source: {provenance.get('source', 'Unknown')} · "
            f"Records: {provenance.get('records_found', len(history))} · "
            f"Status: {provenance.get('status', 'AVAILABLE')} · "
            f"As of: {provenance.get('as_of', 'Unknown')}"
        )


def _render_trade_plan(report: Mapping[str, Any]) -> None:
    plan = report.get("trade_plan") or {}
    st.markdown("### Live Price & Educational Trade Plan")
    if not plan.get("actionable"):
        st.warning(plan.get("reason", "A current quote is required before Atlas can calculate a trade plan."))
        return

    entry_low = _money(plan.get("entry_low"))
    entry_high = _money(plan.get("entry_high"))
    entry_zone = (
        f"{entry_low}–{entry_high}"
        if "Unavailable" not in (entry_low, entry_high)
        else "Unavailable"
    )

    _render_trade_card_grid([
        ("Current Price", _money(plan.get("current_price")), "current-price"),
        ("Entry Zone", entry_zone, "entry-zone"),
        ("Stop", _money(plan.get("stop_loss")), "stop-loss"),
        ("Target 1", _money(plan.get("target_1")), "target-1"),
        ("Target 2", _money(plan.get("target_2")), "target-2"),
        ("Atlas Target", _money(plan.get("atlas_target")), "atlas-target"),
        ("Analyst Average", _money(plan.get("analyst_average_target")), "analyst-average"),
        ("Do Not Chase", _money(plan.get("do_not_chase")), "do-not-chase"),
        ("R/R to Target 1", plan.get("risk_reward_target_1", "Unavailable"), "risk-reward"),
        ("Primary Horizon", (plan.get("horizon") or {}).get("primary", "Unavailable"), "horizon"),
    ])

    quote = plan.get("quote") or {}
    st.caption(
        f"Price as of {quote.get('price_as_of', 'Unknown')} · "
        f"Source: {quote.get('quote_source', 'Unknown')} · "
        f"Market: {quote.get('market_status', 'Unknown')}"
    )
    st.warning(
        "Educational guidance only. Stop prices and targets are not guaranteed, "
        "and gaps can cause execution outside the displayed levels."
    )


def _render_ai_intelligence(report: Mapping[str, Any]) -> None:
    intelligence = report.get("intelligence") or {}
    today = intelligence.get("today_move") or {}

    st.markdown("### Atlas AI Intelligence")
    _render_consistent_prose(
        intelligence.get("executive_summary")
        or report.get("executive_summary")
        or "No grounded executive summary is currently available.",
        qa_name="atlas-ai-intelligence-summary",
    )

    support_col, risk_col = st.columns(2)
    with support_col:
        st.markdown("#### Why Atlas Supports It")
        items = intelligence.get("why_atlas_supports_it") or []
        if items:
            for item in items:
                st.success(str(item))
        else:
            st.info("No structured supporting evidence is currently populated.")
    with risk_col:
        st.markdown("#### Key Risks")
        items = intelligence.get("key_risks") or []
        if items:
            for item in items:
                st.warning(str(item))
        else:
            st.info("No structured risk evidence is currently populated.")

    st.markdown("#### Today's Move Explained")
    c = st.columns(2)
    c[0].metric("Move Explanation", today.get("headline", "Under review"))
    c[1].metric(
        "Explanation Confidence",
        _pct(today.get("explanation_confidence_pct")),
    )

    facts = today.get("verified_facts") or []
    inferences = today.get("atlas_inferences") or []
    limitations = today.get("data_limitations") or []
    for item in facts:
        st.markdown(f"**Verified fact:** {item}")
    for item in inferences:
        st.markdown(f"**Atlas inference:** {item}")
    for item in limitations:
        st.caption(f"Data limitation: {item}")

    up_col, down_col = st.columns(2)
    with up_col:
        st.markdown("#### What Could Upgrade the Rating")
        for item in intelligence.get("upgrade_triggers") or []:
            st.info(str(item))
    with down_col:
        st.markdown("#### What Could Downgrade the Rating")
        for item in intelligence.get("downgrade_triggers") or []:
            st.warning(str(item))

    st.caption(intelligence.get("evidence_note", ""))


def _render_ask_atlas(report: Mapping[str, Any]) -> None:
    st.markdown("### Ask Atlas AI")
    st.caption(
        "Ask about today's move, the verdict, earnings, risks, valuation, "
        "or what could change the rating."
    )

    ticker = str(report.get("ticker") or "UNKNOWN")
    suggested = st.columns(4)
    prompts = [
        "Why did this stock move today?",
        "Why is this the current Atlas rating?",
        "What are the biggest risks?",
        "Explain this for a beginner.",
    ]
    for col, prompt in zip(suggested, prompts):
        if col.button(prompt, key=f"ask_suggest_{ticker}_{prompt}"):
            st.session_state[f"ask_atlas_question_{ticker}"] = prompt

    question = st.text_input(
        "Question",
        value=st.session_state.get(f"ask_atlas_question_{ticker}", ""),
        placeholder="Example: What would upgrade this stock to Buy Now?",
        key=f"ask_atlas_input_{ticker}",
    )
    if st.button(
        "Ask Atlas",
        key=f"ask_atlas_submit_{ticker}",
        type="primary",
        use_container_width=True,
    ):
        st.session_state[f"ask_atlas_answer_{ticker}"] = ask_atlas(
            question,
            report,
        )

    result = st.session_state.get(f"ask_atlas_answer_{ticker}")
    if result:
        st.markdown(result.get("answer") or "")
        sources = result.get("sources_used") or []
        st.caption(
            f"Mode: {result.get('mode', 'Unknown')} · "
            f"Atlas sections used: {', '.join(sources) if sources else 'None'} · "
            f"Report generated: {result.get('generated_from', 'Unknown')}"
        )

def render_atlas_research_v2(row: Mapping[str, Any]) -> None:
    report = build_atlas_research_v2(row)
    _inject_visual_standards()

    st.markdown(
        f"""
        <div style="border:1px solid rgba(95,159,226,.32);border-radius:24px;padding:24px;
        background:linear-gradient(145deg,rgba(14,39,65,.98),rgba(7,18,34,.98));margin-bottom:18px">
          <div style="color:#8fa8c4;font-size:.75rem;font-weight:850;letter-spacing:.14em;text-transform:uppercase">
            Atlas V2 Institutional Intelligence
          </div>
          <div style="color:#f8faff;font-size:2.5rem;font-weight:900;margin-top:8px">
            {escape(str(report.get("ticker") or "UNKNOWN"))}
          </div>
          <div style="color:#aebbd0;margin-top:9px">
            {escape(str(report.get("company") or ""))} ·
            {escape(str(report.get("sector") or "Unknown"))} ·
            {escape(str(report.get("committee_verdict") or "Monitor").replace("_", " ").title())}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c = st.columns(5)
    c[0].metric("Verdict", str(report.get("committee_verdict") or "Monitor").replace("_", " ").title())
    c[1].metric("Opportunity", _score(report.get("opportunity_score")))
    c[2].metric("Confidence", _pct(report.get("confidence_pct")))
    c[3].metric("Expected Return", _pct(report.get("expected_return_pct"), signed=True))
    c[4].metric("Research Completeness", _pct(report.get("research_completeness_pct")))

    st.markdown("## Executive Summary")
    _render_consistent_prose(
        report.get("executive_summary") or "No executive summary is currently available.",
        qa_name="executive-summary",
    )
    guidance = report.get("guidance_summary") or {}
    action = guidance.get("action_now") or {}
    st.markdown("### What the investor should do now")
    st.info(
        f"{action.get('current_action', 'Monitor')} · "
        f"{action.get('entry_timing_context', 'No verified timing instruction is available.')} · "
        f"Position guidance: {action.get('position_size_guidance', 'Unavailable')}"
    )
    support_col, risk_col = st.columns(2)
    with support_col:
        st.markdown("### Why")
        for item in guidance.get("supporting_facts") or []:
            st.success(f"{item.get('fact')} {item.get('why_it_matters')}")
            st.caption(f"Source: {item.get('source')} · As of: {item.get('as_of')}")
    with risk_col:
        st.markdown("### What Atlas is cautious about")
        risks = guidance.get("key_risks") or []
        for item in risks:
            st.warning(f"{item.get('risk')} {item.get('consequence')}")
        if not risks:
            st.info("No concrete adverse evidence is populated; monitor the thesis-change conditions below.")
    catalyst = guidance.get("next_catalyst") or {}
    st.markdown("### What happens next")
    st.write(
        f"{catalyst.get('event', 'No verified next catalyst is available')}"
        + (f" — {catalyst.get('date')}" if catalyst.get("date") else "")
        + f". {catalyst.get('what_atlas_will_watch', '')}"
    )
    changes = guidance.get("thesis_change_conditions") or {}
    with st.expander("What would strengthen, weaken, or invalidate the thesis"):
        for label in ("strengthen", "weaken", "invalidate"):
            st.markdown(f"**{label.title()}**")
            for item in changes.get(label) or []:
                st.write(f"- {item}")
    gaps = guidance.get("unavailable_evidence") or []
    if gaps:
        st.caption("Important evidence unavailable: " + "; ".join(gaps))
    _render_trade_plan(report)

    tabs = st.tabs(
        [
            "Thesis",
            "Financials",
            "Earnings",
            "Wall Street",
            "News",
            "Political",
            "Ownership",
            "Chart & Technicals",
            "Valuation & Risk",
            "Final Decision",
            "AI Intelligence",
            "Ask Atlas AI",
        ]
    )

    with tabs[0]:
        st.markdown("### Investment Thesis")
        st.write(report.get("investment_thesis") or "No investment thesis is currently available.")
        bull, bear = st.columns(2)
        with bull:
            st.markdown("#### Bull Case")
            items = report.get("bull_case") or []
            if items:
                for item in items:
                    st.success(str(item))
            else:
                st.info("No structured bull-case evidence is available.")
        with bear:
            st.markdown("#### Bear Case")
            items = report.get("bear_case") or []
            if items:
                for item in items:
                    st.warning(str(item))
            else:
                st.info("No structured bear-case evidence is available.")

        st.markdown("#### Score Attribution")
        attribution = report.get("score_attribution") or {}
        rows = []
        for category, values in (
            ("Opportunity", attribution.get("opportunity_attribution") or {}),
            ("Confidence", attribution.get("confidence_attribution") or {}),
        ):
            for factor, contribution in values.items():
                rows.append(
                    {
                        "Score": category,
                        "Factor": factor.replace("_", " ").title(),
                        "Contribution": contribution,
                    }
                )
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    with tabs[1]:
        section = report["sections"]["financials"]
        st.markdown("### Financial Intelligence")
        _meta(section)
        _metric_grid(
            section.get("data") or {},
            money_keys={"free_cash_flow", "cash", "debt"},
            pct_keys={
                "revenue_growth_pct",
                "eps_growth_pct",
                "gross_margin_pct",
                "operating_margin_pct",
                "net_margin_pct",
                "roe_pct",
                "roic_pct",
            },
        )
        _render_interpretation(section.get("interpretation", ""))

    with tabs[2]:
        section = report["sections"]["earnings"]
        st.markdown("### Latest Earnings & Transcript")
        _meta(section)
        data = section.get("data") or {}
        _metric_grid(
            data,
            pct_keys={"eps_surprise_pct", "revenue_surprise_pct"},
        )
        for key in ("guidance", "management_tone", "transcript_summary", "important_quote"):
            if data.get(key):
                st.markdown(f"#### {key.replace('_', ' ').title()}")
                st.write(data[key])

        history = section.get("history") or []
        st.markdown("#### Previous Earnings History")
        if history:
            st.dataframe(pd.DataFrame(history), hide_index=True, use_container_width=True)
        else:
            st.info("No structured multi-quarter earnings history is attached to this stock row.")
        _render_interpretation(section.get("interpretation", ""))

    with tabs[3]:
        section = report["sections"]["analysts"]
        st.markdown("### Wall Street & Top Analyst Intelligence")
        _meta(section)
        data = section.get("data") or {}
        _metric_grid(
            data,
            money_keys={
                "average_target",
                "high_target",
                "low_target",
                "top_analyst_target",
                "highest_published_target",
            },
        )
        details = section.get("details") or []
        st.markdown("#### Analyst Detail & Status")
        if details:
            st.dataframe(pd.DataFrame(details), hide_index=True, use_container_width=True)
        else:
            st.info(
                "Individual analyst records are not present. Atlas will not call the highest target "
                "a 'top analyst' unless accuracy or ranking data are supplied."
            )
        _render_interpretation(section.get("interpretation", ""))

    with tabs[4]:
        section = report["sections"]["news"]
        st.markdown("### Recent News & Catalyst Intelligence")
        _meta(section)
        items = section.get("data") or []
        if not items:
            st.info("No verified recent-news records are attached to the current research row.")
        for item in items:
            with st.container(border=True):
                st.markdown(f"**{item.get('headline', 'Headline unavailable')}**")
                details = " · ".join(
                    str(value)
                    for value in (item.get("source"), item.get("date"), item.get("sentiment"))
                    if value
                )
                if details:
                    st.caption(details)
                if item.get("summary"):
                    st.write(item["summary"])
                if item.get("impact") is not None:
                    st.metric("Materiality / Impact", _score(item["impact"]))
        _render_interpretation(section.get("interpretation", ""))

    with tabs[5]:
        section = report["sections"]["political"]
        st.markdown("### Political, Congressional & Regulatory Intelligence")
        _meta(section)
        data = section.get("data") or {}
        _metric_grid(
            data,
            pct_keys={"political_support_score"},
        )
        transactions = data.get("transactions") or []
        st.markdown("#### Recent Political Transactions")
        if transactions:
            st.dataframe(pd.DataFrame(transactions), hide_index=True, use_container_width=True)
        else:
            st.info(
                "No structured recent political transactions are present. This is missing evidence, "
                "not confirmation that no activity exists."
            )
        _render_interpretation(section.get("interpretation", ""))

    with tabs[6]:
        section = report["sections"]["ownership"]
        st.markdown("### Ownership, Institutions & Insiders")
        _meta(section)
        data = section.get("data") or {}
        _metric_grid(
            data,
            pct_keys={"institutional_ownership_pct", "institutional_change_pct"},
        )
        if data.get("major_holders"):
            st.markdown("#### Major Holders")
            st.dataframe(pd.DataFrame(data["major_holders"]), hide_index=True, use_container_width=True)
        if data.get("insider_transactions"):
            st.markdown("#### Insider Transactions")
            st.dataframe(pd.DataFrame(data["insider_transactions"]), hide_index=True, use_container_width=True)
        _render_interpretation(section.get("interpretation", ""))

    with tabs[7]:
        section = report["sections"]["technical"]
        st.markdown("### Technical Intelligence")
        _meta(section)
        _metric_grid(
            section.get("data") or {},
            money_keys={"price", "sma20", "sma50", "sma200", "support", "resistance"},
        )
        _render_price_chart(report)
        _render_interpretation(section.get("interpretation", ""))

    with tabs[8]:
        st.markdown("### Fair Value Scenarios")
        cases = report.get("fair_value_cases") or []
        if cases:
            cols = st.columns(min(3, len(cases)))
            for col, case in zip(cols, cases):
                with col:
                    st.markdown(f"#### {case.get('label', 'Case')}")
                    st.metric("Fair Value", _money(case.get("fair_value")))
                    st.metric("Expected Return", _pct(case.get("expected_return_pct"), signed=True))
                    st.caption(f"Probability: {_pct(case.get('probability_pct'))}")
        else:
            st.info("Fair-value scenarios are unavailable.")

        risk = report["sections"]["risk"]
        st.markdown("### Atlas Risk Center")
        if risk.get("data"):
            for item in risk["data"]:
                with st.container(border=True):
                    st.markdown(f"**{item.get('factor')} — {item.get('level')}**")
                    st.write(item.get("atlas_interpretation"))
        else:
            st.info("No structured risk factors are currently available.")
        _render_interpretation(risk.get("interpretation", ""))

    with tabs[9]:
        st.markdown("### Final Atlas Guidance")
        plan = report.get("trade_plan") or {}
        horizon = (plan.get("horizon") or {}).get("primary", "Research / Monitor")
        st.info(
            f"Atlas currently classifies this as {str(report.get('committee_verdict') or 'Monitor').replace('_', ' ').title()} "
            f"with a primary horizon of {horizon}. Opportunity is {_score(report.get('opportunity_score'))}, "
            f"confidence is {_pct(report.get('confidence_pct'))}, and research completeness is "
            f"{_pct(report.get('research_completeness_pct'))}."
        )

        readiness = []
        for name, section in report["sections"].items():
            readiness.append(
                {
                    "Area": name.title(),
                    "Status": section.get("status"),
                    "Completeness": section.get("completeness_pct"),
                }
            )
        st.markdown("#### Research Readiness")
        st.dataframe(pd.DataFrame(readiness), hide_index=True, use_container_width=True)

        if report.get("enricher_errors"):
            st.warning(
                "Some optional live enrichers failed: "
                + "; ".join(str(error) for error in report["enricher_errors"])
            )

    with tabs[10]:
        _render_ai_intelligence(report)

    with tabs[11]:
        _render_ask_atlas(report)


__all__ = ["render_atlas_research_v2"]
