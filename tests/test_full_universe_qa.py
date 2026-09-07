from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from services.full_universe_qa import MISSING_REASONS, classify_missing, crawl_universe, write_json_report
from services.publication_governance import VERSION as GOVERNANCE_VERSION, promote_atomically, stage_candidate_artifacts


def row(ticker="T000", *, market_cap=1000.0, action="WAIT_FOR_CONFIRMATION"):
    evaluation = {
        "ticker": ticker,
        "methodology_version": "FOUNDER_GUIDANCE_V1",
        "market_snapshot": {"price": 10.0, "provider_timestamp": "2026-09-04T20:00:00+00:00", "market_session": "REGULAR"},
        "technical_confirmation": {"state": "CONSTRUCTIVE", "evidence": {"close": 10, "rsi": 52, "sma50": 9, "sma200": 8}},
        "trial_presentation_fields": {"latest_revenue": 100, "current_shares_outstanding": 100, "market_cap": market_cap},
        "opportunity": 70, "decision_confidence": 75, "component_coverage": 90,
        "guidance": {"state": action, "status": "AVAILABLE", "policy_version": "HOME_MULTI_THESIS_ACTION_V1", "opportunity_thesis": "QUALITY_GROWTH"},
        "actionability": {"status": "NOT_ACTIONABLE"},
        "trade_plan": {"entry_low": 9, "entry_high": 10, "stop_loss": 8, "trade_target_1": 12, "risk_reward": 2},
        "technical_quality": {"score": 70}, "fundamental_quality": {"score": 70}, "valuation_quality": {"score": 60},
        "risk_quality": {"score": 70}, "entry_quality": {"score": 60}, "volume_quality": {"score": 55},
    }
    return {"ticker": ticker, "company": ticker, "quote_type": "EQUITY", "canonical_investment_evaluation": evaluation,
            "publication_certification": {"version": GOVERNANCE_VERSION, "certification_state": "CERTIFIED",
                "customer_publication_allowed": True, "action_publication_eligible": True, "certified_action": action}}


def universe(**overrides):
    return [row(f"T{i:03d}", **overrides) for i in range(150)]


def test_150_name_crawler_and_lineage_sheets_pass():
    report = crawl_universe(universe(), run_id="test")
    assert report["gate"] == "PASS"
    assert report["summary"]["universe_count"] == 150
    assert len(report["sheets"]["Master"]) == 150
    assert list(report["sheets"]) == ["Master", "Financials", "Financial_Reconciliation", "Estimates", "Valuation_Models", "Valuation_Reconciliation", "Peer_Sets", "Source_Lineage", "Missing_Data", "Validation_Failures", "Street_Analyst", "Context", "Six_Pillar_QA", "Action_QA", "Run_Over_Run", "Customer_Surface_Audit", "Numerical_Anomalies", "ATLAS_vs_Street", "Screenshot_Index", "Universe_Summary"]
    assert report["summary"]["qa_engine_status"] == "OPERATIONAL"
    assert report["summary"]["dataset_certification_status"] == "PASS"


@pytest.mark.parametrize("context,expected", [
    ({"status": "THROTTLED"}, "PROVIDER_THROTTLED"),
    ({"mapping_missing": True}, "MAPPING_MISSING"),
    ({"period_mismatch": True}, "PERIOD_MISMATCH"),
    ({"unit_error": True}, "UNIT_ERROR"),
    ({"status": "NOT_APPLICABLE"}, "MODEL_NOT_APPLICABLE"),
    ({"secondary_unavailable": True}, "SECONDARY_VALIDATION_UNAVAILABLE"),
])
def test_missing_reason_classification(context, expected):
    result = classify_missing(field="x", context=context)
    assert result["reason"] == expected
    assert result["reason"] in MISSING_REASONS
    assert "recommended_remediation" in result


