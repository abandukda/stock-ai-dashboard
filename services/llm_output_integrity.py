"""Mechanical guard for LLM explanations of canonical Guidance V1 records."""

from __future__ import annotations

import re
from typing import Any, Mapping


GUIDANCE_STATES = {
    "BUY_NOW", "ACCUMULATE", "WAIT_FOR_ENTRY", "WAIT_FOR_CONFIRMATION",
    "AVOID", "DATA_LIMITED",
}
LEGACY_OR_UNAPPROVED_STATES = {"MONITOR", "HOLD", "MAINTAIN"}
OPPORTUNITY_THESES = {
    "QUALITY_GROWTH", "VALUE_RERATING", "RECOVERY", "ATTRACTIVE_ENTRY",
    "BREAKOUT", "DEVELOPING_SETUP",
}


def _normalized_tokens(text: str) -> set[str]:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(text or "").upper()).strip("_")
    return {
        state for state in GUIDANCE_STATES | LEGACY_OR_UNAPPROVED_STATES
        if re.search(rf"(?:^|_){re.escape(state)}(?:_|$)", normalized)
    }


def validate_llm_explanation(text: str, evaluation: Mapping[str, Any]) -> dict[str, Any]:
    guidance = str((evaluation.get("guidance") or {}).get("state") or "DATA_LIMITED").upper()
    actionability = str((evaluation.get("actionability") or {}).get("status") or "UNAVAILABLE").upper()
    mentioned = _normalized_tokens(text)
    violations = []
    conflicting = sorted(state for state in mentioned if state != guidance)
    if conflicting:
        violations.append("CONFLICTING_GUIDANCE:" + ",".join(conflicting))
    if mentioned & LEGACY_OR_UNAPPROVED_STATES:
        violations.append("UNAPPROVED_GUIDANCE_STATE")

    normalized = re.sub(r"[^A-Z0-9]+", "_", str(text or "").upper()).strip("_")
    mentioned_theses = {
        thesis for thesis in OPPORTUNITY_THESES
        if re.search(rf"(?:^|_){re.escape(thesis)}(?:_|$)", normalized)
    }
    canonical_thesis = str(evaluation.get("opportunity_thesis") or
                           (evaluation.get("guidance") or {}).get("opportunity_thesis") or "").upper()
    if any(thesis != canonical_thesis for thesis in mentioned_theses):
        violations.append("ALTERED_OPPORTUNITY_THESIS")

    action_match = re.search(r"actionability[^a-z0-9]{0,20}([a-z_ ]+)", str(text or ""), re.I)
    if action_match:
        claimed = action_match.group(1).strip().upper().replace(" ", "_").rstrip("._")
        if claimed and not claimed.startswith(actionability):
            violations.append("ALTERED_ACTIONABILITY")

    canonical = {
        "opportunity": evaluation.get("opportunity"),
        "decision confidence": evaluation.get("decision_confidence"),
        "atlas fair value": (evaluation.get("atlas_valuation") or {}).get("fair_value"),
        "expected return": (evaluation.get("atlas_valuation") or {}).get("expected_return"),
        "entry": (evaluation.get("trade_plan") or {}).get("entry_low"),
        "stop": (evaluation.get("trade_plan") or {}).get("stop"),
        "target": (evaluation.get("trade_plan") or {}).get("target_1") or (evaluation.get("trade_plan") or {}).get("target"),
    }
    lower = str(text or "").lower()
    for label, value in canonical.items():
        match = re.search(rf"{re.escape(label)}[^0-9+\-]{{0,20}}([+\-]?\d+(?:\.\d+)?)", lower)
        if match and value is None:
            violations.append("INVENTED_CANONICAL_VALUE:" + label.upper().replace(" ", "_"))
        elif match and value is not None and abs(float(match.group(1)) - float(value)) > 0.11:
            violations.append("ALTERED_CANONICAL_VALUE:" + label.upper().replace(" ", "_"))

    state_fields = {
        "technical state": str((evaluation.get("technical_confirmation") or {}).get("state") or "UNAVAILABLE"),
        "volume state": str((evaluation.get("volume_intelligence") or {}).get("state") or "UNAVAILABLE"),
    }
    for label, value in state_fields.items():
        match = re.search(rf"{re.escape(label)}[^a-z0-9]{{0,20}}([a-z][a-z0-9_ -]*)", lower)
        if match:
            claimed = match.group(1).strip().upper().replace(" ", "_").replace("-", "_").rstrip("._")
            canonical_state = value.upper().replace(" ", "_")
            if claimed and not claimed.startswith(canonical_state):
                violations.append("ALTERED_CANONICAL_STATE:" + label.upper().replace(" ", "_"))
    return {"valid": not violations, "violations": tuple(violations)}


def deterministic_guidance_explanation(evaluation: Mapping[str, Any]) -> str:
    guidance = evaluation.get("guidance") or {}
    state = str(guidance.get("state") or "DATA_LIMITED").replace("_", " ")
    actionability = str((evaluation.get("actionability") or {}).get("status") or "UNAVAILABLE").replace("_", " ")
    reasons = ", ".join(str(item).replace("_", " ").lower() for item in guidance.get("reason_codes") or ())
    thesis = str(evaluation.get("opportunity_thesis") or guidance.get("opportunity_thesis") or "").replace("_", " ")
    thesis_copy = f" Opportunity thesis: {thesis}." if thesis else ""
    return f"ATLAS Guidance: {state}. Actionability: {actionability}." + thesis_copy + (f" Current reasons: {reasons}." if reasons else "")


def enforce_llm_integrity(text: str, evaluation: Mapping[str, Any]) -> dict[str, Any]:
    result = validate_llm_explanation(text, evaluation)
    if result["valid"]:
        return {"text": str(text), "accepted": True, **result}
    return {
        "text": deterministic_guidance_explanation(evaluation),
        "accepted": False,
        **result,
    }


__all__ = [
    "deterministic_guidance_explanation", "enforce_llm_integrity",
    "validate_llm_explanation",
]
