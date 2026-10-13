from scripts.build_g6_enterprise_expansion_plan import build_plan


def test_plan_deduplicates_and_separates_contract_observation_and_controls():
    rows = [
        {"ticker": "NVDA", "endpoint_family": "financial_statements", "customer_published": "True", "publishable_buy_now": "True"},
        {"ticker": "NVDA", "endpoint_family": "financial_statements", "customer_published": "True", "publishable_buy_now": "True"},
        {"ticker": "NVDA", "endpoint_family": "basic_financials", "customer_published": "True", "publishable_buy_now": "True"},
    ]
    plan = build_plan(rows)
    assert plan["stage_0_response_validation"]["request_count"] == 1
    assert plan["expanded_scope"]["request_count"] == 5
    assert plan["contractual_rights"]["explicit_numeric_rpm"] is None
    assert plan["observed_behavior"]["status"] == "UNOBSERVED_FOR_THIS_SCOPE"
    assert plan["engineering_controls"]["initial_rpm"] == 60
    assert plan["provider_calls"] == 0


def test_unpublished_rows_do_not_enter_scope():
    plan = build_plan([{"ticker": "CRC", "endpoint_family": "financial_statements", "customer_published": "False", "publishable_buy_now": "False"}])
    assert plan["source_gap_inventory"]["published_tickers"] == 0
    assert plan["expanded_scope"]["request_count"] == 0
