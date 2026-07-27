
from engines.institutional_scoring_engine import score_stock

def test_scoring_uses_canonical_financial_and_technical_components():
    row = {
        "Ticker": "TEST",
        "Company": "Test",
        "Sector": "Technology",
        "Price": 100,
        "Revenue Growth": 12,
        "EPS Growth": 15,
        "Operating Margin": 25,
        "Free Cash Flow": 1000,
        "Current Ratio": 1.8,
        "RSI": 58,
        "20D %": 4,
        "Volume Ratio": 1.3,
        "Analyst Support Score": 70,
    }
    result = score_stock(row)
    assert result["components"]["fundamentals"] is not None
    assert result["components"]["technical"] is not None
    assert result["component_details"]["fundamentals"]["status"] == "AVAILABLE"
    assert result["raw"]["Ticker"] == "TEST"
