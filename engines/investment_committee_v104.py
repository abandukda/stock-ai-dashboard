"""
Atlas V104 — Calibrated Investment Committee Decision Layer

Principles:
- Missing optional evidence does not create an AVOID verdict.
- AVOID requires confirmed weakness or a materially negative setup.
- BUY_NOW requires both quality and actionable timing.
- ACCUMULATE covers attractive medium/long-term opportunities with imperfect timing.
"""

from __future__ import annotations

from typing import Any, Mapping


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _status(row: Mapping[str, Any], name: str) -> str:
    details = row.get("component_details") or {}
    component = details.get(name) or {}
    return str(component.get("status") or "LEGACY").upper()


def _missing_detail(row: Mapping[str, Any], name: str, fallback: str) -> str:
    component = (row.get("component_details") or {}).get(name) or {}
    missing = component.get("missing_fields") or component.get("missing") or []
    if isinstance(missing, str):
        missing = [missing]
    labels = [str(item).replace("_", " ") for item in missing if item]
    return f"Missing {name} evidence: {', '.join(labels[:5])}." if labels else fallback


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
    analyst = _num(components.get("analyst"), 50.0)
    institutional = components.get("institutional")
    political = components.get("political")

    financial_status = _status(row, "fundamentals")
    technical_status = _status(row, "technical")

    confirmed_weak_fundamentals = (
        fundamentals < 40
        and financial_status in {"AVAILABLE", "LEGACY"}
    )
    confirmed_weak_technical = (
        technical < 35
        and technical_status in {"AVAILABLE", "LEGACY"}
    )
    confirmed_negative_upside = (
        upside_value is not None and upside_value < 0
    )

    blockers: list[str] = []
    cautions: list[str] = []

    if coverage < 55:
        cautions.append("Evidence coverage is still developing.")
    if financial_status == "AVAILABLE" and fundamentals < 55:
        cautions.append("Verified fundamental quality is below Atlas preference.")
    elif financial_status in {"PARTIAL", "NOT_LOADED", "NO_DATA"}:
        cautions.append(_missing_detail(
            row,
            "fundamentals",
            "Fundamental evidence is incomplete; the provider supplied no field-level detail.",
        ))
    if technical_status == "AVAILABLE" and technical < 52:
        cautions.append("Technical confirmation remains weak.")
    elif technical_status in {"PARTIAL", "NOT_LOADED", "NO_DATA"}:
        cautions.append(_missing_detail(
            row,
            "technical",
            "Technical evidence is incomplete; the provider supplied no field-level detail.",
        ))
    if upside_value is None:
        cautions.append("Validated fair-value upside is unavailable.")
    elif upside_value > 60:
        cautions.append("Implied upside is unusually high and needs validation.")
    elif upside_value < 8:
        cautions.append("Validated upside is currently limited.")

    if confirmed_weak_fundamentals:
        blockers.append("Confirmed fundamental quality is materially weak.")
    if confirmed_negative_upside:
        blockers.append("Validated fair value implies downside.")
    if confirmed_weak_technical and upside_value is not None and upside_value < 5:
        blockers.append("Technical weakness is paired with limited valuation support.")
    if score < 45:
        blockers.append("The overall opportunity score is materially weak.")

    buy_now = (
        score >= 70
        and confidence >= 66
        and coverage >= 65
        and fundamentals >= 58
        and technical >= 56
        and valuation >= 58
        and upside_value is not None
        and 10 <= upside_value <= 55
        and not blockers
    )

    accumulate = (
        score >= 62
        and confidence >= 56
        and coverage >= 58
        and fundamentals >= 48
        and valuation >= 55
        and upside_value is not None
        and upside_value >= 8
        and not blockers
    )

    committee_ready = (
        score >= 62
        and confidence >= 56
        and coverage >= 58
        and not blockers
    )

    if buy_now:
        verdict = "BUY_NOW"
    elif accumulate:
        verdict = "ACCUMULATE"
    elif blockers:
        verdict = "AVOID"
    else:
        verdict = "MONITOR"

    positives: list[str] = []
    if fundamentals >= 68:
        positives.append(f"Fundamental quality scores {fundamentals:.1f}/100.")
    if technical >= 68:
        positives.append(f"Technical confirmation scores {technical:.1f}/100.")
    if valuation >= 62:
        positives.append(f"Valuation support scores {valuation:.1f}/100.")
    if analyst >= 65:
        positives.append(f"Wall Street support scores {analyst:.1f}/100.")
    if institutional is not None and _num(institutional) >= 65:
        positives.append("Institutional evidence is supportive.")
    if political is not None and _num(political) >= 65:
        positives.append("Recent disclosed political activity is supportive.")
    if upside_value is not None and 12 <= upside_value <= 55:
        positives.append(f"Validated upside is {upside_value:.1f}%.")

    thesis = str(row.get("investment_thesis") or "").strip()
    if thesis and len(positives) < 5:
        positives.append(thesis)

    if not positives:
        positives.append("The stock remains under research while Atlas validates the thesis.")

    wait_reasons = blockers + cautions
    if verdict == "BUY_NOW" and confidence < 75:
        wait_reasons.append("Position size should remain measured until confidence improves.")
    elif verdict == "ACCUMULATE":
        wait_reasons.append(
            "Atlas sees value, but prefers staged buying rather than chasing the current price."
        )
    elif verdict == "MONITOR":
        wait_reasons.append(
            "Atlas needs stronger confirmation before issuing an actionable rating."
        )
    if not wait_reasons:
        wait_reasons.append("No major blockers identified.")

    upgrade_triggers: list[str] = []
    downgrade_triggers: list[str] = []

    if verdict != "BUY_NOW":
        if technical < 60:
            upgrade_triggers.append("Technical score improves above 60.")
        if confidence < 66:
            upgrade_triggers.append("Confidence improves above 66%.")
        if upside_value is None:
            upgrade_triggers.append("A validated fair-value target becomes available.")
        elif upside_value < 10:
            upgrade_triggers.append("Expected return improves above 10%.")
    if fundamentals < 58:
        upgrade_triggers.append("Fundamental quality improves above 58.")

    downgrade_triggers.extend(
        [
            "Guidance or earnings estimates deteriorate materially.",
            "Validated fair value falls below the current price.",
            "Technical structure breaks with sustained heavy selling volume.",
        ]
    )

    sizing = (
        "5–7%"
        if verdict == "BUY_NOW" and confidence >= 78
        else "3–5%"
        if verdict == "BUY_NOW"
        else "2–4%"
        if verdict == "ACCUMULATE"
        else "0–2%"
    )

    return {
        "committee_verdict": verdict,
        "research_candidate": score >= 58,
        "committee_ready": committee_ready,
        "position_size_range": sizing,
        "positive_drivers": positives[:6],
        "reasons_to_wait": wait_reasons[:6],
        "primary_blocker": wait_reasons[0] if wait_reasons else None,
        "upgrade_triggers": upgrade_triggers[:5],
        "downgrade_triggers": downgrade_triggers[:5],
    }


__all__ = ["build_committee_verdict"]
