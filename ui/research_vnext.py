"""ATLAS VNext UX-2 Research decision dossier.

Presentation only: this module consumes an already-built canonical Research
report.  It never calculates recommendations, scores, valuation, technical
states, or trade levels.
"""

from __future__ import annotations

from html import escape
from typing import Any, Callable, Final, Mapping

import pandas as pd
import streamlit as st

from engines.semantic_fields import is_missing_scalar, safe_mapping, safe_sequence
from ui.vnext_presentation import (
    AvailabilityState, CanonicalNumberFormatter, decision_header,
    evidence_drawer, evidence_health, monitor_technical_scenario,
    price_action_strip, primary_evidence_pair, technical_state_badge,
)


RESEARCH_VNEXT_VERSION: Final = "ATLAS_RESEARCH_VNEXT_UX2"
RESEARCH_VNEXT_SECTIONS: Final = (
    "Decision",
    "Fundamentals & Valuation",
    "Technical & Trade State",
    "Catalysts & Sentiment",
    "Risk & Evidence",
)

# Explicit migration ledger. Values are the sole primary destination; detailed
# evidence may also be cross-referenced from Decision without becoming a second
# source of truth.
RESEARCH_EVIDENCE_MIGRATION: Final = {
    "Executive Summary": "Decision",
    "Investment Thesis": "Decision",
    "Bull Case": "Decision",
    "Bear Case": "Decision",
    "Final Atlas Guidance": "Decision",
    "Recommendation / Verdict": "Decision",
    "Evidence-gap warning": "Decision",
    "Strengthen / Weaken / Invalidate": "Decision",
    "What happens next": "Decision",
    "Atlas Quant FV": "Fundamentals & Valuation",
    "Atlas-FV upside": "Fundamentals & Valuation",
    "AI valuation method / assumptions": "Fundamentals & Valuation",
    "Valuation agreement": "Fundamentals & Valuation",
    "Wall Street consensus / range": "Fundamentals & Valuation",
    "Atlas vs Wall Street": "Fundamentals & Valuation",
    "Financial metrics / interpretation": "Fundamentals & Valuation",
    "Earnings history / trend": "Fundamentals & Valuation",
    "Deterministic technical state": "Technical & Trade State",
    "Current price / entry / targets / stop": "Technical & Trade State",
    "Risk reward / horizon / position guidance": "Technical & Trade State",
    "Technical metrics / interpretation": "Technical & Trade State",
    "Historical price chart / records": "Technical & Trade State",
    "Company news / materiality": "Catalysts & Sentiment",
    "Analyst sentiment / trend / actions": "Catalysts & Sentiment",
    "Earnings and event watch": "Catalysts & Sentiment",
    "Management guidance": "Catalysts & Sentiment",
    "Policy developments": "Catalysts & Sentiment",
    "Today's move explanation": "Catalysts & Sentiment",
    "Transcript intelligence": "Catalysts & Sentiment",
    "Risk factors / interpretation": "Risk & Evidence",
    "Research readiness": "Risk & Evidence",
    "Ownership / major holders / insiders": "Risk & Evidence",
    "Political transaction evidence": "Risk & Evidence",
    "Score attribution": "Risk & Evidence",
    "Provenance / evidence IDs / freshness": "Risk & Evidence",
    "AI assumptions / evidence gaps": "Risk & Evidence",
    "Limitations / stale / unavailable states": "Risk & Evidence",
    "Disclosures": "Risk & Evidence",
    "Ask Atlas AI tab": "Persistent contextual CTA",
}


def _scalar_text(value: Any, fallback: str = "Unavailable") -> str:
    if isinstance(value, (Mapping, list, tuple, set, frozenset)) or is_missing_scalar(value):
        return fallback
    return str(value).strip()


def _first_mapping_item(value: Any) -> Mapping[str, Any]:
    for item in safe_sequence(value):
        if isinstance(item, Mapping):
            return item
    return {}


def _technical_state(report: Mapping[str, Any]) -> Any:
    section = safe_mapping(safe_mapping(report.get("sections")).get("technical"))
    data = safe_mapping(section.get("data"))
    for key in ("technical_state", "state", "setup_state", "breakout_state"):
        if key in data and not is_missing_scalar(data.get(key)):
            return data.get(key)
    for key in ("technical_state", "technical_intelligence_state"):
        if key in report and not is_missing_scalar(report.get(key)):
            return report.get(key)
    return None


