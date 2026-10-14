import copy

from services.customer_per_share_credibility import project_per_share_credibility


def fixture():
    periods = [
        {"fiscal_year": 2024, "fiscal_period_start": "2023-01-01", "fiscal_period_end": "2023-12-31", "filed_date": "2024-02-01", "accepted_date": "2024-02-01", "accession": "a1"},
        {"fiscal_year": 2025, "fiscal_period_start": "2024-01-01", "fiscal_period_end": "2024-12-31", "filed_date": "2025-02-01", "accepted_date": "2025-02-01", "accession": "a2"},
    ]
    provenance = {"raw_sha256": "a" * 64, "filing_accession": "a1"}
    eps = {"concept": "us-gaap_EarningsPerShareDiluted", "unit": {"canonical": "USD_PER_SHARE", "currency": "USD", "original": "usd/share"}, "cells": [
        {"accession": "a1", "status": "AVAILABLE", "value": 0, "fact_id": "eps1", "provenance": provenance},
        {"accession": "a2", "status": "UNAVAILABLE", "value": None, "reason": "FIELD_NOT_REPORTED_FOR_PERIOD"},
    ]}
    shares = {"concept": "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding", "unit": {"canonical": "SHARES", "original": "shares"}, "cells": [
        {"accession": "a1", "status": "AVAILABLE", "value": 100, "fact_id": "shares1", "provenance": provenance},
        {"accession": "a2", "status": "AVAILABLE", "value": 1000, "fact_id": "shares2", "provenance": {**provenance, "filing_accession": "a2"}},
    ]}
    return {"contract": "ATLAS_G6_ANNUAL_STATEMENT_PRESENTATION_V1", "ticker": "NVDA", "periods": periods, "statements": {"INCOME_STATEMENT": [eps, shares]}, "sha256": "p"*64, "source_normalized_sha256": "n"*64, "source_series_sha256": "s"*64}


def test_reported_zero_is_available_but_missing_is_not_zero():
    result = project_per_share_credibility(fixture())
    first, second = result["records"]
    assert first["diluted_eps"]["status"] == "AVAILABLE"
    assert first["diluted_eps"]["value"] == 0
    assert first["diluted_eps"]["zero_semantics"] == "REPORTED_ZERO"
    assert second["diluted_eps"]["status"] == "UNAVAILABLE"
    assert second["diluted_eps"]["value"] is None


def test_share_discontinuity_is_not_silently_treated_as_split_adjusted():
    result = project_per_share_credibility(fixture())
    assert {r["share_basis"]["status"] for r in result["records"]} == {"PROVIDER_REPORTED_SHARE_BASIS_UNVERIFIED"}
    assert all(r["share_basis"]["adjustment_applied"] is False for r in result["records"])
    assert result["records"][1]["share_basis"]["discontinuity_from_prior_period"] is True
    assert result["records"][1]["share_basis"]["comparability_to_prior_period"] == "UNVERIFIED_SHARE_BASIS_DISCONTINUITY"


def test_certified_corporate_action_evidence_is_disclosed_without_mutating_values():
    source = fixture(); before = copy.deepcopy(source)
    evidence = {"status": "CERTIFIED", "ticker": "NVDA", "source_sha256": "c"*64, "action": "STOCK_SPLIT"}
    result = project_per_share_credibility(source, corporate_action_evidence=evidence)
    assert result["records"][0]["share_basis"]["status"] == "CORPORATE_ACTION_BASIS_CERTIFIED"
    assert result["records"][1]["diluted_weighted_average_shares"]["value"] == 1000
    assert source == before


def test_alias_concepts_preserve_accession_fact_id_units_and_source_hash():
    source = fixture(); source["statements"]["INCOME_STATEMENT"][0]["concept"] = "EarningsPerShareDiluted"
    result = project_per_share_credibility(source)
    cell = result["records"][0]["diluted_eps"]
    assert cell["fact_id"] == "eps1"
    assert cell["unit"]["canonical"] == "USD_PER_SHARE"
    assert cell["provenance"]["raw_sha256"] == "a"*64
    assert result["rating_authority"] == result["publication_authority"] == "UNCHANGED"
