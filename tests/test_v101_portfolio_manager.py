from engines.portfolio_manager_engine import build_portfolio_plan,validate_portfolio_contract
def test_portfolio():
    c=[{"ticker":"NVDA","opportunity_score":96},{"ticker":"MSFT","opportunity_score":90},{"ticker":"LLY","opportunity_score":80}]
    m=build_portfolio_plan(c)
    assert m["recommended_cash_pct"]>=0
    assert validate_portfolio_contract(m)==[]
def test_top_alloc():
    m=build_portfolio_plan([{"ticker":"A","opportunity_score":100},{"ticker":"B","opportunity_score":50}])
    assert m["allocations"][0]["recommended_allocation_pct"]>=m["allocations"][1]["recommended_allocation_pct"]
def test_readonly():
    assert build_portfolio_plan([])["read_only"] is True
