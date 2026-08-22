from __future__ import annotations

import json

from engines.fmp_normalization import (
    latest_valid_transcript_period,
    normalize_analyst_estimate,
    normalize_fund_disclosure,
    normalize_ratios,
    normalize_transcript_period,
)
from services.fmp_stable_client import (
    AUTHORIZATION_FAILURE,
    AUTHORIZED_EMPTY,
    FMPStableClient,
    RATE_LIMITED,
    SCHEMA_FAILURE,
    SUCCESS,
)


class _Response:
    def __init__(self, status_code=200, payload=None, json_error=False):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("provider body intentionally hidden")
        return self._payload


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return self.response


def test_stable_analyst_schema_current_names_zero_negative_and_provenance():
    result = normalize_analyst_estimate({
        "date": "2027-01-31", "epsAvg": 0, "epsHigh": 1.2, "epsLow": -0.4,
        "revenueAvg": -10, "revenueHigh": 0, "revenueLow": -20,
        "numAnalystsEps": 0, "numAnalystsRevenue": 14,
        "ebitAvg": 1, "ebitHigh": 2, "ebitLow": -1,
        "ebitdaAvg": 3, "ebitdaHigh": 4, "ebitdaLow": 0,
        "netIncomeAvg": -2, "netIncomeHigh": 2, "netIncomeLow": -4,
    }, fetched_at="2026-08-22T00:00:00Z")
    assert result["fiscal_date"] == "2027-01-31"
    assert result["eps_estimate_avg"] == 0
    assert result["eps_estimate_low"] == -0.4
    assert result["revenue_estimate_avg"] == -10
    assert result["eps_analyst_count"] == 0
    assert result["ebitda_estimate_low"] == 0
    assert result["net_income_estimate_avg"] == -2
    assert result["estimate_vintage_status"] == "NOT_POINT_IN_TIME_VINTAGE"
    assert result["provenance"] == {
        "provider": "FMP", "endpoint_family": "analyst-estimates",
        "fetched_at": "2026-08-22T00:00:00Z", "semantic_status": "AVAILABLE",
        "observation_date": "2027-01-31",
    }


def test_analyst_legacy_aliases_remain_compatible():
    result = normalize_analyst_estimate({
        "fiscalDateEnding": "2026-12-31", "estimatedEpsAvg": 5.5,
        "estimatedRevenueAvg": 100, "numberAnalystsEstimatedEps": 7,
    })
    assert result["fiscal_date"] == "2026-12-31"
    assert result["eps_estimate_avg"] == 5.5
    assert result["revenue_estimate_avg"] == 100
    assert result["eps_analyst_count"] == 7


def test_ratio_normalizer_uses_stable_aliases_without_double_scaling():
    result = normalize_ratios({
        "date": "2026-06-30", "returnOnEquity": 0.1691,
        "returnOnAssets": -0.02, "currentRatio": 0,
        "grossProfitMargin": 0.75, "operatingProfitMargin": 0.42,
        "netProfitMargin": 0.3, "debtToEquityRatio": 1.25,
        "returnOnInvestedCapital": 0.22,
    })
    assert result["return_on_equity"] == 0.1691
    assert result["return_on_assets"] == -0.02
    assert result["current_ratio"] == 0
    assert result["operating_profit_margin"] == 0.42
    assert result["debt_to_equity"] == 1.25
    assert result["roic"] == 0.22
    assert result["ratio_unit"] == "DECIMAL_RATIO"


def test_ratio_legacy_aliases_are_supported_without_heuristic_conversion():
    result = normalize_ratios({
        "returnOnEquityRatio": 0.1, "returnOnAssetsRatio": 0,
        "grossProfitRatio": -0.1, "operatingIncomeRatio": 0.2,
        "netIncomeRatio": 0.15, "debtEquityRatio": 2.0, "roic": -0.03,
    })
    assert result["return_on_equity"] == 0.1
    assert result["return_on_assets"] == 0
    assert result["gross_profit_margin"] == -0.1
    assert result["debt_to_equity"] == 2.0


def test_fund_disclosure_keeps_reporting_and_filing_dates_separate():
    result = normalize_fund_disclosure({
        "investorName": "Example Fund", "cik": "0001", "symbol": "NVDA",
        "securityName": "NVIDIA", "securityCusip": "000000000",
        "sharesNumber": 0, "weight": -0.1, "marketValue": 0,
        "date": "2026-06-30", "filingDate": "2026-08-14",
    }, fetched_at="2026-08-15T00:00:00Z")
    assert result["shares"] == 0
    assert result["weight"] == -0.1
    assert result["market_value"] == 0
    assert result["reporting_date"] == "2026-06-30"
    assert result["filing_date"] == "2026-08-14"
    assert result["evidence_available_from"] == "2026-08-14"
    assert result["evidence_type"] == "INSTITUTIONAL_FUND_HOLDING"


def test_transcript_period_mapping_and_latest_selection():
    rows = [
        {"symbol": "NVDA", "year": 2025, "quarter": 4, "date": "2026-02-20"},
        {"symbol": "NVDA", "year": 2026, "quarter": 1, "date": "2026-05-20"},
        {"symbol": "NVDA", "year": 2026, "quarter": 9, "date": "2026-06-20"},
    ]
    first = normalize_transcript_period(rows[0])
    assert (first["fiscal_year"], first["fiscal_quarter"]) == (2025, 4)
    latest = latest_valid_transcript_period(rows)
    assert latest is not None
    assert (latest["fiscal_year"], latest["fiscal_quarter"]) == (2026, 1)
    assert latest["transcript_date"] == "2026-05-20"


def test_client_classifies_success_empty_auth_rate_limit_and_schema_without_key_leak():
    cases = [
        (_Response(200, [{"symbol": "NVDA"}]), SUCCESS),
        (_Response(200, []), AUTHORIZED_EMPTY),
        (_Response(403, {}), AUTHORIZATION_FAILURE),
        (_Response(429, {}), RATE_LIMITED),
        (_Response(200, None, json_error=True), SCHEMA_FAILURE),
        (_Response(200, "unexpected scalar"), SCHEMA_FAILURE),
    ]
    for response, expected in cases:
        session = _Session(response)
        result = FMPStableClient("super-secret", session=session).get("profile", {"symbol": "NVDA"})
        assert result.outcome == expected
        assert "super-secret" not in json.dumps(result.__dict__, default=str)
        assert session.calls[0][1]["apikey"] == "super-secret"


def test_missing_key_is_authorization_failure_with_zero_network_calls():
    session = _Session(_Response(200, []))
    result = FMPStableClient("", session=session).get("profile", {"symbol": "NVDA"})
    assert result.outcome == AUTHORIZATION_FAILURE
    assert result.attempts == 0
    assert session.calls == []


def test_malformed_rows_fail_closed_as_data_unavailable():
    analyst = normalize_analyst_estimate({"epsAvg": "not-a-number"})
    ratios = normalize_ratios({"returnOnEquity": float("nan")})
    holding = normalize_fund_disclosure({"symbol": "NVDA"})
    assert analyst["eps_estimate_avg"] is None
    assert analyst["provenance"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert ratios["return_on_equity"] is None
    assert ratios["provenance"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert holding["provenance"]["semantic_status"] == "DATA_UNAVAILABLE"
