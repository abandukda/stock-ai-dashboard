from scripts.finnhub_contract_gap_closure import quote_comparison
from scripts.finnhub_websocket_audit import classify_messages
from services.finnhub_contract_gap_governance import (
    authority_state, estimate_bridge, forward_route_gate,
)
from services.finnhub_shadow_provider import (
    ENDPOINT_BY_CAPABILITY, FINNHUB_ESTIMATE_CAPABILITIES,
    FINNHUB_ESTIMATE_CONTRACT, FinnhubShadowAdapter,
)


class Response:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload

    def json(self): return self._payload


def test_provider_written_estimate_contract_is_absolute_and_keeps_vintage_unproven():
    assert FINNHUB_ESTIMATE_CONTRACT["value_unit"]["value"] == "ABSOLUTE_UNITS"
    assert FINNHUB_ESTIMATE_CONTRACT["scale"]["value"] == "IDENTITY"
    assert FINNHUB_ESTIMATE_CONTRACT["currency"]["source_field"] == "company_profile.estimateCurrency"
    assert FINNHUB_ESTIMATE_CONTRACT["provider_vintage"]["status"] == "UNAVAILABLE"
    assert FINNHUB_ESTIMATE_CONTRACT["revision_history"]["status"] == "UNPROVEN"


def test_profile_preserves_estimate_currency_and_estimate_normalization_is_not_million_scaled():
    payloads = iter([
        {"name": "Example", "currency": "USD", "estimateCurrency": "USD"},
        {"freq": "annual", "data": [{"period": "2027-12-31", "year": 2027,
          "revenueAvg": 12_345_678_901, "revenueHigh": 13_000_000_000,
          "revenueLow": 12_000_000_000, "numberAnalysts": 9}]},
    ])
    adapter = FinnhubShadowAdapter("key", get=lambda *_a, **_k: Response(next(payloads)))
    profile = adapter.fetch("company_profile", "AAPL").payload
    estimate = adapter.fetch("revenue_estimates", "AAPL").payload
    assert profile["estimate_currency"] == "USD"
    assert estimate["value_scale"] == "ABSOLUTE_UNITS"
    assert estimate["estimates"][0]["average"] == 12_345_678_901
    assert estimate["basis"] == "MONETARY_ABSOLUTE"
    assert estimate["provider_vintage"] == "UNAVAILABLE"


def test_every_contracted_estimate_endpoint_is_wired_with_annual_frequency():
    calls = []
    adapter = FinnhubShadowAdapter("key", get=lambda url, **kwargs: calls.append((url, kwargs)) or Response({"freq": "annual", "data": []}))
    for capability in sorted(FINNHUB_ESTIMATE_CAPABILITIES):
        adapter.fetch(capability, "AAPL")
    assert len(calls) == 11
    assert all(call[1]["params"]["freq"] == "annual" for call in calls)


def test_contract_endpoint_names_match_signed_appendix():
    assert ENDPOINT_BY_CAPABILITY["dividends"].path == "/stock/dividend"
    assert ENDPOINT_BY_CAPABILITY["revenue_breakdown"].path == "/stock/revenue-breakdown2"
    assert ENDPOINT_BY_CAPABILITY["quote_us"].path == "/quote/us"
    assert ENDPOINT_BY_CAPABILITY["historical_market_cap"].path == "/stock/historical-market-cap"
    assert ENDPOINT_BY_CAPABILITY["price_metrics"].path == "/stock/price-metric"
    assert ENDPOINT_BY_CAPABILITY["sector_metrics"].path == "/sector/metrics"


def test_estimate_bridge_requires_currency_period_frequency_and_compatible_price_currency():
    good = estimate_bridge(
        {"estimate_currency": "USD"},
        {"frequency": "annual", "estimates": [{"period": "2027-12-31", "frequency": "annual"}]},
        capability="eps_estimates", price_currency="USD",
    )
    assert good["status"] == "CERTIFIED_PROVIDER_CONTRACT"
    assert good["basis"] == "PER_SHARE"
    bad = estimate_bridge(
        {"estimate_currency": "EUR"},
        {"frequency": "annual", "estimates": [{"period": "2027-12-31", "frequency": "annual"}]},
        capability="eps_estimates", price_currency="USD",
    )
    assert bad["status"] == "CONTRACT_MISMATCH"
    assert "PRICE_ESTIMATE_CURRENCY_MISMATCH" in bad["blockers"]


def test_forward_routes_remain_fail_closed_until_method_specific_bridges_pass():
    bridge = {"status": "CERTIFIED_PROVIDER_CONTRACT", "blockers": []}
    assert forward_route_gate(route="VAL_FORWARD_PE_V1", estimate_bridge_result=bridge,
                              peer_certified=False)["status"] == "FAIL_CLOSED"
    assert forward_route_gate(route="VAL_FORWARD_PE_V1", estimate_bridge_result=bridge,
                              peer_certified=True)["status"] == "ELIGIBLE_COMPLETE"
    dcf = forward_route_gate(route="VAL_FCFF_DCF_V1", estimate_bridge_result=bridge,
                             peer_certified=True)
    assert set(dcf["blockers"]) == {"ACCOUNTING_BRIDGE_NOT_CERTIFIED", "SCENARIO_EVIDENCE_NOT_CERTIFIED", "WACC_INPUTS_INCOMPLETE"}


def test_new_families_never_gain_authority_from_endpoint_success_alone():
    assert authority_state("quote_us", live_status="UNVERIFIED_SHADOW", provenance_complete=True) == "DISPLAY_ONLY"
    assert authority_state("sector_metrics", live_status="UNVERIFIED_SHADOW", provenance_complete=True) == "CONTEXTUAL_CERTIFIED"
    assert authority_state("eps_estimates", live_status="UNVERIFIED_SHADOW", semantics_certified=False,
                           provenance_complete=True) == "CONTRACT_PENDING"
    assert authority_state("eps_estimates", live_status="UNVERIFIED_SHADOW", semantics_certified=True,
                           provenance_complete=True) == "CANONICAL_CERTIFIED"


def test_quote_comparison_and_websocket_evidence_are_non_scoring():
    quote = {"price": 10, "open": 9, "high": 11, "low": 8, "previous_close": 9, "provider_timestamp": 1}
    assert quote_comparison(quote, dict(quote)) == "SEMANTICALLY_EQUIVALENT"
    result = classify_messages([{"type": "trade", "data": [{"s": "AAPL", "p": 10, "t": 1, "type": "trade"}]}])
    assert result["suitability"] == "LIVE_DISPLAY"
    assert result["scoring_allowed"] is False
    assert result["venues_present"] is False


def test_unavailable_new_endpoint_still_returns_complete_provenance():
    record = FinnhubShadowAdapter("", get=lambda *_a, **_k: None).fetch("earnings_quality", "AAPL")
    assert record.payload["status"] == "DATA_UNAVAILABLE"
    assert record.provenance.raw_evidence_id
    assert record.provenance.display_permission.value == "PROHIBITED"
