"""Named runtime guards for evidence entering certified ATLAS consumers.

This module makes family boundaries executable and auditable.  It does not
calculate a score and does not select a provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from services.provider_domain_contracts import GovernedRecord, require_certified_calculation


class CertifiedConsumer(str, Enum):
    VALUATION = "VALUATION"
    ACTION = "ACTION"
    SIX_PILLAR = "SIX_PILLAR"
    OPPORTUNITY = "OPPORTUNITY"
    RVOL = "RVOL"
    VOLUME_QUALITY = "VOLUME_QUALITY"
    LIQUIDITY_GATE = "LIQUIDITY_GATE"
    BREAKOUT_CONFIRMATION = "BREAKOUT_CONFIRMATION"
    TECHNICAL_SCORE = "TECHNICAL_SCORE"
    BUY_NOW_CERTIFICATION = "BUY_NOW_CERTIFICATION"


@dataclass(frozen=True)
class BoundaryDecision:
    consumer: str
    accepted: bool
    evidence_id: str
    dataset_family: str
    coverage_class: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def certified_input(record: GovernedRecord, consumer: CertifiedConsumer) -> tuple[Mapping[str, Any], BoundaryDecision]:
    """Return payload only when the common certified-calculation guard passes."""
    p = record.provenance
    try:
        payload = require_certified_calculation(record)
    except (PermissionError, ValueError) as exc:
        decision = BoundaryDecision(
            consumer=consumer.value, accepted=False, evidence_id=p.raw_evidence_id,
            dataset_family=p.dataset_family.value,
            coverage_class=p.market_coverage_class.value, reason=str(exc),
        )
        error = PermissionError(f"{consumer.value}: {exc}")
        setattr(error, "boundary_decision", decision.as_dict())
        raise error from exc
    return payload, BoundaryDecision(
        consumer=consumer.value, accepted=True, evidence_id=p.raw_evidence_id,
        dataset_family=p.dataset_family.value,
        coverage_class=p.market_coverage_class.value, reason="CERTIFIED_INPUT_ACCEPTED",
    )


def attempt_certified_input(record: GovernedRecord, consumer: CertifiedConsumer) -> dict[str, Any]:
    """Log-safe helper for adversarial reports; never swallows an acceptance."""
    try:
        _payload, decision = certified_input(record, consumer)
        return decision.as_dict()
    except PermissionError as exc:
        return dict(getattr(exc, "boundary_decision", {"consumer": consumer.value, "accepted": False, "reason": str(exc)}))


__all__ = ["BoundaryDecision", "CertifiedConsumer", "attempt_certified_input", "certified_input"]
