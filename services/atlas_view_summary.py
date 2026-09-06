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
    valuation_drivers = dict(card.get("valuation_driver_evidence") or {})
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
        "ticker": card.get("ticker"), "company": card.get("company"),
        "production_rank": card.get("production_rank"), "setup_score": card.get("scan_conviction"),
        "setup_score_scale": 100, "indicator_periods": [20, 50, 200],
        "price": card.get("display_price"), "price_label": card.get("display_price_label"),
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
        "atlas_fair_value": card.get("atlas_fair_value"), "atlas_fv_status": card.get("atlas_valuation_status"),
        "expected_return": card.get("atlas_expected_return"),
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
            "status": card.get("atlas_valuation_status"), "target": card.get("atlas_fair_value"),
            "expected_return": card.get("atlas_expected_return"),
            "driver_evidence": valuation_drivers,
            "rejection_reasons": list(valuation.get("reason_codes") or valuation.get("reasons") or ()),
        },
        "wall_street": wall_street,
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
    }


def deterministic_summary(payload: Mapping[str, Any]) -> str:
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
    industry = str(company_evidence.get("industry") or "").strip().lower()
    domain = f" in {industry}" if industry else ""
    company_context = f"{business_summary}; " if business_summary else ""
    opening = {
        "VALUE_RERATING": f"{company_context}{company} could rerate over the next 6–12 months if {support} translates into greater earnings power than the market currently reflects{domain}.",
        "QUALITY_GROWTH": f"{company_context}{company}'s upside depends on sustaining {support}, which could compound future earnings power{domain}.",
        "ATTRACTIVE_ENTRY": f"{company_context}{company} offers potential upside from {support} while the current price remains favorable relative to published value{domain}.",
        "RECOVERY": f"{company_context}{company}'s recovery case depends on {support} developing into a durable improvement in operating performance{domain}.",
        "BREAKOUT": f"{company_context}{company}'s near-term upside case is a confirmed market breakout supported by {support}{domain}.",
    }.get(thesis, (
        f"{company_context}{company}'s available business and financial evidence supports a developing market opportunity tied to {support}{domain}."
        if business_summary or financial else
        f"Company-specific financial evidence is not available for {company}, so this view is limited to its developing market setup."
    ))

    if atlas.get("status") == "PUBLISHED" and atlas.get("target") is not None:
        inputs = []
        if drivers.get("forward_eps") is not None: inputs.append(f"forward EPS of ${float(drivers['forward_eps']):.2f}")
        if drivers.get("justified_pe") is not None: inputs.append(f"a {float(drivers['justified_pe']):.1f}× justified earnings multiple")
        if pct(drivers.get("growth_input_pct")): inputs.append(f"a {pct(drivers['growth_input_pct'])} growth input")
        rationale = " and ".join(inputs[:2]) or support
        valuation_sentence = f"From a current price of ${float(payload.get('price')):.2f}, ATLAS's ${float(atlas['target']):.2f} fair value implies {float(atlas.get('expected_return') or 0):.1f}% upside, supported by {rationale}."
    else:
        valuation_sentence = "ATLAS has not published a fair value because the available valuation evidence is insufficient."

    street_target, gap = comparison.get("street_target"), comparison.get("target_gap_pct")
    state = str(comparison.get("state") or "")
    if street_target is not None:
        relation = {"ATLAS_MORE_BULLISH":"more bullish than", "WALL_STREET_MORE_BULLISH":"less bullish than", "ALIGNED":"broadly aligned with"}.get(state, "compared with")
        if abs(float(gap or 0)) > 15 and atlas.get("status") == "PUBLISHED":
            explanation = (
                "the difference is grounded in " + " and ".join(inputs[:2])
                if inputs else "the currently available evidence does not fully explain the valuation gap"
            )
            street_sentence = f"ATLAS is {relation} Wall Street's ${float(street_target):.2f} average target; {explanation}."
        else:
            street_sentence = f"ATLAS is {relation} Wall Street's ${float(street_target):.2f} average target."
    else:
        street_sentence = "A commercially displayable Wall Street comparison is not available."

    catalyst = next(iter(payload.get("commercial_catalysts") or ()), {})
    catalyst_impact = str(catalyst.get('evidence_summary') or 'may affect forward estimates and execution').strip().rstrip('.')
    catalyst_impact = catalyst_impact[:1].lower() + catalyst_impact[1:] if catalyst_impact else "may affect forward estimates and execution"
    catalyst_sentence = f"The latest material catalyst is “{str(catalyst.get('headline')).strip().rstrip('.!?')},” which {catalyst_impact}." if catalyst.get("headline") else "No licensed company-specific catalyst is available, so the thesis rests on financial, valuation, and market evidence."
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
    action_sentence = f"The key risk is {risk_copy}; ATLAS's {action} stance reflects that {blocker}."
    return " ".join((opening, valuation_sentence, street_sentence, catalyst_sentence, action_sentence))


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
    violations: list[str] = []
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


__all__ = ["SUMMARY_VERSION", "audit_summary_differentiation", "build_summary_payload", "deterministic_summary", "generate_summaries", "llm_configuration_status", "validate_summary"]