def test_market_cap_bridge_is_p0_and_blocks_publication():
    report = crawl_universe(universe(market_cap=4000), run_id="bad")
    assert report["gate"] == "FAIL"
    assert report["summary"]["severity_counts"]["P0"] == 150
    assert report["summary"]["market_cap_failure_count"] == 150


def test_ev_bridge_requires_and_reconciles_published_share_denominator():
    rows = universe()
    evaluation = rows[0]["canonical_investment_evaluation"]
    evaluation["atlas_valuation"] = {"professional_valuation_v2": {"status": "PUBLISHED", "atlas_base_fair_value": 11,
        "atlas_fair_value_low": 9, "atlas_fair_value_high": 13, "models": [{"methodology_id": "VAL_EV_EBITDA_V1",
        "status": "PUBLISHED", "value": 11, "key_assumptions": {"forward_ebitda": 100, "multiple": 10,
        "net_debt": -100, "diluted_shares": 100}}]}}
    report = crawl_universe(rows)
    reconciliation = report["sheets"]["Financial_Reconciliation"][0]
    assert reconciliation["ev_status"] == "PASS"
    assert not any(item["category"] == "EV_BRIDGE" for item in report["sheets"]["Validation_Failures"])


def test_p3_and_p4_are_nonblocking_but_p2_blocks():
    rows = universe()
    rows[0]["canonical_investment_evaluation"]["trial_presentation_fields"]["operating_profit_margin"] = 6600
    report = crawl_universe(rows)
    assert report["summary"]["severity_counts"]["P2"] == 1
    assert report["gate"] == "FAIL"


def test_p1_blocks_while_p3_p4_remain_nonblocking():
    rows = universe()
    valuation = {"status": "PUBLISHED", "atlas_base_fair_value": 20, "atlas_fair_value_low": 8,
                 "atlas_fair_value_high": 12, "models": []}
    rows[0]["canonical_investment_evaluation"]["atlas_valuation"] = {"professional_valuation_v2": valuation}
    assert crawl_universe(rows)["summary"]["severity_counts"]["P1"] == 1
    rows = universe()
    rows[0]["canonical_investment_evaluation"]["atlas_valuation"] = {"professional_valuation_v2": {
        "status": "PUBLISHED", "atlas_base_fair_value": 10, "atlas_fair_value_low": 8, "atlas_fair_value_high": 12,
        "models": [{"methodology_id": "VAL_FCFF_DCF_V1", "status": "PUBLISHED", "value": 10,
                    "key_assumptions": {"wacc": .06, "terminal_growth": .025, "terminal_value_pct_of_enterprise_value": .96}}]}}
    report = crawl_universe(rows)
    assert report["summary"]["severity_counts"]["P3"] > 0
    assert report["summary"]["severity_counts"]["P4"] == 1
    assert report["gate"] == "PASS"


def test_json_export_and_candidate_hash_integrity(tmp_path):
    report = crawl_universe(universe())
    output = tmp_path / "report.json"
    write_json_report(report, output)
    assert json.loads(output.read_text())["gate"] == "PASS"
    manifest = {"run_id": "x", "publication_gate_status": "PASS"}
    stage_candidate_artifacts({Path("market_full_scan.json"): universe()}, manifest=manifest, candidate_dir=tmp_path / "candidate")
    assert len(json.loads((tmp_path / "candidate/market_full_scan.json").read_text())) == 150


def test_atomic_promotion_and_last_known_good_restore_contract(tmp_path):
    production = tmp_path / "market_full_scan.json"
    production.write_text(json.dumps([{"ticker": "OLD"}]))
    promote_atomically({production: [{"ticker": "NEW"}]}, manifest={"run_id": "ok", "publication_gate_status": "PASS"},
                       manifest_path=tmp_path / "publication_manifest.json", audit_path=tmp_path / "publication_audit.jsonl")
    assert json.loads(production.read_text())[0]["ticker"] == "NEW"
    assert json.loads((tmp_path / ".market_full_scan.json.last_known_good").read_text())[0]["ticker"] == "OLD"
    with pytest.raises(RuntimeError, match="PUBLICATION_GATE_FAILED"):
        promote_atomically({production: [{"ticker": "BAD"}]}, manifest={"run_id": "bad", "publication_gate_status": "FAIL"},
                           manifest_path=tmp_path / "publication_manifest.json", audit_path=tmp_path / "publication_audit.jsonl")
    assert json.loads(production.read_text())[0]["ticker"] == "NEW"


