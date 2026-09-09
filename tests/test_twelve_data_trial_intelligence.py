from services.twelve_data_trial_intelligence import ENDPOINTS, acquire_twelve_trial_dossiers, normalize_trial_dossier
from services.share_structure_governance import materialize_share_bridge
import pytest


class Response:
    def raise_for_status(self): pass
    def json(self): return {"data": [{"value": 1}]}


def test_internal_trial_acquires_evidence_envelopes_without_scoring():
    calls = []
    result = acquire_twelve_trial_dossiers(
        ["mu"], get=lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
        secrets={"TWELVE_DATA_API_KEY": "secret"}, environ={"ATLAS_DATA_MODE": "INTERNAL_TRIAL"},
    )
    assert result["successful_calls"] == len(ENDPOINTS)
    assert len(calls) == len(ENDPOINTS)
    assert result["dossiers"]["MU"]["evidence_ids"]
    assert "score" not in result["dossiers"]["MU"]


def test_successful_same_run_evidence_is_reused_without_network_refetch():
    calls, cache = [], {}
    first = acquire_twelve_trial_dossiers(
        ["mu"], endpoints=("statistics",), evidence_cache=cache,
        get=lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
        secrets={"TWELVE_DATA_API_KEY": "secret"}, environ={"ATLAS_DATA_MODE": "INTERNAL_TRIAL"},
    )
    second = acquire_twelve_trial_dossiers(
        ["mu"], endpoints=("statistics",), evidence_cache=cache,
        get=lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
        secrets={"TWELVE_DATA_API_KEY": "secret"}, environ={"ATLAS_DATA_MODE": "INTERNAL_TRIAL"},
    )
    assert first["provider_calls"] == 1 and second["provider_calls"] == 0
    assert second["cache_hits"] == 1 and second["calls_avoided"] == 1
    assert len(calls) == 1


def test_commercial_mode_disables_trial_intelligence_before_reading_key():
    result = acquire_twelve_trial_dossiers(["MU"], secrets={}, environ={"ATLAS_DATA_MODE": "COMMERCIAL_CUSTOMER"})
    assert result["status"] == "DISABLED"
    assert result["provider_calls"] == 0


def test_statistics_overwrite_untrusted_legacy_values_with_twelve_authority():
    dossier = {"families": {"statistics": {"payload": {"statistics": {"financials": {
        "operating_margin": .18,
        "income_statement": {"quarterly_revenue_growth": .12, "quarterly_earnings_growth_yoy": .25},
        "balance_sheet": {"current_ratio_mrq": 1.6},
        "cash_flow": {"levered_free_cash_flow_ttm": 1000},
    }}}}}, "evidence_ids": ("TDTRIAL-1",)}
    row = normalize_trial_dossier({"ticker": "MU", "revenue_growth": 99}, dossier)
    assert row["revenue_growth"] == 12.0
    assert row["earnings_growth"] == 25
    assert row["operating_profit_margin"] == 18
    assert row["current_ratio"] == 1.6
    assert "free_cash_flow" not in row
    assert row["provider_defined_fcf"] == 1000


def test_zero_cash_flow_values_are_preserved_as_real_evidence():
    dossier = {"families": {"statistics": {"payload": {"statistics": {"financials": {
        "cash_flow": {"levered_free_cash_flow_ttm": 0, "operating_cash_flow_ttm": 0},
    }}}}}}
    row = normalize_trial_dossier({"ticker": "ZERO"}, dossier)
    assert "free_cash_flow" not in row
    assert row["provider_defined_fcf"] == 0
    assert row["operating_cash_flow"] == 0


