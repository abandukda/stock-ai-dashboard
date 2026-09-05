"""Bounded on-demand evaluation orchestration with no provider acquisition."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation
from engines.component_builder import build_components
from engines.semantic_fields import scanner_trade_plan
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
    phase1_enabled: bool | None = None,
) -> dict[str, Any]:
    symbol = str(_first(row, "ticker", "Ticker", "symbol") or "").upper()
    phase1 = dict(twelve_data_phase1 or {})
    if phase1:
        from services.live_market.twelve_data_phase1 import twelve_data_enabled
        enabled = twelve_data_enabled() if phase1_enabled is None else bool(phase1_enabled)
        if not enabled:
            phase1 = {}
    phase1_current = phase1.get("current_price") if isinstance(phase1.get("current_price"), Mapping) else {}
    phase1_last_known = phase1.get("last_known_market") if isinstance(phase1.get("last_known_market"), Mapping) else {}
    market_source = (
        phase1_current if phase1_current.get("status") == "AVAILABLE" else
        phase1_last_known if phase1_last_known.get("status") == "AVAILABLE" else
        _market_evidence(row)
    )
    supplied_market = row.get("canonical_market_snapshot") if isinstance(row.get("canonical_market_snapshot"), Mapping) else {}
    market = (
        dict(supplied_market)
        if supplied_market and supplied_market.get("evidence_id") == market_source.get("evidence_id")
        else build_market_snapshot(symbol, market_source)
    )
    daily_contract = phase1.get("canonical_technical_history") if isinstance(phase1.get("canonical_technical_history"), Mapping) else {}
    if bars is None and daily_contract.get("status") == "AVAILABLE":
        try:
            bars = tuple(
                DailyBar(
                    symbol, datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00")),
                    float(item["open"]), float(item["high"]), float(item["low"]),
                    float(item["close"]), float(item["volume"]), bool(item.get("completed", True)),
                )
                for item in daily_contract.get("bars") or ()
            )
        except (KeyError, TypeError, ValueError):
            bars = None
    technical = _technical_contract(row, bars)
    completed_daily_volume = phase1.get("completed_daily_volume") if isinstance(phase1.get("completed_daily_volume"), Mapping) else {}
    if completed_daily_volume.get("authority") is True:
        technical = {
            **technical,
            "evidence": {
                **dict(technical.get("evidence") or {}),
                "confirmation_relative_volume": completed_daily_volume.get("relative_volume"),
                "current_volume": completed_daily_volume.get("current_volume"),
                "average_volume": completed_daily_volume.get("average_volume"),
                "average_dollar_volume": completed_daily_volume.get("average_dollar_volume"),
                "volume_evidence_id": completed_daily_volume.get("evidence_id"),
                "approved_volume_authority": "TWELVE_DATA_COMPLETED_DAILY_VOLUME",
                "completed_daily_evidence": completed_daily_volume.get("completed_daily_evidence", True),
                "valid_daily_volume_baseline": completed_daily_volume.get("valid_daily_volume_baseline", True),
                "volume_statistic": completed_daily_volume.get("statistic", "DAILY_RELATIVE_VOLUME"),
            },
        }
    bar_contract = phase1.get("completed_bars") if isinstance(phase1.get("completed_bars"), Mapping) else {}
    if phase1 and technical.get("status") != "AVAILABLE" and bar_contract.get("confirmation_allowed") is not True:
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
    fundamentals["evidence_ids"] = tuple(row.get("twelve_trial_evidence_ids") or ())
    risk_supplied = row.get("canonical_risk") if isinstance(row.get("canonical_risk"), Mapping) else {}
    risk = dict(risk_supplied) if risk_supplied else {
        "status": "AVAILABLE" if _first(row, "primary_risk", "Primary Risk", "risk_reward") is not None else "DATA_UNAVAILABLE",
        "as_of": _first(row, "risk_as_of", "scan_time"),
        "net_debt_to_ebitda": _first(row, "net_debt_to_ebitda", "Net Debt / EBITDA"),
        "evidence": {
            "drawdown_label": _first(row, "drawdown_label"),
            "volatility_risk": _first(row, "volatility_risk", "volatility_state"),
        },
    }
    decision = (context or {}).get("production_decision") if isinstance((context or {}).get("production_decision"), Mapping) else {}
    # Decision Metrics V1 calculates these inside the canonical evaluator.
    # No legacy scan, rank, analyst, or presentation values are accepted.
    opportunity = confidence = coverage = None
    if isinstance(row.get("canonical_on_demand_trade_plan"), Mapping):
        trade_plan = dict(row["canonical_on_demand_trade_plan"])
    else:
        persisted_plan = scanner_trade_plan(row)
        trade_plan = {
            **persisted_plan,
            "source": "PERSISTED_SCANNER_TRADE_PLAN",
            "as_of": _first(row, "scan_time", "generated_at"),
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