def test_workflow_candidate_gate_contract_and_syntax():
    path = Path(".github/workflows/atlas_full_qa_certification.yml")
    source = path.read_text()
    assert source.startswith("name: ATLAS Full QA Certification\n")
    assert "workflow_run" in source and "workflow_dispatch" in source and "workflow_call" in source
    assert "schedule:" in source
    assert "atlas-scan-candidate-${{ steps.candidate.outputs.run_id }}" in source
    assert "--promote" in source and "atlas-full-qa-${{ github.run_id }}" in source
    assert source.index("Capture and validate desktop/mobile customer surfaces") < source.index("--promote")
    assert "agents.full_qa_visual_certification" in source
    assert "id: visual_qa" in source and "continue-on-error: true" in source
    assert "if: steps.visual_qa.outcome == 'failure'" in source
    overnight = Path(".github/workflows/overnight_scan.yml").read_text()
    assert "ATLAS_PUBLICATION_OUTPUT_MODE: \"CANDIDATE\"" in overnight
    assert "git push origin main" not in overnight


def test_xlsx_exporter_uses_artifact_tool_and_all_required_sheets():
    source = Path("scripts/export_full_qa_xlsx.mjs").read_text()
    assert '@oai/artifact-tool' in source
    for sheet in ("Master", "Financial_Reconciliation", "Valuation_Models", "Source_Lineage", "Universe_Summary", "Numerical_Anomalies", "Screenshot_Index"):
        assert sheet in Path("services/full_universe_qa.py").read_text()


def test_intu_and_nem_permanent_accounting_fixtures():
    rows = universe()
    rows[0] = row("INTU")
    rows[1] = row("NEM")
    for item in rows[:2]:
        item["canonical_investment_evaluation"]["trial_presentation_fields"].update({
            "basic_shares": 100, "diluted_shares": 101, "operating_cash_flow": 50,
            "capital_expenditure": -10, "free_cash_flow": 40, "cash_and_equivalents": 20,
            "total_debt": 30, "net_debt": 10,
        })
    report = crawl_universe(rows)
    fixtures = {item["ticker"]: item for item in report["sheets"]["Financial_Reconciliation"]}
    assert fixtures["INTU"]["fcf_status"] == "PASS"
    assert fixtures["NEM"]["net_debt_status"] == "PASS"
    financials = {item["ticker"]: item for item in report["sheets"]["Financials"]}
    assert financials["INTU"]["share_basis"] == "DILUTED"
    assert financials["NEM"]["diluted_shares"] == 101


def test_share_basis_inversion_is_blocking_p2():
    rows = universe()
    rows[0]["canonical_investment_evaluation"]["trial_presentation_fields"].update({"basic_shares": 110, "diluted_shares": 100})
    report = crawl_universe(rows)
    assert report["gate"] == "FAIL"
    assert any(item["category"] == "SHARE_BASIS" for item in report["sheets"]["Validation_Failures"])


def test_xlsx_export_smoke_when_artifact_tool_available(tmp_path):
    node_path = os.getenv("NODE_PATH")
    if not node_path:
        pytest.skip("artifact-tool runtime is not configured")
    report = crawl_universe(universe())
    input_path, output_path = tmp_path / "report.json", tmp_path / "report.xlsx"
    write_json_report(report, input_path)
    subprocess.run(["node", "scripts/export_full_qa_xlsx.mjs", str(input_path), str(output_path)], check=True)
    assert output_path.stat().st_size > 1000
