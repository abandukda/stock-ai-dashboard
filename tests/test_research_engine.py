from engines.research_engine import calculate_upside, validated_target, build_research_snapshot


def test_calculate_upside_uncapped():
    assert round(calculate_upside(100, 150), 1) == 50.0


def test_calculate_upside_invalid_inputs():
    assert calculate_upside(0, 150) is None
    assert calculate_upside(None, 150) is None


def test_validated_target_prefers_available_target():
    row = {"Price": 100, "Target": "", "Analyst Target": "$123.45"}
    assert validated_target(row) == 123.45


def test_build_research_snapshot():
    row = {"Ticker": "opra", "Company": "Opera Limited", "Price": "$20", "Target": "$25"}
    snap = build_research_snapshot(row)
    assert snap["ticker"] == "OPRA"
    assert snap["has_valid_target"] is True
    assert round(snap["upside_pct"], 1) == 25.0
