"""Dormant Twelve Data Phase 1 authority adapter.

The adapter validates provider evidence; it never ranks securities or derives
technical/volume states.  Network acquisition is explicit and remains disabled
unless the single ``TWELVE_DATA_ENABLED`` activation boundary is true.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
import os
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from services.live_market.models import classify_market_session, normalize_ticker


TWELVE_DATA_ENABLED_FLAG = "TWELVE_DATA_ENABLED"
ADAPTER_VERSION = "TWELVE_DATA_PHASE1_ADAPTER_V1"
PUBLICATION_POLICY_VERSION = "TWELVE_DATA_1MIN_PUBLICATION_POLICY_V1"
REST_BASE = "https://api.twelvedata.com"
EASTERN = ZoneInfo("America/New_York")


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_twelve_data_setting(
    name: str, *, secrets: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Read a setting without ever logging or embedding its value."""
    if secrets is None:
        try:
            import streamlit as st
            secrets = st.secrets
        except Exception:
            secrets = {}
    try:
        secret_value = secrets.get(name) if secrets is not None else None
    except Exception:
        secret_value = None
    if secret_value not in (None, ""):
        return str(secret_value)
    return str((environ or os.environ).get(name, ""))


def twelve_data_enabled(
    *, secrets: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    environment = environ if environ is not None else os.environ
    if TWELVE_DATA_ENABLED_FLAG in environment:
        return _truthy(environment.get(TWELVE_DATA_ENABLED_FLAG))
    return _truthy(load_twelve_data_setting(
        TWELVE_DATA_ENABLED_FLAG, secrets=secrets, environ=environ,
    ))


@dataclass(frozen=True)
class Phase1Policy:
    websocket_receipt_freshness_seconds: float = 15.0
    websocket_extended_hours_freshness_seconds: float = 30.0
    completed_bar_publication_safety_seconds: float = 90.0
    publication_policy_version: str = PUBLICATION_POLICY_VERSION

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "Phase1Policy":
        source = environ or os.environ
        return cls(
            websocket_receipt_freshness_seconds=float(
                source.get("TWELVE_DATA_PHASE1_WS_FRESHNESS_SECONDS", "15")
            ),
            websocket_extended_hours_freshness_seconds=float(
                source.get("TWELVE_DATA_PHASE1_WS_EXTENDED_FRESHNESS_SECONDS", "30")
            ),
            completed_bar_publication_safety_seconds=float(
                source.get("TWELVE_DATA_PHASE1_BAR_SAFETY_SECONDS", "90")
            ),
        )


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _evidence_id(*parts: Any) -> str:
    identity = "|".join(str(part or "") for part in parts)
    return "TD1-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def _aware(value: Any, *, local_zone: ZoneInfo = EASTERN) -> datetime | None:
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000.0
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_zone)
    return parsed.astimezone(timezone.utc)


def normalize_websocket_price(
    ticker: str,
    event: Mapping[str, Any] | None,
    *,
    received_timestamp: datetime,
    now: datetime | None = None,
    policy: Phase1Policy | None = None,
) -> dict[str, Any]:
    """Return a current-price candidate only for a fresh, same-symbol event."""
    symbol = normalize_ticker(ticker)
    source = dict(event or {})
    configured = policy or Phase1Policy.from_environment()
    received = _aware(received_timestamp)
    current = _aware(now or datetime.now(timezone.utc))
    supplied_symbol = source.get("symbol") or source.get("ticker")
    price = _number(source.get("price"))
    provider_time = _aware(source.get("timestamp") or source.get("provider_timestamp"))
    reasons: list[str] = []
    if not supplied_symbol or str(supplied_symbol).upper() != symbol:
        reasons.append("WEBSOCKET_SYMBOL_MISMATCH")
    if price is None or price <= 0:
        reasons.append("WEBSOCKET_PRICE_INVALID")
    session_time = provider_time or received
    session = classify_market_session(session_time).value if session_time else "CLOSED"
    freshness_limit = (
        configured.websocket_extended_hours_freshness_seconds
        if session in {"PRE_MARKET", "AFTER_HOURS"}
        else configured.websocket_receipt_freshness_seconds
    )
    if received is None or current is None:
        reasons.append("LOCAL_RECEIPT_TIMESTAMP_MISSING")
        receipt_age = None
    else:
        receipt_age = max(0.0, (current - received).total_seconds())
        if receipt_age > freshness_limit:
            reasons.append("WEBSOCKET_RECEIPT_STALE")
    if session in {"CLOSED", "OVERNIGHT"}:
        reasons.append("NO_CURRENT_MARKET_SESSION")
    available = not reasons
    return {
        "version": ADAPTER_VERSION,
        "ticker": symbol,
        "status": "AVAILABLE" if available else "DATA_UNAVAILABLE",
        "price": price if available else None,
        "provider": "TWELVE_DATA",
        "provider_timestamp": provider_time.isoformat() if provider_time else None,
        "received_timestamp": received.isoformat() if received else None,
        "receipt_age_seconds": receipt_age,
        "freshness_limit_seconds": freshness_limit,
        "market_session": session,
        "source_type": "TWELVE_DATA_WEBSOCKET",
        "stale": not available,
        "feed_health": "HEALTHY" if available else "DEGRADED",
        "timestamp_precision": "PROVIDER_MINUTE_GRANULAR_LOCAL_RECEIPT_REQUIRED",
        "evidence_id": _evidence_id(symbol, "WEBSOCKET", provider_time, received, price),
        "methodology_version": ADAPTER_VERSION,
        "reason_codes": tuple(reasons),
    }


