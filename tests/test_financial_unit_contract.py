from engines.component_builder import build_components
from engines.financial_unit_contract import (
    CONTRACT_VERSION, FinancialUnit, convert, normalize_field,
)
import pytest


def test_mktx_ratio_decimal_normalizes_once_at_scoring_boundary():
    row = {
        "operating_profit_margin": 0.403935869,
        "operating_margin_lineage": {"scale": "RATIO_DECIMAL"},
    }
    fundamentals = build_components(row)["fundamentals"]
    assert fundamentals["data"]["operating_margin_pct"] == 40.3935869
    semantics = fundamentals["data"]["unit_semantics"]["operating_margin_pct"]
    assert semantics["source_unit"] == "RATIO_DECIMAL"
    assert semantics["normalized_unit"] == "PERCENTAGE_POINTS"
    assert semantics["contract_version"] == CONTRACT_VERSION


def test_percentage_points_do_not_scale_twice():
    result = normalize_field({"Operating Margin": 40.3935869}, "operating_margin_pct")
    assert result["normalized_value"] == 40.3935869
    assert result["source_unit"] == "PERCENTAGE_POINTS"


def test_growth_percent_negative_zero_and_missing_are_deterministic():
    assert normalize_field({"revenue_growth": -0.5}, "revenue_growth_pct")["normalized_value"] == -0.5
    assert normalize_field({"revenue_growth": 0}, "revenue_growth_pct")["normalized_value"] == 0
    assert normalize_field({}, "revenue_growth_pct")["normalized_value"] is None


def test_other_growth_and_payout_contracts_are_explicit():
    assert normalize_field({"ebitda_growth_pct": -0.5}, "ebitda_growth_pct")["normalized_value"] == -0.5
    assert normalize_field({"freeCashFlowGrowth": 0.125}, "fcf_growth_pct")["normalized_value"] == 12.5
    assert normalize_field({"payout_ratio": 0.42}, "payout_ratio_pct")["normalized_value"] == 42


def test_component_normalizes_financial_values_from_nested_payload_sources():
    fundamentals = build_components({"financials": {
        "revenueGrowth": 0.12,
        "operating_profit_margin": 0.25,
    }})["fundamentals"]
    assert fundamentals["data"]["revenue_growth_pct"] == 12
    assert fundamentals["data"]["operating_margin_pct"] == 25


def test_ratio_fields_convert_exactly_once_without_magnitude_inference():
    for field, key in (
        ("gross_margin_pct", "gross_profit_margin"),
        ("net_margin_pct", "net_profit_margin"),
        ("roe_pct", "return_on_equity"),
        ("roa_pct", "return_on_assets"),
        ("roic_pct", "return_on_invested_capital"),
    ):
        result = normalize_field({key: 0.25}, field)
        assert result["normalized_value"] == 25
        assert result["source_unit"] == "RATIO_DECIMAL"


def test_basis_points_have_explicit_conversion_and_unknown_is_rejected():
    assert convert(125, source_unit=FinancialUnit.BASIS_POINTS) == 1.25
    result = normalize_field({"operating_profit_margin": None}, "operating_margin_pct")
    assert result["normalized_value"] is None


def test_fundamental_formula_is_unchanged_but_receives_normalized_margin():
    row = {
        "Revenue Growth": -0.5, "EPS Growth": -4.3,
        "operating_profit_margin": 0.403935869,
        "operating_margin_lineage": {"scale": "RATIO_DECIMAL"},
        "Free Cash Flow": 332_329_000, "Current Ratio": 7.465,
    }
    fundamentals = build_components(row)["fundamentals"]
    expected_parts = (49.375, 45.7, 35 + 40.3935869 * 1.5, 72, 89)
    assert fundamentals["score"] == round(sum(expected_parts) / len(expected_parts), 1)
    assert fundamentals["score"] == 70.3


@pytest.mark.parametrize("ticker,ratio", (
    ("LOPE", 0.2742330955545309), ("MKTX", 0.40393586901548917),
    ("TK", 0.21762258825511838), ("INCY", 0.26118008061087183),
    ("HURN", 0.11047098449041665), ("LILA", 0.16196929449371933),
    ("ZIM", 0.14323165609339242), ("GSL", 0.4985145391884085),
    ("STGW", 0.05481849432794775), ("VTRS", 0.017727396695081783),
    ("AES", 0.16103981034905585), ("BLKB", 0.1690534534481307),
    ("ITRN", 0.2158970316664949), ("NATL", 0.10978410656867249),
    ("KD", 0.0420752716671084), ("KOP", 0.11669238546267227),
    ("TXN", 0.34724578667571543),
))
def test_current_publishable_margin_shapes_have_unambiguous_scoring_units(ticker, ratio):
    fundamentals = build_components({
        "ticker": ticker, "operating_profit_margin": ratio,
        "operating_margin_lineage": {"scale": "RATIO_DECIMAL"},
    })["fundamentals"]
    assert fundamentals["data"]["operating_margin_pct"] == pytest.approx(ratio * 100)
    assert fundamentals["data"]["unit_semantics"]["operating_margin_pct"]["source_unit"] == "RATIO_DECIMAL"
