"""Guidance-first Home VNext presentation."""

from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import streamlit as st

from engines.research_engine import begin_research_entry, research_interaction_contract
from ui.market_timestamp import format_market_timestamp_et


def _display(value: Any) -> str:
    if value is None or value == "":
        return "Unavailable"
    return str(value).replace("_", " ").title()


def _score(value: Any, *, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    try:
        number = float(value)
        return f"{number:,.1f}{suffix}"
    except (TypeError, ValueError):
        return "Unavailable"


def _money(value: Any) -> str:
    if value is None:
        return "Unavailable"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _timestamp(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(ZoneInfo("America/New_York")).strftime("%b %-d, %Y · %-I:%M %p ET")
    except (TypeError, ValueError):
        return "Timestamp unavailable"


def _open_research(ticker: str, key: str) -> None:
    contract = research_interaction_contract(ticker, key)
    st.markdown(
        f'<span data-atlas-qa="home-guidance-research-cta" data-atlas-ticker="{html.escape(ticker)}" '
        f'data-atlas-interaction-id="{html.escape(contract["interaction_id"])}" '
        f'data-atlas-expected-page="{html.escape(contract["expected_page"])}" '
        f'data-atlas-expected-ticker="{html.escape(contract["expected_ticker"])}" aria-hidden="true" '
        'style="display:none">home-guidance-research-cta</span>', unsafe_allow_html=True,
    )
    if st.button(f"View Full Investment Case — {ticker}", key=key, type="primary", width="stretch"):
        begin_research_entry(
            st.session_state, ticker, source="HOME_GUIDANCE_VNEXT",
            interaction_id=contract["interaction_id"],
        )
        st.rerun()


def _metric(label: str, value: str) -> str:
    normalized = str(value or "").strip().lower()
    availability_class = " atlas-home-guidance-unavailable" if normalized in {
        "unavailable", "data unavailable", "not applicable", "timestamp unavailable",
    } else ""
    return (
        f'<span class="atlas-home-guidance-metric{availability_class}">'
        f'<small>{html.escape(label)}</small><b>{html.escape(value)}</b></span>'
    )


def _evidence_value(value: Any, status: Any, *, money: bool = False) -> str:
    """Prefer the canonical value; otherwise retain its canonical availability."""
    if value is not None and value != "":
        return _money(value) if money else _display(value)
    normalized = str(status or "DATA_UNAVAILABLE").upper()
    if normalized == "NOT_APPLICABLE":
        return "Not applicable"
    return "Unavailable"


def _compact_number(value: Any) -> str:
    if value is None:
        return "Unavailable"
    try:
        amount = float(value)
        if abs(amount) >= 1_000_000_000:
            return f"{amount / 1_000_000_000:,.1f}B"
        if abs(amount) >= 1_000_000:
            return f"{amount / 1_000_000:,.1f}M"
        return f"{amount:,.1f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _ratio(value: Any) -> str:
    """Preserve meaningful persisted ratio precision without inventing it."""
    if value is None:
        return "Unavailable"
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "Unavailable"


def _atlas_score_presentation(value: Any) -> dict[str, Any]:
    """Map canonical Scan Conviction into display-only Home score treatment."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return {
            "available": False, "display": "Unavailable", "band": "Unavailable",
            "tone": "unavailable", "stars": "☆☆☆☆☆", "filled_stars": 0,
        }
    if not (-1_000_000 < score < 1_000_000):
        return {
            "available": False, "display": "Unavailable", "band": "Unavailable",
            "tone": "unavailable", "stars": "☆☆☆☆☆", "filled_stars": 0,
        }
    if score >= 90:
        band, tone, filled = "Exceptional", "exceptional", 5
    elif score >= 80:
        band, tone, filled = "Strong", "strong", 4
    elif score >= 70:
        band, tone, filled = "Constructive", "constructive", 3
    elif score >= 60:
        band, tone, filled = "Developing", "developing", 2
    else:
        band, tone, filled = "Weak", "weak", 1
    number = f"{score:,.1f}".rstrip("0").rstrip(".")
    return {
        "available": True, "display": f"{number} / 100", "band": band,
        "tone": tone, "stars": "★" * filled + "☆" * (5 - filled),
        "filled_stars": filled, "star_fill_percent": max(0.0, min(100.0, score)),
    }


def _atlas_score(card: Mapping[str, Any]) -> str:
    score = _atlas_score_presentation(card.get("scan_conviction"))
    limited = _customer_state(card).upper() in {"DATA_LIMITED", "WITHHELD"}
    unavailable = str(card.get("actionability") or "").upper() == "UNAVAILABLE"
    sublabel = (
        f'{score["band"]} setup quality, but not yet actionable.'
        if score["available"] and (limited or unavailable)
        else "Setup quality is shown separately from Guidance and Actionability."
    )
    canonical_value = card.get("scan_conviction")
    return (
        f'<div class="atlas-home-atlas-score atlas-home-score-{score["tone"]}" '
        f'data-atlas-qa="home-atlas-score" data-atlas-score-source="SCAN_CONVICTION" '
        f'data-atlas-score-value="{html.escape(str(canonical_value if canonical_value is not None else "UNAVAILABLE"))}" '
        f'data-atlas-score-band="{html.escape(score["band"])}">'
        '<span class="atlas-home-score-label">ATLAS Setup Score</span>'
        f'<strong>{html.escape(score["display"])}</strong>'
        f'<span class="atlas-home-score-stars" aria-hidden="true" data-atlas-display-only="true" '
        f'style="--atlas-star-fill:{score.get("star_fill_percent", 0):.1f}%">★★★★★</span>'
        f'<b>{html.escape(score["band"] + " Setup" if score["available"] else score["band"])}</b>'
        f'<small>{html.escape(sublabel)}</small>'
        '</div>'
    )


def _market_evidence_badge(card: Mapping[str, Any]) -> str:
    evidence = card.get("market_evidence") if isinstance(card.get("market_evidence"), Mapping) else {}
    status = str(evidence.get("status") or "UNAVAILABLE").upper()
    if status == "LIVE":
        age = _score(evidence.get("freshness_age_seconds"), suffix=" seconds ago")
        label, detail, tone = "LIVE", f"Updated {age}", "live"
    elif status in {"STALE", "LAST_KNOWN"}:
        session = str(evidence.get("market_session") or "UNKNOWN").replace("_", " ").title()
        timestamp = format_market_timestamp_et(evidence.get("provider_timestamp"))
        label = "LAST KNOWN" if status == "LAST_KNOWN" else "STALE"
        detail, tone = f"{session} · {timestamp} · Last known", "stale"
    else:
        label, detail, tone = "PRICE UNAVAILABLE", "Price context is not currently displayed", "unavailable"
    quality = card.get("completed_bar_quality") if isinstance(card.get("completed_bar_quality"), Mapping) else {}
    warning = (
        '<i class="atlas-home-quality-warning" title="Some market observations may have gaps" '
        'aria-label="Market evidence quality notice">ⓘ</i>'
        if str(quality.get("status") or "").upper() == "DEGRADED" else ""
    )
    return (
        f'<div class="atlas-home-market-badge atlas-home-market-{tone}" data-atlas-market-status="{status}" '
        f'data-atlas-market-source="{html.escape(str(evidence.get("source_type") or "UNAVAILABLE"))}">'
        f'<b>{label}</b><span>{html.escape(detail)}</span>{warning}</div>'
    )
def _paid_client_full_evidence(card: Mapping[str, Any]) -> str:
    """Customer research dossier; canonical values are displayed, never recalculated."""
    evaluation = dict(card.get("evaluation") or {})
    canonical_valuation = dict(evaluation.get("atlas_valuation") or {})
    professional = dict(canonical_valuation.get("professional_valuation_v2") or {})
    validation = dict(evaluation.get("valuation_validation") or {})
    fundamentals = dict(card.get("fundamentals_evidence") or {})
    company = dict(card.get("company_evidence") or {})
    technical = dict(card.get("canonical_technical_evidence") or card.get("technical_evidence") or {})
    volume = dict(card.get("volume_evidence") or {})
    street = dict(card.get("wall_street") or {})
    trade = dict(card.get("trade_plan") or {})
    context = dict(card.get("context_evidence") or {})
    lanes = dict(card.get("internal_evidence_lanes") or {})
    valuation_inputs = dict(evaluation.get("trial_presentation_fields") or {})

    def rows(values: Sequence[tuple[str, Any, str]]) -> str:
        rendered = []
        for label, value, kind in values:
            if value is None or value == "" or value == () or value == []:
                continue
            display = _money(value) if kind == "money" else _score(value, suffix="%") if kind == "pct" else _score(value) if kind == "score" else _display(value)
            rendered.append(f'<span><small>{html.escape(label)}</small><b>{html.escape(display)}</b></span>')
        return '<div class="atlas-home-dossier-grid">' + "".join(rendered) + "</div>" if rendered else '<p class="atlas-home-muted">Detailed evidence not available</p>'

    action = dict(card.get("customer_action") or {})
    decision = rows((
        ("Customer Action", f'{action.get("stars", "")} {action.get("label", "WATCH")}', "text"),
        ("Opportunity", card.get("opportunity"), "score"),
        ("Decision Confidence", card.get("decision_confidence"), "pct"),
        ("Evidence Coverage", card.get("component_coverage"), "pct"),
        ("Opportunity Thesis", card.get("opportunity_thesis"), "text"),
        ("Valuation Confidence", professional.get("valuation_confidence"), "pct"),
        ("Evaluated", _timestamp(card.get("evaluation_timestamp")), "text"),
        ("Discovery Setup Quality", _atlas_score_presentation(card.get("scan_conviction"))["display"], "text"),
    ))
    pillars = [(label, dict(evaluation.get(key) or {}).get("score"), "score") for label, key in (
        ("Technical Quality", "technical_quality"), ("Fundamental Quality", "fundamental_quality"),
        ("Valuation Quality", "valuation_quality"), ("Risk Quality", "risk_quality"),
        ("Entry Quality", "entry_quality"), ("Volume Quality", "volume_quality"),
    )]
    validation_state = str(validation.get("certification_state") or "")
    validation_copy = {
        "CERTIFIED": "Validated",
        "CERTIFIED_HIGH_UNCERTAINTY": "Validated with high uncertainty",
        "REVIEW_REQUIRED": "Under review — not displayed as a confident customer fair value",
        "INSUFFICIENT_INPUTS": "Not published — supporting inputs are incomplete",
        "NOT_APPLICABLE": "Not applicable for this company",
    }.get(validation_state)
    customer_value_allowed = validation.get("customer_publication_allowed") is not False
    valuation = rows((
        ("Current Price", card.get("display_price"), "money"),
        ("ATLAS Base Fair Value", professional.get("atlas_base_fair_value") if professional.get("status") == "PUBLISHED" and customer_value_allowed else card.get("atlas_fair_value") if str(card.get("atlas_valuation_status")).upper() == "PUBLISHED" and customer_value_allowed else None, "money"),
        ("Model Valuation Range", f'{_money(professional.get("atlas_fair_value_low"))}–{_money(professional.get("atlas_fair_value_high"))}' if customer_value_allowed and professional.get("atlas_fair_value_low") is not None and professional.get("atlas_fair_value_high") is not None else None, "text"),
        ("Scenario Range", f'{_money(professional.get("atlas_bear_case"))}–{_money(professional.get("atlas_bull_case"))}' if customer_value_allowed and professional.get("atlas_bear_case") is not None and professional.get("atlas_bull_case") is not None else None, "text"),
        ("Expected Return", card.get("atlas_expected_return") if customer_value_allowed else None, "pct"),
        ("Valuation Confidence", professional.get("valuation_confidence"), "pct"),
        ("Evidence Strength", (validation.get("valuation_evidence_strength") or professional.get("valuation_evidence_strength") or {}).get("classification"), "text"),
        ("Valuation Review", validation_copy, "text"),
        ("Publication Status", "Published" if str(card.get("atlas_valuation_status")).upper() == "PUBLISHED" else "Not Published", "text"),
        ("Methodology", professional.get("valuation_methodology_version") or canonical_valuation.get("methodology_version"), "text"),
        ("Valuation As Of", _timestamp(card.get("evaluation_timestamp")), "text"),
        ("Forward EPS", company.get("forward_eps"), "money"),
        ("Forward Revenue", company.get("forward_revenue"), "money"),
        ("Forward Fiscal Period", company.get("forward_eps_period") or company.get("forward_revenue_period"), "text"),
    ))
    drivers = dict(card.get("valuation_driver_evidence") or {})
    driver_bits = []
    if drivers.get("forward_eps") is not None: driver_bits.append(f'forward EPS of {_money(drivers["forward_eps"])}')
    if drivers.get("justified_pe") is not None: driver_bits.append(f'a {_score(drivers["justified_pe"])}× justified earnings multiple')
    if drivers.get("growth_input_pct") is not None: driver_bits.append(f'a {_score(drivers["growth_input_pct"], suffix="%")} growth input')
    driver_summary = "ATLAS fair value is supported by " + ", ".join(driver_bits) + "." if driver_bits else "ATLAS valuation attribution is not detailed enough to publish an economic driver summary."
    model_rows = []
    for model in professional.get("models") or ():
        if not isinstance(model, Mapping):
            continue
        label = str(model.get("name") or "Valuation method")
        if model.get("status") == "PUBLISHED" and not customer_value_allowed:
            value = "Withheld pending validation review"
        elif model.get("status") == "PUBLISHED":
            assumptions = dict(model.get("key_assumptions") or {})
            key_assumption = assumptions.get("multiple_basis") or (f'WACC {_score(float(assumptions["wacc"])*100, suffix="%")}' if assumptions.get("wacc") is not None else None)
            period = f' · {model.get("fiscal_period")}' if model.get("fiscal_period") else ''
            detail = f' · {key_assumption}' if key_assumption else ''
            value = f'{_money(model.get("value"))} · {_score(float(model.get("weight") or 0) * 100, suffix="% weight")} · {_score(model.get("confidence"), suffix="% confidence")}{period}{detail}'
        elif model.get("status") == "NOT_APPLICABLE":
            value = "Not Applicable"
        else:
            value = f'Not Published · {_display(model.get("reason"))}' if model.get("reason") else "Not Published"
        model_rows.append((label, value, "text"))
    valuation_methods = rows(tuple(model_rows)) if model_rows else '<p class="atlas-home-muted">Professional valuation model detail is not yet published</p>'
    scenarios = rows((("Bear Case", professional.get("atlas_bear_case"), "money"),
                      ("Base Case", professional.get("atlas_base_fair_value"), "money"),
                      ("Bull Case", professional.get("atlas_bull_case"), "money"))) if customer_value_allowed and professional.get("scenario_status")=="PUBLISHED" else '<p class="atlas-home-muted">Independent bear and bull scenario evidence is not available; ATLAS publishes only the base estimate.</p>' if customer_value_allowed else '<p class="atlas-home-muted">Scenario values are withheld pending validation review.</p>'
    sensitivity_rows = tuple(
        (f'WACC {_score(float(item.get("wacc")) * 100, suffix="%")} · growth {_score(float(item.get("terminal_growth")) * 100, suffix="%")}', item.get("fair_value"), "money")
        for item in (professional.get("sensitivity") or ()) if isinstance(item, Mapping)
    )
    sensitivity = rows(sensitivity_rows) if sensitivity_rows and customer_value_allowed else '<p class="atlas-home-muted">Sensitivity is not published without complete validated scenario inputs</p>'
    diagnostics = dict(professional.get("valuation_diagnostics") or {})
    explanation = dict(professional.get("valuation_explanation") or {})
    customer_flag_labels = {
        "MODEL_DISPERSION_HIGH": "Professional methods produce materially different estimates.",
        "FAIR_VALUE_RANGE_WIDE": "The published fair-value range is wide.",
        "TERMINAL_VALUE_DEPENDENCE_HIGH": "A large share of DCF value depends on long-term assumptions.",
        "BULL_CASE_EXTREME": "The bull case requires especially favorable assumptions.",
        "BEAR_BASE_GAP_HIGH": "The downside scenario sits materially below the base case.",
        "MODEL_CONCENTRATION_SINGLE_METHOD": "Only one complete professional method supports this valuation.",
        "SENSITIVITY_WIDE": "Fair value is highly sensitive to discount-rate and growth assumptions.",
        "WACC_BELOW_RISK_FREE": "The blended discount rate is below the Treasury benchmark because lower after-tax debt cost reduces the weighted average.",
        "WACC_G_SPREAD_BELOW_1PCT": "The discount rate is less than one percentage point above long-run growth, creating extreme terminal sensitivity.",
        "WACC_G_SPREAD_BELOW_1_5PCT": "The discount-rate cushion above long-run growth is unusually narrow.",
        "WACC_G_SPREAD_BELOW_2PCT": "The discount-rate cushion above long-run growth is narrow.",
    }
    uncertainty_items = [customer_flag_labels[flag] for flag in diagnostics.get("flags") or () if flag in customer_flag_labels]
    uncertainty = (
        '<ul>' + ''.join(f'<li>{html.escape(item)}</li>' for item in uncertainty_items) + '</ul>'
        if uncertainty_items else '<p class="atlas-home-muted">No elevated valuation-uncertainty signal was identified.</p>'
    )
    explainability = rows(tuple((label, explanation.get(key), "text") for label, key in (
        ("Primary Driver", "primary_valuation_driver"),
        ("Secondary Driver", "secondary_valuation_driver"),
        ("Biggest Uncertainty", "biggest_valuation_uncertainty"),
        ("ATLAS vs Street", "atlas_vs_street"),
        ("Scenario Risk", "scenario_risk"),
    )))
    peer_rows=[]
    for model in professional.get("models") or ():
        peer_evidence=dict((model.get("key_assumptions") or {}).get("peer_evidence") or {})
        for peer in peer_evidence.get("included_peers") or ():
            if isinstance(peer,Mapping):
                peer_rows.append((f'{peer.get("peer_ticker")} · {peer.get("peer_company_name")}',
                                  f'{_score(peer.get("multiple"))}× · {_display(peer.get("basis"))} · {_display(peer.get("provider"))}',"text"))
    peer_section=rows(tuple(peer_rows)) if peer_rows else '<p class="atlas-home-muted">No independently auditable peer basket is published for the available method.</p>'
    dcf_model = next((model for model in professional.get("models") or () if model.get("methodology_id") == "VAL_FCFF_DCF_V1" and model.get("status") == "PUBLISHED"), {})
    dcf_assumptions = dict(dcf_model.get("key_assumptions") or {})
    discount_rate_evidence = rows((
        ("WACC", dcf_assumptions.get("wacc") * 100 if dcf_assumptions.get("wacc") is not None else None, "pct"),
        ("Risk-Free Rate", valuation_inputs.get("risk_free_rate") * 100 if valuation_inputs.get("risk_free_rate") is not None else None, "pct"),
        ("Equity Risk Premium", valuation_inputs.get("equity_risk_premium") * 100 if valuation_inputs.get("equity_risk_premium") is not None else None, "pct"),
        ("Beta", valuation_inputs.get("beta"), "score"), ("Cost of Equity", valuation_inputs.get("cost_of_equity") * 100 if valuation_inputs.get("cost_of_equity") is not None else None, "pct"),
        ("Terminal Growth", dcf_assumptions.get("terminal_growth") * 100 if dcf_assumptions.get("terminal_growth") is not None else None, "pct"),
        ("Terminal Value / EV", dcf_assumptions.get("terminal_value_pct_of_enterprise_value") * 100 if dcf_assumptions.get("terminal_value_pct_of_enterprise_value") is not None else None, "pct"),
    ))

    street_visible = street.get("commercial_display_status") == "DISPLAY_ALLOWED" or street.get("display_scope") == "INTERNAL_TRIAL"
    street_section = rows((
        ("Consensus", street.get("rating") if street_visible else None, "text"),
        ("Analyst Count", street.get("analyst_count") if street_visible else None, "score"),
        ("Average Target", street.get("mean_target") if street_visible else None, "money"),
        ("Low Target", street.get("low_target") if street_visible else None, "money"),
        ("High Target", street.get("high_target") if street_visible else None, "money"),
        ("Street Implied Upside", street.get("implied_upside") if street_visible else None, "pct"),
        ("ATLAS vs Street", explanation.get("atlas_vs_street") if street_visible else None, "text"),
        ("Data As Of", _timestamp(card.get("evaluation_timestamp")) if street_visible else None, "text"),
    )) if street_visible else '<p class="atlas-home-muted">Wall Street outlook not published in this display mode</p>'
    estimate_evidence = dict(company.get("forward_estimate_evidence") or {})
    estimate_rows = []
    for label, singular, plural in (("Forward EPS", "eps", "eps_periods"), ("Forward Revenue", "revenue", "revenue_periods")):
        period_items = estimate_evidence.get(plural) or ([estimate_evidence.get(singular)] if estimate_evidence.get(singular) else [])
        for item in period_items:
          if isinstance(item, Mapping):
            period = item.get("period") or item.get("date")
            average = item.get("avg_estimate") if item.get("avg_estimate") is not None else item.get("average")
            if average is not None:
                estimate_rows.append((f'{label} · {_display(period)}', average, "money"))
            for suffix, key in (("Low", "low_estimate"), ("High", "high_estimate"), ("Analysts", "number_of_analysts")):
                if item.get(key) is not None: estimate_rows.append((f"{label} {suffix}", item.get(key), "score" if key == "number_of_analysts" else "money"))
    forward_estimates = rows(tuple(estimate_rows)) if estimate_rows else '<p class="atlas-home-muted">Forward estimate detail not available</p>'
    eps_estimates = rows(tuple(item for item in estimate_rows if item[0].startswith("Forward EPS")))
    revenue_estimates = rows(tuple(item for item in estimate_rows if item[0].startswith("Forward Revenue")))
    revision_history = dict(company.get("estimate_revision_history") or {})
    revision_rows = [
        (f'{item.get("metric")} · {item.get("estimate_period")} · {item.get("horizon_days")}D', item.get("revision_pct"), "pct")
        for item in revision_history.get("horizon_comparisons") or () if isinstance(item, Mapping) and item.get("revision_pct") is not None
    ]
    revision_section = rows(tuple(revision_rows)) if revision_rows else '<p class="atlas-home-muted">Revision history not yet sufficient</p>'

    financial = rows((
        ("Revenue", fundamentals.get("revenue"), "money"), ("YoY Revenue Growth", fundamentals.get("revenue_growth"), "pct"),
        ("EPS", fundamentals.get("eps"), "money"), ("EPS Growth", company.get("earnings_growth"), "pct"),
        ("Gross Margin", fundamentals.get("gross_margin"), "pct"), ("Operating Margin", fundamentals.get("operating_margin"), "pct"),
        ("Net Margin", fundamentals.get("net_margin"), "pct"), ("Operating Cash Flow", fundamentals.get("operating_cash_flow"), "money"),
        ("Free Cash Flow", fundamentals.get("free_cash_flow"), "money"), ("Cash", fundamentals.get("cash"), "money"),
        ("Total Debt", fundamentals.get("debt"), "money"),
        ("EBITDA Margin", fundamentals.get("ebitda_margin"), "pct"),
        ("Net Debt / EBITDA", fundamentals.get("net_debt_to_ebitda"), "score"),
        ("Return on Equity", fundamentals.get("roe"), "pct"), ("Return on Invested Capital", fundamentals.get("roic"), "pct"),
        ("Reporting Period", fundamentals.get("reporting_period"), "text"), ("Financial As Of", fundamentals.get("financial_as_of"), "text"),
    ))
    earnings = rows((
        ("Earnings Date", company.get("latest_earnings_date"), "text"), ("EPS Actual", company.get("reported_eps"), "money"),
        ("EPS Estimate", company.get("eps_estimate"), "money"), ("EPS Surprise", company.get("eps_surprise_pct"), "pct"),
        ("Revenue Actual", company.get("reported_revenue"), "money"), ("Revenue Estimate", company.get("revenue_estimate"), "money"),
        ("Revenue Surprise", company.get("revenue_surprise_pct"), "pct"),
        ("Guidance Direction", company.get("guidance_direction"), "text"),
    ))
    technical_section = rows((
        ("Technical State", _display(card.get("technical_state")) if card.get("technical_status") == "AVAILABLE" else None, "text"),
        ("RSI", technical.get("rsi14") or technical.get("rsi"), "score"),
        ("SMA50", technical.get("sma50"), "money"), ("SMA200", technical.get("sma200"), "money"),
        ("Support", technical.get("support"), "money"), ("Resistance", technical.get("pivot") or technical.get("resistance"), "money"),
        ("Volume State", _display(card.get("volume_state")) if card.get("volume_state") not in {None, "DATA_UNAVAILABLE", "UNAVAILABLE"} else None, "text"), ("Relative Volume", volume.get("relative_volume"), "score"),
        ("20-Day Average Volume", volume.get("average_volume_20d") or volume.get("average_volume"), "score"),
        ("Average Dollar Volume", volume.get("average_dollar_volume"), "money"),
        ("Breakout Confirmation", "Confirmed" if card.get("technical_state") == "BREAKOUT_CONFIRMED" else "Not Confirmed", "text"),
    ))
    trade_values = (
        ("entry", "Preferred Entry", f'{_money(trade.get("entry_low"))}–{_money(trade.get("entry_high"))}' if trade.get("entry_low") is not None and trade.get("entry_high") is not None else None),
        ("stop", "Risk Stop", _money(trade.get("stop") or trade.get("stop_loss")) if trade.get("stop") is not None or trade.get("stop_loss") is not None else None),
        ("target", "Technical Trade Target", _money(trade.get("target_1") or trade.get("target")) if trade.get("target_1") is not None or trade.get("target") is not None else None),
        ("fair-value", "Longer-Term ATLAS Fair Value", _money(card.get("atlas_fair_value")) if str(card.get("atlas_valuation_status")).upper() == "PUBLISHED" else None),
    )
    trade_section = '<div class="atlas-home-trade-row">' + "".join(
        f'<span data-atlas-trade-segment="{kind}"><small>{html.escape(label)}</small><b>{html.escape(value)}</b></span>'
        for kind, label, value in trade_values if value is not None
    ) + "</div>" if any(value is not None for _, _, value in trade_values) else '<p class="atlas-home-muted">No published trade plan</p>'

    why = [text for text in (
        "Published valuation indicates meaningful rerating potential." if card.get("atlas_expected_return") is not None and float(card["atlas_expected_return"]) > 10 else None,
        "Forward revenue and earnings evidence supports future earnings power." if company.get("forward_eps") is not None or company.get("forward_revenue") is not None else None,
        "Price remains in or near the preferred entry area." if card.get("entry_relationship") == "WITHIN_ENTRY_RANGE" else None,
        "The completed-session technical structure remains constructive." if card.get("technical_status") == "AVAILABLE" else None,
    ) if text][:4]
    why_html = "".join(f"<li>{html.escape(item)}</li>" for item in why) or "<li>The current evidence does not support a stronger customer-readable reason.</li>"
    state = _customer_state(card)
    change = {
        "BUY_NOW": "The rating would weaken if forward estimates deteriorate, support fails, or expected return falls below the governed threshold.",
        "ACCUMULATE": "The rating can improve as the thesis confirms; it would weaken if earnings, valuation, or support deteriorates.",
        "WAIT_FOR_ENTRY": "The rating can improve if price returns to the preferred entry area without damaging the business thesis.",
        "WAIT_FOR_CONFIRMATION": "The rating can improve when price structure or participation provides the required confirmation.",
        "DATA_LIMITED": "The rating can improve when sufficient current financial, valuation, and market evidence becomes available.",
        "AVOID": "The rating can improve only after the cited risk and fundamental evidence materially changes.",
    }.get(state, "The rating changes only when the underlying investment evidence changes.")

    catalysts = "".join(
        f'<article><small>{html.escape(format_market_timestamp_et(item.get("published_at"), unavailable="Date not available"))} · {html.escape(str(item.get("publisher") or item.get("source") or "Source"))}</small><b>{html.escape(str(item.get("headline") or item.get("title")))}</b><span>{html.escape(str(item.get("why_it_matters") or item.get("summary") or "May affect forward estimates or execution."))}</span></article>'
        for item in (card.get("recent_catalysts") or ())[:3] if item.get("headline") or item.get("title")
    ) or '<p class="atlas-home-muted">No licensed material catalyst is currently available</p>'
    insider = dict(context.get("insider") or {})
    institutional = dict(context.get("institutional") or {})
    political = dict(context.get("political") or {})
    context_section = rows((
        ("Insider Direction", insider.get("activity"), "text"), ("Open-Market Buys", insider.get("buy_count"), "score"),
        ("Open-Market Sells", insider.get("sell_count"), "score"), ("Institutional Ownership", institutional.get("ownership_pct"), "pct"),
        ("Institutional Trend", institutional.get("trend"), "text"), ("Congressional Activity", political.get("summary"), "text"),
    ))
    sources = []
    for label, source, stamp in (
        ("Market", (card.get("market_evidence") or {}).get("provider"), (card.get("market_evidence") or {}).get("provider_timestamp")),
        ("Valuation", "ATLAS", card.get("evaluation_timestamp")),
        ("Financials", "Twelve Data / persisted fundamentals", card.get("evaluation_timestamp")),
        ("Technical", "Twelve Data completed-session history", card.get("latest_rating_as_of")),
    ):
        if source: sources.append(f"{label}: {source} · {_timestamp(stamp)}")
    source_html = "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in sources) + "</ul>"
    return (
        '<div class="atlas-home-full-evidence atlas-home-paid-dossier" data-atlas-qa="home-guidance-full-evidence">'
        f'<section><h4>Decision Summary</h4>{decision}{rows(pillars)}</section>'
        f'<section><h4>{"Why ATLAS Dislikes It" if state == "AVOID" else "Why ATLAS Likes It"}</h4><ul>{why_html}</ul><p><b>Main Constraint / Risk:</b> {html.escape(_decisive_customer_constraint(card))}</p></section>'
        f'<section><h4>ATLAS Professional Valuation</h4>{valuation}<p>{html.escape(driver_summary)}</p>{explainability}{uncertainty}{discount_rate_evidence}</section>'
        f'<section><h4>Valuation by Method</h4>{valuation_methods}</section><section><h4>Peer Multiple Evidence</h4>{peer_section}</section><section><h4>Bear / Base / Bull</h4>{scenarios}</section><section><h4>Sensitivity</h4>{sensitivity}</section>'
        f'<section><h4>Wall Street Analyst Outlook</h4>{street_section}</section>'
        f'<section><h4>Forward EPS Estimates</h4>{eps_estimates}</section><section><h4>Forward Revenue Estimates</h4>{revenue_estimates}</section>'
        f'<section><h4>Estimate Revision History</h4>{revision_section}</section>'
        f'<section><h4>Latest Earnings</h4>{earnings}</section><section><h4>Financial Snapshot</h4>{financial}</section>'
        f'<section><h4>Recent Catalysts</h4><div class="atlas-home-catalysts">{catalysts}</div></section>'
        f'<section><h4>Technical &amp; Volume</h4>{technical_section}</section><section><h4>Trade Plan</h4>{trade_section}</section>'
        f'<section><h4>Insider Activity</h4>{rows((("Recent Insider Direction", insider.get("activity"), "text"), ("Open-Market Buys", insider.get("buy_count"), "score"), ("Open-Market Sells", insider.get("sell_count"), "score")))}</section>'
        f'<section><h4>Institutional Ownership</h4>{rows((("Institutional Ownership", institutional.get("ownership_pct"), "pct"), ("Recent Direction", institutional.get("trend"), "text")))}</section>'
        f'<section><h4>Congressional Activity</h4>{rows((("Recent Activity", political.get("summary"), "text"), ("Purchases", political.get("buy_count"), "score"), ("Sales", political.get("sell_count"), "score")))}<p class="atlas-home-muted">Congressional activity is contextual and does not influence the ATLAS rating.</p></section>'
        f'<section><h4>What Could Change the Rating</h4><p>{html.escape(change)}</p></section><section><h4>Evidence Sources</h4>{source_html}</section></div>'
    )


def _decisive_customer_constraint(card: Mapping[str, Any]) -> str:
    state = _customer_state(card)
    if state == "BUY_NOW": return "Forward estimates, valuation support, and price structure must remain intact."
    if state == "ACCUMULATE": return "The thesis is attractive, but the evidence supports staged rather than full deployment."
    if state == "WAIT_FOR_ENTRY": return "The current price is outside the preferred entry area."
    if state == "WAIT_FOR_CONFIRMATION": return "Technical or participation confirmation remains incomplete."
    if state == "AVOID": return "Current downside evidence outweighs the opportunity."
    return "The evidence is not complete enough for capital deployment."


def _full_evidence(card: Mapping[str, Any]) -> str:
    """Compatibility entry point for the paid-client dossier."""
    return _paid_client_full_evidence(card)


def _clean_checkpoint(value: Any) -> str:
    cleaned = str(value or "").strip().rstrip(".")
    for suffix in (" is required", " must be published"):
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    return cleaned


def _atlas_observations(card: Mapping[str, Any]) -> tuple[str, ...]:
    """Select at most four sourced observations without promoting authority."""
    persisted_technical = card.get("technical_evidence") or {}
    canonical_technical = card.get("canonical_technical_evidence") or {}
    technical = canonical_technical or persisted_technical
    volume = card.get("volume_evidence") or {}
    recovery = card.get("recovery") or {}
    trade = card.get("trade_plan") or {}
    price = card.get("display_price")
    items: list[str] = []
    low, high = trade.get("entry_low"), trade.get("entry_high")
    relationship = str(card.get("entry_relationship") or "")
    if price is not None and low is not None and high is not None:
        relation = {
            "WITHIN_ENTRY_RANGE": "remains within",
            "BELOW_ENTRY_RANGE": "is below",
            "ABOVE_ENTRY_RANGE": "is above",
        }.get(relationship, "is measured against")
        items.append(f'{card.get("display_price_label") or "Price"} {_money(price)} {relation} the {_money(low)}–{_money(high)} entry range')
    above = []
    below = []
    canonical_state = (
        str(card.get("technical_state") or "").replace("_", " ").title()
        if str(card.get("technical_status") or "").upper() == "AVAILABLE" else ""
    )
    persisted_price = technical.get("close") if canonical_technical else technical.get("price")
    for label, key in (("SMA20", "sma20"), ("SMA50", "sma50"), ("SMA200", "sma200")):
        average = technical.get(key)
        if persisted_price is not None and average is not None:
            (above if persisted_price >= average else below).append(label)
    if above or below:
        structure = []
        if above: structure.append("above " + " / ".join(above))
        if below: structure.append("below " + " / ".join(below))
        if canonical_state:
            evidence_label = "canonical daily structure" if canonical_technical else "persisted price structure"
            items.append(f"Canonical Technical State is {canonical_state}; {evidence_label} is " + " and ".join(structure))
        else:
            items.append("Persisted price structure is " + " and ".join(structure))
    elif canonical_state:
        items.append(f"Canonical Technical State is {canonical_state}")
    if recovery.get("score") is not None:
        state = str(recovery.get("state") or "").replace("🟢", "").replace("🟡", "").strip()
        items.append(f"Recovery Score is {_score(recovery.get('score'))}" + (f" — {state}" if state else ""))
    if volume.get("relative_volume") is not None:
        items.append(f"Persisted contextual relative volume is {_ratio(volume.get('relative_volume'))}×")
    return tuple(items[:4])


def _quick_known(card: Mapping[str, Any]) -> tuple[str, ...]:
    """Compatibility alias for the bounded sourced-observation contract."""
    return _atlas_observations(card)


def _quick_needs(card: Mapping[str, Any]) -> tuple[str, ...]:
    labels = {
        "CURRENT_MARKET_EVIDENCE_UNAVAILABLE": "Fresh exact-symbol current-price authority",
        "TECHNICAL_STRUCTURE_UNAVAILABLE": "Canonical technical state",
        "PRICE_EVIDENCE_UNAVAILABLE": "Valid approved price evidence",
        "BASIC_FUNDAMENTALS_UNAVAILABLE": "Canonical fundamental evidence",
        "RISK_EVIDENCE_UNAVAILABLE": "Canonical risk evidence",
        "BREAKOUT_VOLUME_NOT_CONFIRMED": "Approved breakout-volume confirmation",
        "VOLUME_CONFIRMATION_UNAVAILABLE": "Approved volume-confirmation authority",
        "VALUATION_CONFIRMATION_UNAVAILABLE": "Published canonical valuation confirmation",
        "TRADE_PLAN_INCOMPLETE": "Complete canonical trade plan",
    }
    codes = tuple(str(code) for code in card.get("reason_codes") or ())
    if codes:
        return tuple(labels[code] if code in labels else code.replace("_", " ").title() for code in codes)[:3]
    values = card.get("what_changes_guidance") or ()
    return tuple(_clean_checkpoint(value) for value in values if _clean_checkpoint(value))[:3]


def _guidance_explanation(card: Mapping[str, Any]) -> str:
    codes = tuple(str(code) for code in card.get("reason_codes") or ())
    copy = {
        "ALL_BUY_NOW_GATES_PASSED": "Business quality, valuation, risk, entry conditions and price structure support initiating a position.",
        "ALL_ACCUMULATE_GATES_PASSED": "The investment case supports beginning with a partial position and adding only as the thesis confirms.",
        "CURRENT_MARKET_EVIDENCE_UNAVAILABLE": "The opportunity is worth watching, but ATLAS needs fresher market evidence before recommending a position.",
        "TECHNICAL_STRUCTURE_UNAVAILABLE": "The setup has not produced enough confirmed technical evidence for ATLAS to recommend an entry yet.",
        "PRICE_EVIDENCE_UNAVAILABLE": "ATLAS is waiting for a reliable price observation before judging the entry.",
        "BREAKOUT_VOLUME_NOT_CONFIRMED": "The price setup is constructive, but participation has not confirmed the move yet.",
        "VOLUME_CONFIRMATION_UNAVAILABLE": "The setup still needs stronger participation before ATLAS can recommend an entry.",
        "PRICE_ABOVE_ENTRY_RANGE": "The thesis remains constructive, but the current price is above ATLAS's preferred entry range.",
        "TECHNICAL_STATE_EXTENDED": "Momentum is constructive, but the shares are extended and offer an unattractive entry today.",
        "BASIC_FUNDAMENTALS_UNAVAILABLE": "ATLAS needs stronger business evidence before recommending capital.",
        "RISK_EVIDENCE_UNAVAILABLE": "The downside case is not sufficiently defined for ATLAS to recommend a position.",
    }
    return next((copy[code] for code in codes if code in copy), "ATLAS is watching the setup, but the evidence is not strong enough for a position yet.")


def _what_changes_call(card: Mapping[str, Any]) -> str:
    needs = _quick_needs(card)
    if not needs:
        return "Guidance will change only when an existing canonical gate produces a different governed result."
    readable = [value[:1].lower() + value[1:] for value in needs]
    conditions = readable[0] if len(readable) == 1 else ", ".join(readable[:-1]) + f" and {readable[-1]}"
    verb = "is" if len(readable) == 1 else "are"
    return f"Guidance can advance only after {conditions} {verb} available; remaining confirmation gates would then be evaluated normally."


def _atlas_summary(card: Mapping[str, Any]) -> str:
    ai_view = card.get("atlas_ai_view") if isinstance(card.get("atlas_ai_view"), Mapping) else {}
    if ai_view.get("text"):
        return str(ai_view["text"])
    from services.atlas_view_summary import build_summary_payload, deterministic_summary
    return deterministic_summary(build_summary_payload(card))


def _quick_evidence(card: Mapping[str, Any]) -> str:
    known = "".join(f'<li>{html.escape(item)}</li>' for item in _atlas_observations(card))
    needed = "".join(f'<li>{html.escape(item)}</li>' for item in _quick_needs(card))
    return (
        '<div class="atlas-home-guidance-quick" data-atlas-qa="home-guidance-quick-evidence">'
        f'<section><h4>What ATLAS sees</h4><ul>{known}</ul></section>'
        f'<section><h4>What ATLAS needs</h4><ul>{needed}</ul></section>'
        '</div>'
    )


def _key_numbers(card: Mapping[str, Any]) -> str:
    persisted_technical = card.get("technical_evidence") or {}
    canonical_technical = card.get("canonical_technical_evidence") or {}
    technical, volume = canonical_technical or persisted_technical, card.get("volume_evidence") or {}
    recovery, trade = card.get("recovery") or {}, card.get("trade_plan") or {}
    values: list[tuple[str, str]] = []
    if card.get("display_price") is not None:
        values.append((str(card.get("display_price_label") or "Price"), _money(card.get("display_price"))))
    if trade.get("entry_low") is not None and trade.get("entry_high") is not None:
        values.append(("Entry Range", f'{_money(trade.get("entry_low"))}–{_money(trade.get("entry_high"))}'))
    rsi = technical.get("rsi14") if canonical_technical else technical.get("rsi")
    if rsi is not None: values.append(("RSI", _score(rsi)))
    if recovery.get("score") is not None: values.append(("Recovery", _score(recovery.get("score"))))
    if volume.get("relative_volume") is not None: values.append(("Contextual RVOL", _ratio(volume.get("relative_volume")) + "×"))
    resistance = technical.get("pivot") if canonical_technical else technical.get("resistance")
    if resistance is not None: values.append(("Resistance", _money(resistance)))
    stop = trade.get("stop") if trade.get("stop") is not None else trade.get("stop_loss")
    target = trade.get("target_1") if trade.get("target_1") is not None else trade.get("target")
    if stop is not None or target is not None:
        values.append(("Stop / Target 1", f'{_money(stop)} / {_money(target)}'))
    if card.get("atlas_fair_value") is not None and str(card.get("atlas_valuation_status") or "").upper() == "PUBLISHED":
        values.append(("Atlas FV", _money(card.get("atlas_fair_value"))))
    cells = "".join(_metric(label, value) for label, value in values[:7])
    return f'<div class="atlas-home-key-numbers" data-atlas-qa="home-key-numbers">{cells}</div>'


def _action_tone(value: Any) -> str:
    state = str(value or "DATA_LIMITED").upper()
    if state in {"BUY_NOW", "BUY", "ACCUMULATE", "BUILD_A_POSITION"}:
        return "positive"
    if state == "AVOID":
        return "negative"
    if state in {"WAIT_FOR_CONFIRMATION", "WAIT_FOR_ENTRY", "WAIT_FOR_BETTER_ENTRY", "DATA_LIMITED", "DECISION_PENDING"}:
        return "waiting"
    return "neutral"


def _customer_state(card: Mapping[str, Any]) -> str:
    return str(card.get("customer_guidance") or card.get("guidance") or "WITHHELD")


def _action_card(card: Mapping[str, Any]) -> str:
    guidance = _customer_state(card)
    action = card.get("customer_action") or {}
    tone = str(action.get("tone") or _action_tone(guidance))
    action_label = str(action.get("label") or "WATCH — NOT READY YET")
    stars = str(action.get("stars") or "")
    thesis = str(card.get("opportunity_thesis") or "").upper()
    thesis_label = {
        "QUALITY_GROWTH": "Quality Growth Opportunity",
        "VALUE_RERATING": "Value / Rerating Opportunity",
        "RECOVERY": "Recovery Opportunity",
        "ATTRACTIVE_ENTRY": "Attractive Entry",
        "BREAKOUT": "Breakout Confirmed",
        "DEVELOPING_SETUP": "Developing Setup",
    }.get(thesis)
    thesis_copy = f'<em>{html.escape(thesis_label)}</em>' if thesis_label else ""
    stars_copy = f'<b class="atlas-home-action-stars">{html.escape(stars)}</b>' if stars else ""
    return (
        f'<div class="atlas-home-action atlas-home-action-{tone}" data-atlas-qa="home-action" '
        f'data-atlas-action-tone="{tone}" data-atlas-star-rating="{html.escape(str(action.get("rating") or 2.5))}" '
        f'data-atlas-opportunity-thesis="{html.escape(thesis)}">'
        f'<small>ATLAS RATING</small>{stars_copy}<strong>{html.escape(action_label)}</strong>'
        f'{thesis_copy}<span>{html.escape(str(action.get("instruction") or _guidance_explanation(card)))}</span></div>'
    )


def _target_tiles(card: Mapping[str, Any]) -> str:
    street = card.get("wall_street") or {}
    published = str(card.get("atlas_valuation_status") or "").upper() == "PUBLISHED"
    values = [("Current", _money(card.get("display_price")) if card.get("display_price") is not None else "Not Published", "current")]
    if published:
        values.extend((
            ("ATLAS Target", _money(card.get("atlas_fair_value")), "atlas"),
            ("ATLAS Upside", _score(card.get("atlas_expected_return"), suffix="%"), "atlas"),
        ))
    else:
        values.append(("ATLAS Target / Upside", "Not Published", "atlas"))
    if street.get("mean_target") is not None:
        values.extend((
            ("Wall Street Avg Target", _money(street.get("mean_target")), "street"),
            ("Wall Street Upside", _score(street.get("implied_upside"), suffix="%"), "street"),
        ))
    else:
        values.append(("Wall Street Target / Upside", "Not Published", "street"))
    tile_parts = []
    for label, value, authority in values:
        muted_class = "atlas-home-target-muted" if value == "Not Published" else ""
        tile_parts.append(
            f'<span class="atlas-home-target atlas-home-target-{authority} {muted_class}">'
            f'<small>{html.escape(label)}</small><b>{html.escape(value)}</b></span>'
        )
    tiles = "".join(tile_parts)
    atlas, street_target = card.get("atlas_fair_value"), street.get("mean_target")
    divergence = ""
    if published and atlas is not None and street_target not in (None, 0):
        gap = ((float(atlas) / float(street_target)) - 1.0) * 100.0
        label = "ATLAS MORE BULLISH" if gap > 15 else "STREET MORE BULLISH" if gap < -15 else "ATLAS + STREET ALIGNED"
        divergence = (
            f'<strong class="atlas-home-divergence" data-atlas-target-gap="{gap:.2f}">{label} · '
            f'{html.escape(_money(atlas))} vs Street {html.escape(_money(street_target))}</strong>'
        )
    return (
        '<div class="atlas-home-comparison" data-atlas-qa="home-target-comparison">'
        f'{tiles}{divergence}<em>Wall Street is external context and does not determine the ATLAS rating.</em></div>'
    )


def _pillar_band(value: Any, status: Any) -> str:
    if str(status or "").upper() not in {"AVAILABLE", "PARTIAL"} or value is None:
        return "Unavailable"
    score = float(value)
    return "Strong" if score >= 80 else "Good" if score >= 65 else "Moderate" if score >= 50 else "Weak"


def _six_pillar_summary(card: Mapping[str, Any]) -> str:
    pillars = card.get("six_pillars") if isinstance(card.get("six_pillars"), Mapping) else {}
    labels = (
        ("Technical", "technical_quality"), ("Fundamentals", "fundamental_quality"),
        ("Valuation", "valuation_quality"), ("Risk", "risk_quality"),
        ("Entry", "entry_quality"), ("Volume", "volume_quality"),
    )
    cells = []
    for label, key in labels:
        item = pillars.get(key) if isinstance(pillars.get(key), Mapping) else {}
        band = _pillar_band(item.get("score"), item.get("status"))
        tone = band.lower()
        cells.append(f'<span class="atlas-home-pillar atlas-home-pillar-{tone}"><small>{label}</small><b>{band}</b></span>')
    return '<div class="atlas-home-pillars" data-atlas-qa="home-six-pillars">' + "".join(cells) + '</div>'


def _technical_cue(card: Mapping[str, Any]) -> str:
    state = str(card.get("technical_state") or "").upper()
    mapping = {
        "NEAR_BREAKOUT": "Near breakout", "BREAKOUT_CONFIRMED": "Constructive trend",
        "SETUP_FORMING": "Constructive trend", "RECOVERING": "Recovering",
        "EXTENDED": "Extended", "TREND_WEAKENING": "Trend weakening",
        "NO_SETUP": "No confirmed setup",
    }
    return mapping.get(state, "Technical cue not published")


def _mini_chart(card: Mapping[str, Any], selected_range: str = "1Y") -> str:
    contract = card.get("home_chart") if isinstance(card.get("home_chart"), Mapping) else {}
    all_bars = [bar for bar in contract.get("bars") or () if isinstance(bar, Mapping) and bar.get("close") is not None]
    counts = {"1M": 23, "3M": 66, "1Y": 260}
    selected_range = selected_range if selected_range in counts else "1Y"
    bars = all_bars[-counts[selected_range]:]
    if str(contract.get("status") or "").upper() != "AVAILABLE" or len(bars) < 2:
        return ""
    closes = [float(bar["close"]) for bar in bars]
    low, high = min(closes), max(closes)
    span = high - low or 1.0
    width, height = 520.0, 148.0
    plot_left, plot_right = 44.0, 518.0
    points = " ".join(
        f"{plot_left + index * (plot_right-plot_left) / (len(closes) - 1):.1f},{height - ((value - low) / span * (height - 18) + 9):.1f}"
        for index, value in enumerate(closes)
    )
    rising = closes[-1] >= closes[0]
    stroke = "#2fb7a4" if rising else "#d66b72"
    trade = card.get("trade_plan") or {}
    entry_low, entry_high = trade.get("entry_low"), trade.get("entry_high")
    chart_overlays = ""
    right_labels: list[tuple[float, str, str, int]] = []
    level_legend: list[tuple[str, str, str]] = []
    for tick in range(4):
        tick_value = low + span * tick / 3
        tick_y = height - ((tick_value - low) / span * (height - 18) + 9)
        chart_overlays += (
            f'<line x1="{plot_left:g}" x2="{plot_right:g}" y1="{tick_y:.1f}" y2="{tick_y:.1f}" '
            'stroke="rgba(148,163,184,.12)" stroke-width="1"/>'
            f'<text x="2" y="{max(9, tick_y+3):.1f}" fill="#7f8da1" font-size="9">{html.escape(_money(tick_value))}</text>'
        )
    technical = card.get("technical_evidence") or {}
    def add_level(value: Any, label: str, color: str, dash: str = "5 5", priority: int = 9) -> None:
        nonlocal chart_overlays
        if value is None or not low <= float(value) <= high:
            return
        y = height - ((float(value) - low) / span * (height - 18) + 9)
        chart_overlays += (
            f'<line x1="{plot_left:g}" x2="{plot_right:g}" y1="{y:.1f}" y2="{y:.1f}" stroke="{color}" '
            f'stroke-width="1.2" stroke-dasharray="{dash}" opacity=".72"/>'
        )
        level_legend.append((label, _money(value), color))
    add_level(technical.get("sma50"), "SMA50", "#b58be8", priority=6)
    add_level(technical.get("sma200"), "SMA200", "#72a7e8", priority=7)
    add_level(technical.get("support"), "Support", "#48b883", "3 5", 5)
    add_level(technical.get("resistance"), "Resistance", "#d7a542", "3 5", 4)
    if entry_low is not None and entry_high is not None:
        zone_low, zone_high = float(entry_low), float(entry_high)
        if zone_high >= low and zone_low <= high:
            top_y = height - ((min(zone_high, high) - low) / span * (height - 18) + 9)
            bottom_y = height - ((max(zone_low, low) - low) / span * (height - 18) + 9)
            chart_overlays += (
                f'<rect x="{plot_left:g}" y="{top_y:.1f}" width="{plot_right-plot_left:g}" height="{max(2.0, bottom_y-top_y):.1f}" '
                f'fill="rgba(93,145,214,.12)"/><text x="{plot_left+6:g}" y="18" fill="#9fc2ed" font-size="12">Entry zone</text>'
            )
    target = card.get("atlas_fair_value") if str(card.get("atlas_valuation_status") or "").upper() == "PUBLISHED" else None
    off_chart_target = ""
    if target is not None:
        if low <= float(target) <= high:
            target_y = height - ((float(target) - low) / span * (height - 18) + 9)
            chart_overlays += (
                f'<line x1="{plot_left:g}" x2="{plot_right:g}" y1="{target_y:.1f}" y2="{target_y:.1f}" '
                'stroke="#48b883" stroke-width="1.6" stroke-dasharray="7 7"/>'
            )
            right_labels.append((target_y, f"ATLAS Target {_money(target)}", "#78d7c8", 2))
        else:
            direction = "↑" if float(target) > high else "↓"
            upside = card.get("atlas_expected_return")
            suffix = f' · {_score(upside, suffix="%")}' if upside is not None else ""
            off_chart_target = f'<div class="atlas-home-offchart-target">{direction} ATLAS Target {_money(target)}{suffix}</div>'
    current_y = height - ((closes[-1] - low) / span * (height - 18) + 9)
    chart_overlays += (
        f'<circle cx="{plot_right:g}" cy="{current_y:.1f}" r="4" fill="{stroke}"/>'
    )
    right_labels.append((current_y, f"Current {_money(closes[-1])}", "#e2e8f0", 1))
    placed: list[float] = []
    for raw_y, label, color, _priority in sorted(right_labels, key=lambda item: item[3]):
        label_y = min(max(raw_y, 10.0), height - 5.0)
        while any(abs(label_y - used) < 12 for used in placed) and label_y < height - 6:
            label_y += 12
        if any(abs(label_y - used) < 12 for used in placed):
            label_y = max(10.0, min(placed) - 12)
        placed.append(label_y)
        chart_overlays += (
            f'<line x1="{plot_right-22:g}" y1="{raw_y:.1f}" x2="{plot_right-18:g}" y2="{label_y:.1f}" stroke="{color}" opacity=".7"/>'
            f'<text x="{plot_right-5:g}" y="{label_y:.1f}" text-anchor="end" fill="{color}" font-size="9">{html.escape(label)}</text>'
        )
    def date_label(bar: Mapping[str, Any]) -> str:
        raw = bar.get("datetime") or bar.get("timestamp") or bar.get("date")
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return parsed.strftime("%b %Y")
        except (TypeError, ValueError):
            return ""
    start_label, end_label = date_label(bars[0]), date_label(bars[-1])
    metadata = {
        "provider": contract.get("provider"), "range": selected_range,
        "interval": contract.get("interval"), "adjustment": contract.get("adjustment_mode"),
        "timestamp": contract.get("newest_completed_bar_timestamp"), "evidence_id": contract.get("evidence_id"),
    }
    legend = "".join(
        f'<span style="--atlas-level:{color}"><i></i>{html.escape(label)} <b>{html.escape(value)}</b></span>'
        for label, value, color in level_legend
    )
    return (
        '<div class="atlas-home-chart" data-atlas-qa="home-mini-chart" '
        f'data-atlas-chart-contract="{html.escape(json.dumps(metadata, sort_keys=True))}">'
        f'<div><b>{html.escape(selected_range)} price trend</b>'
        f'<span class="atlas-home-tech-cue">{html.escape(_technical_cue(card))}</span></div>'
        f'<svg viewBox="0 0 {width:g} {height:g}" role="img" aria-label="Twelve Data {html.escape(selected_range)} closing price trend">'
        f'{chart_overlays}'
        f'<polyline fill="none" stroke="{stroke}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" points="{points}"/></svg>'
        f'<div class="atlas-home-chart-legend">{legend}</div>'
        f'{off_chart_target}'
        f'<div class="atlas-home-chart-dates"><span>{html.escape(start_label)}</span><span>{html.escape(end_label)}</span></div>'
        f'<small>Twelve Data · split-adjusted daily bars · through {html.escape(format_market_timestamp_et(contract.get("newest_completed_bar_timestamp")))}'
        f'{" · ATLAS target " + _money(target) if target is not None else ""}</small>'
        '</div>'
    )


def _why_it_could_win(card: Mapping[str, Any]) -> str:
    items: list[tuple[str, str]] = []
    recovery = card.get("recovery") or {}
    if recovery.get("score") is not None:
        items.append(("↑", "Trend recovery", "Shares are rebuilding after earlier weakness."))
    cue = _technical_cue(card)
    if cue != "Technical cue not published":
        items.append(("↗", cue, "Price structure is moving toward a stronger technical setup."))
    if str(card.get("entry_relationship") or "") == "WITHIN_ENTRY_RANGE":
        items.append(("◎", "Attractive entry", "Price remains near ATLAS's preferred entry zone."))
    if (str(card.get("atlas_valuation_status") or "").upper() == "PUBLISHED"
            and card.get("atlas_expected_return") is not None
            and float(card["atlas_expected_return"]) > 0):
        items.insert(0, ("$", "Valuation opportunity", "Published ATLAS valuation indicates meaningful potential upside."))
    cells = "".join(f'<span><b>{icon}</b><i>{html.escape(title)}<small>{html.escape(copy)}</small></i></span>' for icon, title, copy in items[:3])
    return f'<div class="atlas-home-win" data-atlas-qa="home-why-win">{cells}</div>' if cells else ""


def _recent_catalysts(card: Mapping[str, Any]) -> str:
    cells = []
    seen: set[str] = set()
    for item in card.get("recent_catalysts") or ():
        if len(cells) == 2:
            break
        headline = item.get("title") or item.get("headline")
        identity = " ".join(str(headline or "").lower().split())
        if not headline or identity in seen:
            continue
        seen.add(identity)
        category = str(item.get("category") or "COMPANY_EVENT").replace("_", " ").title()
        stamp = format_market_timestamp_et(item.get("published_at"), unavailable="Date unavailable")
        why = item.get("why_it_matters") or item.get("summary")
        if not why:
            continue
        cells.append(
            f'<article><small>{html.escape(category)} · {html.escape(stamp)}</small>'
            f'<b>{html.escape(str(headline))}</b><span>{html.escape(why)}</span></article>'
        )
    if not cells:
        return ""
    return '<div class="atlas-home-catalysts" data-atlas-qa="home-catalysts">' + "".join(cells) + "</div>"


def _trial_context(card: Mapping[str, Any]) -> str:
    if str(card.get("display_scope") or "") != "INTERNAL_TRIAL":
        return ""
    street = dict(card.get("wall_street") or {})
    context = dict(card.get("context_evidence") or {})
    items: list[tuple[str, str]] = []
    if street.get("rating") or street.get("analyst_count") is not None:
        label = str(street.get("rating") or "Consensus available").replace("_", " ").title()
        count = f" · {int(street['analyst_count'])} analysts" if street.get("analyst_count") is not None else ""
        items.append(("Analyst outlook", label + count))
    insider = dict(context.get("insider") or {})
    if insider.get("activity"):
        counts = ""
        if insider.get("buy_count") is not None or insider.get("sell_count") is not None:
            counts = f" · {int(insider.get('buy_count') or 0)} buys / {int(insider.get('sell_count') or 0)} sells"
        items.append(("Insider activity", str(insider["activity"]).title() + counts))
    institutional = dict(context.get("institutional") or {})
    ownership = institutional.get("ownership_pct")
    if institutional.get("trend"):
        items.append(("Institutional trend", str(institutional["trend"])))
    elif ownership is not None and 0 <= float(ownership) <= 100:
        items.append(("Institutional ownership", f"{float(ownership):.1f}%"))
    elif ownership is not None:
        items.append(("Institutional ownership", "Reported data requires normalization review"))
    political = dict(context.get("political") or {})
    if political.get("summary"):
        items.append(("Political context", str(political["summary"])))
    if not items:
        return ""
    return '<div class="atlas-home-trial-context">' + "".join(
        f'<span><small>{html.escape(label)}</small><b>{html.escape(value)}</b></span>' for label, value in items[:4]
    ) + '</div><em class="atlas-home-context-note">Supporting context only; it does not determine the ATLAS rating.</em>'


def _decisive_reason(card: Mapping[str, Any]) -> str:
    state = _customer_state(card).upper()
    title = {
        "BUY_NOW": "Why Buy Now", "BUY": "Why Buy Now",
        "ACCUMULATE": "Why Build a Position", "BUILD_A_POSITION": "Why Build a Position",
        "WAIT_FOR_ENTRY": "Why ATLAS Is Waiting for Price",
        "WAIT_FOR_CONFIRMATION": "Why ATLAS Is Waiting",
        "DATA_LIMITED": "Why It's Not Ready Yet",
        "AVOID": "Why ATLAS Says Avoid",
    }.get(state, "Why ATLAS Is Waiting")
    return (
        '<div class="atlas-home-decisive" data-atlas-qa="home-decisive-reason">'
        f'<b>{html.escape(title)}</b><span>{html.escape(_guidance_explanation(card))}</span></div>'
    )


def _card(card: Mapping[str, Any], *, key: str, first: bool = False, total: int = 0) -> None:
    ticker = str(card.get("ticker") or "UNKNOWN")
    guidance = _display(_customer_state(card))
    actionability = _display(card.get("actionability"))
    st.markdown(
        f'<div class="atlas-home-guidance-card-marker" data-atlas-qa="home-guidance-card" '
        f'data-atlas-first="{str(first).lower()}" data-atlas-ticker="{html.escape(ticker)}" '
        f'data-atlas-production-rank="{int(card.get("production_rank") or 0)}" '
        f'data-atlas-guidance="{html.escape(_customer_state(card))}" '
        f'data-atlas-actionability="{html.escape(str(card.get("actionability") or "UNAVAILABLE"))}" '
        f'data-atlas-opportunity="{html.escape(str(card.get("opportunity") if card.get("opportunity") is not None else "UNAVAILABLE"))}" '
        f'data-atlas-decision-confidence="{html.escape(str(card.get("decision_confidence") if card.get("decision_confidence") is not None else "UNAVAILABLE"))}" '
        f'data-atlas-scan-conviction="{html.escape(str(card.get("scan_conviction") if card.get("scan_conviction") is not None else "UNAVAILABLE"))}" '
        'aria-hidden="true"></div>', unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown(
            '<div class="atlas-home-card-head">'
            f'<span>DISCOVERY RANK #{card.get("production_rank")}</span>'
            f'<div><h3>{html.escape(ticker)} <i>— {html.escape(str(card.get("company") or ticker))}</i></h3></div>'
            f'<aside><strong>{html.escape(_money(card.get("display_price")))}</strong>'
            f'<small>{html.escape(str(card.get("display_price_label") or "Price unavailable"))}</small></aside>'
            '</div>', unsafe_allow_html=True,
        )
        st.markdown(_market_evidence_badge(card), unsafe_allow_html=True)
        st.markdown(_action_card(card), unsafe_allow_html=True)
        st.caption(
            f"Latest ATLAS Rating — {_timestamp(card.get('latest_rating_as_of'))} · "
            f"Live Entry Status — {card.get('live_entry_status') or 'Current-session evidence unavailable'}"
        )
        chart_contract = card.get("home_chart") if isinstance(card.get("home_chart"), Mapping) else {}
        if str(chart_contract.get("status") or "").upper() == "AVAILABLE" and len(chart_contract.get("bars") or ()) >= 2:
            st.markdown('<h4 class="atlas-home-view-title">Price Chart</h4>', unsafe_allow_html=True)
            selected_range = st.radio(
                f"{ticker} chart range", ("1M", "3M", "1Y"), index=2, horizontal=True,
                key=f"home_chart_range_{key}_{ticker}", label_visibility="collapsed",
            )
            chart_html = _mini_chart(card, selected_range)
            if chart_html:
                st.markdown(chart_html, unsafe_allow_html=True)
        st.markdown('<h4 class="atlas-home-view-title">Price Outlook</h4>', unsafe_allow_html=True)
        st.markdown(_target_tiles(card), unsafe_allow_html=True)
        st.markdown('<h4 class="atlas-home-view-title">ATLAS Investment View</h4>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="atlas-home-guidance-summary" data-atlas-qa="home-guidance-summary">{html.escape(_atlas_summary(card))}</p>',
            unsafe_allow_html=True,
        )
        st.markdown('<h4 class="atlas-home-view-title">Six-Pillar Decision Evidence</h4>', unsafe_allow_html=True)
        st.markdown(_six_pillar_summary(card), unsafe_allow_html=True)
        win = _why_it_could_win(card)
        if win:
            st.markdown('<h4 class="atlas-home-subhead">Why It Could Win</h4>', unsafe_allow_html=True)
            st.markdown(win, unsafe_allow_html=True)
        st.markdown(_decisive_reason(card), unsafe_allow_html=True)
        catalysts = _recent_catalysts(card)
        if catalysts:
            st.markdown('<h4 class="atlas-home-subhead">Recent Catalysts</h4>', unsafe_allow_html=True)
            st.markdown(catalysts, unsafe_allow_html=True)
        trial_context = _trial_context(card)
        if trial_context:
            st.markdown('<h4 class="atlas-home-subhead">Analyst & Ownership Context</h4>', unsafe_allow_html=True)
            st.markdown(trial_context, unsafe_allow_html=True)
        _open_research(ticker, f"home_guidance_{key}_{ticker}")
        with st.expander("Full Evidence", expanded=False):
            st.markdown(_full_evidence(card), unsafe_allow_html=True)


def _section_marker(name: str) -> None:
    st.markdown(
        f'<span data-atlas-qa="home-guidance-section" data-atlas-section="{html.escape(name)}" '
        'aria-hidden="true" style="display:none">home-guidance-section</span>', unsafe_allow_html=True,
    )


def _home_candidate_surface(all_cards: Sequence[Mapping[str, Any]], *, limit: int = 10) -> list[Mapping[str, Any]]:
    """Keep every governed Buy Now, then fill by immutable production order."""
    all_cards = list(all_cards)
    actionable = [card for card in all_cards if _customer_state(card) == "BUY_NOW"]
    selected_tickers = {str(card.get("ticker") or "") for card in actionable}
    return actionable + [
        card for card in all_cards
        if str(card.get("ticker") or "") not in selected_tickers
    ][:max(0, limit - len(actionable))]


def _render_groups(story: Mapping[str, Any], *, emit_interactive) -> None:
    cards = _home_candidate_surface(story.get("cards") or ())
    _section_marker("customer-action-groups")
    if not cards:
        st.info("No persisted Home candidates are available.")
        emit_interactive()
        return
    groups = (
        ("TOP ACTIONABLE OPPORTUNITIES", {"BUY_NOW", "ACCUMULATE"}),
        ("WAITING FOR AN ENTRY", {"WAIT_FOR_ENTRY", "WAIT_FOR_CONFIRMATION"}),
        ("WATCHLIST", {"DATA_LIMITED"}),
        ("RATINGS BEING REFRESHED", {"WITHHELD"}),
        ("AVOID", {"AVOID"}),
    )
    emitted = False
    for title, states in groups:
        members = [card for card in cards if _customer_state(card) in states]
        if not members and title != "TOP ACTIONABLE OPPORTUNITIES":
            continue
        st.markdown(f"### {title}")
        if title == "TOP ACTIONABLE OPPORTUNITIES" and not any(_customer_state(card) == "BUY_NOW" for card in members):
            st.caption("No opportunities currently meet ATLAS's 5-star Buy Now standard.")
        for index, card in enumerate(members):
            _card(card, key=f"action_{title}_{index}", first=not emitted, total=int(story.get("candidate_count") or len(story.get("cards") or ())))
            if not emitted:
                emit_interactive()
                emitted = True
    if not emitted:
        emit_interactive()


def _action_counts(story: Mapping[str, Any]) -> str:
    states = [_customer_state(card) for card in story.get("cards") or ()]
    values = (
        ("5★ Buy Now", states.count("BUY_NOW"), "buy"),
        ("4.5★ Build", states.count("ACCUMULATE"), "build"),
        ("4★ Wait for Entry", states.count("WAIT_FOR_ENTRY"), "wait"),
        ("3.5★ Wait for Confirmation", states.count("WAIT_FOR_CONFIRMATION"), "wait"),
        ("Watch", states.count("DATA_LIMITED"), "watch"),
    )
    return '<div class="atlas-home-action-counts">' + "".join(
        f'<span class="atlas-home-count-{tone}"><small>{html.escape(label)}</small><b>{count}</b></span>'
        for label, count, tone in values
    ) + '</div>'


def _comparison(card: Mapping[str, Any]) -> None:
    street = card.get("wall_street") or {}
    atlas, wall = st.columns(2)
    with atlas:
        st.markdown("#### ATLAS")
        st.write(f"Guidance: **{_display(card.get('guidance'))}**")
        st.write(f"Actionability: **{_display(card.get('actionability'))}**")
        st.write(f"Opportunity: **{_score(card.get('opportunity'))}**")
        st.write(f"Decision Confidence: **{_score(card.get('decision_confidence'), suffix='%')}**")
        st.write(f"Atlas FV: **{_money(card.get('atlas_fair_value'))}**")
        st.write(f"Technical / Volume: **{_display(card.get('technical_state'))} / {_display(card.get('volume_state'))}**")
    with wall:
        st.markdown("#### Wall Street")
        st.write(f"Consensus: **{_display(street.get('rating'))}**")
        st.write(f"Analyst count: **{_score(street.get('analyst_count'))}**")
        st.write(f"Mean target: **{_money(street.get('mean_target'))}**")
        st.write(f"Range: **{_money(street.get('low_target'))}–{_money(street.get('high_target'))}**")
        st.write(f"Implied upside: **{_score(street.get('implied_upside'), suffix='%')}**")
    st.caption("Wall Street evidence is contextual. It cannot create ATLAS Guidance or populate Atlas Fair Value.")


def _inject_css() -> None:
    st.markdown("""<style>
    :root{--atlas-teal:#2fb7a4;--atlas-green:#48b883;--atlas-amber:#d7a542;--atlas-red:#d66b72;--atlas-blue:#5d91d6;--atlas-muted:#8b98aa;--atlas-panel:rgba(17,28,45,.72)}
    .atlas-home-guidance-hero{padding:.45rem 0 .7rem}.atlas-home-guidance-badge{display:inline-block;border:1px solid rgba(59,130,246,.5);border-radius:999px;padding:.25rem .6rem;font-size:.72rem;font-weight:800}
    .atlas-home-card-head{display:grid;grid-template-columns:1fr auto;align-items:end;gap:.35rem .75rem;margin:.06rem 0 .22rem}.atlas-home-card-head>span{grid-column:1/-1;font-size:.72rem;font-weight:850;letter-spacing:.13em;color:var(--atlas-blue)}.atlas-home-card-head h3{margin:0!important;padding:0!important;font-size:1.5rem!important;line-height:1.15!important;color:#f7fafc}.atlas-home-card-head h3 i{font-size:.9rem;font-style:normal;font-weight:500;color:#aab5c5}.atlas-home-card-head aside{text-align:right}.atlas-home-card-head aside strong,.atlas-home-card-head aside small{display:block}.atlas-home-card-head aside strong{font-size:1.4rem;color:#f7fafc}.atlas-home-card-head aside small{font-size:.72rem;color:var(--atlas-muted)}
    .atlas-home-action-counts{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.35rem;margin:.6rem 0 1rem}.atlas-home-action-counts span{display:flex;justify-content:space-between;align-items:center;gap:.4rem;padding:.48rem .58rem;border-radius:10px;background:rgba(15,23,42,.46);border:1px solid rgba(148,163,184,.16)}.atlas-home-action-counts small{font-size:.7rem;color:#9aa7b9}.atlas-home-action-counts b{font-size:1.05rem}.atlas-home-count-buy b{color:var(--atlas-green)}.atlas-home-count-build b{color:var(--atlas-teal)}.atlas-home-count-wait b,.atlas-home-count-watch b{color:var(--atlas-amber)}
    .atlas-home-action{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:.18rem .85rem;padding:.78rem .92rem;border-radius:14px;border:1px solid;background:var(--atlas-panel)}.atlas-home-action>small{grid-column:1/-1;font-size:.68rem;font-weight:800;letter-spacing:.13em}.atlas-home-action-stars{grid-row:2/5;font-size:1.65rem;line-height:1;letter-spacing:.02em;white-space:nowrap}.atlas-home-action strong{font-size:1.3rem;line-height:1.12}.atlas-home-action em{font-size:.8rem;font-style:normal;font-weight:700;color:#bfdbfe}.atlas-home-action span{font-size:.8rem;line-height:1.35;color:#cbd5e1}.atlas-home-action-positive,.atlas-home-action-buy,.atlas-home-action-build{border-color:rgba(47,183,164,.42);box-shadow:inset 4px 0 0 var(--atlas-teal);background:linear-gradient(125deg,rgba(47,183,164,.15),rgba(17,28,45,.62));color:#78d7c8}.atlas-home-action-waiting,.atlas-home-action-wait,.atlas-home-action-watch{border-color:rgba(215,165,66,.4);box-shadow:inset 4px 0 0 var(--atlas-amber);background:linear-gradient(125deg,rgba(215,165,66,.14),rgba(17,28,45,.62));color:#edc878}.atlas-home-action-negative,.atlas-home-action-avoid{border-color:rgba(214,107,114,.45);box-shadow:inset 4px 0 0 var(--atlas-red);background:linear-gradient(125deg,rgba(214,107,114,.14),rgba(17,28,45,.62));color:#ee9da2}.atlas-home-action-neutral{border-color:rgba(93,145,214,.4);box-shadow:inset 4px 0 0 var(--atlas-blue)}
    .atlas-home-view-title,.atlas-home-subhead{margin:.32rem 0 .15rem!important;padding:0!important;font-size:.96rem!important;letter-spacing:.01em;color:#dce8f6}.atlas-home-guidance-summary{padding:.55rem .65rem;border-left:3px solid var(--atlas-blue);border-radius:0 9px 9px 0;background:rgba(36,61,92,.2)}
    .atlas-home-chart{min-height:220px;padding:.65rem .7rem;border-radius:13px;background:linear-gradient(145deg,rgba(16,29,47,.92),rgba(20,38,55,.55));border:1px solid rgba(93,145,214,.22)}.atlas-home-chart>div{display:flex;justify-content:space-between;align-items:center;gap:.5rem}.atlas-home-chart b{font-size:.82rem;color:#dce8f6}.atlas-home-chart svg{display:block;width:100%;height:148px;margin:.25rem 0}.atlas-home-chart small{display:block;font-size:.68rem;line-height:1.3;color:var(--atlas-muted)}.atlas-home-chart-empty{display:flex;flex-direction:column;justify-content:center;gap:.35rem;color:var(--atlas-muted)}.atlas-home-chart-empty span{font-size:.78rem}.atlas-home-tech-cue{display:inline-flex;padding:.18rem .48rem;border-radius:999px;background:rgba(47,183,164,.11);border:1px solid rgba(47,183,164,.32);font-size:.72rem;font-weight:700;color:#82d7cb;white-space:nowrap}
    .atlas-home-chart-dates{display:flex!important;justify-content:space-between!important;margin-left:44px;color:#718096;font-size:.64rem}.atlas-home-offchart-target{justify-content:flex-end!important;margin:-.05rem 0 .18rem!important;color:#78d7c8;font-size:.68rem;font-weight:750}.atlas-home-quality-warning{color:#94a3b8;font-style:normal;cursor:help}
    .atlas-home-chart-legend{display:flex!important;justify-content:flex-start!important;flex-wrap:wrap;gap:.25rem .65rem;margin:.05rem 0 .15rem;font-size:.66rem;color:#9aa7b9}.atlas-home-chart-legend span{display:inline-flex;align-items:center;gap:.22rem;white-space:nowrap}.atlas-home-chart-legend i{display:inline-block;width:.72rem;border-top:2px solid var(--atlas-level)}.atlas-home-chart-legend b{font-size:.66rem;color:#cbd5e1}
    .atlas-home-comparison{display:grid;grid-template-columns:1fr 1fr;gap:.3rem;min-height:220px}.atlas-home-target{display:flex;flex-direction:column;justify-content:center;min-width:0;padding:.55rem .58rem;border-radius:11px;background:rgba(15,26,43,.72);border:1px solid rgba(148,163,184,.16)}.atlas-home-target small,.atlas-home-target b{display:block}.atlas-home-target small{font-size:.68rem;line-height:1.25;color:#9aa7b9}.atlas-home-target b{margin-top:.18rem;font-size:1rem;color:#f1f5f9}.atlas-home-target-atlas{border-color:rgba(47,183,164,.28);background:rgba(22,82,75,.12)}.atlas-home-target-atlas b{color:#7bd5c7}.atlas-home-target-street{border-color:rgba(93,145,214,.25);background:rgba(34,74,123,.11)}.atlas-home-target-street b{color:#9fc2ed}.atlas-home-target-muted b{font-size:.8rem;font-weight:600;color:#8995a5}.atlas-home-comparison em{grid-column:1/-1;font-size:.66rem;line-height:1.3;font-style:normal;color:#778497}
    .atlas-home-divergence{grid-column:1/-1;padding:.38rem .52rem;border-left:3px solid var(--atlas-blue);font-size:.78rem;color:#cfe2fa;background:rgba(37,99,235,.08)}
    .atlas-home-pillars{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.28rem}.atlas-home-pillar{display:grid;gap:.15rem;padding:.42rem .48rem;border:1px solid rgba(148,163,184,.18);border-radius:9px;background:rgba(15,23,42,.28)}.atlas-home-pillar small{font-size:.67rem;color:#8fa0b5}.atlas-home-pillar b{font-size:.78rem;color:#cbd5e1}.atlas-home-pillar-strong b,.atlas-home-pillar-good b{color:#76d2c3}.atlas-home-pillar-moderate b{color:#edc878}.atlas-home-pillar-weak b{color:#ee9da2}.atlas-home-pillar-unavailable b{color:#788599}
    .atlas-home-win{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.35rem}.atlas-home-win span{display:flex;align-items:center;gap:.45rem;padding:.5rem .6rem;border-radius:10px;background:rgba(47,183,164,.075);border:1px solid rgba(47,183,164,.18);font-size:.8rem;color:#cbd5e1}.atlas-home-win b{display:grid;place-items:center;width:1.5rem;height:1.5rem;border-radius:50%;background:rgba(47,183,164,.14);color:#70d2c3}
    .atlas-home-decisive{display:grid;gap:.18rem;margin:.5rem 0;padding:.58rem .68rem;border-radius:10px;border-left:3px solid var(--atlas-amber);background:rgba(109,77,22,.1)}.atlas-home-decisive b{font-size:.82rem;color:#edc878}.atlas-home-decisive span{font-size:.8rem;line-height:1.4;color:#bdc7d5}
    .atlas-home-catalysts{display:grid;grid-template-columns:1fr 1fr;gap:.42rem}.atlas-home-catalysts article{display:flex;flex-direction:column;gap:.22rem;padding:.58rem .65rem;border-radius:11px;border:1px solid rgba(93,145,214,.2);background:rgba(37,69,106,.1)}.atlas-home-catalysts small{font-size:.66rem;text-transform:uppercase;letter-spacing:.055em;color:#8fb4e3}.atlas-home-catalysts b{font-size:.82rem;line-height:1.3;color:#dce8f6}.atlas-home-catalysts span{font-size:.74rem;line-height:1.35;color:#95a3b6}
    .atlas-home-trial-context{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.35rem}.atlas-home-trial-context span{display:grid;gap:.18rem;padding:.5rem .58rem;border-radius:10px;background:rgba(37,69,106,.09);border:1px solid rgba(93,145,214,.18)}.atlas-home-trial-context small{font-size:.66rem;color:#8fa5bf}.atlas-home-trial-context b{font-size:.78rem;line-height:1.3;color:#d5dfeb}.atlas-home-context-note{display:block;margin-top:.3rem;font-size:.65rem;font-style:normal;color:#778497}
    .atlas-home-guidance-primary{display:grid;grid-template-columns:1.35fr 1fr;gap:.3rem;margin:.06rem 0 .14rem}.atlas-home-guidance-primary span{padding:.28rem .46rem;border-radius:10px;background:rgba(37,99,235,.12);border:1px solid rgba(96,165,250,.3)}
    .atlas-home-guidance-state-data-limited span:first-child{background:linear-gradient(135deg,rgba(245,158,11,.13),rgba(120,53,15,.08));border-color:rgba(245,158,11,.34)}
    .atlas-home-guidance-identity{display:flex;align-items:baseline;flex-wrap:wrap;gap:.22rem .48rem;margin:.02rem 0 .12rem;color:#cbd5e1}.atlas-home-guidance-identity strong{font-size:1.12rem;color:#f8fafc}.atlas-home-guidance-identity span{font-size:.76rem;font-weight:400;color:#7f8b9d}.atlas-home-guidance-identity em{padding:.16rem .48rem;border:1px solid rgba(96,165,250,.28);border-radius:999px;font-size:.72rem;font-style:normal;color:#bfdbfe;background:rgba(37,99,235,.07)}
    .atlas-home-market-badge{display:flex;align-items:center;flex-wrap:wrap;gap:.18rem .5rem;margin:.02rem 0 .14rem;padding:.25rem .48rem;border-radius:8px;border:1px solid rgba(100,116,139,.3);background:rgba(15,23,42,.32)}.atlas-home-market-badge b{font-size:.7rem;letter-spacing:.06em}.atlas-home-market-badge span{font-size:.75rem;color:#94a3b8}.atlas-home-market-badge small{flex-basis:100%;font-size:.72rem;color:#fbbf24}.atlas-home-market-live{border-color:rgba(20,184,166,.42)}.atlas-home-market-live b{color:#2dd4bf}.atlas-home-market-stale b{color:#f59e0b}.atlas-home-market-unavailable b{color:#94a3b8}
    .atlas-home-atlas-score{--score-accent:#14b8a6;display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:.12rem .58rem;margin:.04rem 0 .18rem;padding:.48rem .62rem;border:1px solid color-mix(in srgb,var(--score-accent) 42%,transparent);border-radius:12px;background:linear-gradient(110deg,color-mix(in srgb,var(--score-accent) 16%,transparent),rgba(15,23,42,.18));box-shadow:inset 3px 0 0 var(--score-accent)}.atlas-home-score-label{font-size:.74rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#cbd5e1}.atlas-home-atlas-score strong{font-size:1.42rem;line-height:1;color:#f8fafc;white-space:nowrap}.atlas-home-score-stars{font-size:1rem;letter-spacing:.06em;white-space:nowrap;background:linear-gradient(90deg,var(--score-accent) 0 var(--atlas-star-fill,0%),rgba(148,163,184,.28) var(--atlas-star-fill,0%) 100%);background-clip:text;-webkit-background-clip:text;color:transparent}.atlas-home-atlas-score b{font-size:.82rem;line-height:1.2;color:var(--score-accent);text-transform:uppercase;letter-spacing:.045em}.atlas-home-atlas-score small{grid-column:2/-1;font-size:.78rem;line-height:1.3;color:#cbd5e1}.atlas-home-score-exceptional{--score-accent:#14b8a6}.atlas-home-score-strong{--score-accent:#3b82f6}.atlas-home-score-constructive{--score-accent:#eab308}.atlas-home-score-developing{--score-accent:#f97316}.atlas-home-score-weak{--score-accent:#c96a70}.atlas-home-score-unavailable{--score-accent:#64748b}
    .atlas-home-guidance-primary small,.atlas-home-guidance-primary strong,.atlas-home-guidance-metric small,.atlas-home-guidance-metric b{display:block}.atlas-home-guidance-primary small{font-size:.62rem;letter-spacing:.035em;color:#94a3b8}.atlas-home-guidance-metric small{font-size:.82rem;letter-spacing:.025em;color:#94a3b8;line-height:1.25}.atlas-home-guidance-primary strong{font-size:1.05rem;margin-top:.06rem;line-height:1.08}
    .atlas-home-guidance-core,.atlas-home-guidance-evidence{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.1rem;margin:.06rem 0 .12rem}.atlas-home-guidance-core{padding:.03rem 0;background:rgba(15,23,42,.3);border-radius:8px}.atlas-home-guidance-core .atlas-home-guidance-metric b{font-size:1.15rem;line-height:1.25}.atlas-home-guidance-evidence{grid-template-columns:repeat(4,minmax(0,1fr))}.atlas-home-guidance-metric{padding:.24rem .36rem;border-left:2px solid rgba(148,163,184,.35);min-width:0}.atlas-home-guidance-metric b{overflow-wrap:anywhere;line-height:1.25}.atlas-home-guidance-unavailable b{color:#7f8b9d!important;font-weight:600}.atlas-home-guidance-unavailable small{color:#64748b!important}
    .atlas-home-key-numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:.18rem;margin:.02rem 0 .14rem;padding:.24rem;border:1px solid rgba(96,165,250,.18);border-radius:10px;background:rgba(15,23,42,.24)}.atlas-home-key-numbers .atlas-home-guidance-metric{border-left-color:rgba(96,165,250,.42)}
    .atlas-home-evidence-status{display:inline-flex;align-items:center;gap:.4rem;margin:.02rem 0 .12rem;padding:.16rem .42rem;border:1px solid rgba(245,158,11,.24);border-radius:999px;background:rgba(120,53,15,.08);color:#a8b3c4}.atlas-home-evidence-status small{font-size:.65rem;letter-spacing:.06em}.atlas-home-evidence-status b{font-size:.72rem;color:#fcd38d}
    .atlas-home-guidance-explanation{margin:.02rem 0 .08rem!important;font-size:.8rem;color:#a8b3c4}.atlas-home-change-call{display:grid;gap:.12rem;margin:.04rem 0 .14rem;padding:.4rem .52rem;border-left:3px solid rgba(245,158,11,.5);background:rgba(120,53,15,.07)}.atlas-home-change-call b{font-size:.8rem;color:#fcd38d}.atlas-home-change-call span{font-size:.84rem;line-height:1.4;color:#cbd5e1}
    .atlas-home-guidance-summary{margin:.08rem 0 .12rem!important;font-size:.9rem;line-height:1.42;color:#dbeafe;font-weight:500}.atlas-home-guidance-quick{display:grid;grid-template-columns:1fr 1fr;gap:.55rem;margin:.06rem 0 .14rem}.atlas-home-guidance-quick section{padding:.42rem .55rem;border:1px solid rgba(148,163,184,.18);border-radius:9px;background:rgba(15,23,42,.22)}.atlas-home-guidance-quick h4{margin:0 0 .22rem;font-size:.95rem;line-height:1.3;font-weight:650}.atlas-home-guidance-quick section:first-child h4{color:#bfdbfe}.atlas-home-guidance-quick section:last-child h4{color:#fcd38d}.atlas-home-guidance-quick ul{margin:0;padding-left:1.05rem}.atlas-home-guidance-quick li{margin:.08rem 0;font-size:.86rem;line-height:1.35;color:#cbd5e1}
    .atlas-home-full-evidence{display:block;margin:0;color:#cbd5e1}.atlas-home-full-evidence section{display:block;padding:.72rem 0;border-top:1px solid rgba(148,163,184,.18)}.atlas-home-full-evidence section:first-child{padding-top:0;border-top:0}.atlas-home-full-evidence h4{margin:0 0 .4rem;font-size:1rem;line-height:1.35;font-weight:650;color:#dbeafe}.atlas-home-full-evidence p{margin:.22rem 0;font-size:.875rem;line-height:1.48}.atlas-home-full-evidence p>b,.atlas-home-full-reasons b,.atlas-home-trade-row b{color:#a8b3c4}.atlas-home-full-evidence small{color:#8793a6}.atlas-home-full-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.3rem}.atlas-home-full-metrics .atlas-home-guidance-metric{padding:.32rem .42rem}.atlas-home-full-note{color:#8793a6}.atlas-home-full-reasons{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}.atlas-home-full-reasons ul{margin:.22rem 0 0;padding-left:1.05rem}.atlas-home-full-reasons li{margin:.16rem 0;font-size:.875rem;line-height:1.48}.atlas-home-reason-codes{font-size:.76rem!important;line-height:1.4!important;color:#718096!important;overflow-wrap:anywhere}.atlas-home-trade-row{display:flex;flex-wrap:wrap;align-items:baseline;gap:.2rem .48rem;font-size:.9rem;line-height:1.5}.atlas-home-trade-row span{white-space:nowrap}.atlas-home-trade-row span+span::before{content:"·";margin-right:.48rem;color:#718096}
    .atlas-home-dossier-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.38rem}.atlas-home-dossier-grid>span{display:flex;min-width:0;flex-direction:column;gap:.12rem;padding:.5rem .58rem;border-radius:9px;background:rgba(21,36,54,.48)}.atlas-home-dossier-grid small{font-size:.67rem;text-transform:uppercase;letter-spacing:.045em}.atlas-home-dossier-grid b{font-size:.86rem;overflow-wrap:anywhere;color:#dce8f6}.atlas-home-paid-dossier ul{margin:.2rem 0;padding-left:1.1rem}.atlas-home-paid-dossier li{margin:.16rem 0;font-size:.86rem;line-height:1.45}.atlas-home-muted{color:#8793a6!important}
    .atlas-home-guidance-status{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.08rem;margin:.02rem 0 .08rem;padding:.08rem .06rem;border-top:1px solid rgba(148,163,184,.18);border-bottom:1px solid rgba(148,163,184,.18)}.atlas-home-guidance-status .atlas-home-guidance-metric{padding:.18rem .28rem;border-left:0}.atlas-home-guidance-status .atlas-home-guidance-metric:nth-child(2){border-left:2px solid rgba(59,130,246,.35);background:rgba(37,99,235,.045)}.atlas-home-guidance-status .atlas-home-guidance-metric:nth-child(3){border-left:2px solid rgba(168,85,247,.35);background:rgba(126,34,206,.045)}.atlas-home-guidance-status small{font-size:.8rem}.atlas-home-guidance-status b{font-size:.92rem;line-height:1.3}
    .atlas-home-snapshot-lines{display:grid;grid-template-columns:1fr 1fr;gap:.18rem .65rem;margin:.08rem 0 .12rem}.atlas-home-snapshot-lines h4{grid-column:1/-1;margin:0;font-size:.98rem;font-weight:600;line-height:1.35;color:#dbeafe}.atlas-home-snapshot-lines p{margin:0;font-size:.875rem;line-height:1.42;color:#cbd5e1}.atlas-home-snapshot-lines b{color:#a8b3c4}.atlas-home-guidance-limited{display:grid;grid-template-columns:1fr 1fr;gap:.45rem;margin:.08rem 0 .12rem;padding:.42rem .5rem;border-radius:8px;background:linear-gradient(135deg,rgba(245,158,11,.075),rgba(15,23,42,.12));border:1px solid rgba(245,158,11,.22)}.atlas-home-guidance-limited>span+span{border-left:1px solid rgba(148,163,184,.18);padding-left:.45rem}.atlas-home-guidance-limited b,.atlas-home-guidance-limited small{display:block}.atlas-home-guidance-limited b{font-size:.95rem;font-weight:600;line-height:1.35;color:#fcd38d}.atlas-home-guidance-limited small{font-size:.85rem;line-height:1.4;margin-top:.12rem;color:#c6cfdd}.atlas-home-guidance-limited code{font-size:.78rem;line-height:1.35;color:#a8b3c4;overflow-wrap:anywhere}
    .atlas-home-guidance-card-marker{height:0}
    body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMarkdownContainer"]{margin-bottom:0!important}
    body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:.3rem}
    body:has([data-atlas-qa="home-guidance-vnext"]) h1,body:has([data-atlas-qa="home-guidance-vnext"]) h2,body:has([data-atlas-qa="home-guidance-vnext"]) h3{margin-top:.35rem;margin-bottom:.25rem;padding:.18rem 0!important}
    body:has([data-atlas-qa="home-guidance-vnext"]) .atlas-home-guidance-hero h1{font-size:2.1rem;line-height:1.06}
    body:has([data-atlas-qa="home-guidance-vnext"]) h2{font-size:1.55rem;line-height:1.1}
    body:has([data-atlas-qa="home-guidance-vnext"]) .stButton>button[kind="primary"]{min-height:2.05rem;padding:.2rem .7rem}
    body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stExpander"] details summary{min-height:2.1rem!important;padding:.12rem .65rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stExpander"] details summary p{font-size:.82rem;margin:0}
    @media(min-width:481px){body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stLayoutWrapper"]>[data-testid="stVerticalBlock"]{gap:.1rem}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stLayoutWrapper"] h3{font-size:1.35rem!important;line-height:1.08!important;padding:.1rem 0!important;margin:0!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stLayoutWrapper"] [data-testid="stElementContainer"]{margin-top:0!important;margin-bottom:0!important}}
    @media(max-width:700px){body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"]:has([role="radiogroup"]){position:sticky!important;top:3.75rem!important;z-index:990!important;margin-top:.35rem!important;background:var(--background-color,#0e1117);padding:.15rem 0 .2rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"] [role="radiogroup"]{flex-wrap:nowrap!important;overflow-x:auto!important;padding-bottom:.2rem;scrollbar-width:thin}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stRadio"] [role="radiogroup"] label{flex:0 0 auto!important;white-space:nowrap;padding:.28rem .52rem!important;min-height:30px!important}}
    @media(max-width:480px){body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]{padding-top:.2rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:.24rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stElementContainer"]:has([data-atlas-qa][aria-hidden="true"]){display:none!important}.atlas-home-guidance-hero{padding:.04rem 0 .11rem}.atlas-home-guidance-hero h1{font-size:1.5rem;line-height:1.16;margin:.02rem 0 .08rem}.atlas-home-guidance-hero p{margin:.08rem 0}.atlas-home-guidance-primary{grid-template-columns:1fr 1fr;gap:.18rem;margin:.01rem 0 .06rem}.atlas-home-guidance-primary span{padding:.2rem .3rem}.atlas-home-guidance-primary small{font-size:.68rem}.atlas-home-guidance-primary strong{font-size:.92rem;line-height:1.22}.atlas-home-guidance-core{grid-template-columns:repeat(3,minmax(0,1fr));gap:.06rem;margin:.04rem 0 .08rem}.atlas-home-guidance-core .atlas-home-guidance-metric{padding:.14rem .12rem}.atlas-home-guidance-core small{font-size:.8125rem;line-height:1.25}.atlas-home-guidance-core .atlas-home-guidance-metric b{font-size:1.125rem;line-height:1.25}.atlas-home-guidance-status{grid-template-columns:repeat(2,minmax(0,1fr));gap:.1rem;margin:.02rem 0 .08rem;padding:.1rem .05rem}.atlas-home-guidance-status .atlas-home-guidance-metric{padding:.15rem .16rem}.atlas-home-guidance-status small{font-size:.8125rem}.atlas-home-guidance-status b{font-size:.88rem;line-height:1.3}.atlas-home-guidance-evidence{grid-template-columns:repeat(2,minmax(0,1fr))}h2{margin:.2rem 0!important;font-size:1.25rem!important;line-height:1.2!important}h3{font-size:1rem!important;line-height:1.2!important;margin:.04rem 0!important;padding:.05rem 0!important}.atlas-home-guidance-card-marker+div [data-testid="stVerticalBlock"]{gap:.14rem}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stExpander"] details summary{min-height:1.9rem!important;padding:.08rem .5rem!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stExpander"] details summary p{font-size:.82rem;white-space:normal;line-height:1.3}}
    @media(max-width:480px){body:has([data-atlas-qa="home-guidance-vnext"]) h2{margin:.1rem 0!important;padding:.02rem 0!important}body:has([data-atlas-qa="home-guidance-vnext"]) [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:.2rem!important}.atlas-home-snapshot-lines{grid-template-columns:1fr;gap:.14rem;margin:.08rem 0 .12rem}.atlas-home-snapshot-lines h4{font-size:.95rem;line-height:1.35}.atlas-home-snapshot-lines p{font-size:.825rem;line-height:1.4}.atlas-home-guidance-limited{grid-template-columns:1fr;padding:.3rem .36rem;gap:.22rem;margin:.08rem 0 .12rem}.atlas-home-guidance-limited>span+span{border-left:0;border-top:1px solid rgba(148,163,184,.18);padding-left:0;padding-top:.22rem}.atlas-home-guidance-limited b{font-size:.92rem}.atlas-home-guidance-limited small{font-size:.8125rem;line-height:1.4}.atlas-home-guidance-limited code{font-size:.75rem;line-height:1.35;overflow-wrap:anywhere}}
    @media(max-width:700px){.atlas-home-win{grid-template-columns:1fr}.atlas-home-catalysts{grid-template-columns:1fr}.atlas-home-chart,.atlas-home-comparison{min-height:unset}.atlas-home-chart svg{height:125px}.atlas-home-pillars{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-home-dossier-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:480px){.atlas-home-card-head{grid-template-columns:1fr auto;align-items:end}.atlas-home-card-head>span{grid-column:1/-1}.atlas-home-card-head h3{font-size:1.35rem!important}.atlas-home-card-head aside strong{font-size:1.2rem}.atlas-home-guidance-identity{gap:.18rem .38rem;margin:.02rem 0 .1rem}.atlas-home-guidance-identity strong{font-size:1rem}.atlas-home-guidance-identity span{font-size:.74rem}.atlas-home-guidance-identity em{font-size:.72rem}.atlas-home-atlas-score{grid-template-columns:auto 1fr auto;gap:.1rem .42rem;padding:.55rem;margin:.03rem 0 .12rem;min-height:108px}.atlas-home-score-label{font-size:.7rem}.atlas-home-atlas-score strong{font-size:1.25rem}.atlas-home-score-stars{grid-row:2;grid-column:1/3;font-size:.88rem}.atlas-home-atlas-score b{grid-row:1;grid-column:3}.atlas-home-atlas-score small{grid-row:3;grid-column:1/-1;font-size:.76rem}.atlas-home-guidance-summary{font-size:.84rem;line-height:1.4;margin:.08rem 0 .12rem!important}.atlas-home-guidance-quick{grid-template-columns:1fr;gap:.28rem;margin:.06rem 0 .14rem}.atlas-home-guidance-quick section{padding:.36rem .46rem}.atlas-home-guidance-quick h4{font-size:.92rem}.atlas-home-guidance-quick li{font-size:.825rem;line-height:1.38}.atlas-home-key-numbers{grid-template-columns:repeat(2,minmax(0,1fr));gap:.12rem;padding:.18rem}.atlas-home-key-numbers .atlas-home-guidance-metric{padding:.18rem .22rem}.atlas-home-full-evidence section{padding:.58rem 0}.atlas-home-full-evidence h4{font-size:.95rem;margin-bottom:.32rem}.atlas-home-full-evidence p,.atlas-home-full-reasons li{font-size:.825rem;line-height:1.45}.atlas-home-full-metrics{grid-template-columns:1fr;gap:.18rem}.atlas-home-full-reasons{grid-template-columns:1fr;gap:.55rem}.atlas-home-trade-row{gap:.16rem .38rem;font-size:.84rem}.atlas-home-trade-row span+span::before{margin-right:.38rem}.atlas-home-comparison{grid-template-columns:1fr 1fr}.atlas-home-target{padding:.48rem}.atlas-home-target b{font-size:.92rem}}
    .atlas-home-comparison{grid-template-columns:repeat(auto-fit,minmax(125px,1fr));min-height:0}.atlas-home-win i{display:grid;gap:.12rem;font-style:normal;font-weight:700;color:#d9e3ef}.atlas-home-win i small{font-size:.72rem;line-height:1.3;font-weight:400;color:#96a4b6}
    @media(max-width:700px){.atlas-home-action-counts{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-home-comparison{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-home-comparison .atlas-home-target-current{grid-column:1/-1}.atlas-home-action{grid-template-columns:1fr}.atlas-home-action-stars{grid-row:auto;font-size:1.45rem}.atlas-home-action>small{grid-column:auto}.atlas-home-card-head h3 i{display:block;margin-top:.18rem}}
    </style>""", unsafe_allow_html=True)


def render_home_guidance_vnext(story: Mapping[str, Any], *, emit_interactive=None) -> None:
    """Render persisted Guidance shell; optional context occurs after interactivity."""
    if emit_interactive is None:
        from services.session_stability import emit_page_interactive as emit
        emit_interactive = lambda: emit(st, "Home")
    _inject_css()
    st.markdown(
        f'<span data-atlas-qa="home-guidance-vnext" data-atlas-version="{html.escape(str(story.get("version")))}" '
        f'data-atlas-mode="{html.escape(str(story.get("mode")))}" aria-hidden="true" style="display:none">home-guidance-vnext</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="atlas-home-guidance-hero">'
        '<h1>ATLAS Today</h1>'
        '<span class="atlas-home-guidance-badge">ATLAS Decision Dashboard</span>'
        '<p>High-conviction setups, current stance, and the evidence that matters.</p>'
        f'<small>Production scan: {html.escape(_timestamp(story.get("scan_timestamp")))} · {int(story.get("candidate_count", 0))} candidates</small>'
        '</div>', unsafe_allow_html=True,
    )
    st.markdown(_action_counts(story), unsafe_allow_html=True)
    st.markdown("## Today's ATLAS Actions")
    _render_groups(story, emit_interactive=emit_interactive)


__all__ = ["render_home_guidance_vnext"]
