"""Field-level presentation readiness after analyst context validation.

These receipts do not admit data or grant display rights. The customer builder
supplies its already validated families and existing display flag. Downstream
views must not infer readiness of one field from the combined module status.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

CONTRACT = "ATLAS_ANALYST_DISPLAY_READINESS_V1"
CLASSIFICATION = "CONTEXTUAL_NON_SCORING"


def _positive(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except (OverflowError, ValueError, TypeError):
        return False


def build_analyst_display_readiness(*, display_enabled: bool, targets: Mapping[str, Any],
                                   analyst_count: int | None, consensus: str | None,
                                   recommendation_period: str | None) -> dict[str, Any]:
    """Project independently available target and recommendation facts.

    Caller must first apply the existing family/projection admission validators.
    Missing values remain absent. A zero count is evidence of no coverage, not
    an inferred bullish consensus. No certified price/Fair Value is modified.
    """
    enabled = display_enabled is True
    payload = targets.get("payload") if isinstance(targets.get("payload"), Mapping) else {}
    provenance = targets.get("provenance") if isinstance(targets.get("provenance"), Mapping) else {}
    target = payload.get("target_mean")
    target_ready = enabled and _positive(target) and bool(provenance.get("raw_evidence_id"))
    coverage_ready = enabled and type(analyst_count) is int and analyst_count > 0 and bool(consensus)
    coverage_zero = enabled and type(analyst_count) is int and analyst_count == 0
    return {
        "contract": CONTRACT, "classification": CLASSIFICATION, "display_enabled": enabled,
        "rating_authority": "UNCHANGED", "publication_authority": "UNCHANGED",
        "average_target": {
            "status": "DISABLED" if not enabled else "AVAILABLE" if target_ready else "UNAVAILABLE",
            "value": target if target_ready else None,
            "as_of": payload.get("last_updated") if target_ready else None,
            "evidence_ids": (str(provenance["raw_evidence_id"]),) if target_ready else (),
        },
        "recommendation_coverage": {
            "status": "DISABLED" if not enabled else "AVAILABLE" if coverage_ready else
                      "NO_COVERAGE" if coverage_zero else "UNAVAILABLE",
            "count": analyst_count if coverage_ready or coverage_zero else None,
            "consensus": consensus if coverage_ready else None,
            "as_of": recommendation_period if coverage_ready or coverage_zero else None,
        },
    }


def analyst_display_fact(readiness: Any, field: str) -> dict[str, Any]:
    """Read a typed presentation fact; absent/ambiguous receipts fail closed."""
    unavailable = {"status": "UNAVAILABLE"}
    if (not isinstance(readiness, Mapping) or field not in {"average_target", "recommendation_coverage"}
            or readiness.get("contract") != CONTRACT or readiness.get("classification") != CLASSIFICATION
            or readiness.get("rating_authority") != "UNCHANGED"
            or readiness.get("publication_authority") != "UNCHANGED"):
        return unavailable
    fact = readiness.get(field)
    if not isinstance(fact, Mapping):
        return unavailable
    if readiness.get("display_enabled") is not True:
        return {"status": "DISABLED"}
    if fact.get("status") == "UNAVAILABLE":
        return unavailable
    if field == "average_target":
        if (fact.get("status") != "AVAILABLE" or not _positive(fact.get("value"))
                or not isinstance(fact.get("as_of"), str) or not fact["as_of"]
                or not isinstance(fact.get("evidence_ids"), (list, tuple)) or not fact["evidence_ids"]
                or not all(isinstance(item, str) and item.strip() for item in fact["evidence_ids"])):
            return unavailable
    elif fact.get("status") == "NO_COVERAGE":
        if type(fact.get("count")) is not int or fact["count"] != 0 or fact.get("consensus") is not None:
            return unavailable
    elif (fact.get("status") != "AVAILABLE" or type(fact.get("count")) is not int
          or not 0 < fact["count"] <= 2**53 - 1 or not isinstance(fact.get("consensus"), str) or not fact["consensus"]):
        return unavailable
    return dict(fact)


__all__ = ["CONTRACT", "build_analyst_display_readiness", "analyst_display_fact"]
