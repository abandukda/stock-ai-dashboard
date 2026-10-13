"""Scheduling and safety contracts for unattended Report Card operations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Mapping


NEW_YORK = ZoneInfo("America/New_York")
AUTOMATION_TOKEN = "REPORT_CARD_AUTOMATION_OPERATE"
REQUIRED_CERTIFICATIONS = frozenset({
    "PROVIDER_FREE_PLAN_PASS",
    "LIVE_ACQUISITION_PASS",
    "DETERMINISTIC_PRODUCER_PASS",
    "APPEND_BACKUP_RESTORE_PASS",
    "SECOND_CYCLE_RELIABILITY_PASS",
})


@dataclass(frozen=True)
class AutomationDecision:
    allowed: bool
    reason: str
    local_time: str


def scheduled_wake_decision(*, now: datetime, enabled: bool, kill_switch: bool,
                            authorization: str, certifications: Mapping[str, bool]) -> AutomationDecision:
    """Fail closed unless this is the DST-safe 18:30 New York wake and all gates pass."""
    local = now.astimezone(NEW_YORK)
    stamp = local.isoformat()
    if kill_switch:
        return AutomationDecision(False, "AUTOMATION_KILL_SWITCH_ACTIVE", stamp)
    if not enabled:
        return AutomationDecision(False, "AUTOMATION_NOT_ENABLED", stamp)
    if authorization != AUTOMATION_TOKEN:
        return AutomationDecision(False, "AUTOMATION_AUTHORIZATION_INVALID", stamp)
    missing = sorted(name for name in REQUIRED_CERTIFICATIONS if certifications.get(name) is not True)
    if missing:
        return AutomationDecision(False, "AUTOMATION_CERTIFICATION_INCOMPLETE:" + ",".join(missing), stamp)
    if (local.hour, local.minute) != (18, 30):
        return AutomationDecision(False, "NOT_1830_AMERICA_NEW_YORK", stamp)
    return AutomationDecision(True, "AUTOMATION_WAKE_AUTHORIZED", stamp)


def bounded_call_budget(*, unique_due_tickers: int, due_horizons: int,
                        retry_attempts: int) -> int:
    if unique_due_tickers < 0 or due_horizons < 0 or retry_attempts < 0:
        raise ValueError("CALL_BUDGET_INPUT_INVALID")
    if retry_attempts > 1:
        raise ValueError("AUTOMATION_RETRY_LIMIT_EXCEEDED")
    return due_horizons * (3 * unique_due_tickers + 1) * (retry_attempts + 1)


__all__ = ["AUTOMATION_TOKEN", "AutomationDecision", "REQUIRED_CERTIFICATIONS",
           "bounded_call_budget", "scheduled_wake_decision"]
