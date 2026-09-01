"""ATLAS VNext UX-2 Research decision dossier.

Presentation only: this module consumes an already-built canonical Research
report.  It never calculates recommendations, scores, valuation, technical
states, or trade levels.
"""

from __future__ import annotations

from datetime import date, datetime
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
    families = safe_mapping(_canonical_context(report).get("evidence_families"))
    canonical_data = safe_mapping(safe_mapping(families.get("technicals")).get("data"))
    for key in ("technical_state", "state", "setup_state", "breakout_state"):
        if key in canonical_data and not is_missing_scalar(canonical_data.get(key)):
            return canonical_data.get(key)
    return None


def _canonical_context(report: Mapping[str, Any]) -> Mapping[str, Any]:
    return safe_mapping(report.get("research_context"))


def _canonical_decision(report: Mapping[str, Any]) -> Mapping[str, Any]:
    return safe_mapping(_canonical_context(report).get("production_decision"))


def _decision_value(report: Mapping[str, Any], canonical_key: str, report_key: str) -> Any:
    """Resolve immutable decision authority without cross-field substitution."""
    decision = safe_mapping(_canonical_context(report).get("production_decision"))
    return decision.get(canonical_key) if decision else report.get(report_key)


def _normalized_status(value: Any) -> str:
    status = str(value or "DATA_UNAVAILABLE").strip().upper().replace(" ", "_")
    if status in {"AVAILABLE", "PARTIAL", "DATA_UNAVAILABLE", "NOT_APPLICABLE", "TEMPORARILY_UNAVAILABLE"}:
        return status
    if status == "UNAVAILABLE":
        return "DATA_UNAVAILABLE"
    return "DATA_UNAVAILABLE"


def _family_availability(report: Mapping[str, Any], *family_names: str, section_name: str | None = None) -> str:
    """Resolve evidence availability without treating a populated container as evidence."""
    statuses: list[str] = []
    families = safe_mapping(_canonical_context(report).get("evidence_families"))
    for name in family_names:
        envelope = safe_mapping(families.get(name))
        if envelope:
            statuses.append(_normalized_status(envelope.get("semantic_status")))
    if section_name:
        section = safe_mapping(safe_mapping(report.get("sections")).get(section_name))
        if section:
            raw = section.get("semantic_status") or section.get("status")
            statuses.append(_normalized_status(raw))
    if "AVAILABLE" in statuses:
        return "AVAILABLE"
    if "PARTIAL" in statuses:
        return "PARTIAL"
    if statuses and all(item == "NOT_APPLICABLE" for item in statuses):
        return "NOT_APPLICABLE"
    if "TEMPORARILY_UNAVAILABLE" in statuses:
        return "TEMPORARILY_UNAVAILABLE"
    return "DATA_UNAVAILABLE"


def technical_availability(report: Mapping[str, Any]) -> dict[str, Any]:
    state = _technical_state(report)
    evidence = _family_availability(report, "technicals", section_name="technical")
    badge = technical_state_badge(state)
    if badge.canonical_value:
        label = badge.label
    elif evidence == "AVAILABLE":
        label = "Technical evidence available · State not published"
    elif evidence == "PARTIAL":
        label = "Technical evidence partial · State not published"
    elif evidence == "NOT_APPLICABLE":
        label = "Technical evidence not applicable"
    else:
        label = "Technical evidence unavailable"
    return {"state": state, "evidence_status": evidence, "badge": badge, "label": label}


def risk_evidence_availability(report: Mapping[str, Any]) -> dict[str, str]:
    """Presentation-only factor availability; never changes risk conclusions."""
    registry = safe_mapping(report.get("evidence_registry"))
    valuation_status = _normalized_status(safe_mapping(registry.get("valuation")).get("status"))
    if valuation_status == "DATA_UNAVAILABLE" and report.get("atlas_valuation_status") not in {None, "", "NOT_PUBLISHED"}:
        valuation_status = "AVAILABLE"
    market = safe_mapping(report.get("market_context"))
    macro_status = "AVAILABLE" if any(not is_missing_scalar(value) for value in market.values()) else "DATA_UNAVAILABLE"
    return {
        "Financial": _family_availability(
            report, "financial_statements", "ratios_key_metrics", "growth_segments", section_name="financials"
        ),
        "Valuation": valuation_status,
        "Technical": _family_availability(report, "technicals", section_name="technical"),
        "Institutional": _family_availability(report, "institutional_ownership", section_name="ownership"),
        "Political / Regulatory": _family_availability(report, section_name="political"),
        "Macro": macro_status,
    }


def _clip_words(value: Any, limit: int) -> str:
    text = _scalar_text(value, "")
    words = text.split()
    return text if len(words) <= limit else " ".join(words[:limit]).rstrip(" ,;:") + "…"


def _display_status(status: str) -> str:
    return str(status or "DATA_UNAVAILABLE").replace("_", " ").title()


def _canonical_financial_value(report: Mapping[str, Any], data: Mapping[str, Any], *keys: str) -> Any:
    """Use one alias order for displayed canonical financial evidence."""
    for source in (data, report):
        for key in keys:
            value = source.get(key)
            if not is_missing_scalar(value) and not isinstance(value, (Mapping, list, tuple, set, frozenset)):
                return value
    return None


