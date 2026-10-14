from pathlib import Path

from ui.customer_research_v2 import _statement_history_frame, _statement_history_trend


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

