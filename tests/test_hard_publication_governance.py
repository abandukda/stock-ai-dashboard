from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from engines.professional_valuation_v2 import classify_company, value_company
from services.atlas_view_summary import build_summary_payload
from services.publication_governance import (
    build_manifest, certify_record, certify_rows, promote_atomically,
    run_over_run_anomalies,
)


ROOT = Path(__file__).resolve().parents[1]


def _production_row(ticker="UBER"):
    rows = json.loads((ROOT / "market_full_scan.json").read_text())
    return deepcopy(next(row for row in rows if row.get("ticker") == ticker))


def _certifiable_row(ticker="UBER"):
    row = _production_row(ticker)
    evaluation = row["canonical_investment_evaluation"]
    fields = evaluation["trial_presentation_fields"]
    fields["current_shares_outstanding"] = fields["market_cap"] / evaluation["market_snapshot"]["price"]
    fields["capital_expenditures"] = fields["operating_cash_flow"] - fields["free_cash_flow"]
    evaluation.pop("valuation_validation", None)
    return row


def _observed(row):
    value = row["canonical_investment_evaluation"]["market_snapshot"]["provider_timestamp"]
    return datetime.fromisoformat(value.replace("Z", "+00:00")) + timedelta(days=1)


def test_valid_customer_action_requires_whole_record_certification():
    row = _certifiable_row()
    result = certify_record(row, now=_observed(row))
    assert result["certification_state"] == "CERTIFIED"
    assert result["certified_action"] == row["canonical_investment_evaluation"]["guidance"]["state"]


def test_validation_failure_withholds_action_and_never_maps_to_investment_opinion():
    row = _production_row()
    row["canonical_investment_evaluation"]["market_snapshot"]["price"] = -1
    result = certify_record(row, now=_observed(row))
    assert result["certification_state"] == "REVIEW_REQUIRED"
    assert result["certified_action"] is None
    assert result["action_publication_eligible"] is False
    assert "WATCH" not in json.dumps(result)


def test_market_cap_share_bridge_failure_is_withheld_before_customer_curation():
    row = _certifiable_row("NEM")
    fields = row["canonical_investment_evaluation"]["trial_presentation_fields"]
    fields["current_shares_outstanding"] = fields["market_cap"] / row["canonical_investment_evaluation"]["market_snapshot"]["price"] * 0.80
    fields["share_structure"] = {}
    result = certify_record(row, now=_observed(row))
    assert result["certification_state"] == "REVIEW_REQUIRED"
    assert result["customer_publication_allowed"] is False
    assert result["components"]["accounting_bridge"]["blockers"] == ["MARKET_CAP_RECONCILIATION_FAILED"]


def test_ticker_local_failure_does_not_withhold_healthy_ticker():
    healthy, broken = _certifiable_row(), _certifiable_row()
    broken["ticker"] = "WRONG"
    certified = certify_rows([healthy, broken], now=_observed(healthy))
    assert certified[0]["publication_certification"]["customer_publication_allowed"] is True
    assert certified[1]["publication_certification"]["customer_publication_allowed"] is False


def test_manifest_blocks_systemic_provider_failure_and_hashes_candidates():
    rows = certify_rows([_production_row()], now=_observed(_production_row()))
    manifest = build_manifest(rows, run_id="r1", generated_at="2026-09-06T00:00:00Z",
                              artifact_payloads={"market_full_scan.json": rows},
                              provider_status={"status": "DATA_UNAVAILABLE"})
    assert manifest["publication_gate_status"] == "FAIL"
    assert manifest["artifact_hashes"]["market_full_scan.json"]


def test_manifest_does_not_duplicate_bulk_evaluations_or_diagnostics():
    rows = certify_rows([_certifiable_row("NEM")], now=_observed(_certifiable_row("NEM")))
    manifest = build_manifest(
        rows,
        run_id="r1",
        generated_at="2026-09-06T00:00:00Z",
        artifact_payloads={"market_full_scan.json": rows},
        provider_status={"status": "AVAILABLE", "provider_calls": 42, "evaluations": [{"large": "payload"}], "diagnostics": [{"large": "payload"}]},
    )
    assert manifest["provider_status"] == {"status": "AVAILABLE", "provider_calls": 42}


def test_large_full_evaluation_artifact_uses_compact_json(tmp_path):
    from services.publication_governance import stage_candidate_artifacts

    stage_candidate_artifacts(
        {tmp_path / "full_evaluation_pool.json": [{"ticker": "TEST", "nested": {"value": 1}}]},
        manifest={"publication_gate_status": "PASS"},
        candidate_dir=tmp_path / "candidate",
    )
    payload = (tmp_path / "candidate" / "full_evaluation_pool.json").read_text()
    assert payload == '[{"ticker":"TEST","nested":{"value":1}}]\n'


def test_atomic_promotion_retains_last_known_good_on_gate_failure(tmp_path):
    production = tmp_path / "market_full_scan.json"
    production.write_text('{"old": true}\n')
    with pytest.raises(RuntimeError, match="PUBLICATION_GATE_FAILED"):
        promote_atomically({production: {"new": True}}, manifest={"publication_gate_status": "FAIL"},
                           manifest_path=tmp_path / "manifest.json", audit_path=tmp_path / "audit.jsonl")
    assert json.loads(production.read_text()) == {"old": True}


