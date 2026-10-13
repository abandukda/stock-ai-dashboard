"""Single read-only customer projection contract for ATLAS customer routes.

The view wraps persisted certified authority and presentation availability. It
never calculates Action, Fair Value, Opportunity, Confidence, pillars, or
publication eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from services.customer_research_v2 import build_customer_research_v2


class Availability(str, Enum):
    CERTIFIED_CURRENT = "CERTIFIED_CURRENT"
    CERTIFIED_DATED = "CERTIFIED_DATED"
    EXTERNAL_CONTEXT = "EXTERNAL_CONTEXT"
    MISSING_RETAINED_EVIDENCE = "MISSING_RETAINED_EVIDENCE"
    PROVIDER_RETRIEVAL_UNAVAILABLE = "PROVIDER_RETRIEVAL_UNAVAILABLE"
    METHODOLOGY_RESTRICTED = "METHODOLOGY_RESTRICTED"
    PUBLICATION_WITHHELD = "PUBLICATION_WITHHELD"


def parse_instant(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def customer_date(value: Any) -> str:
    instant = parse_instant(value)
    return instant.strftime("%b %d, %Y") if instant else "Date unavailable"


def certified_freshness(value: Any, *, now: datetime | None = None, max_age_days: int = 5) -> Availability:
    instant = parse_instant(value)
    if instant is None:
        return Availability.MISSING_RETAINED_EVIDENCE
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return Availability.CERTIFIED_CURRENT if (current - instant).total_seconds() <= max_age_days * 86400 else Availability.CERTIFIED_DATED


@dataclass(frozen=True)
class CustomerResearchView:
    ticker: str
    status: str
    payload: Mapping[str, Any]
    identity: Mapping[str, Any]
    availability: Mapping[str, str]

    @property
    def publication_allowed(self) -> bool:
        return self.status == "AVAILABLE" and bool((self.payload.get("authority") or {}).get("publication_allowed"))

    def as_mapping(self) -> dict[str, Any]:
        return dict(self.payload)


def build_customer_research_view(report: Mapping[str, Any], *, now: datetime | None = None) -> CustomerResearchView:
    projected = build_customer_research_v2(report)
    status = str(projected.get("status") or "RATING_NOT_PUBLISHED")
    ticker = str(projected.get("ticker") or report.get("ticker") or report.get("Ticker") or "").strip().upper()
    identity = projected.get("identity") if isinstance(projected.get("identity"), Mapping) else {}
    if status != "AVAILABLE":
        availability = {"publication": Availability.PUBLICATION_WITHHELD.value}
    else:
        header = projected.get("header") if isinstance(projected.get("header"), Mapping) else {}
        availability = {
            "publication": Availability.CERTIFIED_CURRENT.value,
            "certified_close": certified_freshness(header.get("price_timestamp"), now=now).value,
            "analyst_context": (
                Availability.EXTERNAL_CONTEXT.value
                if (projected.get("wall_street") or {}).get("status") in {"AVAILABLE", "PARTIAL"}
                else Availability.MISSING_RETAINED_EVIDENCE.value
            ),
            "valuation": (
                Availability.CERTIFIED_CURRENT.value
                if (projected.get("valuation_chart") or {}).get("status") == "AVAILABLE"
                else Availability.MISSING_RETAINED_EVIDENCE.value
            ),
            "financials": (
                Availability.CERTIFIED_CURRENT.value
                if (projected.get("financial_snapshot") or {}).get("status") in {"AVAILABLE", "PARTIAL"}
                else Availability.MISSING_RETAINED_EVIDENCE.value
            ),
            "news": (
                Availability.EXTERNAL_CONTEXT.value
                if (projected.get("recent_changes") or {}).get("status") == "AVAILABLE"
                else Availability.MISSING_RETAINED_EVIDENCE.value
            ),
            "earnings": (
                Availability.EXTERNAL_CONTEXT.value
                if (projected.get("catalysts") or {}).get("status") == "AVAILABLE"
                else Availability.MISSING_RETAINED_EVIDENCE.value
            ),
        }
    return CustomerResearchView(
        ticker=ticker,
        status=status,
        payload=MappingProxyType(dict(projected)),
        identity=MappingProxyType(dict(identity)),
        availability=MappingProxyType(availability),
    )


__all__ = ["Availability", "CustomerResearchView", "build_customer_research_view", "certified_freshness", "customer_date", "parse_instant"]
