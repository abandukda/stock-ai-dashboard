"""Grounded, validated AI phrasing for the customer ATLAS View."""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any, Callable, Mapping, Sequence


SUMMARY_VERSION = "ATLAS_VIEW_SUMMARY_V3"
GUIDANCE_STATES = {
    "BUY_NOW", "ACCUMULATE", "WAIT_FOR_ENTRY", "WAIT_FOR_CONFIRMATION", "AVOID", "DATA_LIMITED",
}
TECHNICAL_STATES = {
    "NO_SETUP", "SETUP_FORMING", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED", "EXTENDED", "FAILED_BREAKOUT",
}

PILLAR_101 = {
    "technical_quality": "Is the stock's price trend healthy?",
    "fundamental_quality": "Is the underlying business financially healthy?",
    "valuation_quality": "Does the stock appear reasonably priced?",
    "risk_quality": "How much could go wrong?",
    "entry_quality": "Is today's price a sensible place to enter?",
    "volume_quality": "Is trading activity supporting the move?",
}

ACTION_101 = {
    "BUY NOW": "ATLAS sees an attractive combination of price, company quality, risk, and entry conditions right now.",
    "BUILD A POSITION": "ATLAS likes the opportunity, but suggests adding gradually rather than buying the full position at once.",
    "WAIT FOR BETTER ENTRY": "ATLAS likes the company, but believes the current price is not the best place to buy.",
    "WAIT FOR CONFIRMATION": "The opportunity is promising, but ATLAS is waiting for stronger evidence before acting.",
    "WATCH": "There are some positive signs, but not enough evidence to buy yet.",
    "WATCH — NOT READY YET": "There are some positive signs, but not enough evidence to buy yet.",
    "AVOID": "ATLAS currently sees more risk than opportunity.",
}


def _certified_value(certified: Mapping[str, Any], name: str) -> Any:
    field = dict(dict(certified.get("fields") or {}).get(name) or {})
    return field.get("value") if str(field.get("certification_status") or "").startswith("CERTIFIED") else None


def _customer_amount(value: Any) -> str | None:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    for scale, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(amount) >= scale:
            return f"${amount / scale:,.1f}{suffix}"
    return f"${amount:,.2f}"


def build_certified_summary_facts(card: Mapping[str, Any]) -> dict[str, Any]:
    """Project the sole customer authority into a stable narrative contract."""
    certified = dict(card.get("certified_customer_evaluation") or {})
    if not certified:
        return {}
    domains = dict(certified.get("domains") or {})
    decision = dict(certified.get("decision") or {})
    street = dict(certified.get("wall_street_analysis") or {})
    methods = []
    for method in certified.get("valuation_methods") or ():
        if not isinstance(method, Mapping):
            continue
        value, weight = dict(method.get("value") or {}), dict(method.get("weight") or {})
        if value.get("value") is not None:
            methods.append({"name": method.get("name"), "value": value.get("value"), "weight": weight.get("value")})
    risk = dict(certified.get("risk") or {})
    risk_evidence = dict(risk.get("evidence") or {})
    consensus = dict(street.get("consensus") or {})
    estimates = dict(street.get("estimate_context") or {})
    facts = {
        "ticker": certified.get("ticker") or card.get("ticker"),
        "company": card.get("company"),
        "company_description": dict(card.get("company_evidence") or {}).get("business_summary"),
        "industry": dict(card.get("company_evidence") or {}).get("industry"),
        "current_price": _certified_value(certified, "price"),
        "atlas_fair_value": _certified_value(certified, "atlas_fair_value"),
        "atlas_upside_pct": _certified_value(certified, "atlas_upside_pct"),
        "action": decision.get("action"),
        "revenue": _certified_value(certified, "revenue"),
        "revenue_growth": _certified_value(certified, "revenue_growth_pct"),
        "eps": _certified_value(certified, "eps"),
        "eps_growth": _certified_value(certified, "eps_growth_pct"),
        "operating_margin": _certified_value(certified, "operating_margin_pct"),
        "free_cash_flow": _certified_value(certified, "free_cash_flow"),
        "forward_eps": _certified_value(certified, "forward_eps"),
        "forward_revenue": _certified_value(certified, "forward_revenue"),
        "wall_street_analysis": street,
        "valuation_methods": tuple(methods),
        "primary_risk": next((risk_evidence.get(key) for key in ("primary_risk", "volatility_risk", "drawdown_label") if risk_evidence.get(key)), None),
        "domain_statuses": domains,
        "certification_status": certified.get("customer_publication_allowed"),
    }
    facts["financial_evidence_available"] = any(facts.get(key) is not None for key in (
        "revenue", "revenue_growth", "eps", "eps_growth", "operating_margin", "free_cash_flow", "forward_eps", "forward_revenue",
    ))
    facts["valuation_evidence_available"] = facts["atlas_fair_value"] is not None
    facts["wall_street_evidence_available"] = bool(street.get("status") in {"WALL_STREET_AVAILABLE", "WALL_STREET_PARTIAL"})
    facts["wall_street_coverage"] = {
        "ratings_available": bool(consensus.get("consensus_rating") or street.get("rating_distribution")),
        "target_available": consensus.get("target_mean") is not None,
        "estimates_available": any(value is not None for value in estimates.values()),
        "recent_actions_available": bool(street.get("recent_actions")),
        "analyst_count": consensus.get("analyst_count"),
    }
    facts["valuation_method_count"] = len(methods)
    facts["single_method_concentration"] = len(methods) == 1 and float(methods[0].get("weight") or 0) >= .999
    return facts


def _company_risk(facts: Mapping[str, Any]) -> str:
    raw = str(facts.get("primary_risk") or "").strip().rstrip(".")
    generic = not raw or bool(re.fullmatch(r"(?:shallow|moderate|deep) drawdown", raw, re.I))
    industry = str(facts.get("industry") or "").lower()
    company = str(facts.get("company") or "").lower()
    if generic:
        if any(token in industry + " " + company for token in ("marine", "shipping", "tanker", "teekay")):
            return "exposure to freight rates, vessel use, leverage, and industry cyclicality"
        if any(token in industry + " " + company for token in ("oil", "gas", "energy", "petroleum", "bp p.l.c")):
            return "exposure to commodity prices, refining margins, production, and capital-allocation execution"
        if any(token in industry for token in ("capital markets", "exchange", "financial data")):
            return "exposure to transaction volumes, pricing pressure, and competitive execution"
        if any(token in industry for token in ("biotech", "biotechnology", "pharmaceutical")):
            return "exposure to clinical, regulatory, and commercialization outcomes"
        if any(token in industry for token in ("software", "cloud", "application")):
            return "exposure to growth durability, margins, customer retention, and valuation sensitivity"
    return raw or "the expected business improvement may not arrive"