def test_atomic_promotion_writes_manifest_and_immutable_audit(tmp_path):
    production = tmp_path / "market_full_scan.json"
    production.write_text('{"old": true}\n')
    manifest = {"publication_gate_status": "PASS", "run_id": "r2"}
    promote_atomically({production: {"new": True}}, manifest=manifest,
                       manifest_path=tmp_path / "manifest.json", audit_path=tmp_path / "audit.jsonl")
    assert json.loads(production.read_text()) == {"new": True}
    assert json.loads((tmp_path / "manifest.json").read_text())["run_id"] == "r2"
    assert "ATOMIC_PUBLICATION" in (tmp_path / "audit.jsonl").read_text()


def test_llm_payload_rejects_uncertified_valuation_and_fundamentals():
    card = {
        "ticker": "TEST", "company": "Test", "display_price": 100,
        "atlas_fair_value": 999, "atlas_valuation_status": "PUBLISHED", "atlas_expected_return": 899,
        "fundamentals_evidence": {"revenue_growth": 500}, "company_evidence": {"forward_eps": 99},
        "publication_certification": {"components": {
            "market": {"state": "CERTIFIED"}, "valuation": {"state": "REVIEW_REQUIRED"},
            "fundamentals": {"state": "REVIEW_REQUIRED"},
        }},
    }
    payload = build_summary_payload(card)
    assert payload["atlas_fair_value"] is None
    assert payload["fundamentals"] == {}
    assert payload["company_evidence"] == {}


def test_nem_permanently_routes_as_commodity_and_excludes_pe():
    row = _production_row("NEM")
    fields = row["canonical_investment_evaluation"]["trial_presentation_fields"]
    assert classify_company({**row, **fields}) == "COMMODITY_PRODUCER"
    from services.professional_valuation_evidence import enrich_professional_inputs
    valuation = value_company(enrich_professional_inputs({**row, **fields}))
    pe = next(model for model in valuation["models"] if model["methodology_id"] == "VAL_FORWARD_PE_V1")
    assert pe["status"] == "NOT_APPLICABLE"


def test_provider_raw_to_canonical_lineage_and_forward_period_selection():
    from services.twelve_data_trial_intelligence import normalize_trial_dossier
    dossier = {"observed_at": "2026-09-06T00:00:00Z", "evidence_ids": ["e1"], "families": {
        "statistics": {"payload": {"statistics": {"financials": {"income_statement": {"revenue_ttm": 1000}}, "stock_statistics": {"shares_outstanding": 10}}}},
        "income_statement": {"payload": {"income_statement": [{"fiscal_date": "2025-12-31", "sales": 900}]}},
        "earnings_estimate": {"payload": {"earnings_estimate": [
            {"period": "current_quarter", "date": "2026-09-30", "avg_estimate": 1},
            {"period": "next_year", "date": "2027-12-31", "avg_estimate": 5, "analyst_count": 12},
        ]}},
        "revenue_estimate": {"payload": {"revenue_estimate": []}},
    }}
    result = normalize_trial_dossier({"ticker": "ABC"}, dossier)
    lineage = result["professional_evidence_lineage"]["fields"]
    assert lineage["latest_revenue"]["raw_field"] == "statistics.financials.income_statement.revenue_ttm"
    assert lineage["latest_revenue"]["canonical_field"] == "latest_revenue"
    assert result["forward_eps"] == 5 and result["forward_eps_period"] == "2027-12-31"
    assert lineage["forward_eps"]["transformation"] == "SELECT_NEXT_YEAR_THEN_CURRENT_YEAR"


def test_acquisition_dossier_preserves_observation_timestamp(monkeypatch):
    from services.twelve_data_trial_intelligence import acquire_twelve_trial_dossiers
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"ok": True}
    result = acquire_twelve_trial_dossiers(
        ["ABC"], get=lambda *args, **kwargs: Response(), endpoints=("profile",),
        environ={"ATLAS_DATA_MODE": "INTERNAL_TRIAL", "TWELVE_DATA_API_KEY": "redacted"},
    )
    assert result["dossiers"]["ABC"]["observed_at"] == result["observed_at"]


def test_run_over_run_anomaly_requires_attributable_evidence_change():
    old = _production_row()
    new = deepcopy(old)
    old_fields = old["canonical_investment_evaluation"]["trial_presentation_fields"]
    new_fields = new["canonical_investment_evaluation"]["trial_presentation_fields"]
    old_fields["latest_revenue"] = 100
    new_fields["latest_revenue"] = 200
    old["professional_evidence_lineage"] = {"evidence_ids": ["same"]}
    new["professional_evidence_lineage"] = {"evidence_ids": ["same"]}
    anomalies = run_over_run_anomalies([new], [old])
    assert anomalies[0]["field"] == "latest_revenue"
    new["professional_evidence_lineage"] = {"evidence_ids": ["changed"]}
    assert run_over_run_anomalies([new], [old]) == []


def test_overnight_exposes_primary_and_secondary_validation_credentials():
    workflow=(ROOT/".github/workflows/overnight_scan.yml").read_text()
    assert "TWELVE_DATA_API_KEY: ${{ secrets.TWELVE_DATA_API_KEY }}" in workflow
    assert "FMP_API_KEY: ${{ secrets.FMP_API_KEY }}" in workflow
    assert 'ATLAS_HARD_PUBLICATION_GOVERNANCE_ENABLED: "true"' in workflow
