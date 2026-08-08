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


def test_target_details_separates_atlas_and_wall_street():
    from engines.research_engine import target_details
    # Generic `target` is a legacy/trade field and must not be silently treated
    # as an independently modelled Atlas fair value.
    row = {"price": 100, "ai_base_target": 125, "target_mean_price": 115}
    result = target_details(row)
    assert result["atlas_target"] == 125
    assert result["wall_street_target"] == 115
    assert round(result["atlas_upside_pct"], 1) == 25.0

def test_financial_snapshot_calculates_net_cash():
    from engines.research_engine import build_financial_snapshot
    result = build_financial_snapshot({"total_cash": 500, "total_debt": 125, "free_cashflow": 50})
    assert result["net_cash"] == 375
    assert result["free_cash_flow"] == 50
