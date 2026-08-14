import inspect

import pytest

import overnight_market_scan as scan
from engines.atlas_valuation import (
    AtlasValuationInputs,
    DERIVED_FROM_PRICE_AND_FORWARD_PE,
    FALLBACK_ASSUMPTION,
    FORMULA_NOT_APPLICABLE,
    INSUFFICIENT_INPUTS,
    MODEL_UNDER_REVIEW,
    PROVIDER_DIRECT,
    PUBLISHED,
    REJECTED_EXTREME_DOWNSIDE,
    REJECTED_EXTREME_UPSIDE,
    calculate_atlas_fair_value,
    canonical_operating_margin,
)
from engines.live_research_engine import _fair_value_complete
from engines.semantic_fields import canonical_atlas_fair_value, valuation_families
from services.ai_synthesis import build_ticker_context


def inputs(**overrides):
    values = {
        "price": 100.0,
        "forward_pe": 20.0,
        "revenue_growth": 10.0,
        "revenue_growth_source": "TEST_PROVIDER",
        "revenue_growth_horizon": "PROVIDER_DEFINED",
    }
    values.update(overrides)
    return AtlasValuationInputs(**values)


def test_direct_and_derived_forward_eps_have_explicit_provenance():
    direct = calculate_atlas_fair_value(inputs(forward_eps=5.5, forward_eps_source="TEST_PROVIDER"))
    derived = calculate_atlas_fair_value(inputs(forward_eps=None))
    assert direct.forward_eps == 5.5
    assert direct.forward_eps_method == PROVIDER_DIRECT
    assert direct.forward_eps_source == "TEST_PROVIDER"
    assert derived.forward_eps == 5.0
    assert derived.forward_eps_method == DERIVED_FROM_PRICE_AND_FORWARD_PE


@pytest.mark.parametrize("invalid_direct", [None, 0, -2.5, "malformed"])
def test_invalid_direct_eps_uses_only_price_forward_pe_derivation(invalid_direct):
    result = calculate_atlas_fair_value(inputs(forward_eps=invalid_direct))
    assert result.forward_eps == 5.0
    assert result.forward_eps_method == DERIVED_FROM_PRICE_AND_FORWARD_PE


def test_historical_and_quarterly_eps_aliases_are_never_forward_eps():
    parsed = AtlasValuationInputs.from_row({
        "price": 100,
        "forward_pe": None,
        "eps_estimate": 12,
        "latest_eps": 11,
        "reported_eps": 10,
        "trailing_eps": 9,
        "diluted_eps": 8,
    })
    result = calculate_atlas_fair_value(parsed)
    assert parsed.forward_eps is None
    assert result.forward_eps is None
    assert result.status == INSUFFICIENT_INPUTS


def test_scanner_persists_existing_metadata_provenance_without_extra_calls(monkeypatch):
    calls = {"ticker": 0, "info": 0}

    class FakeTicker:
        def get_info(self):
            calls["info"] += 1
            return {
                "shortName": "Example",
                "forwardPE": 20.0,
                "forwardEps": 5.0,
                "revenueGrowth": 0.12,
                "earningsGrowth": -0.05,
            }

    def ticker(symbol):
        calls["ticker"] += 1
        assert symbol == "EXM"
        return FakeTicker()

    monkeypatch.setattr(scan.yf, "Ticker", ticker)
    metadata = scan.get_metadata("EXM")
    assert calls == {"ticker": 1, "info": 1}
    assert metadata["forward_eps"] == 5.0
    assert metadata["forward_eps_source"] == "YAHOO_INFO"
    assert metadata["revenue_growth_source"] == "YAHOO_INFO"
    assert metadata["revenue_growth_horizon"] == "PROVIDER_DEFINED"
    assert metadata["earnings_growth"] == -0.05


def test_quarterly_estimate_and_analyst_targets_cannot_set_atlas_value():
    baseline = calculate_atlas_fair_value(inputs())
    with_analysts = calculate_atlas_fair_value(inputs(
        analyst_target_mean=900, analyst_target_low=800, analyst_target_high=1000,
    ))
    assert with_analysts.fair_value == baseline.fair_value
    unavailable = AtlasValuationInputs.from_row({
        "price": 100, "eps_estimate": 12, "analyst_target_mean": 500,
        "ai_base_target": 400, "trade_target_1": 300, "target": 200,
    })
    assert calculate_atlas_fair_value(unavailable).status == INSUFFICIENT_INPUTS


