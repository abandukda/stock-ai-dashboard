"""Grounded, validated AI phrasing for the customer ATLAS View."""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any, Callable, Mapping, Sequence


SUMMARY_VERSION = "ATLAS_VIEW_SUMMARY_V2"
GUIDANCE_STATES = {
    "BUY_NOW", "ACCUMULATE", "WAIT_FOR_ENTRY", "WAIT_FOR_CONFIRMATION", "AVOID", "DATA_LIMITED",
}
TECHNICAL_STATES = {
    "NO_SETUP", "SETUP_FORMING", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED", "EXTENDED", "FAILED_BREAKOUT",
}


def _valuation_comparison(card: Mapping[str, Any]) -> dict[str, Any]:
    atlas = card.get("atlas_fair_value") if str(card.get("atlas_valuation_status") or "").upper() == "PUBLISHED" else None
    street = dict(card.get("wall_street") or {})
    street_target = street.get("mean_target") if street.get("commercial_display_status") == "DISPLAY_ALLOWED" else None
    if atlas is None:
        state = "ATLAS_VALUATION_UNAVAILABLE"
    elif street_target is None:
        state = "WALL_STREET_UNAVAILABLE"
    elif abs(float(atlas) - float(street_target)) <= max(abs(float(atlas)), 1) * .05:
        state = "ALIGNED"
    elif float(atlas) > float(street_target):
        state = "ATLAS_MORE_BULLISH"
    else:
        state = "WALL_STREET_MORE_BULLISH"
    return {"state": state, "atlas_target": atlas, "street_target": street_target}


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
    evaluation = dict(card.get("evaluation") or {})
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
        "atlas_valuation": {
            "status": card.get("atlas_valuation_status"), "target": card.get("atlas_fair_value"),
            "expected_return": card.get("atlas_expected_return"),
            "driver_evidence": valuation_drivers,
            "rejection_reasons": list(valuation.get("reason_codes") or valuation.get("reasons") or ()),
        },
        "wall_street": wall_street,
        "valuation_comparison": _valuation_comparison(card),
        "risk_evidence": {
            "status": card.get("risk_status"), "canonical": risk.get("evidence"),
            "strongest_fundamental_risk": company.get("primary_risk"),
            "valuation_risk": valuation.get("risk") or valuation.get("risk_status"),
            "technical_risk": list(card.get("why_atlas") or ())[:2],
        },
        "guidance": card.get("guidance"), "actionability": card.get("actionability"),
        "customer_action": (card.get("customer_action") or {}).get("label"),
        "reason_codes": list(card.get("reason_codes") or ()),
        "allowed_change_conditions": list(card.get("what_changes_guidance") or ()),
        "commercial_catalysts": catalysts,
    }


