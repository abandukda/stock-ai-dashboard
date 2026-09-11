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


def test_mpln_same_statement_operating_margin_replaces_provider_ebit_ratio():
    dossier = {"families": {
        "statistics": {"observed_at": "2026-09-10T20:29:10Z", "evidence_id": "TD-STATS", "payload": {
            "statistics": {"financials": {"operating_margin": -1.5520134877243657,
                "income_statement": {"revenue_ttm": 930_624_000}}}}},
        "income_statement": {"observed_at": "2026-09-10T20:29:10Z", "evidence_id": "TD-INCOME", "payload": {
            "income_statement": [{"fiscal_date": "2024-12-31", "period": "annual", "currency": "USD",
                                  "sales": 932_000_000, "operating_income": 98_931_000,
                                  "ebit": -1_444_341_000}]}}
    }}
    row = normalize_trial_dossier({"ticker": "MPLN"}, dossier)
    assert row["provider_defined_operating_profit_margin"] == pytest.approx(-155.20134877243657)
    assert row["operating_profit_margin"] == pytest.approx(98_931_000 / 932_000_000)
    assert row["historical_operating_margin"] == row["operating_profit_margin"]
    assert row["latest_revenue"] == 932_000_000
    assert row["operating_margin_lineage"]["scale"] == "RATIO_DECIMAL"
    assert row["operating_margin_lineage"]["evidence_id"] == "TD-INCOME"


@pytest.mark.parametrize("mismatch", ["currency", "unit"])
def test_statement_margin_fails_closed_on_currency_or_unit_mismatch(mismatch):
    statement = {"fiscal_date": "2025-12-31", "sales": 100, "operating_income": 20,
                 "sales_currency": "USD", "operating_income_currency": "USD",
                 "sales_unit": "MILLIONS", "operating_income_unit": "MILLIONS"}
    if mismatch == "currency":
        statement["operating_income_currency"] = "EUR"
    else:
        statement["operating_income_unit"] = "THOUSANDS"
    dossier = {"families": {
        "statistics": {"payload": {"statistics": {"financials": {"operating_margin": .40}}}},
        "income_statement": {"payload": {"income_statement": [statement]}},
    }}
    row = normalize_trial_dossier({"ticker": "MISMATCH"}, dossier)
    assert row["operating_profit_margin"] == 40
    assert "historical_operating_margin" not in row
    assert "operating_margin_lineage" not in row


@pytest.mark.parametrize("ticker,provider_margin", [
    ("TGT", .061), ("NVDA", .62), ("DAR", -.04), ("MKTX", .41), ("REGN", .33),
])
def test_existing_provider_margin_is_unchanged_without_comparable_statement_pair(ticker, provider_margin):
    dossier = {"families": {"statistics": {"payload": {"statistics": {
        "financials": {"operating_margin": provider_margin}}}}}}
    row = normalize_trial_dossier({"ticker": ticker}, dossier)
    assert row["operating_profit_margin"] == pytest.approx(provider_margin * 100)
    assert row["provider_defined_operating_profit_margin"] == pytest.approx(provider_margin * 100)
    assert "historical_operating_margin" not in row


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


def test_wall_street_price_target_and_recommendations_are_context_only_and_exactly_mapped():
    dossier = {"evidence_ids": ("TD-TARGET", "TD-REC"), "families": {
        "price_target": {"observed_at": "2026-09-09T12:00:00Z", "evidence_id": "TD-TARGET", "payload": {
            "price_target": {"high": 220, "median": 185, "low": 136, "average": 184.01, "current": 169.56, "currency": "USD"}
        }},
        "recommendations": {"observed_at": "2026-09-09T12:00:00Z", "evidence_id": "TD-REC", "payload": {
            "trends": {"current_month": {"strong_buy": 13, "buy": 20, "hold": 8, "sell": 0, "strong_sell": 0}}, "rating": 8.2
        }},
        "eps_trend": {"observed_at": "2026-09-09T12:00:00Z", "evidence_id": "TD-TREND", "payload": {
            "eps_trend": [{"date": "2027-01-31", "period": "next_year", "current_estimate": 2.0, "7_days_ago": 1.9, "30_days_ago": 1.8, "90_days_ago": 1.6}]
        }},
        "analyst_ratings/light": {"observed_at": "2026-09-09T12:00:00Z", "evidence_id": "TD-RATING", "payload": {
            "ratings": [{"date": "2026-09-01", "firm": "Keybanc", "rating_change": "Upgrade", "rating_current": "Overweight", "rating_prior": "Sector Weight"}]
        }},
    }}
    row = normalize_trial_dossier({"ticker": "AAPL", "atlas_fair_value": 999}, dossier)
    assert row["analyst_target_mean"] == 184.01
    assert row["analyst_target_median"] == 185
    assert (row["analyst_target_low"], row["analyst_target_high"]) == (136, 220)
    assert row["analyst_count"] == 41
    assert [row[key] for key in ("strong_buy", "buy", "hold", "sell", "strong_sell")] == [13, 20, 8, 0, 0]
    assert row["recommendation_key"] == "strong_buy"
    assert row["eps_revision_7d"] == 5.26 and row["eps_revision_90d"] == 25.0
    assert row["analyst_actions"][0]["rating_action"] == "Upgrade"
    assert row["analyst_actions"][0]["evidence_id"] == "TD-RATING"
    assert row["atlas_fair_value"] == 999
    assert row["wall_street_evidence_lineage"]["non_scoring"] is True


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
        "cash_flow": {"observed_at":"2026-09-08T00:00:00Z","evidence_id":"TD-CF","payload": {"cash_flow": [{"date": "2025-12-31", "free_cash_flow": 999,
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


def test_peer_statistics_as_of_uses_family_observation_not_dossier_or_scan_time():
    dossier={"observed_at":"2099-01-01T00:00:00Z","families":{"statistics":{
        "observed_at":"2026-09-09T14:30:00Z","evidence_id":"TD-STATS",
        "payload":{"statistics":{"valuations_metrics":{"forward_pe":20,"enterprise_to_ebitda":12}}}}}}
    row=normalize_trial_dossier({"ticker":"STAMP"},dossier)
    assert row["professional_evidence_as_of"]=="2026-09-09T14:30:00Z"
    assert row["professional_evidence_fetched_at"]=="2026-09-09T14:30:00Z"
    assert row["professional_evidence_lineage"]["fields"]["provider_forward_pe"]["evidence_id"]=="TD-STATS"
    missing=normalize_trial_dossier({"ticker":"MISSING"},{"observed_at":"2099-01-01T00:00:00Z","families":dossier["families"] | {"statistics":{**dossier["families"]["statistics"],"observed_at":None}}})
    assert missing["professional_evidence_as_of"] is None


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
