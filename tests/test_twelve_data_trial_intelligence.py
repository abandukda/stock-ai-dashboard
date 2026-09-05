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