def _canonical_context(report: Mapping[str, Any]) -> Mapping[str, Any]:
    return safe_mapping(report.get("research_context"))


def _critical_gaps(report: Mapping[str, Any]) -> tuple[str, ...]:
    guidance = safe_mapping(report.get("guidance_summary"))
    gaps = [_scalar_text(item, "") for item in safe_sequence(guidance.get("unavailable_evidence"))]
    context = _canonical_context(report)
    gaps.extend(_scalar_text(item, "") for item in safe_sequence(context.get("limitations")))
    return tuple(dict.fromkeys(item for item in gaps if item))


def _freshness(report: Mapping[str, Any]) -> tuple[str, str | None]:
    families = safe_mapping(_canonical_context(report).get("evidence_families"))
    statuses = {
        str(safe_mapping(envelope).get("cache_status") or "")
        for envelope in families.values()
        if isinstance(envelope, Mapping)
    }
    if "STALE_FALLBACK" in statuses:
        return "STALE_FALLBACK", "STALE_FALLBACK"
    if statuses & {"FETCHED", "REFRESHED", "FRESH_CACHE"}:
        return "AVAILABLE", "Fresh / cached evidence"
    return "DATA_UNAVAILABLE", None


def build_research_decision_view(report: Mapping[str, Any]) -> dict[str, Any]:
    """Build a non-mutating presentation model from canonical report values."""
    guidance = safe_mapping(report.get("guidance_summary"))
    action = safe_mapping(guidance.get("action_now"))
    plan = safe_mapping(report.get("trade_plan"))
    support_item = _first_mapping_item(guidance.get("supporting_facts"))
    risk_item = _first_mapping_item(guidance.get("key_risks"))
    support = " ".join(filter(None, (
        _scalar_text(support_item.get("fact"), ""),
        _scalar_text(support_item.get("why_it_matters"), ""),
    ))) or _scalar_text((safe_sequence(report.get("bull_case")) or [None])[0])
    risk = " ".join(filter(None, (
        _scalar_text(risk_item.get("risk"), ""),
        _scalar_text(risk_item.get("consequence"), ""),
    ))) or _scalar_text((safe_sequence(report.get("bear_case")) or [None])[0])
    completeness = report.get("research_completeness_pct")
    verdict = _scalar_text(report.get("committee_verdict"), "Monitor")
    try:
        materially_incomplete = completeness is None or float(completeness) < 70.0
    except (TypeError, ValueError):
        materially_incomplete = True
    monitor = verdict.upper().replace(" ", "_") in {"MONITOR", "WATCH", "RESEARCH_/_MONITOR"} or materially_incomplete
    status, cache_status = _freshness(report)
    gaps = _critical_gaps(report)
    health = evidence_health(
        semantic_status=status,
        cache_status=cache_status,
        completeness_pct=completeness,
        limitations=gaps,
    )
    header = decision_header(
        recommendation=report.get("committee_verdict"),
        opportunity=report.get("opportunity_score"),
        confidence=report.get("confidence_pct"),
        research_completeness=completeness,
        actionability_label="Monitor — Not currently actionable" if monitor else _scalar_text(action.get("current_action"), verdict.replace("_", " ").title()),
    )
    prices = price_action_strip(
        current_price=plan.get("current_price", report.get("current_price")),
        entry_low=plan.get("entry_low"), entry_high=plan.get("entry_high"),
        invalidation=plan.get("stop_loss"),
    )
    evidence = primary_evidence_pair(support=support, contradiction_or_risk=risk)
    change = report.get("change_since_last_scan") or report.get("material_change")
    if isinstance(change, (Mapping, list, tuple, set, frozenset)):
        change = None
    return {
        "header": header, "prices": prices, "evidence": evidence,
        "health": health, "technical_badge": technical_state_badge(_technical_state(report)),
        "monitor_or_incomplete": monitor, "critical_gaps": gaps,
        "material_change": _scalar_text(change, "") or None,
    }


def _section_marker(name: str, ticker: str) -> None:
    slug = name.lower().replace("&", "and").replace("/", "-").replace(" ", "-")
    st.markdown(
        f'<span data-atlas-qa="research-vnext-section" data-atlas-section="{escape(slug)}" '
        f'data-atlas-ticker="{escape(ticker)}" data-atlas-rendered="true" '
        'aria-hidden="true" style="display:none">research-vnext-section</span>',
        unsafe_allow_html=True,
    )


