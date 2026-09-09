"""Second-stage, non-scoring revalidation for canonical BUY_NOW decisions."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

VERSION = "ATLAS_BUY_NOW_REVALIDATION_V1"


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    if strength.get("strong_action_eligible") is not True:
        blockers.append("BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT")
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
        "invalidation_thesis": {"stop_loss": trade.get("stop_loss"), "primary_risk": risk.get("primary_risk")},
    }


__all__ = ["VERSION", "revalidate_buy_now"]
