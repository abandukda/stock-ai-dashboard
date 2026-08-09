from agents.runtime_qa_reasonableness import evaluate_visible_page

def test_buy_now_low_confidence_is_flagged():
    issues=evaluate_visible_page("Test","BUY NOW Confidence 42 Expected Return 20")
    assert any(x["category"]=="Decision Reasonableness" for x in issues)

def test_invalid_score_range_is_flagged():
    assert any(x["category"]=="Score Range" for x in evaluate_visible_page("Test","Opportunity 132"))
