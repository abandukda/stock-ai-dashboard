"""Presentation-only formatting for customer-facing market timestamps."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


_EASTERN = ZoneInfo("America/New_York")


def format_market_timestamp_et(value: Any, *, unavailable: str = "Timestamp unavailable") -> str:
    """Render a canonical/provider timestamp in concise Eastern Time without mutating it."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_EASTERN)
        eastern = parsed.astimezone(_EASTERN)
    except (TypeError, ValueError):
        return unavailable
    hour = eastern.strftime("%I").lstrip("0") or "0"
    return f"{eastern.strftime('%b')} {eastern.day}, {hour}:{eastern.strftime('%M %p')} ET"
