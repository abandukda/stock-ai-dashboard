import math

import pytest

from engines.institutional_formulas import (
    annualized_volatility, average_return, beta, cagr, capm_cost_of_equity,
    comparable_growth, dcf_equity_value, earnings_surprise, fcfe, fcff,
    dividend_discount_model, enterprise_to_equity_value, free_cash_flow, margin,
    downside_deviation, interest_coverage, max_drawdown, return_on_assets,
    return_on_equity, reward_risk, roic, sharpe_ratio, sortino_ratio,
    terminal_value_perpetuity, wacc,
)
from engines.methodology_registry import REGISTRY, assert_registered, methodology, registry_snapshot
from engines.professional_valuation_v2 import INSUFFICIENT_INPUTS, NOT_APPLICABLE, PUBLISHED, classify_company, value_company
from services.technical_intelligence.engine import _rsi, _wilder_average
from services.analyst_estimate_snapshot_store import append_daily_snapshots, revision_summary
from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation


def test_registry_classifies_every_method_exclusively_and_blocks_unknown_ids():
    assert len(REGISTRY) >= 35
    for item in REGISTRY.values():
        assert item.is_standard_method != item.is_atlas_derived
        assert item.required_inputs and item.publication_requirements
    assert assert_registered("FIN_ROIC_V1", standard_name=True).name == "Return on Invested Capital"
    with pytest.raises(KeyError, match="UNREGISTERED_CANONICAL_METHODOLOGY"):
        methodology("MADE_UP_SHARPE")
    assert registry_snapshot()["version"].startswith("ATLAS_INSTITUTIONAL")


def test_standard_fundamental_formulas_and_denominator_guards():
    assert comparable_growth(120, 100) == pytest.approx(.2)
    assert margin(25, 100) == pytest.approx(.25)
    assert free_cash_flow(100, -30) == 70
    assert fcff(100, .25, 10, 20, 5) == 60
    assert fcfe(80, 10, 20, 5, 4) == 69
    assert average_return(20, 90, 110) == pytest.approx(.2)
    assert roic(100, .25, 350, 400) == pytest.approx(.2)
    with pytest.raises(ValueError): comparable_growth(10, -1)
    with pytest.raises(ValueError): earnings_surprise(1, 0)


def test_wacc_dcf_and_terminal_value_use_consistent_cash_flow_discounting():
    re = capm_cost_of_equity(.04, 1.2, .05)
    discount = wacc(800, 200, re, .06, .25)
    assert re == pytest.approx(.10) and discount == pytest.approx(.089)
    result = dcf_equity_value([100, 110, 120], discount, .025, 200, 50, 100)
    assert result["per_share_value"] > 0
    assert 0 < result["terminal_value_pct_of_enterprise_value"] < 1
    with pytest.raises(ValueError, match="DISCOUNT_RATE_MUST_EXCEED_GROWTH"):
        terminal_value_perpetuity(100, .03, .03)


def test_registered_risk_and_performance_formulas():
    returns = [.01, -.02, .03, .005]
    assert annualized_volatility(returns) == pytest.approx(__import__("statistics").stdev(returns)*math.sqrt(252))
    assert beta([.01,.02,.03], [.005,.01,.015]) == pytest.approx(2)
    assert max_drawdown([100,120,90,110]) == pytest.approx(-.25)
    assert cagr(100,121,2) == pytest.approx(.1)
    assert dividend_discount_model(2, .10, .04) == pytest.approx(33.333333)
    assert enterprise_to_equity_value(1000, 200, 50, 100) == pytest.approx(8.5)
    assert reward_risk(100, 130, 90) == 3
    assert sharpe_ratio([.01, -.01, .02]) == pytest.approx(6.928203, rel=.01)
    assert sortino_ratio([.01, -.01, .02]) > 0
    assert downside_deviation([.01, -.01, .02]) > 0
    assert interest_coverage(100, -20) == 5
    assert return_on_equity(20, 90, 110) == pytest.approx(.2)
    assert return_on_assets(10, 190, 210) == pytest.approx(.05)


@pytest.mark.parametrize(("row","expected"), [
    ({"security_type":"ETF"},"ETF"), ({"industry":"Banks - Regional","forward_eps":2},"BANK"),
    ({"industry":"Biotechnology","forward_eps":-1},"PRE_PROFIT_BIOTECH"),
    ({"industry":"Drug Manufacturers - General","forward_eps":5},"PROFITABLE_PHARMA"),
    ({"industry":"Software - Application","revenue_growth":.3,"forward_eps":2},"HIGH_GROWTH_SOFTWARE"),
])
def test_company_type_routing(row, expected):
    assert classify_company(row) == expected


