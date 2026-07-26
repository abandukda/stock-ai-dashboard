
"""
Atlas V2 Phase 2A — Canonical supporting-data enrichment.

Runs before scoring and again before report assembly so institutional and
political data already present in raw/nested payloads are not ignored.
"""

from __future__ import annotations

from typing import Any, Mapping

from adapters.institutional_adapter_v2 import normalize_institutional_data
from adapters.political_adapter_v2 import normalize_political_data


def enrich_supporting_research_data(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(row)
    institutional = normalize_institutional_data(row)
    political = normalize_political_data(row)

    result["ownership"] = {
        **(
            row.get("ownership")
            if isinstance(row.get("ownership"), Mapping)
            else {}
        ),
        **institutional,
    }
    result["institutional"] = {
        **(
            row.get("institutional")
            if isinstance(row.get("institutional"), Mapping)
            else {}
        ),
        **institutional,
    }
    result["political"] = {
        **(
            row.get("political")
            if isinstance(row.get("political"), Mapping)
            else {}
        ),
        **political,
    }

    for key in (
        "institutional_ownership_pct",
        "institutional_change_pct",
        "institutional_buying",
        "institutional_selling",
        "major_holders",
        "institutional_score",
    ):
        value = institutional.get(key)
        if value not in (None, "", [], {}):
            result[key] = value

    for source_key, target_key in (
        ("political_score", "political_score"),
        ("buyers", "political_buyers"),
        ("sellers", "political_sellers"),
        ("transactions", "political_transactions"),
        ("policy_summary", "political_support_summary"),
        ("regulatory_exposure", "regulatory_exposure"),
        ("export_control_exposure", "export_control_exposure"),
        ("government_contract_exposure", "government_contract_exposure"),
        ("tariff_exposure", "tariff_exposure"),
    ):
        value = political.get(source_key)
        if value not in (None, "", [], {}):
            result[target_key] = value

    result["institutional_data_status"] = institutional.get("status")
    result["political_data_status"] = political.get("status")
    result["political_retrieval_status"] = political.get(
        "retrieval_status"
    )

    return result


__all__ = ["enrich_supporting_research_data"]
