"""Read-only adapter for customer-publishable certified decision authority.

This module only projects values already present in a certified customer
evaluation.  It never calculates or repairs protected investment fields.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _source_record(value: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = _mapping(value.get("Raw") or value.get("raw"))
    return raw or value


def certified_customer_evaluation(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the exact embedded certified evaluation, including nested rows."""
    source = _source_record(value)
    certified = _mapping(source.get("certified_customer_evaluation"))
    if certified:
        return certified
    current = _mapping(source.get("canonical_investment_evaluation"))
    return _mapping(current.get("certified_customer_evaluation"))


def customer_authority(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project certified customer authority, failing closed when unavailable."""
    source = _source_record(value)
    certified = certified_customer_evaluation(source)
    allowed = certified.get("customer_publication_allowed") is True
    decision = _mapping(certified.get("decision"))
    fields = _mapping(certified.get("fields"))
    digests = _mapping(certified.get("digests"))
    fair_value_envelope = _mapping(fields.get("atlas_fair_value"))
    ticker = str(certified.get("ticker") or source.get("ticker") or source.get("Ticker") or "").strip().upper()
    required = (
        decision.get("action"), decision.get("opportunity"),
        decision.get("decision_confidence"), fair_value_envelope.get("value"),
    )
    field_status = str(fair_value_envelope.get("certification_status") or "").upper()
    available = bool(
        allowed and ticker
        and field_status in {"CERTIFIED", "CERTIFIED_HIGH_UNCERTAINTY", "PUBLISHED", "AVAILABLE"}
        and all(item is not None and item != "" for item in required)
    )
    if not available:
        return {
            "status": "RATING_NOT_PUBLISHED", "ticker": ticker,
            "publication_allowed": False, "certified_customer_evaluation": certified,
        }
    publication = _mapping(source.get("publication_certification"))
    evidence_ids = sorted({
        str(item)
        for item in (_mapping(source.get("canonical_investment_evaluation")).get("evidence_ids") or ())
        if item
    })
    return {
        "status": "AVAILABLE",
        "ticker": ticker,
        "publication_allowed": True,
        "action": str(decision["action"]).strip().upper().replace(" ", "_"),
        "fair_value": fair_value_envelope["value"],
        "opportunity": decision["opportunity"],
        "confidence": decision["decision_confidence"],
        "evaluation_snapshot": str(digests.get("evaluation_snapshot_id") or ""),
        "candidate_identity": source.get("candidate_digest") or source.get("candidate_id"),
        "publication_identity": source.get("publication_digest") or publication.get("publication_digest"),
        "source_identity": source.get("source_sha") or publication.get("source_sha"),
        "evidence_ids": evidence_ids,
        "certified_customer_evaluation": certified,
    }


def customer_authority_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical protected customer-authority identity.

    Presentation and enrichment metadata are deliberately excluded.  This
    identity is suitable for proving that Research and Ask are bound to the
    same certified decision without making viewport- or render-time fields
    part of that proof.
    """
    embedded = _mapping(value.get("customer_authority_identity"))
    authority = customer_authority(value)
    source = embedded or authority
    return {
        "ticker": str(source.get("ticker") or authority.get("ticker") or "").strip().upper(),
        "candidate_digest": str(source.get("candidate_digest") or authority.get("candidate_identity") or ""),
        "publication_digest": str(source.get("publication_digest") or authority.get("publication_identity") or ""),
        "source_sha": str(source.get("source_sha") or authority.get("source_identity") or ""),
        "evaluation_snapshot": str(source.get("evaluation_snapshot") or authority.get("evaluation_snapshot") or ""),
        "action": str(source.get("action") or authority.get("action") or ""),
        "fair_value": source.get("fair_value", authority.get("fair_value")),
        "opportunity": source.get("opportunity", authority.get("opportunity")),
        "confidence": source.get("confidence", authority.get("confidence")),
        "evidence_ids": sorted({str(item) for item in (source.get("evidence_ids") or authority.get("evidence_ids") or ()) if item}),
    }


def customer_authority_digest(value: Mapping[str, Any]) -> str:
    payload = customer_authority_identity(value)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def bind_report_to_customer_authority(report: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    """Bind an explanatory Research/Ask report to saved certified authority."""
    authority = customer_authority(source)
    bound = dict(report)
    bound["ticker"] = authority.get("ticker") or bound.get("ticker")
    bound["certified_customer_evaluation"] = authority.get("certified_customer_evaluation") or {}
    bound["customer_authority_identity"] = customer_authority_identity(source)
    context = dict(_mapping(bound.get("research_context")))
    if authority.get("status") == "AVAILABLE":
        context["production_decision"] = {
            "semantic_status": "AVAILABLE",
            "recommendation": authority["action"],
            "opportunity": authority["opportunity"],
            "confidence": authority["confidence"],
            "atlas_fair_value": authority["fair_value"],
            "evaluation_snapshot_id": authority["evaluation_snapshot"],
            "candidate_digest": authority.get("candidate_identity"),
            "publication_digest": authority.get("publication_identity"),
            "source_sha": authority.get("source_identity"),
        }
    else:
        context["production_decision"] = {
            "semantic_status": "DATA_UNAVAILABLE",
            "reason": "RATING_NOT_PUBLISHED",
        }
    bound["research_context"] = context
    return bound


__all__ = [
    "bind_report_to_customer_authority", "certified_customer_evaluation",
    "customer_authority", "customer_authority_digest", "customer_authority_identity",
]
