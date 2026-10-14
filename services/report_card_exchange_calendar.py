"""Deterministic, provider-free XNYS calendar evidence for Report Card operations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

import exchange_calendars as xcals

from services.report_card_observation_activation import FINALIZED_SESSION_STATUS


CALENDAR_SCHEMA = "ATLAS_XNYS_GOVERNED_CALENDAR_V1"
CALENDAR_NAME = "XNYS"
CALENDAR_TIMEZONE = "America/New_York"
FINALIZATION_GRACE = timedelta(minutes=30)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def build_xnys_calendar(*, start_date: str, as_of: datetime) -> dict[str, Any]:
    """Return sessions through the latest close that is safely finalized."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("XNYS_CUTOFF_MUST_BE_TIMEZONE_AWARE")
    observed = as_of.astimezone(timezone.utc)
    calendar = xcals.get_calendar(CALENDAR_NAME)
    schedule = calendar.schedule.loc[start_date:observed.date().isoformat()]
    if schedule.empty:
        raise ValueError("XNYS_CALENDAR_HAS_NO_SESSIONS")
    finalized = schedule[schedule["close"] + FINALIZATION_GRACE <= observed]
    if finalized.empty:
        raise ValueError("XNYS_FINALIZED_SESSION_REQUIRED")
    last_label = finalized.index[-1].date().isoformat()
    last = finalized.iloc[-1]
    sessions = [item.date().isoformat() for item in finalized.index]
    value: dict[str, Any] = {
        "schema_version": CALENDAR_SCHEMA,
        "source": "exchange_calendars",
        "calendar": CALENDAR_NAME,
        "version": str(xcals.__version__),
        "timezone": CALENDAR_TIMEZONE,
        "generated_at": observed.isoformat(),
        "trading_sessions": sessions,
        "finalized_session": last_label,
        "session_status": FINALIZED_SESSION_STATUS,
        "session_open_at": last["open"].to_pydatetime().astimezone(timezone.utc).isoformat(),
        "session_close_at": last["close"].to_pydatetime().astimezone(timezone.utc).isoformat(),
        "early_close": bool((last["close"] - last["open"]) < timedelta(hours=6, minutes=30)),
        "finalization_grace_seconds": int(FINALIZATION_GRACE.total_seconds()),
    }
    value["artifact_sha256"] = hashlib.sha256(_canonical(value).encode()).hexdigest()
    return value


def verify_xnys_calendar(value: dict[str, Any], *, as_of: datetime) -> None:
    expected_hash = value.get("artifact_sha256")
    unhashed = {key: item for key, item in value.items() if key != "artifact_sha256"}
    if hashlib.sha256(_canonical(unhashed).encode()).hexdigest() != expected_hash:
        raise ValueError("XNYS_CALENDAR_DIGEST_MISMATCH")
    if value.get("schema_version") != CALENDAR_SCHEMA or value.get("calendar") != CALENDAR_NAME:
        raise ValueError("XNYS_CALENDAR_IDENTITY_INVALID")
    if value.get("version") != str(xcals.__version__) or value.get("timezone") != CALENDAR_TIMEZONE:
        raise ValueError("XNYS_CALENDAR_PROVENANCE_INVALID")
    regenerated = build_xnys_calendar(
        start_date=str(value["trading_sessions"][0]), as_of=as_of,
    )
    for key in ("trading_sessions", "finalized_session", "session_open_at", "session_close_at", "early_close"):
        if regenerated[key] != value.get(key):
            raise ValueError(f"XNYS_CALENDAR_REPLAY_MISMATCH:{key}")


__all__ = ["CALENDAR_SCHEMA", "build_xnys_calendar", "verify_xnys_calendar"]
