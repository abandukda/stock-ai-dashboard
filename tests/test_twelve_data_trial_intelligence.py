from services.twelve_data_trial_intelligence import ENDPOINTS, acquire_twelve_trial_dossiers, normalize_trial_dossier


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


def test_commercial_mode_disables_trial_intelligence_before_reading_key():
    result = acquire_twelve_trial_dossiers(["MU"], secrets={}, environ={"ATLAS_DATA_MODE": "COMMERCIAL_CUSTOMER"})
    assert result["status"] == "DISABLED"
    assert result["provider_calls"] == 0


def test_statistics_normalize_missing_fundamentals_without_overwriting_atlas_values():
    dossier = {"families": {"statistics": {"payload": {"statistics": {"financials": {
        "operating_margin": .18,
        "income_statement": {"quarterly_revenue_growth": .12, "quarterly_earnings_growth_yoy": .25},
        "balance_sheet": {"current_ratio_mrq": 1.6},
        "cash_flow": {"levered_free_cash_flow_ttm": 1000},
    }}}}}, "evidence_ids": ("TDTRIAL-1",)}
    row = normalize_trial_dossier({"ticker": "MU", "revenue_growth": 99}, dossier)
    assert row["revenue_growth"] == 99
    assert row["earnings_growth"] == 25
    assert row["operating_profit_margin"] == 18
    assert row["current_ratio"] == 1.6
    assert row["free_cash_flow"] == 1000


def test_zero_cash_flow_values_are_preserved_as_real_evidence():
    dossier = {"families": {"statistics": {"payload": {"statistics": {"financials": {
        "cash_flow": {"levered_free_cash_flow_ttm": 0, "operating_cash_flow_ttm": 0},
    }}}}}}
    row = normalize_trial_dossier({"ticker": "ZERO"}, dossier)
    assert row["free_cash_flow"] == 0
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
    assert row["forward_eps"] == 8 and row["forward_eps_period"] == "next_year"
    assert row["forward_revenue"] == 50 and row["forward_revenue_period"] == "next_year"
    assert row["forward_estimate_evidence"]["eps"]["period"] == "next_year"
    assert row["forward_estimate_evidence"]["evidence_ids"] == ("TD-EPS", "TD-REV")
    assert row["forward_eps_period_type"] == "ANNUAL"
    assert row["forward_eps_basis"] == "UNKNOWN"
    assert len(row["forward_estimate_evidence"]["eps_periods"]) == 2


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
