import pytest
import statistics

from services.professional_valuation_evidence import (
    apply_peer_multiple_evidence, build_operating_forecast, enrich_professional_inputs,
)
from engines.professional_valuation_v2 import value_company
from services.valuation_evidence_strength import certify_peer_multiple


def dossier():
    income=[]; cash=[]
    for year,revenue in ((2025,1000),(2024,900),(2023,800)):
        income.append({"fiscal_date":f"{year}-12-31","sales":revenue,"ebit":revenue*.2,"pretax_income":100,"income_tax":21})
        cash.append({"fiscal_date":f"{year}-12-31","operating_activities":{"depreciation":revenue*.04,"accounts_receivable":-10,"accounts_payable":5,"other_assets_liabilities":0},"investing_activities":{"capital_expenditures":-revenue*.05},"interest_paid":20})
    return {"families":{"income_statement":{"payload":{"income_statement":income}},"cash_flow":{"payload":{"cash_flow":cash}}}}


def row(ticker="AAA", industry="Software", pe=20):
    return {"ticker":ticker,"company":f"{ticker} Corp","industry":industry,"sector":"Technology","forward_revenue":1200,
            "forward_estimate_evidence":{"revenue":{"avg_estimate":1200,"low_estimate":1100,"high_estimate":1350,"sales_growth":.2}},
            "twelve_trial_dossier":dossier(),"total_debt":200,"cash_and_equivalents":100,
            "market_cap":pe*5*100,"diluted_shares":100,"beta":1.1,"current_price":pe*5,
            "free_cash_flow":pe*50,
            "professional_evidence_as_of":"2026-09-09T00:00:00Z",
            "professional_evidence_lineage":{"provider":"FINNHUB","evidence_ids":[f"FH-{ticker}"],"fields":{
                "market_cap":{"evidence_id":f"FH-MC-{ticker}","unit":"USD","currency":"USD","as_of":"2026-09-09T00:00:00Z"},
                "free_cash_flow":{"evidence_id":f"FH-FCF-{ticker}","unit":"USD","currency":"USD","period":"2025-12-31"},
                "diluted_shares":{"evidence_id":f"FH-SH-{ticker}","unit":"SHARES","period":"2025-12-31"},
            }},
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
    assert all(item["peer_ev_ebitda"] == pytest.approx(
        item["peer_enterprise_value"] / item["peer_ebitda"]
    ) for item in ev["included_peers"])


def test_peer_multiples_are_derived_without_provider_precomputed_values():
    rows = [row("A", pe=10), row("B", pe=20), row("C", pe=30), row("D", pe=40)]
    for item in rows:
        item.pop("provider_forward_pe", None)
        item.pop("provider_ev_ebitda", None)
        item.pop("provider_p_fcf", None)
        item["professional_evidence_lineage"]["provider"] = "FINNHUB"
    evidence = apply_peer_multiple_evidence(rows)[0]["justified_forward_pe_peer_evidence"]
    assert evidence["published_median"] == 30
    assert evidence["provider"] == "FINNHUB"
    assert all(item["source_lineage"]["method"] == "PRICE_DIVIDED_BY_FORWARD_EPS"
               for item in evidence["included_peers"])


def test_peer_evidence_contains_no_hard_coded_provider_identity():
    import inspect
    import services.professional_valuation_evidence as module
    assert '"provider":"TWELVE_DATA"' not in inspect.getsource(module.apply_peer_multiple_evidence)


def test_peer_evidence_serialization_is_independent_of_input_order():
    rows = [row("TARGET", pe=10), row("C", pe=20), row("A", pe=30), row("B", pe=40)]
    forward = {item["ticker"]: item for item in apply_peer_multiple_evidence(rows)}["TARGET"]
    reverse = {item["ticker"]: item for item in apply_peer_multiple_evidence(list(reversed(rows)))}["TARGET"]
    assert forward["justified_p_fcf_peer_evidence"] == reverse["justified_p_fcf_peer_evidence"]
    assert forward["justified_p_fcf_peer_evidence"]["final_peer_set"] == ["A", "B", "C"]


def test_provider_neutral_p_fcf_route_publishes_and_certifies_with_complete_peer_evidence():
    prepared = apply_peer_multiple_evidence([
        row("A", pe=10), row("B", pe=20), row("C", pe=30), row("D", pe=40)
    ])
    valuation = value_company(prepared[0])
    model = next(item for item in valuation["models"] if item["methodology_id"] == "VAL_P_FCF_V1")
    assert model["status"] == "PUBLISHED"
    assert model["value"] == pytest.approx(prepared[0]["free_cash_flow"] * prepared[0]["justified_p_fcf"] /
                                           prepared[0]["diluted_shares"])
    certification = certify_peer_multiple(model)
    assert certification["status"] == "CERTIFIED"
    assert certification["included_peer_count"] == 3


def test_sector_fallback_is_audited_but_does_not_disqualify_certified_peers():
    subject = row("TGT", industry="Unique Industry", pe=10)
    peers = [row(ticker, industry=f"Peer Industry {index}", pe=pe)
             for index, (ticker, pe) in enumerate((("P1", 20), ("P2", 30), ("P3", 40)), start=1)]
    prepared = apply_peer_multiple_evidence([subject, *peers])
    evidence = prepared[0]["justified_p_fcf_peer_evidence"]
    assert evidence["selection_rule"] == "same sector fallback"
    assert all(item["comparability_flags"] == ["SECTOR_FALLBACK"] for item in evidence["included_peers"])
    model = next(item for item in value_company(prepared[0])["models"]
                 if item["methodology_id"] == "VAL_P_FCF_V1")
    certification = certify_peer_multiple(model)
    assert certification["status"] == "CERTIFIED"
    assert certification["informational_comparability_flags"] == ["SECTOR_FALLBACK"]
    assert certification["disqualifying_comparability_flags"] == []


def test_sector_fallback_keeps_scale_and_security_mismatch_exclusions():
    subject = row("TGT", industry="Unique Industry", pe=10)
    subject.update({"security_type": "Common Stock", "market_cap": 10_000})
    valid = []
    for ticker, cap in (("P1", 9_000), ("P2", 11_000), ("P3", 12_000)):
        item = row(ticker, industry="Other", pe=20)
        item.update({"security_type": "Common Stock", "market_cap": cap})
        valid.append(item)
    scale = row("TINY", industry="Other", pe=20)
    scale.update({"security_type": "Common Stock", "market_cap": 100})
    mismatch = row("ETF", industry="Other", pe=20)
    mismatch.update({"security_type": "ETF", "market_cap": 10_000})
    evidence = apply_peer_multiple_evidence([subject, *valid, scale, mismatch])[0][
        "justified_p_fcf_peer_evidence"
    ]
    reasons = {item["peer_ticker"]: item["exclusion_reason"] for item in evidence["excluded_peers"]}
    assert reasons["TINY"] == "SCALE_GAP_OVER_10X"
    assert reasons["ETF"] == "SECURITY_TYPE_MISMATCH"
    assert set(evidence["final_peer_set"]) == {"P1", "P2", "P3"}


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda model: model["key_assumptions"].update(multiple=999), "PEER_MEDIAN_RECONCILIATION_FAILED"),
        (lambda model: model["key_assumptions"]["peer_evidence"]["included_peers"][0].update(
            peer_fcf_currency="EUR"), "PEER_P_FCF_RECONCILIATION_FAILED"),
        (lambda model: model["key_assumptions"]["peer_evidence"]["included_peers"][0].update(
            peer_fcf_unit=""), "PEER_VALUATION_LINEAGE_INCOMPLETE"),
        (lambda model: model["key_assumptions"]["peer_evidence"]["included_peers"][0].update(
            evidence_ids=[]), "PEER_VALUATION_LINEAGE_INCOMPLETE"),
    ],
)
def test_peer_certification_still_fails_closed_on_noninformational_defects(mutation, reason):
    prepared = apply_peer_multiple_evidence([
        row("A", pe=10), row("B", pe=20), row("C", pe=30), row("D", pe=40)
    ])
    model = next(item for item in value_company(prepared[0])["models"]
                 if item["methodology_id"] == "VAL_P_FCF_V1")
    mutation(model)
    result = certify_peer_multiple(model)
    assert result["status"] == "INSUFFICIENT"
    assert reason in result["reason_codes"]


