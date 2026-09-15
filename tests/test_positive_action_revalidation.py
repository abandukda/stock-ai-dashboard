from copy import deepcopy

from services.positive_action_revalidation import revalidate_buy_now
from services.publication_governance import certify_record
from engines.professional_valuation_v2 import value_company
from services.valuation_evidence_strength import classify_valuation_evidence


def _peer(ticker, multiple):
    return {"peer_ticker":ticker,"peer_company_name":f"{ticker} Corp","peer_sector":"Industrials",
            "peer_industry":"Medical Devices","peer_enterprise_value":multiple*100,
            "peer_ebitda":100,"peer_ev_ebitda":multiple,"multiple":multiple,"basis":"TTM",
            "evidence_as_of":"2026-09-08T20:00:00Z","provider":"TWELVE_DATA",
            "evidence_ids":[f"TD-{ticker}"],"comparability_status":"CERTIFIED","comparability_flags":[]}


def _reachable_multi_method_valuation():
    peers={"included_peers":[_peer("A",8),_peer("B",10),_peer("C",12)],"minimum_peer_count":3}
    professional=value_company({"ticker":"TEST","price":100,"industry":"Medical Devices",
        "forward_eps":6,"forward_eps_period":"FY2027","justified_forward_pe":10,
        "justified_forward_pe_basis":"certified peers","justified_forward_pe_peer_evidence":peers,
        "forward_ebitda":1_000,"justified_ev_ebitda":10,"justified_ev_ebitda_basis":"certified peers",
        "justified_ev_ebitda_peer_evidence":peers,"diluted_shares":100,"total_debt":100,
        "cash_and_equivalents":100})
    validation={"customer_publication_allowed":True,"certification_state":"CERTIFIED",
        "checks":{name:{"status":"PASS"} for name in ("market_cap_bridge","ev_bridge","fcf_reconciliation","period_basis")},
        "input_lineage":{"forward_eps":{"evidence_id":"TD-EPS"},"ebitda":{"evidence_id":"TD-EBITDA"},
                         "diluted_shares":{"evidence_id":"TD-SHARES"}}}
    validation["valuation_evidence_strength"]=classify_valuation_evidence(professional,validation)
    assert sum(model["status"]=="PUBLISHED" for model in professional["models"]) == 2
    assert validation["valuation_evidence_strength"]["strong_action_eligible"] is True
    return professional,validation


def buy_evaluation():
    professional,validation=_reachable_multi_method_valuation()
    return {
        "decision_digest": "decision-1", "evidence_as_of": {"market": "2026-09-08T20:00:00Z"},
        "guidance": {"state": "BUY_NOW", "opportunity_thesis": "QUALITY_GROWTH"},
        "opportunity_thesis": "QUALITY_GROWTH", "opportunity": 85,
        "decision_confidence": 82, "component_coverage": 95,
        "market_snapshot": {"price": 100, "provider_timestamp": "2026-09-08T20:00:00Z",
                            "evidence_id": "TD-MKT", "latest_completed_session_valid": True},
        "technical_confirmation": {"status": "AVAILABLE", "completed_bar": True, "fingerprint": "tech-1"},
        "volume_intelligence": {"status": "AVAILABLE", "completed_daily_evidence": True,
                                "valid_daily_volume_baseline": True, "evidence_id": "TD-VOL"},
        "fundamentals": {"status": "AVAILABLE", "evidence_ids": ["FMP-FUND"]},
        "risk": {"status": "AVAILABLE", "as_of": "2026-09-08T20:00:00Z", "primary_risk": "Execution"},
        "trade_plan": {"entry_low": 95, "entry_high": 101, "stop_loss": 90},
        "atlas_valuation": {"professional_valuation_v2": professional},
        "valuation_validation": validation,
    }


def test_buy_now_passes_only_after_exact_snapshot_revalidation():
    result = revalidate_buy_now(buy_evaluation())
    assert result["status"] == "BUY_NOW_REVALIDATED"
    assert result["source_decision_digest"] == "decision-1"
    assert result["exact_snapshot_digest"]


def test_missing_critical_buy_evidence_remains_pending_without_changing_action():
    evaluation = buy_evaluation()
    evaluation["technical_confirmation"]["completed_bar"] = False
    result = revalidate_buy_now(evaluation)
    assert result["status"] == "BUY_NOW_PENDING_REVALIDATION"
    assert "TECHNICAL_SNAPSHOT_NOT_REVALIDATED" in result["blockers"]
    assert result["canonical_action"] == "BUY_NOW"


