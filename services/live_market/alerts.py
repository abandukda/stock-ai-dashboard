"""Durable, idempotent technical-state alert contracts."""

from __future__ import annotations

from datetime import timezone
import hashlib
import json
from typing import Protocol
from uuid import uuid4

from .models import AlertEvent, FeedHealth, TechnicalStateResult


class AlertRepository(Protocol):
    def insert_if_absent(self, event: AlertEvent) -> bool: ...


class InMemoryAlertRepository:
    def __init__(self) -> None:
        self._events: dict[str, AlertEvent] = {}

    def insert_if_absent(self, event: AlertEvent) -> bool:
        if event.event_fingerprint in self._events:
            return False
        self._events[event.event_fingerprint] = event
        return True

    def all(self) -> tuple[AlertEvent, ...]:
        return tuple(self._events.values())


def create_alert_event(result: TechnicalStateResult, recipients: tuple[str, ...], urgency: str) -> AlertEvent | None:
    if result.feed_health != FeedHealth.HEALTHY or result.previous_state == result.new_state:
        return None
    canonical = {
        "ticker": result.ticker,
        "previous_state": result.previous_state.value,
        "new_state": result.new_state.value,
        "event_timestamp": result.event_timestamp.astimezone(timezone.utc).isoformat(),
        "evidence": dict(result.evidence),
    }
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return AlertEvent(
        event_id=str(uuid4()), ticker=result.ticker,
        previous_state=result.previous_state, new_state=result.new_state,
        event_timestamp=result.event_timestamp, evidence=dict(result.evidence),
        urgency=str(urgency), event_fingerprint=fingerprint,
        feed_health=result.feed_health, recipients=tuple(sorted(set(recipients))),
    )
