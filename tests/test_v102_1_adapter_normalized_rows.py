from adapters.scanner_adapter import adapt_scanner_row


def test_adapter_reads_normalized_app_row_and_raw_payload():
    result = adapt_scanner_row(
        {
            "Ticker": "CRM",
            "Company": "Salesforce",
            "Sector": "Technology",
            "Industry": "Software",
            "Price": 170.0,
            "Final Conviction": 91,
            "AI Fair Value": 210.0,
            "Analyst Target": 200.0,
            "Investment Thesis": "Constructive thesis",
            "Raw": {
                "quote_type": "EQUITY",
                "finance_agent_score": 73,
                "analyst_support_score": 88,
                "guidance": "Constructive guidance",
                "ai_committee": {
                    "Technical Agent": {"score": 94}
                },
            },
        }
    )

    assert result["eligible"] is True
    assert result["ticker"] == "CRM"
    assert result["technical_score"] == 94
    assert result["financial_health_score"] == 73
    assert result["current_price"] == 170.0
    assert result["atlas_fair_value"] is not None


def test_adapter_accepts_committee_list_shape():
    result = adapt_scanner_row(
        {
            "Ticker": "ABC",
            "Sector": "Technology",
            "Price": 100,
            "Final Conviction": 80,
            "Investment Thesis": "Thesis",
            "Raw": {
                "quote_type": "EQUITY",
                "finance_agent_score": 70,
                "ai_committee": [
                    {
                        "agent": "Technical Agent",
                        "score": 82,
                    }
                ],
            },
        }
    )

    assert result["technical_score"] == 82
