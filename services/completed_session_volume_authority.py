"""Provider-neutral completed-session consolidated-volume authority gate."""
from __future__ import annotations

from typing import Any, Mapping


VERSION = "ATLAS_COMPLETED_SESSION_VOLUME_AUTHORITY_V1"


def certify_completed_session_volume(evidence: Mapping[str, Any]) -> dict[str, Any]:
    blockers = []
    if evidence.get("completed_daily_evidence") is not True:
        blockers.append("COMPLETED_SESSION_REQUIRED")
    if evidence.get("valid_daily_volume_baseline") is not True:
        blockers.append("VALID_DAILY_BASELINE_REQUIRED")
    if str(evidence.get("volume_session_scope") or "").upper() != "COMPLETED_SESSION":
        blockers.append("SESSION_SCOPE_NOT_COMPLETED")
    if str(evidence.get("volume_semantics") or "").upper() not in {
        "CONSOLIDATED_VOLUME", "CONSOLIDATED_AFTER_4PM",
    }:
        blockers.append("VOLUME_NOT_CONSOLIDATED")
    if str(evidence.get("provider_authority") or "").upper() != "CANONICAL_CERTIFIED":
        blockers.append("PROVIDER_AUTHORITY_NOT_CERTIFIED")
    if not evidence.get("volume_evidence_id"):
        blockers.append("VOLUME_EVIDENCE_ID_MISSING")
    if not evidence.get("as_of"):
        blockers.append("COMPLETED_SESSION_TIMESTAMP_MISSING")
    return {
        "version": VERSION,
        "status": "CERTIFIED" if not blockers else "REJECTED",
        "authorized": not blockers,
        "blockers": tuple(blockers),
    }


__all__ = ["VERSION", "certify_completed_session_volume"]
