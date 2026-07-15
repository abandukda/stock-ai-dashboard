from engines.research_intelligence_engine import build_research_report, research_completeness


def sample():
    return {
        "Ticker": "MSFT", "Company": "Microsoft Corporation", "Current Price": 450,
        "Atlas Fair Value": 540, "Revenue Growth": .18, "Earnings Growth": .22,
        "Operating Margin": .46, "Free Cash Flow": 37_000_000_000,
        "RSI": 58, "SMA50": 430, "SMA200": 390, "Relative Volume": 1.1,
        "Analyst Target": 560, "Analyst High": 620, "Analyst Low": 470, "Analyst Count": 31,
        "latest_news_headline": "Cloud demand remains strong", "latest_news_source": "Provider",
        "political_support_summary": "Federal AI modernization spending is a potential tailwind.",
        "Institutional Ownership": .74, "Smart Money Score": 72,
        "earnings_ai_summary": "Cloud growth and guidance were constructive.",
        "Quality": 92, "Financial Health": 90, "Valuation Score": 75,
        "Technical Score": 78, "Confidence": 86, "News Score": 76,
    }


def test_report_is_structured_and_complete():
    report = build_research_report(sample())
    assert report["financial"]["bullets"]
    assert report["technical"]["bullets"]
    assert report["analysts"]["consensus"] == 560
    assert report["valuation"]["upside"] == 20.0
    assert report["completeness"]["count"] >= 7
    assert report["risks"]
    assert "0.00" not in " ".join(report["risks"])


def test_missing_values_are_not_turned_into_zero():
    report = build_research_report({"Ticker": "TEST", "Company": "Test Co", "Current Ratio": None})
    text = " ".join(report["financial"]["bullets"] + report["risks"])
    assert "0.00" not in text
    assert research_completeness({"Ticker": "TEST"})["count"] == 0
