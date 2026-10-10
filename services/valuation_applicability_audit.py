"""Read-only consistency diagnostics for registered valuation applicability."""
from __future__ import annotations

from typing import Any

from services.canonical_data_validation import _applicability
from services.valuation_evidence_strength import PROFESSIONAL_METHOD_POLICY


def registry_conflicts() -> tuple[dict[str, Any], ...]:
    conflicts = []
    for company_type, policy in sorted(PROFESSIONAL_METHOD_POLICY.items()):
        for methodology_id in sorted(policy.get("applicable") or ()):
            validation_status = _applicability({"methodology_id": methodology_id}, company_type)
            if validation_status == "WEAK_FOR_COMPANY_TYPE":
                conflicts.append({
                    "company_type": company_type,
                    "methodology_id": methodology_id,
                    "canonical_validation": validation_status,
                    "evidence_strength_policy": "APPLICABLE",
                    "requires_methodology_owner_decision": True,
                })
    return tuple(conflicts)


__all__ = ["registry_conflicts"]
