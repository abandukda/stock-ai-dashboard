"""
Atlas V104 — Investment Committee Decision Layer

Transforms V103 scored candidates into:
- Research Candidate
- Committee Ready
- BUY NOW
- ACCUMULATE
- MONITOR
- AVOID

The discovery list and final investment verdict are intentionally separated.
"""

from __future__ import annotations

from typing import Any, Mapping


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_committee_verdict(row: Mapping[str, Any]) -> dict[str, Any]:
    score = _num(row.get("opportunity_score"))
    confidence = _num(row.get("confidence_pct"))
    coverage = _num(row.get("component_coverage_pct"))
    upside = row.get("expected_return_pct")
    upside_value = _num(upside, -999.0) if upside is not None else None

    components = row.get("components") or {}
    fundamentals = _num(components.get("fundamentals"), 50.0)
    technical = _num(components.get("technical"), 50.0)
    valuation = _num(components.get("valuation"), 50.0)
    institutional = components.get("institutional")
    political = components.get("political")

    blockers = []
    if coverage < 55:
        blockers.append("Evidence coverage is below 55%.")
    if fundamentals < 55:
        blockers.append("Fundamental quality is not yet strong enough.")
    if technical < 52:
        blockers.append("Technical confirmation is weak.")
    if upside_value is None:
        blockers.append("Validated fair-value upside is unavailable.")
    elif upside_value > 60:
        blockers.append("Implied upside is unusually high and requires validation.")
    elif upside_value < 8:
        blockers.append("Validated upside is below 8%.")

    buy_now = (
        score >= 72
        and confidence >= 69
        and coverage >= 70
        and fundamentals >= 60
        and technical >= 58
        and upside_value is not None
        and 10 <= upside_value <= 55
        and not any("unusually high" in item for item in blockers)
    )

    committee_ready = (
        score >= 68
        and confidence >= 65
        and coverage >= 65
    )

    if buy_now:
        verdict = "BUY_NOW"
    elif score >= 70 and confidence >= 66:
        verdict = "ACCUMULATE"
    elif score < 48 or fundamentals < 40:
        verdict = "AVOID"
    else:
        verdict = "MONITOR"

    positives = []
    if fundamentals >= 70:
        positives.append("Strong fundamental quality")
    if technical >= 70:
        positives.append("Positive technical confirmation")
    if valuation >= 65:
        positives.append("Attractive valuation support")
    if institutional is not None and _num(institutional) >= 65:
        positives.append("Institutional accumulation support")
    if political is not None and _num(political) >= 65:
        positives.append("Positive disclosed political activity")
    if upside_value is not None and 12 <= upside_value <= 55:
        positives.append("Validated upside is attractive")
    if not positives:
        positives.append("Ranks highly relative to the reviewed universe")

    wait_reasons = list(blockers)
    if confidence < 75:
        wait_reasons.append("Confidence remains below high-conviction territory.")
    if not wait_reasons:
        wait_reasons.append("No major blockers identified.")

    sizing = (
        "6–8%"
        if verdict == "BUY_NOW" and confidence >= 78
        else "3–5%"
        if verdict == "BUY_NOW"
        else "2–4%"
        if verdict == "ACCUMULATE"
        else "0–2%"
    )

    return {
        "committee_verdict": verdict,
        "research_candidate": score >= 60,
        "committee_ready": committee_ready,
        "position_size_range": sizing,
        "positive_drivers": positives[:5],
        "reasons_to_wait": wait_reasons[:5],
        "primary_blocker": wait_reasons[0] if wait_reasons else None,
    }


__all__ = ["build_committee_verdict"]
