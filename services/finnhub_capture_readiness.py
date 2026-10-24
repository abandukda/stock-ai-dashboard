"""Offline-only readiness contract for a later bounded Finnhub history pilot.

There is deliberately no transport in this module.  It creates a disabled,
source-bound six-request manifest, validates synthetic/private raw-first
captures, and rehearses durable consume-once approval claims.  None of those
operations grants entitlement, acquisition, publication, or recommendation
authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Any, Mapping

from services.operations_gateway import RESEARCH_ENDPOINTS, canonical_bytes, sha256
from services.report_card_exchange_calendar import build_xnys_calendar, verify_xnys_calendar
from services.research_refresh_execution import request_parameters


SCHEMA = "ATLAS_FINNHUB_CAPTURE_READINESS_V1"
SYMBOLS = ("NVDA", "SPY")
CAPABILITIES = (
    ("historical_ohlcv", "/stock/candle"),
    ("splits", "/stock/split"),
    ("dividends", "/stock/dividend2"),
)
MAX_BODY_BYTES = 8 * 1024 * 1024
UNKNOWN_BLOCKERS = (
    "CREDENTIAL_LOCATION_UNKNOWN",
    "PRIVATE_RAW_STORAGE_LOCATION_UNKNOWN",
    "UNEXPIRED_ENTITLEMENT_EVIDENCE_REQUIRED",
    "UNEXPIRED_OWNER_APPROVAL_REQUIRED",
    "DURABLE_CLAIM_ROOT_UNKNOWN",
)


@dataclass(frozen=True)
class InMemoryFixtureSource:
    """Immutable bytes-only source with no socket, URL, header or credential API."""

    manifest_sha256: str
    bodies: Mapping[str, bytes]
    fail_at_ordinal: int | None = None

    @classmethod
    def from_mapping(cls, plan: Mapping[str, Any], bodies: Mapping[str, bytes], *,
                     fail_at_ordinal: int | None = None) -> "InMemoryFixtureSource":
        expected = {row["request_sha256"] for row in plan.get("requests") or ()}
        if (not re.fullmatch(r"[0-9a-f]{64}", str(plan.get("manifest_sha256") or ""))
                or set(bodies) != expected
                or any(type(value) is not bytes for value in bodies.values())
                or (fail_at_ordinal is not None
                    and (type(fail_at_ordinal) is not int or not 1 <= fail_at_ordinal <= 6))):
            raise ValueError("CAPTURE_READINESS_FIXTURE_SOURCE_INVALID")
        return cls(str(plan["manifest_sha256"]), MappingProxyType(dict(bodies)), fail_at_ordinal)

    def body_for(self, request: Mapping[str, Any]) -> bytes:
        if self.fail_at_ordinal == request.get("ordinal"):
            raise RuntimeError("CAPTURE_READINESS_SYNTHETIC_INTERRUPTION")
        return self.bodies[str(request["request_sha256"])]


def _digest(value: Any) -> str:
    return sha256(canonical_bytes(value))


def _unix(day: str) -> int:
    parsed = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def build_offline_plan(*, source_sha: str, implementation_sha256: str,
                       executed_at: datetime) -> dict[str, Any]:
    """Derive the latest finalized XNYS session at call time; never backdate it."""
    if (not re.fullmatch(r"[0-9a-f]{40}", source_sha)
            or not re.fullmatch(r"[0-9a-f]{64}", implementation_sha256)):
        raise ValueError("CAPTURE_READINESS_IMPLEMENTATION_IDENTITY_INVALID")
    if (not isinstance(executed_at, datetime) or executed_at.tzinfo is None
            or executed_at.utcoffset() is None):
        raise ValueError("CAPTURE_READINESS_EXECUTION_TIME_INVALID")
    observed = executed_at.astimezone(timezone.utc)
    recent = (observed.date() - timedelta(days=10)).isoformat()
    finalized_calendar = build_xnys_calendar(start_date=recent, as_of=observed)
    finalized = finalized_calendar["finalized_session"]
    canonical_candle = request_parameters("historical_ohlcv", "NVDA",
                                          as_of=datetime.fromisoformat(finalized).date())
    start = datetime.fromtimestamp(canonical_candle["from"], timezone.utc).date().isoformat()
    calendar = build_xnys_calendar(start_date=start, as_of=observed)
    finalized = calendar["finalized_session"]
    requests = []
    for symbol in SYMBOLS:
        for capability, endpoint in CAPABILITIES:
            parameters = request_parameters(
                capability, symbol, as_of=datetime.fromisoformat(finalized).date(),
            )
            row = {"ordinal": len(requests) + 1, "method": "GET", "ticker": symbol,
                   "capability": capability, "endpoint": endpoint, "parameters": parameters}
            row["request_sha256"] = _digest(row)
            requests.append(row)
    plan: dict[str, Any] = {
        "schema": SCHEMA, "mode": "OFFLINE_DISABLED_NO_TRANSPORT",
        "source_sha": source_sha, "implementation_sha256": implementation_sha256,
        "generated_at": observed.isoformat(), "finalized_session": finalized,
        "calendar": calendar, "calendar_artifact_sha256": calendar["artifact_sha256"],
        "limits": {"max_get_attempts": 6, "concurrency": 1, "retries": 0,
                   "automatic_redirects": False, "verified_account_limit_rpm_max": 60,
                   "response_body_bytes_max": MAX_BODY_BYTES, "timeout_seconds": 30},
        "requests": requests, "raw_output": "PRIVATE_RAW_FIRST",
        "evidence_class": "COMPLETED_SESSION_DAILY_NOT_INTRADAY",
        "recommendation_authority": "NONE", "publication_authority": "NONE",
        "provider_calls": 0, "authorization_consumed": False,
        "blockers": list(UNKNOWN_BLOCKERS),
    }
    plan["manifest_sha256"] = _digest(plan)
    return plan


def validate_plan(plan: Mapping[str, Any], *, executed_at: datetime) -> None:
    required_keys = {"schema", "mode", "source_sha", "implementation_sha256", "generated_at",
                     "finalized_session", "calendar", "calendar_artifact_sha256", "limits",
                     "requests", "raw_output", "evidence_class", "recommendation_authority",
                     "publication_authority", "provider_calls", "authorization_consumed",
                     "blockers", "manifest_sha256"}
    if set(plan) != required_keys:
        raise ValueError("CAPTURE_READINESS_PLAN_SCHEMA_INVALID")
    unsigned = dict(plan)
    supplied = unsigned.pop("manifest_sha256", None)
    if supplied != _digest(unsigned) or plan.get("schema") != SCHEMA:
        raise ValueError("CAPTURE_READINESS_MANIFEST_DIGEST_INVALID")
    if plan.get("mode") != "OFFLINE_DISABLED_NO_TRANSPORT" or plan.get("provider_calls") != 0:
        raise PermissionError("CAPTURE_READINESS_TRANSPORT_NOT_DISABLED")
    if (plan.get("raw_output") != "PRIVATE_RAW_FIRST"
            or plan.get("evidence_class") != "COMPLETED_SESSION_DAILY_NOT_INTRADAY"
            or plan.get("recommendation_authority") != "NONE"
            or plan.get("publication_authority") != "NONE"):
        raise PermissionError("CAPTURE_READINESS_AUTHORITY_INVARIANT_INVALID")
    try:
        generated = datetime.fromisoformat(str(plan["generated_at"]).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("CAPTURE_READINESS_GENERATION_TIME_INVALID") from None
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("CAPTURE_READINESS_GENERATION_TIME_INVALID")
    expected = build_offline_plan(source_sha=str(plan.get("source_sha")),
                                  implementation_sha256=str(plan.get("implementation_sha256")),
                                  executed_at=executed_at)
    if plan.get("finalized_session") != expected["finalized_session"]:
        raise ValueError("CAPTURE_READINESS_STALE_SESSION")
    calendar = plan.get("calendar")
    if (not isinstance(calendar, dict)
            or calendar.get("artifact_sha256") != plan.get("calendar_artifact_sha256")
            or calendar.get("generated_at") != generated.astimezone(timezone.utc).isoformat()):
        raise ValueError("CAPTURE_READINESS_CALENDAR_EVIDENCE_INVALID")
    verify_xnys_calendar(calendar, as_of=executed_at)
    calendar_identity_keys = ("schema_version", "source", "calendar", "version", "timezone",
                              "trading_sessions", "finalized_session", "session_status",
                              "session_open_at", "session_close_at", "early_close",
                              "finalization_grace_seconds")
    if any(calendar.get(key) != expected["calendar"].get(key) for key in calendar_identity_keys):
        raise ValueError("CAPTURE_READINESS_CALENDAR_COVERAGE_INVALID")
    close = datetime.fromisoformat(str(calendar["session_close_at"]).replace("Z", "+00:00"))
    finalized_at = close + timedelta(seconds=int(calendar["finalization_grace_seconds"]))
    if not finalized_at <= generated.astimezone(timezone.utc) <= executed_at.astimezone(timezone.utc):
        raise ValueError("CAPTURE_READINESS_GENERATION_TIME_INVALID")
    if plan.get("limits") != expected["limits"] or plan.get("requests") != expected["requests"]:
        raise ValueError("CAPTURE_READINESS_SCOPE_INVALID")
    if plan.get("blockers") != list(UNKNOWN_BLOCKERS) or plan.get("authorization_consumed") is not False:
        raise PermissionError("CAPTURE_READINESS_BLOCKERS_INVALID")
    for row in plan["requests"]:
        if row["endpoint"] not in RESEARCH_ENDPOINTS:
            raise PermissionError("CAPTURE_READINESS_ENDPOINT_INVALID")


def validate_approval(plan: Mapping[str, Any], *, approval: Mapping[str, Any],
                      entitlement: Mapping[str, Any], now: datetime) -> None:
    """Reject live admission: required runtime authority is intentionally absent."""
    validate_plan(plan, executed_at=now)
    try:
        approval_expiry = datetime.fromisoformat(str(approval["expires_at"]).replace("Z", "+00:00"))
        entitlement_expiry = datetime.fromisoformat(str(entitlement["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        raise PermissionError("CAPTURE_READINESS_EXPIRY_EVIDENCE_INVALID") from None
    if (now.tzinfo is None or now.utcoffset() is None
            or approval_expiry.tzinfo is None or entitlement_expiry.tzinfo is None):
        raise PermissionError("CAPTURE_READINESS_EXPIRY_EVIDENCE_INVALID")
    raise PermissionError("CAPTURE_READINESS_LIVE_ADMISSION_NOT_IMPLEMENTED")


def _private_directory(path: Path) -> Path:
    path = path.absolute()
    for candidate in (path, *path.parents):
        if candidate.exists() and stat.S_ISLNK(candidate.lstat().st_mode):
            raise PermissionError("CAPTURE_READINESS_SYMLINK_PATH_FORBIDDEN")
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if created:
        os.chmod(path, 0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("CAPTURE_READINESS_PRIVATE_DIRECTORY_INVALID")
    return path


def _write_private_once(path: Path, value: bytes) -> str:
    if type(value) is not bytes or len(value) > MAX_BODY_BYTES:
        raise ValueError("CAPTURE_READINESS_PRIVATE_WRITE_SIZE_INVALID")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(value):
            written = os.write(descriptor, value[offset:])
            if not isinstance(written, int) or written <= 0:
                raise OSError("CAPTURE_READINESS_PRIVATE_WRITE_INCOMPLETE")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    persisted = path.read_bytes()
    if persisted != value:
        raise OSError("CAPTURE_READINESS_PRIVATE_WRITE_VERIFICATION_FAILED")
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return hashlib.sha256(persisted).hexdigest()


def run_offline_fixture(
    plan: Mapping[str, Any], *, source: InMemoryFixtureSource,
    private_output_root: Path, durable_claim_root: Path, fixture_label: str,
    executed_at: datetime,
) -> dict[str, Any]:
    """Exercise raw-first capture mechanics with an explicitly synthetic adapter.

    This entry point rejects ordinary callables so a live HTTP client cannot be
    accidentally supplied.  It writes each returned body once before any JSON
    interpretation, retaining partial raw evidence when a later fixture fails.
    It never accepts a credential, base URL, headers, or network configuration.
    """
    validate_plan(plan, executed_at=executed_at)
    if (type(source) is not InMemoryFixtureSource
            or source.manifest_sha256 != plan["manifest_sha256"]
            or not re.fullmatch(r"FIXTURE:[A-Z0-9][A-Z0-9_-]{2,63}", fixture_label)):
        raise PermissionError("CAPTURE_READINESS_IMMUTABLE_FIXTURE_SOURCE_REQUIRED")
    output_root = _private_directory(Path(private_output_root))
    claim_root = _private_directory(Path(durable_claim_root))
    run = _private_directory(output_root / plan["manifest_sha256"])
    synthetic_claim = claim_root / f".{plan['manifest_sha256']}.synthetic-consumed"
    _write_private_once(synthetic_claim, canonical_bytes({
        "classification": "SYNTHETIC_FIXTURE_REHEARSAL_NOT_LIVE_AUTHORIZATION",
        "fixture_label": fixture_label, "manifest_sha256": plan["manifest_sha256"],
        "source_sha": plan["source_sha"], "implementation_sha256": plan["implementation_sha256"],
    }) + b"\n")
    raw_by_request: dict[str, bytes] = {}
    persisted_hashes: dict[str, str] = {}
    try:
        for row in plan["requests"]:
            raw = source.body_for(row)
            if type(raw) is not bytes or not 0 < len(raw) <= MAX_BODY_BYTES:
                raise ValueError("CAPTURE_READINESS_FIXTURE_BODY_SIZE_OR_TYPE_INVALID")
            identity = row["request_sha256"]
            persisted_hashes[identity] = _write_private_once(
                run / f"{row['ordinal']:02d}-{identity}.raw", raw,
            )
            if persisted_hashes[identity] != hashlib.sha256(raw).hexdigest():
                raise OSError("CAPTURE_READINESS_PERSISTED_HASH_MISMATCH")
            raw_by_request[identity] = raw
    except Exception as exc:
        _write_private_once(run / "incomplete.json", canonical_bytes({
            "classification": "SYNTHETIC_FIXTURE_INCOMPLETE_NOT_LIVE_CAPTURE",
            "fixture_label": fixture_label, "manifest_sha256": plan["manifest_sha256"],
            "completed_raw_bodies": len(raw_by_request), "failure_type": type(exc).__name__,
        }) + b"\n")
        raise
    validated = validate_synthetic_capture(plan, raw_by_request, executed_at=executed_at)
    summary = {
        **validated, "fixture_label": fixture_label,
        "classification": "SYNTHETIC_FIXTURE_REHEARSAL_NOT_LIVE_CAPTURE",
        "manifest_sha256": plan["manifest_sha256"], "raw_output_private": True,
        "live_authorization_consumed": False, "provider_transport_available": False,
        "provider_call_measurement": "NOT_APPLICABLE_IMMUTABLE_MEMORY_SOURCE",
        "gateway_capture_time_contract": "MISSING_NOT_INGESTIBLE",
        "per_request_attempt_telemetry": "MISSING_NOT_INGESTIBLE",
    }
    _write_private_once(run / "summary.json", canonical_bytes(summary) + b"\n")
    return summary


def _raw_json(raw: bytes) -> Any:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BODY_BYTES:
        raise ValueError("CAPTURE_READINESS_RAW_BODY_SIZE_INVALID")
    def constant(_: str) -> None:
        raise ValueError("CAPTURE_READINESS_NONFINITE_VALUE")
    try:
        return json.loads(raw, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("CAPTURE_READINESS_RAW_JSON_INVALID") from None


def validate_synthetic_capture(plan: Mapping[str, Any], raw_by_request: Mapping[str, bytes], *,
                               executed_at: datetime) -> dict[str, Any]:
    """Validate labeled fixture bytes as a complete aligned private capture."""
    validate_plan(plan, executed_at=executed_at)
    expected = {row["request_sha256"]: row for row in plan["requests"]}
    if set(raw_by_request) != set(expected):
        raise ValueError("CAPTURE_READINESS_PARTIAL_CAPTURE")
    values: dict[tuple[str, str], Any] = {}
    raw_hashes = {}
    for identity, row in expected.items():
        raw = raw_by_request[identity]
        value = _raw_json(raw)
        raw_hashes[identity] = hashlib.sha256(raw).hexdigest()
        values[(row["ticker"], row["capability"])] = value
    sessions_by_symbol = {}
    for symbol in SYMBOLS:
        candle_request = next(row for row in plan["requests"]
                              if row["ticker"] == symbol and row["capability"] == "historical_ohlcv")
        candle = values[(symbol, "historical_ohlcv")]
        if not isinstance(candle, Mapping) or candle.get("s") != "ok":
            raise ValueError("CAPTURE_READINESS_CANDLE_STATUS_INVALID")
        arrays = [candle.get(key) for key in ("t", "o", "h", "l", "c", "v")]
        if any(not isinstance(value, list) for value in arrays) or not arrays[0] or len({len(value) for value in arrays}) != 1:
            raise ValueError("CAPTURE_READINESS_CANDLE_ARRAY_INVALID")
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
               for value in arrays for item in value):
            raise ValueError("CAPTURE_READINESS_CANDLE_NONFINITE_OR_INVALID")
        for opened, high, low, close, volume in zip(*arrays[1:]):
            if min(opened, high, low, close) <= 0 or volume < 0 or not (low <= opened <= high and low <= close <= high):
                raise ValueError("CAPTURE_READINESS_OHLCV_INVALID")
        try:
            instants = [datetime.fromtimestamp(item, timezone.utc) for item in arrays[0]]
        except (ValueError, OverflowError, OSError):
            raise ValueError("CAPTURE_READINESS_CANDLE_TIMESTAMP_INVALID") from None
        if any(type(item) is not int or instant.time() != datetime.min.time()
               for item, instant in zip(arrays[0], instants)):
            raise ValueError("CAPTURE_READINESS_CANDLE_TIMESTAMP_AMBIGUOUS")
        sessions = [instant.date().isoformat() for instant in instants]
        declared_start = datetime.fromtimestamp(
            candle_request["parameters"]["from"], timezone.utc,
        ).date().isoformat()
        expected_calendar = plan["calendar"]
        expected_sessions = list(expected_calendar["trading_sessions"])
        if (expected_calendar["finalized_session"] != plan["finalized_session"]
                or expected_sessions[0] < declared_start
                or candle_request["parameters"]["to"] != _unix(plan["finalized_session"]) + 86399
                or sessions != expected_sessions):
            raise ValueError("CAPTURE_READINESS_CANDLE_SESSION_INVALID")
        sessions_by_symbol[symbol] = sessions
        for capability in ("splits", "dividends"):
            actions = values[(symbol, capability)]
            if not isinstance(actions, list):
                raise ValueError("CAPTURE_READINESS_CORPORATE_ACTION_INVALID")
            for action in actions:
                action_date = action.get("date") if isinstance(action, Mapping) else None
                if not isinstance(action_date, str) or action_date not in sessions:
                    raise ValueError("CAPTURE_READINESS_CORPORATE_ACTION_INVALID")
                numeric_fields = (("fromFactor", "toFactor") if capability == "splits" else ("amount",))
                if any(isinstance(action.get(field), bool)
                       or not isinstance(action.get(field), (int, float))
                       or not math.isfinite(action[field])
                       or (action[field] <= 0 if capability == "splits" else action[field] < 0)
                       for field in numeric_fields):
                    raise ValueError("CAPTURE_READINESS_CORPORATE_ACTION_INVALID")
            action_dates = [action["date"] for action in actions]
            if action_dates != sorted(set(action_dates)):
                raise ValueError("CAPTURE_READINESS_CORPORATE_ACTION_INVALID")
    if sessions_by_symbol["NVDA"] != sessions_by_symbol["SPY"]:
        raise ValueError("CAPTURE_READINESS_SPY_ALIGNMENT_INVALID")
    return {"status": "SYNTHETIC_FIXTURE_VALID_ONLY", "fixture_label_required": True,
            "session_count": len(sessions_by_symbol["NVDA"]), "raw_sha256": raw_hashes,
            "publication_authority": "NONE",
            "adjustment_authority": "UNRESOLVED_REQUIRES_SEPARATE_ADMISSION",
            "ingestion_authority": "NONE_MISSING_CAPTURE_WINDOW_TELEMETRY_AND_ADJUSTMENT_EVIDENCE"}


__all__ = ["InMemoryFixtureSource", "MAX_BODY_BYTES", "SCHEMA", "build_offline_plan",
           "run_offline_fixture", "validate_approval", "validate_plan",
           "validate_synthetic_capture"]
