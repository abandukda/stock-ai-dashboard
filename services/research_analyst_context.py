"""Pure validation of normalized analyst context, never rating authority.

Hashes establish byte consistency, not the meaning of counts, targets or dates.
Malformed families are withheld as a whole; no missing value becomes zero and
no count/price is coerced from a boolean, fractional count or numeric string.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
import re
from typing import Any, Mapping


SCHEMA = "ATLAS_NORMALIZED_ANALYST_CONTEXT_V1"
COUNT_FIELDS = ("strong_buy", "buy", "hold", "sell", "strong_sell")
# Customer chart/JSON consumers must retain exact integer values. This is a
# serialization boundary, not an estimated maximum number of analysts.
COUNT_MAX_EXACT_INTEGER = 2**53 - 1
TARGET_FIELDS = ("target_low", "target_mean", "target_median", "target_high")


def _as_of(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return datetime.combine(date.fromisoformat(value), datetime.min.time(), timezone.utc)
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return instant.astimezone(timezone.utc) if instant.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _identity_matches(item: Mapping[str, Any], ticker: str) -> bool:
    return all(key not in item or isinstance(item[key], str) and item[key].strip().upper() == ticker
               for key in ("ticker", "symbol"))


def _target_update_valid(value: Any, checked: datetime) -> bool:
    """Validate source precision without inventing a provider timezone.

    Finnhub's documented native target clock has no offset. Its calendar date
    can be checked against the response capture date, but its wall time is not
    an attested UTC instant. Offset-aware values retain exact instant checks.
    """
    if not isinstance(value, str):
        return False
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return date.fromisoformat(value) <= checked.date()
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value):
            native = datetime.fromisoformat(value)
            return native.date() <= checked.date()
    except (TypeError, ValueError, OverflowError):
        return False
    instant = _as_of(value)
    return instant is not None and instant <= checked


def analyst_context_rejection(capability: str, payload: Any, *, ticker: str,
                               now: datetime) -> str | None:
    """Return a fixed public rejection code, or None; never mutate input.

    Only recommendations/price_targets are governed here. Empty recommendation
    periods are valid absence of coverage. Targets can be partial, but supplied
    values and a source update date must be valid; missing values stay missing.
    """
    if capability not in {"recommendations", "price_targets"}:
        return None
    if (not isinstance(payload, Mapping) or not isinstance(ticker, str) or not ticker
            or not _identity_matches(payload, ticker.upper())):
        return "ANALYST_CONTEXT_IDENTITY_OR_SCHEMA_INVALID"
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return "ANALYST_CONTEXT_TIME_INVALID"
    checked = now.astimezone(timezone.utc)
    if capability == "recommendations":
        periods = payload.get("periods")
        if not isinstance(periods, list):
            return "RECOMMENDATIONS_SCHEMA_INVALID"
        previous = None
        for item in periods:
            if not isinstance(item, Mapping) or not _identity_matches(item, ticker.upper()):
                return "ANALYST_CONTEXT_IDENTITY_OR_SCHEMA_INVALID"
            period = _as_of(item.get("period"))
            if (period is None or len(item["period"]) != 10 or period > checked
                    or previous is not None and period >= previous):
                return "RECOMMENDATIONS_PERIOD_INVALID"
            if (any(type(item.get(key)) is not int or not 0 <= item[key] <= COUNT_MAX_EXACT_INTEGER
                    for key in COUNT_FIELDS)
                    or sum(item[key] for key in COUNT_FIELDS) > COUNT_MAX_EXACT_INTEGER):
                return "RECOMMENDATIONS_COUNTS_INVALID"
            previous = period
        return None
    if not _target_update_valid(payload.get("last_updated"), checked):
        return "PRICE_TARGET_DATE_INVALID"
    supplied = {key: payload[key] for key in TARGET_FIELDS if payload.get(key) is not None}
    try:
        valid = supplied and all(type(value) in (int, float) and math.isfinite(value) and value > 0
                                 for value in supplied.values())
    except (OverflowError, TypeError, ValueError):
        valid = False
    if not valid:
        return "PRICE_TARGET_VALUE_INVALID"
    low, high = supplied.get("target_low"), supplied.get("target_high")
    if low is not None and high is not None and low > high:
        return "PRICE_TARGET_RANGE_INVALID"
    if any(low is not None and value < low or high is not None and value > high
           for key, value in supplied.items() if key in {"target_mean", "target_median"}):
        return "PRICE_TARGET_RANGE_INVALID"
    return None


__all__ = ["SCHEMA", "COUNT_FIELDS", "COUNT_MAX_EXACT_INTEGER", "TARGET_FIELDS", "analyst_context_rejection"]
