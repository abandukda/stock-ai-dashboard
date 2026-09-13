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
