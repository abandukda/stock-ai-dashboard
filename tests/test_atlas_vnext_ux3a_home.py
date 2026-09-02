from __future__ import annotations

from agents.runtime_qa_architecture import protected_decision_digest
from engines.research_context import build_production_decision
from engines.research_engine import begin_research_entry
from ui.home_v104 import (
    _market_brief_items,
    build_home_opportunity_card,
    select_best_opportunities,
    select_watch_closely,
)


def _row(ticker="NVDA", **overrides):
    row = {
        "ticker": ticker,
        "company": f"{ticker} Corp",
        "Recommendation": "BUY_NOW",
        "Opportunity": 84,
        "Confidence": 78,
        "decision_expected_return_pct": 18.4,
        "preferred_entry_low": 95,
        "preferred_entry_high": 101,
        "technical_state": "NEAR_BREAKOUT",
        "guidance_summary": {
            "supporting_facts": [{"fact": "Revenue growth and earnings evidence remain supportive while the deterministic setup approaches confirmation."}],
            "key_risks": [{"risk": "Valuation remains elevated relative to current growth evidence."}],
            "next_catalyst": {"event": "Next verified earnings report", "date": "2026-09-01"},
            "action_now": {"current_action": "Wait for the preferred zone or deterministic breakout confirmation."},
        },
    }
    row.update(overrides)
    return row


def test_ux3a_card_uses_immutable_distinct_decision_fields():
    source = _row()
    before = protected_decision_digest(build_production_decision(source))
    card = build_home_opportunity_card(source)
    after = protected_decision_digest(card["production_decision"])
    assert before == after
    assert card["state"] == "BUY_NOW"
    assert card["opportunity"] == 84
    assert card["confidence"] == 78
    assert card["supported_upside"] == 18.4
    assert "position_size" not in card
    assert "trade_plan" not in card


def test_nested_persisted_row_remains_immutable_decision_authority():
    source = _row(raw={
        "ticker": "NVDA", "Recommendation": "MONITOR", "Opportunity": 61,
        "Confidence": 72, "decision_expected_return_pct": 9.5,
    })
    card = build_home_opportunity_card(source)
    assert card["state"] == "MONITOR"
    assert card["opportunity"] == 61
    assert card["confidence"] == 72
    assert card["supported_upside"] == 9.5


def test_card_thesis_is_grounded_bounded_and_fails_closed():
    card = build_home_opportunity_card(_row())
    assert len(card["thesis"].split()) <= 30
    missing = build_home_opportunity_card(_row(guidance_summary={}))
    assert missing["thesis"] == "Grounded thesis unavailable"
    assert missing["catalyst"] == "Catalyst unavailable"
    assert missing["risk"] == "Unavailable"


def test_best_opportunities_preserve_input_rank_and_limit():
    rows = [_row(str(index), Opportunity=100 - index) for index in range(10)]
    cards = select_best_opportunities(rows)
    assert [card["ticker"] for card in cards] == [str(index) for index in range(8)]


def test_watch_closely_uses_only_existing_deterministic_states():
    rows = [
        _row("A", technical_state="NEAR_BREAKOUT"),
        _row("B", technical_state="SETUP_FORMING"),
        _row("C", technical_state="NO_SETUP"),
    ]
    assert [card["ticker"] for card in select_watch_closely(rows)] == ["A", "B"]


def test_market_brief_is_grounded_and_limited_to_four_short_items():
    items = _market_brief_items(
        {"morning_view": "Atlas is selective today with evidence concentrated in a small number of ranked opportunities."},
        {
            "market_regime": "RISK_ON",
            "upcoming_earnings": [{"ticker": "NVDA"}],
            "major_research_changes": ["NVDA evidence changed"],
        },
    )
    assert len(items) == 4
    assert all(len(item.split()) <= 25 for item in items)


def test_home_investment_case_handoff_preserves_exact_ticker_and_session():
    state = {"authenticated": True, "role": "viewer", "active_research_ticker": "OLD"}
    result = begin_research_entry(
        state, "NVDA", source="HOME_TIER_CARD",
        interaction_id="home_ux3_best_1_NVDA",
    )
    assert result["ticker"] == "NVDA"
    assert state["active_research_ticker"] == "NVDA"
    assert state["v79_pending_research_ticker"] == "NVDA"
    assert state["v79_pending_page"] == "Research Any Ticker"
    assert state["authenticated"] is True


def test_missing_production_and_etf_inputs_remain_fail_closed():
    missing = build_home_opportunity_card({"ticker": "MISSING", "company": "Missing"})
    assert missing["state"] == "Decision unavailable"
    assert missing["preferred_action"] == "Required source evidence missing"
    assert missing["opportunity"] is None
    assert missing["confidence"] is None
    assert missing["supported_upside"] is None
    etf = build_home_opportunity_card(_row("SCHD", security_type="ETF", Recommendation="MONITOR"))
    assert etf["state"] == "MONITOR"
    assert etf["ticker"] == "SCHD"


def test_ux3a_home_source_has_responsive_hierarchy_and_no_position_sizing():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    for label in (
        "ATLAS Today", "Market Brief", "What matters today",
        "Best Opportunities Right Now", "Watch Closely / Near Breakout",
        "Recovery Opportunities", "Watchlist & Holdings", "Deeper Market Detail",
        "View Investment Case",
    ):
        assert label in source
    assert "atlas-ux3-card-head" in source
    assert "atlas-ux3-metrics" in source
