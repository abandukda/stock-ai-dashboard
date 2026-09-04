"""Bounded on-demand evaluation orchestration with no provider acquisition."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation
from engines.component_builder import build_components
from services.canonical_market_snapshot import build_market_snapshot
from services.live_market.models import FeedHealth, SecurityType, TechnicalState
from services.technical_intelligence.engine import DailyBar, TechnicalIntelligenceEngine


POSITIVE_GUIDANCE = {"BUY_NOW", "ACCUMULATE"}
DOWNGRADE_STATES = {"AVOID", "WAIT_FOR_ENTRY", "WAIT_FOR_CONFIRMATION", "DATA_LIMITED"}


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, "", "Unavailable"):
            return row.get(key)
    return None


def _technical_contract(
    row: Mapping[str, Any], bars: Sequence[DailyBar] | None,
) -> dict[str, Any]:
    if bars:
        analysis = TechnicalIntelligenceEngine().evaluate(
            bars, security_type=SecurityType.STOCK, feed_health=FeedHealth.HEALTHY,
        )
        return {
            "status": "AVAILABLE" if not analysis.result.evidence.get("fail_closed_reason") else "DATA_UNAVAILABLE",
            "state": analysis.result.new_state.value,
            "score": analysis.result.score,
            "as_of": analysis.result.event_timestamp.isoformat(),
            "feed_health": analysis.result.feed_health.value,
            "completed_bar": bool(bars[-1].completed),
            "evidence": dict(analysis.result.evidence),
            "fingerprint": analysis.result.fingerprint,
        }
    supplied = row.get("canonical_technical") if isinstance(row.get("canonical_technical"), Mapping) else {}
    return dict(supplied) if supplied else {
        "status": "DATA_UNAVAILABLE", "state": "UNAVAILABLE", "score": None,
        "as_of": None, "feed_health": "UNAVAILABLE", "completed_bar": False,
        "evidence": {},
    }


def _market_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    supplied = row.get("canonical_market_snapshot")
    if isinstance(supplied, Mapping):
        return dict(supplied)
    timestamp = _first(row, "price_as_of", "quote_timestamp", "scan_time", "generated_at")
    return {
        "price": _first(row, "current_price", "price", "Price"),
        "provider": _first(row, "quote_source", "price_source") or "PERSISTED_SNAPSHOT",
        "provider_timestamp": timestamp,
        "received_timestamp": timestamp,
        "source_type": "LAST_KNOWN",
        "stale": True,
        "feed_health": "DEGRADED",
    }


def evaluate_on_demand(
    row: Mapping[str, Any], *, context: Mapping[str, Any] | None = None,
    bars: Sequence[DailyBar] | None = None, previous_evaluation: Mapping[str, Any] | None = None,
    twelve_data_phase1: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = str(_first(row, "ticker", "Ticker", "symbol") or "").upper()
    phase1 = dict(twelve_data_phase1 or {})
    if phase1:
        from services.live_market.twelve_data_phase1 import twelve_data_enabled
        if not twelve_data_enabled():
            phase1 = {}
    market_source = phase1.get("current_price") if isinstance(phase1.get("current_price"), Mapping) else _market_evidence(row)
    market = build_market_snapshot(symbol, market_source)
    technical = _technical_contract(row, bars)
    bar_contract = phase1.get("completed_bars") if isinstance(phase1.get("completed_bars"), Mapping) else {}
    if phase1 and bar_contract.get("confirmation_allowed") is not True:
        technical = {
            **technical, "status": "DATA_UNAVAILABLE", "completed_bar": False,
            "feed_health": "DEGRADED",
            "evidence": {
                **dict(technical.get("evidence") or {}),
                "bar_quality_reason_codes": tuple(bar_contract.get("reason_codes") or ()),
                "bar_gap_metadata": tuple(bar_contract.get("gap_metadata") or ()),
            },
        }
    elif phase1 and bar_contract.get("latest_completed_bar"):
        latest = dict(bar_contract["latest_completed_bar"])
        technical = {
            **technical, "completed_bar": True, "feed_health": "HEALTHY",
            "as_of": latest.get("timestamp"),
            "evidence": {**dict(technical.get("evidence") or {}), "phase1_bar_quality": "VALIDATED"},
        }
    components = build_components(row)
    fundamentals = dict(components.get("fundamentals") or {})
    risk_supplied = row.get("canonical_risk") if isinstance(row.get("canonical_risk"), Mapping) else {}
    risk = dict(risk_supplied) if risk_supplied else {
        "status": "AVAILABLE" if _first(row, "primary_risk", "Primary Risk", "risk_reward") is not None else "DATA_UNAVAILABLE",
        "as_of": _first(row, "risk_as_of", "scan_time"),
    }
    decision = (context or {}).get("production_decision") if isinstance((context or {}).get("production_decision"), Mapping) else {}
    # Only explicit canonical on-demand values are accepted. Scan Conviction,
    # analyst support and persisted production-decision outputs are not fallbacks.
    opportunity = row.get("canonical_on_demand_opportunity")
    confidence = row.get("canonical_on_demand_decision_confidence")
    coverage = row.get("canonical_on_demand_component_coverage")
    trade_plan = row.get("canonical_on_demand_trade_plan") if isinstance(row.get("canonical_on_demand_trade_plan"), Mapping) else {
        "entry_low": decision.get("entry_low"), "entry_high": decision.get("entry_high"),
        "stop": decision.get("stop"), "target": decision.get("decision_target"),
        "target_1": decision.get("trade_target_1"), "target_2": decision.get("trade_target_2"),
    }
    evidence_ids = [
        evidence_id for ids in ((context or {}).get("evidence_registry") or {}).values()
        for evidence_id in (ids or [])
    ]
    evaluation = build_canonical_evaluation(
        symbol, evaluation_mode="ON_DEMAND", market_snapshot=market,
        technical=technical, fundamentals=fundamentals, risk=risk,
        trade_plan=trade_plan, opportunity=opportunity,
        decision_confidence=confidence, coverage=coverage,
        valuation_inputs=row.get("canonical_valuation_inputs") if isinstance(row.get("canonical_valuation_inputs"), Mapping) else row,
        valuation_component_score=row.get("canonical_valuation_component_score"),
        evidence_ids=evidence_ids,
        positive_action_volume_authority_required=bool(phase1),
    )
    return apply_guidance_hysteresis(previous_evaluation, evaluation)


def apply_guidance_hysteresis(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> dict[str, Any]:
    if not previous:
        return dict(current)
    prior_state = str((previous.get("guidance") or {}).get("state") or "")
    current_state = str((current.get("guidance") or {}).get("state") or "")
    if current_state in DOWNGRADE_STATES:
        return dict(current)
    if current_state not in POSITIVE_GUIDANCE or prior_state == current_state:
        return dict(current)
    completed = bool((current.get("technical_confirmation") or {}).get("completed_bar"))
    stable_digest = current.get("input_digest") == previous.get("candidate_upgrade_digest")
    if completed and stable_digest:
        return dict(current)
    held = dict(current)
    held["candidate_upgrade_digest"] = current.get("input_digest")
    held["guidance"] = {
        **dict(current.get("guidance") or {}),
        "state": prior_state or "WAIT_FOR_CONFIRMATION",
        "actionability": "NOT_ACTIONABLE",
        "reason_codes": ("POSITIVE_UPGRADE_CONFIRMATION_PENDING",),
    }
    held["actionability"] = {
        "status": "NOT_ACTIONABLE", "initiating_supported": False,
        "adding_supported": False, "reason_codes": ("POSITIVE_UPGRADE_CONFIRMATION_PENDING",),
    }
    return held


__all__ = ["apply_guidance_hysteresis", "evaluate_on_demand"]
