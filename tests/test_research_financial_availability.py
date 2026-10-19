from services.research_financial_availability import (
    build_financial_availability, financial_context_sentence,
)


def _history(*, annual=True, quarterly=True, stale=False):
    lane_rows = {
        "INCOME_STATEMENT": ({"concept": "Revenue"},),
        "CASH_FLOW": ({"concept": "OperatingCashFlow"},),
        "BALANCE_SHEET": ({"concept": "Assets"},),
    }
    return {
        "status": "AVAILABLE", "freshness_status": "STALE_RETAINED" if stale else "CURRENT",
        "annual": {"status": "AVAILABLE" if annual else "UNAVAILABLE", "visible_periods": ("2024", "2025") if annual else (),
                   "statements": lane_rows if annual else {}},
        "quarterly": {"status": "AVAILABLE" if quarterly else "UNAVAILABLE", "visible_periods": ("2026-Q1",) if quarterly else (),
                      "statements": lane_rows if quarterly else {}},
    }


def _annual(available=True):
    return {
        "status": "AVAILABLE" if available else "UNAVAILABLE",
        "periods": ({"fiscal_year": "2024"}, {"fiscal_year": "2025"}) if available else (),
        "statements": {
            "INCOME_STATEMENT": ({"concept": "Revenue"},),
            "CASH_FLOW": ({"concept": "CashFlow"},),
            "BALANCE_SHEET": ({"concept": "Assets"},),
        } if available else {},
    }


def _depth(complete=True):
    statements = {
        "income_statement": ({"period": "2025", "field": "net_income"},),
        "cash_flow": ({"period": "2025", "field": "free_cash_flow"},),
        "balance_sheet": ({"period": "2025", "field": "cash_and_equivalents"},),
    } if complete else {"income_statement": (), "cash_flow": (), "balance_sheet": ()}
    return {"status": "FULL" if complete else "NOT_AVAILABLE", "statements": statements,
            "valuation_models": ({"fiscal_period": "FY2026"}, {"fiscal_period": "FY2027"}) if complete else ()}


def _snapshot(estimates=True):
    return {"items": ({"field": "forward_eps", "period": "FY2026"},) if estimates else ()}


def test_complete_financial_evidence_has_one_consistent_available_contract():
    result = build_financial_availability(
        ticker="NVDA", snapshot=_snapshot(), depth=_depth(),
        statement_history=_history(), annual_statements=_annual(), freshness={},
    )
    assert result["status"] == "AVAILABLE"
    assert set(result["available_families"]) == set(result["families"])
    assert all(item["status"] == "AVAILABLE" or name == "estimates" and item["status"] == "PARTIAL"
               for name, item in result["families"].items())
    assert "unavailable" not in financial_context_sentence(result).lower()


def test_partial_financial_evidence_names_missing_families_without_hiding_statements():
    result = build_financial_availability(
        ticker="NVDA", snapshot=_snapshot(False), depth=_depth(False),
        statement_history=_history(quarterly=False), annual_statements=_annual(False), freshness={},
    )
    assert result["status"] == "PARTIAL"
    assert result["families"]["income_statement"]["status"] == "AVAILABLE"
    assert result["families"]["estimates"]["status"] == "UNAVAILABLE"
    sentence = financial_context_sentence(result)
    assert "income statements" in sentence
    assert "Unavailable: estimates, valuation metrics" in sentence


def test_explicit_stale_evidence_is_never_presented_as_fresh():
    result = build_financial_availability(
        ticker="NVDA", snapshot=_snapshot(), depth=_depth(),
        statement_history=_history(stale=True), annual_statements=_annual(), freshness={},
    )
    assert result["status"] == "STALE"
    assert "retained stale evidence" in financial_context_sentence(result)


def test_inconsistent_depth_cannot_overrule_rendered_integrity_checked_history():
    result = build_financial_availability(
        ticker="NVDA", snapshot=_snapshot(False), depth=_depth(False),
        statement_history=_history(), annual_statements=_annual(), freshness={},
    )
    assert result["families"]["income_statement"]["status"] == "AVAILABLE"
    assert result["families"]["income_statement"]["source_disagreement"] is True
    assert "income statements" in financial_context_sentence(result)
    assert "financial statements, estimates, and valuation metrics are unavailable" not in financial_context_sentence(result)


def test_unavailable_evidence_remains_explicit_and_never_fabricated():
    result = build_financial_availability(
        ticker="NONE", snapshot={"items": ()}, depth=_depth(False),
        statement_history={"status": "UNAVAILABLE"}, annual_statements=_annual(False), freshness={},
    )
    assert result["status"] == "UNAVAILABLE"
    assert all(item["fact_count"] == 0 for item in result["families"].values())
    assert financial_context_sentence(result).startswith("Verified financial statements")
