"""Optional FMP earnings-call context with no quantitative decision authority."""
from __future__ import annotations

import os
from typing import Any, Mapping


EARNINGS_EVIDENCE_NAMESPACE = "earnings_evidence"


def fmp_earnings_enabled() -> bool:
    return os.getenv("ATLAS_FMP_EARNINGS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def unavailable_earnings_evidence(reason: str = "OPTIONAL_CONTEXT_DISABLED") -> dict[str, Any]:
    return {
        "provider": "FMP",
        "evidence_family": "EARNINGS_TRANSCRIPT_CONTEXT",
        "availability_state": "DATA_UNAVAILABLE",
        "reason": reason,
        "decision_authority": False,
        "quantitative_authority": False,
    }


def validate_earnings_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only qualitative transcript fields inside the strict namespace."""
    allowed = {
        "provider", "evidence_family", "evidence_id", "retrieved_at", "earnings_event_id",
        "transcript_source", "summary", "management_commentary", "guidance_discussion",
        "key_positives", "key_risks", "catalysts", "availability_state", "reason",
    }
    result = {key: value for key, value in payload.items() if key in allowed}
    result.update({"decision_authority": False, "quantitative_authority": False})
    return {EARNINGS_EVIDENCE_NAMESPACE: result}


__all__ = [
    "EARNINGS_EVIDENCE_NAMESPACE", "fmp_earnings_enabled",
    "unavailable_earnings_evidence", "validate_earnings_evidence",
]