def _render_metric(label: str, display: str, *, help_text: str | None = None) -> None:
    st.metric(label, display, help=help_text)


def _render_decision(report: Mapping[str, Any], view: Mapping[str, Any]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN")
    _section_marker("Decision", ticker)
    header = view["header"]
    badge = view["technical_badge"]
    st.markdown("## Decision")
    st.markdown(f"### {header.actionability_label}")
    columns = st.columns(5)
    columns[0].metric("ATLAS State", _scalar_text(header.recommendation, "Monitor").replace("_", " ").title())
    columns[1].metric("Opportunity", _scalar_text(header.opportunity))
    columns[2].metric("Confidence", CanonicalNumberFormatter.percent(header.confidence).display)
    columns[3].metric("Research Completeness", CanonicalNumberFormatter.percent(header.research_completeness).display)
    columns[4].metric("Technical State", badge.label)

    prices = view["prices"]
    price_cols = st.columns(4)
    price_cols[0].metric("Current Price", prices.current_price.display)
    entry = (
        f"{prices.entry_low.display}–{prices.entry_high.display}"
        if prices.entry_low.exact_value is not None and prices.entry_high.exact_value is not None
        else "Unavailable"
    )
    price_cols[1].metric("Preferred Action Zone", entry)
    price_cols[2].metric("Supported Upside", CanonicalNumberFormatter.percent(report.get("atlas_expected_return_pct"), signed=True).display)
    price_cols[3].metric("Downside / Invalidation", prices.invalidation.display)

    evidence = view["evidence"]
    support_col, risk_col = st.columns(2)
    with support_col:
        st.markdown("#### Strongest support")
        st.success(evidence.support)
    with risk_col:
        st.markdown("#### Strongest contradiction / primary risk")
        st.warning(evidence.contradiction_or_risk)

    if view.get("material_change"):
        st.markdown("#### What changed")
        st.info(view["material_change"])

    health = view["health"]
    st.caption(
        f"Evidence: {health.label} · Completeness: {health.completeness.display} · "
        f"Freshness: {health.freshness or 'Unavailable'}"
    )
    if view["critical_gaps"]:
        st.warning("Missing critical evidence: " + "; ".join(view["critical_gaps"][:4]))

    guidance = safe_mapping(report.get("guidance_summary"))
    catalyst = safe_mapping(guidance.get("next_catalyst"))
    st.markdown("#### What happens next")
    st.write(
        _scalar_text(catalyst.get("event"), "No verified next catalyst is available")
        + (f" — {_scalar_text(catalyst.get('date'), '')}" if catalyst.get("date") else "")
        + (f". {_scalar_text(catalyst.get('what_atlas_will_watch'), '')}" if catalyst.get("what_atlas_will_watch") else "")
    )
    changes = safe_mapping(guidance.get("thesis_change_conditions"))
    with st.expander("What strengthens, weakens, or invalidates the thesis", expanded=False):
        for label in ("strengthen", "weaken", "invalidate"):
            st.markdown(f"**{label.title()}**")
            items = safe_sequence(changes.get(label))
            if items:
                for item in items:
                    st.write(f"- {_scalar_text(item)}")
            else:
                st.caption("No grounded condition is populated.")
    with st.expander("Long-form thesis and decision evidence", expanded=False):
        st.markdown("#### Executive Summary")
        st.write(_scalar_text(report.get("executive_summary"), "No grounded executive summary is currently available."))
        st.markdown("#### Investment Thesis")
        st.write(_scalar_text(report.get("source_investment_thesis") or report.get("investment_thesis"), "No grounded thesis is currently available."))
        bull, bear = st.columns(2)
        with bull:
            st.markdown("**Bull Case**")
            for item in safe_sequence(report.get("bull_case")):
                st.success(_scalar_text(item))
        with bear:
            st.markdown("**Bear Case**")
            for item in safe_sequence(report.get("bear_case")):
                st.warning(_scalar_text(item))


def _render_fundamentals(report: Mapping[str, Any], legacy: Mapping[str, Callable[..., Any]]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN")
    _section_marker("Fundamentals & Valuation", ticker)
    st.markdown("## Fundamentals & Valuation")
    legacy["valuation"](report)
    analyst = safe_mapping(report.get("analyst_intelligence"))
    st.markdown("### Wall Street comparison — separate methodology")
    st.caption("Wall Street consensus is external analyst evidence and is not a substitute for Atlas Fair Value.")
    cols = st.columns(3)
    cols[0].metric("Wall Street Consensus", CanonicalNumberFormatter.price(analyst.get("wall_street_mean_target")).display)
    cols[1].metric("Wall Street Implied Upside", CanonicalNumberFormatter.percent(analyst.get("wall_street_implied_upside_pct"), signed=True).display)
    cols[2].metric("Analyst Coverage", CanonicalNumberFormatter.count(analyst.get("analyst_coverage")).display)
    st.write(_scalar_text(analyst.get("atlas_street_divergence_message"), "Valuation comparison unavailable."))

    financials = safe_mapping(safe_mapping(report.get("sections")).get("financials"))
    st.markdown("### Financial Intelligence")
    legacy["meta"](financials)
    legacy["metric_grid"](
        safe_mapping(financials.get("data")),
        money_keys={"free_cash_flow", "cash", "debt"},
        pct_keys={"revenue_growth_pct", "eps_growth_pct", "gross_margin_pct", "operating_margin_pct", "net_margin_pct", "roe_pct", "roic_pct"},
    )
    legacy["interpretation"](_scalar_text(financials.get("interpretation"), ""))

    earnings = safe_mapping(safe_mapping(report.get("sections")).get("earnings"))
    intelligence = safe_mapping(report.get("earnings_intelligence"))
    st.markdown("### Earnings trend")
    if intelligence.get("semantic_status") == "NOT_APPLICABLE":
        st.info("Corporate Earnings Intelligence is not applicable to this ETF.")
    elif intelligence.get("semantic_status") == "AVAILABLE":
        latest = safe_mapping(intelligence.get("latest_quarter"))
        metrics = st.columns(4)
        metrics[0].metric("Latest quarter", _scalar_text(latest.get("fiscal_period") or latest.get("report_date")))
        metrics[1].metric("Quarter result", _scalar_text(intelligence.get("latest_quarter_classification")))
        metrics[2].metric("Consecutive EPS beats", _scalar_text(intelligence.get("consecutive_eps_beats")))
        metrics[3].metric("Consecutive revenue beats", _scalar_text(intelligence.get("consecutive_revenue_beats")))
        summary = safe_mapping(report.get("earnings_summary"))
        st.write(_scalar_text(summary.get("trend_assessment") or summary.get("summary")))
    else:
        st.info("Reported earnings history is unavailable for a grounded trend assessment.")
    with st.expander("Detailed earnings history", expanded=False):
        history = safe_sequence(intelligence.get("history"))
        if history:
            st.dataframe(pd.DataFrame(history), hide_index=True, use_container_width=True)
        else:
            st.info("No structured multi-quarter earnings history is attached.")
        legacy["meta"](earnings)


def _render_technical(report: Mapping[str, Any], view: Mapping[str, Any], legacy: Mapping[str, Callable[..., Any]]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN")
    _section_marker("Technical & Trade State", ticker)
    st.markdown("## Technical & Trade State")
    st.markdown(f"### {view['technical_badge'].label}")
    section = safe_mapping(safe_mapping(report.get("sections")).get("technical"))
    legacy["meta"](section)
    if view["monitor_or_incomplete"]:
        plan = safe_mapping(report.get("trade_plan"))
        scenario = monitor_technical_scenario(
            current_price=plan.get("current_price", report.get("current_price")),
            entry_low=plan.get("entry_low"), entry_high=plan.get("entry_high"),
            invalidation=plan.get("stop_loss"),
        )
        st.warning("Monitor — Not currently actionable")
        with st.expander(scenario.label, expanded=False):
            st.caption(scenario.explanation)
            values = st.columns(4)
            values[0].metric("Current Price", scenario.levels.current_price.display)
            values[1].metric("Entry Low", scenario.levels.entry_low.display)
            values[2].metric("Entry High", scenario.levels.entry_high.display)
            values[3].metric("Invalidation", scenario.levels.invalidation.display)
            targets = st.columns(3)
            targets[0].metric("Target 1", CanonicalNumberFormatter.price(plan.get("target_1")).display)
            targets[1].metric("Target 2", CanonicalNumberFormatter.price(plan.get("target_2")).display)
            targets[2].metric("Risk / Reward", _scalar_text(plan.get("risk_reward_target_1")))
            st.caption(
                " · ".join(filter(None, (
                    f"Horizon: {_scalar_text(plan.get('time_horizon'), '')}" if plan.get("time_horizon") else "",
                    f"Position guidance: {_scalar_text(plan.get('position_sizing') or plan.get('position_guidance'), '')}"
                    if plan.get("position_sizing") or plan.get("position_guidance") else "",
                ))) or "No grounded horizon or position guidance is populated."
            )
    else:
        legacy["trade_plan"](report)
    st.markdown("### Technical evidence")
    legacy["metric_grid"](
        safe_mapping(section.get("data")),
        money_keys={"price", "sma20", "sma50", "sma200", "support", "resistance"},
    )
    legacy["interpretation"](_scalar_text(section.get("interpretation"), ""))
    with st.expander("Chart and historical evidence", expanded=False):
        legacy["price_chart"](report)


def _render_catalysts(report: Mapping[str, Any], legacy: Mapping[str, Callable[..., Any]]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN")
    _section_marker("Catalysts & Sentiment", ticker)
    st.markdown("## Catalysts & Sentiment")
    guidance = safe_mapping(report.get("guidance_summary"))
    catalyst = safe_mapping(guidance.get("next_catalyst"))
    st.markdown("### What could move this security next?")
    st.info(_scalar_text(catalyst.get("event"), "No verified next catalyst is available."))

    earnings_summary = safe_mapping(report.get("earnings_summary"))
    if earnings_summary:
        st.markdown("### Earnings / event watch")
        st.write(_scalar_text(earnings_summary.get("watch_next") or earnings_summary.get("summary")))
    guidance_object = safe_mapping(report.get("management_guidance"))
    st.markdown("### Management Guidance")
    if guidance_object.get("semantic_status") == "AVAILABLE":
        with st.expander("Guidance evidence", expanded=False):
            st.json({key: value for key, value in guidance_object.items() if key not in {"version", "semantic_status"}})
    else:
        st.caption(_scalar_text(guidance_object.get("status_detail"), "Management guidance is unavailable."))

    with st.expander("Analyst sentiment, trend, targets, and actions", expanded=False):
        legacy["analyst"](safe_mapping(report.get("analyst_intelligence")))

    news = safe_mapping(safe_mapping(report.get("sections")).get("news"))
    st.markdown("### Material company news")
    legacy["meta"](news)
    items = [item for item in safe_sequence(news.get("data")) if isinstance(item, Mapping)]
    if not items:
        st.info("No recent high-confidence company-specific news available.")
    for item in items[:3]:
        with st.container(border=True):
            st.markdown(f"**{_scalar_text(item.get('headline'), 'Headline unavailable')}**")
            st.caption(" · ".join(filter(None, (_scalar_text(item.get("source"), ""), _scalar_text(item.get("date"), ""), _scalar_text(item.get("sentiment"), "")))))
            if item.get("summary"):
                st.write(_scalar_text(item.get("summary")))
            if item.get("url"):
                st.markdown(f"[Open verified source]({item['url']})")
    if len(items) > 3:
        with st.expander("All company news and classification evidence", expanded=False):
            for item in items[3:]:
                st.markdown(f"**{_scalar_text(item.get('headline'))}**")
                st.caption(f"Relevance: {_scalar_text(item.get('relevance'))} · Category: {_scalar_text(item.get('classification'))} · Impact: {_scalar_text(item.get('impact'))}")

    policy = safe_mapping(safe_mapping(safe_mapping(report.get("sections")).get("political")).get("data")) or safe_mapping(report.get("policy_intelligence"))
    with st.expander("Material policy developments", expanded=False):
        legacy["policy"](policy)
        st.caption("Political activity is contextual evidence and does not change ATLAS scoring or conviction.")

    today = safe_mapping(safe_mapping(report.get("intelligence")).get("today_move"))
    with st.expander("Today's move — facts, inference, and limitations", expanded=False):
        st.write(_scalar_text(today.get("headline"), "Under review"))
        for item in safe_sequence(today.get("verified_facts")):
            st.markdown(f"**Verified fact:** {_scalar_text(item)}")
        for item in safe_sequence(today.get("atlas_inferences")):
            st.markdown(f"**ATLAS inference:** {_scalar_text(item)}")
        for item in safe_sequence(today.get("data_limitations")):
            st.caption(f"Data limitation: {_scalar_text(item)}")

    transcript = safe_mapping(report.get("transcript_intelligence"))
    with st.expander("Earnings call / transcript intelligence", expanded=False):
        if transcript.get("semantic_status") == "AVAILABLE":
            st.json({key: value for key, value in transcript.items() if key not in {"version", "semantic_status"}})
        else:
            st.info(_scalar_text(transcript.get("status_detail"), "Transcript intelligence not yet available."))


def _render_risk_evidence(report: Mapping[str, Any], view: Mapping[str, Any], legacy: Mapping[str, Callable[..., Any]]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN")
    _section_marker("Risk & Evidence", ticker)
    st.markdown("## Risk & Evidence")
    risk = safe_mapping(safe_mapping(report.get("sections")).get("risk"))
    st.markdown("### Risk Center")
    rows = [item for item in safe_sequence(risk.get("data")) if isinstance(item, Mapping)]
    if rows:
        for item in rows:
            with st.container(border=True):
                st.markdown(f"**{_scalar_text(item.get('factor'))} — {_scalar_text(item.get('level'))}**")
                st.write(_scalar_text(item.get("atlas_interpretation")))
    else:
        st.info("No structured risk factors are currently available.")
    legacy["interpretation"](_scalar_text(risk.get("interpretation"), ""))

    sections = safe_mapping(report.get("sections"))
    readiness = [
        {"Area": name.title(), "Status": safe_mapping(section).get("status"), "Completeness": safe_mapping(section).get("completeness_pct")}
        for name, section in sections.items()
    ]
    with st.expander("Research readiness, freshness, and limitations", expanded=False):
        if readiness:
            st.dataframe(pd.DataFrame(readiness), hide_index=True, use_container_width=True)
        health = view["health"]
        st.write(f"Evidence state: {health.label}; completeness {health.completeness.display}; freshness {health.freshness or 'Unavailable'}.")
        for limitation in health.limitations:
            st.warning(limitation)

    ownership = safe_mapping(sections.get("ownership"))
    with st.expander("Ownership, major holders, and insider evidence", expanded=False):
        legacy["meta"](ownership)
        data = safe_mapping(ownership.get("data"))
        legacy["metric_grid"](data, pct_keys={"institutional_ownership_pct", "institutional_change_pct"})
        if safe_sequence(data.get("major_holders")):
            st.markdown("#### Major Holders")
            st.dataframe(pd.DataFrame(safe_sequence(data.get("major_holders"))), hide_index=True, use_container_width=True)
        if safe_sequence(data.get("insider_transactions")):
            st.markdown("#### Insider Transactions")
            st.dataframe(pd.DataFrame(safe_sequence(data.get("insider_transactions"))), hide_index=True, use_container_width=True)

    political = safe_mapping(sections.get("political"))
    political_data = safe_mapping(political.get("data")) or safe_mapping(report.get("policy_intelligence"))
    with st.expander("Security-relevant political/context evidence", expanded=False):
        st.caption("Contextual evidence only; political activity does not contribute to ATLAS scoring or conviction.")
        transactions = safe_sequence(political_data.get("policymaker_transactions"))
        if transactions:
            st.dataframe(pd.DataFrame(transactions), hide_index=True, use_container_width=True)
        else:
            st.info("No verified security-level political transaction evidence is available.")

    attribution = safe_mapping(report.get("score_attribution"))
    with st.expander("Score attribution", expanded=False):
        attribution_rows = []
        for category, values in (("Opportunity", safe_mapping(attribution.get("opportunity_attribution"))), ("Confidence", safe_mapping(attribution.get("confidence_attribution")))):
            for factor, contribution in values.items():
                attribution_rows.append({"Score": category, "Factor": str(factor).replace("_", " ").title(), "Contribution": contribution})
        if attribution_rows:
            st.dataframe(pd.DataFrame(attribution_rows), hide_index=True, use_container_width=True)
        else:
            st.info("No score-attribution evidence is populated.")

    context = _canonical_context(report)
    families = safe_mapping(context.get("evidence_families"))
    registry = safe_mapping(report.get("evidence_registry")) or safe_mapping(context.get("evidence_registry"))
    evidence_ids = []
    provenance = []
    for family, envelope_value in families.items():
        envelope = safe_mapping(envelope_value)
        evidence_ids.extend(_scalar_text(item, "") for item in safe_sequence(envelope.get("evidence_ids")))
        provider = _scalar_text(envelope.get("provider"), "")
        if provider:
            provenance.append(f"{family}: {provider}")
    drawer = evidence_drawer(
        title="Provenance, evidence IDs, and canonical registry",
        evidence_ids=tuple(item for item in evidence_ids if item),
        provenance=tuple(dict.fromkeys(provenance)),
        limitations=view["critical_gaps"],
    )
    with st.expander(drawer.title, expanded=False):
        if registry:
            st.dataframe(pd.DataFrame([{"Family": family, **safe_mapping(value)} for family, value in registry.items()]), hide_index=True, use_container_width=True)
        if drawer.provenance:
            st.caption("Provenance: " + "; ".join(drawer.provenance))
        if drawer.evidence_ids:
            st.caption("Evidence IDs: " + ", ".join(drawer.evidence_ids))

    ai = safe_mapping(report.get("ai_valuation"))
    with st.expander("AI assumptions and valuation evidence gaps", expanded=False):
        st.write(_scalar_text(ai.get("ai_method_rationale"), "Method rationale unavailable."))
        assumptions = safe_sequence(ai.get("ai_assumptions"))
        if assumptions:
            st.dataframe(pd.DataFrame(assumptions), hide_index=True, use_container_width=True)
        for gap in safe_sequence(ai.get("ai_evidence_gaps")):
            st.warning(_scalar_text(gap))
    st.caption("ATLAS Research is decision support, not personalized financial advice. Evidence availability and market conditions can change.")


def _render_ask_cta(report: Mapping[str, Any]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN").upper()
    st.markdown(
        f'<span data-atlas-qa="research-ask-cta" data-atlas-ticker="{escape(ticker)}" '
        'data-atlas-destination="ask-ai" aria-hidden="true" style="display:none">research-ask-cta</span>',
        unsafe_allow_html=True,
    )
    if st.button("Ask ATLAS about this research", key=f"vnext_ask_atlas_{ticker}", type="primary", use_container_width=True):
        st.session_state["ask_ai_question"] = f"Why does ATLAS currently classify {ticker} this way?"
        st.session_state["ask_ai_ticker"] = ticker
        st.session_state["v79_pending_page"] = "Ask AI"
        st.rerun()


def render_research_vnext(report: Mapping[str, Any], *, legacy: Mapping[str, Callable[..., Any]]) -> None:
    """Render five decision-oriented sections from the canonical report."""
    ticker = str(report.get("ticker") or "UNKNOWN").upper()
    view = build_research_decision_view(report)
    st.markdown(
        f'<span data-atlas-qa="research-vnext" data-atlas-version="{RESEARCH_VNEXT_VERSION}" '
        f'data-atlas-ticker="{escape(ticker)}" data-atlas-section-count="5" '
        f'data-atlas-monitor="{str(bool(view["monitor_or_incomplete"])).lower()}" '
        'aria-hidden="true" style="display:none">research-vnext</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        [data-testid="stTabs"] [role="tablist"] { gap: .35rem; }
        @media (max-width: 700px) {
          [data-testid="stTabs"] [role="tablist"] { flex-wrap: wrap; overflow-x: visible; }
          [data-testid="stTabs"] [role="tab"] { flex: 1 1 46%; min-height: 44px; white-space: normal; }
          [data-testid="stDataFrame"] { max-width: 100%; overflow-x: auto; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    tabs = st.tabs(list(RESEARCH_VNEXT_SECTIONS))
    with tabs[0]:
        _render_decision(report, view)
    with tabs[1]:
        _render_fundamentals(report, legacy)
    with tabs[2]:
        _render_technical(report, view, legacy)
    with tabs[3]:
        _render_catalysts(report, legacy)
    with tabs[4]:
        _render_risk_evidence(report, view, legacy)
    _render_ask_cta(report)


__all__ = [
    "RESEARCH_EVIDENCE_MIGRATION", "RESEARCH_VNEXT_SECTIONS",
    "RESEARCH_VNEXT_VERSION", "build_research_decision_view",
    "render_research_vnext",
]