def quote_as_non_authoritative(ticker: str, quote: Mapping[str, Any] | None) -> dict[str, Any]:
    """Retain quote provenance while mechanically excluding it as CURRENT_PRICE."""
    source = dict(quote or {})
    return {
        "version": ADAPTER_VERSION,
        "ticker": normalize_ticker(ticker),
        "status": "CONTEXT_ONLY" if source else "DATA_UNAVAILABLE",
        "price": _number(source.get("close") or source.get("price")),
        "provider_timestamp": source.get("timestamp"),
        "source_type": "TWELVE_DATA_QUOTE_CONTEXT_ONLY",
        "current_price_authority": False,
        "reason_codes": ("QUOTE_NOT_APPROVED_AS_CURRENT_PRICE_AUTHORITY",),
    }


def _bar_time(value: Any, zone: ZoneInfo) -> datetime | None:
    return _aware(value, local_zone=zone)


def validate_time_series(
    ticker: str,
    payload: Mapping[str, Any] | None,
    *,
    received_timestamp: datetime,
    now: datetime | None = None,
    policy: Phase1Policy | None = None,
) -> dict[str, Any]:
    """Validate 1-minute bars without filling gaps or synthesizing observations."""
    symbol = normalize_ticker(ticker)
    source = dict(payload or {})
    configured = policy or Phase1Policy.from_environment()
    received = _aware(received_timestamp)
    current = _aware(now or received_timestamp)
    meta = source.get("meta") if isinstance(source.get("meta"), Mapping) else {}
    zone_name = str(meta.get("exchange_timezone") or "America/New_York")
    try:
        zone = ZoneInfo(zone_name)
    except Exception:
        zone = EASTERN
    rows = source.get("values") if isinstance(source.get("values"), Sequence) else []
    parsed: list[dict[str, Any]] = []
    invalid_count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_count += 1
            continue
        stamp = _bar_time(row.get("datetime") or row.get("timestamp"), zone)
        open_, high, low, close = (_number(row.get(key)) for key in ("open", "high", "low", "close"))
        volume = _number(row.get("volume"))
        valid = bool(
            stamp and open_ is not None and high is not None and low is not None and close is not None
            and volume is not None and volume >= 0 and low <= min(open_, close) <= max(open_, close) <= high
        )
        if not valid:
            invalid_count += 1
            continue
        parsed.append({
            "ticker": symbol, "timestamp": stamp.isoformat(), "open": open_, "high": high,
            "low": low, "close": close, "volume": volume,
            "session": classify_market_session(stamp).value, "source_type": "TWELVE_DATA_TIME_SERIES_1MIN",
        })
    input_timestamps = [row["timestamp"] for row in parsed]
    ordered_in_response = input_timestamps in (sorted(input_timestamps), sorted(input_timestamps, reverse=True))
    parsed.sort(key=lambda row: row["timestamp"])
    duplicate_count = len(parsed) - len({row["timestamp"] for row in parsed})
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in parsed:
        if row["timestamp"] not in seen:
            seen.add(row["timestamp"])
            unique.append(row)
    gaps: list[dict[str, Any]] = []
    for previous, following in zip(unique, unique[1:]):
        left = _aware(previous["timestamp"])
        right = _aware(following["timestamp"])
        if not left or not right:
            continue
        if (
            previous["session"] == following["session"] == "REGULAR"
            and left.astimezone(EASTERN).date() == right.astimezone(EASTERN).date()
            and right - left > timedelta(minutes=1)
        ):
            gaps.append({
                "after": left.isoformat(), "before": right.isoformat(),
                "missing_minutes": int((right - left).total_seconds() // 60) - 1,
                "classification": "UNKNOWN_REGULAR_SESSION_GAP",
            })
    safety = timedelta(seconds=configured.completed_bar_publication_safety_seconds)
    completed = []
    for row in unique:
        stamp = _aware(row["timestamp"])
        eligible = bool(current and stamp and current >= stamp + timedelta(minutes=1) + safety)
        completed.append({**row, "completed": eligible, "publication_observed_at": received.isoformat() if received else None})
    eligible = [row for row in completed if row["completed"]]
    degraded = bool(invalid_count or duplicate_count or gaps or not ordered_in_response)
    status = "AVAILABLE" if eligible and not degraded else "DEGRADED" if eligible else "DATA_UNAVAILABLE"
    confirmation_allowed = status == "AVAILABLE"
    return {
        "version": ADAPTER_VERSION,
        "ticker": symbol,
        "status": status,
        "provider": "TWELVE_DATA",
        "source_type": "TWELVE_DATA_TIME_SERIES_1MIN",
        "received_timestamp": received.isoformat() if received else None,
        "publication_policy_version": configured.publication_policy_version,
        "evidence_id": _evidence_id(symbol, "TIME_SERIES_1MIN", received, len(completed)),
        "methodology_version": ADAPTER_VERSION,
        "publication_safety_seconds": configured.completed_bar_publication_safety_seconds,
        "ordered_in_response": ordered_in_response,
        "duplicate_count": duplicate_count,
        "invalid_bar_count": invalid_count,
        "gap_metadata": tuple(gaps),
        "bars": tuple(completed),
        "latest_completed_bar": eligible[-1] if eligible else None,
        "confirmation_allowed": confirmation_allowed,
        "reason_codes": tuple(
            code for condition, code in (
                (not eligible, "COMPLETED_BAR_UNAVAILABLE"),
                (not ordered_in_response, "BAR_ORDER_INVALID"),
                (duplicate_count > 0, "DUPLICATE_BAR_IDENTITY"),
                (invalid_count > 0, "INVALID_OHLCV_BAR"),
                (bool(gaps), "REGULAR_SESSION_GAPS_PRESENT"),
            ) if condition
        ),
    }


def validate_daily_time_series(
    ticker: str,
    payload: Mapping[str, Any] | None,
    *,
    received_timestamp: datetime,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Publish split-adjusted completed daily bars for the approved technical engine."""
    symbol = normalize_ticker(ticker)
    source = dict(payload or {})
    received = _aware(received_timestamp)
    current = _aware(now or received_timestamp)
    meta = source.get("meta") if isinstance(source.get("meta"), Mapping) else {}
    provider_symbol = normalize_ticker(str(meta.get("symbol") or ""))
    zone_name = str(meta.get("exchange_timezone") or "America/New_York")
    try:
        zone = ZoneInfo(zone_name)
    except Exception:
        zone = EASTERN
    invalid = 0
    parsed: list[dict[str, Any]] = []
    for row in source.get("values") if isinstance(source.get("values"), Sequence) else ():
        if not isinstance(row, Mapping):
            invalid += 1
            continue
        raw_stamp = row.get("datetime") or row.get("timestamp")
        try:
            day = datetime.fromisoformat(str(raw_stamp)).date()
            stamp = datetime(day.year, day.month, day.day, 16, 0, tzinfo=zone).astimezone(timezone.utc)
        except (TypeError, ValueError):
            invalid += 1
            continue
        open_, high, low, close = (_number(row.get(key)) for key in ("open", "high", "low", "close"))
        volume = _number(row.get("volume"))
        if not (
            open_ is not None and high is not None and low is not None and close is not None
            and volume is not None and volume >= 0 and low <= min(open_, close) <= max(open_, close) <= high
        ):
            invalid += 1
            continue
        completed = bool(current and current >= stamp + timedelta(seconds=90))
        if completed:
            parsed.append({
                "ticker": symbol, "timestamp": stamp.isoformat(), "open": open_, "high": high,
                "low": low, "close": close, "volume": volume, "completed": True,
                "session": "REGULAR", "source_type": "TWELVE_DATA_TIME_SERIES_1DAY",
            })
    parsed.sort(key=lambda row: row["timestamp"])
    duplicates = len(parsed) - len({row["timestamp"] for row in parsed})
    unique = list({row["timestamp"]: row for row in parsed}.values())
    enough = len(unique) >= 200
    valid = provider_symbol == symbol and enough and not invalid and not duplicates
    reasons = tuple(code for condition, code in (
        (provider_symbol != symbol, "DAILY_SYMBOL_MISMATCH"),
        (not enough, "INSUFFICIENT_DAILY_HISTORY"),
        (invalid > 0, "INVALID_DAILY_OHLCV_BAR"),
        (duplicates > 0, "DUPLICATE_DAILY_BAR_IDENTITY"),
    ) if condition)
    return {
        "version": ADAPTER_VERSION, "ticker": symbol,
        "status": "AVAILABLE" if valid else "DATA_UNAVAILABLE",
        "provider": "TWELVE_DATA", "source_type": "TWELVE_DATA_TIME_SERIES_1DAY",
        "interval": "1day", "range": "1Y", "adjustment_mode": "splits",
        "extended_hours_included": False, "received_timestamp": received.isoformat() if received else None,
        "bars": tuple(unique), "records_found": len(unique), "minimum_history": 200,
        "newest_completed_bar_timestamp": unique[-1]["timestamp"] if unique else None,
        "evidence_id": _evidence_id(symbol, "TIME_SERIES_1DAY", unique[-1]["timestamp"] if unique else None, len(unique)),
        "reason_codes": reasons,
    }


def build_phase1_bundle(
    ticker: str,
    *,
    websocket_event: Mapping[str, Any] | None,
    time_series_payload: Mapping[str, Any] | None,
    daily_time_series_payload: Mapping[str, Any] | None = None,
    received_timestamp: datetime,
    now: datetime | None = None,
    policy: Phase1Policy | None = None,
) -> dict[str, Any]:
    completed_bars = validate_time_series(
        ticker, time_series_payload, received_timestamp=received_timestamp, now=now, policy=policy,
    )
    daily_history = validate_daily_time_series(
        ticker, daily_time_series_payload, received_timestamp=received_timestamp, now=now,
    ) if daily_time_series_payload is not None else {
        "status": "DATA_UNAVAILABLE", "bars": (),
        "reason_codes": ("DAILY_TECHNICAL_HISTORY_NOT_ACQUIRED",),
    }
    latest_intraday = completed_bars.get("latest_completed_bar") or {}
    daily_bars = tuple(daily_history.get("bars") or ())
    latest_daily = daily_bars[-1] if daily_bars else {}
    # A completed regular-session daily bar is the governed close used to retain
    # a rating while the market is closed.  It is distinct from a live entry
    # price and never becomes websocket/current-price authority.
    latest = latest_intraday or latest_daily
    completed_session = bool(latest_daily and daily_history.get("status") == "AVAILABLE")
    last_known_market = {
        "status": "AVAILABLE" if latest else "DATA_UNAVAILABLE",
        "price": latest.get("close"),
        "provider": "TWELVE_DATA",
        "provider_timestamp": latest.get("timestamp"),
        "received_timestamp": completed_bars.get("received_timestamp"),
        "market_session": latest.get("session"),
        "source_type": "TWELVE_DATA_LATEST_COMPLETED_BAR",
        "stale": True,
        "feed_health": "HEALTHY" if completed_bars.get("status") == "AVAILABLE" else "DEGRADED",
        "evidence_id": completed_bars.get("evidence_id"),
        "methodology_version": ADAPTER_VERSION,
        "latest_completed_session_valid": completed_session,
        "reason_codes": tuple(completed_bars.get("reason_codes") or ()),
    }
    return {
        "version": ADAPTER_VERSION,
        "ticker": normalize_ticker(ticker),
        "current_price": normalize_websocket_price(
            ticker, websocket_event, received_timestamp=received_timestamp, now=now, policy=policy,
        ),
        "completed_bars": completed_bars,
        "canonical_technical_history": daily_history,
        "last_known_market": last_known_market,
        "intraday_volume": {
            "status": "DATA_UNAVAILABLE",
            "authority": False,
            "reason_codes": ("TIME_ALIGNED_INTRADAY_VOLUME_BASELINE_NOT_IMPLEMENTED",),
        },
        "completed_daily_volume": _completed_daily_volume(daily_history),
        "breakout_volume_confirmation": {
            "status": "DATA_UNAVAILABLE",
            "authority": False,
            "reason_codes": ("PHASE2_VOLUME_METHODOLOGY_REQUIRED",),
        },
    }


def _completed_daily_volume(daily_history: Mapping[str, Any]) -> dict[str, Any]:
    bars = tuple(daily_history.get("bars") or ())
    if daily_history.get("status") != "AVAILABLE" or len(bars) < 21:
        return {"status": "DATA_UNAVAILABLE", "authority": False, "reason_codes": ("DAILY_VOLUME_BASELINE_UNAVAILABLE",)}
    latest = bars[-1]
    baseline = bars[-21:-1]
    average = sum(float(item["volume"]) for item in baseline) / len(baseline)
    average_dollar = sum(float(item["volume"]) * float(item["close"]) for item in baseline) / len(baseline)
    relative = float(latest["volume"]) / average if average > 0 else None
    return {
        "status": "AVAILABLE" if relative is not None else "DATA_UNAVAILABLE",
        "authority": relative is not None,
        "source_type": "TWELVE_DATA_COMPLETED_DAILY_VOLUME",
        "relative_volume": relative,
        "current_volume": float(latest["volume"]),
        "average_volume": average,
        "average_dollar_volume": average_dollar,
        "as_of": latest.get("timestamp"),
        "evidence_id": daily_history.get("evidence_id"),
        "reason_codes": ("COMPLETED_DAILY_VOLUME_BASELINE_VALIDATED",) if relative is not None else ("DAILY_VOLUME_BASELINE_UNAVAILABLE",),
    }


class TwelveDataPhase1Adapter:
    """Explicit REST adapter; never called implicitly by customer routes."""

    def __init__(self, api_key: str, *, enabled: bool, get: Callable[..., Any]) -> None:
        if not enabled:
            raise RuntimeError("TWELVE_DATA_ENABLED is false")
        if not str(api_key or "").strip():
            raise RuntimeError("TWELVE_DATA_API_KEY is unavailable")
        self._api_key = str(api_key)
        self._get = get

    def fetch_time_series(
        self, ticker: str, *, interval: str = "1min", outputsize: int = 120,
        prepost: bool = True,
    ) -> Mapping[str, Any]:
        response = self._get(
            f"{REST_BASE}/time_series",
            params={
                "symbol": normalize_ticker(ticker), "interval": str(interval),
                "outputsize": int(outputsize), "prepost": "true" if prepost else "false", "adjust": "splits",
            },
            headers={"Authorization": f"apikey {self._api_key}"}, timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("malformed Twelve Data time_series response")
        return payload


def build_adapter_if_enabled(
    *, get: Callable[..., Any], secrets: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> TwelveDataPhase1Adapter | None:
    """Construct the explicit adapter only after the single flag permits it."""
    if not twelve_data_enabled(secrets=secrets, environ=environ):
        return None
    key = load_twelve_data_setting("TWELVE_DATA_API_KEY", secrets=secrets, environ=environ)
    return TwelveDataPhase1Adapter(key, enabled=True, get=get)


__all__ = [
    "ADAPTER_VERSION", "PUBLICATION_POLICY_VERSION", "Phase1Policy",
    "TWELVE_DATA_ENABLED_FLAG", "TwelveDataPhase1Adapter", "build_adapter_if_enabled",
    "build_phase1_bundle", "load_twelve_data_setting", "normalize_websocket_price",
    "quote_as_non_authoritative", "twelve_data_enabled",
    "validate_daily_time_series", "validate_time_series",
]
