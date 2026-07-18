"""
Atlas V95.2 — Shared Data Integrity Helpers

One canonical implementation for:
- missing-value detection;
- preserving legitimate zero/False values;
- first-present field resolution;
- numeric coercion;
- percentage normalization.

These functions are deterministic and have no Streamlit or provider dependencies.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
import math
import re

MISSING_STRINGS = frozenset({
    "",
    "n/a",
    "na",
    "none",
    "null",
    "nan",
    "unavailable",
    "under review",
    "not available",
    "not reported",
    "unknown",
    "-",
    "—",
})


def is_present(value: Any, *, zero_is_missing: bool = False) -> bool:
    """Return True when a value is usable. Zero and False are valid by default."""
    if value is None:
        return False

    if isinstance(value, str):
        text = value.strip()
        if text.lower() in MISSING_STRINGS:
            return False
        if zero_is_missing:
            try:
                return float(text.replace(",", "").replace("$", "").replace("%", "")) != 0
            except Exception:
                return True
        return True

    if isinstance(value, bool):
        return not zero_is_missing or value is True

    if isinstance(value, (int, float)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return False
        return not zero_is_missing or number != 0

    try:
        # pandas / numpy scalar NaN support without importing either library.
        if value != value:
            return False
    except Exception:
        pass

    return True


def first_present(
    row: Mapping[str, Any] | None,
    keys: Sequence[str],
    *,
    default: Any = None,
    raw_key: str = "Raw",
    zero_is_missing: bool = False,
) -> Any:
    """
    Resolve the first present value from normalized data, then Raw data.

    Unlike ``a or b``, this preserves legitimate values such as 0, 0.0, and False.
    """
    data = dict(row or {})
    raw = data.get(raw_key)
    raw = raw if isinstance(raw, Mapping) else {}

    for source in (data, raw):
        for key in keys:
            if key not in source:
                continue
            value = source.get(key)
            if is_present(value, zero_is_missing=zero_is_missing):
                return value
    return default


def to_number(value: Any, default: float | None = None) -> float | None:
    """Coerce a provider value to float while preserving a real zero."""
    if not is_present(value):
        return default

    if isinstance(value, bool):
        return float(value)

    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else default

    text = str(value).strip()
    multiplier = 1.0
    suffix = text[-1:].lower()

    if suffix == "k":
        multiplier = 1_000.0
        text = text[:-1]
    elif suffix == "m":
        multiplier = 1_000_000.0
        text = text[:-1]
    elif suffix == "b":
        multiplier = 1_000_000_000.0
        text = text[:-1]
    elif suffix == "t":
        multiplier = 1_000_000_000_000.0
        text = text[:-1]

    cleaned = (
        text.replace(",", "")
        .replace("$", "")
        .replace("%", "")
        .replace("x", "")
        .strip()
    )
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return default

    try:
        number = float(match.group(0)) * multiplier
        return number if math.isfinite(number) else default
    except Exception:
        return default


def normalize_percent(
    value: Any,
    default: float | None = None,
    *,
    decimal_threshold: float = 2.0,
    maximum_absolute: float | None = 500.0,
) -> float | None:
    """
    Normalize provider percentages.

    Examples:
        0.15 -> 15.0
        "15%" -> 15.0
        15 -> 15.0
    """
    number = to_number(value, default)
    if number is None:
        return default

    if abs(number) <= decimal_threshold:
        number *= 100.0

    if maximum_absolute is not None and abs(number) > maximum_absolute:
        return default

    return number


__all__ = [
    "MISSING_STRINGS",
    "is_present",
    "first_present",
    "to_number",
    "normalize_percent",
]
