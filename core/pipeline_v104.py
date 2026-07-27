"""
Atlas V104/V2 — Research Candidate and Investment Committee Pipeline

Compatibility build: preserve the existing V103/V104 scoring, confidence,
ranking, and committee behavior while canonical component details are added
inside score_stock().
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from engines.institutional_scoring_engine import score_stock
from engines.confidence_calibration_engine import (
    calibrate_v103_confidence,
)
from engines.investment_committee_v104 import (
    build_committee_verdict,
)


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


def build_v104_pipeline(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    all_rows = []

    for raw in rows or []:
        if not isinstance(raw, Mapping):
            continue

        item = score_stock(raw)

        if (
            item.get("eligible")
            and item.get("opportunity_score") is not None
        ):
            item.update(calibrate_v103_confidence(item))
            item["opportunity_tier"] = _tier(
                item.get("opportunity_score")
            )
            item.update(build_committee_verdict(item))
            item["action_code"] = item["committee_verdict"]

        all_rows.append(item)

    ranked = [
        row
        for row in all_rows
        if row.get("eligible")
        and row.get("opportunity_score") is not None
    ]
    ranked.sort(
        key=lambda row: (
            row.get("opportunity_score") or 0,
            row.get("confidence_pct") or 0,
        ),
        reverse=True,
    )

    total = len(ranked)
    for index, row in enumerate(ranked, start=1):
        row["overall_rank"] = index
        row["universe_count"] = total
        percentile = index / total * 100 if total else 100
        row["top_percentile_text"] = (
            f"Top {percentile:.1f}%"
            if percentile < 10
            else f"Top {percentile:.0f}%"
        )

    research_candidates = []
    sector_counts = {}

    for row in ranked:
        if len(research_candidates) >= 12:
            break
        sector = row.get("sector") or "Unknown"
        if sector_counts.get(sector, 0) >= 2:
            continue
        research_candidates.append(row)
        sector_counts[sector] = (
            sector_counts.get(sector, 0) + 1
        )

    return {
        "version": "V2-COMPATIBILITY",
        "all_rows": all_rows,
        "ranked_candidates": ranked,
        "research_candidates": research_candidates,
        "selected_candidates": research_candidates,
        "summary": {
            "received": len(all_rows),
            "eligible": len(ranked),
            "research_candidates": len(research_candidates),
            "committee_ready": sum(
                bool(row.get("committee_ready"))
                for row in ranked
            ),
            "buy_now": sum(
                row.get("committee_verdict") == "BUY_NOW"
                for row in ranked
            ),
            "accumulate": sum(
                row.get("committee_verdict") == "ACCUMULATE"
                for row in ranked
            ),
            "monitor": sum(
                row.get("committee_verdict") == "MONITOR"
                for row in ranked
            ),
            "excluded_or_incomplete": (
                len(all_rows) - len(ranked)
            ),
        },
    }


__all__ = ["build_v104_pipeline"]