def deterministic_summary(payload: Mapping[str, Any]) -> str:
    ticker = str(payload.get("ticker") or "This candidate")
    company = str(payload.get("company") or ticker)
    fundamentals = dict(payload.get("fundamentals") or {})
    company_evidence = dict(payload.get("company_evidence") or {})
    evidence: list[str] = []
    revenue_growth = fundamentals.get("revenue_growth")
    operating_margin = fundamentals.get("operating_margin")
    if company_evidence.get("eps_surprise_pct") is not None and float(company_evidence["eps_surprise_pct"]) >= 10:
        evidence.append("a latest-quarter earnings beat")
    if revenue_growth is not None and float(revenue_growth) > 0:
        evidence.append("positive revenue growth")
    if company_evidence.get("revenue_surprise_pct") is not None and float(company_evidence["revenue_surprise_pct"]) >= 5:
        evidence.append("revenue ahead of expectations")
    if company_evidence.get("earnings_growth") is not None and float(company_evidence["earnings_growth"]) > 0:
        evidence.append("improving earnings power")
    if fundamentals.get("free_cash_flow") is not None and float(fundamentals["free_cash_flow"]) > 0:
        evidence.append("positive free cash flow")
    if operating_margin is not None and float(operating_margin) > 0:
        evidence.append("an established operating profit base")
    if company_evidence.get("estimate_revision"):
        evidence.append("a supportive change in forward estimates")
    business_summary = str(company_evidence.get("business_summary") or "").strip()
    industry = str(company_evidence.get("industry") or "").strip()
    if business_summary:
        business_focus = " ".join(business_summary.split())
        sentence_end = re.search(r"[.!?](?=\s+[A-Z])", business_focus)
        if sentence_end and sentence_end.end() <= 300:
            business_focus = business_focus[:sentence_end.end()]
        elif len(business_focus) > 240:
            prefix = business_focus[:240]
            cuts = [prefix.rfind(token) for token in (", ", "; ", ". ")]
            cut = max((position for position in cuts if position >= 110), default=prefix.rfind(" "))
            business_focus = prefix[:cut]
        business_focus = re.sub(r"[!?]+", ",", business_focus)
        business_focus = business_focus.strip(" ,.")
        first = f"{company}'s upside case starts with its business: {business_focus}"
    elif industry:
        first = f"{company}'s upside case is tied to execution in {industry.lower()}."
    else:
        first = f"{company}'s available evidence supports a market-setup thesis rather than a fundamental growth claim."
    if not first.endswith((".", "!", "?")):
        first += "."
    catalyst = next(iter(payload.get("commercial_catalysts") or ()), {})
    support = " and ".join(evidence[:2]) if evidence else "the available operating evidence"
    atlas = dict(payload.get("atlas_valuation") or {})
    if atlas.get("target") is not None and atlas.get("expected_return") is not None:
        drivers = dict(atlas.get("driver_evidence") or {})
        method = str(drivers.get("method") or "").lower()
        model_context = "growth-adjusted forward earnings framework" if "growth-adjusted" in method else "published valuation framework"
        second = f"The ATLAS {model_context} derives its upside from {support}, although realizing that potential still requires durable execution."
    elif evidence:
        second = f"The clearest financial support is {support}, while ATLAS has not published a valuation target."
    else:
        second = "ATLAS has not published a valuation target because the available evidence is not sufficient to ground one."
    if catalyst.get("headline"):
        headline = re.sub(r"[.!?]+", "", str(catalyst["headline"]).strip())
        third = f"The recent company-specific development, “{headline},” is the most relevant catalyst to monitor."
    else:
        third = "No company-specific catalyst is included in the current evidence, so the case rests on existing financial and market evidence."
    constraints = []
    if payload.get("contextual_rvol") is not None and float(payload["contextual_rvol"]) < 1:
        constraints.append("market participation remains too weak for confirmation")
    if str(payload.get("bar_quality") or "").upper() == "DEGRADED":
        constraints.append("short-term bar continuity is limited")
    reasons = list(payload.get("reason_codes") or ())
    if "CURRENT_MARKET_EVIDENCE_UNAVAILABLE" in reasons:
        constraints.append("the latest market evidence is not fresh enough for an entry decision")
    elif reasons:
        constraints.append("the remaining confirmation evidence has not cleared")
    state = str(payload.get("canonical_technical_state") or "UNAVAILABLE")
    if not constraints and state in {"NO_SETUP", "SETUP_FORMING", "NEAR_BREAKOUT", "FAILED_BREAKOUT", "EXTENDED"}:
        constraints.append({
            "NO_SETUP": "the price structure has not formed a confirmed setup",
            "SETUP_FORMING": "the price structure is still developing",
            "NEAR_BREAKOUT": "the potential breakout is not yet confirmed",
            "FAILED_BREAKOUT": "the prior breakout attempt failed",
            "EXTENDED": "the price is extended beyond a preferred entry",
        }[state])
    guidance = str(payload.get("customer_action") or payload.get("guidance") or "WATCH — NOT READY YET").replace("_", " ")
    lead = " and ".join(constraints[:2]) or "the remaining confirmation gates have not cleared"
    risk = dict(payload.get("risk_evidence") or {}).get("strongest_fundamental_risk")
    if isinstance(risk, (list, tuple)):
        risk = next((str(item) for item in risk if item), None)
    if risk and re.search(r"no (?:major )?(?:financial )?(?:red flag|risk)", str(risk), re.I):
        risk = None
    if risk:
        risk_copy = str(risk).strip().rstrip(".")
        fourth = f"The key risk: {risk_copy}; ATLAS rates it {guidance} because {lead}."
    else:
        fourth = f"The principal limitation is {lead}; that is why ATLAS rates it {guidance}."
    return f"{first} {second} {third} {fourth}"


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
    allowed = _numbers(payload)
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
    if "RECOVERY SCORE" in copy.upper() or re.search(r"\b\d+(?:\.\d+)?×\s+(?:CONTEXTUAL\s+)?VOLUME\b", copy, re.I):
        violations.append("RAW_DASHBOARD_METRIC_RECITATION")
    if any(state != canonical_guidance for state in mentioned_guidance):
        violations.append("UNSUPPORTED_GUIDANCE")
    mentioned_technical = {state for state in TECHNICAL_STATES if state in upper}
    canonical_technical = str(payload.get("canonical_technical_state") or "UNAVAILABLE").upper()
    if any(state != canonical_technical for state in mentioned_technical):
        violations.append("UNSUPPORTED_TECHNICAL_STATE")
    if re.search(r"\b(guaranteed|will certainly|should buy|should sell|we recommend)\b", copy, re.I):
        violations.append("UNSUPPORTED_RECOMMENDATION_OR_CERTAINTY")
    financial_lanes = {**dict(payload.get("fundamentals") or {}), **dict(payload.get("latest_earnings") or {}), **dict(payload.get("forward_outlook") or {})}
    if re.search(r"\b(revenue|sales|earnings|eps|margin|profit|cash flow|debt)\b", copy, re.I) and not any(value is not None and value != "" for value in financial_lanes.values()):
        violations.append("UNSUPPORTED_FINANCIAL_CLAIM")
    catalyst_claim = re.search(r"\b(catalyst|product launch|fda|contract|acquisition|merger)\b", copy, re.I)
    catalyst_absence = re.search(r"\b(no|without|lacks?|unavailable|not included|not identified)\b[^.]{0,60}\bcatalyst\b", copy, re.I)
    if catalyst_claim and not catalyst_absence and not payload.get("commercial_catalysts"):
        violations.append("UNSUPPORTED_CATALYST_CLAIM")
    street = dict(payload.get("wall_street") or {})
    if re.search(r"\b(Wall Street|analysts?|consensus|upgrade|downgrade)\b", copy, re.I) and street.get("commercial_display_status") != "DISPLAY_ALLOWED":
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
        system_prompt = "You are writing an investment thesis, not summarizing a dashboard. In 3-5 concise sentences begin with the company name or ticker and answer: what could cause this COMPANY to outperform; what financial or business evidence supports that upside; what recent catalyst matters; how ATLAS valuation compares with Wall Street when both are legally available; the most important downside risk; and why ATLAS recommends customer_action. Select only the most decision-relevant evidence and vary emphasis and structure when evidence differs. Prioritize company/business, earnings, revisions, valuation and catalysts before technical context. Technical evidence alone cannot support business claims; if company evidence is absent, transparently write a market-setup thesis. Every company-specific and numerical claim must exist in the payload. Wall Street never determines the action. Never mention rank, setup score, Recovery Score, contextual RVOL, reason codes, provider/canonical terminology, or internal state names. Use customer_action verbatim when naming the stance. Return JSON {\"summaries\":[...]} in input order."
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
