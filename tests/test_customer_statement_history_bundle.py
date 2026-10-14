from services.customer_statement_history_bundle import customer_statement_history


TICKERS = ("AVT", "BKTI", "CODA", "CSCO", "CTS", "DIOD", "EXTR", "GNE", "MSFT", "NVDA", "SBC")


def test_retained_statement_history_bundle_is_integrity_checked_for_all_eleven_tickers():
    annual_periods = quarterly_periods = 0
    for ticker in TICKERS:
        history = customer_statement_history(ticker)
        assert history["contract"] == "ATLAS_CUSTOMER_STATEMENT_HISTORY_PROJECTION_V1"
        assert history["ticker"] == ticker
        assert history["status"] == "AVAILABLE"
        assert history["read_only"] is True and history["provider_calls"] == 0
        assert history["rating_authority"] == history["publication_authority"] == "UNCHANGED"
        annual_periods += history["annual"]["retained_period_count"]
        quarterly_periods += history["quarterly"]["retained_period_count"]
    assert annual_periods == 147
    assert quarterly_periods == 447


def test_unretained_ticker_is_typed_unavailable():
    assert customer_statement_history("AAPL") == {
        "status": "UNAVAILABLE", "ticker": "AAPL",
        "reason": "SOURCE_BOUND_STATEMENT_HISTORY_NOT_RETAINED",
    }

