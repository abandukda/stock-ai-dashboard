"""Presentation-only Home story built from immutable production artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from engines.atlas_guidance_v1 import founder_guidance_v1_enabled
from engines.research_context import build_production_decision
from engines.semantic_fields import analyst_consensus, canonical_atlas_fair_value, atlas_valuation_status, number
from services.on_demand_evaluation_service import evaluate_on_demand


HOME_GUIDANCE_STORY_VERSION = "HOME_GUIDANCE_VNEXT_V1"
GUIDANCE_GROUPS = (
    ("Actionable Now", {"BUY_NOW", "ACCUMULATE"}),
    ("Getting Close", {"WAIT_FOR_CONFIRMATION", "WAIT_FOR_ENTRY"}),
    ("Risk / Avoid", {"AVOID"}),
    ("Data Limited", {"DATA_LIMITED"}),
)

HOME_FIELD_AUTHORITY = {
    "production_rank": "market_full_scan.json immutable file position",
    "guidance": "CANONICAL_INVESTMENT_EVALUATION_V1.guidance",
    "actionability": "CANONICAL_INVESTMENT_EVALUATION_V1.actionability",
    "opportunity": "CANONICAL_INVESTMENT_EVALUATION_V1.opportunity",
    "decision_confidence": "CANONICAL_INVESTMENT_EVALUATION_V1.decision_confidence",
    "scan_conviction": "persisted Full Scan conviction",
    "atlas_fair_value": "ATLAS_VALUATION_V1 published value",
    "atlas_expected_return": "ATLAS_VALUATION_V1 published expected return",
    "technical_state": "canonical technical evaluation state",
    "volume_state": "ATLAS_VOLUME_INTELLIGENCE_V1 state",
    "recovery_score": "recovery_scan.json exact-ticker row",
    "analyst_consensus": "persisted analyst consensus family",
    "trade_plan": "canonical evaluation trade_plan",
}


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("rows", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
    return []


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("Ticker") or row.get("symbol") or "").strip().upper()


def _present(value: Any) -> bool:
    return value is not None and value != "" and not isinstance(value, (Mapping, list, tuple, set))


def _technical_status(evaluation: Mapping[str, Any]) -> tuple[str, str]:
    technical = evaluation.get("technical_confirmation") if isinstance(evaluation.get("technical_confirmation"), Mapping) else {}
    return str(technical.get("state") or "UNAVAILABLE"), str(technical.get("status") or "DATA_UNAVAILABLE")


def _reason_copy(code: str) -> str:
    copy = {
        "CURRENT_MARKET_EVIDENCE_UNAVAILABLE": "Fresh market evidence is required.",
        "TECHNICAL_STRUCTURE_UNAVAILABLE": "Canonical technical confirmation is required.",
        "PRICE_EVIDENCE_UNAVAILABLE": "A valid approved price observation is required.",
        "BASIC_FUNDAMENTALS_UNAVAILABLE": "Basic canonical fundamentals are required.",
        "RISK_EVIDENCE_UNAVAILABLE": "Canonical risk evidence is required.",
        "BREAKOUT_VOLUME_NOT_CONFIRMED": "Completed-bar volume confirmation is required.",
        "CANONICAL_OPPORTUNITY_UNAVAILABLE": "Canonical Opportunity must be published.",
        "DECISION_CONFIDENCE_UNAVAILABLE": "Decision Confidence must be published.",
        "TRADE_PLAN_INCOMPLETE": "A complete canonical trade plan is required.",
        "VALUATION_CONFIRMATION_UNAVAILABLE": "Published Atlas valuation confirmation is required.",
        "PRICE_ABOVE_ENTRY_RANGE": "Price must return to an approved entry range.",
        "TECHNICAL_STATE_EXTENDED": "Technical extension must normalize.",
    }
    return copy.get(str(code), str(code).replace("_", " ").capitalize() + ".")


def _evidence_health(evaluation: Mapping[str, Any]) -> str:
    statuses = []
    for key in ("fundamentals", "risk"):
        item = evaluation.get(key) if isinstance(evaluation.get(key), Mapping) else {}
        statuses.append(str(item.get("status") or "DATA_UNAVAILABLE"))
    technical = evaluation.get("technical_confirmation") if isinstance(evaluation.get("technical_confirmation"), Mapping) else {}
    statuses.append(str(technical.get("status") or "DATA_UNAVAILABLE"))
    if statuses and all(status == "AVAILABLE" for status in statuses):
        return "COMPLETE"
    if any(status in {"AVAILABLE", "PARTIAL"} for status in statuses):
        return "PARTIAL"
    return "LIMITED"


def build_home_guidance_candidate(
    row: Mapping[str, Any], *, production_rank: int,
    recovery_row: Mapping[str, Any] | None = None,
    current_evaluation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one Home card without ranking or decision recalculation."""
    ticker = _ticker(row)
    production_decision = build_production_decision(row)
    evaluation = dict(current_evaluation or evaluate_on_demand(
        row, context={"production_decision": production_decision, "evidence_registry": {}},
    ))
    guidance = evaluation.get("guidance") if isinstance(evaluation.get("guidance"), Mapping) else {}
    actionability = evaluation.get("actionability") if isinstance(evaluation.get("actionability"), Mapping) else {}
    valuation = evaluation.get("atlas_valuation") if isinstance(evaluation.get("atlas_valuation"), Mapping) else {}
    valuation_status = str(valuation.get("status") or atlas_valuation_status(row) or "DATA_UNAVAILABLE")
    fair_value = valuation.get("fair_value") if valuation_status == "PUBLISHED" else None
    expected_return = valuation.get("expected_return") if valuation_status == "PUBLISHED" and fair_value is not None else None
    street = analyst_consensus(row)
    price = number(row.get("current_price") if row.get("current_price") is not None else row.get("price"))
    street_upside = (
        round(((street["mean"] / price) - 1) * 100, 1)
        if street.get("mean") is not None and price is not None and price > 0 else None
    )
    reasons = tuple(str(item) for item in guidance.get("reason_codes") or ())
    technical_state, technical_status = _technical_status(evaluation)
    volume = evaluation.get("volume_intelligence") if isinstance(evaluation.get("volume_intelligence"), Mapping) else {}
    risk = evaluation.get("risk") if isinstance(evaluation.get("risk"), Mapping) else {}
    fundamentals = evaluation.get("fundamentals") if isinstance(evaluation.get("fundamentals"), Mapping) else {}
    recovery = dict(recovery_row or {})
    company = row.get("company") or row.get("company_name") or row.get("name") or ticker
    return {
        "ticker": ticker,
        "company": str(company),
        "production_rank": int(production_rank),
        "guidance": str(guidance.get("state") or "DATA_LIMITED"),
        "guidance_status": str(guidance.get("status") or "DATA_UNAVAILABLE"),
        "actionability": str(actionability.get("status") or guidance.get("actionability") or "UNAVAILABLE"),
        "opportunity": evaluation.get("opportunity"),
        "decision_confidence": evaluation.get("decision_confidence"),
        "scan_conviction": number(row.get("conviction") if row.get("conviction") is not None else row.get("conviction_score")),
        "atlas_fair_value": fair_value,
        "atlas_valuation_status": valuation_status,
        "atlas_expected_return": expected_return,
        "atlas_expected_return_status": "AVAILABLE" if expected_return is not None else "DATA_UNAVAILABLE",
        "technical_state": technical_state,
        "technical_status": technical_status,
        "volume_state": str(volume.get("state") or "UNAVAILABLE"),
        "volume_status": str(volume.get("status") or "DATA_UNAVAILABLE"),
        "fundamentals_status": str(fundamentals.get("status") or "DATA_UNAVAILABLE"),
        "risk_status": str(risk.get("status") or "DATA_UNAVAILABLE"),
        "trade_plan_status": "AVAILABLE" if (evaluation.get("trade_plan") or {}) else "DATA_UNAVAILABLE",
        "reason_codes": reasons,
        "why_atlas": tuple(_reason_copy(code) for code in reasons[:3]),
        "what_changes_guidance": tuple(_reason_copy(code) for code in reasons[:3]),
        "evidence_health": _evidence_health(evaluation),
        "methodology_version": evaluation.get("methodology_version"),
        "evaluation_timestamp": evaluation.get("evaluated_at"),
        "market_source_type": str((evaluation.get("market_snapshot") or {}).get("source_type") or "UNAVAILABLE"),
        "market_customer_label": str((evaluation.get("market_snapshot") or {}).get("customer_label") or "Market evidence unavailable"),
        "trade_plan": dict(evaluation.get("trade_plan") or {}),
        "wall_street": {
            "rating": row.get("recommendation_key"), "analyst_count": street.get("count"),
            "mean_target": street.get("mean"), "low_target": street.get("low"),
            "high_target": street.get("high"), "implied_upside": street_upside,
            "target_actions": tuple(row.get("phase1_target_actions") or ()),
        },
        "recovery": {
            "score": recovery.get("recovery_score"),
            "state": recovery.get("recovery_label") or recovery.get("recovery_state"),
            "reason": recovery.get("recovery_rebound_reason") or recovery.get("recovery_thesis"),
            "snapshot_timestamp": recovery.get("scan_time") or recovery.get("generated_at"),
        },
        "production_decision": dict(production_decision),
        "evaluation": evaluation,
        "presentation_mode": "ACTIVE" if founder_guidance_v1_enabled() and current_evaluation is not None else "PREVIEW",
    }


