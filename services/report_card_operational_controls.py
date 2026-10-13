"""Provider-free operational controls for Report Card activation evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence


VERSION = "ATLAS_REPORT_CARD_OPERATIONAL_CONTROLS_V1"
PUBLICATION_STATES = frozenset({"PROVEN_PUBLISHED", "PROVEN_WITHHELD", "UNPROVEN"})


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def reconcile_publication(*, signals: Sequence[Mapping[str, Any]],
                          publication_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Classify without inference: only exact immutable identity matches prove a state."""
    keys = ("signal_id", "candidate_digest", "publication_digest", "evaluation_snapshot_id", "decision_digest")
    evidence = {tuple(str(row.get(k) or "") for k in keys): row for row in publication_rows}
    rows = []
    for signal in signals:
        identity = tuple(str(signal.get(k) or "") for k in keys)
        match = evidence.get(identity) if all(identity) else None
        state = "UNPROVEN"
        evidence_id = None
        if match and match.get("customer_visible_artifact") is True:
            state, evidence_id = "PROVEN_PUBLISHED", match.get("evidence_id")
        elif match and match.get("withheld_certification") is True:
            state, evidence_id = "PROVEN_WITHHELD", match.get("evidence_id")
        rows.append({"signal_id": str(signal.get("signal_id") or ""), "classification": state,
                     "evidence_id": evidence_id, "identity": dict(zip(keys, identity))})
    counts = {state: sum(row["classification"] == state for row in rows) for state in sorted(PUBLICATION_STATES)}
    result = {"version": VERSION, "rows": rows, "counts": counts,
              "customer_replicable_count": counts["PROVEN_PUBLISHED"], "provider_calls": 0}
    result["sha256"] = digest(result)
    return result


def compare_entry_prices(*, signals: Sequence[Mapping[str, Any]], closes: Mapping[str, Mapping[str, Any]],
                         sessions: Sequence[str]) -> dict[str, Any]:
    """Compare registered reference with first complete post-publication close; never select a method."""
    output = []
    for signal in signals:
        published = datetime.fromisoformat(str(signal["publication_timestamp"]).replace("Z", "+00:00")).date()
        eligible = next((session for session in sessions if datetime.fromisoformat(session).date() > published), None)
        candidate = (closes.get(str(signal["ticker"]).upper()) or {}).get(eligible) if eligible else None
        registered = signal.get("reference_price")
        delta = None if candidate in (None, "") or registered in (None, "") else float(candidate) - float(registered)
        output.append({"signal_id": signal["signal_id"], "ticker": str(signal["ticker"]).upper(),
                       "registered_reference_price": registered, "first_complete_close_session": eligible,
                       "first_complete_close_price": candidate, "absolute_difference": delta,
                       "method_changed": False, "owner_decision_required": True})
    result = {"version": VERSION, "status": "COMPARISON_ONLY", "rows": output, "provider_calls": 0}
    result["sha256"] = digest(result)
    return result


def detect_restatement(*, prior: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    changed = sorted(session for session in set(prior) & set(current)
                     if prior[session] != current[session])
    return {"status": "RESTATEMENT_DETECTED" if changed else "UNCHANGED", "changed_sessions": changed,
            "fail_closed": bool(changed)}


def classify_unavailable(*, price_status: str, delisting_evidence: Mapping[str, Any] | None) -> str:
    if price_status == "AVAILABLE":
        return "AVAILABLE"
    evidence = delisting_evidence or {}
    if evidence.get("certification_status") == "CERTIFIED" and evidence.get("delisted") is True and evidence.get("evidence_id"):
        return "DELISTED"
    return "TEMPORARILY_UNAVAILABLE"


def validate_entitlement(evidence: Mapping[str, Any]) -> dict[str, Any]:
    required = {"historical_ohlcv", "splits", "dividends"}
    capabilities = set(evidence.get("capabilities") or ())
    valid = (evidence.get("status") == "APPROVED" and bool(evidence.get("contract_id"))
             and bool(evidence.get("effective_at")) and required <= capabilities)
    if not valid:
        raise PermissionError("FINNHUB_CONTRACT_ENTITLEMENT_EVIDENCE_REQUIRED")
    return {"status": "ENTITLEMENT_EVIDENCE_VALID", "contract_id": evidence["contract_id"],
            "capabilities": sorted(required), "evidence_sha256": digest(evidence), "provider_calls": 0}


def heartbeat_decision(*, now: datetime, expected_start: datetime, started_at: datetime | None,
                       completed_at: datetime | None, completion_status: str | None,
                       grace: timedelta) -> dict[str, Any]:
    now = now.astimezone(timezone.utc)
    if started_at is None and now > expected_start.astimezone(timezone.utc) + grace:
        state = "NEVER_STARTED"
    elif started_at is not None and completed_at is None and now > started_at.astimezone(timezone.utc) + grace:
        state = "DID_NOT_COMPLETE"
    elif completed_at is not None and completion_status != "SUCCESS":
        state = "FAILED"
    else:
        state = "HEALTHY"
    return {"status": state, "alert_required": state != "HEALTHY", "independent_of_github_actions": True}


__all__ = ["VERSION", "classify_unavailable", "compare_entry_prices", "detect_restatement",
           "digest", "heartbeat_decision", "reconcile_publication", "validate_entitlement"]
