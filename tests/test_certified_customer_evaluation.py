import json
from copy import deepcopy
from pathlib import Path

from services.certified_customer_evaluation import (
    build_certified_customer_evaluation, certified_projection_matches,
)
from services.publication_governance import certify_record


ROOT = Path(__file__).resolve().parents[1]


def _row(ticker):
    for name in ("market_full_scan.json", "full_evaluation_pool.json"):
        rows = json.loads((ROOT / name).read_text())
        match = next((row for row in rows if row.get("ticker") == ticker), None)
        if match:
            return match
    raise LookupError(ticker)


def test_current_certified_buy_now_projection_is_snapshot_atomic():
    result = build_certified_customer_evaluation(_row("CXT"))
    assert result["customer_publication_allowed"] is True
    assert result["decision"]["action"] == "BUY_NOW"
    assert result["fields"]["price"]["value"] == 50.37
    assert result["digests"]["evaluation_snapshot_id"]
    assert result["digests"]["market_digest"]
    assert result["digests"]["valuation_digest"]
    assert result["digests"]["decision_digest"]
    assert result["digests"]["certification_digest"]


def test_sd_extreme_value_fails_closed_without_extraordinary_certification():
    result = build_certified_customer_evaluation(_row("SD"))
    assert result["fields"]["atlas_fair_value"]["value"] is None
    assert result["fields"]["atlas_upside_pct"]["value"] is None
    assert result["fields"]["atlas_fair_value"]["certification_status"] == "REVIEW_REQUIRED"
    assert result["decision"]["action"] is None
    assert result["customer_publication_allowed"] is False


def test_stage_a_publication_cannot_bypass_stage_b_sd_failure():
    row = deepcopy(_row("SD"))
    row.pop("publication_certification", None)
    certification = certify_record(row)
    assert certification["customer_publication_allowed"] is False
    assert certification["certified_action"] is None
    assert "CUSTOMER_PROJECTION_RECONCILIATION_FAILED" in certification["blockers"]


def test_mpln_same_period_operating_margin_reconstructs_without_mismatch():
    row = deepcopy(_row("CXT"))
    row["ticker"] = "MPLN"
    evaluation = row["canonical_investment_evaluation"]
    evaluation["ticker"] = "MPLN"
    evaluation["fundamentals"]["data"]["revenue"] = 930_624_000
    evaluation["fundamentals"]["data"]["operating_margin_pct"] = 98_931_000 / 930_624_000
    lineage = evaluation["valuation_validation"]["input_lineage"]
    lineage["revenue"]["value"] = lineage["revenue"]["canonical_value"] = 930_624_000
    lineage["operating_income"] = {
        "value": 98_931_000, "canonical_value": 98_931_000,
        "period": "2024-12-31", "period_type": "ANNUAL", "basis": "PROVIDER_REPORTED",
        "unit": "CURRENCY", "currency": "USD", "source": "TWELVE_DATA",
        "evidence_id": "TD-MPLN-OI", "as_of": "2026-09-11T00:00:00Z",
    }
    result = build_certified_customer_evaluation(row)
    expected = 98_931_000 / 930_624_000
    assert abs(result["accounting_reconstruction"]["operating_margin_pct"] - expected) < 1e-12
    assert "operating_margin_pct" not in result["accounting_mismatches"]


def test_forward_estimate_without_period_or_evidence_is_never_exposed():
    row = deepcopy(_row("CXT"))
    lineage = row["canonical_investment_evaluation"]["valuation_validation"]["input_lineage"]
    lineage["forward_eps"]["period"] = None
    lineage["forward_eps"]["evidence_id"] = None
    row["canonical_investment_evaluation"]["trial_presentation_fields"]["forward_estimate_evidence"]["evidence_ids"] = []
    result = build_certified_customer_evaluation(row)
    assert result["fields"]["forward_eps"]["value"] is None
    assert result["fields"]["forward_eps"]["certification_status"] == "INSUFFICIENT_INPUTS"


