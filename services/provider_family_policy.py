"""Central family/consumer permissions for provider evidence."""
from __future__ import annotations

from typing import Any

from services.provider_domain_contracts import DatasetFamily, GovernedRecord, UsePermission


FAMILY_POLICY_VERSION = "ATLAS_PROVIDER_FAMILY_POLICY_V1"

FAMILY_PERMISSIONS = {
    DatasetFamily.CANONICAL_QUANTITATIVE: {
        "shadow": True, "context": False, "live_display": False,
        "certified_calculation": "ONLY_AFTER_CERTIFICATION",
    },
    DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE: {
        "shadow": True, "context": True, "live_display": False,
        "certified_calculation": False,
    },
    DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE: {
        "shadow": True, "context": True, "live_display": False,
        "certified_calculation": False,
    },
    DatasetFamily.LIVE_DISPLAY_ONLY: {
        "shadow": True, "context": False, "live_display": "ONLY_IF_LICENSED",
        "certified_calculation": False,
    },
    DatasetFamily.CERTIFIED_ANALYTICAL: {
        "shadow": False, "context": True, "live_display": True,
        "certified_calculation": True,
    },
}

FORBIDDEN_CERTIFIED_INPUT_FAMILIES = frozenset({
    DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE,
    DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
    DatasetFamily.LIVE_DISPLAY_ONLY,
})


def assert_family_not_certified_input(family: DatasetFamily) -> None:
    if family in FORBIDDEN_CERTIFIED_INPUT_FAMILIES:
        raise PermissionError(f"{family.value} cannot feed certified calculations")


_CUSTOMER_CONTEXT_FIELDS = frozenset({
    "consensus", "rating_distribution", "recent_actions", "estimate_context",
    "headline", "article_timestamp", "article_publisher", "filing_type",
    "filing_date", "ownership_summary", "insider_summary", "profile_summary",
})


def bounded_customer_context(record: GovernedRecord) -> dict[str, Any]:
    """Project only explicitly licensed context; raw payloads never pass through."""
    if record.provenance.display_permission not in {UsePermission.CONTEXT_ONLY, UsePermission.DISPLAY_ONLY}:
        return {"semantic_status": "DATA_UNAVAILABLE"}
    return {
        "semantic_status": "AVAILABLE",
        "provider": record.provenance.provider,
        "evidence_id": record.provenance.raw_evidence_id,
        "as_of": record.provenance.source_timestamp or record.provenance.capture_timestamp,
        **{key: value for key, value in record.payload.items() if key in _CUSTOMER_CONTEXT_FIELDS},
    }


__all__ = ["FAMILY_PERMISSIONS", "FAMILY_POLICY_VERSION", "FORBIDDEN_CERTIFIED_INPUT_FAMILIES", "assert_family_not_certified_input", "bounded_customer_context"]
