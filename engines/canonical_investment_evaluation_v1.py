"""Authority-clean canonical evaluation shared by snapshot and on-demand modes."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from engines.atlas_guidance_v1 import evaluate_guidance
from engines.atlas_valuation import AtlasValuationInputs, calculate_atlas_fair_value
from engines.volume_intelligence_v1 import build_volume_intelligence


EVALUATION_VERSION = "CANONICAL_INVESTMENT_EVALUATION_V1"
METHODOLOGY_VERSION = "FOUNDER_GUIDANCE_V1"
THRESHOLD_VERSION = "BULL_RUN_RADAR_V1_PROVISIONAL_LAUNCH"
EVALUATION_MODES = {"SNAPSHOT", "ON_DEMAND"}


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(nested) for key, nested in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _digest(value: Any) -> str:
    payload = json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_canonical_evaluation(
    ticker: str,
    *,
    evaluation_mode: str,
    market_snapshot: Mapping[str, Any],
    technical: Mapping[str, Any],
    fundamentals: Mapping[str, Any],
    risk: Mapping[str, Any],
    trade_plan: Mapping[str, Any] | None = None,
    opportunity: Any = None,
    decision_confidence: Any = None,
    coverage: Any = None,
    valuation_inputs: Mapping[str, Any] | None = None,
    valuation_component_score: Any = None,
    evidence_ids: list[str] | tuple[str, ...] = (),
    positive_action_volume_authority_required: bool = False,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    mode = str(evaluation_mode or "").upper()
    if mode not in EVALUATION_MODES:
        raise ValueError("evaluation_mode must be SNAPSHOT or ON_DEMAND")
    symbol = str(ticker or "").upper().strip()
    if not symbol:
        raise ValueError("ticker is required")

    valuation_source = dict(valuation_inputs or {})
    valuation_source["price"] = market_snapshot.get("price")
    valuation_result = calculate_atlas_fair_value(AtlasValuationInputs.from_row(valuation_source))
    valuation = {
        "status": valuation_result.status,
        "fair_value": valuation_result.fair_value,
        "expected_return": valuation_result.upside_pct,
        "score": valuation_component_score,
        "methodology_version": "ATLAS_VALUATION_V1",
        "input_authority": "CANONICAL_ATLAS_INPUTS_ONLY",
    }
    volume_evidence = dict(technical.get("evidence") or {})
    volume_evidence.update({
        "feed_health": technical.get("feed_health", market_snapshot.get("feed_health")),
        "completed_bar": technical.get("completed_bar", True),
        "breakout_candidate": technical.get("state") == "BREAKOUT_CONFIRMED",
        "as_of": technical.get("as_of"),
    })
    volume = build_volume_intelligence(volume_evidence)
    approved_volume_authority = volume_evidence.get("approved_volume_authority") == "TWELVE_DATA_COMPLETED_DAILY_VOLUME"
    if positive_action_volume_authority_required and not approved_volume_authority:
        # Twelve Data Phase 1 deliberately has no production intraday-volume
        # authority. Persisted/raw volume fields must not leak through here.
        volume = {
            **volume,
            "status": "DATA_UNAVAILABLE",
            "state": "UNAVAILABLE",
            "volume_confirmed": False,
            "relative_volume": None,
            "current_volume": None,
            "reason_codes": ("TIME_ALIGNED_INTRADAY_VOLUME_BASELINE_NOT_IMPLEMENTED",),
        }
    guidance_inputs = {
        "methodology_version": METHODOLOGY_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "market_snapshot": dict(market_snapshot),
        "technical": dict(technical),
        "volume": volume,
        "fundamentals": dict(fundamentals),
        "risk": dict(risk),
        "valuation": valuation,
        "trade_plan": dict(trade_plan or {}),
        "opportunity": opportunity,
        "decision_confidence": decision_confidence,
        "coverage": coverage,
    }
    if positive_action_volume_authority_required:
        guidance_inputs["positive_action_volume_authority_required"] = True
    guidance = evaluate_guidance(guidance_inputs)
    timestamp = evaluated_at or datetime.now(timezone.utc).isoformat()
    evidence_as_of = {
        "market": market_snapshot.get("provider_timestamp"),
        "technical": technical.get("as_of"),
        "fundamentals": fundamentals.get("as_of"),
        "risk": risk.get("as_of"),
    }
    canonical_inputs = {
        "ticker": symbol, "evaluation_mode": mode,
        "market_snapshot": dict(market_snapshot), "technical": dict(technical),
        "fundamentals": dict(fundamentals), "risk": dict(risk),
        "trade_plan": dict(trade_plan or {}), "opportunity": opportunity,
        "decision_confidence": decision_confidence, "coverage": coverage,
        "valuation_inputs": valuation_source, "valuation_component_score": valuation_component_score,
        "evidence_ids": list(evidence_ids), "methodology_version": METHODOLOGY_VERSION,
        "threshold_version": THRESHOLD_VERSION,
    }
    if positive_action_volume_authority_required:
        canonical_inputs["positive_action_volume_authority_required"] = True
    input_digest = _digest(canonical_inputs)
    record = {
        "version": EVALUATION_VERSION,
        "ticker": symbol,
        "evaluation_mode": mode,
        "evaluated_at": timestamp,
        "market_data_as_of": market_snapshot.get("provider_timestamp"),
        "evidence_as_of": evidence_as_of,
        "methodology_version": METHODOLOGY_VERSION,
        "valuation_methodology_version": "ATLAS_VALUATION_V1",
        "technical_threshold_version": THRESHOLD_VERSION,
        "future_calibration_required": True,
        "input_digest": input_digest,
        "market_snapshot": dict(market_snapshot),
        "technical_confirmation": dict(technical),
        "fundamentals": dict(fundamentals),
        "risk": dict(risk),
        "volume_intelligence": volume,
        "atlas_valuation": valuation,
        "opportunity": opportunity,
        "decision_confidence": decision_confidence,
        "component_coverage": coverage,
        "guidance": guidance,
        "actionability": {
            "status": guidance["actionability"],
            "initiating_supported": guidance["actionability"] == "ACTIONABLE",
            "adding_supported": guidance["actionability"] == "ACTIONABLE",
            "reason_codes": guidance["reason_codes"],
        },
        "trade_plan": dict(trade_plan or {}),
        "evidence_ids": list(evidence_ids),
    }
    record["decision_digest"] = _digest({key: value for key, value in record.items() if key != "evaluated_at"})
    return record


__all__ = [
    "EVALUATION_MODES", "EVALUATION_VERSION", "METHODOLOGY_VERSION",
    "THRESHOLD_VERSION", "build_canonical_evaluation",
]