def test_forward_estimates_use_annual_forward_period_not_quarterly_record():
    dossier = {"observed_at": "2026-09-05T20:00:00Z", "evidence_ids": ("TD-EPS", "TD-REV"), "families": {
        "earnings_estimate": {"payload": {"earnings_estimate": [
            {"period": "current_quarter", "avg_estimate": -1},
            {"period": "next_year", "avg_estimate": 8},
        ]}},
        "revenue_estimate": {"payload": {"revenue_estimate": [
            {"period": "current_quarter", "avg_estimate": 10},
            {"period": "next_year", "avg_estimate": 50},
        ]}},
    }}
    row = normalize_trial_dossier({"ticker": "FWD"}, dossier)
    assert row["forward_eps"] == 8 and row["forward_eps_period"] is None
    assert row["forward_revenue"] == 50 and row["forward_revenue_period"] is None
    assert row["forward_estimate_evidence"]["eps"]["period"] == "next_year"
    assert row["forward_estimate_evidence"]["evidence_ids"] == ("TD-EPS", "TD-REV")
    assert row["forward_eps_period_type"] == "ANNUAL"
    assert row["forward_eps_basis"] == "UNKNOWN"
    assert len(row["forward_estimate_evidence"]["eps_periods"]) == 2


def test_stale_yahoo_forward_eps_is_rejected_and_refetched_from_governed_estimate():
    dossier = {"observed_at": "2026-09-08T00:00:00Z", "evidence_ids": ("TD-EPS",), "families": {
        "earnings_estimate": {"payload": {"earnings_estimate": [
            {"period": "next_year", "date": "2027-12-31", "avg_estimate": 8, "number_of_analysts": 12}
        ]}}
    }}
    row = normalize_trial_dossier({"ticker": "FWD", "forward_eps": 99, "forward_eps_source": "YAHOO_INFO"}, dossier)
    assert row["forward_eps"] == 8 and row["forward_eps_source"] == "TWELVE_DATA"
    lineage = row["professional_evidence_lineage"]["fields"]["forward_eps"]
    assert lineage["period"] == "2027-12-31" and lineage["analyst_count"] == 12


def test_cash_flow_statement_capex_variant_creates_canonical_fcf_without_backsolve():
    dossier = {"observed_at": "2026-09-08T00:00:00Z", "evidence_ids": ("TD-CF",), "families": {
        "cash_flow": {"payload": {"cash_flow": [{"date": "2025-12-31", "free_cash_flow": 999,
            "capital_expenditure": -30, "operating_activities": {"operating_cash_flow": 150}}]}}
    }}
    row = normalize_trial_dossier({"ticker": "FCF"}, dossier)
    assert row["capital_expenditures"] == -30 and row["free_cash_flow"] == 120
    assert row["provider_defined_fcf"] == 999
    fields = row["professional_evidence_lineage"]["fields"]
    assert fields["free_cash_flow"]["transformation"] == "OCF_MINUS_ABS_CAPEX"
    assert fields["free_cash_flow"]["canonical_value"] == 120
    assert fields["operating_cash_flow"]["period"] == fields["capital_expenditures"]["period"] == "2025-12-31"
    assert fields["operating_cash_flow"]["as_of"] == fields["capital_expenditures"]["as_of"] == "2026-09-08T00:00:00Z"


def test_cash_flow_mixed_period_evidence_does_not_publish_canonical_fcf():
    dossier = {"families": {
        "statistics": {"payload": {"statistics": {"financials": {"cash_flow": {"operating_cash_flow_ttm": 150}}}}},
        "cash_flow": {"payload": {"cash_flow": [{"date": "2025-12-31", "capital_expenditure": -30,
                                                    "free_cash_flow": 120}]}}
    }}
    row = normalize_trial_dossier({"ticker": "MIXED"}, dossier)
    assert row["operating_cash_flow"] == 150 and row["capital_expenditures"] == -30
    assert "free_cash_flow" not in row
    assert row["provider_defined_fcf"] == 120


