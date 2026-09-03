"""Deterministic Guidance V1 volume-state normalization.

This module does not fetch data and does not score investments.  It exposes
only the volume states approved by Founder Guidance V1.
"""

from __future__ import annotations

from typing import Any, Mapping
import math


VOLUME_INTELLIGENCE_VERSION = "ATLAS_VOLUME_INTELLIGENCE_V1"
STRONG_CONFIRMATION = "STRONG_CONFIRMATION"
NORMAL = "NORMAL"
UNAVAILABLE = "UNAVAILABLE"
BREAKOUT_RELATIVE_VOLUME_THRESHOLD = 1.40
AVERAGE_VOLUME_LOOKBACK = 20
MINIMUM_AVERAGE_DOLLAR_VOLUME = 2_000_000.0


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def build_volume_intelligence(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(evidence or {})
    relative_volume = _number(source.get("confirmation_relative_volume"))
    if relative_volume is None:
        relative_volume = _number(source.get("relative_volume"))
    average_dollar_volume = _number(source.get("average_dollar_volume"))
    valid = (
        relative_volume is not None
        and relative_volume >= 0
        and source.get("feed_health", "HEALTHY") == "HEALTHY"
        and source.get("completed_bar", True) is True
    )
    liquid = average_dollar_volume is None or average_dollar_volume >= MINIMUM_AVERAGE_DOLLAR_VOLUME
    confirmed = bool(
        valid and liquid and source.get("breakout_candidate") is True
        and relative_volume >= BREAKOUT_RELATIVE_VOLUME_THRESHOLD
    )
    state = STRONG_CONFIRMATION if confirmed else NORMAL if valid else UNAVAILABLE
    return {
        "version": VOLUME_INTELLIGENCE_VERSION,
        "threshold_version": "BULL_RUN_RADAR_V1_PROVISIONAL",
        "status": "AVAILABLE" if valid else "DATA_UNAVAILABLE",
        "state": state,
        "volume_confirmed": confirmed,
        "relative_volume": relative_volume,
        "current_volume": _number(source.get("current_volume")),
        "average_volume": _number(source.get("average_volume")),
        "average_volume_lookback": AVERAGE_VOLUME_LOOKBACK,
        "average_dollar_volume": average_dollar_volume,
        "minimum_average_dollar_volume": MINIMUM_AVERAGE_DOLLAR_VOLUME,
        "breakout_relative_volume_threshold": BREAKOUT_RELATIVE_VOLUME_THRESHOLD,
        "as_of": source.get("as_of"),
        "reason_codes": (
            ("COMPLETED_BREAKOUT_VOLUME_CONFIRMED",) if confirmed
            else ("VOLUME_AVAILABLE_NOT_CANONICALLY_STRONG",) if valid
            else ("VOLUME_EVIDENCE_UNAVAILABLE",)
        ),
        "contextual_distribution_evidence": source.get("distribution_evidence"),
        "limitations": (
            "WEAK_CONFIRMATION and DISTRIBUTION_RISK are not publishable in Guidance V1.",
        ),
    }


__all__ = [
    "AVERAGE_VOLUME_LOOKBACK", "BREAKOUT_RELATIVE_VOLUME_THRESHOLD",
    "MINIMUM_AVERAGE_DOLLAR_VOLUME", "NORMAL", "STRONG_CONFIRMATION",
    "UNAVAILABLE", "VOLUME_INTELLIGENCE_VERSION", "build_volume_intelligence",
]
