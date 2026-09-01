
"""
Atlas V2 Phase 1 — Unified Institutional Research Report
"""

from __future__ import annotations

from html import escape
from typing import Any, Mapping
import re

import pandas as pd
import streamlit as st
from engines.news_link_integrity import news_source_presentation

from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines.ask_atlas_engine import ask_atlas
from engines.semantic_fields import (
    is_missing_scalar, number, safe_date_text, safe_mapping,
    safe_scalar_display, safe_sequence,
)
from services.research_render_diagnostics import checkpoint
from services.policy_data import enrich_policy_for_research
from services.ai_valuation_synthesis import get_ai_valuation_for_research
from ui.vnext_presentation import CanonicalNumberFormatter


_QA_FAMILY_SECTION = {
    "profile": None,
    "financial_statements": "financials",
    "ratios_key_metrics": "financials",
    "growth_segments": "financials",
    "earnings_history": "earnings",
    "analyst_estimates": "analysts",
    "analyst_consensus_targets": "analysts",
    "analyst_actions": "analysts",
    "institutional_ownership": "ownership",
    "company_news": "news",
    "press_releases": "news",
    "sec_filings": None,
}


def _render_architecture_qa_markers(report: Mapping[str, Any]) -> None:
    """Emit identity/digest metadata only; never expose hidden financial data."""
    context = report.get("research_context") if isinstance(report.get("research_context"), Mapping) else {}
    families = context.get("evidence_families") if isinstance(context.get("evidence_families"), Mapping) else {}
    sections = report.get("sections") if isinstance(report.get("sections"), Mapping) else {}
    markers = []
    for family, section_name in _QA_FAMILY_SECTION.items():
        section = sections.get(section_name) if section_name else None
        displayed = family == "profile" or (
            isinstance(section, Mapping)
            and section.get("semantic_status") == "AVAILABLE"
        )
        envelope = families.get(family) if isinstance(families.get(family), Mapping) else {}
        markers.append(
            f'<span data-atlas-qa="research-rendered-family" '
            f'data-atlas-family="{escape(family)}" '
            f'data-atlas-displayed="{str(bool(displayed)).lower()}" '
            f'data-atlas-rendered-status="{escape(str((section or {}).get("semantic_status") or "DATA_UNAVAILABLE"))}" '
            f'data-atlas-provider="{escape(str(envelope.get("provider") or ""))}" '
            f'data-atlas-cache-status="{escape(str(envelope.get("cache_status") or ""))}" '
            f'data-atlas-render-source="legacy-report-adapter" aria-hidden="true" style="display:none">{escape(family)}</span>'
        )
    try:
        from agents.runtime_qa_architecture import stable_digest
        valuation = report.get("valuation_families") if isinstance(report.get("valuation_families"), Mapping) else {}
        value_markers = (
            ("atlas_fair_value", report.get("atlas_fair_value")),
            ("wall_street_target", valuation.get("analyst_target_mean")),
            ("analyst_target_range", (valuation.get("analyst_target_low"), valuation.get("analyst_target_high"))),
        )
        for role, value in value_markers:
            markers.append(
                f'<span data-atlas-qa="valuation-provenance" data-atlas-value-role="{role}" '
                f'data-atlas-value-present="{str(value is not None).lower()}" '
                f'data-atlas-value-digest="{stable_digest(value)}" aria-hidden="true" style="display:none">{role}</span>'
            )
    except Exception:
        pass
    st.markdown("".join(markers), unsafe_allow_html=True)


def _money(value: Any) -> str:
    return CanonicalNumberFormatter.currency(value).display


def _pct(value: Any, signed: bool = False) -> str:
    return CanonicalNumberFormatter.percent(value, signed=signed).display


