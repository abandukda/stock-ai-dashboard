from services.valuation_evidence_strength import (
    MULTI_METHOD_CORROBORATED, SINGLE_METHOD_HIGH_SUPPORT,
    SINGLE_METHOD_LIMITED_SUPPORT, certify_peer_multiple,
    certify_method_bridges, classify_valuation_evidence,
)


def _peer(ticker, multiple):
    return {"peer_ticker":ticker,"peer_company_name":f"{ticker} Corp","peer_sector":"Industrials",
            "peer_industry":"Distribution","peer_enterprise_value":multiple*100,
            "peer_ebitda":100,"peer_ev_ebitda":multiple,"multiple":multiple,"basis":"TTM",
            "as_of":"2026-09-09T00:00:00Z","evidence_as_of":"2026-09-09T00:00:00Z",
            "provider":"TWELVE_DATA","evidence_ids":[f"TD-{ticker}"],
            "comparability_status":"CERTIFIED","comparability_flags":[]}


def _single_professional(*, peer=True):
    peer_evidence={"included_peers":[_peer("A",8),_peer("B",10),_peer("C",12)],"minimum_peer_count":3}
    return {"status":"PUBLISHED","company_type":"PROFITABLE_OPERATING_COMPANY","valuation_confidence":75,
            "atlas_bear_case":80,"atlas_bull_case":130,"scenario_status":"PUBLISHED",
            "single_method_sufficiency":{"status":"APPROVED","methodology_id":"VAL_EV_EBITDA_V1","company_type":"PROFITABLE_OPERATING_COMPANY"},
            "valuation_diagnostics":{"flags":["MODEL_CONCENTRATION_SINGLE_METHOD"]},
            "valuation_explanation":{"primary_valuation_driver":"Peer multiple","secondary_valuation_driver":"No independent second valuation method is available for cross-checking.","biggest_valuation_uncertainty":"Peer comparability"},
            "models":[{"methodology_id":"VAL_EV_EBITDA_V1","status":"PUBLISHED","weight":1.0,
                       "key_assumptions":{"multiple":10,"forward_ebitda":100,"net_debt":50,"diluted_shares":10,
                                          "peer_evidence":peer_evidence if peer else None}}]}


def _validation():
    return {"checks":{name:{"status":"PASS"} for name in ("market_cap_bridge","ev_bridge","fcf_reconciliation","period_basis")}}


def _single_high_professional():
    value=_single_professional()
    value["company_type"]="HIGH_GROWTH_SOFTWARE"
    value["single_method_sufficiency"]={"status":"APPROVED","methodology_id":"VAL_FCFF_DCF_V1","company_type":"HIGH_GROWTH_SOFTWARE"}
    value["models"]=[{"methodology_id":"VAL_FCFF_DCF_V1","status":"PUBLISHED","weight":1.0,"key_assumptions":{
        "forecast_fcff":[100,110],"wacc":.09,"terminal_growth":.025,"total_debt":100,
        "cash_and_equivalents":50,"diluted_shares":10}}]
    return value


def test_two_independent_methods_are_corroborated():
    professional=_single_professional()
    professional["models"].append({"methodology_id":"VAL_FCFF_DCF_V1","status":"PUBLISHED","weight":.4,"key_assumptions":{
        "forecast_fcff":[100,110],"wacc":.09,"terminal_growth":.025,"total_debt":100,
        "cash_and_equivalents":50,"diluted_shares":10}})
    result=classify_valuation_evidence(professional,_validation())
    assert result["classification"]==MULTI_METHOD_CORROBORATED and result["strong_action_eligible"] is True


def test_single_method_requires_every_governed_high_support_condition():
    result=classify_valuation_evidence(_single_high_professional(),_validation())
    assert result["classification"]==SINGLE_METHOD_HIGH_SUPPORT and result["strong_action_eligible"] is True
    limited=_single_high_professional(); limited["valuation_confidence"]=55
    result=classify_valuation_evidence(limited,_validation())
    assert result["classification"]==SINGLE_METHOD_LIMITED_SUPPORT
    assert "valuation_confidence_high_support" in result["unmet_requirements"]


def test_missing_peer_lineage_prevents_single_method_high_support():
    result=classify_valuation_evidence(_single_professional(peer=False),_validation())
    assert result["classification"]==SINGLE_METHOD_LIMITED_SUPPORT
    assert result["requirements"]["peer_evidence_certified"] is False


def test_missing_peer_evidence_as_of_has_explicit_failure_semantics():
    professional=_single_professional()
    professional["models"][0]["key_assumptions"]["peer_evidence"]["included_peers"][0]["evidence_as_of"]=None
    check=certify_peer_multiple(professional["models"][0])
    assert check["status"]=="INSUFFICIENT"
    assert "PEER_VALUATION_AS_OF_UNAVAILABLE" in check["reason_codes"]


def test_generic_operating_company_cannot_gain_single_method_exception_by_declaration_alone():
    result=classify_valuation_evidence(_single_professional(),_validation())
    assert result["classification"]==SINGLE_METHOD_LIMITED_SUPPORT
    assert result["requirements"]["explicit_method_sufficiency"] is False


def test_peer_multiple_is_exactly_reproducible():
    model=_single_professional()["models"][0]
    result=certify_peer_multiple(model)
    assert result["status"]=="CERTIFIED"
    assert result["reproduced_median"]==result["used_multiple"]==10


def test_method_bridge_aggregation_ignores_unpublished_method_inputs():
    professional=_single_high_professional()
    result=certify_method_bridges(professional,_validation())
    assert result["status"]=="CERTIFIED"
    assert set(result["methods"])=={"VAL_FCFF_DCF_V1"}
    assert "dividend_next" not in result["methods"]["VAL_FCFF_DCF_V1"]["inputs"]


def test_required_published_method_bridge_input_fails_explicitly():
    professional=_single_high_professional()
    professional["models"][0]["key_assumptions"]["wacc"]=None
    result=certify_method_bridges(professional,_validation())
    assert result["status"]=="INSUFFICIENT"
    assert result["methods"]["VAL_FCFF_DCF_V1"]["inputs"]["wacc"]["reason"]=="VALUATION_BRIDGE_INPUT_UNCERTIFIED"
