
from engines.component_builder import build_components

def test_legitimate_zero_growth_is_not_missing():
    row = {
        "Ticker": "TEST",
        "Revenue Growth": 0,
        "EPS Growth": 0,
        "Operating Margin": 20,
        "Free Cash Flow": 100,
        "Current Ratio": 1.5,
    }
    component = build_components(row)["fundamentals"]
    assert "revenue_growth_pct" not in component["missing_fields"]
    assert component["data"]["revenue_growth_pct"] == 0

def test_missing_financial_data_does_not_create_neutral_score():
    component = build_components({"Ticker": "TEST"})["fundamentals"]
    assert component["status"] == "NOT_LOADED"
    assert component["score"] is None
