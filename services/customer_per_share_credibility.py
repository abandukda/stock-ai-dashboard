"""Fail-closed projection of filing-reported diluted EPS and share bases."""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT = "ATLAS_CUSTOMER_PER_SHARE_CREDIBILITY_V1"
EPS_CONCEPTS = {"EarningsPerShareDiluted", "us-gaap_EarningsPerShareDiluted"}
SHARE_CONCEPTS = {
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding",
}


def _periods(presentation: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(p["accession"]): p for p in presentation.get("periods") or []}


def _rows(presentation: Mapping[str, Any], concepts: set[str]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in (presentation.get("statements") or {}).get("INCOME_STATEMENT", [])
        if row.get("concept") in concepts
    ]


def _cell_by_accession(rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        for cell in row.get("cells") or []:
            if cell.get("status") == "AVAILABLE":
                result[str(cell["accession"])] = {"row": row, "cell": cell}
    return result


def project_per_share_credibility(
    annual_presentation: Mapping[str, Any],
    *,
    corporate_action_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project filing facts without silently normalizing historical share bases.

    A numeric zero is an available reported value. Missing facts remain unavailable.
    Split adjustment is never inferred from magnitude discontinuities.
    """
    if annual_presentation.get("contract") != "ATLAS_G6_ANNUAL_STATEMENT_PRESENTATION_V1":
        raise ValueError("ANNUAL_PRESENTATION_CONTRACT_MISMATCH")
    periods = _periods(annual_presentation)
    eps = _cell_by_accession(_rows(annual_presentation, EPS_CONCEPTS))
    shares = _cell_by_accession(_rows(annual_presentation, SHARE_CONCEPTS))
    proven = bool(
        corporate_action_evidence
        and corporate_action_evidence.get("status") == "CERTIFIED"
        and corporate_action_evidence.get("ticker") == annual_presentation.get("ticker")
        and corporate_action_evidence.get("source_sha256")
    )
    records = []
    prior_share_value: float | int | None = None
    for accession, period in sorted(periods.items(), key=lambda item: str(item[1].get("fiscal_period_end"))):
        eps_item, share_item = eps.get(accession), shares.get(accession)
        eps_cell = eps_item and eps_item["cell"]
        share_cell = share_item and share_item["cell"]
        eps_value = eps_cell.get("value") if eps_cell else None
        share_value = share_cell.get("value") if share_cell else None
        discontinuity = bool(
            prior_share_value not in (None, 0)
            and share_value not in (None, 0)
            and (float(share_value) / float(prior_share_value) >= 3 or float(share_value) / float(prior_share_value) <= 1 / 3)
        )
        records.append({
            "fiscal_year": period.get("fiscal_year"),
            "period_start": period.get("fiscal_period_start"),
            "period_end": period.get("fiscal_period_end"),
            "filed_date": period.get("filed_date"),
            "accepted_date": period.get("accepted_date"),
            "accession": accession,
            "diluted_eps": {
                "status": "AVAILABLE" if eps_cell else "UNAVAILABLE",
                "value": eps_value,
                "zero_semantics": "REPORTED_ZERO" if eps_cell and eps_value == 0 else None,
                "unit": eps_item["row"].get("unit") if eps_item else {"canonical": "USD_PER_SHARE"},
                "fact_id": eps_cell.get("fact_id") if eps_cell else None,
                "provenance": eps_cell.get("provenance") if eps_cell else None,
                "reason": None if eps_cell else "FIELD_NOT_REPORTED_FOR_PERIOD",
            },
            "diluted_weighted_average_shares": {
                "status": "AVAILABLE" if share_cell else "UNAVAILABLE",
                "value": share_value,
                "zero_semantics": "REPORTED_ZERO" if share_cell and share_value == 0 else None,
                "unit": share_item["row"].get("unit") if share_item else {"canonical": "SHARES"},
                "fact_id": share_cell.get("fact_id") if share_cell else None,
                "provenance": share_cell.get("provenance") if share_cell else None,
                "reason": None if share_cell else "FIELD_NOT_REPORTED_FOR_PERIOD",
            },
            "share_basis": {
                "status": "CORPORATE_ACTION_BASIS_CERTIFIED" if proven else "PROVIDER_REPORTED_SHARE_BASIS_UNVERIFIED",
                "adjustment_applied": False,
                "source_scale_status": "SOURCE_UNIT_ONLY_NO_TABLE_SCALE_ATTESTATION",
                "discontinuity_from_prior_period": discontinuity,
                "comparability_to_prior_period": "UNVERIFIED_SHARE_BASIS_DISCONTINUITY" if discontinuity and not proven else ("CERTIFIED" if proven else "NOT_CERTIFIED"),
                "evidence": dict(corporate_action_evidence) if proven else None,
            },
        })
        if share_value is not None:
            prior_share_value = share_value
    return {
        "contract": CONTRACT,
        "ticker": annual_presentation.get("ticker"),
        "status": "AVAILABLE" if any(r["diluted_eps"]["status"] == "AVAILABLE" for r in records) else "UNAVAILABLE",
        "records": records,
        "source_presentation_sha256": annual_presentation.get("sha256"),
        "source_normalized_sha256": annual_presentation.get("source_normalized_sha256"),
        "source_series_sha256": annual_presentation.get("source_series_sha256"),
        "disclosure": {
            "metric_identity": "FILING_REPORTED_DILUTED_EPS_AND_WEIGHTED_AVERAGE_DILUTED_SHARES",
            "restatement_policy": "EACH_ACCESSION_IS_PRESERVED;NO_CROSS_ACCESSION_VALUE_REPLACEMENT",
            "split_policy": "NO_SPLIT_ADJUSTMENT_WITHOUT_CERTIFIED_RETAINED_CORPORATE_ACTION_EVIDENCE",
            "missing_policy": "UNAVAILABLE_IS_NEVER_ZERO",
        },
        "rating_authority": "UNCHANGED",
        "publication_authority": "UNCHANGED",
        "provider_calls": 0,
    }


__all__ = ["CONTRACT", "project_per_share_credibility"]