def build_atlas_street_divergence_explanation(facts: Mapping[str, Any]) -> dict[str, Any]:
    street = dict(facts.get("wall_street_analysis") or {})
    consensus = dict(street.get("consensus") or {})
    atlas, target = facts.get("atlas_fair_value"), consensus.get("target_mean")
    gap = ((float(atlas) / float(target)) - 1) * 100 if atlas is not None and target not in (None, 0) else None
    classification = (
        "NOT_COMPARABLE" if gap is None else "BROADLY_ALIGNED" if abs(gap) < 10 else
        "MODEST_DIVERGENCE" if abs(gap) < 25 else "MATERIAL_DIVERGENCE" if abs(gap) <= 50 else "LARGE_DIVERGENCE"
    )
    methods = sorted((dict(item) for item in facts.get("valuation_methods") or ()), key=lambda item: float(item.get("weight") or 0), reverse=True)
    published = [item for item in methods if item.get("value") is not None]
    direction = "above" if gap is not None and gap > 0 else "below"
    if gap is None:
        explanation = None
    elif published:
        # Explain the gap with the method that most strongly pulls value away
        # from Street, not merely the method with the largest blend weight.
        lead = max(published, key=lambda item: abs(float(item.get("value") or 0) - float(target)))
        explanation = (
            f"ATLAS is {abs(gap):.1f}% {direction} Wall Street. Its largest valuation contribution is "
            f"{str(lead.get('name') or 'the leading certified method').replace('FCFF Discounted Cash Flow', 'long-term cash-flow value').replace('EV / EBITDA', 'operating-earnings peer value')}, "
            f"which indicates ${float(lead['value']):.2f} per share with {float(lead.get('weight') or 0) * 100:.1f}% weight; "
            "analysts' assumptions are not disclosed, so ATLAS cannot attribute the remaining gap to a specific forecast."
        )
    else:
        explanation = "ATLAS and Wall Street differ, but the certified method detail is insufficient to attribute the gap safely."
    return {"atlas_vs_street_pct": round(gap, 2) if gap is not None else None, "classification": classification,
            "direction": direction if gap is not None else None, "explanation": explanation,
            "methods": tuple(published), "street_target_as_of": street.get("as_of")}