def test_growth_provenance_and_missing_assumption_are_explicit():
    provider = calculate_atlas_fair_value(inputs())
    fallback = calculate_atlas_fair_value(inputs(revenue_growth=None, revenue_growth_source=None, revenue_growth_horizon=None))
    assert provider.growth_source == "TEST_PROVIDER"
    assert provider.growth_horizon == "PROVIDER_DEFINED"
    assert fallback.growth_method == FALLBACK_ASSUMPTION
    assert fallback.growth_value == 8.0
    assert "REVENUE_GROWTH_FALLBACK_8_PERCENT" in fallback.assumption_flags


def test_operating_margin_alias_normalizes_once_and_applies_existing_bonus():
    assert canonical_operating_margin({"operating_profit_margin": 0.25}) == 25.0
    assert canonical_operating_margin({"operating_profit_margin": 25.0}) == 25.0
    decimal = calculate_atlas_fair_value(AtlasValuationInputs.from_row({
        "price": 100, "forward_pe": 20, "revenue_growth": 0.10,
        "operating_profit_margin": 0.25,
    }))
    percentage = calculate_atlas_fair_value(AtlasValuationInputs.from_row({
        "price": 100, "forward_pe": 20, "revenue_growth": 10,
        "operating_margin": 25,
    }))
    assert decimal.justified_pe == percentage.justified_pe == 22.5
    assert decimal.fair_value == percentage.fair_value


@pytest.mark.parametrize(
    ("margin", "expected_pe"),
    [(24.99, 20.5), (25.00, 22.5), (25.01, 22.5), (0.2499, 20.5), (0.25, 22.5), (0.2501, 22.5)],
)
def test_existing_margin_bonus_boundary_is_exact(margin, expected_pe):
    result = calculate_atlas_fair_value(inputs(operating_margin=margin))
    assert result.justified_pe == expected_pe


def test_statuses_rejected_values_and_sentinel_are_deterministic():
    assert calculate_atlas_fair_value(inputs(price=None)).status == INSUFFICIENT_INPUTS
    assert calculate_atlas_fair_value(inputs(forward_pe=0)).status == FORMULA_NOT_APPLICABLE
    extreme_up = calculate_atlas_fair_value(inputs(forward_pe=5, revenue_growth=40))
    extreme_down = calculate_atlas_fair_value(inputs(forward_pe=100, revenue_growth=-10))
    sentinel = calculate_atlas_fair_value(inputs(forward_pe=16 / 1.3, revenue_growth=0))
    assert extreme_up.status == REJECTED_EXTREME_UPSIDE and extreme_up.fair_value is None
    assert extreme_down.status == REJECTED_EXTREME_DOWNSIDE and extreme_down.fair_value is None
    assert sentinel.status == MODEL_UNDER_REVIEW and sentinel.fair_value is None
    assert "raw_fair_value" not in extreme_up.public_fields()
    assert "raw_upside_pct" not in extreme_up.public_fields()
    assert "validation_flags" not in extreme_up.public_fields()
    assert "atlas_valuation_validation_flags" not in extreme_up.public_fields()


def test_multiple_expansion_and_analyst_discrepancy_are_diagnostic_only():
    baseline = calculate_atlas_fair_value(inputs(forward_pe=10, revenue_growth=40))
    compared = calculate_atlas_fair_value(inputs(
        forward_pe=10, revenue_growth=40, analyst_target_low=50, analyst_target_high=150,
    ))
    assert compared.raw_fair_value == baseline.raw_fair_value
    assert compared.multiple_expansion_ratio == 3.4
    assert compared.multiple_expansion_band == "ABOVE_3_0X"
    assert compared.analyst_discrepancy == "ATLAS_ABOVE_ANALYST_HIGH"


def test_scheduled_and_live_use_identical_canonical_methodology():
    row = {"price": 100.0, "current_price": 100.0}
    meta = {
        "forward_pe": 20.0, "forward_eps": 5.0, "forward_eps_source": "YAHOO_INFO",
        "revenue_growth": 0.10, "revenue_growth_source": "YAHOO_INFO",
        "revenue_growth_horizon": "PROVIDER_DEFINED", "operating_profit_margin": 0.25,
        "analyst_target_mean": 500, "analyst_target_low": 400, "analyst_target_high": 600,
    }
    scheduled = scan.v803_apply_complete_research_fields(dict(row), dict(meta))
    live = _fair_value_complete(100.0, {
        "forwardPE": 20.0, "forwardEps": 5.0, "revenueGrowth": 0.10,
    }, {
        "Forward PE": 20.0, "Revenue Growth": 10.0, "Operating Margin": 25.0,
        "revenue_growth_source": "YAHOO_INFO", "revenue_growth_horizon": "PROVIDER_DEFINED",
    }, {
        "analyst_target_mean": 500, "analyst_target_low": 400, "analyst_target_high": 600,
    })
    assert scheduled["atlas_fair_value"] == live["atlas_fair_value"] == 112.5
    assert scheduled["atlas_valuation_status"] == live["atlas_valuation_status"] == PUBLISHED


