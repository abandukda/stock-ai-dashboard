"""Provider-neutral current-market snapshot for deterministic evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
import math

from services.live_market.models import classify_market_session


MARKET_SNAPSHOT_VERSION = "CANONICAL_MARKET_SNAPSHOT_V1"
LIVE_FRESHNESS_SECONDS = 15.0


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def build_market_snapshot(
    ticker: str,
    evidence: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    source = dict(evidence or {})
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    provider_timestamp = _timestamp(source.get("provider_timestamp") or source.get("market_timestamp"))
    received_timestamp = _timestamp(source.get("received_timestamp"))
    price = _number(source.get("price"))
    source_type = str(source.get("source_type") or "UNAVAILABLE").upper()
    session = str(source.get("market_session") or "")
    if not session and provider_timestamp is not None:
        session = classify_market_session(provider_timestamp).value
    session = session or "CLOSED"
    age = None if received_timestamp is None else max(0.0, (current - received_timestamp).total_seconds())
    feed_health = str(source.get("feed_health") or "UNAVAILABLE").upper()
    explicit_stale = source.get("stale")
    live_source = source_type in {
        "CURRENT_QUOTE", "LIVE", "INTRADAY", "TWELVE_DATA_WEBSOCKET",
    }
    stale = bool(explicit_stale) if explicit_stale is not None else (
        not live_source or age is None or age > LIVE_FRESHNESS_SECONDS or feed_health != "HEALTHY"
    )
    fresh_current = bool(price is not None and price > 0 and live_source and not stale)
    return {
        "version": MARKET_SNAPSHOT_VERSION,
        "ticker": str(ticker or "").upper().strip(),
        "price": price,
        "provider": source.get("provider"),
        "provider_timestamp": provider_timestamp.isoformat() if provider_timestamp else None,
        "received_timestamp": received_timestamp.isoformat() if received_timestamp else None,
        "market_session": session,
        "source_type": source_type,
        "freshness_age_seconds": age,
        "stale": stale,
        "feed_health": feed_health,
        "fresh_current_price": fresh_current,
        "customer_label": (
            "Current quote" if fresh_current else
            "Prior close" if source_type == "PRIOR_CLOSE" else
            "Last known price" if price is not None else "Price unavailable"
        ),
    }


__all__ = ["LIVE_FRESHNESS_SECONDS", "MARKET_SNAPSHOT_VERSION", "build_market_snapshot"]
