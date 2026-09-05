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
    }


def deterministic_summary(payload: Mapping[str, Any]) -> str:
    ticker = str(payload.get("ticker") or "This candidate")
    rank, score = payload.get("production_rank"), payload.get("setup_score")
    first = f"{ticker} ranks #{rank} with an ATLAS Setup Score of {float(score):g} / 100." if rank and score is not None else f"{ticker} has approved setup evidence."
    evidence = []
    price = payload.get("price")
    if price is not None:
        evidence.append(f"{str(payload.get('price_label') or 'Price')} is ${float(price):,.2f}")
    state = str(payload.get("canonical_technical_state") or "UNAVAILABLE")
    if state != "UNAVAILABLE":
        evidence.append(f"canonical Technical State is {state.replace('_', ' ')}")
    if payload.get("recovery_score") is not None:
        evidence.append(f"Recovery is {float(payload['recovery_score']):g}")
    second = ("; ".join(evidence[:3]) + ".") if evidence else "Canonical directional evidence remains limited."
    constraints = []
    if payload.get("contextual_rvol") is not None:
        constraints.append(f"contextual RVOL is {float(payload['contextual_rvol']):g}×")
    if str(payload.get("bar_quality") or "").upper() == "DEGRADED":
        constraints.append("bar quality is degraded")
    reasons = list(payload.get("reason_codes") or ())
    if reasons:
        constraints.append(str(reasons[0]).replace("_", " ").lower())
    guidance = str(payload.get("guidance") or "DATA_LIMITED").replace("_", " ")
    lead = "; ".join(constraints[:2]) or "The remaining governed gates have not all cleared"
    return f"{first} {second} {lead[:1].upper() + lead[1:]}, so ATLAS Guidance is {guidance}."


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
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return None
    try:
        from openai import OpenAI
        completion = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
            model=os.getenv("ATLAS_LLM_MODEL", "gpt-4o-mini"), temperature=0.1, max_tokens=1200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Phrase each supplied ATLAS record as 2-4 concise analyst sentences. Use only supplied facts, preserve Guidance exactly, make no recommendation or prediction, and return JSON {\"summaries\":[...]} in input order."},
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
