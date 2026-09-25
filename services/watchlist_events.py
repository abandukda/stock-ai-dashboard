"""Provider-neutral, deterministic watchlist state-change events."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

VERSION = "ATLAS_WATCHLIST_EVENT_V1"
EVENT_TYPES = (
    "ACTION_UPGRADE", "ACTION_DOWNGRADE", "STRONGEST_OPPORTUNITY_ENTERED",
    "STRONGEST_OPPORTUNITY_EXITED", "FAIR_VALUE_MATERIAL_CHANGE",
    "EARNINGS_AVAILABLE", "EVIDENCE_BECAME_LIMITED", "EVIDENCE_RESTORED",
)
ACTION_ORDER = {
    "RATING_NOT_PUBLISHED": 0, "AVOID": 1, "WATCH_NOT_READY": 2,
    "WAIT_FOR_CONFIRMATION": 3, "WAIT_FOR_BETTER_ENTRY": 4,
    "BUILD_A_POSITION": 5, "BUY_NOW": 6,
}


def derive_watchlist_events(
    *, user_id: str, watchlist_id: str, ticker: str,
    previous: Mapping[str, Any], current: Mapping[str, Any],
    material_fair_value_pct: float = 10.0,
) -> list[dict[str, Any]]:
    """Derive material events only; display-price movement is intentionally ignored."""
    prior_action = str(previous.get("canonical_action") or "RATING_NOT_PUBLISHED")
    action = str(current.get("canonical_action") or "RATING_NOT_PUBLISHED")
    kinds: list[str] = []
    if action != prior_action:
        kinds.append("ACTION_UPGRADE" if ACTION_ORDER.get(action, -1) > ACTION_ORDER.get(prior_action, -1) else "ACTION_DOWNGRADE")
    if current.get("strongest_opportunity") is True and previous.get("strongest_opportunity") is not True:
        kinds.append("STRONGEST_OPPORTUNITY_ENTERED")
    if previous.get("strongest_opportunity") is True and current.get("strongest_opportunity") is not True:
        kinds.append("STRONGEST_OPPORTUNITY_EXITED")
    old_fv, new_fv = previous.get("fair_value"), current.get("fair_value")
    try:
        if float(old_fv) and abs(float(new_fv) / float(old_fv) - 1) * 100 >= material_fair_value_pct:
            kinds.append("FAIR_VALUE_MATERIAL_CHANGE")
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    if current.get("earnings_evidence_id") and current.get("earnings_evidence_id") != previous.get("earnings_evidence_id"):
        kinds.append("EARNINGS_AVAILABLE")
    prior_limited = bool(previous.get("evidence_limited"))
    now_limited = bool(current.get("evidence_limited"))
    if now_limited and not prior_limited:
        kinds.append("EVIDENCE_BECAME_LIMITED")
    if prior_limited and not now_limited:
        kinds.append("EVIDENCE_RESTORED")
    events = []
    for kind in kinds:
        identity = {
            "user_id": user_id, "watchlist_id": watchlist_id, "ticker": ticker.upper(),
            "event_type": kind, "candidate_digest": current.get("candidate_digest"),
            "certification_timestamp": current.get("certification_timestamp"),
            "evidence_ids": sorted(str(x) for x in current.get("evidence_ids", ()) if x),
        }
        event_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        events.append({
            "version": VERSION, "event_id": event_id, **identity,
            "previous_canonical_action": prior_action, "current_canonical_action": action,
            "previous_fair_value": old_fv, "current_fair_value": new_fv,
            "delivery_status": "NOT_SENT", "non_scoring": True,
        })
    return events


def suppress_duplicate_events(events: Sequence[Mapping[str, Any]], seen_event_ids: Sequence[str]) -> list[dict[str, Any]]:
    seen = {str(value) for value in seen_event_ids}
    output = []
    for event in events:
        event_id = str(event.get("event_id") or "")
        if event_id and event_id not in seen:
            output.append(dict(event)); seen.add(event_id)
    return output


__all__ = ["ACTION_ORDER", "EVENT_TYPES", "VERSION", "derive_watchlist_events", "suppress_duplicate_events"]