def test_single_method_limited_support_withholds_buy_now_without_changing_canonical_action():
    evaluation = buy_evaluation()
    professional = value_company({"ticker":"TEST","price":100,"industry":"Medical Devices",
                                  "forward_eps":6,"forward_eps_period":"FY2027","justified_forward_pe":22,
                                  "justified_forward_pe_basis":"certified history"})
    evaluation["atlas_valuation"]["professional_valuation_v2"] = professional
    strength = classify_valuation_evidence(professional, {"checks": {name:{"status":"PASS"} for name in ("market_cap_bridge","ev_bridge","fcf_reconciliation","period_basis")}})
    evaluation["valuation_validation"]["valuation_evidence_strength"] = strength
    result = revalidate_buy_now(evaluation)
    assert result["status"] == "BUY_NOW_PENDING_REVALIDATION"
    assert result["canonical_action"] == "BUY_NOW"
    assert "BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT" in result["blockers"]
    assert "BUY_NOW_METHOD_CORROBORATION_INSUFFICIENT" in result["blockers"]
    assert "BUY_NOW_SINGLE_METHOD_STRONG_ACTION_POLICY_RETIRED" in result["blockers"]


def test_publication_component_carries_single_method_buy_now_blocker():
    evaluation = buy_evaluation()
    evaluation["valuation_validation"]["valuation_evidence_strength"] = {
        "classification":"SINGLE_METHOD_LIMITED_SUPPORT","strong_action_eligible":False,
    }
    evaluation["positive_action_revalidation"] = revalidate_buy_now(evaluation)
    result = certify_record({"ticker":"TEST","price":100,"current_shares_outstanding":10,"market_cap":1000,
                             "canonical_investment_evaluation":evaluation})
    component=result["components"]["positive_action_revalidation"]
    assert "BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT" in component["blockers"]
    assert result["customer_publication_allowed"] is False


def test_professional_v2_to_publication_chain_exposes_exact_single_method_blockers():
    evaluation = buy_evaluation()
    professional = value_company({"ticker":"TEST","price":100,"industry":"Medical Devices",
                                  "forward_eps":6,"forward_eps_period":"FY2027","justified_forward_pe":22,
                                  "justified_forward_pe_basis":"certified history"})
    validation = {"customer_publication_allowed":True,
                  "checks":{name:{"status":"PASS"} for name in ("market_cap_bridge","ev_bridge","fcf_reconciliation","period_basis")}}
    validation["valuation_evidence_strength"] = classify_valuation_evidence(professional, validation)
    evaluation["atlas_valuation"]["professional_valuation_v2"] = professional
    evaluation["valuation_validation"] = validation
    evaluation["positive_action_revalidation"] = revalidate_buy_now(evaluation)
    certified = certify_record({"ticker":"TEST","canonical_investment_evaluation":evaluation})
    blockers = certified["components"]["positive_action_revalidation"]["blockers"]
    assert "BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT" in blockers
    assert "BUY_NOW_VALUATION_CONFIDENCE_INSUFFICIENT" in blockers
    assert "BUY_NOW_SINGLE_METHOD_STRONG_ACTION_POLICY_RETIRED" in blockers


def test_professional_v2_multi_method_path_reaches_buy_revalidation_and_publication_component():
    evaluation=buy_evaluation()
    evaluation["positive_action_revalidation"]=revalidate_buy_now(evaluation)
    assert evaluation["positive_action_revalidation"]["status"]=="BUY_NOW_REVALIDATED"
    certified=certify_record({"ticker":"TEST","canonical_investment_evaluation":evaluation})
    component=certified["components"]["positive_action_revalidation"]
    assert component["state"]=="CERTIFIED" and component["blockers"]==[]


def test_material_street_divergence_requires_scenario_review_not_anchoring():
    evaluation = buy_evaluation()
    professional = evaluation["atlas_valuation"]["professional_valuation_v2"]
    professional["atlas_base_fair_value"] = 200
    professional["valuation_diagnostics"]["street_target_context"] = 100
    professional["sensitivity"] = []
    professional["scenario_status"] = "INSUFFICIENT_ECONOMIC_SCENARIO_INPUTS"
    pending = revalidate_buy_now(evaluation)
    assert pending["street_divergence_review"] == "STRONG_NUMERICAL_QA"
    assert pending["canonical_action"] == "BUY_NOW"
    # Street remains contextual: the canonical value and Action are untouched.
    assert professional["atlas_base_fair_value"] == 200


def test_non_buy_action_does_not_require_positive_revalidation():
    evaluation = deepcopy(buy_evaluation())
    evaluation["guidance"]["state"] = "WAIT_FOR_CONFIRMATION"
    assert revalidate_buy_now(evaluation)["status"] == "NOT_REQUIRED"


def test_publication_rejects_stale_buy_revalidation_digest():
    evaluation = buy_evaluation()
    evaluation["positive_action_revalidation"] = revalidate_buy_now(evaluation)
    evaluation["positive_action_revalidation"]["source_decision_digest"] = "older-snapshot"
    result = certify_record({"ticker": "TEST", "canonical_investment_evaluation": evaluation})
    component = result["components"]["positive_action_revalidation"]
    assert component["state"] == "REVIEW_REQUIRED"
    assert component["blockers"] == ["BUY_NOW_REVALIDATION_SNAPSHOT_MISMATCH"]
    assert result["customer_publication_allowed"] is False