def certify_customer_presentation_consistency(text: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    facts = dict(payload.get("certified_summary_facts") or {})
    copy = " ".join(str(text or "").split())
    contradictions = []
    checks = (
        ("FINANCIAL", facts.get("financial_evidence_available"), r"financial evidence (?:is not|isn't) available|financial evidence (?:is )?unavailable"),
        ("VALUATION", facts.get("valuation_evidence_available"), r"valuation (?:is not|isn't) available|valuation unavailable"),
        ("WALL_STREET", facts.get("wall_street_evidence_available"), r"Wall Street (?:information|evidence|consensus) (?:is not|isn't) available|Wall Street unavailable"),
    )
    for domain, available, pattern in checks:
        if available and re.search(pattern, copy, re.I): contradictions.append(f"{domain}_AVAILABILITY_CONTRADICTION")
    coverage = dict(facts.get("wall_street_coverage") or {})
    if coverage.get("ratings_available") and not coverage.get("target_available") and re.search(r"no verified Wall Street consensus", copy, re.I):
        contradictions.append("WALL_STREET_PARTIAL_COVERAGE_CONTRADICTION")
    if facts.get("single_method_concentration") and not re.search(r"one certified valuation method|single.method", copy, re.I):
        contradictions.append("SINGLE_METHOD_CONCENTRATION_OMITTED")
    upside = facts.get("atlas_upside_pct")
    if upside is not None and float(upside) > 75 and not re.search(r"(?:supported|based) (?:by|on).{0,80}(?:certified valuation method|valuation methods)", copy, re.I):
        contradictions.append("EXTREME_UPSIDE_METHOD_BASIS_OMITTED")
    numeric_claims = (
        ("ATLAS_FAIR_VALUE_MISMATCH", r"fair value at \$([\d,]+(?:\.\d+)?)", facts.get("atlas_fair_value")),
        ("CURRENT_PRICE_MISMATCH", r"(?:certified|current) price(?: of| is| at)? \$([\d,]+(?:\.\d+)?)", facts.get("current_price")),
        ("WALL_STREET_TARGET_MISMATCH", r"Wall Street(?:'s)? average target is \$([\d,]+(?:\.\d+)?)", dict(facts.get("wall_street_analysis") or {}).get("consensus", {}).get("target_mean")),
        ("FORWARD_EPS_MISMATCH", r"forward earnings are \$([\d,]+(?:\.\d+)?) per share", facts.get("forward_eps")),
    )
    for code, pattern, expected in numeric_claims:
        match = re.search(pattern, copy, re.I)
        if match and (expected is None or abs(float(match.group(1).replace(",", "")) - float(expected)) > .015):
            contradictions.append(code)
    if facts.get("forward_eps") is None and re.search(r"forward (?:EPS|earnings)(?: are| is|:) +\$?0(?:\.0+)?\b", copy, re.I):
        contradictions.append("UNAVAILABLE_FORWARD_EPS_RENDERED_AS_ZERO")
    divergence_claim = re.search(r"ATLAS is ([\d.]+)% (above|below) Wall Street", copy, re.I)
    if divergence_claim:
        governed = build_atlas_street_divergence_explanation(facts)
        expected_gap = governed.get("atlas_vs_street_pct")
        expected_direction = governed.get("direction")
        if expected_gap is None or abs(float(divergence_claim.group(1)) - abs(float(expected_gap))) > .11 or divergence_claim.group(2).lower() != expected_direction:
            contradictions.append("ATLAS_STREET_DIVERGENCE_MISMATCH")
    risk_claim = re.search(r"The main certified risk is (.+?)(?:\.|$)", copy, re.I)
    if risk_claim:
        expected_risk = _company_risk(facts).lower().strip()
        actual_risk = risk_claim.group(1).lower().strip()
        allowed_risks = {expected_risk}
        if str(dict(facts.get("wall_street_analysis") or {}).get("recent_trend") or "").upper() == "DETERIORATING":
            allowed_risks.add(expected_risk + " and deteriorating analyst actions")
        if actual_risk not in allowed_risks:
            contradictions.append("CERTIFIED_RISK_MISMATCH")
    safe = copy
    if contradictions:
        sentences = [sentence for sentence in re.split(r"(?<=[.!?])\s+", copy) if not any(
            code.startswith(domain) and re.search(pattern, sentence, re.I)
            for domain, available, pattern in checks for code in contradictions
        )]
        safe = " ".join(sentences)
    return {"valid": not contradictions, "violations": tuple(contradictions), "safe_text": safe}

def thesis_style_violations(text: str) -> tuple[str, ...]:
    """Client-language checks only; this function has no investment authority."""
    copy=" ".join(str(text or "").split()); issues=[]
    sentences=[part for part in re.split(r"(?<=[.!?])\s+",copy) if part]
    if any(len(sentence.split())>65 for sentence in sentences): issues.append("OVERLY_LONG_SENTENCE")
    if len(re.findall(r"\b(?:score|confidence|coverage|pillar)\b",copy,re.I))>=4: issues.append("EXCESSIVE_SCORE_LISTING")
    if len(re.findall(r"\bATLAS sees\b",copy,re.I))>=2: issues.append("REPEATED_ATLAS_SEES")
    if re.search(r"\b(?:all gates passed|governed gates|reason codes?|policy version)\b",copy,re.I): issues.append("MECHANICAL_INTERNAL_TONE")
    jargon=set(re.findall(r"\b(?:WACC|FCFF|ROIC|beta|terminal value|terminal growth|EV/EBITDA|estimate revisions?)\b",copy,re.I))
    if len(jargon)>5: issues.append("EXCESSIVE_JARGON_DENSITY")
    if jargon and not re.search(r"\b(?:because|which|meaning|means|so |reflects|depends|sensitive)\b",copy,re.I): issues.append("MISSING_EDUCATIONAL_INTERPRETATION")
    if copy and not re.search(r"\b(?:risk|uncertain|sensitive|could weaken|depends|but|too weak|incomplete|deteriorat)\b",copy,re.I): issues.append("MISSING_RISK_EXPLANATION")
    return tuple(issues)


def _valuation_comparison(card: Mapping[str, Any]) -> dict[str, Any]:
    atlas = card.get("atlas_fair_value") if str(card.get("atlas_valuation_status") or "").upper() == "PUBLISHED" else None
    street = dict(card.get("wall_street") or {})
    street_visible = street.get("commercial_display_status") == "DISPLAY_ALLOWED" or street.get("display_scope") == "INTERNAL_TRIAL"
    street_target = street.get("mean_target") if street_visible else None
    gap = None
    if atlas is None:
        state = "ATLAS_VALUATION_UNAVAILABLE"
    elif street_target is None or float(street_target) == 0:
        state = "WALL_STREET_UNAVAILABLE"
    else:
        gap = ((float(atlas) / float(street_target)) - 1.0) * 100.0
        state = "ATLAS_MORE_BULLISH" if gap > 15.0 else "WALL_STREET_MORE_BULLISH" if gap < -15.0 else "ALIGNED"
    return {"state": state, "atlas_target": atlas, "street_target": street_target,
            "target_gap_pct": round(gap, 2) if gap is not None else None}


def _openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key
    try:
        import streamlit as st
        return str(st.secrets.get("OPENAI_API_KEY", "")).strip()
    except Exception:
        return ""


def llm_configuration_status() -> dict[str, Any]:
    available = bool(_openai_key())
    return {
        "available": available,
        "required_secret": None if available else "OPENAI_API_KEY",
        "model": os.getenv("ATLAS_LLM_MODEL", "gpt-4o-mini"),
    }


def build_summary_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    certified_facts = dict(card.get("certified_summary_facts") or build_certified_summary_facts(card))
    certification = dict(card.get("publication_certification") or {})
    certified_components = dict(certification.get("components") or {})
    def allowed(name: str) -> bool:
        return str((certified_components.get(name) or {}).get("state")) in {"CERTIFIED", "CERTIFIED_HIGH_UNCERTAINTY"}
    persisted_technical = dict(card.get("technical_evidence") or {})
    canonical_technical = dict(card.get("canonical_technical_evidence") or {})
    technical = canonical_technical or persisted_technical
    volume = dict(card.get("volume_evidence") or {})
    recovery = dict(card.get("recovery") or {})
    trade = dict(card.get("trade_plan") or {})
    market = dict(card.get("market_evidence") or {})
    fundamentals = dict(card.get("fundamentals_evidence") or {})
    company = dict(card.get("company_evidence") or {})
    wall_street = dict(card.get("wall_street") or {})
    wall_street_analysis = dict(card.get("wall_street_analysis") or {})
    if not wall_street_analysis and (
        wall_street.get("display_scope") == "INTERNAL_TRIAL" or
        wall_street.get("commercial_display_status") == "DISPLAY_ALLOWED"
    ):
        from engines.analyst_intelligence import build_analyst_intelligence
        wall_street_analysis = dict(build_analyst_intelligence({
            "current_price": card.get("display_price"),
            "analyst_target_mean": wall_street.get("mean_target"),
            "analyst_target_median": wall_street.get("median_target"),
            "analyst_target_low": wall_street.get("low_target"),
            "analyst_target_high": wall_street.get("high_target"),
            "analyst_count": wall_street.get("analyst_count"),
            "recommendation_key": wall_street.get("rating"),
            "atlas_fair_value": card.get("atlas_fair_value"),
            "atlas_fv_upside_pct": card.get("atlas_expected_return"),
        }).get("wall_street_analysis") or {})
    context = dict(card.get("context_evidence") or {})
    internal_lanes = dict(card.get("internal_evidence_lanes") or {})
    evaluation = dict(card.get("evaluation") or {})
    pillars = {
        key: dict(evaluation.get(key) or {}) for key in (
            "technical_quality", "fundamental_quality", "valuation_quality",
            "risk_quality", "entry_quality", "volume_quality",
        )
    }
    risk = dict(evaluation.get("risk") or {})
    valuation = dict(evaluation.get("atlas_valuation") or {})
    professional_valuation = dict(valuation.get("professional_valuation_v2") or {})
    valuation_drivers = dict(card.get("valuation_driver_evidence") or {})
    if certification:
        if not allowed("technical"): canonical_technical = persisted_technical = technical = {}
        if not allowed("volume"): volume = {}
        if not allowed("trade_plan"): trade = {}
        if not allowed("market"): market = {}
        if not allowed("fundamentals"): fundamentals = company = {}
        if not allowed("risk"): risk = {}
        if not allowed("valuation"):
            valuation = professional_valuation = valuation_drivers = {}
        context_state = dict(certification.get("optional_context") or {})
        if context_state.get("wall_street") != "CONTEXT_VALIDATED": wall_street = {}
        if context_state.get("news") != "CONTEXT_VALIDATED": card = {**dict(card), "recent_catalysts": ()}
    catalysts = []
    for item in (card.get("recent_catalysts") or ())[:3]:
        if isinstance(item, Mapping):
            catalysts.append({
                "headline": item.get("title") or item.get("headline"), "category": item.get("category"),
                "published_at": item.get("published_at"), "source": item.get("publisher") or item.get("source"),
                "evidence_id": item.get("evidence_id") or item.get("id"),
                "evidence_summary": item.get("summary") or item.get("why_it_matters"),
            })
    return {
        "certified_summary_facts": certified_facts,
        "ticker": card.get("ticker"), "company": card.get("company"),
        "production_rank": card.get("production_rank"), "setup_score": card.get("scan_conviction"),
        "setup_score_scale": 100, "indicator_periods": [20, 50, 200],
        "price": card.get("display_price") if not certification or allowed("market") else None, "price_label": card.get("display_price_label"),
        "market_session": market.get("market_session"), "market_status": market.get("status"),
        "market_timestamp": market.get("provider_timestamp"),
        "canonical_technical_state": card.get("technical_state") if card.get("technical_status") == "AVAILABLE" else "UNAVAILABLE",
        "sma20": technical.get("sma20"), "sma50": technical.get("sma50"), "sma200": technical.get("sma200"),
        "rsi": technical.get("rsi14") if canonical_technical else technical.get("rsi"), "entry_relationship": card.get("entry_relationship"),
        "entry_low": trade.get("entry_low"), "entry_high": trade.get("entry_high"),
        "support": technical.get("support"), "resistance": technical.get("pivot") if canonical_technical else technical.get("resistance"),
        "stop": trade.get("stop") if trade.get("stop") is not None else trade.get("stop_loss"),
        "target_1": trade.get("target_1") if trade.get("target_1") is not None else trade.get("target"),
        "recovery_score": recovery.get("score"), "recovery_state": recovery.get("state"),
        "atlas_fair_value": card.get("atlas_fair_value") if not certification or allowed("valuation") else None, "atlas_fv_status": card.get("atlas_valuation_status") if not certification or allowed("valuation") else "NOT_PUBLISHED",
        "expected_return": card.get("atlas_expected_return") if not certification or allowed("valuation") else None,
        "contextual_rvol": volume.get("relative_volume"), "volume_status": card.get("volume_status"),
        "bar_quality": (card.get("completed_bar_quality") or {}).get("status"),
        "fundamentals_status": card.get("fundamentals_status"), "risk_status": card.get("risk_status"),
        "company_evidence": company,
        "fundamentals": fundamentals,
        "latest_earnings": {key: company.get(key) for key in (
            "latest_earnings_date", "reported_eps", "eps_estimate", "eps_surprise_pct",
            "reported_revenue", "revenue_estimate", "revenue_surprise_pct",
        )},
        "forward_outlook": {key: company.get(key) for key in (
            "forward_eps", "forward_revenue", "estimate_revision", "estimate_contributor_count", "next_earnings_date",
        )},
        "forward_estimate_evidence": dict(company.get("forward_estimate_evidence") or {}),
        "atlas_valuation": {
            "status": card.get("atlas_valuation_status") if not certification or allowed("valuation") else "NOT_PUBLISHED", "target": card.get("atlas_fair_value") if not certification or allowed("valuation") else None,
            "expected_return": card.get("atlas_expected_return") if not certification or allowed("valuation") else None,
            "driver_evidence": valuation_drivers,
            "rejection_reasons": list(valuation.get("reason_codes") or valuation.get("reasons") or ()),
            "professional_valuation_v2": professional_valuation,
        },
        "wall_street": wall_street,
        "wall_street_analysis": wall_street_analysis,
        "insider_ownership_political_context": context,
        "internal_trial_evidence": internal_lanes,
        "valuation_comparison": _valuation_comparison(card),
        "risk_evidence": {
            "status": card.get("risk_status"), "canonical": risk.get("evidence"),
            "strongest_fundamental_risk": company.get("primary_risk"),
            "valuation_risk": valuation.get("risk") or valuation.get("risk_status"),
            "technical_risk": list(card.get("why_atlas") or ())[:2],
        },
        "guidance": card.get("guidance"), "actionability": card.get("actionability"),
        "publication_certification_state": certification.get("certification_state"),
        "opportunity_thesis": card.get("opportunity_thesis"),
        "customer_action": (card.get("customer_action") or {}).get("label"),
        "six_pillars": pillars,
        "opportunity": evaluation.get("opportunity", card.get("opportunity")),
        "component_coverage": evaluation.get("component_coverage"),
        "decision_confidence": evaluation.get("decision_confidence", card.get("decision_confidence")),
        "decision_metrics_methodology": evaluation.get("decision_metrics_methodology"),
        "reason_codes": list(card.get("reason_codes") or ()),
        "allowed_change_conditions": list(card.get("what_changes_guidance") or ()),
        "commercial_catalysts": catalysts,
        "pillar_explanations": PILLAR_101,
    }


def plain_english_summary(payload: Mapping[str, Any]) -> str:
    """Explain certified facts for a first-time investor; never make a decision."""
    facts = dict(payload.get("certified_summary_facts") or {})
    if facts:
        company = str(facts.get("company") or facts.get("ticker") or "This company")
        financial = []
        for label, key in (("revenue growth", "revenue_growth"), ("earnings growth", "eps_growth")):
            if facts.get(key) is not None:
                value = float(facts[key]); value = value * 100 if abs(value) <= 1 and value not in (0, -0.5) else value
                financial.append(f"{label} was {value:.1f}%")
        if facts.get("free_cash_flow") is not None and float(facts["free_cash_flow"]) > 0:
            financial.append(f"free cash flow was {_customer_amount(facts['free_cash_flow'])}")
        if facts.get("forward_eps") is not None:
            financial.append(f"forward earnings are ${float(facts['forward_eps']):.2f} per share")
        if facts.get("forward_revenue") is not None:
            financial.append(f"forward revenue is about {_customer_amount(facts['forward_revenue'])}")
        description = str(facts.get("company_description") or "").strip()
        if description:
            description = next((part.strip().rstrip(".") for part in re.split(r"(?<=[.!?])\s+", description) if part.strip()), "")
        description_identity = re.sub(r"[^a-z0-9]+", "", description.lower())
        company_identity = re.sub(r"[^a-z0-9]+", "", company.lower())
        same_identity = bool(
            description_identity
            and company_identity
            and (
                description_identity == company_identity
                or description_identity in company_identity
                or company_identity in description_identity
            )
        )
        identity = f"{description}. " if description and not same_identity and len(description.split()) <= 14 else ""
        opening = (
            identity + f"{company}'s financial record shows " + " and ".join(financial[:2]) + "."
            if financial else f"{company}'s available certified record is focused on its market setup rather than a detailed financial growth case."
        )
        atlas, upside = facts.get("atlas_fair_value"), facts.get("atlas_upside_pct")
        if atlas is not None and upside is not None:
            valuation = f"ATLAS estimates fair value at ${float(atlas):.2f}, implying {float(upside):.1f}% potential from the certified price."
            methods = tuple(facts.get("valuation_methods") or ())
            if facts.get("single_method_concentration") and methods:
                method_name = str(methods[0].get("name") or "the available method").replace("EV / EBITDA", "operating-earnings peer value").replace("FCFF Discounted Cash Flow", "long-term cash-flow value")
                valuation += f" The estimate is based on one certified valuation method—{method_name}—so it carries more model concentration than a multi-method valuation."
                if float(upside) > 75:
                    valuation += f" ATLAS's {float(upside):.1f}% upside is supported by this single certified valuation method."
        else:
            valuation = "ATLAS has not published a fair value for this snapshot."
        divergence = build_atlas_street_divergence_explanation(facts)
        street = dict(facts.get("wall_street_analysis") or {}); consensus = dict(street.get("consensus") or {})
        coverage = dict(facts.get("wall_street_coverage") or {})
        if facts.get("wall_street_evidence_available") and consensus.get("target_mean") is not None:
            street_copy = f"Wall Street's average target is ${float(consensus['target_mean']):.2f}"
            if consensus.get("analyst_count") is not None: street_copy += f" across {int(consensus['analyst_count'])} analysts"
            street_copy += ";"
            if divergence.get("classification") not in {"NOT_COMPARABLE", "BROADLY_ALIGNED"}:
                if facts.get("single_method_concentration"):
                    gap = float(divergence.get("atlas_vs_street_pct") or 0)
                    direction = "above" if gap > 0 else "below"
                    explanation = f"ATLAS is {abs(gap):.1f}% {direction} Wall Street, while analysts' detailed assumptions are not disclosed."
                else:
                    explanation = str(divergence.get("explanation") or "")
                    explanation = explanation.replace("Wall Street. Its", "Wall Street because its", 1)
                street_copy += " " + explanation
            trend = str(street.get("recent_trend") or "").upper()
            if trend == "DETERIORATING": street_copy = street_copy.rstrip(".") + "; recent analyst actions have deteriorated."
        elif coverage.get("ratings_available"):
            rating = str(consensus.get("consensus_rating") or "ratings").title()
            count = f" from {int(coverage['analyst_count'])} analysts" if coverage.get("analyst_count") is not None else ""
            street_copy = f"Wall Street ratings are available{count} with a {rating} consensus, but ATLAS does not have a verified consensus price target for this snapshot."
        else:
            street_copy = "A verified Wall Street comparison is not available for this snapshot."
        action = str(facts.get("action") or payload.get("customer_action") or "WATCH").replace("_", " ")
        action_label = {"ACCUMULATE": "BUILD A POSITION", "DATA LIMITED": "WATCH"}.get(action, action)
        action_reason = ACTION_101.get(action_label, ACTION_101["WATCH"])
        if action_reason.startswith("ATLAS "):
            action_reason = "it " + action_reason[6:7].lower() + action_reason[7:]
        risk = _company_risk(facts)
        trend_risk = " and deteriorating analyst actions" if str(street.get("recent_trend") or "").upper() == "DETERIORATING" else ""
        closing = f"ATLAS rates the stock {action_label} because {action_reason.rstrip('.')}. The main certified risk is {risk}{trend_risk}."
        return " ".join((opening, valuation, street_copy, closing))
    company = str(payload.get("company") or payload.get("ticker") or "This company")
    company_evidence = dict(payload.get("company_evidence") or {})
    fundamentals = dict(payload.get("fundamentals") or {})
    raw_description = str(company_evidence.get("business_summary") or "").strip()
    description = next((part.strip().rstrip(".") for part in re.split(r"(?<=[.!?])\s+", raw_description) if part.strip()), "")
    if not description or len(description.split()) > 24:
        opening = f"Company-specific financial evidence is not available for {company}, so this view is limited to its developing market setup."
    else:
        opening = f"{company}: {description}." if company.lower() not in description.lower() else f"{description}."
    supports = []
    for label, value in (("revenue growth", fundamentals.get("revenue_growth")), ("earnings growth", company_evidence.get("earnings_growth"))):
        try:
            number = float(value) * (100 if abs(float(value)) <= 2 else 1)
            supports.append(f"{label} of {number:.1f}%")
        except (TypeError, ValueError):
            pass
    if fundamentals.get("free_cash_flow") is not None:
        try:
            if float(fundamentals["free_cash_flow"]) > 0:
                supports.append("the business generated cash after operating and investment spending")
        except (TypeError, ValueError):
            pass
    outlook = "The investment case depends on " + (" and ".join(supports[:2]) if supports else "the available company evidence producing stronger future earnings") + ", which could increase the company's value."
    atlas = dict(payload.get("atlas_valuation") or {})
    if atlas.get("status") == "PUBLISHED" and atlas.get("target") is not None and atlas.get("expected_return") is not None:
        upside = float(atlas["expected_return"])
        price_view = "cheap" if upside >= 15 else "fairly priced" if upside > -10 else "expensive"
        valuation = f"ATLAS considers the shares {price_view}: its ${float(atlas['target']):.2f} fair value implies {upside:.1f}% upside based on expected profits and how comparable companies are valued."
    else:
        valuation = "ATLAS has not published a fair value because the certified valuation evidence is not sufficient."
    wall = dict(payload.get("wall_street_analysis") or {})
    consensus = dict(wall.get("consensus") or {})
    comparison = dict(wall.get("atlas_comparison") or {})
    if wall.get("display_authority") == "COMMERCIAL_RIGHTS_UNCONFIRMED":
        street = "Wall Street information is not shown because commercial-use permission is not confirmed."
    elif wall.get("status") in {"WALL_STREET_AVAILABLE", "WALL_STREET_PARTIAL"} and consensus.get("target_mean") is not None:
        street = f"Wall Street's average target is ${float(consensus['target_mean']):.2f}"
        if consensus.get("implied_upside_pct") is not None:
            street += f", or {float(consensus['implied_upside_pct']):.1f}% potential"
        relation = comparison.get("relationship")
        relation_copy = {
            "ATLAS MORE CONSTRUCTIVE": f"ATLAS is more bullish than Wall Street's ${float(consensus['target_mean']):.2f} average target.",
            "WALL STREET MORE CONSTRUCTIVE": f"Wall Street is more bullish than ATLAS at its ${float(consensus['target_mean']):.2f} average target.",
            "BROADLY ALIGNED": "ATLAS and analysts reach a similar valuation conclusion.",
            "MATERIAL DIVERGENCE": "ATLAS and analysts disagree materially about value.",
        }.get(relation, "")
        street = street + "; " + relation_copy
    else:
        street = "No verified Wall Street consensus is currently available; the ATLAS rating relies on its own certified evidence."
    action = str(payload.get("customer_action") or payload.get("guidance") or "WATCH").replace("_", " ")
    if action in {"DATA LIMITED", "UNAVAILABLE"}: action = "WATCH"
    action_copy = ACTION_101.get(action, ACTION_101["WATCH"])
    action_reason = action_copy.rstrip(".")
    if not action_reason.startswith("ATLAS "):
        action_reason = action_reason[:1].lower() + action_reason[1:]
    risk = dict(payload.get("risk_evidence") or {}).get("strongest_fundamental_risk")
    if isinstance(risk, (list, tuple)): risk = next((str(item) for item in risk if item), None)
    volume = dict(payload.get("six_pillars") or {}).get("volume_quality") or {}
    weak_volume = volume.get("score") is not None and float(volume.get("score")) < 50
    industry = str(company_evidence.get("industry") or "").lower()
    industry_risk = "fertilizer demand and pricing could weaken profits" if "fertilizer" in industry else None
    risk_copy = str(risk).strip().rstrip(".") if risk else (industry_risk or ("trading activity is not yet supporting the move" if weak_volume else "the expected improvement may not arrive"))
    watch = "stronger trading activity and business progress" if weak_volume else "continued business progress"
    return " ".join((opening, outlook, valuation, street, f"ATLAS rates the stock {action} because {action_reason}; the main risk is that {risk_copy}, so watch for {watch}."))


def deterministic_summary(payload: Mapping[str, Any]) -> str:
    return plain_english_summary(payload)
    # Retained below for backward-compatible source archaeology; unreachable.
    ticker = str(payload.get("ticker") or "This candidate")
    company = str(payload.get("company") or ticker)
    fundamentals, company_evidence = dict(payload.get("fundamentals") or {}), dict(payload.get("company_evidence") or {})
    atlas, comparison = dict(payload.get("atlas_valuation") or {}), dict(payload.get("valuation_comparison") or {})
    drivers = dict(atlas.get("driver_evidence") or {})
    thesis = str(payload.get("opportunity_thesis") or "DEVELOPING_SETUP").upper()

    def pct(value: Any) -> str | None:
        try:
            number = float(value); number = number * 100 if abs(number) <= 2 else number
            return f"{number:.1f}%"
        except (TypeError, ValueError):
            return None

    financial = []
    if pct(fundamentals.get("revenue_growth")): financial.append(f"revenue growth of {pct(fundamentals['revenue_growth'])}")
    if pct(company_evidence.get("earnings_growth")): financial.append(f"earnings growth of {pct(company_evidence['earnings_growth'])}")
    if company_evidence.get("eps_surprise_pct") is not None: financial.append(f"an EPS surprise of {pct(company_evidence['eps_surprise_pct'])}")
    if fundamentals.get("free_cash_flow") is not None and float(fundamentals["free_cash_flow"]) > 0: financial.append("positive free cash flow")
    support = " and ".join(financial[:2]) or "the available operating evidence"
    raw_business_summary = str(company_evidence.get("business_summary") or "").strip()
    # A profile can be several paragraphs long. The thesis needs the core
    # business model, not a pasted company biography.
    business_summary = next((part.strip() for part in re.split(r"(?<=[.!?])\s+", raw_business_summary) if part.strip()), "").rstrip(".")
    if len(business_summary.split()) > 22:
        business_summary = ""
    industry = str(company_evidence.get("industry") or "").strip().lower()
    domain = f" in {industry}" if industry else ""
    company_context = f"{business_summary}; " if business_summary else ""
    try: revenue_growth = float(fundamentals.get("revenue_growth"))
    except (TypeError, ValueError): revenue_growth = None
    try: earnings_growth = float(company_evidence.get("earnings_growth"))
    except (TypeError, ValueError): earnings_growth = None
    if thesis == "VALUE_RERATING" and revenue_growth is not None and revenue_growth < 0:
        value_opening = f"{company_context}{company}'s rerating case depends on earnings and cash-flow improvement overcoming a {pct(revenue_growth)} revenue contraction{domain}."
    elif thesis == "VALUE_RERATING" and earnings_growth is not None and earnings_growth < 0:
        value_opening = f"{company_context}{company}'s rerating case rests on {pct(revenue_growth) + ' revenue growth' if revenue_growth is not None else 'revenue momentum'} eventually restoring earnings power after a {pct(earnings_growth)} earnings decline{domain}."
    elif thesis == "VALUE_RERATING" and revenue_growth is not None and earnings_growth is not None and revenue_growth >= 20 and earnings_growth >= 20:
        value_opening = f"{company_context}{company} could rerate if broad operating momentum—{pct(revenue_growth)} revenue growth and {pct(earnings_growth)} earnings growth—proves durable{domain}."
    elif thesis == "VALUE_RERATING" and earnings_growth is not None and earnings_growth >= 20:
        value_opening = f"{company_context}{company} could rerate as {pct(earnings_growth)} earnings growth outpaces {pct(revenue_growth) + ' revenue growth' if revenue_growth is not None else 'the current sales trend'}, signaling stronger operating leverage{domain}."
    else:
        value_opening = f"{company_context}{company} could rerate over the next 6–12 months if {support} translates into greater earnings power than the market currently reflects{domain}."
    opening = {
        "VALUE_RERATING": value_opening,
        "QUALITY_GROWTH": f"{company_context}{company}'s upside depends on sustaining {support}, which could compound future earnings power{domain}.",
        "ATTRACTIVE_ENTRY": f"{company_context}{company} offers potential upside from {support} while the current price remains favorable relative to published value{domain}.",
        "RECOVERY": f"{company_context}{company}'s recovery case depends on {support} developing into a durable improvement in operating performance{domain}.",
        "BREAKOUT": f"{company_context}{company}'s near-term upside case is a confirmed market breakout supported by {support}{domain}.",
    }.get(thesis, (
        f"{company_context}{company}'s available business and financial evidence supports a developing market opportunity tied to {support}{domain}."
        if business_summary or financial else
        f"Company-specific financial evidence is not available for {company}, so this view is limited to its developing market setup."
    ))
    industry_driver = (
        "coal volumes, realized pricing, and mining costs are the operating variables to watch" if "coal" in industry else
        "commodity realizations, refining economics, and capital discipline are the operating variables to watch" if "oil & gas" in industry else
        "product demand, clinical execution, and portfolio durability are the operating variables to watch" if any(token in industry for token in ("drug", "biotech", "pharma")) else
        "customer demand, recurring economics, and margin execution are the operating variables to watch" if "software" in industry else
        "sales demand, pricing, and margin execution are the operating variables to watch" if "retail" in industry else
        "industry demand, pricing, and execution are the operating variables to watch" if industry else ""
    )
    if industry_driver:
        opening = opening.rstrip(".") + f"; {industry_driver}."
    if atlas.get("status") == "PUBLISHED" and atlas.get("expected_return") is not None and float(atlas["expected_return"]) <= 0:
        opening = f"{company_context}{company}'s operating case is supported by {support}{domain}, but the current price already exceeds ATLAS's professionally derived base fair value."

    if atlas.get("status") == "PUBLISHED" and atlas.get("target") is not None:
        inputs = []
        professional = dict(atlas.get("professional_valuation_v2") or {})
        professional_explanation = dict(professional.get("valuation_explanation") or {})
        published_models = [model for model in professional.get("models") or () if model.get("status") == "PUBLISHED"]
        if published_models:
            inputs.append(" and ".join(str(model.get("name")) for model in published_models[:2]))
        if drivers.get("forward_eps") is not None: inputs.append(f"forward EPS of ${float(drivers['forward_eps']):.2f}")
        if drivers.get("justified_pe") is not None: inputs.append(f"a {float(drivers['justified_pe']):.1f}× justified earnings multiple")
        if pct(drivers.get("growth_input_pct")): inputs.append(f"a {pct(drivers['growth_input_pct'])} growth input")
        rationale = str(professional_explanation.get("primary_valuation_driver") or " and ".join(inputs[:2]) or support).strip().rstrip(".")
        uncertainty_flags = set((professional.get("valuation_diagnostics") or {}).get("flags") or ())
        uncertainty_note = (
            " The valuation is highly sensitive because most DCF value lies beyond the explicit forecast period."
            if "TERMINAL_VALUE_DEPENDENCE_HIGH" in uncertainty_flags else
            " ATLAS's professional methods disagree materially, which lowers valuation confidence."
            if "MODEL_DISPERSION_HIGH" in uncertainty_flags else
            " Only one complete professional method is available, limiting valuation confidence."
            if "MODEL_CONCENTRATION_SINGLE_METHOD" in uncertainty_flags else ""
        )
        support_phrase = f"the model evidence that {rationale}" if "contributes" in rationale.lower() else rationale
        valuation_sentence = f"From a current price of ${float(payload.get('price')):.2f}, ATLAS's ${float(atlas['target']):.2f} fair value implies {float(atlas.get('expected_return') or 0):.1f}% upside, supported by {support_phrase}.{uncertainty_note}"
    else:
        valuation_sentence = "ATLAS has not published a fair value because the available valuation evidence is insufficient."

    street_target, gap = comparison.get("street_target"), comparison.get("target_gap_pct")
    state = str(comparison.get("state") or "")
    if street_target is not None:
        relation = {"ATLAS_MORE_BULLISH":"more bullish than", "WALL_STREET_MORE_BULLISH":"less bullish than", "ALIGNED":"broadly aligned with"}.get(state, "compared with")
        if abs(float(gap or 0)) > 15 and atlas.get("status") == "PUBLISHED":
            explanation = str(professional_explanation.get("atlas_vs_street") or (
                "the difference is grounded in " + " and ".join(inputs[:2])
                if inputs else "the currently available evidence does not fully explain the valuation gap"
            )).strip().rstrip(".")
            street_sentence = f"ATLAS is {relation} Wall Street's ${float(street_target):.2f} average target; {explanation}."
        else:
            street_sentence = f"ATLAS is {relation} Wall Street's ${float(street_target):.2f} average target."
    else:
        street_sentence = "A commercially displayable Wall Street comparison is not available."

    catalyst = next(iter(payload.get("commercial_catalysts") or ()), {})
    catalyst_impact = str(catalyst.get('evidence_summary') or 'may affect forward estimates and execution').strip().rstrip('.')
    catalyst_impact = catalyst_impact[:1].lower() + catalyst_impact[1:] if catalyst_impact else "may affect forward estimates and execution"
    catalyst_sentence = f"The latest material catalyst is “{str(catalyst.get('headline')).strip().rstrip('.!?')},” which {catalyst_impact}." if catalyst.get("headline") else ""
    catalyst_sentence = catalyst_sentence.replace(" .", ".")

    reasons = set(payload.get("reason_codes") or ())
    technical_state = str(payload.get("canonical_technical_state") or "")
    action = str(payload.get("customer_action") or payload.get("guidance") or "WATCH").replace("_", " ")
    if action in {"DATA LIMITED", "UNAVAILABLE"}: action = "WATCH"
    blocker = (
        "price is above the preferred entry area" if "PRICE_ABOVE_ENTRY_RANGE" in reasons else
        "technical confirmation remains incomplete" if action == "WAIT FOR CONFIRMATION" else
        "the entry is not yet attractive" if action == "WAIT FOR BETTER ENTRY" else
        "the setup is not yet actionable" if action == "WATCH" else
        "the evidence supports only a staged initial position" if action == "BUILD A POSITION" else
        "a break in operating or price evidence would invalidate the current entry"
    )
    risk = dict(payload.get("risk_evidence") or {}).get("strongest_fundamental_risk")
    if isinstance(risk, (list, tuple)): risk = next((str(item) for item in risk if item), None)
    if risk and re.search(r"no (?:major )?(?:financial )?(?:red flag|risk)", str(risk), re.I): risk = None
    risk_copy = str(risk).strip().rstrip(".") if risk else blocker
    action_reason = (
        "the financial, valuation, risk, and entry evidence currently align" if action == "BUY NOW" else
        "the opportunity is attractive, but a staged position better reflects the remaining uncertainty" if action == "BUILD A POSITION" else
        blocker
    )
    action_sentence = f"The risk to watch is {risk_copy}; ATLAS's {action} stance reflects that {action_reason}."
    return " ".join(part for part in (opening, valuation_sentence, street_sentence, catalyst_sentence, action_sentence) if part)


def _numbers(value: Any) -> list[float]:
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _numbers(nested)]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in _numbers(nested)]
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, str):
        return [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", value.replace(",", ""))]
    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


def validate_summary(text: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    copy = " ".join(str(text or "").split())
    violations: list[str] = list(thesis_style_violations(copy))
    if not 3 <= len([part for part in re.split(r"(?<=[.!?])\s+", copy) if part]) <= 5:
        violations.append("SENTENCE_COUNT")
    # The product contract permits the fixed investment horizon; it is not an
    # evidence claim sourced from a ticker payload.
    allowed = _numbers(payload) + [6.0, 12.0]
    for lane in (payload.get("fundamentals") or {}, payload.get("latest_earnings") or {}, payload.get("forward_outlook") or {}):
        for key, value in dict(lane).items():
            if any(token in str(key).lower() for token in ("growth", "margin", "surprise")):
                try:
                    numeric = float(value)
                    if abs(numeric) <= 1:
                        allowed.append(numeric * 100)
                except (TypeError, ValueError):
                    pass
    for token in re.findall(r"(?<![A-Za-z])\$?(-?\d+(?:\.\d+)?)", copy.replace(",", "")):
        number = float(token)
        if not any(abs(number - value) <= max(0.011, abs(value) * 0.0001) for value in allowed):
            violations.append("UNSOURCED_NUMBER")
            break
    upper = re.sub(r"[^A-Z0-9]+", "_", copy.upper())
    mentioned_guidance = {state for state in GUIDANCE_STATES if state in upper}
    canonical_guidance = str(payload.get("guidance") or "DATA_LIMITED").upper()
    if "DATA LIMITED" in copy.upper() or "DATA_LIMITED" in upper:
        violations.append("INTERNAL_GUIDANCE_EXPOSED")
    if re.search(r"\b(?:DISCOVERY\s+)?RANK\b|\bSETUP SCORE\b|\bSCAN CONVICTION\b", copy, re.I):
        violations.append("PRIMARY_THESIS_DASHBOARD_LANGUAGE")
    if re.search(r"\b(?:governed|investment-quality|technical) gates?\b|\ball (?:buy|accumulate) gates passed\b", copy, re.I):
        violations.append("GENERIC_GATE_LANGUAGE")
    if "RECOVERY SCORE" in copy.upper() or re.search(r"\b\d+(?:\.\d+)?×\s+(?:CONTEXTUAL\s+)?VOLUME\b", copy, re.I):
        violations.append("RAW_DASHBOARD_METRIC_RECITATION")
    if any(state != canonical_guidance for state in mentioned_guidance):
        violations.append("UNSUPPORTED_GUIDANCE")
    thesis = str(payload.get("opportunity_thesis") or "").upper()
    thesis_labels = {
        "QUALITY_GROWTH": "QUALITY GROWTH", "VALUE_RERATING": "VALUE RERATING",
        "RECOVERY": "RECOVERY", "ATTRACTIVE_ENTRY": "ATTRACTIVE ENTRY",
        "BREAKOUT": "BREAKOUT", "DEVELOPING_SETUP": "DEVELOPING SETUP",
    }
    mentioned_theses = {
        key for key, label in thesis_labels.items()
        if re.search(rf"\b{re.escape(label)}\s+(?:OPPORTUNITY|THESIS)\b|\b(?:OPPORTUNITY|THESIS)\s*:\s*{re.escape(label)}\b", copy, re.I)
    }
    if any(item != thesis for item in mentioned_theses):
        violations.append("ALTERED_OPPORTUNITY_THESIS")
    mentioned_technical = {state for state in TECHNICAL_STATES if state in upper}
    canonical_technical = str(payload.get("canonical_technical_state") or "UNAVAILABLE").upper()
    if any(state != canonical_technical for state in mentioned_technical):
        violations.append("UNSUPPORTED_TECHNICAL_STATE")
    if re.search(r"\b(guaranteed|will certainly|should buy|should sell|we recommend)\b", copy, re.I):
        violations.append("UNSUPPORTED_RECOMMENDATION_OR_CERTAINTY")
    financial_lanes = {**dict(payload.get("fundamentals") or {}), **dict(payload.get("latest_earnings") or {}), **dict(payload.get("forward_outlook") or {})}
    financial_available = any(value is not None and value != "" for value in financial_lanes.values())
    if financial_available and not re.search(r"\b(revenue|sales|earnings|eps|margin|profit|cash flow|debt|forward estimate)\b", copy, re.I):
        violations.append("AVAILABLE_FINANCIAL_EVIDENCE_IGNORED")
    if re.search(r"\b(revenue|sales|earnings|eps|margin|profit|cash flow|debt)\b", copy, re.I) and not any(value is not None and value != "" for value in financial_lanes.values()):
        violations.append("UNSUPPORTED_FINANCIAL_CLAIM")
    catalyst_claim = re.search(r"\b(catalyst|product launch|fda|contract|acquisition|merger)\b", copy, re.I)
    catalyst_absence = re.search(r"\b(no|without|lacks?|unavailable|not included|not identified)\b[^.]{0,60}\bcatalyst\b", copy, re.I)
    if catalyst_claim and not catalyst_absence and not payload.get("commercial_catalysts"):
        violations.append("UNSUPPORTED_CATALYST_CLAIM")
    street = dict(payload.get("wall_street") or {})
    street_visible = street.get("commercial_display_status") == "DISPLAY_ALLOWED" or street.get("display_scope") == "INTERNAL_TRIAL"
    if re.search(r"\b(Wall Street|analysts?|consensus|upgrade|downgrade)\b", copy, re.I) and not street_visible:
        violations.append("UNSUPPORTED_ANALYST_CLAIM")
    atlas = dict(payload.get("atlas_valuation") or {})
    atlas_claim = re.search(r"\bATLAS (?:target|valuation|upside)\b", copy, re.I)
    atlas_absence = re.search(r"\b(?:not published|unavailable|no published)\b[^.]{0,40}\b(?:target|valuation|upside)\b", copy, re.I)
    if atlas_claim and not atlas_absence and atlas.get("status") != "PUBLISHED":
        violations.append("UNSUPPORTED_ATLAS_VALUATION_CLAIM")
    atlas_target_claim = re.search(r"ATLAS\s+(?:target|fair value)[^$\d-]{0,20}\$?(-?\d+(?:\.\d+)?)", copy, re.I)
    if atlas_target_claim and (atlas.get("target") is None or abs(float(atlas_target_claim.group(1)) - float(atlas["target"])) > .011):
        violations.append("TARGET_SUBSTITUTION")
    comparison = str((payload.get("valuation_comparison") or {}).get("state") or "")
    comparison_claims = {
        "ATLAS more bullish": "ATLAS_MORE_BULLISH", "Wall Street more bullish": "WALL_STREET_MORE_BULLISH",
        "ATLAS and Wall Street are aligned": "ALIGNED",
    }
    if any(phrase.lower() in copy.lower() and comparison != state for phrase, state in comparison_claims.items()):
        violations.append("UNSUPPORTED_VALUATION_COMPARISON")
    target_gap = (payload.get("valuation_comparison") or {}).get("target_gap_pct")
    if target_gap is not None and abs(float(target_gap)) > 15 and not re.search(r"\bWall Street\b", copy, re.I):
        violations.append("MATERIAL_STREET_DIVERGENCE_IGNORED")
    if payload.get("commercial_catalysts") and not any(str(item.get("headline") or "").lower() in copy.lower() for item in payload["commercial_catalysts"]):
        violations.append("AVAILABLE_CATALYST_IGNORED")
    if atlas.get("expected_return") is not None and float(atlas["expected_return"]) > 20:
        driver_values = dict(atlas.get("driver_evidence") or {})
        if driver_values and not re.search(r"\b(forward EPS|earnings multiple|growth input|revenue|cash flow|margin)\b", copy, re.I):
            violations.append("LARGE_UPSIDE_DRIVER_UNEXPLAINED")
    uncertainty_flags=set(((atlas.get("professional_valuation_v2") or {}).get("valuation_diagnostics") or {}).get("flags") or ())
    if uncertainty_flags.intersection({"MODEL_DISPERSION_HIGH","TERMINAL_VALUE_DEPENDENCE_HIGH","FAIR_VALUE_RANGE_WIDE","SENSITIVITY_WIDE","MODEL_CONCENTRATION_SINGLE_METHOD"}) and not re.search(r"\b(sensitiv|uncertain|disagree|dispersion|single|one complete|terminal|long-term assumption|forecast period|confidence)\b",copy,re.I):
        violations.append("VALUATION_UNCERTAINTY_IGNORED")
    ticker = str(payload.get("ticker") or "").upper()
    company = str(payload.get("company") or "").upper()
    if ticker not in copy.upper() and company not in copy.upper():
        violations.append("COMPANY_IDENTITY_MISSING")
    return {"valid": not violations, "violations": tuple(dict.fromkeys(violations))}


def _default_llm(payloads: Sequence[Mapping[str, Any]]) -> Sequence[str] | None:
    api_key = _openai_key()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        system_prompt = "You are writing an investment thesis, not summarizing a dashboard. In 3-5 concise sentences begin with the company name or ticker and answer: what could cause this COMPANY to outperform; what specifically supports future revenue, EPS, or cash-flow growth; what recent catalyst matters; what Wall Street expects and how ATLAS valuation compares when visible in this data mode; what insider, institutional, or political context is relevant; the most important downside risk; and why ATLAS recommends customer_action. Treat opportunity_thesis as immutable and explain that thesis when it is present; never select or change it. For non-breakout theses, ordinary volume may reduce near-term confirmation but is not a fatal investment veto. Only a BREAKOUT thesis may claim breakout confirmation. Select only the most decision-relevant evidence and vary emphasis and structure when evidence differs. Prioritize company/business, earnings, revisions, valuation and catalysts before technical context. Technical evidence alone cannot support business claims; if company evidence is absent, transparently write a market-setup thesis. Every company-specific and numerical claim must exist in the payload. Wall Street and insider/ownership/political evidence are non-scoring context and never determine the action. Never mention rank, setup score, Recovery Score, contextual RVOL, reason codes, provider/canonical terminology, or internal state names. Use customer_action verbatim when naming the stance. Return JSON {\"summaries\":[...]} in input order."
        output: list[str] = []
        for start in range(0, len(payloads), 5):
            batch = list(payloads[start:start + 5])
            completion = client.chat.completions.create(
                model=os.getenv("ATLAS_LLM_MODEL", "gpt-4o-mini"), temperature=0.1, max_tokens=1800,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(batch, sort_keys=True, default=str)},
                ],
            )
            parsed = json.loads(completion.choices[0].message.content or "{}")
            values = parsed.get("summaries")
            if isinstance(values, list):
                output.extend(str(value) for value in values[:len(batch)])
            else:
                output.extend([""] * len(batch))
            if len(output) < start + len(batch):
                output.extend([""] * (start + len(batch) - len(output)))
        return output
    except Exception:
        return None


