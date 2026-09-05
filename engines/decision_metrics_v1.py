"""Founder-governed six-pillar ATLAS decision metrics.

This module is deterministic and acquisition-free. Missing evidence is never
replaced by a neutral score and contextual evidence never enters the result.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Mapping


METHODOLOGY_VERSION = "ATLAS_DECISION_METRICS_V1"
PILLAR_WEIGHTS = {
    "technical_quality": 25.0,
    "fundamental_quality": 20.0,
    "valuation_quality": 20.0,
    "risk_quality": 15.0,
    "entry_quality": 10.0,
    "volume_quality": 10.0,
}
VALUATION_BREAKPOINTS = ((0.0, 0.0), (5.0, 30.0), (10.0, 50.0), (15.0, 60.0),
                         (20.0, 70.0), (30.0, 82.0), (40.0, 92.0), (50.0, 100.0))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(str(value).replace("$", "").replace(",", "").replace("%", "").rstrip("xX"))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source.get(key) not in (None, "", "Unavailable", "UNAVAILABLE"):
            return source.get(key)
    return None


def _component(name: str, score: float | None, coverage_fraction: float, *,
               status: str, evidence_ids=(), details=None) -> dict[str, Any]:
    weight = PILLAR_WEIGHTS[name]
    available = score is not None and coverage_fraction > 0
    return {
        "status": status if available else "DATA_UNAVAILABLE",
        "score": round(score, 2) if score is not None else None,
        "pillar_weight": weight,
        "coverage_fraction": round(coverage_fraction if available else 0.0, 4),
        "effective_weight": round(weight * coverage_fraction, 2) if available else 0.0,
        "evidence_ids": tuple(str(item) for item in evidence_ids if item),
        "details": dict(details or {}),
    }


def _technical(technical: Mapping[str, Any]) -> dict[str, Any]:
    score = _number(technical.get("score"))
    available = str(technical.get("status") or "").upper() == "AVAILABLE" and score is not None
    return _component("technical_quality", score if available else None, 1.0 if available else 0.0,
                      status="AVAILABLE", evidence_ids=(technical.get("fingerprint"),),
                      details={"state": technical.get("state"), "as_of": technical.get("as_of"),
                               "methodology_version": (technical.get("evidence") or {}).get("model_version")})


def _fundamental(fundamentals: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(fundamentals.get("data") or {})
    families = {
        "revenue": _first(data, "revenue_growth_pct", "revenue"),
        "earnings": _first(data, "eps_growth_pct", "eps", "earnings_growth"),
        "profitability": _first(data, "operating_margin_pct", "gross_margin_pct"),
        "cash_flow": _first(data, "free_cash_flow", "operating_cash_flow"),
        "balance_sheet": _first(data, "current_ratio", "net_debt_to_ebitda", "debt_to_equity"),
    }
    source_status = str(fundamentals.get("status") or "").upper()
    count = 5 if source_status == "AVAILABLE" else sum(_number(value) is not None for value in families.values())
    score = _number(fundamentals.get("score"))
    publishable = score is not None and (source_status == "AVAILABLE" or (source_status == "PARTIAL" and count >= 3))
    fraction = count / 5.0 if publishable else 0.0
    return _component("fundamental_quality", score if publishable else None, fraction,
                      status="AVAILABLE" if count == 5 else "PARTIAL",
                      evidence_ids=tuple(fundamentals.get("evidence_ids") or ()),
                      details={"available_families": tuple(k for k, v in families.items() if _number(v) is not None),
                               "fundamental_subcoverage": round(count / 5.0, 2)})


def valuation_quality(valuation: Mapping[str, Any]) -> dict[str, Any]:
    expected = _number(valuation.get("expected_return"))
    published = str(valuation.get("status") or "").upper() == "PUBLISHED"
    valid = valuation.get("validation_passed", published) is True
    if not (published and valid and _number(valuation.get("fair_value")) is not None and expected is not None):
        return _component("valuation_quality", None, 0.0, status="DATA_UNAVAILABLE")
    if expected <= 0:
        score = 0.0
    elif expected >= 50:
        score = 100.0
    else:
        score = 0.0
        for (x0, y0), (x1, y1) in zip(VALUATION_BREAKPOINTS, VALUATION_BREAKPOINTS[1:]):
            if x0 <= expected <= x1:
                score = y0 + (expected - x0) * (y1 - y0) / (x1 - x0)
                break
    return _component("valuation_quality", score, 1.0, status="AVAILABLE",
                      details={"expected_return": expected})


def _reward_risk(plan: Mapping[str, Any]) -> float | None:
    explicit = _number(_first(plan, "risk_reward", "risk_reward_target_1"))
    if explicit is not None:
        return explicit
    low = _number(plan.get("entry_low")); high = _number(plan.get("entry_high"))
    stop = _number(_first(plan, "stop", "stop_loss"))
    target = _number(_first(plan, "target", "target_1", "trade_target_1"))
    if None in (low, high, stop, target) or not (0 < stop < low <= high < target):
        return None
    return (target - high) / (high - stop)


def _risk(risk: Mapping[str, Any], fundamentals: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(fundamentals.get("data") or {})
    evidence = dict(risk.get("evidence") or {})
    leverage = _number(_first(risk, "net_debt_to_ebitda"))
    if leverage is None:
        leverage = _number(evidence.get("net_debt_to_ebitda"))
    leverage_score = None if leverage is None else (100 if leverage <= 1 else 80 if leverage <= 2 else 60 if leverage <= 3 else 40 if leverage < 4 else 20)
    fcf = _number(_first(data, "free_cash_flow")); ocf = _number(_first(data, "operating_cash_flow"))
    if fcf is not None and ocf is not None:
        cash_score = 100 if fcf > 0 and ocf > 0 else 45 if ocf > 0 and fcf < 0 else 20 if fcf < 0 and ocf < 0 else 70
    elif (fcf is not None and fcf > 0) or (ocf is not None and ocf > 0):
        cash_score = 70
    else:
        cash_score = None
    risk_label = str(_first(risk, "volatility_risk", "drawdown_risk", "risk_level") or
                     _first(evidence, "volatility_risk", "drawdown_risk", "risk_level", "drawdown_label") or "").lower()
    risk_map = {"low": 100, "moderate-low": 80, "low to moderate": 80, "shallow drawdown": 80,
                "moderate": 60, "moderate drawdown": 60, "elevated": 40, "deep drawdown": 40,
                "high": 20, "severe drawdown": 20}
    volatility_score = risk_map.get(risk_label)
    rr = _reward_risk(plan)
    reward_score = None if rr is None else 100 if rr >= 3 else 80 if rr >= 2 else 60 if rr >= 1.5 else 40 if rr >= 1 else 20
    values = ((leverage_score, .30), (cash_score, .25), (volatility_score, .20), (reward_score, .25))
    available_weight = sum(weight for value, weight in values if value is not None)
    score = sum(value * weight for value, weight in values if value is not None) / available_weight if available_weight else None
    return _component("risk_quality", score, available_weight, status="AVAILABLE" if available_weight == 1 else "PARTIAL",
                      details={"balance_sheet_leverage": leverage_score, "cash_flow_earnings": cash_score,
                               "volatility_drawdown": volatility_score, "reward_risk": reward_score,
                               "reward_risk_ratio": rr})


def _entry(plan: Mapping[str, Any], market: Mapping[str, Any], technical: Mapping[str, Any]) -> dict[str, Any]:
    price = _number(market.get("price")); low = _number(plan.get("entry_low")); high = _number(plan.get("entry_high"))
    stop = _number(_first(plan, "stop", "stop_loss")); target = _number(_first(plan, "target", "target_1", "trade_target_1"))
    complete = None not in (low, high, stop, target) and bool(0 < stop < low <= high < target)
    if not complete or price is None:
        return _component("entry_quality", None, 0.0, status="DATA_UNAVAILABLE")
    rr = _reward_risk(plan)
    state = str(technical.get("state") or "").upper(); entry_status = str(plan.get("entry_status") or "").upper()
    if rr is not None and rr < 1.0:
        score = 20
    elif state == "EXTENDED" or entry_status in {"WAIT_FOR_ENTRY", "DO_NOT_CHASE"}:
        score = 35
    elif low <= price <= high:
        score = 100
    elif price < low:
        score = 85
    elif _number(plan.get("do_not_chase")) is not None and price <= _number(plan.get("do_not_chase")):
        score = 60
    else:
        score = 35
    return _component("entry_quality", score, 1.0, status="AVAILABLE",
                      details={"entry_relationship": "INSIDE" if low <= price <= high else "BELOW" if price < low else "ABOVE", "reward_risk_ratio": rr})


def _volume(volume: Mapping[str, Any]) -> dict[str, Any]:
    rvol = _number(volume.get("relative_volume"))
    valid = (str(volume.get("status") or "").upper() == "AVAILABLE" and rvol is not None and rvol >= 0
             and volume.get("completed_daily_evidence") is True
             and volume.get("valid_daily_volume_baseline") is True
             and str(volume.get("feed_health") or "HEALTHY").upper() == "HEALTHY"
             and str(volume.get("statistic") or "DAILY_RELATIVE_VOLUME").upper() == "DAILY_RELATIVE_VOLUME")
    if not valid:
        return _component("volume_quality", None, 0.0, status="DATA_UNAVAILABLE")
    score = 100 if rvol >= 1.4 else 80 if rvol >= 1.2 else 65 if rvol >= 1 else 50 if rvol >= .8 else 30 if rvol >= .6 else 15
    return _component("volume_quality", score, 1.0, status="AVAILABLE",
                      evidence_ids=(volume.get("evidence_id"),), details={"daily_relative_volume": rvol})


def build_decision_metrics(*, technical: Mapping[str, Any], fundamentals: Mapping[str, Any],
                           valuation: Mapping[str, Any], risk: Mapping[str, Any],
                           trade_plan: Mapping[str, Any], volume: Mapping[str, Any],
                           market_snapshot: Mapping[str, Any], evidence_quality: tuple[float, ...] = ()) -> dict[str, Any]:
    pillars = {
        "technical_quality": _technical(technical),
        "fundamental_quality": _fundamental(fundamentals),
        "valuation_quality": valuation_quality(valuation),
        "risk_quality": _risk(risk, fundamentals, trade_plan),
        "entry_quality": _entry(trade_plan, market_snapshot, technical),
        "volume_quality": _volume(volume),
    }
    coverage = round(sum(item["effective_weight"] for item in pillars.values()), 2)
    available = [item for item in pillars.values() if item["score"] is not None]
    opportunity = (round(sum(item["score"] * item["effective_weight"] for item in available) /
                         sum(item["effective_weight"] for item in available), 2)
                   if coverage >= 58 and available else None)
    scores = [item["score"] for item in available]
    agreement = round(max(0.0, min(100.0, 100.0 - 2.0 * statistics.pstdev(scores))), 2) if len(scores) >= 2 else None
    quality = list(evidence_quality)
    if market_snapshot.get("fresh_current_price") is True: quality.append(100.0)
    elif market_snapshot.get("latest_completed_session_valid") is True: quality.append(90.0)
    if str(technical.get("feed_health") or "").upper() == "HEALTHY": quality.append(100.0)
    fund = pillars["fundamental_quality"]
    if fund["score"] is not None: quality.append(100.0 * fund["coverage_fraction"])
    if pillars["valuation_quality"]["score"] is not None: quality.append(100.0)
    evidence_quality_score = round(statistics.fmean(quality), 2) if quality else None
    confidence = (round(.60 * coverage + .25 * agreement + .15 * evidence_quality_score, 2)
                  if len(available) >= 3 and coverage >= 58 and agreement is not None and evidence_quality_score is not None else None)
    return {
        "decision_metrics_methodology": METHODOLOGY_VERSION,
        **pillars,
        "opportunity": opportunity,
        "component_coverage": coverage,
        "decision_confidence": confidence,
        "cross_component_agreement": agreement,
        "evidence_quality": evidence_quality_score,
        "available_core_pillars": len(available),
    }


__all__ = ["METHODOLOGY_VERSION", "PILLAR_WEIGHTS", "build_decision_metrics", "valuation_quality"]
