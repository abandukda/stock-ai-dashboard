
from engines.component_builder import build_components

def test_missing_rsi_is_not_zero():
    row = {
        "Ticker": "TEST",
        "Price": 100,
        "20D %": 3,
        "Volume Ratio": 1.2,
    }
    component = build_components(row)["technical"]
    assert component["data"]["rsi"] is None
    assert "rsi" in component["missing_fields"]

def test_real_zero_rsi_is_preserved():
    row = {
        "Ticker": "TEST",
        "Price": 100,
        "RSI": 0,
        "20D %": 0,
        "Volume Ratio": 1,
    }
    component = build_components(row)["technical"]
    assert component["data"]["rsi"] == 0
