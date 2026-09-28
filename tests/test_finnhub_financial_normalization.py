from __future__ import annotations

import math

from services.finnhub_financial_normalization import (
    MISSING_PROVIDER_FACT, NONNUMERIC_PROVIDER_VALUE, VALID_NUMERIC_FACT,
    canonical_financial_facts, safe_numeric,
)


REPORT = {
    "quarter": 0, "form": "10-K", "endDate": "2025-12-31",
    "filedDate": "2026-02-01", "accessNumber": "0001", "currency": "USD",
}


def fact(concept: str, value, unit: str = "usd"):
    return {"concept": f"us-gaap_{concept}", "value": value, "unit": unit}


def normalize(*facts):
    diagnostics = []
    result = canonical_financial_facts(facts, REPORT, diagnostics=diagnostics)
    return result, diagnostics


def classifications(diagnostics, field):
    return [row["raw_value_classification"] for row in diagnostics if row["canonical_field"] == field]


def test_safe_numeric_accepts_finite_numbers_and_numeric_strings():
    assert safe_numeric(12) == (12.0, VALID_NUMERIC_FACT)
    assert safe_numeric(12.5) == (12.5, VALID_NUMERIC_FACT)
    assert safe_numeric(" 12345.67 ") == (12345.67, VALID_NUMERIC_FACT)


def test_safe_numeric_rejects_missing_sentinels_nonnumeric_boolean_and_nonfinite():
    for value in (None, "", "   "):
        assert safe_numeric(value)[0] is None
        assert safe_numeric(value)[1] == MISSING_PROVIDER_FACT
    for value in ("N/A", " na ", "NAN", "NULL", "-", "not-a-number", True,
                  math.nan, math.inf, -math.inf):
        assert safe_numeric(value)[0] is None
        assert safe_numeric(value)[1] == NONNUMERIC_PROVIDER_VALUE


def test_current_debt_nonnumeric_uses_valid_long_term_without_zero_substitution():
    result, diagnostics = normalize(fact("DebtCurrent", "N/A"), fact("LongTermDebtNoncurrent", 90))
    assert result["total_debt"]["value"] == 90
    assert result["total_debt"]["source_fields"] == ["us-gaap_LongTermDebtNoncurrent"]
    assert NONNUMERIC_PROVIDER_VALUE in classifications(diagnostics, "debt_current")


def test_long_term_debt_nonnumeric_uses_valid_current_without_zero_substitution():
    result, _ = normalize(fact("DebtCurrent", 10), fact("LongTermDebtNoncurrent", "N/A"))
    assert result["total_debt"]["value"] == 10
    assert result["total_debt"]["source_fields"] == ["us-gaap_DebtCurrent"]


def test_both_debt_components_nonnumeric_omit_total_debt():
    result, diagnostics = normalize(fact("DebtCurrent", "N/A"), fact("LongTermDebtNoncurrent", "N/A"),
                                    fact("Revenues", 100))
    assert "total_debt" not in result
    assert result["revenue"]["value"] == 100
    assert classifications(diagnostics, "debt_current") == [NONNUMERIC_PROVIDER_VALUE]
    assert classifications(diagnostics, "debt_long_term") == [NONNUMERIC_PROVIDER_VALUE]


def test_nonnumeric_ocf_omits_fcf_but_preserves_other_facts():
    result, _ = normalize(fact("NetCashProvidedByUsedInOperatingActivities", "N/A"),
                          fact("PaymentsToAcquirePropertyPlantAndEquipment", 25), fact("Revenues", 100))
    assert "operating_cash_flow" not in result
    assert "free_cash_flow" not in result
    assert result["revenue"]["value"] == 100


def test_nonnumeric_capex_omits_fcf_without_zero_substitution():
    result, _ = normalize(fact("NetCashProvidedByUsedInOperatingActivities", 80),
                          fact("PaymentsToAcquirePropertyPlantAndEquipment", "N/A"))
    assert result["operating_cash_flow"]["value"] == 80
    assert "capex" not in result
    assert "free_cash_flow" not in result


def test_nonnumeric_diluted_shares_are_missing_evidence():
    result, diagnostics = normalize(fact("WeightedAverageNumberOfDilutedSharesOutstanding", "N/A", "shares"),
                                    fact("WeightedAverageNumberOfSharesOutstandingBasic", 50, "shares"))
    assert "weighted_average_shares_diluted" not in result
    assert result["weighted_average_shares_basic"]["value"] == 50
    assert classifications(diagnostics, "weighted_average_shares_diluted") == [NONNUMERIC_PROVIDER_VALUE]


def test_invalid_primary_concept_falls_through_existing_governed_alias_order():
    result, diagnostics = normalize(fact("Revenues", "N/A"),
                                    fact("RevenueFromContractWithCustomerExcludingAssessedTax", "12345.67"))
    assert result["revenue"]["value"] == 12345.67
    assert result["revenue"]["source_field"].endswith("RevenueFromContractWithCustomerExcludingAssessedTax")
    assert classifications(diagnostics, "revenue") == [NONNUMERIC_PROVIDER_VALUE, VALID_NUMERIC_FACT]


def test_valid_record_remains_numerically_identical_and_fcf_formula_is_unchanged():
    result, _ = normalize(
        fact("Revenues", 100), fact("OperatingIncomeLoss", 20),
        fact("NetCashProvidedByUsedInOperatingActivities", 80),
        fact("PaymentsToAcquirePropertyPlantAndEquipment", -25),
        fact("DebtCurrent", 10), fact("LongTermDebtNoncurrent", 90),
    )
    assert result["revenue"]["value"] == 100
    assert result["ebit"]["value"] == 20
    assert result["total_debt"]["value"] == 100
    assert result["free_cash_flow"]["value"] == 55
