import json
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "generate_buy_now_attrition_report.py"
SPEC = importlib.util.spec_from_file_location("generate_buy_now_attrition_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
classify = MODULE.classify
generate = MODULE.generate
valuation_attrition_causes = MODULE.valuation_attrition_causes
valuation_method_readiness = MODULE.valuation_method_readiness


def test_classification_precedence_and_population_mismatch(tmp_path):
    assert classify({"blockers": []})[2] == "LEGITIMATE_HIGH_UNCERTAINTY"
    assert classify({"blockers": ["CUSTOMER_PROJECTION_RECONCILIATION_FAILED"]})[2] == "SNAPSHOT_DEFECT"
    assert classify({"blockers": ["FCF_CANONICAL_RECONCILIATION_FAILURE"]})[2] == "LEGITIMATE_MISSING_EVIDENCE"

    pool = [{
        "ticker": "AAA",
        "canonical_investment_evaluation": {"guidance": {"state": "BUY_NOW"}},
        "publication_certification": {
            "certification_state": "REVIEW_REQUIRED",
            "customer_publication_allowed": False,
            "blockers": ["BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT"],
        },
    }]
    pool_path = tmp_path / "pool.json"
    provenance_path = tmp_path / "provenance.json"
    pool_path.write_text(json.dumps(pool), encoding="utf-8")
    provenance_path.write_text(json.dumps({"run_id": "immutable-run"}), encoding="utf-8")

    report = generate(pool_path, provenance_path, expected=27)

    assert report["diagnostic_only"] is True
    assert report["methodology_changed"] is False
    assert report["population_contract"] == {
        "expected_canonical_buy_now_count": 27,
        "observed_canonical_buy_now_count": 1,
        "status": "MISMATCH",
        "note": "Immutable source contains 1 canonical BUY NOW records, not 27; no records were inferred or synthesized.",
    }
    assert report["aggregate"]["classification_counts"] == {"LEGITIMATE_MISSING_EVIDENCE": 1}


def test_valuation_attrition_decomposes_existing_certification_evidence():
    evaluation = {
        "atlas_valuation": {
            "reason_codes": ["FORWARD_EPS_UNAVAILABLE"],
            "professional_valuation_v2": {"scenario_status": "DATA_UNAVAILABLE"},
        },
        "valuation_validation": {"valuation_evidence_strength": {
            "published_method_count": 0,
            "requirements": {"scenario_evidence_published": False},
            "peer_certification": {"status": "INSUFFICIENT"},
            "method_bridge_certification": {"methods": {"DCF": {"inputs": {
                "forecast_fcff": {"certified": False, "value_present": False},
                "diluted_shares": {"certified": False, "value_present": False},
                "net_debt": {"certified": False, "value_present": False},
            }}}},
        }},
    }
    causes = valuation_attrition_causes(evaluation, {"blockers": ["BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT"]})
    assert causes == [
        "INSUFFICIENT_CERTIFIED_METHODS", "PEER_EVIDENCE_INCOMPLETE",
        "SCENARIO_EVIDENCE_INCOMPLETE", "VALUATION_TIMESTAMP_MISSING",
        "ACCOUNTING_BRIDGE_INCOMPLETE", "SHARE_BRIDGE_INCOMPLETE",
        "EV_EQUITY_BRIDGE_INCOMPLETE", "PROVIDER_EVIDENCE_UNAVAILABLE",
    ]


def test_valuation_attrition_does_not_infer_causes_without_blocker():
    assert valuation_attrition_causes({}, {"blockers": []}) == []


def test_method_readiness_reports_route_applicability_and_missing_inputs_without_invention():
    evaluation={"atlas_valuation":{"professional_valuation_v2":{"models":[
        {"methodology_id":"VAL_EV_EBITDA_V1","status":"PUBLISHED"},
        {"methodology_id":"VAL_FCFF_DCF_V1","status":"INSUFFICIENT_INPUTS","reason":"EXPLICIT_FCFF_FORECAST_OR_CAPITAL_INPUTS_MISSING"},
        {"methodology_id":"VAL_DDM_GORDON_V1","status":"NOT_APPLICABLE","reason":"COMPANY_TYPE_NOT_ELIGIBLE"},
    ]}},"valuation_validation":{"valuation_evidence_strength":{"professionally_applicable_methods":["VAL_EV_EBITDA_V1","VAL_FCFF_DCF_V1"]}}}
    result=valuation_method_readiness(evaluation)
    assert result[0]["completed_after_fix"] is True
    assert result[1]["gap_type"]=="PROVIDER_OR_NORMALIZATION_GAP" and result[1]["eligible_for_route"] is True
    assert result[2]["gap_type"]=="GENUINE_NON_APPLICABILITY" and result[2]["eligible_for_route"] is False