def professional_row(**overrides):
    row = {"ticker":"TEST","price":100,"industry":"Medical Devices","forward_eps":6,
           "forward_eps_period":"FY2027","justified_forward_pe":22,
           "justified_forward_pe_basis":"five-year history and selected peers"}
    row.update(overrides); return row


def test_professional_valuation_reconciles_only_valid_models_and_has_no_outcome_cap():
    result = value_company(professional_row())
    assert result["status"] == PUBLISHED and result["atlas_base_fair_value"] == 132
    assert result["atlas_expected_return"] == 32
    assert result["models"][1]["methodology_id"] == "VAL_FORWARD_PE_V1"
    extreme = value_company(professional_row(justified_forward_pe=90))
    assert extreme["status"] == PUBLISHED and extreme["atlas_base_fair_value"] == 540


def test_professional_scenarios_change_economic_inputs_and_dcf_sensitivity_is_explicit():
    row = professional_row(
        valuation_scenarios={
            "bear": {"forward_eps": 5, "justified_forward_pe": 18},
            "bull": {"forward_eps": 8, "justified_forward_pe": 25},
        }
    )
    result = value_company(row, as_of="2026-09-05T20:00:00Z")
    assert result["atlas_bear_case"] == 90 and result["atlas_bull_case"] == 200
    assert result["scenario_status"] == "PUBLISHED"
    assert result["weighting_basis"].startswith("Deterministic company-type")


def test_professional_diagnostics_flag_dispersion_and_calibrate_confidence_without_capping_value():
    result = value_company(professional_row(
        forward_ebitda=10, justified_ev_ebitda=10,
        justified_ev_ebitda_basis="median current peer multiple",
        diluted_shares=1, total_debt=0, cash_and_equivalents=0,
    ))
    assert result["atlas_fair_value_high"] == 132
    assert result["atlas_fair_value_low"] == 100
    assert result["valuation_diagnostics"]["model_dispersion_pct"] > 20
    assert result["valuation_confidence"] < 80
    assert result["valuation_explanation"]["highest_weight_method"]


def test_single_method_is_disclosed_and_cannot_have_high_confidence():
    result = value_company(professional_row())
    assert "MODEL_CONCENTRATION_SINGLE_METHOD" in result["valuation_diagnostics"]["flags"]
    assert result["valuation_confidence"] <= 55


def test_ddm_routes_only_when_complete_and_never_uses_street_target():
    row = {"ticker":"BANK","industry":"Banks - Regional","price":40,"forward_eps":None,
           "dividend_next":2,"cost_of_equity":.10,"dividend_growth":.04}
    result = value_company(row)
    assert result["status"] == PUBLISHED
    assert next(model for model in result["models"] if model["methodology_id"] == "VAL_DDM_GORDON_V1")["value"] == pytest.approx(33.3333)


def test_wall_street_and_context_are_strictly_non_authoritative():
    baseline = value_company(professional_row())
    changed = value_company(professional_row(analyst_target_mean=9999, insider_buy_count=500, political_support="BUY"))
    for key in ("atlas_base_fair_value","models","valuation_confidence","company_type"):
        assert changed[key] == baseline[key]
    assert changed["wall_street_used"] is False


def test_missing_inputs_fail_closed_and_etf_is_not_valued_as_a_company():
    assert value_company({"ticker":"MISS","price":10})["status"] == INSUFFICIENT_INPUTS
    etf = value_company({"ticker":"SPY","price":600,"security_type":"ETF","forward_eps":50,
                         "forward_eps_period":"FY2027","justified_forward_pe":20,"justified_forward_pe_basis":"peer"})
    assert etf["status"] == NOT_APPLICABLE and etf["atlas_base_fair_value"] is None


def test_legacy_multiple_without_professional_basis_cannot_publish_v2():
    result = value_company({"price":100,"forward_eps":5,"forward_eps_period":"FY2027","atlas_valuation_justified_pe":25})
    assert result["status"] == INSUFFICIENT_INPUTS
    assert result["models"][1]["reason"] == "EPS_PERIOD_OR_JUSTIFIED_MULTIPLE_EVIDENCE_MISSING"


