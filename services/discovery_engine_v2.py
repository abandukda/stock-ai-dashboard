"""Recall-oriented discovery orchestration around the frozen ATLAS methodology.

This module never calculates a pillar, Opportunity, Confidence, valuation, or
Action.  It chooses which inexpensive broad-scan records deserve canonical
evaluation, measures misses after evaluation, and curates certified results.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
import random
from typing import Any, Iterable, Mapping, Sequence

VERSION = "ATLAS_DISCOVERY_ENGINE_V2_1"
CANDIDATE_SIZES = (500, 650, 800, 1000, 1250, 1500)
FULL_EVALUATION_SIZES = (250, 300, 350, 400, 500, 650, 750, 800, 1000, 1100, 1250, 1400, 1500)
ACTION_PRIORITY = {
    "BUY_NOW": 6, "ACCUMULATE": 5, "WAIT_FOR_ENTRY": 4,
    "WAIT_FOR_CONFIRMATION": 3, "DATA_LIMITED": 2, "AVOID": 1,
}


def _number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").strip().upper()


def _growth(value: Any) -> float | None:
    value = _number(value)
    if value is None:
        return None
    return value / 100 if abs(value) > 2 else value


def qualification_channels(row: Mapping[str, Any]) -> list[str]:
    """Return independent, intentionally broad discovery paths.

    Bounds use existing broad-scan observations only.  They are qualification
    predicates, not a replacement score and not a prediction of final Action.
    """
    price = _number(row.get("price") or row.get("current_price"))
    sma20, sma50, sma200 = (_number(row.get(key)) for key in ("sma20", "sma50", "sma200"))
    rsi = _number(row.get("rsi"))
    revenue_growth, earnings_growth = _growth(row.get("revenue_growth")), _growth(row.get("earnings_growth"))
    fcf = _number(row.get("free_cash_flow"))
    margin = _growth(row.get("operating_profit_margin") or row.get("net_profit_margin"))
    forward_pe, ev_ebitda = _number(row.get("forward_pe")), _number(row.get("ev_to_ebitda"))
    high = _number(row.get("high_52w"))
    one_month = _growth(row.get("return_1m_pct"))
    six_month = _growth(row.get("return_6m_pct"))
    channels: list[str] = []

    if ((revenue_growth is not None and revenue_growth >= .08) or
            (earnings_growth is not None and earnings_growth >= .10)) and (margin is None or margin > 0):
        channels.append("QUALITY_GROWTH")
    if (forward_pe is not None and 0 < forward_pe <= 22) or (ev_ebitda is not None and 0 < ev_ebitda <= 14) or (fcf is not None and fcf > 0):
        channels.append("VALUE_RERATING")
    if price and ((sma20 and .94 <= price / sma20 <= 1.04) or (sma50 and .92 <= price / sma50 <= 1.06)):
        channels.append("ATTRACTIVE_ENTRY")
    if price and sma20 and sma50 and price >= sma20 >= sma50 and (sma200 is None or price >= sma200):
        channels.append("TECHNICAL_SETUP")
    if price and high and price / high >= .94 and rsi is not None and 48 <= rsi <= 75:
        channels.append("BREAKOUT")
    if price and sma20 and sma50 and price >= sma20 and price < sma50 and rsi is not None and rsi >= 42:
        channels.append("RECOVERY")
    if earnings_growth is not None and earnings_growth > 0 and revenue_growth is not None and revenue_growth > 0:
        channels.append("ESTIMATE_INFLECTION")
    if fcf is not None and fcf > 0 and (margin is None or margin > 0):
        channels.append("CASH_FLOW_QUALITY")
    if revenue_growth is not None and revenue_growth >= 0 and fcf is not None and fcf > 0 and rsi is not None and 35 <= rsi <= 70:
        channels.append("DEFENSIVE_QUALITY")
    if one_month is not None and six_month is not None and one_month > 0 and six_month > 0:
        channels.append("MOMENTUM_QUALITY")
    return list(dict.fromkeys(channels))


def potential_positive_lane(row: Mapping[str, Any], channels: Sequence[str] | None = None) -> bool:
    """Broad protected lane; deliberately does not recreate Guidance gates."""
    channels = tuple(channels or qualification_channels(row))
    constructive = {"QUALITY_GROWTH", "VALUE_RERATING", "ATTRACTIVE_ENTRY", "TECHNICAL_SETUP", "BREAKOUT", "CASH_FLOW_QUALITY"}
    return len(constructive.intersection(channels)) >= 2 or (
        "ATTRACTIVE_ENTRY" in channels and "TECHNICAL_SETUP" in channels
    )


def decorate_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(row)
    channels = qualification_channels(output)
    output["prescreen_score"] = _number(output.get("raw_conviction_before_normalization") or output.get("conviction") or output.get("score"))
    output["prescreen_channels"] = channels
    output["protected_positive_lane"] = potential_positive_lane(output, channels)
    # Ordering aid only.  It preserves the legacy prescreen signal while
    # rewarding independent paths and completeness; it is never customer score.
    completeness_fields = ("price", "sma20", "sma50", "rsi", "revenue_growth", "earnings_growth", "free_cash_flow", "market_cap")
    completeness = sum(output.get(key) not in (None, "") for key in completeness_fields) / len(completeness_fields)
    legacy = output["prescreen_score"] or 0
    output["medium_stage_score"] = round(legacy + min(len(channels), 5) * 2 + completeness * 5 + (4 if output["protected_positive_lane"] else 0), 4)
    output["discovery_engine_version"] = VERSION
    return output


def select_candidate_pool(rows: Sequence[Mapping[str, Any]], size: int) -> list[dict[str, Any]]:
    decorated = [decorate_candidate(row) for row in rows]
    qualified = [row for row in decorated if row["prescreen_channels"] or (row.get("prescreen_score") or 0) >= 38]
    qualified_ids = {_ticker(row) for row in qualified}
    exploratory = [row for row in decorated if _ticker(row) not in qualified_ids]
    qualified.sort(key=lambda row: (bool(row["protected_positive_lane"]), row["medium_stage_score"], _number(row.get("dollar_volume")) or 0), reverse=True)
    # Ten percent is an explicit false-negative control lane. Half protects
    # liquid sparse-data names; half is stable random-like coverage by ticker
    # digest so QA does not only inspect expected winners.
    exploration_budget = min(len(exploratory), max(0, size // 10))
    liquid = sorted(exploratory, key=lambda row: _number(row.get("dollar_volume")) or 0, reverse=True)
    digest = sorted(exploratory, key=lambda row: hashlib.sha256(_ticker(row).encode()).hexdigest())
    exploration: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in (liquid[:exploration_budget // 2], digest):
        for row in source:
            if _ticker(row) not in seen:
                row["prescreen_channels"] = [*(row.get("prescreen_channels") or ()), "EXPLORATION_CONTROL"]
                exploration.append(row); seen.add(_ticker(row))
            if len(exploration) >= exploration_budget:
                break
        if len(exploration) >= exploration_budget:
            break
    result = qualified[:max(0, size - len(exploration))] + exploration
    result.sort(key=lambda row: (bool(row["protected_positive_lane"]), row["medium_stage_score"], _number(row.get("dollar_volume")) or 0), reverse=True)
    return result[:max(0, size)]


def select_full_evaluation_pool(candidates: Sequence[Mapping[str, Any]], size: int) -> list[dict[str, Any]]:
    """Allocate independent channel lanes before filling by combined ordering."""
    ordered = [dict(row) for row in candidates]
    if size <= 0:
        return []
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    protected = [row for row in ordered if row.get("protected_positive_lane")]
    # V2.1 recall repair: the governed validation sample showed a systemic
    # cluster of BUILD outcomes whose only inexpensive signal was a favorable
    # entry relationship. Preserve the entire entry lane before aggregate fill;
    # this is an OR-based discovery protection, never a final Action rule.
    attractive_entry = [row for row in ordered if "ATTRACTIVE_ENTRY" in (row.get("prescreen_channels") or ())]
    lane_budget = max(1, size // 20)
    by_lane: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        for lane in row.get("prescreen_channels") or ():
            by_lane[lane].append(row)
    for source in (protected, attractive_entry, *(by_lane[key][:lane_budget] for key in sorted(by_lane)), ordered):
        for row in source:
            ticker = _ticker(row)
            if ticker and ticker not in seen:
                selected.append(dict(row)); seen.add(ticker)
            if len(selected) >= size:
                return selected
    return selected


def validation_sample(discarded: Sequence[Mapping[str, Any]], *, near_cutoff: int = 100,
                      random_size: int = 100, seed: str = "ATLAS_DISCOVERY_V2") -> list[dict[str, Any]]:
    near = [dict(row) for row in discarded[:near_cutoff]]
    seen = {_ticker(row) for row in near}
    remainder = [dict(row) for row in discarded[near_cutoff:] if _ticker(row) not in seen]
    stable_seed = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    random_rows = random.Random(stable_seed).sample(remainder, min(random_size, len(remainder)))
    for row in near: row["discovery_validation_cohort"] = "NEAR_CUTOFF"
    for row in random_rows: row["discovery_validation_cohort"] = "RANDOM_CONTROL"
    return near + random_rows


def canonical_action(row: Mapping[str, Any]) -> str:
    return str((((row.get("canonical_investment_evaluation") or {}).get("guidance") or {}).get("state") or "DATA_LIMITED"))


def _metric(row: Mapping[str, Any], key: str) -> float:
    value = (row.get("canonical_investment_evaluation") or {}).get(key)
    if isinstance(value, Mapping):
        value = value.get("score")
    return _number(value) or 0


def certified(row: Mapping[str, Any]) -> bool:
    return bool((row.get("publication_certification") or {}).get("customer_publication_allowed"))


def curate_customer_150(rows: Sequence[Mapping[str, Any]], size: int = 150) -> list[dict[str, Any]]:
    publishable = [dict(row) for row in rows if certified(row)]
    publishable.sort(key=lambda row: (
        ACTION_PRIORITY.get(canonical_action(row), 0), _metric(row, "opportunity"),
        _metric(row, "decision_confidence"), _metric(row, "component_coverage"),
        _number(row.get("relative_rank_score")) or 0,
    ), reverse=True)
    result = publishable[:size]
    for rank, row in enumerate(result, 1):
        row["production_rank"] = rank
        row["discovery_rank"] = rank
        row["full_evaluation_complete"] = True
    return result


def recall_report(retained: Sequence[Mapping[str, Any]], controls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Measure observed validation recall; controls must already be evaluated."""
    retained_ids = {_ticker(row) for row in retained}
    evaluated = [row for row in (*retained, *controls) if (row.get("canonical_investment_evaluation") or {}).get("guidance")]
    definitions = {
        "buy_now": lambda r: certified(r) and canonical_action(r) == "BUY_NOW",
        "build_or_better": lambda r: certified(r) and canonical_action(r) in {"BUY_NOW", "ACCUMULATE"},
        "high_opportunity": lambda r: _metric(r, "opportunity") >= 75,
        "high_confidence": lambda r: _metric(r, "decision_confidence") >= 80,
        "attractive_valuation": lambda r: _metric(r, "valuation_quality") >= 70,
        "technical_opportunity": lambda r: _metric(r, "technical_quality") >= 70,
    }
    metrics: dict[str, Any] = {}
    for name, predicate in definitions.items():
        positives = [row for row in evaluated if predicate(row)]
        retained_positive = sum(_ticker(row) in retained_ids for row in positives)
        metrics[f"{name}_recall"] = round(retained_positive / len(positives), 4) if positives else None
        metrics[f"{name}_positive_sample"] = len(positives)
    misses = []
    for row in controls:
        action = canonical_action(row)
        if certified(row) and action in {"BUY_NOW", "ACCUMULATE"}:
            channels = list(row.get("prescreen_channels") or ())
            if "ATTRACTIVE_ENTRY" in channels:
                root_cause = "CUTOFF_EFFECT"
                reason = "Attractive-entry lane lost to the aggregate full-evaluation cutoff."
            elif not channels:
                root_cause = "MISSING_DISCOVERY_LANE"
                reason = "No governed discovery lane retained the canonical positive outcome."
            else:
                root_cause = "RANKING_COMPRESSION"
                reason = "Qualified discovery evidence ranked below the governed pool cutoff."
            misses.append({"ticker": _ticker(row), "action": action,
                           "severity": "D0" if action == "BUY_NOW" else "D1",
                           "cohort": row.get("discovery_validation_cohort"),
                           "prescreen_channels": channels,
                           "prescreen_score": row.get("prescreen_score"),
                           "medium_stage_score": row.get("medium_stage_score"),
                           "broad_prescan_rank": row.get("broad_prescan_rank"),
                           "cutoff_position": row.get("full_evaluation_rank"),
                           "root_cause": root_cause, "reason_dropped": reason})
    counts = Counter(item["severity"] for item in misses)
    if len(controls) < 200:
        counts["D2"] += 1
    recall_thresholds = {
        "buy_now_recall": 1.0,
        "build_or_better_recall": .95,
        "high_opportunity_recall": .95,
        "technical_opportunity_recall": .95,
    }
    threshold_failures = [
        key for key, minimum in recall_thresholds.items()
        if metrics.get(key) is not None and metrics[key] < minimum
    ]
    if threshold_failures:
        counts["D2"] += 1
    return {"version": VERSION, "evaluated_sample_size": len(evaluated),
            "validation_control_size": len(controls), "metrics": metrics,
            "misses": misses, "severity_counts": {f"D{i}": counts.get(f"D{i}", 0) for i in range(5)},
            "discovery_gate": "FAIL" if counts.get("D0") or len(controls) < 200 or threshold_failures else "PASS",
            "thresholds": recall_thresholds, "threshold_failures": threshold_failures,
            "minimum_validation_sample": 200}