def test_professional_capital_and_reporting_lineage_is_normalized_without_fabrication():
    dossier = {"observed_at":"2026-09-05T20:00:00Z","evidence_ids":("TD-1",),"families":{
        "statistics":{"payload":{"statistics":{"market_capitalization":1000,"shares_outstanding":50,"beta":1.2,"financials":{}}}},
        "income_statement":{"payload":{"income_statement":[{"fiscal_date":"2025-12-31","weighted_average_shares_diluted":48,"ebitda":120,"ebit":100}]}},
        "balance_sheet":{"payload":{"balance_sheet":[{}]}}, "cash_flow":{"payload":{"cash_flow":[{}]}},
    }}
    row = normalize_trial_dossier({"ticker":"LINEAGE"}, dossier)
    assert row["diluted_shares"] == 48 and row["market_cap"] == 1000 and row["beta"] == 1.2
    assert row["financial_reporting_period"] == "2025-12-31"
    assert row["professional_evidence_lineage"]["evidence_ids"] == ("TD-1",)


def test_approved_profile_replaces_unknown_sector_and_persists_lineage():
    dossier = {"observed_at": "2026-09-07T00:00:00Z", "evidence_ids": ("TD-PROFILE",), "families": {
        "profile": {"payload": {"sector": "Technology", "industry": "Software—Application"},
                    "evidence_id": "TD-PROFILE", "observed_at": "2026-09-07T00:00:00Z"},
    }}
    row = normalize_trial_dossier({"ticker": "TEST", "sector": "Unknown", "industry": "Unknown"}, dossier)
    assert row["sector"] == "Technology"
    assert row["industry"] == "Software—Application"
    assert row["sector_lineage"]["authority_order"] == "PRIMARY_PROFILE_SOURCE"


def test_adr_share_bridge_preserves_reported_values_and_applies_ratio():
    row = materialize_share_bridge({"ticker": "BP", "current_price": 40, "market_cap": 1200,
                                    "current_shares_outstanding": 180})
    structure = row["share_structure"]
    assert row["current_shares_outstanding"] == 180
    assert row["market_cap"] == 1200
    assert structure["adr_ratio"] == 6
    assert structure["market_cap_reconciliation_shares"] == 30
    assert structure["market_cap_reconciliation_method"] == "ADR_RATIO_ADJUSTED_ORDINARY_SHARES"


@pytest.mark.parametrize(("ticker", "ratio"), [("TSM", 5), ("BEKE", 3), ("DRD", 10)])
def test_regression_sensitive_adr_ratios_use_economic_share_bridge(ticker, ratio):
    row = materialize_share_bridge({"ticker": ticker, "current_price": 10, "market_cap": 100,
                                    "current_shares_outstanding": 10 * ratio})
    assert row["share_structure"]["market_cap_reconciliation_shares"] == 10
    assert row["share_structure"]["classification"] == "ADR_RATIO"


def test_qsr_dual_class_uses_provider_implied_total_economic_shares():
    row = materialize_share_bridge({"ticker": "QSR", "current_price": 10, "market_cap": 150,
                                    "current_shares_outstanding": 10})
    assert row["share_structure"]["classification"] == "DUAL_CLASS"
    assert row["share_structure"]["market_cap_reconciliation_shares"] == 15


def test_dual_class_bridge_is_explicit_and_does_not_replace_reported_shares():
    row = materialize_share_bridge({"ticker": "CVNA", "current_price": 10, "market_cap": 1000,
                                    "current_shares_outstanding": 60})
    assert row["current_shares_outstanding"] == 60
    assert row["share_structure"]["classification"] == "DUAL_CLASS"
    assert row["share_structure"]["market_cap_reconciliation_shares"] == 100


def test_onc_depositary_ratio_reconciles_ordinary_shares_to_ads_basis():
    row = materialize_share_bridge({"ticker": "ONC", "current_price": 350, "market_cap": 39_550,
                                    "current_shares_outstanding": 1_469})
    assert row["share_structure"]["adr_ratio"] == 13
    assert row["share_structure"]["market_cap_reconciliation_shares"] == 113
