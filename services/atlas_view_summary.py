"""Grounded, validated AI phrasing for the customer ATLAS View."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Mapping, Sequence


SUMMARY_VERSION = "ATLAS_VIEW_SUMMARY_V1"
GUIDANCE_STATES = {
    "BUY_NOW", "ACCUMULATE", "WAIT_FOR_ENTRY", "WAIT_FOR_CONFIRMATION", "AVOID", "DATA_LIMITED",
}
TECHNICAL_STATES = {
    "NO_SETUP", "SETUP_FORMING", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED", "EXTENDED", "FAILED_BREAKOUT",
}


def _openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key
    try:
        import streamlit as st
        return str(st.secrets.get("OPENAI_API_KEY", "")).strip()
    except Exception:
        return ""


def build_summary_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    persisted_technical = dict(card.get("technical_evidence") or {})
    canonical_technical = dict(card.get("canonical_technical_evidence") or {})
    technical = canonical_technical or persisted_technical
    volume = dict(card.get("volume_evidence") or {})
    recovery = dict(card.get("recovery") or {})
    trade = dict(card.get("trade_plan") or {})
    market = dict(card.get("market_evidence") or {})
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
        "guidance": card.get("guidance"), "actionability": card.get("actionability"),
        "reason_codes": list(card.get("reason_codes") or ()),
        "allowed_change_conditions": list(card.get("what_changes_guidance") or ()),
        "commercial_catalysts": [
            {
                "headline": item.get("title") or item.get("headline"),
                "category": item.get("category"), "published_at": item.get("published_at"),
            }
            for item in (card.get("recent_catalysts") or ())[:2]
            if isinstance(item, Mapping)
        ],
    }


def deterministic_summary(payload: Mapping[str, Any]) -> str:
    ticker = str(payload.get("ticker") or "This candidate")
    evidence = []
    state = str(payload.get("canonical_technical_state") or "UNAVAILABLE")
    if state != "UNAVAILABLE":
        evidence.append({
            "SETUP_FORMING": "a technical setup that is still forming",
            "NEAR_BREAKOUT": "a technical setup approaching breakout",
            "BREAKOUT_CONFIRMED": "a confirmed technical breakout",
            "EXTENDED": "an established but extended trend",
            "FAILED_BREAKOUT": "a setup reassessing a failed breakout",
            "NO_SETUP": "a still-unconfirmed technical structure",
        }.get(state, f"the {state.replace('_', ' ').lower()} technical structure"))
    if payload.get("recovery_score") is not None:
        evidence.append(f"a Recovery Score of {float(payload['recovery_score']):g}")
    if payload.get("expected_return") is not None and str(payload.get("atlas_fv_status") or "").upper() == "PUBLISHED":
        evidence.append(f"published ATLAS upside of {float(payload['expected_return']):g}%")
    catalyst = next(iter(payload.get("commercial_catalysts") or ()), {})
    if catalyst.get("headline"):
        evidence.append(f"the recent {str(catalyst.get('category') or 'company event').replace('_', ' ').lower()}")
    support = " and ".join(evidence[:2]) if evidence else "the approved evidence that currently supports the setup"
    first = f"{ticker}'s potential rests on {support}, giving the setup a credible path to improve if confirmation follows."
    constraints = []
    if payload.get("contextual_rvol") is not None:
        constraints.append(f"participation remains {float(payload['contextual_rvol']):g}× contextual volume")
    if str(payload.get("bar_quality") or "").upper() == "DEGRADED":
        constraints.append("short-term bar continuity is limited")
    reasons = list(payload.get("reason_codes") or ())
    if reasons:
        constraints.append(str(reasons[0]).replace("_", " ").lower())
    guidance = str(payload.get("guidance") or "DATA_LIMITED").replace("_", " ")
    lead = " and ".join(constraints[:2]) or "the remaining confirmation gates have not cleared"
    second = f"The main constraint is that {lead}."
    third = f"ATLAS therefore remains at {guidance} until the evidence supports a stronger action."
    return f"{first} {second} {third}"


def _numbers(value: Any) -> list[float]:
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _numbers(nested)]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in _numbers(nested)]
    if isinstance(value, bool) or value is None:
        return []
    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


def validate_summary(text: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    copy = " ".join(str(text or "").split())
    violations: list[str] = []
    if not 2 <= len([part for part in re.split(r"(?<=[.!?])\s+", copy) if part]) <= 4:
        violations.append("SENTENCE_COUNT")
    allowed = _numbers(payload)
    for token in re.findall(r"(?<![A-Za-z])\$?(-?\d+(?:\.\d+)?)", copy.replace(",", "")):
        number = float(token)
        if not any(abs(number - value) <= max(0.011, abs(value) * 0.0001) for value in allowed):
            violations.append("UNSOURCED_NUMBER")
            break
    upper = re.sub(r"[^A-Z0-9]+", "_", copy.upper())
    mentioned_guidance = {state for state in GUIDANCE_STATES if state in upper}
    canonical_guidance = str(payload.get("guidance") or "DATA_LIMITED").upper()
    if any(state != canonical_guidance for state in mentioned_guidance):
        violations.append("UNSUPPORTED_GUIDANCE")
    mentioned_technical = {state for state in TECHNICAL_STATES if state in upper}
    canonical_technical = str(payload.get("canonical_technical_state") or "UNAVAILABLE").upper()
    if any(state != canonical_technical for state in mentioned_technical):
        violations.append("UNSUPPORTED_TECHNICAL_STATE")
    if re.search(r"\b(guaranteed|will certainly|should buy|should sell|we recommend)\b", copy, re.I):
        violations.append("UNSUPPORTED_RECOMMENDATION_OR_CERTAINTY")
    if str(payload.get("ticker") or "").upper() not in copy.upper():
        violations.append("TICKER_MISSING")
    return {"valid": not violations, "violations": tuple(dict.fromkeys(violations))}


def _default_llm(payloads: Sequence[Mapping[str, Any]]) -> Sequence[str] | None:
    api_key = _openai_key()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        completion = OpenAI(api_key=api_key).chat.completions.create(
            model=os.getenv("ATLAS_LLM_MODEL", "gpt-4o-mini"), temperature=0.1, max_tokens=1200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Write a genuinely analytical 2-4 sentence ATLAS investment thesis for each supplied record. Explain the strongest credible source of potential, the most relevant catalyst or differentiating evidence, the decisive blocker or risk, and why the governed Guidance follows. Synthesize rather than list metrics. Use only supplied facts, preserve Guidance exactly, make no unsupported recommendation or prediction, and return JSON {\"summaries\":[...]} in input order."},
                {"role": "user", "content": json.dumps(list(payloads), sort_keys=True, default=str)},
            ],
        )
        parsed = json.loads(completion.choices[0].message.content or "{}")
        values = parsed.get("summaries")
        return values if isinstance(values, list) else None
    except Exception:
        return None


def generate_summaries(
    payloads: Sequence[Mapping[str, Any]],
    *, llm: Callable[[Sequence[Mapping[str, Any]]], Sequence[str] | None] | None = None,
) -> list[dict[str, Any]]:
    generated = (llm or _default_llm)(payloads)
    results = []
    for index, payload in enumerate(payloads):
        candidate = str(generated[index]) if generated and index < len(generated) else ""
        validation = validate_summary(candidate, payload) if candidate else {"valid": False, "violations": ("LLM_UNAVAILABLE",)}
        accepted = bool(candidate and validation["valid"])
        results.append({
            "version": SUMMARY_VERSION, "text": candidate if accepted else deterministic_summary(payload),
            "source": "VALIDATED_LLM" if accepted else "DETERMINISTIC_FALLBACK",
            "accepted": accepted, "validation": validation,
        })
    return results


__all__ = ["SUMMARY_VERSION", "build_summary_payload", "deterministic_summary", "generate_summaries", "validate_summary"]
