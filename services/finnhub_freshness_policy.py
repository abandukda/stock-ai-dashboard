"""Operational freshness certification for Finnhub acquisition families.

This policy governs whether newly acquired evidence may enter certification. It
does not change investment scoring, weights, or publication thresholds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


VERSION = "ATLAS_FINNHUB_FAMILY_FRESHNESS_V1"
FUTURE_SKEW_SECONDS = 300
CAPTURE_START_TOLERANCE_SECONDS = 60
MAX_COMPLETED_MARKET_AGE_DAYS = 7

POLICIES = {
    "company_profile": "CURRENT_RUN_CAPTURE",
    "financial_statements": "CURRENT_RUN_CAPTURE_PERIOD_BOUND",
    "basic_financials": "CURRENT_RUN_CAPTURE",
    "historical_ohlcv": "CURRENT_RUN_CAPTURE_FINALIZED_SESSION",
    "eps_estimates": "CURRENT_RUN_CAPTURE_PERIOD_BOUND",
    "ebitda_estimates": "CURRENT_RUN_CAPTURE_PERIOD_BOUND",
}


def _utc(value: Any, code: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"FRESHNESS_{code}_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"FRESHNESS_{code}_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def certify_family_freshness(
    *, capability: str, record: Mapping[str, Any], acquisition_started_at: datetime,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    if capability not in POLICIES:
        raise ValueError("FRESHNESS_CAPABILITY_NOT_REGISTERED")
    checked = (checked_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    started = acquisition_started_at.astimezone(timezone.utc)
    provenance = dict(record.get("provenance") or {})
    captured = _utc(provenance.get("capture_timestamp"), "CAPTURE_TIMESTAMP")
    if captured.timestamp() < started.timestamp() - CAPTURE_START_TOLERANCE_SECONDS:
        raise ValueError(f"FRESHNESS_STALE_CAPTURE:{capability}")
    if captured.timestamp() > checked.timestamp() + FUTURE_SKEW_SECONDS:
        raise ValueError(f"FRESHNESS_FUTURE_CAPTURE:{capability}")

    payload = dict(record.get("payload") or {})
    status = "FRESH"
    latest_period = None
    if capability == "financial_statements":
        reports = list(payload.get("reports") or ())
        periods = sorted(str(item.get("fiscal_date")) for item in reports if item.get("fiscal_date"))
        latest_period = periods[-1] if periods else None
        if latest_period and _utc(latest_period + "T00:00:00+00:00", "FISCAL_PERIOD") > captured:
            raise ValueError("FRESHNESS_FINANCIAL_PERIOD_AFTER_CAPTURE")
        status = "FRESH" if reports else "UNAVAILABLE"
    elif capability == "historical_ohlcv":
        stamps = list(payload.get("timestamps") or ())
        flags = list(payload.get("completed_session_flags") or ())
        completed = [
            datetime.fromtimestamp(float(stamp), timezone.utc)
            for index, stamp in enumerate(stamps)
            if index < len(flags) and flags[index] is True
        ]
        if completed:
            latest = max(completed)
            latest_period = latest.date().isoformat()
            if latest > captured:
                raise ValueError("FRESHNESS_MARKET_SESSION_AFTER_CAPTURE")
            if (captured.date() - latest.date()).days > MAX_COMPLETED_MARKET_AGE_DAYS:
                raise ValueError("FRESHNESS_MARKET_SESSION_STALE")
        else:
            status = "UNAVAILABLE"
    elif capability in {"eps_estimates", "ebitda_estimates"}:
        estimates = list(payload.get("estimates") or ())
        period_values = [item.get("period") for item in estimates]
        if estimates and any(not value for value in period_values):
            raise ValueError("FRESHNESS_ESTIMATE_PERIOD_MISSING")
        periods = []
        for value in period_values:
            # Forward periods may legitimately follow capture time. The freshness
            # invariant is therefore identity completeness and parseability, not
            # a historical-period cutoff.
            periods.append(_utc(str(value) + "T00:00:00+00:00", "ESTIMATE_PERIOD"))
        latest_period = max(periods).date().isoformat() if periods else None
        status = "FRESH" if estimates else "UNAVAILABLE"
    elif not payload:
        status = "UNAVAILABLE"

    return {
        "policy_version": VERSION,
        "capability": capability,
        "policy": POLICIES[capability],
        "status": status,
        "capture_timestamp": captured.isoformat(),
        "latest_effective_period": latest_period,
    }


__all__ = ["POLICIES", "VERSION", "certify_family_freshness"]
