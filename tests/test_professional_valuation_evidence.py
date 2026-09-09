import pytest
import statistics

from services.professional_valuation_evidence import (
    apply_peer_multiple_evidence, build_operating_forecast, enrich_professional_inputs,
)


def dossier():
    income=[]; cash=[]
    for year,revenue in ((2025,1000),(2024,900),(2023,800)):
        income.append({"fiscal_date":f"{year}-12-31","sales":revenue,"ebit":revenue*.2,"pretax_income":100,"income_tax":21})
        cash.append({"fiscal_date":f"{year}-12-31","operating_activities":{"depreciation":revenue*.04,"accounts_receivable":-10,"accounts_payable":5,"other_assets_liabilities":0},"investing_activities":{"capital_expenditures":-revenue*.05},"interest_paid":20})
    return {"families":{"income_statement":{"payload":{"income_statement":income}},"cash_flow":{"payload":{"cash_flow":cash}}}}


def row(ticker="AAA", industry="Software", pe=20):
    return {"ticker":ticker,"industry":industry,"sector":"Technology","forward_revenue":1200,
            "forward_estimate_evidence":{"revenue":{"avg_estimate":1200,"low_estimate":1100,"high_estimate":1350,"sales_growth":.2}},
            "twelve_trial_dossier":dossier(),"total_debt":200,"cash_and_equivalents":100,
            "market_cap":2000,"diluted_shares":100,"beta":1.1,"provider_forward_pe":pe,
            "provider_ev_ebitda":12,
            "professional_evidence_as_of":"2026-09-09T00:00:00Z",
            "professional_evidence_lineage":{"evidence_ids":[f"TD-{ticker}"]},
            "forward_ebitda":250,"forward_eps":5,"forward_eps_period":"2027-12-31"}


def test_fcff_forecast_is_reproducible_and_exposes_historical_ratio_lineage():
    first=build_operating_forecast(row()); second=build_operating_forecast(row())
    assert first==second and first["status"]=="ELIGIBLE_COMPLETE"
    assert len(first["forecast_fcff"])==5
    assert first["source_periods"]==["2025-12-31","2024-12-31","2023-12-31"]


def test_wacc_and_scenarios_use_versioned_market_and_company_evidence():
    result=enrich_professional_inputs(row())
    assert result["wacc"] > result["terminal_growth"]
    assert result["market_assumption_lineage"]["risk_free_rate_source"]
    assert result["valuation_scenarios"]["bear"]["wacc"] == result["wacc"]
    assert result["valuation_scenarios"]["bull"]["wacc"] == result["wacc"]
    assert result["market_assumption_lineage"]["risk_free_rate_maturity"] == "10-year nominal CMT"
    assert "floored at maturity-matched Treasury" in result["cost_of_debt_method"]
    assert result["cost_of_debt"] >= result["risk_free_rate"]
    assert result["equity_weight"] + result["debt_weight"] == pytest.approx(1)


def test_peer_set_requires_three_comparables_and_is_deterministic():
    rows=apply_peer_multiple_evidence([row("A",pe=10),row("B",pe=20),row("C",pe=30),row("D",pe=40)])
    a=rows[0]
    assert a["justified_forward_pe"]==30
    assert a["deterministic_peer_set"]["peers"]==["B","C","D"]
    assert "Street" not in a["justified_forward_pe_basis"]
    ev=a["justified_ev_ebitda_peer_evidence"]
    assert ev["published_median"]==statistics.median(item["peer_ev_ebitda"] for item in ev["included_peers"])
    assert all(item["peer_enterprise_value"]==2100 and item["peer_ebitda"]==250 for item in ev["included_peers"])
