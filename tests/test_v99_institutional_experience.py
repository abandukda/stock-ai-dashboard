from ui.institutional_experience import build_card_view_model, index_by_ticker

def test_v99_builds_view_model():
    row = {"Ticker":"NVDA","Company":"NVIDIA","Recommendation":"Buy Now",
           "v93_snapshot":{"current_price":100,"atlas_fair_value":125,
           "expected_return_pct":25,"confidence":90,"research_completeness_pct":95}}
    ranking = {"opportunity_score":96.4,"opportunity_tier":"ELITE",
               "overall_rank":3,"universe_count":8000,"top_percentile_text":"Top 0.04%"}
    vm = build_card_view_model(row, ranking=ranking, competition={"portfolio_rank":2})
    assert vm["opportunity_score"] == 96.4
    assert vm["expected_return"] == 25
    assert vm["portfolio_rank"] == 2

def test_v99_preserves_zero_values():
    row = {"Ticker":"ZERO","v93_snapshot":{"current_price":0,"expected_return_pct":0,"confidence":0}}
    vm = build_card_view_model(row)
    assert vm["current_price"] == 0
    assert vm["expected_return"] == 0
    assert vm["confidence"] == 0

def test_v99_indexes_by_ticker():
    result = index_by_ticker([{"ticker":"nvda"},{"Ticker":"MSFT"}])
    assert set(result) == {"NVDA","MSFT"}
