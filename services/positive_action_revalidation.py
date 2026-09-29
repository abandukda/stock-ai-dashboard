"""Second-stage, non-scoring revalidation for canonical BUY_NOW decisions."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

VERSION = "ATLAS_BUY_NOW_REVALIDATION_V2"

VALUATION_REQUIREMENT_BLOCKERS = {
    "company_type_route_registered": "BUY_NOW_VALUATION_ROUTE_UNREGISTERED",
    "published_methods_professionally_appropriate": "BUY_NOW_VALUATION_METHOD_INAPPROPRIATE",
    "method_professionally_appropriate": "BUY_NOW_VALUATION_METHOD_INAPPROPRIATE",
    "explicit_method_sufficiency": "BUY_NOW_SINGLE_METHOD_SUFFICIENCY_UNAPPROVED",
    "single_method_strong_action_policy_active": "BUY_NOW_SINGLE_METHOD_STRONG_ACTION_POLICY_RETIRED",
    "valuation_confidence_high_support": "BUY_NOW_VALUATION_CONFIDENCE_INSUFFICIENT",
    "scenario_evidence_published": "BUY_NOW_SCENARIO_EVIDENCE_INSUFFICIENT",
    "peer_evidence_certified": "BUY_NOW_PEER_EVIDENCE_INSUFFICIENT",
    "peer_evidence_certified_where_used": "BUY_NOW_PEER_EVIDENCE_INSUFFICIENT",
    "all_bridge_inputs_certified": "BUY_NOW_ACCOUNTING_BRIDGE_INSUFFICIENT",
    "valuation_certification_publishable": "BUY_NOW_VALUATION_CERTIFICATION_INCOMPLETE",
    "no_material_qa_flags": "BUY_NOW_VALUATION_QA_FLAGS_PRESENT",
    "economic_explanation_complete": "BUY_NOW_VALUATION_EXPLANATION_INCOMPLETE",
}


def valuation_sufficiency_blockers(strength: Mapping[str, Any]) -> tuple[str, ...]:
    """Expand the evidence-strength contract into auditable BUY sub-blockers."""
    blockers = []
    method_count = int(_number(strength.get("published_method_count")) or 0)
    if method_count < 2:
        blockers.append("BUY_NOW_METHOD_CORROBORATION_INSUFFICIENT")
    unmet = tuple(strength.get("unmet_requirements") or ())
    for requirement in unmet:
        blocker = VALUATION_REQUIREMENT_BLOCKERS.get(str(requirement))
        if blocker:
            blockers.append(blocker)
    return tuple(dict.fromkeys(blockers))


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_method_corroboration(professional: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    """Count only certified, applicable, canonical same-snapshot methods."""
    applicability = {
        str(item.get("methodology_id") or ""): str(item.get("applicability") or "")
        for item in validation.get("model_applicability") or ()
    }
    valuation_as_of = professional.get("valuation_as_of")
    included: list[str] = []
    excluded: list[dict[str, str]] = []
    for raw in professional.get("models") or ():
        model = dict(raw)
        method_id = str(model.get("methodology_id") or "")
        reason = None
        if model.get("status") != "PUBLISHED":
            reason = "METHOD_NOT_PUBLISHED"
        elif str(model.get("evidence_tier") or "").upper() in {"SHADOW_ONLY", "UNVERIFIED_SHADOW"}:
            reason = "SHADOW_METHOD_EXCLUDED"
        elif model.get("certification_state") not in (None, "CERTIFIED", "CERTIFIED_HIGH_UNCERTAINTY"):
            reason = "METHOD_NOT_CERTIFIED"
        elif applicability.get(method_id) in {"NOT_APPLICABLE", "WEAK_FOR_COMPANY_TYPE"}:
            reason = "METHOD_NOT_APPLICABLE"
        elif model.get("snapshot_identity") and valuation_as_of and model.get("snapshot_identity") != valuation_as_of:
            reason = "STALE_SNAPSHOT_METHOD_EXCLUDED"
        if reason:
            excluded.append({"method_id": method_id, "reason": reason})
        else:
            included.append(method_id)
    return {
        "certified_method_count": len(included),
        "methods_included": included,
        "methods_excluded": excluded,
        "valuation_as_of": valuation_as_of,
    }


def revalidate_buy_now(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    """Recheck exact-snapshot evidence without modifying the canonical Action."""
    action = str(((evaluation.get("guidance") or {}).get("state") or ""))
    if action != "BUY_NOW":
        return {"version": VERSION, "status": "NOT_REQUIRED", "canonical_action": action}
    market = dict(evaluation.get("market_snapshot") or {})
    technical = dict(evaluation.get("technical_confirmation") or {})
    volume = dict(evaluation.get("volume_intelligence") or {})
    fundamentals = dict(evaluation.get("fundamentals") or {})
    risk = dict(evaluation.get("risk") or {})
    trade = dict(evaluation.get("trade_plan") or {})
    valuation = dict(evaluation.get("atlas_valuation") or {})
    professional = dict(valuation.get("professional_valuation_v2") or {})
    validation = dict(evaluation.get("valuation_validation") or {})
    corroboration = canonical_method_corroboration(professional, validation)
    blockers: list[str] = []
    if not market.get("evidence_id") or not market.get("provider_timestamp") or _number(market.get("price")) is None:
        blockers.append("MARKET_SNAPSHOT_NOT_REVALIDATED")
    if market.get("fresh_current_price") is not True and market.get("latest_completed_session_valid") is not True:
        blockers.append("MARKET_FRESHNESS_NOT_REVALIDATED")
    if technical.get("status") != "AVAILABLE" or technical.get("completed_bar") is not True or not technical.get("fingerprint"):
        blockers.append("TECHNICAL_SNAPSHOT_NOT_REVALIDATED")
    if (volume.get("status") != "AVAILABLE" or volume.get("completed_daily_evidence") is not True
            or volume.get("valid_daily_volume_baseline") is not True or not volume.get("evidence_id")):
        blockers.append("VOLUME_NOT_REVALIDATED")
    if fundamentals.get("status") != "AVAILABLE" or not fundamentals.get("evidence_ids"):
        blockers.append("FUNDAMENTALS_NOT_REVALIDATED")
    if risk.get("status") != "AVAILABLE" or not risk.get("as_of"):
        blockers.append("RISK_NOT_REVALIDATED")
    if any(_number(trade.get(key)) is None for key in ("entry_low", "entry_high", "stop_loss")):
        blockers.append("TRADE_PLAN_NOT_REVALIDATED")
    if professional.get("status") != "PUBLISHED" or validation.get("customer_publication_allowed") is not True:
        blockers.append("VALUATION_NOT_REVALIDATED")
    strength = dict(validation.get("valuation_evidence_strength") or professional.get("valuation_evidence_strength") or {})
    if strength:
        # The canonical method bundle is authoritative for count propagation;
        # all other strong-action requirements remain owned by the existing
        # valuation-evidence policy and are not relaxed here.
        strength["published_method_count"] = corroboration["certified_method_count"]
        if corroboration["certified_method_count"] < 2:
            strength["strong_action_eligible"] = False
            unmet = list(strength.get("unmet_requirements") or ())
            if "method_corroboration" not in unmet:
                unmet.append("method_corroboration")
            strength["unmet_requirements"] = unmet
    if strength.get("strong_action_eligible") is not True:
        blockers.append("BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT")
        blockers.extend(valuation_sufficiency_blockers(strength))
    if any(_number(evaluation.get(key)) is None for key in ("opportunity", "decision_confidence", "component_coverage")):
        blockers.append("DECISION_METRICS_NOT_REVALIDATED")
    explanation = dict(professional.get("valuation_explanation") or {})
    if not explanation.get("primary_valuation_driver") or not explanation.get("biggest_valuation_uncertainty"):
        blockers.append("ECONOMIC_EXPLANATION_NOT_REVALIDATED")
    if not (evaluation.get("opportunity_thesis") or (evaluation.get("guidance") or {}).get("opportunity_thesis")):
        blockers.append("ECONOMIC_THESIS_NOT_REVALIDATED")

    diagnostics = dict(professional.get("valuation_diagnostics") or {})
    street = _number(diagnostics.get("street_target_context"))
    base = _number(professional.get("atlas_base_fair_value"))
    divergence = abs(base / street - 1) * 100 if base is not None and street not in (None, 0) else None
    divergence_level = "STANDARD"
    if divergence is not None and divergence > 75:
        divergence_level = "STRONG_NUMERICAL_QA"
        checks = dict(validation.get("checks") or {})
        if any((checks.get(name) or {}).get("status") == "FAIL" for name in ("market_cap_bridge", "ev_bridge", "period_basis")):
            blockers.append("STREET_DIVERGENCE_NUMERICAL_QA_FAILED")
    elif divergence is not None and divergence > 50:
        divergence_level = "SCENARIO_AND_SENSITIVITY_REVIEW"
        if not professional.get("sensitivity") and professional.get("scenario_status") != "PUBLISHED":
            blockers.append("STREET_DIVERGENCE_SCENARIO_REVIEW_MISSING")
    elif divergence is not None and divergence > 25:
        divergence_level = "ENHANCED_ECONOMIC_EXPLANATION"
    digest_payload = {
        "decision_digest": evaluation.get("decision_digest"), "market_evidence_id": market.get("evidence_id"),
        "technical_fingerprint": technical.get("fingerprint"), "volume_evidence_id": volume.get("evidence_id"),
        "valuation_as_of": professional.get("valuation_as_of"), "action": action,
    }
    return {
        "version": VERSION,
        "status": "BUY_NOW_REVALIDATED" if not blockers else "BUY_NOW_PENDING_REVALIDATION",
        "canonical_action": action, "blockers": blockers,
        "source_decision_digest": evaluation.get("decision_digest"),
        "exact_snapshot_digest": hashlib.sha256(json.dumps(digest_payload, sort_keys=True, default=str).encode()).hexdigest(),
        "evidence_as_of": dict(evaluation.get("evidence_as_of") or {}),
        "street_divergence_pct": round(divergence, 2) if divergence is not None else None,
        "street_divergence_review": divergence_level,
        "economic_explanation": explanation,
        "valuation_evidence_strength": strength,
        "canonical_method_corroboration": corroboration,
        "valuation_sufficiency_blockers": valuation_sufficiency_blockers(strength),
        "invalidation_thesis": {"stop_loss": trade.get("stop_loss"), "primary_risk": risk.get("primary_risk")},
    }


__all__ = ["VALUATION_REQUIREMENT_BLOCKERS", "VERSION", "canonical_method_corroboration",
           "revalidate_buy_now", "valuation_sufficiency_blockers"]
