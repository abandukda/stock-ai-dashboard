
from engines.institutional_scoring_engine import score_stock


def test_legacy_scores_remain_when_canonical_data_is_absent():
    row = {
        "Ticker": "LEGACY",
        "Company": "Legacy Test",
        "Sector": "Technology",
        "Price": 100,
        "Final Conviction": 80,
        "Technical Score": 90,
        "Finance Agent Score": 85,
        "Analyst Support Score": 75,
        "Analyst Target": 125,
    }
    result = score_stock(row)

    assert result["eligible"] is True
    assert result["components"]["fundamentals"] == 85
    assert result["components"]["technical"] == 90
    assert result["opportunity_score"] is not None
    assert result["component_details"]["fundamentals"]["status"] == "NOT_LOADED"


def test_canonical_financial_overrides_legacy_when_real_data_exists():
    row = {
        "Ticker": "CANON",
        "Company": "Canonical Test",
        "Sector": "Technology",
        "Price": 100,
        "Final Conviction": 70,
        "Finance Agent Score": 20,
        "Technical Score": 60,
        "Analyst Support Score": 70,
        "Analyst Target": 120,
        "Revenue Growth": 20,
        "EPS Growth": 25,
        "Operating Margin": 30,
        "Free Cash Flow": 1000,
        "Current Ratio": 2.0,
    }
    result = score_stock(row)

    assert result["component_details"]["fundamentals"]["status"] == "AVAILABLE"
    assert result["components"]["fundamentals"] == result["component_details"]["fundamentals"]["score"]
    assert result["components"]["fundamentals"] != 20


def test_missing_rsi_does_not_become_zero_or_break_legacy_technical():
    row = {
        "Ticker": "TECH",
        "Company": "Technical Test",
        "Sector": "Technology",
        "Price": 100,
        "Final Conviction": 75,
        "Finance Agent Score": 70,
        "Technical Score": 88,
        "Analyst Support Score": 70,
        "Analyst Target": 120,
        "20D %": 2,
        "Volume Ratio": 1.1,
    }
    result = score_stock(row)

    assert result["component_details"]["technical"]["data"]["rsi"] is None
    assert result["components"]["technical"] is not None