def _score(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _customer_evidence_source(value: Any) -> str:
    """Translate internal feed provenance into a paid-client evidence label."""
    text = safe_scalar_display(value)
    lowered = text.lower()
    if "analyst" in lowered or "consensus" in lowered:
        return "Wall Street consensus evidence"
    if "earning" in lowered:
        return "Reported earnings evidence"
    if "ownership" in lowered:
        return "Ownership evidence"
    if any(name in lowered for name in ("yahoo", "finnhub", "fmp", "newsapi")):
        return "Atlas normalized research evidence"
    return text or "Atlas research evidence"


def _clean_prose(value: Any) -> str:
    """Normalize generated prose so Markdown cannot create accidental code pills."""
    text = safe_scalar_display(value).replace("`", "")
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


def _policy_status_label(value: Any) -> str:
    return str(value or "INSUFFICIENT_VERIFIED_EVIDENCE").replace("_", " ").title()


def _load_policy_enrichment(symbol: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Failure-safe boundary for optional explicit-ticker policy enrichment."""
    if not symbol:
        return {"government_contract_evidence": [], "metrics": {"provider_call_count": 0}}
    try:
        return enrich_policy_for_research(symbol, row)
    except Exception:
        return {
            "government_contract_evidence": [],
            "metrics": {"provider_call_count": 0, "failure_count": 1},
        }


def _load_ai_valuation(symbol: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Failure-safe, explicit-ticker boundary for research-only AI valuation."""
    if not symbol:
        return {}
    try:
        return get_ai_valuation_for_research(symbol, row)
    except Exception:
        return {
            "ticker": symbol, "ai_valuation_status": "UNDER_REVIEW",
            "ai_bear_value": None, "ai_base_value": None, "ai_bull_value": None,
            "ai_evidence_gaps": ["ATLAS AI Valuation is temporarily unavailable."],
            "ai_validation_status": "NOT_PUBLISHED",
        }


def _render_hybrid_valuation(report: Mapping[str, Any]) -> None:
    st.markdown("## ATLAS Valuation")
    current = report.get("current_price")
    quant = report.get("atlas_fair_value")
    top = st.columns(3)
    top[0].metric("Current Price", _money(current))
    if quant is None:
        top[1].metric("Atlas Quant Fair Value", "Not published")
        top[2].metric("Quant-FV Implied Upside", "Unavailable")
    else:
        top[1].metric("Atlas Quant Fair Value", _money(quant))
        top[2].metric("Quant-FV Implied Upside", _pct(report.get("atlas_fv_upside_pct"), signed=True))

    ai = report.get("ai_valuation") or {}
    st.markdown("### ATLAS AI Valuation")
    if ai.get("ai_valuation_status") != "PUBLISHED":
        if ai.get("ai_valuation_status") == "INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE":
            st.info(
                "Under Review — Atlas has sufficient company-level financial evidence for AI valuation analysis, "
                "but an independently calibrated justified-multiple framework is not yet available."
            )
        else:
            gaps = ai.get("ai_evidence_gaps") or []
            explanation = gaps[0] if gaps else "The AI valuation evidence gate has not been satisfied."
            st.info(f"Not published — {explanation}")
    else:
        values = st.columns(3)
        values[0].metric("AI Bear Value", _money(ai.get("ai_bear_value")))
        values[1].metric("AI Base Value", _money(ai.get("ai_base_value")))
        values[2].metric("AI Bull Value", _money(ai.get("ai_bull_value")))
        detail = st.columns(3)
        detail[0].metric("AI Base Implied Upside", _pct(ai.get("ai_base_upside_pct"), signed=True))
        confidence = ai.get("ai_valuation_confidence") or {}
        detail[1].metric("Deterministic Confidence", f"{confidence.get('band', 'Unavailable')} · {confidence.get('score', 0):.1f}%")
        detail[2].metric("Valuation Horizon", ai.get("ai_valuation_horizon") or "12–18 months")
        with st.expander("AI valuation method, assumptions, and evidence"):
            st.write(ai.get("ai_method_rationale") or "Method rationale unavailable.")
            st.write("Method: " + str(ai.get("ai_valuation_method") or "Unavailable").replace("_", " ").title())
            if ai.get("ai_assumptions"):
                st.dataframe(pd.DataFrame(ai["ai_assumptions"]), hide_index=True, use_container_width=True)
            if ai.get("ai_evidence_gaps"):
                st.caption("Evidence gaps: " + "; ".join(ai["ai_evidence_gaps"]))
    relationship = str(ai.get("valuation_relationship") or "COMPARISON_UNAVAILABLE").replace("_", " ").title()
    st.markdown("### Valuation Agreement")
    st.caption(f"{relationship}. Phase 7A comparison thresholds are provisional and research-only.")


def _render_policy_intelligence(policy: Mapping[str, Any]) -> None:
    st.markdown("### Policy & Government Intelligence")
    status = str(policy.get("policy_overall_status") or "INSUFFICIENT_VERIFIED_EVIDENCE")
    st.markdown(f"**Overall Policy Exposure:** {_policy_status_label(status)}")
    if status == "INSUFFICIENT_VERIFIED_EVIDENCE":
        st.info("Atlas does not currently have enough verified company-specific policy evidence to classify this exposure.")
        return
    labels = (
        ("Government Exposure", "government_contract_evidence"),
        ("Regulatory Exposure", "regulatory_evidence"),
        ("Trade / Tariff Exposure", "trade_tariff_evidence"),
        ("Export Controls / Sanctions", "export_control_evidence"),
        ("Lobbying Activity", "lobbying_evidence"),
    )
    st.markdown("#### Key Policy Factors")
    shown = 0
    for label, key in labels:
        items = policy.get(key) or []
        if not items:
            continue
        st.markdown(f"**{label}**")
        st.write(items[0].get("fact"))
    developments = []
    for key in (
        "government_contract_evidence", "regulatory_evidence",
        "trade_tariff_evidence", "export_control_evidence",
        "legislative_policy_evidence", "public_funding_evidence", "policy_news",
    ):
        developments.extend(policy.get(key) or [])
    if developments:
        st.markdown("#### Recent Material Developments")
    for item in developments[:5]:
        with st.container(border=True):
            st.markdown(f"**What happened:** {escape(str(item.get('fact') or 'Evidence unavailable'))}")
            if item.get("why_it_matters"):
                st.write(f"Why it matters: {item['why_it_matters']}")
            details = " · ".join(str(value) for value in (
                item.get("event_date"), item.get("authority"), item.get("relevance_status")
            ) if value)
            if details:
                st.caption(details)
            shown += 1
    if not shown and status != "INSUFFICIENT_VERIFIED_EVIDENCE":
        st.caption("No current material development cards are available.")


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
        .atlas-analyst-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
            gap: .8rem;
            margin: .7rem 0 1.1rem;
        }
        .atlas-analyst-card, .atlas-action-card {
            min-width: 0;
            border: 1px solid rgba(120, 155, 205, .28);
            border-radius: 16px;
            padding: 1rem;
            background: rgba(16, 30, 50, .72);
            overflow-wrap: anywhere;
        }
        .atlas-analyst-label { color:#aebbd0; font-size:.76rem; text-transform:uppercase; letter-spacing:.07em; }
        .atlas-analyst-value { color:#f8faff; font-size:1.35rem; font-weight:800; margin-top:.25rem; }
        .atlas-action-list { display:grid; gap:.7rem; }
        @media (max-width: 900px) {
            .atlas-analyst-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .atlas-action-list { grid-template-columns: 1fr; }
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


def _analyst_intelligence_html(intelligence: Mapping[str, Any]) -> str:
    """Build responsive customer-facing analyst cards with optional data omitted."""
    metrics = [
        ("Wall Street Consensus", _money(intelligence.get("wall_street_mean_target"))),
        ("Wall Street Implied Upside", _pct(intelligence.get("wall_street_implied_upside_pct"), signed=True)),
        ("Analyst Coverage", intelligence.get("analyst_coverage")),
        ("Analyst Agreement", intelligence.get("analyst_agreement")),
    ]
    if intelligence.get("wall_street_median_target") is not None:
        metrics.append(("Median Target", _money(intelligence.get("wall_street_median_target"))))
    cards = "".join(
        f'<div class="atlas-analyst-card"><div class="atlas-analyst-label">{escape(str(label))}</div>'
        f'<div class="atlas-analyst-value">{escape(safe_scalar_display(value))}</div></div>'
        for label, value in metrics
        if not isinstance(value, (Mapping, list, tuple, set, frozenset))
        and not is_missing_scalar(value)
    )
    return f'<div class="atlas-analyst-grid">{cards}</div>'


def _divergence_disclosure(report: Mapping[str, Any]) -> str | None:
    analyst = report.get("analyst_intelligence") or {}
    verdict = str(report.get("committee_verdict") or "").upper().replace(" ", "_")
    atlas_upside = analyst.get("atlas_fv_upside_pct")
    street_upside = analyst.get("wall_street_implied_upside_pct")
    if verdict != "BUY_NOW" or atlas_upside is None or street_upside is None or not (atlas_upside < 0 < street_upside):
        return None
    return (
        "**ATLAS / STREET DIVERGENCE**\n\n"
        f"Atlas's independent valuation indicates {abs(float(atlas_upside)):.1f}% downside, while Wall Street "
        f"consensus indicates {float(street_upside):.1f}% upside. The current BUY NOW decision is supported "
        "by other components of the existing Atlas decision model."
    )


def _render_analyst_intelligence(intelligence: Mapping[str, Any]) -> None:
    intelligence = safe_mapping(intelligence)
    st.markdown("## Wall Street Analyst Intelligence")
    st.markdown(_analyst_intelligence_html(intelligence), unsafe_allow_html=True)
    low, high = intelligence.get("wall_street_low_target"), intelligence.get("wall_street_high_target")
    if low is not None and high is not None:
        st.markdown("### Target Range")
        st.write(f"{_money(low)} — {_money(high)}")
        if intelligence.get("target_dispersion_pct") is not None:
            st.caption(f"Dispersion: {_pct(intelligence.get('target_dispersion_pct'))}")
    response_count = number(intelligence.get("recommendation_response_count"))
    sentiment_counts = [number(intelligence.get(key)) for key in (
        "strong_buy_count", "buy_count", "hold_count", "sell_count", "strong_sell_count",
    )]
    sentiment_pcts = [number(intelligence.get(key)) for key in ("bullish_pct", "neutral_pct", "bearish_pct")]
    if response_count is not None and all(value is not None for value in sentiment_counts + sentiment_pcts):
        labels = ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")
        st.markdown("### Analyst Sentiment")
        st.write(" | ".join(labels))
        st.write(" | ".join(str(int(value)) for value in sentiment_counts))
        st.caption(
            f"{sentiment_pcts[0]:.1f}% Bullish · {sentiment_pcts[1]:.1f}% Neutral · "
            f"{sentiment_pcts[2]:.1f}% Bearish · Latest recommendation responses"
        )
    actions = [item for item in safe_sequence(intelligence.get("recent_actions")) if isinstance(item, Mapping)]
    if actions:
        st.markdown("### Analyst Trend")
        trend_cols = st.columns(2)
        for col, days in zip(trend_cols, (30, 90)):
            trend = safe_mapping(intelligence.get(f"trend_{days}d"))
            col.metric(f"{days} Days", trend.get("classification", "STABLE"))
            col.caption(f"{trend.get('positive', 0)} positive · {trend.get('negative', 0)} negative · {trend.get('neutral', 0)} neutral")
        st.markdown("### Recent Analyst Actions")
        action_html = []
        for action in actions:
            target_text = ""
            if action.get("current_target") is not None and action.get("previous_target") is not None:
                target_text = f"Target {_money(action['previous_target'])} → {_money(action['current_target'])}<br>"
            elif action.get("current_target") is not None:
                target_text = f"Target {_money(action['current_target'])}<br>"
            rating = escape(str(action.get("current_rating") or action.get("primary_action") or "Action"))
            action_html.append(
                '<div class="atlas-action-card">'
                f'<strong>{escape(str(action.get("firm") or "Firm"))}</strong><br>{rating}<br>{target_text}'
                f'{escape(str(action.get("primary_action") or ""))} · {escape(str(action.get("date") or "")[:10])}'
                '</div>'
            )
        st.markdown(f'<div class="atlas-action-list">{"".join(action_html)}</div>', unsafe_allow_html=True)
        all_actions = [item for item in safe_sequence(intelligence.get("all_actions")) if isinstance(item, Mapping)]
        if len(all_actions) > len(actions):
            with st.expander("View all analyst actions"):
                for action in all_actions:
                    date_text = safe_date_text(action.get("date")) or ""
                    st.write(f"{date_text[:10]} · {safe_scalar_display(action.get('firm'), 'Firm')} · {safe_scalar_display(action.get('primary_action'), 'Action')}")
    st.markdown("### Atlas vs Wall Street")
    atlas_value = intelligence.get("atlas_fair_value")
    street_value = intelligence.get("wall_street_mean_target")
    available_values = []
    if atlas_value is not None:
        available_values.append(("Atlas Fair Value", _money(atlas_value)))
    if street_value is not None:
        available_values.append(("Wall Street Consensus", _money(street_value)))
    if available_values:
        compare = st.columns(len(available_values))
        for column, (label, value) in zip(compare, available_values):
            column.metric(label, value)
    st.markdown(f"**{intelligence.get('atlas_street_relationship', 'VALUATION COMPARISON UNAVAILABLE')}**")
    st.write(intelligence.get("atlas_street_divergence_message") or "")


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
    data = safe_mapping(data)
    money_keys = money_keys or set()
    pct_keys = pct_keys or set()
    scalar = [
        (key, value)
        for key, value in data.items()
        if not isinstance(value, (Mapping, list, tuple, set, frozenset)) and not is_missing_scalar(value)
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
        evidence_ids = result.get("evidence_ids_used") or []
        missing = result.get("evidence_missing") or []
        st.caption(
            f"Mode: {result.get('mode', 'Unknown')} · "
            f"Ticker: {result.get('ticker', ticker)} · "
            f"Section: {result.get('section', 'overview')} · "
            f"Atlas sections used: {', '.join(sources) if sources else 'None'} · "
            f"Report generated: {result.get('generated_at') or result.get('generated_from', 'Unknown')} · "
            f"Evidence IDs: {', '.join(evidence_ids) if evidence_ids else 'None'} · "
            f"Evidence missing: {', '.join(missing) if missing else 'None'} · "
            f"Evidence as of: {result.get('as_of_date') or 'Unavailable'} · "
            f"Framework: {result.get('framework_version', 'Unknown')}"
        )

def render_atlas_research_v2(row: Mapping[str, Any]) -> None:
    checkpoint("render_atlas_research_v2:before")
    # Compatibility entry point only. The legacy implementation remains below
    # for rollback/migration reference, but the active customer path always
    # resolves UX-2 dynamically and returns before the twelve-tab baseline.
    from ui.research_vnext import render_full_research_vnext
    render_full_research_vnext(row)
    checkpoint("render_atlas_research_v2:after")
    return

    research_row = dict(row)
    symbol = str(research_row.get("ticker") or research_row.get("Ticker") or "").strip().upper()
    canonical_context = research_row.get("research_context") if isinstance(research_row.get("research_context"), Mapping) else {}
    canonical_families = canonical_context.get("evidence_families") if isinstance(canonical_context.get("evidence_families"), Mapping) else {}
    action_family = canonical_families.get("analyst_actions") if isinstance(canonical_families.get("analyst_actions"), Mapping) else {}
    canonical_actions = ((action_family.get("data") or {}).get("actions") or []) if isinstance(action_family.get("data"), Mapping) else []
    # FIRST.3 canonical actions are authoritative for explicit Research.  Do not
    # reacquire or overwrite them with the legacy Yahoo action adapter.
    retrieval = {
        "actions": canonical_actions,
        "cache_hit": action_family.get("cache_status") in {"FRESH_CACHE", "STALE_FALLBACK"},
        "retrieval_seconds": 0.0,
        "request_count": 0,
        "provider": action_family.get("provider"),
        "fallback_reason": action_family.get("fallback_reason"),
    }
    research_row["analyst_actions"] = canonical_actions
    policy_retrieval = _load_policy_enrichment(symbol, research_row)
    research_row["policy_intelligence_external"] = policy_retrieval
    research_row["ai_valuation_external"] = _load_ai_valuation(symbol, research_row)
    checkpoint("build_atlas_research_v2:call")
    report = build_atlas_research_v2(research_row)
    checkpoint("build_atlas_research_v2:return")
    report["analyst_action_retrieval"] = retrieval
    report["policy_source_metrics"] = policy_retrieval.get("metrics") or {}
    _inject_visual_standards()
    _render_architecture_qa_markers(report)

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

    # UX-2 replaces the V1 twelve-tab presentation baseline. The canonical
    # builder and every evidence object above remain unchanged; only their
    # customer-facing hierarchy is migrated into five decision sections.
    from ui.research_vnext import render_research_vnext
    render_research_vnext(
        report,
        legacy={
            "valuation": _render_hybrid_valuation,
            "analyst": _render_analyst_intelligence,
            "meta": _meta,
            "metric_grid": _metric_grid,
            "interpretation": _render_interpretation,
            "trade_plan": _render_trade_plan,
            "price_chart": _render_price_chart,
            "policy": _render_policy_intelligence,
        },
    )
    checkpoint("render_atlas_research_v2:after")
    return

    c = st.columns(5)
    c[0].metric("Verdict", str(report.get("committee_verdict") or "Monitor").replace("_", " ").title())
    c[1].metric("Opportunity", _score(report.get("opportunity_score")))
    c[2].metric("Confidence", _pct(report.get("confidence_pct")))
    c[3].metric("Atlas-FV Implied Upside", _pct(report.get("atlas_expected_return_pct"), signed=True))
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
    analyst = report.get("analyst_intelligence") or {}
    disclosure = _divergence_disclosure(report)
    if disclosure:
        st.warning(disclosure)
    checkpoint("valuation_render:before")
    _render_hybrid_valuation(report)
    checkpoint("valuation_render:after")
    checkpoint("analyst_render:before")
    _render_analyst_intelligence(analyst)
    checkpoint("analyst_render:after")
    support_col, risk_col = st.columns(2)
    with support_col:
        st.markdown("### Why")
        for item in guidance.get("supporting_facts") or []:
            st.success(f"{item.get('fact')} {item.get('why_it_matters')}")
            st.caption(f"Source: {_customer_evidence_source(item.get('source'))} · As of: {item.get('as_of')}")
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
    checkpoint("earnings_render:before")
    earnings_brief = report.get("earnings_summary") or {}
    st.markdown("### Earnings Intelligence")
    if earnings_brief.get("semantic_status") == "AVAILABLE":
        st.write(earnings_brief.get("summary"))
    elif earnings_brief.get("semantic_status") == "NOT_APPLICABLE":
        st.caption("Corporate Earnings Intelligence is not applicable to this ETF.")
    else:
        st.caption("Reported earnings history is unavailable for a grounded trend assessment.")
    checkpoint("earnings_render:after")
    checkpoint("research_tabs_render:before")
    tabs = st.tabs(
        [
            "Thesis",
            "Growth & Profitability",
            "Earnings Intelligence",
            "Risk",
            "Catalysts & Company News",
            "Ownership",
            "Political Intelligence Boundary",
            "Earnings Call Boundary",
            "Chart & Technicals",
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
        intelligence = report.get("earnings_intelligence") or {}
        summary = report.get("earnings_summary") or {}
        st.markdown("### Deterministic Earnings Intelligence")
        _meta(section)
        latest = intelligence.get("latest_quarter") or {}
        if intelligence.get("semantic_status") == "AVAILABLE":
            metrics = st.columns(4)
            metrics[0].metric("Latest quarter", latest.get("fiscal_period") or latest.get("report_date") or "Unavailable")
            metrics[1].metric("Quarter result", intelligence.get("latest_quarter_classification") or "Unavailable")
            metrics[2].metric("Consecutive EPS beats", intelligence.get("consecutive_eps_beats", 0))
            metrics[3].metric("Consecutive revenue beats", intelligence.get("consecutive_revenue_beats", 0))
            st.write(summary.get("what_happened"))
            st.write(summary.get("trend_assessment"))
            st.info(summary.get("watch_next"))
        elif intelligence.get("semantic_status") == "NOT_APPLICABLE":
            st.info("Corporate Earnings Intelligence is not applicable to this ETF.")
        else:
            st.info("No structured multi-quarter earnings history is attached to this stock row.")

        history = intelligence.get("history") or []
        st.markdown("#### Previous Earnings History")
        if history:
            st.dataframe(pd.DataFrame(history), hide_index=True, use_container_width=True)
        else:
            st.info("No structured multi-quarter earnings history is attached to this stock row.")
        guidance_object = report.get("management_guidance") or {}
        st.markdown("#### Management Guidance")
        if guidance_object.get("semantic_status") == "AVAILABLE":
            st.json({key: value for key, value in guidance_object.items() if key not in {"version", "semantic_status"}})
        else:
            st.caption(guidance_object.get("status_detail") or "Management guidance is unavailable.")

    with tabs[3]:
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

    checkpoint("news_render:before")
    with tabs[4]:
        section = report["sections"]["news"]
        st.markdown("### Company News Intelligence")
        _meta(section)
        items = section.get("data") or []
        if not items:
            st.info("No recent high-confidence company-specific news available.")
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
                source_link = news_source_presentation(item)
                if source_link["href"]:
                    st.markdown(f"[Open verified source]({source_link['href']})")
                else:
                    st.caption(f"Source: {source_link['source']} · {source_link['limitation']}")
                if item.get("relevance"):
                    st.caption(f"Relevance: {item['relevance']} · Category: {item.get('classification', 'Other Company-Specific')}")
                if item.get("impact") is not None:
                    st.metric("Materiality / Impact", _score(item["impact"]))
        _render_interpretation(section.get("interpretation", ""))

    checkpoint("news_render:after")
    with tabs[6]:
        section = report["sections"]["political"]
        data = section.get("data") or report.get("policy_intelligence") or {}
        _render_policy_intelligence(data)
        transactions = data.get("policymaker_transactions") or []
        if transactions:
            st.markdown("#### Policymaker Transactions")
            st.caption("Transactions are disclosure evidence, not policy support or government endorsement.")
            st.dataframe(pd.DataFrame(transactions), hide_index=True, use_container_width=True)

    checkpoint("ownership_render:before")
    with tabs[5]:
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

    checkpoint("ownership_render:after")
    checkpoint("technicals_render:before")
    with tabs[8]:
        section = report["sections"]["technical"]
        st.markdown("### Technical Intelligence")
        _meta(section)
        _metric_grid(
            section.get("data") or {},
            money_keys={"price", "sma20", "sma50", "sma200", "support", "resistance"},
        )
        _render_price_chart(report)
        _render_interpretation(section.get("interpretation", ""))

    checkpoint("technicals_render:after")
    with tabs[7]:
        st.markdown("### Earnings Call / Transcript Intelligence")
        transcript = report.get("transcript_intelligence") or {}
        if transcript.get("semantic_status") == "AVAILABLE":
            st.json({key: value for key, value in transcript.items() if key not in {"version", "semantic_status"}})
        else:
            st.info(transcript.get("status_detail") or "Transcript intelligence not yet available.")

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

    _render_trade_plan(report)
    checkpoint("research_tabs_render:after")
    checkpoint("render_atlas_research_v2:after")


__all__ = ["render_atlas_research_v2"]