def generate_summaries(
    payloads: Sequence[Mapping[str, Any]],
    *, llm: Callable[[Sequence[Mapping[str, Any]]], Sequence[str] | None] | None = None,
) -> list[dict[str, Any]]:
    generated = (llm or _default_llm)(payloads)
    results = []
    configuration = llm_configuration_status()
    for index, payload in enumerate(payloads):
        candidate = str(generated[index]) if generated and index < len(generated) else ""
        validation = validate_summary(candidate, payload) if candidate else {"valid": False, "violations": ("LLM_UNAVAILABLE",)}
        accepted = bool(candidate and validation["valid"])
        results.append({
            "version": SUMMARY_VERSION, "text": candidate if accepted else deterministic_summary(payload),
            "source": "LLM_VALIDATED" if accepted else "DETERMINISTIC_FALLBACK",
            "accepted": accepted, "validation": validation,
            "llm_configuration": configuration,
            "evidence_map": summary_evidence_map(payload),
            "professional_detail": {
                "valuation": dict((payload.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}),
                "six_pillars": dict(payload.get("six_pillars") or {}),
                "wall_street": dict(payload.get("wall_street_analysis") or {}),
            },
            "pillar_explanations": dict(PILLAR_101),
        })
    return results


def audit_summary_differentiation(
    payloads: Sequence[Mapping[str, Any]], results: Sequence[Mapping[str, Any]], *, threshold: float = .86,
) -> dict[str, Any]:
    normalized = []
    for payload, result in zip(payloads, results):
        text = str(result.get("text") or "").lower()
        for identity in (payload.get("ticker"), payload.get("company")):
            if identity:
                text = text.replace(str(identity).lower(), "<company>")
        text = re.sub(r"\$?-?\d+(?:\.\d+)?%?", "<number>", text)
        normalized.append(" ".join(text.split()))
    flagged = []
    for left in range(len(normalized)):
        for right in range(left + 1, len(normalized)):
            similarity = SequenceMatcher(None, normalized[left], normalized[right]).ratio()
            if similarity >= threshold:
                flagged.append({
                    "left": payloads[left].get("ticker"), "right": payloads[right].get("ticker"),
                    "similarity": round(similarity, 3),
                })
    return {"threshold": threshold, "flagged_pairs": flagged, "passed": not flagged}


def summary_evidence_map(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Stable audit pointers for every numeric family used by 101 copy."""
    return {
        "identity": {"company": payload.get("company"), "ticker": payload.get("ticker")},
        "company": dict(payload.get("company_evidence") or {}),
        "financials": dict(payload.get("fundamentals") or {}),
        "atlas_valuation": dict(payload.get("atlas_valuation") or {}),
        "wall_street": dict(payload.get("wall_street_analysis") or {}),
        "action": {"customer_action": payload.get("customer_action"), "guidance": payload.get("guidance")},
        "risk": dict(payload.get("risk_evidence") or {}),
        "volume": dict((payload.get("six_pillars") or {}).get("volume_quality") or {}),
    }


__all__ = ["SUMMARY_VERSION", "ACTION_101", "PILLAR_101", "audit_summary_differentiation", "build_summary_payload", "deterministic_summary", "plain_english_summary", "summary_evidence_map", "generate_summaries", "llm_configuration_status", "thesis_style_violations", "validate_summary"]