def _customer_event_label(event: Any, event_date: Any, *, today: date | None = None) -> str:
    """Describe event timing without changing the provider's date."""
    label = _scalar_text(event, "No verified catalyst is available")
    raw = _scalar_text(event_date, "")
    parsed: date | None = None
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                parsed = date.fromisoformat(raw[:10])
            except ValueError:
                parsed = None
    reference = today or date.today()
    if parsed is not None and "earnings" in label.lower():
        direction = "Next scheduled" if parsed >= reference else "Latest scheduled/reported"
        return f"{direction} earnings report"
    return label


def _clean_customer_prose(value: Any) -> str:
    text = _scalar_text(value, "")
    return text.replace("Atlas views revenue growth is ", "ATLAS views revenue growth of ")


def _block_marker(name: str, ticker: str) -> None:
    st.markdown(
        f'<span data-atlas-qa="research-ux3b-block" data-atlas-block="{escape(name)}" '
        f'data-atlas-ticker="{escape(ticker)}" aria-hidden="true" style="display:none">ux3b</span>',
        unsafe_allow_html=True,
    )


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
    canonical_recommendation = _decision_value(report, "recommendation", "committee_verdict")
    canonical_opportunity = _decision_value(report, "opportunity", "opportunity_score")
    canonical_confidence = _decision_value(report, "confidence", "confidence_pct")
    verdict = _scalar_text(canonical_recommendation, "Unavailable")
    try:
        materially_incomplete = completeness is None or float(completeness) < 70.0
    except (TypeError, ValueError):
        materially_incomplete = True
    monitor = verdict.upper().replace(" ", "_") in {"MONITOR", "WATCH", "RESEARCH_/_MONITOR", "UNAVAILABLE"} or materially_incomplete
    status, cache_status = _freshness(report)
    gaps = _critical_gaps(report)
    health = evidence_health(
        semantic_status=status,
        cache_status=cache_status,
        completeness_pct=completeness,
        limitations=gaps,
    )
    header = decision_header(
        recommendation=canonical_recommendation,
        opportunity=canonical_opportunity,
        confidence=canonical_confidence,
        research_completeness=completeness,
        actionability_label=(
            "Research incomplete — not currently actionable"
            if monitor and verdict.upper() == "UNAVAILABLE"
            else "Monitor — Not currently actionable"
            if monitor
            else _scalar_text(action.get("current_action"), verdict.replace("_", " ").title())
        ),
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
    technical = technical_availability(report)
    return {
        "header": header, "prices": prices, "evidence": evidence,
        "health": health, "technical_badge": technical["badge"],
        "technical_availability": technical,
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


def _metric_currency_range(low: Any, high: Any) -> str:
    """Escape currency markers so Streamlit does not parse them as inline math."""
    return CanonicalNumberFormatter.currency_range(low, high).display.replace("$", r"\$")


def _render_decision(report: Mapping[str, Any], view: Mapping[str, Any]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN")
    _section_marker("Decision", ticker)
    header = view["header"]
    badge = view["technical_badge"]
    st.markdown("## Decision")
    st.markdown(f"### {header.actionability_label}")
    _block_marker("decision-why", ticker)
    st.markdown("#### Why")
    support = _clean_customer_prose(view["evidence"].support)
    constraint = _clean_customer_prose(view["evidence"].contradiction_or_risk)
    if constraint.lower().startswith("main risk is "):
        constraint = constraint[13:].strip()
    why = _clip_words(" ".join(filter(None, (support, f"Primary constraint: {constraint}" if constraint else ""))), 55)
    st.write(why or "ATLAS does not have enough canonical evidence to publish a decision explanation.")

    guidance = safe_mapping(report.get("guidance_summary"))
    action = safe_mapping(guidance.get("action_now"))
    decision = _canonical_decision(report)
    st.markdown("#### What I Would Do")
    with st.container(key=f"vnext_decision_action_{ticker}"):
        if decision.get("semantic_status") == "DATA_UNAVAILABLE" or is_missing_scalar(decision.get("recommendation")):
            st.info("ATLAS does not currently publish an actionable recommendation for this security.")
        elif view["monitor_or_incomplete"]:
            st.info(f"{_scalar_text(decision.get('recommendation')).replace('_', ' ')} — Not currently actionable.")
        else:
            st.info(_scalar_text(action.get("current_action"), _scalar_text(decision.get("recommendation"))))

    _block_marker("decision-core-metrics", ticker)
    columns = st.columns(5)
    columns[0].metric("Opportunity", _scalar_text(header.opportunity))
    columns[1].metric("Confidence", CanonicalNumberFormatter.percent(header.confidence).display)
    prices = view["prices"]
    columns[2].metric("Current Price", prices.current_price.display)
    canonical_expected_return = _decision_value(report, "decision_expected_return", "atlas_expected_return_pct")
    columns[3].metric("Atlas-FV Expected Return", CanonicalNumberFormatter.percent(canonical_expected_return, signed=True).display)
    columns[4].metric("Stop / Invalidation", prices.invalidation.display)

    evidence = view["evidence"]
    support_facts = [item for item in safe_sequence(guidance.get("supporting_facts")) if isinstance(item, Mapping)]
    risk_facts = [item for item in safe_sequence(guidance.get("key_risks")) if isinstance(item, Mapping)]
    support_col, risk_col = st.columns(2)
    with support_col:
        _block_marker("why-atlas-likes-it", ticker)
        st.markdown("#### Why ATLAS Likes It")
        if support_facts:
            for item in support_facts[:3]:
                st.write(f"- {_clip_words(item.get('fact'), 24)}")
        else:
            st.caption("No grounded supporting evidence is currently available.")
    with risk_col:
        _block_marker("what-stops-atlas", ticker)
        st.markdown("#### What Stops ATLAS")
        if risk_facts:
            for item in risk_facts[:3]:
                st.write(f"- {_clip_words(item.get('risk'), 24)}")
        else:
            st.caption("No grounded constraint is currently available.")

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

    catalyst = safe_mapping(guidance.get("next_catalyst"))
    st.markdown("#### What happens next")
    st.write(
        _customer_event_label(catalyst.get("event"), catalyst.get("date"))
        + (f" — {_scalar_text(catalyst.get('date'), '')}" if catalyst.get("date") else "")
        + (f". {_scalar_text(catalyst.get('what_atlas_will_watch'), '')}" if catalyst.get("what_atlas_will_watch") else "")
    )
    changes = safe_mapping(guidance.get("thesis_change_conditions"))
    _block_marker("what-changes-the-thesis", ticker)
    st.markdown("#### What Changes the Thesis")
    change_cols = st.columns(3)
    for column, label in zip(change_cols, ("strengthen", "weaken", "invalidate")):
        with column:
            st.markdown(f"**{label.title()}**")
            items = safe_sequence(changes.get(label))
            if items:
                for item in items[:3]:
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


def build_investment_brief(report: Mapping[str, Any]) -> str:
    """Deterministic 60-second brief assembled from canonical structured fields."""
    parts: list[str] = []
    decision = _canonical_decision(report)
    recommendation = _scalar_text(decision.get("recommendation"), "")
    if recommendation:
        parts.append(f"ATLAS currently classifies the security as {recommendation.replace('_', ' ')}.")
    sections = safe_mapping(report.get("sections"))
    financials = safe_mapping(sections.get("financials"))
    financial_data = safe_mapping(financials.get("data"))
    if _normalized_status(financials.get("semantic_status") or financials.get("status")) in {"AVAILABLE", "PARTIAL"}:
        revenue_growth = CanonicalNumberFormatter.percent(financial_data.get("revenue_growth_pct"), signed=False)
        eps_growth = CanonicalNumberFormatter.percent(financial_data.get("eps_growth_pct"), signed=False)
        if revenue_growth.exact_value is not None:
            parts.append(f"Current evidence reports revenue growth of {revenue_growth.display}.")
        if eps_growth.exact_value is not None:
            parts.append(f"Current evidence reports EPS growth of {eps_growth.display}.")
    earnings = safe_mapping(sections.get("earnings"))
    if _normalized_status(earnings.get("semantic_status") or earnings.get("status")) in {"AVAILABLE", "PARTIAL"}:
        earnings_data = safe_mapping(earnings.get("data"))
        eps_surprise = CanonicalNumberFormatter.percent(earnings_data.get("eps_surprise_pct"), signed=True)
        if eps_surprise.exact_value is not None:
            parts.append(f"The latest reported EPS surprise was {eps_surprise.display}.")
    analyst = safe_mapping(report.get("analyst_intelligence"))
    divergence = _clip_words(analyst.get("atlas_street_divergence_message"), 20)
    if divergence:
        parts.append(divergence)
    technical = technical_availability(report)
    if technical["badge"].canonical_value:
        parts.append(f"The deterministic technical state is {technical['badge'].label}.")
    guidance = safe_mapping(report.get("guidance_summary"))
    risk = _first_mapping_item(guidance.get("key_risks"))
    if risk:
        constraint = _clean_customer_prose(risk.get("risk"))
        if constraint.lower().startswith("main risk is "):
            constraint = constraint[13:].strip()
        if constraint:
            parts.append(f"Primary constraint: {_clip_words(constraint, 20).rstrip('.')}.")
    text = " ".join(part for part in parts if part)
    return _clip_words(text, 100) if len(text.split()) >= 20 else "Available evidence is not yet sufficient for a grounded 60-second investment brief."


def _direction(value: Any, *, positive_is_improving: bool = True) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unavailable"
    if number == 0:
        return "Stable"
    improving = number > 0 if positive_is_improving else number < 0
    return "Improving" if improving else "Weakening"


def _render_financial_direction(report: Mapping[str, Any], legacy: Mapping[str, Callable[..., Any]]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN")
    section = safe_mapping(safe_mapping(report.get("sections")).get("financials"))
    data = safe_mapping(section.get("data"))
    _block_marker("financial-direction", ticker)
    st.markdown("### Financial Direction")
    if _normalized_status(section.get("semantic_status") or section.get("status")) not in {"AVAILABLE", "PARTIAL"}:
        st.info("Financial direction is unavailable from the current canonical evidence.")
        return
    direction_cols = st.columns(4)
    direction_cols[0].metric("Revenue Direction", _direction(data.get("revenue_growth_pct")))
    direction_cols[1].metric("EPS Direction", _direction(data.get("eps_growth_pct")))
    margins = [data.get(key) for key in ("gross_margin_pct", "operating_margin_pct", "net_margin_pct") if data.get(key) is not None]
    direction_cols[2].metric("Margin Direction", "Stable" if margins else "Unavailable")
    fcf = data.get("free_cash_flow")
    direction_cols[3].metric("Cash Generation", _direction(fcf))
    st.write(_clip_words(_clean_customer_prose(section.get("interpretation")), 60) or "No grounded financial interpretation is populated.")
    metrics = st.columns(6)
    values = (
        ("Revenue Growth", CanonicalNumberFormatter.percent(data.get("revenue_growth_pct"), signed=True).display),
        ("EPS Growth", CanonicalNumberFormatter.percent(data.get("eps_growth_pct"), signed=True).display),
        ("Operating Margin", CanonicalNumberFormatter.percent(data.get("operating_margin_pct")).display),
        ("Free Cash Flow", CanonicalNumberFormatter.currency(data.get("free_cash_flow")).display),
        ("Cash", CanonicalNumberFormatter.currency(_canonical_financial_value(report, data, "cash", "total_cash", "cash_and_equivalents", "Cash")).display),
        ("Debt", CanonicalNumberFormatter.currency(_canonical_financial_value(report, data, "debt", "total_debt", "Total Debt")).display),
    )
    for column, (label, value) in zip(metrics, values):
        column.metric(label, value)
    with st.expander("View full financials", expanded=False):
        legacy["metric_grid"](
            data,
            money_keys={"free_cash_flow", "operating_cash_flow", "cash", "debt"},
            pct_keys={"revenue_growth_pct", "eps_growth_pct", "gross_margin_pct", "operating_margin_pct", "net_margin_pct", "roe_pct", "roic_pct"},
        )


def _render_fundamentals(report: Mapping[str, Any], legacy: Mapping[str, Callable[..., Any]]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN")
    _section_marker("Fundamentals & Valuation", ticker)
    st.markdown("## Fundamentals & Valuation")
    _block_marker("sixty-second-investment-brief", ticker)
    st.markdown("### 60-Second Investment Brief")
    st.write(build_investment_brief(report))

    valuation = safe_mapping(report.get("valuation_families"))
    analyst = safe_mapping(report.get("analyst_intelligence"))
    st.markdown("### Valuation")
    valuation_cols = st.columns(3)
    valuation_cols[0].metric("Current Price", CanonicalNumberFormatter.price(report.get("current_price")).display)
    valuation_cols[1].metric("Atlas Quant Fair Value", CanonicalNumberFormatter.price(_decision_value(report, "atlas_fair_value", "atlas_fair_value")).display)
    valuation_cols[2].metric("Atlas-FV Expected Return", CanonicalNumberFormatter.percent(_decision_value(report, "decision_expected_return", "atlas_expected_return_pct"), signed=True).display)
    street_cols = st.columns(2)
    street_cols[0].metric("Wall Street Mean Target", CanonicalNumberFormatter.price(analyst.get("wall_street_mean_target")).display)
    street_cols[1].metric(
        "Wall Street Low / High",
        _metric_currency_range(analyst.get("wall_street_low_target"), analyst.get("wall_street_high_target")),
    )
    st.markdown("#### Valuation Interpretation")
    st.caption("Wall Street consensus is external analyst evidence and is not a substitute for Atlas Fair Value.")
    st.write(_scalar_text(analyst.get("atlas_street_divergence_message"), "Valuation comparison unavailable."))
    with st.expander("Valuation assumptions, scenarios, evidence gaps, and methodology", expanded=False):
        legacy["valuation"](report)
        scenario_rows = [
            {"Scenario": label, "Value": valuation.get(key)}
            for label, key in (("Bear", "scenario_bear"), ("Base", "scenario_base"), ("Bull", "scenario_bull"))
            if valuation.get(key) is not None
        ]
        if scenario_rows:
            st.dataframe(pd.DataFrame(scenario_rows), hide_index=True, use_container_width=True)
        else:
            st.caption("Canonical valuation scenarios are unavailable.")

    _render_financial_direction(report, legacy)

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
    technical = view["technical_availability"]
    _block_marker("deterministic-technical-state", ticker)
    st.markdown("### Deterministic Technical State")
    st.info(technical["label"])
    section = safe_mapping(safe_mapping(report.get("sections")).get("technical"))
    legacy["meta"](section)
    interpretation = _clip_words(section.get("interpretation"), 45)
    if interpretation:
        st.write(interpretation)
    plan = safe_mapping(report.get("trade_plan"))
    if view["monitor_or_incomplete"]:
        scenario = monitor_technical_scenario(
            current_price=plan.get("current_price", report.get("current_price")),
            entry_low=plan.get("entry_low"), entry_high=plan.get("entry_high"),
            invalidation=plan.get("stop_loss"),
        )
        technical_state = _scalar_text(technical.get("state"), "").upper().replace(" ", "_")
        if technical_state in {"MONITOR", "WATCH"}:
            st.warning(f"{technical_state.replace('_', ' ').title()} — Not currently actionable")
        else:
            st.info("No actionable technical state is currently published.")
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
            st.caption(f"Entry status: {_display_status(_scalar_text(plan.get('entry_status'), 'DATA_UNAVAILABLE'))}")
            st.caption(
                " · ".join(filter(None, (
                    f"Horizon: {_scalar_text(plan.get('time_horizon'), '')}" if plan.get("time_horizon") else "",
                    f"Position guidance: {_scalar_text(plan.get('position_sizing') or plan.get('position_guidance'), '')}"
                    if plan.get("position_sizing") or plan.get("position_guidance") else "",
                ))) or "No grounded horizon or position guidance is populated."
            )
    else:
        levels = st.columns(6)
        levels[0].metric("Entry Status", _display_status(_scalar_text(plan.get("entry_status"), "DATA_UNAVAILABLE")))
        levels[1].metric("Action Zone", _metric_currency_range(plan.get("entry_low"), plan.get("entry_high")))
        levels[2].metric("Target 1", CanonicalNumberFormatter.price(plan.get("target_1")).display)
        levels[3].metric("Target 2", CanonicalNumberFormatter.price(plan.get("target_2")).display)
        levels[4].metric("Stop", CanonicalNumberFormatter.price(plan.get("stop_loss")).display)
        levels[5].metric("Risk / Reward", _scalar_text(plan.get("risk_reward_target_1")))
    changes = safe_mapping(safe_mapping(report.get("guidance_summary")).get("thesis_change_conditions"))
    confirm, breaks = st.columns(2)
    with confirm:
        st.markdown("### What confirms the setup?")
        items = safe_sequence(changes.get("strengthen"))
        st.write("\n".join(f"- {_scalar_text(item)}" for item in items[:3]) if items else "No grounded confirmation condition is available.")
    with breaks:
        st.markdown("### What breaks the setup?")
        items = safe_sequence(changes.get("invalidate"))
        st.write("\n".join(f"- {_scalar_text(item)}" for item in items[:3]) if items else "No grounded invalidation condition is available.")
    with st.expander("Technical indicators and chart", expanded=False):
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
    _block_marker("catalyst-next", ticker)
    st.markdown("### What could move this security next?")
    st.info(_customer_event_label(catalyst.get("event"), catalyst.get("date")))

    earnings_summary = safe_mapping(report.get("earnings_summary"))
    earnings = safe_mapping(report.get("earnings_intelligence"))
    latest = safe_mapping(earnings.get("latest_quarter"))
    st.markdown("### Latest Earnings")
    if earnings.get("semantic_status") == "AVAILABLE":
        earnings_cols = st.columns(4)
        earnings_cols[0].metric("Reported quarter", _scalar_text(latest.get("fiscal_period") or latest.get("report_date")))
        earnings_cols[1].metric("EPS surprise", CanonicalNumberFormatter.percent(latest.get("eps_surprise_pct"), signed=True).display)
        earnings_cols[2].metric("Revenue surprise", CanonicalNumberFormatter.percent(latest.get("revenue_surprise_pct"), signed=True).display)
        earnings_cols[3].metric("Classification", _display_status(_scalar_text(earnings.get("latest_quarter_classification"))))
        st.write(_scalar_text(earnings_summary.get("trend_assessment") or earnings_summary.get("summary")))
        st.caption("Watch next: " + _scalar_text(earnings_summary.get("watch_next"), "No verified next-quarter watch item."))
    elif earnings.get("semantic_status") == "NOT_APPLICABLE":
        st.info("Corporate earnings evidence is not applicable to this security.")
    else:
        st.info("Latest reported earnings evidence is unavailable.")
    guidance_object = safe_mapping(report.get("management_guidance"))
    st.markdown("### Management Guidance")
    if guidance_object.get("semantic_status") == "AVAILABLE":
        with st.expander("Guidance evidence", expanded=False):
            st.json({key: value for key, value in guidance_object.items() if key not in {"version", "semantic_status"}})
    else:
        st.caption(_scalar_text(guidance_object.get("status_detail"), "Management guidance is unavailable."))

    analyst = safe_mapping(report.get("analyst_intelligence"))
    st.markdown("### Analyst Trend")
    trend = safe_mapping(analyst.get("trend_90d"))
    analyst_cols = st.columns(3)
    analyst_cols[0].metric("90-day trend", _display_status(_scalar_text(trend.get("classification"))))
    analyst_cols[1].metric("Wall Street consensus", CanonicalNumberFormatter.currency(analyst.get("wall_street_mean_target")).display)
    analyst_cols[2].metric("Coverage", _scalar_text(analyst.get("analyst_coverage")))
    recent_action = _first_mapping_item(analyst.get("recent_actions"))
    if recent_action:
        st.caption(
            "Latest firm action: " + " · ".join(filter(None, (
                _scalar_text(recent_action.get("firm"), ""), _scalar_text(recent_action.get("primary_action"), ""),
                _scalar_text(recent_action.get("date"), ""),
            )))
        )
    else:
        st.caption("No verified firm-level analyst action is available.")
    with st.expander("Analyst targets and firm-level actions", expanded=False):
        legacy["analyst"](safe_mapping(report.get("analyst_intelligence")))
        target_family = safe_mapping(safe_mapping(_canonical_context(report).get("evidence_families")).get("analyst_price_target_actions"))
        target_rows = safe_sequence(safe_mapping(target_family.get("data")).get("actions"))
        if target_rows:
            st.dataframe(pd.DataFrame(target_rows), hide_index=True, use_container_width=True)
            st.caption("Prior target was not provided by the source, so ATLAS does not calculate an individual target change.")
        else:
            st.caption("Individual price-target action evidence is unavailable.")
        snapshot_family = safe_mapping(safe_mapping(_canonical_context(report).get("evidence_families")).get("analyst_estimate_snapshots"))
        st.caption(_scalar_text(safe_mapping(snapshot_family.get("data")).get("status_detail"), "Estimate revision history is still being accumulated."))

    transcript_family = safe_mapping(safe_mapping(_canonical_context(report).get("evidence_families")).get("transcript_intelligence"))
    transcript_data = safe_mapping(transcript_family.get("data"))
    st.markdown("### Management / Transcript Insight")
    if transcript_family.get("semantic_status") == "AVAILABLE":
        for label, key in (("What management emphasized", "management_themes"), ("Supported opportunities", "supported_opportunities"), ("Supported risks", "supported_risks"), ("What to watch next", "monitoring_items")):
            items = safe_sequence(transcript_data.get(key))
            if items:
                st.markdown(f"**{label}**")
                st.write("\n".join(f"- {_scalar_text(safe_mapping(item).get('text') or item)}" for item in items[:4]))
        st.caption("Grounded transcript evidence only; this evidence does not calculate ATLAS decisions or valuation.")
        source_ids = safe_sequence(transcript_family.get("evidence_ids")) or safe_sequence(transcript_data.get("source_evidence_ids"))
        if source_ids:
            st.caption("Transcript evidence: " + ", ".join(_scalar_text(item) for item in source_ids))
    else:
        st.caption("Transcript intelligence has not been loaded for this ticker.")

    import os
    api_key = os.getenv("FMP_API_KEY", "")
    if st.button("Refresh analyst targets & insider evidence", key=f"phase1-post-shell-{ticker}", disabled=not bool(api_key)):
        from services.fmp_phase1_intelligence import refresh_post_shell_evidence
        refresh_post_shell_evidence(ticker, api_key=api_key, security_type=_scalar_text(report.get("security_type"), "EQUITY"))
        st.rerun()
    if st.button("Load latest management transcript", key=f"phase1-transcript-{ticker}", disabled=not bool(api_key)):
        from services.fmp_phase1_intelligence import acquire_latest_transcript_intelligence
        acquire_latest_transcript_intelligence(ticker, api_key=api_key)
        st.rerun()
    transcript_index = safe_mapping(safe_mapping(_canonical_context(report).get("evidence_families")).get("transcript_index"))
    periods = [
        item for item in safe_sequence(safe_mapping(transcript_index.get("data")).get("periods"))
        if isinstance(item, Mapping) and item.get("fiscal_year") and item.get("fiscal_quarter")
    ]
    if periods:
        with st.expander("Previous earnings calls", expanded=False):
            labels = [f"Q{int(item['fiscal_quarter'])} {int(item['fiscal_year'])}" for item in periods]
            selected_label = st.selectbox("Available transcript period", labels, key=f"phase1-transcript-period-{ticker}")
            selected_period = periods[labels.index(selected_label)]
            if st.button("Load selected earnings-call insight", key=f"phase1-transcript-history-{ticker}", disabled=not bool(api_key)):
                from services.fmp_phase1_intelligence import acquire_transcript_intelligence
                acquire_transcript_intelligence(
                    ticker,
                    year=int(selected_period["fiscal_year"]),
                    quarter=int(selected_period["fiscal_quarter"]),
                    api_key=api_key,
                )
                st.rerun()
    operation = safe_mapping(transcript_family.get("operation_metadata"))
    if operation:
        st.markdown(
            '<span data-atlas-transcript-ticker="{ticker}" data-atlas-transcript-year="{year}" '
            'data-atlas-transcript-quarter="{quarter}" data-atlas-transcript-cache-status="{status}" '
            'data-atlas-transcript-provider-calls="{calls}" data-atlas-transcript-evidence-id="{evidence}" '
            'data-atlas-transcript-synthesis-version="{version}" style="display:none"></span>'.format(
                ticker=_scalar_text(operation.get("ticker"), ticker),
                year=_scalar_text(operation.get("selected_year"), ""),
                quarter=_scalar_text(operation.get("selected_quarter"), ""),
                status=_scalar_text(operation.get("cache_status"), "UNAVAILABLE"),
                calls=_scalar_text(operation.get("provider_call_count"), "0"),
                evidence=_scalar_text(operation.get("transcript_evidence_id"), ""),
                version=_scalar_text(operation.get("synthesis_version"), ""),
            ),
            unsafe_allow_html=True,
        )

    ownership = safe_mapping(safe_mapping(safe_mapping(report.get("sections")).get("ownership")).get("data"))
    st.markdown("### Ownership & Insider Context")
    ownership_cols = st.columns(3)
    ownership_cols[0].metric("Institutional ownership", CanonicalNumberFormatter.percent(ownership.get("institutional_ownership_pct")).display)
    ownership_cols[1].metric("Institutional change", CanonicalNumberFormatter.percent(ownership.get("institutional_change_pct"), signed=True).display)
    insider_rows = safe_sequence(ownership.get("insider_transactions"))
    ownership_cols[2].metric("Verified insider records", str(len(insider_rows)) if insider_rows else "Unavailable")
    st.caption("Insider evidence remains unavailable when no verified active family is present; ATLAS does not infer activity from absence.")

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
    st.markdown("### Congressional Activity")
    transactions = safe_sequence(policy.get("policymaker_transactions"))
    if transactions and isinstance(transactions[0], Mapping):
        transaction = transactions[0]
        st.write(" · ".join(filter(None, (
            _scalar_text(transaction.get("politician") or transaction.get("member"), ""),
            _scalar_text(transaction.get("action") or transaction.get("transaction_type"), ""),
            _scalar_text(transaction.get("amount_range") or transaction.get("amount"), ""),
        ))))
        st.caption(" · ".join(filter(None, (
            f"Trade Date: {_scalar_text(transaction.get('transaction_date') or transaction.get('trade_date'), '')}",
            f"Disclosure Date: {_scalar_text(transaction.get('disclosure_date'), '')}",
            f"Source: {_scalar_text(transaction.get('provider') or transaction.get('source'), '')}",
        ))))
    else:
        st.caption("No verified security-level congressional activity is available.")
    st.caption("Political activity is contextual only and never contributes to ATLAS scoring.")
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
    _block_marker("primary-risks", ticker)
    st.markdown("### Primary Risks")
    intelligence = safe_mapping(report.get("intelligence"))
    primary_risks = safe_sequence(intelligence.get("key_risks"))
    if primary_risks:
        st.write("\n".join(f"- {_scalar_text(item)}" for item in primary_risks[:5]))
    else:
        st.info("No grounded primary-risk summary is available.")
    st.markdown("### Evidence Health")
    health = view["health"]
    health_cols = st.columns(3)
    health_cols[0].metric("Evidence state", health.label)
    health_cols[1].metric("Completeness", health.completeness.display)
    health_cols[2].metric("Freshness", health.freshness or "Unavailable")
    st.markdown("### What Is Missing")
    if view["critical_gaps"]:
        st.write("\n".join(f"- {item}" for item in view["critical_gaps"][:8]))
    else:
        st.caption("No critical missing-evidence item is registered.")

    st.markdown("### Risk Evidence Availability")
    st.dataframe(
        pd.DataFrame([{"Evidence area": name, "Availability": _display_status(status)} for name, status in risk_evidence_availability(report).items()]),
        hide_index=True, use_container_width=True,
    )
    with st.expander("Detailed Risk Center", expanded=False):
        st.markdown("#### Structured risk taxonomy")
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
        phase1_insider = safe_mapping(safe_mapping(_canonical_context(report).get("evidence_families")).get("insider_transactions"))
        phase1_rows = safe_sequence(safe_mapping(phase1_insider.get("data")).get("transactions"))
        if phase1_rows:
            st.markdown("#### Canonical Insider Transactions")
            st.dataframe(pd.DataFrame(phase1_rows), hide_index=True, use_container_width=True)
            st.caption("Context only; insider activity does not contribute to scoring, ranking, or recommendation.")

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


def _render_watching_next(report: Mapping[str, Any]) -> None:
    ticker = str(report.get("ticker") or "UNKNOWN").upper()
    _block_marker("watching-next", ticker)
    st.markdown("## What I’m Watching Next")
    guidance = safe_mapping(report.get("guidance_summary"))
    catalyst = safe_mapping(guidance.get("next_catalyst"))
    conditions = safe_mapping(guidance.get("thesis_change_conditions"))
    items = [
        _scalar_text(catalyst.get("event"), ""),
        *(_scalar_text(item, "") for item in safe_sequence(conditions.get("strengthen"))[:2]),
        *(_scalar_text(item, "") for item in safe_sequence(conditions.get("invalidate"))[:2]),
    ]
    items = list(dict.fromkeys(item for item in items if item))
    st.write("\n".join(f"- {item}" for item in items[:5]) if items else "No grounded next-watch item is available.")


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
        /* The fixed Streamlit Cloud viewer/profile badges live outside the
           app iframe. Reserve a responsive gutter so decision evidence and
           CTAs never render beneath those platform-owned controls. */
        [data-testid="stMainBlockContainer"] {
          padding-bottom:max(6rem, calc(1rem + env(safe-area-inset-bottom))) !important;
        }
        [data-testid="stMetric"] { padding-right:5.5rem !important; }
        [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
        [data-testid="stExpander"] summary {
          box-sizing:border-box;
          padding-right:3.5rem !important;
        }
        [class*="st-key-vnext_ask_atlas"] [data-testid="stButton"] { margin-right:5.5rem; }
        [data-testid="stTabs"] [role="tablist"] { gap: .35rem; }
        @media (min-width: 701px) {
          /* Desktop decision metrics sit above the host-control footprint;
             retain a compact readable inset instead of the mobile exclusion zone. */
          [data-testid="stMetric"] { padding-right:.75rem !important; }
        }
        @media (max-width: 700px) {
          [data-testid="stMainBlockContainer"] {
            padding-bottom:max(6.5rem, calc(1rem + env(safe-area-inset-bottom))) !important;
          }
          [data-testid="stMetric"] { padding-right:7rem !important; }
          [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
          [data-testid="stExpander"] summary { padding-right:7.5rem !important; }
          [class*="st-key-vnext_ask_atlas"] [data-testid="stButton"] { margin-right:7rem; }
          [data-testid="stTabs"] [role="tablist"] { flex-wrap: wrap; overflow-x: visible; }
          [data-testid="stTabs"] [role="tab"] { flex: 1 1 46%; min-height: 44px; white-space: normal; }
          [data-testid="stDataFrame"] { max-width: 100%; overflow-x: auto; }
          /* Decision prose and alerts can cross the Cloud host-control
             footprint; reserve only those exposed customer surfaces. */
          [class*="st-key-vnext_ask_atlas"] { margin-right:6.5rem; max-width:calc(100% - 6.5rem); }
          /* Protect the action text from the host controls without narrowing
             the alert component itself. */
          [class*="st-key-vnext_decision_action"] [data-testid="stAlert"] {
            margin-right:0 !important;
            max-width:100% !important;
          }
          [class*="st-key-vnext_decision_action"] [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
            padding-right:4.25rem !important;
          }
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
    _render_watching_next(report)
    _render_ask_cta(report)


def render_full_research_vnext(row: Mapping[str, Any]) -> None:
    """Build and render the canonical report through the active UX-2 surface.

    This is the single runtime activation boundary used by the final app route,
    V104 compatibility entry points, and the preserved V2 adapter.  Importing
    the legacy module at call time intentionally avoids retaining a stale
    pre-deployment renderer function in a long-lived Streamlit process.
    """
    from engines.atlas_research_builder_v2 import build_atlas_research_v2
    from services.research_render_diagnostics import checkpoint
    import ui.research_report_v2 as legacy_report

    research_row = dict(row)
    symbol = str(research_row.get("ticker") or research_row.get("Ticker") or "").strip().upper()
    canonical_context = (
        research_row.get("research_context")
        if isinstance(research_row.get("research_context"), Mapping) else {}
    )
    canonical_families = (
        canonical_context.get("evidence_families")
        if isinstance(canonical_context.get("evidence_families"), Mapping) else {}
    )
    from services.fmp_phase1_intelligence import load_cached_phase1_families
    cached_phase1 = load_cached_phase1_families(
        symbol,
        security_type=str(research_row.get("security_type") or research_row.get("Security Type") or "EQUITY"),
    )
    canonical_context = dict(canonical_context)
    canonical_context["evidence_families"] = {**dict(canonical_families), **cached_phase1}
    research_row["research_context"] = canonical_context
    canonical_families = canonical_context["evidence_families"]
    action_family = (
        canonical_families.get("analyst_actions")
        if isinstance(canonical_families.get("analyst_actions"), Mapping) else {}
    )
    action_data = action_family.get("data") if isinstance(action_family.get("data"), Mapping) else {}
    canonical_actions = action_data.get("actions") or []
    retrieval = {
        "actions": canonical_actions,
        "cache_hit": action_family.get("cache_status") in {"FRESH_CACHE", "STALE_FALLBACK"},
        "retrieval_seconds": 0.0,
        "request_count": 0,
        "provider": action_family.get("provider"),
        "fallback_reason": action_family.get("fallback_reason"),
    }
    research_row["analyst_actions"] = canonical_actions
    policy_retrieval = legacy_report._load_policy_enrichment(symbol, research_row)
    research_row["policy_intelligence_external"] = policy_retrieval
    research_row["ai_valuation_external"] = legacy_report._load_ai_valuation(symbol, research_row)
    checkpoint("build_atlas_research_v2:call")
    report = build_atlas_research_v2(research_row)
    checkpoint("build_atlas_research_v2:return")
    report["analyst_action_retrieval"] = retrieval
    report["policy_source_metrics"] = policy_retrieval.get("metrics") or {}
    legacy_report._inject_visual_standards()
    legacy_report._render_architecture_qa_markers(report)
    banner_state = _scalar_text(
        _decision_value(report, "recommendation", "committee_verdict"),
        "Unavailable",
    ).replace("_", " ").title()

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
            {escape(banner_state)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_research_vnext(
        report,
        legacy={
            "valuation": legacy_report._render_hybrid_valuation,
            "analyst": legacy_report._render_analyst_intelligence,
            "meta": legacy_report._meta,
            "metric_grid": legacy_report._metric_grid,
            "interpretation": legacy_report._render_interpretation,
            "trade_plan": legacy_report._render_trade_plan,
            "price_chart": legacy_report._render_price_chart,
            "policy": legacy_report._render_policy_intelligence,
        },
    )


__all__ = [
    "RESEARCH_EVIDENCE_MIGRATION", "RESEARCH_VNEXT_SECTIONS",
    "RESEARCH_VNEXT_VERSION", "build_research_decision_view",
    "render_full_research_vnext", "render_research_vnext",
]
