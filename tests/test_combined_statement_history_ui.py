from pathlib import Path

from ui.customer_research_v2 import _per_share_credibility_rows, _statement_history_frame, _statement_history_trend


def _periods():
    return [
        {"fiscal_year": 2025, "fiscal_quarter": 1, "fiscal_period_end": "2025-03-31", "accession": "q1"},
        {"fiscal_year": 2025, "fiscal_quarter": 2, "fiscal_period_end": "2025-06-30", "accession": "q2"},
    ]


def _statement():
    return [{
        "concept": "Revenue", "labels": ["Revenue"], "unit": {"canonical": "USD"},
        "cells": [
            {"accession": "q1", "status": "AVAILABLE", "value": 1_000_000},
            {"accession": "q2", "status": "UNAVAILABLE", "value": None},
        ],
    }]


def test_quarterly_history_preserves_period_semantics_and_never_zero_fills():
    frame = _statement_history_frame(_statement(), _periods(), frequency="quarterly")
    assert list(frame.columns) == ["Line item", "FY2025 Q1", "FY2025 Q2"]
    assert frame.iloc[0].to_dict() == {
        "Line item": "Revenue", "FY2025 Q1": "$1.00M", "FY2025 Q2": "Unavailable",
    }


def test_trend_requires_two_exact_reported_values():
    assert _statement_history_trend(_statement(), _periods(), frequency="quarterly").empty
    statement = _statement()
    statement[0]["cells"][1] = {"accession": "q2", "status": "AVAILABLE", "value": 1_200_000}
    trend = _statement_history_trend(statement, _periods(), frequency="quarterly")
    assert trend[["Period", "Value"]].to_dict("records") == [
        {"Period": "FY2025 Q1", "Value": 1_000_000.0},
        {"Period": "FY2025 Q2", "Value": 1_200_000.0},
    ]


def test_customer_copy_discloses_research_101_and_accounting_boundaries():
    source = Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert "Annual and quarterly statements" in source
    assert "cumulative year-to-date except Q1" in source
    assert "Missing values remain Unavailable, never zero" in source
    assert '"statement-history"' in source
    assert "rating_authority" in source and "publication_authority" in source


def test_statement_history_uses_standard_income_statement_hierarchy():
    statement = [
        {"concept": "NetIncomeLoss", "labels": ["Net income"], "unit": {"canonical": "USD"},
         "cells": [{"accession": "a", "status": "AVAILABLE", "value": 2}]},
        {"concept": "Revenues", "labels": ["Revenue"], "unit": {"canonical": "USD"},
         "cells": [{"accession": "a", "status": "AVAILABLE", "value": 10}]},
        {"concept": "OperatingIncomeLoss", "labels": ["Operating income"], "unit": {"canonical": "USD"},
         "cells": [{"accession": "a", "status": "AVAILABLE", "value": 4}]},
    ]
    periods = [{"accession": "a", "fiscal_year": 2025, "fiscal_period_end": "2025-12-31"}]
    frame = _statement_history_frame(statement, periods, frequency="annual")
    assert frame["Line item"].tolist() == ["Revenue", "Operating income", "Net income"]
    assert frame.iloc[0]["2025"] != "Unavailable"


def test_eps_credibility_discloses_unverified_basis_and_preserves_zero():
    credibility = {
        "contract": "ATLAS_CUSTOMER_PER_SHARE_CREDIBILITY_V1", "provider_calls": 0,
        "rating_authority": "UNCHANGED", "publication_authority": "UNCHANGED",
        "records": [{
            "fiscal_year": 2025, "period_end": "2025-01-26", "accession": "0001045810-25-000023",
            "diluted_eps": {"status": "AVAILABLE", "value": 0, "zero_semantics": "REPORTED_ZERO", "fact_id": "eps:1"},
            "diluted_weighted_average_shares": {"status": "AVAILABLE", "value": 24_500_000_000},
            "share_basis": {"status": "PROVIDER_REPORTED_SHARE_BASIS_UNVERIFIED",
                            "discontinuity_from_prior_period": True,
                            "comparability_to_prior_period": "UNVERIFIED_SHARE_BASIS_DISCONTINUITY"},
        }],
    }
    rows = _per_share_credibility_rows(credibility)
    assert rows[0]["Diluted EPS (reported)"] == "$0.00"
    assert rows[0]["Filing accession"] == "0001045810-25-000023"
    assert rows[0]["Share-basis comparability"] == "Unverified Share Basis Discontinuity"
    source = Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert "No split adjustment was inferred" in source
    assert "are not plotted" in source