def build_home_guidance_story(
    full_scan_payload: Any, recovery_payload: Any, *, watchlist_tickers: Iterable[str] = (),
    current_evaluations: Mapping[str, Mapping[str, Any]] | None = None,
    scan_timestamp: Any = None,
) -> dict[str, Any]:
    full_rows = _rows(full_scan_payload)
    recovery_rows = {_ticker(row): row for row in _rows(recovery_payload) if _ticker(row)}
    evaluations = {str(key).upper(): value for key, value in (current_evaluations or {}).items()}
    cards = [
        build_home_guidance_candidate(
            row, production_rank=index, recovery_row=recovery_rows.get(_ticker(row)),
            current_evaluation=evaluations.get(_ticker(row)),
        )
        for index, row in enumerate(full_rows, start=1)
        if _ticker(row)
    ]
    groups = [
        {"title": title, "states": tuple(sorted(states)), "cards": [card for card in cards if card["guidance"] in states]}
        for title, states in GUIDANCE_GROUPS
    ]
    watched = {str(value).strip().upper() for value in watchlist_tickers if str(value).strip()}
    recovery_cards = [card for card in cards if card["recovery"]["score"] is not None]
    timestamp = scan_timestamp or next((row.get("scan_time") or row.get("generated_at") for row in full_rows if row.get("scan_time") or row.get("generated_at")), None)
    active = founder_guidance_v1_enabled() and bool(evaluations)
    return {
        "version": HOME_GUIDANCE_STORY_VERSION,
        "mode": "ACTIVE" if active else "PREVIEW",
        "title": "ATLAS Today",
        "status_label": "Current ATLAS Guidance" if active else "Founder Guidance Preview",
        "freshness_label": "Snapshot Guidance — based on latest available ATLAS evidence",
        "scan_timestamp": timestamp,
        "candidate_count": len(cards),
        "groups": groups,
        "cards": cards,
        "recovery_cards": recovery_cards,
        "watchlist_cards": [card for card in cards if card["ticker"] in watched],
        "technical_cards": [card for card in cards if card["technical_status"] == "AVAILABLE"],
        "what_changed": {"status": "DATA_UNAVAILABLE", "message": "What Changed is not yet available for this evaluation snapshot."},
        "field_authority": dict(HOME_FIELD_AUTHORITY),
    }


__all__ = [
    "GUIDANCE_GROUPS", "HOME_FIELD_AUTHORITY", "HOME_GUIDANCE_STORY_VERSION",
    "build_home_guidance_candidate", "build_home_guidance_story",
]
