"""
Atlas V103 — Integrated Institutional Pipeline
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from engines.institutional_scoring_engine import score_stock
from engines.confidence_calibration_engine import calibrate_v103_confidence


def _tier(score):
    if score is None:
        return "INCOMPLETE"
    if score >= 90:
        return "ELITE"
    if score >= 84:
        return "EXCEPTIONAL"
    if score >= 76:
        return "HIGH"
    if score >= 68:
        return "GOOD"
    if score >= 58:
        return "AVERAGE"
    return "WEAK"


def _decision(row):
    score = row.get("opportunity_score") or 0
    confidence = row.get("confidence_pct") or 0
    upside = row.get("expected_return_pct")
    coverage = row.get("component_coverage_pct") or 0

    if (
        score >= 86
        and confidence >= 82
        and coverage >= 55
        and upside is not None
        and 10 <= upside <= 60
    ):
        return "BUY_NOW"
    if score >= 72 and confidence >= 68:
        return "ACCUMULATE"
    if score < 48:
        return "AVOID"
    return "MONITOR"


def build_v103_pipeline(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    scored = []

    for raw in rows or []:
        if not isinstance(raw, Mapping):
            continue
        item = score_stock(raw)
        if not item.get("eligible"):
            item["excluded_reason"] = "eligibility_filter"
            scored.append(item)
            continue

        if item.get("opportunity_score") is not None:
            item.update(calibrate_v103_confidence(item))
            item["opportunity_tier"] = _tier(item["opportunity_score"])
            item["action_code"] = _decision(item)

        scored.append(item)

    eligible = [
        row
        for row in scored
        if row.get("eligible")
        and row.get("opportunity_score") is not None
    ]
    eligible.sort(
        key=lambda row: (
            row.get("opportunity_score") or 0,
            row.get("confidence_pct") or 0,
        ),
        reverse=True,
    )

    total = len(eligible)
    for index, row in enumerate(eligible, start=1):
        row["overall_rank"] = index
        row["universe_count"] = total
        percentile = index / total * 100 if total else 100
        row["top_percentile_text"] = (
            f"Top {percentile:.1f}%"
            if percentile < 10
            else f"Top {percentile:.0f}%"
        )

    selected = []
    sector_counts = {}
    for row in eligible:
        if len(selected) >= 12:
            break
        sector = row.get("sector") or "Unknown"
        if sector_counts.get(sector, 0) >= 2:
            continue
        selected.append(row)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    return {
        "version": "V103",
        "all_rows": scored,
        "ranked_candidates": eligible,
        "selected_candidates": selected,
        "summary": {
            "received": len(scored),
            "eligible": len(eligible),
            "selected": len(selected),
            "buy_now": sum(row.get("action_code") == "BUY_NOW" for row in eligible),
            "accumulate": sum(row.get("action_code") == "ACCUMULATE" for row in eligible),
            "monitor": sum(row.get("action_code") == "MONITOR" for row in eligible),
            "excluded_or_incomplete": len(scored) - len(eligible),
        },
    }


__all__ = ["build_v103_pipeline"]
