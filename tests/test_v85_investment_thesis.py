from engines.evidence_engine import build_evidence_profile
from engines.investment_thesis_engine import build_investment_thesis


def _row():
    return {
        "Ticker": "MSFT",
        "Company": "Microsoft Corporation",
        "Current Price": 450,
        "Atlas Fair Value": 560,
        "Analyst Target": 540,
        "Revenue Growth": 18,
        "Earnings Growth": 20,
        "Operating Margin": 46,
        "Free Cash Flow": 37_000_000_000,
        "Current Ratio": 1.3,
        "Technical Score": 78,
        "Confidence": 86,
        "RSI": 58,
        "Relative Volume": 1.1,
        "Institutional Ownership": 74,
        "Institutional Ownership Change": 1.2,
        "latest_news_headline": "Enterprise AI demand remains strong",
        "latest_news_summary": "Supports cloud and recurring software growth.",
        "political_support_summary": "Government and enterprise AI spending remain supportive.",
        "earnings_ai_summary": "Management reported durable cloud demand and maintained constructive guidance.",
        "Forward PE": 31,
        "Sector": "Technology",
    }


def test_evidence_profile_is_auditable():
    result = build_evidence_profile(_row())
    assert result["available_pillars"] >= 6
    assert 0 <= result["overall_score"] <= 100
    assert "Financials" in result["pillars"]


def test_thesis_contains_required_sections():
    result = build_investment_thesis(_row())
    assert result["executive_summary"]
    assert result["bull_case"]
    assert result["bear_case"]
    assert result["invalidation"]
    assert result["recommendation"] in {
        "High Conviction Buy", "Buy Now", "Buy on Weakness", "Wait for Confirmation", "Avoid"
    }
    assert result["confidence"] > 0


def test_missing_current_ratio_does_not_become_zero_risk():
    row = _row()
    row.pop("Current Ratio")
    result = build_investment_thesis(row)
    assert not any("0.00" in risk for risk in result["bear_case"])


def test_sparse_data_remains_measured():
    result = build_investment_thesis({"Ticker": "NEW", "Company": "New Co", "Current Price": 10})
    assert result["recommendation"] in {"Wait for Confirmation", "Avoid", "Buy on Weakness"}
    assert result["evidence"]["available_pillars"] <= 2