def test_p_fcf_peer_is_rejected_when_currency_or_lineage_is_incomplete():
    rows = [row("A", pe=10), row("B", pe=20), row("C", pe=30), row("D", pe=40)]
    rows[1]["professional_evidence_lineage"]["fields"]["free_cash_flow"]["currency"] = "EUR"
    rows[2]["professional_evidence_lineage"]["fields"]["free_cash_flow"].pop("evidence_id")
    evidence = apply_peer_multiple_evidence(rows)[0]["justified_p_fcf_peer_evidence"]
    reasons = {item["peer_ticker"]: item["exclusion_reason"] for item in evidence["excluded_peers"]}
    assert reasons["B"] == "P_FCF_CURRENCY_MISMATCH"
    assert reasons["C"] == "P_FCF_EVIDENCE_LINEAGE_INCOMPLETE"


def test_insufficient_peer_evidence_reports_candidate_counts_without_relaxing_minimum():
    evidence = apply_peer_multiple_evidence([row("A"), row("B"), row("C")])[0][
        "justified_p_fcf_peer_evidence"
    ]
    assert evidence["industry_candidate_count"] == 2
    assert evidence["industry_valid_count"] == 2
    assert evidence["minimum_peer_count"] == 3
    assert evidence["sufficiency_status"] == "INSUFFICIENT_CERTIFIED_PEER_COUNT"


def test_listing_form_is_normalized_and_scale_outlier_is_excluded():
    subject=row("TGT"); subject.update({"security_type":"Common Stock","market_cap":10_000})
    peers=[]
    for ticker,security,cap in (("ADR1","American Depositary Receipt",9_000),("ADS1","ADS",11_000),("COM1","Common Stock",12_000),("TINY","Common Stock",100)):
        item=row(ticker); item.update({"security_type":security,"market_cap":cap}); peers.append(item)
    evidence=apply_peer_multiple_evidence([subject,*peers])[0]["justified_forward_pe_peer_evidence"]
    assert set(evidence["final_peer_set"])=={"ADR1","ADS1","COM1"}
    assert any(item["peer_ticker"]=="TINY" and item["exclusion_reason"]=="SCALE_GAP_OVER_10X" for item in evidence["excluded_peers"])