def test_stage_b_upside_mismatch_blocks_value_and_action():
    row = deepcopy(_row("CXT"))
    row["canonical_investment_evaluation"]["atlas_valuation"]["expected_return"] = 999
    result = build_certified_customer_evaluation(row)
    assert result["fields"]["atlas_upside_pct"]["value"] is None
    assert result["fields"]["atlas_upside_pct"]["certification_status"] == "REVIEW_REQUIRED"


def test_projection_does_not_mutate_canonical_evaluation():
    row = _row("CXT")
    before = deepcopy(row)
    build_certified_customer_evaluation(row)
    assert row == before


def test_projection_cannot_be_reused_for_a_different_snapshot():
    row = deepcopy(_row("CXT"))
    evaluation = row["canonical_investment_evaluation"]
    projection = build_certified_customer_evaluation(row)
    assert certified_projection_matches(projection, evaluation, "CXT") is True
    evaluation["decision_digest"] = "different-snapshot"
    assert certified_projection_matches(projection, evaluation, "CXT") is False


def test_wall_street_target_outside_range_is_withheld():
    row = deepcopy(_row("CXT"))
    row["wall_street_analysis"]["consensus"]["target_mean"] = 999
    result = build_certified_customer_evaluation(row)
    assert result["domains"]["wall_street_certification"] == "REVIEW_REQUIRED"
    assert result["wall_street_analysis"] == {}


def test_certified_internal_trial_wall_street_contract_is_preserved():
    result = build_certified_customer_evaluation(_row("CXT"))
    assert result["domains"]["wall_street_certification"] == "CERTIFIED"
    assert result["wall_street_analysis"]["provider"] == "TWELVE_DATA"
    assert result["wall_street_analysis"]["consensus"]["target_mean"] == 70.16667


def test_forward_estimate_explicitly_stale_is_withheld():
    row = deepcopy(_row("CXT"))
    row["canonical_investment_evaluation"]["valuation_validation"]["input_lineage"]["forward_eps"]["stale"] = True
    result = build_certified_customer_evaluation(row)
    assert result["fields"]["forward_eps"]["value"] is None
    assert result["fields"]["forward_eps"]["certification_status"] == "INSUFFICIENT_INPUTS"


def test_ttm_cannot_substitute_for_forward_estimate():
    row = deepcopy(_row("CXT"))
    row["canonical_investment_evaluation"]["valuation_validation"]["input_lineage"]["forward_eps"]["period_type"] = "TTM"
    result = build_certified_customer_evaluation(row)
    assert result["fields"]["forward_eps"]["value"] is None


def test_forward_eps_and_revenue_period_mismatch_fails_closed():
    row = deepcopy(_row("CXT"))
    row["canonical_investment_evaluation"]["valuation_validation"]["input_lineage"]["forward_revenue"]["period"] = "2028-12-31"
    result = build_certified_customer_evaluation(row)
    assert result["fields"]["forward_eps"]["value"] is None
    assert result["fields"]["forward_revenue"]["value"] is None
    assert result["fields"]["forward_eps"]["certification_status"] == "REVIEW_REQUIRED"


def test_wall_street_missing_timestamp_or_action_evidence_is_withheld():
    missing_time = deepcopy(_row("CXT"))
    missing_time["wall_street_analysis"]["as_of"] = None
    assert build_certified_customer_evaluation(missing_time)["wall_street_analysis"] == {}
    missing_action = deepcopy(_row("CXT"))
    missing_action["wall_street_analysis"]["recent_actions"][0]["original_fields"]["evidence_id"] = None
    assert build_certified_customer_evaluation(missing_action)["wall_street_analysis"] == {}


def test_certified_trade_and_method_values_are_field_level_contracts():
    result = build_certified_customer_evaluation(_row("CXT"))
    assert result["trade_plan_fields"]["entry_low"]["snapshot_id"] == result["digests"]["evaluation_snapshot_id"]
    assert result["valuation_methods"]
    assert all(method["value"]["evidence_ids"] for method in result["valuation_methods"] if method["value"]["value"] is not None)
