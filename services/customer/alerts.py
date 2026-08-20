"""Idempotent customer-alert creation and recipient delivery contracts."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Sequence
from uuid import uuid4

from services.live_market.models import normalize_ticker

from .models import AlertDelivery, AlertType, CustomerAlertEvent, NotificationChannel
from .repository import CustomerRepository


def event_fingerprint(ticker: str, alert_type: AlertType, occurred_at: datetime, evidence_identity: Mapping[str, Any]) -> str:
    """Underlying event identity excludes recipients and delivery attempts."""
    payload = {
        "ticker": normalize_ticker(ticker),
        "alert_type": alert_type.value,
        "occurred_at": occurred_at.isoformat(),
        "evidence_identity": dict(evidence_identity),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def create_customer_alert(
    repository: CustomerRepository,
    *,
    ticker: str,
    alert_type: AlertType,
    occurred_at: datetime,
    evidence_identity: Mapping[str, Any],
    recipients: Sequence[tuple[str, NotificationChannel]],
) -> tuple[CustomerAlertEvent, int]:
    fingerprint = event_fingerprint(ticker, alert_type, occurred_at, evidence_identity)
    event = CustomerAlertEvent(str(uuid4()), ticker, alert_type, occurred_at, dict(evidence_identity), fingerprint)
    repository.insert_event_if_absent(event)
    inserted = 0
    for user_id, channel in sorted(set(recipients), key=lambda item: (item[0], item[1].value)):
        delivery = AlertDelivery(str(uuid4()), fingerprint, user_id, channel)
        inserted += int(repository.insert_delivery_if_absent(delivery))
    return event, inserted


__all__ = ["create_customer_alert", "event_fingerprint"]
