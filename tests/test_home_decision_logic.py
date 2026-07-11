from engines.research_engine import atlas_fair_value_details, recommendation_tier
from services.ai_synthesis import build_plain_english_reasons, build_primary_risk_sentence


def test_legacy_30_percent_is_not_displayed_as_identical_fair_value_when_consensus_exists():
    row = {"price": 100, "target": 130, "target_2": 145, "target_mean_price": 112}
    details = atlas_fair_value_details(row)
    assert details["atlas_fair_value"] != 130
    assert round(details["expected_return_pct"], 1) != 30.0
    assert details["source"] == "Atlas blended fair value"


def test_fair_values_vary_with_company_inputs():
    a = atlas_fair_value_details({"price": 100, "target": 130, "target_mean_price": 110})
    b = atlas_fair_value_details({"price": 100, "target": 130, "target_mean_price": 125})
    assert a["atlas_fair_value"] != b["atlas_fair_value"]


def test_primary_risk_is_complete_sentence_without_ellipsis():
    risk = build_primary_risk_sentence({"what_could_go_wrong": "earnings can create gap risk; avoid oversized positions before the report"})
    assert risk.endswith(".")
    assert "..." not in risk
    assert len(risk) < 100


def test_plain_reasons_are_short_and_understandable():
    reasons = build_plain_english_reasons(
        {"revenue_growth": 0.22, "free_cashflow": 100000000, "total_cash": 300, "total_debt": 100, "rsi": 55},
        atlas_fair_value=120,
        current_price=100,
    )
    assert 1 <= len(reasons) <= 4
    assert all(len(x) < 100 for x in reasons)


def test_recommendation_taxonomy_is_consistent():
    assert recommendation_tier({"recommendation": "buy"}, 88, 18) == "HIGH CONVICTION BUY"
    assert recommendation_tier({}, 78, 10) == "BUY ON WEAKNESS"
    assert recommendation_tier({}, 65, 3) == "WAIT FOR CONFIRMATION"