@pytest.mark.parametrize(
    "profile",
    [
        {"forward_pe": 20, "forward_eps": 5, "growth": 10, "margin": 15},
        {"forward_pe": 20, "forward_eps": 5, "growth": 40, "margin": 15},
        {"forward_pe": 20, "forward_eps": 5, "growth": 10, "margin": 25},
        {"forward_pe": 20, "forward_eps": 5, "growth": None, "margin": 15},
        {"forward_pe": 20, "forward_eps": None, "growth": 10, "margin": 15},
        {"forward_pe": 5, "forward_eps": None, "growth": 40, "margin": 15},
        {"forward_pe": 100, "forward_eps": None, "growth": -10, "margin": 15},
        {"forward_pe": 16 / 1.3, "forward_eps": None, "growth": 0, "margin": 15},
    ],
)
def test_scheduled_live_parity_matrix_and_analyst_independence(profile):
    meta = {
        "forward_pe": profile["forward_pe"],
        "forward_eps": profile["forward_eps"],
        "forward_eps_source": "YAHOO_INFO" if profile["forward_eps"] is not None else None,
        "revenue_growth": profile["growth"],
        "revenue_growth_source": "YAHOO_INFO" if profile["growth"] is not None else None,
        "revenue_growth_horizon": "PROVIDER_DEFINED" if profile["growth"] is not None else None,
        "operating_profit_margin": profile["margin"],
        "analyst_target_mean": 9999,
        "analyst_target_low": 9000,
        "analyst_target_high": 10000,
    }
    scheduled = scan.v803_apply_complete_research_fields({"price": 100, "current_price": 100}, dict(meta))
    info = {
        "forwardPE": profile["forward_pe"],
        "forwardEps": profile["forward_eps"],
        "revenueGrowth": profile["growth"],
        "operatingMargins": profile["margin"],
    }
    fundamentals = {
        "Forward PE": profile["forward_pe"],
        "Revenue Growth": profile["growth"],
        "Operating Margin": profile["margin"],
        "revenue_growth_source": "YAHOO_INFO" if profile["growth"] is not None else None,
        "revenue_growth_horizon": "PROVIDER_DEFINED" if profile["growth"] is not None else None,
    }
    live = _fair_value_complete(100, info, fundamentals, {
        "analyst_target_mean": 1,
        "analyst_target_low": 0.5,
        "analyst_target_high": 2,
    })
    keys = (
        "atlas_fair_value", "atlas_fv_upside_pct", "atlas_valuation_status",
        "atlas_valuation_justified_pe", "atlas_valuation_growth_method",
        "forward_eps_method", "atlas_valuation_assumption_flags",
    )
    assert {key: scheduled.get(key) for key in keys} == {key: live.get(key) for key in keys}


def test_canonical_consumers_and_ai_keep_analyst_and_atlas_separate():
    row = {
        "price": 100, "atlas_fair_value": None, "atlas_valuation_status": REJECTED_EXTREME_UPSIDE,
        "analyst_target_mean": 140, "analyst_target_low": 120, "analyst_target_high": 160,
        "ai_base_target": 180, "trade_target_1": 130, "target": 150,
    }
    assert canonical_atlas_fair_value(row) is None
    families = valuation_families(row)
    context = build_ticker_context(row)
    assert families["atlas_fair_value"] is None
    assert families["analyst_target_mean"] == 140
    assert context["atlas_fair_value"] == "Unavailable"
    assert context["atlas_valuation_status"] == REJECTED_EXTREME_UPSIDE
    assert context["analyst_consensus"] == "$140.00"


def test_formula_exists_only_in_canonical_engine_not_migrated_producers():
    assert "0.45 *" not in inspect.getsource(scan.v803_apply_complete_research_fields)
    assert "0.42 *" not in inspect.getsource(_fair_value_complete)
