"""
Atlas V102 Canonical Pipeline
"""
from __future__ import annotations
from typing import Any, Iterable, Mapping
from adapters.scanner_adapter import adapt_scanner_rows
from engines.portfolio_manager_engine import calibrate_confidence
import math

def _num(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default

def _component_score(row):
    components = {
        "quality": row.get("quality_score"),
        "financial_health": row.get("financial_health_score"),
        "technical": row.get("technical_score"),
        "valuation": row.get("valuation_score"),
        "analyst": row.get("analyst_score"),
        "institutional": row.get("institutional_score"),
        "policy": row.get("government_policy_score"),
        "policymaker": row.get("policymaker_disclosure_score"),
        "research": row.get("research_completeness_pct"),
    }
    weights = {
        "quality": .18, "financial_health": .14, "technical": .16,
        "valuation": .14, "analyst": .10, "institutional": .10,
        "policy": .07, "policymaker": .03, "research": .08,
    }
    available = {k:_num(v) for k,v in components.items() if _num(v) is not None}
    if len(available) < 4:
        return None, 0.0, components
    weight_total = sum(weights[k] for k in available)
    score = sum(available[k] * weights[k] for k in available) / weight_total
    coverage = len(available) / len(components) * 100.0
    return round(score,1), round(coverage,1), components

def _tier(score):
    if score is None: return "INCOMPLETE"
    if score >= 90: return "ELITE"
    if score >= 82: return "EXCEPTIONAL"
    if score >= 74: return "HIGH"
    if score >= 65: return "GOOD"
    if score >= 55: return "AVERAGE"
    return "WEAK"

def _percentile_text(rank, total):
    if not total:
        return "Under review"
    top = rank / total * 100.0
    if top < .1: return f"Top {top:.2f}%"
    if top < 1: return f"Top {top:.1f}%"
    return f"Top {top:.0f}%"

def build_canonical_pipeline(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    canonical = adapt_scanner_rows(rows)
    eligible = []
    incomplete = []
    for row in canonical:
        score, coverage, components = _component_score(row)
        row["opportunity_score"] = score
        row["component_coverage_pct"] = coverage
        row["component_values"] = components
        if row["eligible"] and score is not None:
            confidence_input = {
                **row,
                "required_pillars_passed_pct": coverage,
            }
            calibrated = calibrate_confidence(confidence_input)
            row["confidence_pct"] = calibrated["confidence_pct"]
            row["confidence_band"] = calibrated["confidence_band"]
            row["confidence_inputs"] = calibrated
            eligible.append(row)
        else:
            incomplete.append(row)

    eligible.sort(
        key=lambda item: (
            item.get("opportunity_score") or 0,
            item.get("confidence_pct") or 0,
        ),
        reverse=True,
    )
    total = len(eligible)
    sector_counts = {}
    for idx, row in enumerate(eligible, start=1):
        row["overall_rank"] = idx
        row["universe_count"] = total
        row["top_percentile_text"] = _percentile_text(idx, total)
        row["opportunity_tier"] = _tier(row.get("opportunity_score"))
        sector = row.get("sector") or "Unknown"
        sector_counts.setdefault(sector, []).append(row)
    for sector, items in sector_counts.items():
        for idx, row in enumerate(items, start=1):
            row["sector_rank"] = idx
            row["sector_count"] = len(items)

    selected = []
    sector_selected = {}
    for row in eligible:
        if len(selected) >= 12:
            break
        sector = row.get("sector") or "Unknown"
        if sector_selected.get(sector, 0) >= 2:
            continue
        if (row.get("opportunity_score") or 0) < 55:
            continue
        selected.append(row)
        sector_selected[sector] = sector_selected.get(sector, 0) + 1
    for idx, row in enumerate(selected, start=1):
        row["portfolio_rank"] = idx

    return {
        "version": "V102_CANONICAL",
        "canonical_rows": canonical,
        "ranked_candidates": eligible,
        "selected_candidates": selected,
        "incomplete_rows": incomplete,
        "summary": {
            "received": len(canonical),
            "eligible": total,
            "selected": len(selected),
            "buy_now": sum(row.get("action_code") == "BUY_NOW" for row in eligible),
            "accumulate": sum(row.get("action_code") == "ACCUMULATE" for row in eligible),
            "monitor": sum(row.get("action_code") == "MONITOR" for row in eligible),
            "excluded_or_incomplete": len(incomplete),
        },
    }

__all__ = ["build_canonical_pipeline"]
