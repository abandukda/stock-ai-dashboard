from engines.professional_valuation_v2 import classify_company
from services.canonical_data_validation import (
    CERTIFIED, REVIEW_REQUIRED, validate_valuation, validation_health,
)
from ui.home_guidance_vnext import _paid_client_full_evidence


def _row(**overrides):
    trial = {
        "forward_eps": 5.0, "forward_eps_period": "FY2027", "forward_revenue": 1_100.0,
        "operating_cash_flow": 120.0, "capital_expenditures": -20.0, "free_cash_flow": 100.0,
        "cash_and_equivalents": 50.0, "total_debt": 150.0, "current_shares_outstanding": 10.0, "diluted_shares": 10.0,
        "market_cap": 1_000.0, "forward_ebitda": 100.0, "description": "Industrial products company",
    }
    models = [
        {"methodology_id": "VAL_FORWARD_PE_V1", "status": "PUBLISHED", "value": 100.0,
         "weight": .5, "fiscal_period": "FY2027", "key_assumptions": {"forward_eps": 5, "justified_forward_pe": 20}},
        {"methodology_id": "VAL_EV_EBITDA_V1", "status": "PUBLISHED", "value": 100.0,
         "weight": .5, "key_assumptions": {"forward_ebitda": 100, "multiple": 11}},
    ]
    row = {"ticker": "TEST", "price": 100.0, "industry": "Industrial Products",
           "canonical_investment_evaluation": {"trial_presentation_fields": trial,
               "atlas_valuation": {"professional_valuation_v2": {
                   "status": "PUBLISHED", "company_type": "PROFITABLE_OPERATING_COMPANY",
                   "atlas_base_fair_value": 100.0, "models": models,
                   "model_weights": {"VAL_FORWARD_PE_V1": .5, "VAL_EV_EBITDA_V1": .5},
                   "valuation_diagnostics": {"flags": []}, "valuation_as_of": "2026-09-05T20:00:00Z",
               }}}}
    row.update(overrides)
    return row


def test_certifies_reconciled_bridges_and_preserves_lineage():
    result = validate_valuation(_row())
    assert result["certification_state"] == CERTIFIED
    assert result["checks"]["market_cap_bridge"]["status"] == "PASS"
    assert result["checks"]["ev_bridge"]["status"] == "PASS"
    assert result["checks"]["fcf_reconciliation"]["status"] == "PASS"
    assert result["input_lineage"]["forward_eps"]["period"] == "FY2027"
    assert result["input_lineage"]["forward_eps"]["unit"] == "PER_SHARE"


def test_source_divergence_fails_closed_without_selecting_a_source():
    row = _row(approved_secondary_valuation_inputs={
        "forward_eps": {"value": 3.0, "source": "SECONDARY"}
    })
    result = validate_valuation(row)
    assert result["certification_state"] == REVIEW_REQUIRED
    assert "INPUT_SOURCE_DIVERGENCE" in result["warnings"]
    assert result["input_lineage"]["forward_eps"]["value"] == 5.0


def test_period_mismatch_and_market_cap_bridge_fail_closed():
    row = _row()
    row["canonical_investment_evaluation"]["trial_presentation_fields"]["market_cap"] = 2_000
    row["canonical_investment_evaluation"]["atlas_valuation"]["professional_valuation_v2"]["models"][0]["fiscal_period"] = "FY2028"
    result = validate_valuation(row)
    assert {"PERIOD_MISMATCH", "MARKET_CAP_BRIDGE_FAILURE"} <= set(result["warnings"])
    assert result["customer_publication_allowed"] is False


def test_provider_defined_fcf_is_preserved_while_standard_fcf_is_authoritative():
    row = _row()
    trial = row["canonical_investment_evaluation"]["trial_presentation_fields"]
    trial["free_cash_flow"] = 50
    row["canonical_investment_evaluation"]["atlas_valuation"]["professional_valuation_v2"]["models"][1]["value"] = 150
    result = validate_valuation(row)
    assert result["checks"]["fcf_reconciliation"]["provider_defined_fcf"] == 50
    assert result["checks"]["fcf_reconciliation"]["atlas_standard_fcf"] == 100
    assert result["checks"]["fcf_reconciliation"]["canonical_authority"] == "ATLAS_STANDARD_FCF"
    assert "EV_BRIDGE_FAILURE" in result["warnings"]


def test_extreme_dispersion_and_sector_routing_require_review():
    row = _row(industry="Unknown")
    row["canonical_investment_evaluation"]["trial_presentation_fields"]["description"] = "Global gold mining producer"
    models = row["canonical_investment_evaluation"]["atlas_valuation"]["professional_valuation_v2"]["models"]
    models[0]["value"] = 20
    models[1]["value"] = 140
    result = validate_valuation(row)
    assert "SECTOR_MODEL_APPLICABILITY_WARNING" in result["warnings"]
    assert "EXTREME_MODEL_DISPERSION" in result["warnings"]
    assert result["checks"]["dispersion"]["over_5x"] is True


def test_unknown_provider_industry_uses_sourced_profile_for_nem_routing():
    assert classify_company({"industry": "Unknown", "sector": "Unknown",
                             "company_description": "Newmont is a global gold mining company",
                             "forward_eps": 4.0}) == "COMMODITY_PRODUCER"


def test_health_aggregates_certification_and_failures():
    health = validation_health([_row(), _row()])
    assert health["published_audited"] == 2
    assert health["certification_distribution"]["CERTIFIED"] == 2


def test_paid_drawer_translates_review_state_and_distinguishes_model_range():
    row = _row()
    evaluation = row["canonical_investment_evaluation"]
    evaluation["valuation_validation"] = {
        "certification_state": "REVIEW_REQUIRED", "customer_publication_allowed": False,
    }
    html = _paid_client_full_evidence({"evaluation": evaluation, "display_price": 100})
    assert "Under Review — Not Displayed As A Confident Customer Fair Value" in html
    assert "ATLAS Base Fair Value</small><b>" not in html
    assert "Fair Value Range" not in html
