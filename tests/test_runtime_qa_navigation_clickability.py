from agents.atlas_runtime_qa_v2 import DESTRUCTIVE_TERMS


def test_transaction_actions_remain_blocked():
    assert "buy" in DESTRUCTIVE_TERMS
    assert "sell" in DESTRUCTIVE_TERMS
    assert "delete" in DESTRUCTIVE_TERMS
