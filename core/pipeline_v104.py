
"""
Atlas V104/V2 — Research Candidate and Investment Committee Pipeline

Phase 2A enriches institutional and political fields before scoring so those
components are derived from ownership and transaction data when available.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from adapters.research_data_adapter_v2 import (
    enrich_supporting_research_data,
)
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

        enriched_raw = enrich_supporting_research_data(raw)
        item = score_stock(enriched_raw)

        # score_stock preserves its full input under raw. Re-attach normalized
        # sections at top level so the V2 report does not need to rediscover
        # them from nested provider fields.
        item.update(
            {
                key: value
                for key, value in enriched_raw.items()
                if key in {
                    "ownership",
                    "institutional",
                    "political",
                    "institutional_ownership_pct",
                    "institutional_change_pct",
                    "institutional_buying",
                    "institutional_selling",
                    "major_holders",
                    "institutional_score",
                    "political_score",
                    "political_buyers",
                    "political_sellers",
                    "political_transactions",
                    "political_support_summary",
                    "regulatory_exposure",
                    "export_control_exposure",
                    "government_contract_exposure",
                    "tariff_exposure",
                    "institutional_data_status",
                    "political_data_status",
                    "political_retrieval_status",
                }
            }
        )

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
        "version": "V2-PHASE2A",
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
