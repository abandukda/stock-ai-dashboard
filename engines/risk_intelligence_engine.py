"""
Atlas V102.0 — Risk Intelligence Foundation

Read-only foundational risk engine.

This module intentionally keeps V102 simple and stable:
- converts opportunity strength into a basic inverse risk score;
- exposes named risk categories;
- never changes recommendations;
- provides a contract validator for future V102.x expansions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping
import math


@dataclass(frozen=True)
class RiskProfile:
    overall_risk_score: float
    financial_risk: float
    valuation_risk: float
    macro_risk: float
    political_risk: float


def _num(value: Any, default: float = 50.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def build_risk_profile(row: Mapping[str, Any]) -> RiskProfile:
    """
    Build a foundational risk profile from the available opportunity score.

    Higher opportunity scores imply lower foundational risk, but this engine
    remains conservative by clamping the result between 5 and 95.
    """
    opportunity = _clamp(
        _num(
            row.get("opportunity_score", row.get("Opportunity Score", 50.0)),
            50.0,
        )
    )

    overall = _clamp(100.0 - opportunity, 5.0, 95.0)

    return RiskProfile(
        overall_risk_score=round(overall, 1),
        financial_risk=round(_clamp(overall * 0.80), 1),
        valuation_risk=round(_clamp(overall * 0.90), 1),
        macro_risk=round(_clamp(overall * 0.70), 1),
        political_risk=round(_clamp(overall * 0.50), 1),
    )


def risk_profile_to_dict(profile: RiskProfile) -> dict[str, float]:
    return asdict(profile)


def validate_risk_profile(profile: RiskProfile) -> list[str]:
    errors = []

    for field_name, value in asdict(profile).items():
        if not 0.0 <= value <= 100.0:
            errors.append(f"{field_name} must be between 0 and 100")

    return errors


__all__ = [
    "RiskProfile",
    "build_risk_profile",
    "risk_profile_to_dict",
    "validate_risk_profile",
]
