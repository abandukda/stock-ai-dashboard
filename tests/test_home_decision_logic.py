from engines.research_engine import (
    atlas_fair_value_details,
    decision_strength,
    recommendation_tier,
    research_navigation_state,
)
from services.ai_synthesis import build_plain_english_reasons, build_primary_risk_sentence


def test_repeated_30_percent_target_is_rejected_not_blended():
    details = atlas_fair_value_details({"price": 100, "target": 130, "target_mean_price": 112})
    assert details["atlas_fair_value"] is None
    assert details["expected_return_pct"] is None
    assert details["wall_street_consensus"] == 112
    assert details["decision_upside_pct"] == 12
    assert details["rejected_legacy_placeholder"] is True
    assert "under review" in details["source"].lower()


def test_independent_atlas_value_is_kept_when_not_legacy_pattern():
    details = atlas_fair_value_details({"price": 100, "Atlas Fair Value": 118, "target_mean_price": 112})
    assert details["atlas_fair_value"] == 118
    assert round(details["expected_return_pct"], 1) == 18.0


def test_company_specific_reasons_differ_for_different_financial_profiles():
    growth = build_plain_english_reasons(
        {"revenue_growth": 0.28, "earnings_growth": 0.35, "operating_margin": 0.25, "rsi": 54},
        atlas_fair_value=125,
        current_price=100,
    )
    balance_sheet = build_plain_english_reasons(
        {"revenue_growth": 0.06, "free_cashflow": 500_000_000, "total_cash": 2_000_000_000, "total_debt": 200_000_000, "forward_pe": 15},
        atlas_fair_value=None,
        current_price=100,
    )
    assert growth != balance_sheet
    assert any("28.0%" in x for x in growth)
    assert any("Cash exceeds debt" in x for x in balance_sheet)
    assert all(len(x) < 120 for x in growth + balance_sheet)


def test_primary_risk_selects_material_metric_not_generic_earnings_text():
    debt_risk = build_primary_risk_sentence({
        "total_debt": 1_000_000_000,
        "total_cash": 200_000_000,
        "what_could_go_wrong": "earnings can create gap risk; avoid oversized positions before the report",
    })
    valuation_risk = build_primary_risk_sentence({"forward_pe": 58, "total_debt": 100, "total_cash": 500})
    liquidity_risk = build_primary_risk_sentence({"current_ratio": 0.62})
    assert "Debt" in debt_risk
    assert "forward P/E" in valuation_risk
    assert "current ratio" in liquidity_risk
    assert len({debt_risk, valuation_risk, liquidity_risk}) == 3
    assert all(x.endswith(".") and "..." not in x for x in (debt_risk, valuation_risk, liquidity_risk))


def test_qualified_stock_can_be_high_conviction_without_old_buy_label():
    row = {
        "technical_agent_score": 94,
        "fundamentals_agent_score": 92,
        "financial_score": 90,
        "risk_agent_score": 80,
        "valuation_agent_score": 75,
        "current_ratio": 1.6,
    }
    assert decision_strength(row, 84, 18) >= 77
    assert recommendation_tier(row, 84, 18) == "HIGH CONVICTION BUY"


def test_recommendation_tiers_are_distinct_and_evidence_based():
    strong = {"technical_agent_score": 92, "fundamentals_agent_score": 90, "financial_score": 88, "risk_agent_score": 78}
    moderate = {"technical_agent_score": 75, "fundamentals_agent_score": 68, "financial_score": 66, "risk_agent_score": 65}
    weak = {"technical_agent_score": 48, "fundamentals_agent_score": 45, "financial_score": 42, "risk_agent_score": 40}
    assert recommendation_tier(strong, 82, 15) == "HIGH CONVICTION BUY"
    assert recommendation_tier(moderate, 72, 8) in {"BUY ON WEAKNESS", "WAIT FOR CONFIRMATION"}
    assert recommendation_tier(weak, 45, -5) == "AVOID"


def test_research_navigation_handoff_is_single_and_query_param_free():
    state = research_navigation_state(" msft ")
    assert state["v79_pending_research_ticker"] == "MSFT"
    assert state["active_research_ticker"] == "MSFT"
    assert "typed_ticker" not in state
    assert "v73_research_ticker" not in state
    assert state["v79_pending_page"] == "Research Any Ticker"
    assert state["v73_page"] == "Research Any Ticker"
    assert "v784_single_nav" not in state
    assert all("?" not in value for value in state.values())
