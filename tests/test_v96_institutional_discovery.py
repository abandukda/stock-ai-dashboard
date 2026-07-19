from engines.institutional_discovery_engine import (
    DiscoveryConfig,
    evaluate_candidate,
    run_institutional_discovery,
    validate_discovery_invariants,
)


def healthy_row(ticker="GOOD"):
    return {
        "Ticker": ticker,
        "Company": "Healthy Company",
        "Sector": "Technology",
        "Country": "United States",
        "Current Price": 50,
        "Market Cap": 10_000_000_000,
        "Average Volume": 1_000_000,
        "Quality": 75,
        "Financial Health": 75,
        "Technical Score": 70,
        "Valuation Score": 65,
        "Revenue Growth": 18,
        "EPS Growth": 20,
        "Free Cash Flow": 500_000_000,
        "RSI": 58,
        "Atlas Fair Value": 70,
        "Analyst Target": 66,
        "latest_news_headline": "Company raises guidance",
        "earnings_summary": "Beat estimates",
        "institutional_activity": "Accumulation",
        "political_support": "Policy tailwind",
    }


def test_v96_is_read_only_and_shortlists_healthy_candidate():
    result = run_institutional_discovery([healthy_row()])
    assert result["read_only"] is True
    assert result["funnel_counts"]["universe_received"] == 1
    assert result["funnel_counts"]["shortlisted_for_full_research"] == 1
    assert validate_discovery_invariants(result) == []


def test_v96_records_exclusion_reason():
    row = healthy_row("BANK")
    row["Sector"] = "Financial Services"
    audit = evaluate_candidate(row)
    assert audit["discovery_status"] == "EXCLUDED"
    assert "excluded_sector" in audit["failure_reasons"]


def test_v96_never_emits_decision_fields():
    result = run_institutional_discovery([healthy_row()])
    forbidden = {"action_code", "display_action", "Recommendation", "Decision"}
    for candidate in result["shortlisted_candidates"]:
        assert not forbidden.intersection(candidate)