def architecture_experiment(eligible_rows: Sequence[Mapping[str, Any]],
                            evaluated_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Replay governed pool sizes against one canonically evaluated sample."""
    evaluated = {_ticker(row): row for row in evaluated_rows}
    scenarios = []
    for candidate_size in CANDIDATE_SIZES:
        candidate = select_candidate_pool(eligible_rows, candidate_size)
        for full_size in FULL_EVALUATION_SIZES:
            selected = select_full_evaluation_pool(candidate, full_size)
            selected_ids = {_ticker(row) for row in selected}
            retained = [evaluated[ticker] for ticker in selected_ids if ticker in evaluated]
            controls = [row for ticker, row in evaluated.items() if ticker not in selected_ids]
            report = recall_report(retained, controls)
            scenarios.append({
                "candidate_pool_limit": candidate_size, "full_evaluation_limit": full_size,
                "evaluated_overlap": len(retained), "validation_population": len(evaluated),
                "buy_now_recall": report["metrics"]["buy_now_recall"],
                "build_or_better_recall": report["metrics"]["build_or_better_recall"],
                "high_opportunity_recall": report["metrics"]["high_opportunity_recall"],
                "high_confidence_recall": report["metrics"]["high_confidence_recall"],
                "missed_buy_now": report["severity_counts"]["D0"],
                "missed_build": report["severity_counts"]["D1"],
                "discovery_gate": report["discovery_gate"],
            })
    acceptable = [row for row in scenarios if row["missed_buy_now"] == 0 and
                  (row["build_or_better_recall"] is None or row["build_or_better_recall"] >= .95)]
    recommended = min(acceptable, key=lambda row: (row["full_evaluation_limit"], row["candidate_pool_limit"])) if acceptable else None
    return {"version": VERSION, "scenarios": scenarios, "recommended": recommended,
            "confidence_limitation": "Recall is measured on the canonically evaluated governed validation population, not unevaluated securities."}


def funnel_record(*, market_count: int, eligible_count: int, candidate_count: int,
                  full_count: int, customer_count: int, candidate_size: int,
                  full_size: int) -> dict[str, Any]:
    return {"version": VERSION, "market_universe": market_count, "eligible": eligible_count,
            "discovery_candidate_pool": candidate_count, "full_evaluation_pool": full_count,
            "customer_discovery_150": customer_count, "candidate_pool_limit": candidate_size,
            "full_evaluation_limit": full_size}


__all__ = ["ACTION_PRIORITY", "CANDIDATE_SIZES", "FULL_EVALUATION_SIZES", "VERSION",
           "architecture_experiment", "canonical_action", "certified", "curate_customer_150", "decorate_candidate",
           "funnel_record", "potential_positive_lane", "qualification_channels", "recall_report",
           "select_candidate_pool", "select_full_evaluation_pool", "validation_sample"]
