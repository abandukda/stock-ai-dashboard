"""Sanitized lifecycle telemetry for an external email-capable monitor."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Mapping
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


VERSION = "ATLAS_OPERATIONAL_HEARTBEAT_V1"
STATES = frozenset({"run", "complete", "fail"})
OPERATIONS = frozenset({"DAILY_BUY_NOW", "REPORT_CARD_G2", "REPORT_CARD_G3", "REPORT_CARD_G4"})
FAILURE_CODES = frozenset({
    "NONE", "PROVIDER_ERROR", "COVERAGE_COLLAPSE", "FRESHNESS_VIOLATION",
    "CERTIFICATION_FAILURE", "PUBLICATION_REJECTED", "NEVER_STARTED",
    "DID_NOT_COMPLETE", "LEDGER_INTEGRITY_FAILURE", "BACKUP_FAILURE", "UNKNOWN_FAILURE",
})


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def event_envelope(*, operation: str, state: str, run_id: str, source_sha: str,
                   trading_session: str, publication_status: str,
                   failure_code: str = "NONE", recovery_action: str = "NONE") -> dict[str, str]:
    if operation not in OPERATIONS or state not in STATES or failure_code not in FAILURE_CODES:
        raise ValueError("OPERATIONAL_HEARTBEAT_VALUE_NOT_ALLOWLISTED")
    if not run_id or len(source_sha) != 40:
        raise ValueError("OPERATIONAL_HEARTBEAT_IDENTITY_INVALID")
    envelope = {
        "schema_version": VERSION, "operation": operation, "state": state,
        "run_id": run_id, "source_sha": source_sha,
        "trading_session": trading_session, "publication_status": publication_status,
        "failure_code": failure_code, "recovery_action": recovery_action[:240],
    }
    envelope["event_id"] = _digest(envelope)
    return envelope


@dataclass(frozen=True)
class CronitorHeartbeatAdapter:
    """Telemetry-only Cronitor adapter; email routing remains in Cronitor."""

    base_url: str
    timeout_seconds: float = 15.0
    opener: Callable = urlopen

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.hostname not in {"cronitor.link", "eu.cronitor.link"}:
            raise ValueError("OPERATIONAL_HEARTBEAT_DESTINATION_NOT_APPROVED")
        if not parsed.path.strip("/"):
            raise ValueError("OPERATIONAL_HEARTBEAT_DESTINATION_INCOMPLETE")

    def send(self, envelope: Mapping[str, str]) -> dict[str, str | int]:
        parsed = urlparse(self.base_url)
        query = urlencode({
            "state": envelope["state"], "series": envelope["event_id"],
            "env": "production", "message": json.dumps(dict(envelope), separators=(",", ":")),
        })
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))
        response = self.opener(Request(url, method="GET"), timeout=self.timeout_seconds)
        status = int(getattr(response, "status", 0))
        if not 200 <= status < 300:
            raise RuntimeError("OPERATIONAL_HEARTBEAT_DELIVERY_FAILED")
        return {"status": status, "event_id": envelope["event_id"], "destination": "CRONITOR"}


__all__ = ["CronitorHeartbeatAdapter", "event_envelope"]
