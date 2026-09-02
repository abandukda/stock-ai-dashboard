from __future__ import annotations

import pandas as pd

from app import normalize_scan_row
from engines.earnings_decision_story import build_earnings_decision_story
from engines.full_scan_decision_story import build_full_scan_decision_story
from engines.recovery_decision_story import build_recovery_decision_story
from engines.research_context import (
    build_decision_availability, build_production_decision, build_research_context,
)
from ui.full_scan_vnext import _filter_stories, _production_stories
from ui.home_v104 import _home_decision_presentation, build_home_opportunity_card


def _no_decision_row(ticker="MU", *, partial=False):
    row = {
        "ticker": ticker,
        "company_name": ticker,
        "recommendation_key": "strong_buy",  # Wall Street context only.
        "confidence": 97,
        "conviction": 97,
        "relative_rank_score": 130.28,
        "expected_upside_pct": 25.0,
        "entry_low": 10.0,
        "entry_high": 11.0,
        "stop_loss": 9.0,
        "trade_target_1": 12.0,
        "rsi": 55.0,
        "revenue_growth": 0.1,
    }
    if not partial:
        row.update({"analyst_target_mean": 14.0, "news_evidence": [{"headline": "Verified"}]})
    return row


def test_analyst_recommendation_is_not_promoted_to_atlas_decision():
    normalized = normalize_scan_row(_no_decision_row())
    assert normalized["Recommendation"] == "N/A"
    assert normalized["Analyst Recommendation"] == "strong_buy"
    normalized_decision = build_production_decision(normalized)
    assert normalized_decision["semantic_status"] == "DATA_UNAVAILABLE"
    assert normalized_decision["recommendation"] is None
    decision = build_production_decision(_no_decision_row())
    assert decision["semantic_status"] == "DATA_UNAVAILABLE"
    assert decision["recommendation"] is None
    assert decision["opportunity"] is None
    assert decision["confidence"] == 97
    assert decision["availability"]["reason_code"] == "CANONICAL_RECOMMENDATION_NOT_PUBLISHED"
    assert decision["availability"]["confidence_label"] == "Scan Conviction"


def test_high_and_partial_evidence_no_decision_are_explained_without_fallback():
    for row in (_no_decision_row("MU"), _no_decision_row("DAR", partial=True)):
        availability = build_production_decision(row)["availability"]
        assert availability["decision_status"] == "DECISION_NOT_ISSUED"
        assert availability["decision_available"] is False
        assert "Canonical ATLAS Recommendation" in availability["missing_confirmation"]
        assert "MONITOR" not in str(availability).upper()
        assert "BUY NOW" not in str(availability).upper()


def test_true_source_missing_is_distinct_from_decision_not_issued():
    availability = build_decision_availability({"ticker": "EMPTY"})
    assert availability["decision_status"] == "INSUFFICIENT_SOURCE_DATA"
    assert availability["reason_code"] == "SOURCE_DATA_MISSING"


def test_valid_decision_and_independent_opportunity_and_missing_fv():
    decision = build_production_decision({
        "ticker": "AAA", "Recommendation": "BUY NOW", "Opportunity": 0,
        "Confidence": -1, "atlas_fair_value": None,
    })
    assert decision["semantic_status"] == "AVAILABLE"
    assert decision["recommendation"] == "BUY NOW"
    assert decision["opportunity"] == 0
    assert decision["confidence"] == -1
    assert decision["atlas_fair_value"] is None
    assert decision["availability"]["decision_status"] == "DECISION_AVAILABLE"


def test_cross_surface_contract_is_identical():
    row = _no_decision_row()
    context = build_research_context(ticker="MU", production_row=row)
    expected = dict(context["production_decision"]["availability"])
    full = build_full_scan_decision_story(row, production_rank=1)
    recovery = build_recovery_decision_story({**row, "research_context": context})
    earnings = build_earnings_decision_story({**row, "research_context": context})
    home = build_home_opportunity_card({**row, "research_context": context})
    assert full["decision_availability"] == expected
    assert recovery["decision_availability"] == expected
    assert earnings["decision_availability"] == expected
    assert home["decision_availability"] == expected


def test_full_scan_rank_and_filter_do_not_create_decisions():
    row = _no_decision_row()
    frame = pd.DataFrame([{"Ticker": "MU", "Production Rank": 1, "Raw": row}])
    stories = _production_stories(frame)
    filtered = _filter_stories(stories)
    assert filtered[0]["production_rank"] == 1
    assert filtered[0]["filtered_position"] == 1
    assert filtered[0]["canonical_state"] is None
    assert filtered[0]["opportunity"] is None


def test_missing_technical_state_does_not_invent_a_decision_gate():
    row = _no_decision_row()
    row.pop("rsi")
    availability = build_production_decision(row)["availability"]
    assert availability["reason_code"] == "CANONICAL_RECOMMENDATION_NOT_PUBLISHED"
    assert "technical gate" not in str(availability).lower()


def test_home_decision_not_issued_renders_full_shared_contract():
    card = build_home_opportunity_card(_no_decision_row())
    availability = card["decision_availability"]
    assert card["state"] == "Decision not issued"
    assert card["preferred_action"] == "No canonical action issued"
    assert availability["decision_status"] == "DECISION_NOT_ISSUED"
    assert availability["confidence_label"] == "Scan Conviction"
    assert availability["customer_reason"]
    assert availability["evidence_present"]
    assert availability["missing_confirmation"] == (
        "Canonical ATLAS Recommendation", "Canonical Opportunity",
    )
    assert availability["what_atlas_is_waiting_for"]
    rendered = str(card).upper()
    assert "MONITOR" not in rendered
    assert "STRONG_BUY" not in str(card["state"]).upper()


def test_home_insufficient_source_data_is_distinct():
    card = build_home_opportunity_card({"ticker": "EMPTY", "company": "Empty"})
    assert card["state"] == "Decision unavailable"
    assert card["preferred_action"] == "Required source evidence missing"
    assert card["decision_availability"]["decision_status"] == "INSUFFICIENT_SOURCE_DATA"


def test_home_available_decision_preserves_action_and_zero_negative_values():
    row = _no_decision_row("ZERO") | {
        "Recommendation": "BUY NOW", "Opportunity": 0, "Confidence": -1,
        "guidance_summary": {"action_now": {"current_action": "Use the canonical action."}},
    }
    card = build_home_opportunity_card(row)
    assert card["state"] == "BUY NOW"
    assert card["preferred_action"] == "Use the canonical action."
    assert card["opportunity"] == 0
    assert card["confidence"] == -1
    assert card["decision_availability"]["decision_status"] == "DECISION_AVAILABLE"


def test_home_presentation_consumes_contract_without_reclassifying_it():
    decision = build_production_decision(_no_decision_row())
    presentation = _home_decision_presentation(decision)
    assert presentation["availability"] == decision["availability"]
    full = build_full_scan_decision_story(_no_decision_row(), production_rank=1)
    context = build_research_context(ticker="MU", production_row=_no_decision_row())
    assert presentation["availability"] == full["decision_availability"]
    assert presentation["availability"] == context["production_decision"]["availability"]


def test_home_source_renders_every_structured_availability_field():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    for field in (
        "customer_reason", "evidence_present", "missing_confirmation",
        "what_atlas_is_waiting_for", "confidence_label",
    ):
        assert field in source
