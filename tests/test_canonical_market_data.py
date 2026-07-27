
from engines.canonical_market_data import load_price_history


def test_yahoo_success_sets_available_provenance():
    def yahoo(ticker, period, interval):
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

    def fmp(ticker, period):
        raise AssertionError("FMP should not run after Yahoo success")

    result = load_price_history(
        "TEST",
        force_refresh=True,
        yahoo_fetcher=yahoo,
        fmp_fetcher=fmp,
    )
    assert result["status"] == "AVAILABLE"
    assert result["provider_success"] is True
    assert result["mapping_success"] is True
    assert result["records_found"] == 1


def test_fmp_fallback_is_explicit():
    def yahoo(ticker, period, interval):
        return [], "Yahoo timeout"

    def fmp(ticker, period):
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
        yahoo_fetcher=yahoo,
        fmp_fetcher=fmp,
    )
    assert result["status"] == "AVAILABLE"
    assert result["retrieval_status"] == "fallback_success"
    assert "FMP" in result["source"]


def test_provider_failure_does_not_claim_no_records():
    def yahoo(ticker, period, interval):
        return [], "Yahoo timeout"

    def fmp(ticker, period):
        return [], "FMP timeout"

    result = load_price_history(
        "FAILED",
        force_refresh=True,
        yahoo_fetcher=yahoo,
        fmp_fetcher=fmp,
    )
    assert result["status"] == "PROVIDER_ERROR"
    assert result["provider_called"] is True
    assert result["provider_success"] is False
    assert result["records_found"] == 0
