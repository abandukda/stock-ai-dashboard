
"""Canonical component status definitions for Atlas research."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class ComponentStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NO_RECORDS = "NO_RECORDS"
    NOT_LOADED = "NOT_LOADED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    STALE = "STALE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class ComponentResult:
    name: str
    status: ComponentStatus
    score: float | None
    data: dict[str, Any]
    summary: str
    strengths: list[str]
    risks: list[str]
    source: str
    as_of: str
    missing_fields: list[str]
    retrieval_status: str
    cache_status: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def honest_absence_summary(
    component_name: str,
    status: ComponentStatus,
) -> str:
    label = component_name.replace("_", " ").title()

    if status == ComponentStatus.NO_RECORDS:
        return (
            f"No recent {label.lower()} records were returned by the connected "
            "source. This does not establish a positive or negative signal."
        )
    if status == ComponentStatus.NOT_LOADED:
        return (
            f"Atlas did not receive {label.lower()} data for this stock. "
            "No conclusion should be drawn from the absence."
        )
    if status == ComponentStatus.PROVIDER_ERROR:
        return (
            f"The {label.lower()} source could not be reached. Atlas retained "
            "any last-known-good data and did not infer a replacement signal."
        )
    if status == ComponentStatus.STALE:
        return (
            f"The latest {label.lower()} data are stale. Treat the component "
            "as supporting context rather than a current signal."
        )
    if status == ComponentStatus.UNSUPPORTED:
        return f"{label} is not supported by the current data source."
    if status == ComponentStatus.PARTIAL:
        return (
            f"Only part of the expected {label.lower()} data is available. "
            "Atlas reduces confidence rather than filling gaps with defaults."
        )
    return ""


__all__ = [
    "ComponentResult",
    "ComponentStatus",
    "honest_absence_summary",
]
