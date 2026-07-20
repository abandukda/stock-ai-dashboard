from adapters.scanner_adapter import adapt_scanner_row

def test_adapter_maps_current_scanner_schema():
    row = {
        "ticker":"CRM","company":"Salesforce","sector":"Technology",
        "quote_type":"EQUITY","current_price":170.77,
        "analyst_target_mean":245.16,"finance_agent_score":73,
        "analyst_support_score":87.6,
        "ai_committee":{"Technical Agent":{"score":94}},
        "investment_thesis":"Constructive thesis",
    }
    result = adapt_scanner_row(row)
    assert result["ticker"] == "CRM"
    assert result["technical_score"] == 94
    assert result["financial_health_score"] == 73
    assert result["atlas_fair_value"] == 245.16
    assert result["expected_return_pct"] > 0

def test_analyst_buy_is_not_atlas_buy_now():
    row = {"ticker":"A","sector":"Technology","quote_type":"EQUITY",
           "recommendation_key":"strong_buy","current_price":100}
    result = adapt_scanner_row(row)
    assert result["action_code"] != "BUY_NOW"

def test_etf_is_excluded():
    result = adapt_scanner_row({"ticker":"XLV","quote_type":"ETF","sector":"Healthcare"})
    assert result["eligible"] is False
