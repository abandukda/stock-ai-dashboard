
from engines.canonical_market_data import load_price_history


def test_governed_provider_success_sets_available_provenance():
    def provider(ticker, period):
        return [
            {
                "date": "2026-07-01",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 104,
                "volume": 1000,
            }
        ], ""

    result = load_price_history(
        "TEST",
        force_refresh=True,
        provider_fetcher=provider,
    )
    assert result["status"] == "AVAILABLE"
    assert result["provider_success"] is True
    assert result["mapping_success"] is True
    assert result["records_found"] == 1


def test_governed_provider_is_explicit():
    def provider(ticker, period):
        return [
            {
                "date": "2026-07-01",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 104,
                "volume": 1000,
            }
        ], ""

    result = load_price_history(
        "FALLBACK",
        force_refresh=True,
        provider_fetcher=provider,
    )
    assert result["status"] == "AVAILABLE"
    assert result["retrieval_status"] == "provider_success"
    assert result["source"] == "GOVERNED_MARKET_DATA"


def test_provider_failure_does_not_claim_no_records():
    def provider(ticker, period):
        return [], "governed provider timeout"

    result = load_price_history(
        "FAILED",
        force_refresh=True,
        provider_fetcher=provider,
    )
    assert result["status"] == "PROVIDER_ERROR"
    assert result["provider_called"] is False
    assert result["provider_success"] is False
    assert result["records_found"] == 0


def test_no_configured_history_provider_is_explicitly_unavailable():
    result = load_price_history("NO_PROVIDER", force_refresh=True)
    assert result["status"] == "PROVIDER_ERROR"
    assert result["provider_called"] is False
    assert result["source"] == "GOVERNED_MARKET_DATA_UNAVAILABLE"
