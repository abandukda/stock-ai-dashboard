"""
Atlas V103 — Confidence Calibration Engine
"""

from __future__ import annotations

from typing import Any, Mapping
import math


def _num(value: Any, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def calibrate_v103_confidence(scored: Mapping[str, Any]) -> dict[str, Any]:
    score = _num(scored.get("opportunity_score"), 0.0) or 0.0
    coverage = _num(scored.get("component_coverage_pct"), 0.0) or 0.0

    values = [
        _num(value)
        for value in (scored.get("components") or {}).values()
        if _num(value) is not None
    ]

    if values:
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        disagreement = variance ** 0.5
    else:
        disagreement = 30.0

    confidence = (
        score * 0.45
        + coverage * 0.40
        + max(0.0, 100.0 - disagreement * 2.0) * 0.15
    )

    if scored.get("validated_fair_value") is None:
        confidence -= 5.0
    if not scored.get("investment_thesis"):
        confidence -= 5.0
    if scored.get("expected_return_pct") is None:
        confidence -= 4.0

    confidence = max(25.0, min(96.0, confidence))

    if confidence >= 90:
        band = "Exceptional"
    elif confidence >= 82:
        band = "High"
    elif confidence >= 72:
        band = "Strong"
    elif confidence >= 62:
        band = "Moderate"
    elif confidence >= 52:
        band = "Limited"
    else:
        band = "Low"

    return {
        "confidence_pct": round(confidence, 1),
        "confidence_band": band,
        "component_disagreement": round(disagreement, 1),
    }


__all__ = ["calibrate_v103_confidence"]