def test_rsi_and_atr_smoothing_use_wilder_recurrence_not_rolling_mean():
    values = [1, 2, 3, 2, 4, 5, 4, 6, 7, 6, 8, 9, 8, 10, 11, 9, 12]
    changes = [b-a for a,b in zip(values, values[1:])]
    gains = [max(change,0) for change in changes]
    seed = sum(gains[:14])/14
    expected = seed
    for value in gains[14:]: expected = (13*expected+value)/14
    assert _wilder_average(gains,14) == pytest.approx(expected)
    assert 0 <= _rsi(values,14) <= 100


def test_estimate_revisions_require_same_metric_period_basis_and_real_dates(tmp_path):
    base = {"ticker":"ABC","estimate_period":"2027-12-31","period_type":"annual","metric":"EPS",
            "provider":"FMP","endpoint_schema_version":"FMP_ANALYST_ESTIMATE_SNAPSHOT_V1","semantic_status":"AVAILABLE"}
    snapshots = [
        {**base,"average":10,"observed_at":"2026-06-01","evidence_id":"old"},
        {**base,"average":11,"observed_at":"2026-09-01","evidence_id":"new"},
        {**base,"metric":"REVENUE","average":999,"observed_at":"2026-07-01","evidence_id":"other"},
    ]
    append_daily_snapshots("ABC", snapshots, root=tmp_path)
    result = revision_summary("ABC", root=tmp_path)
    eps90 = next(item for item in result["horizon_comparisons"] if item["metric"] == "EPS" and item["horizon_days"] == 90)
    assert eps90["revision_pct"] == 10
    assert eps90["prior_observed_at"] == "2026-06-01"
    assert eps90["methodology_id"] == "FORECAST_REVISION_V1"


def test_certified_v2_is_activated_ticker_by_ticker_and_context_cannot_change_it():
    common = dict(
        ticker="TEST", evaluation_mode="ON_DEMAND",
        market_snapshot={"price":100,"provider_timestamp":"2026-09-05T20:00:00Z","latest_completed_session_valid":True},
        technical={"status":"AVAILABLE","state":"SETUP_FORMING","score":70,"as_of":"2026-09-05","feed_health":"HEALTHY","completed_bar":True,"evidence":{}},
        fundamentals={"status":"AVAILABLE","score":70,"data":{}}, risk={"status":"AVAILABLE","as_of":"2026-09-05"},
        trade_plan={"entry_low":95,"entry_high":105,"stop":90,"target":125,"risk_reward":2},
        valuation_inputs=professional_row(), evaluated_at="2026-09-05T20:00:00Z",
    )
    with_context = build_canonical_evaluation(**common)
    changed_context = build_canonical_evaluation(**{**common,"valuation_inputs":{**professional_row(),"analyst_target_mean":9999,"political_support":"BUY"}})
    assert with_context["atlas_valuation"]["professional_valuation_v2"]["status"] == PUBLISHED
    assert with_context["atlas_valuation"]["professional_v2_activation"] == "CANONICAL_TICKER_LEVEL"
    assert with_context["atlas_valuation"]["fair_value"] == 132
    assert with_context["atlas_valuation"]["legacy_v1_audit"]["canonical"] is False
    assert with_context["guidance"] == changed_context["guidance"]


def test_unpublished_v2_never_falls_back_to_legacy_v1_canonical_value():
    result = build_canonical_evaluation(
        ticker="MISS", evaluation_mode="ON_DEMAND",
        market_snapshot={"price":100,"provider_timestamp":"2026-09-05T20:00:00Z","latest_completed_session_valid":True},
        technical={"status":"AVAILABLE","state":"SETUP_FORMING","score":70,"as_of":"2026-09-05","feed_health":"HEALTHY","completed_bar":True,"evidence":{}},
        fundamentals={"status":"AVAILABLE","score":70,"data":{}}, risk={"status":"AVAILABLE","as_of":"2026-09-05"},
        trade_plan={"entry_low":95,"entry_high":105,"stop":90,"target":125,"risk_reward":2},
        valuation_inputs={"forward_eps":5,"atlas_valuation_justified_pe":25}, evaluated_at="2026-09-05T20:00:00Z",
    )
    valuation=result["atlas_valuation"]
    assert valuation["status"] == "DATA_UNAVAILABLE" and valuation["fair_value"] is None
    assert valuation["legacy_v1_audit"]["canonical"] is False
