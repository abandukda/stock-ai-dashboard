from __future__ import annotations

import copy

from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines.guidance_summary import build_guidance_summary
from engines.research_enrichment_v105 import (
    accepted_company_news,
    build_political_section,
    normalize_analyst_actions,
)
from engines.semantic_fields import (
    canonical_atlas_fair_value,
    scanner_trade_plan,
    valuation_families,
)
from engines.trade_plan_v1052 import build_trade_plan
from services.ai_synthesis import build_ticker_context


def _row(**updates):
    row = {
        "ticker": "TEST",
        "company": "Test Systems Inc.",
        "current_price": 100.0,
        "opportunity_score": 71.9,
        "confidence_pct": 78.9,
        "committee_verdict": "BUY_NOW",
        "atlas_fair_value": 130.0,
        "analyst_target_mean": 120.0,
        "analyst_target_high": 145.0,
        "analyst_target_low": 90.0,
        "analyst_count": 20,
        "ai_bear_target": 85.0,
        "ai_base_target": 125.0,
        "ai_bull_target": 155.0,
        "entry_low": 96.0,
        "entry_high": 101.0,
        "stop_loss": 90.0,
        "target_1": 118.0,
        "target_2": 127.0,
        "risk_reward": 1.8,
    }
    row.update(updates)
    return row


def test_only_explicit_canonical_fields_resolve_as_atlas_fair_value():
    for alias in (
        "target", "Atlas Target", "ai_base_target", "analyst_target_mean",
        "analyst_target_high", "analyst_target_low", "validated_fair_value",
        "trade_target_1", "trade_target_2", "AI Fair Value",
    ):
        assert canonical_atlas_fair_value({alias: 150.0}) is None
    assert canonical_atlas_fair_value({"atlas_fair_value": 0.0}) == 0.0
    assert canonical_atlas_fair_value({"Atlas Fair Value": -5.0}) == -5.0


def test_valuation_families_keep_returns_separate_and_missing_atlas_unavailable():
    values = valuation_families(_row())
    assert values["atlas_expected_return_pct"] == 30.0
    assert values["analyst_upside_pct"] == 20.0
    assert values["scenario_base_upside_pct"] == 25.0
    missing = valuation_families(_row(atlas_fair_value=None, target=160, validated_fair_value=120))
    assert missing["atlas_fair_value"] is None
    assert missing["atlas_expected_return_pct"] is None
    assert missing["analyst_upside_pct"] == 20.0


def test_ask_ai_never_uses_target_or_scenario_as_atlas_fair_value():
    context = build_ticker_context(_row(atlas_fair_value=None, target=160, ai_base_target=150))
    assert context["atlas_fair_value"] == "Unavailable"
    assert context["atlas_expected_return"] == "Unavailable"
    assert context["analyst_target"] == "$120.00"
    assert context["scenario_base"] == "$150.00"
    assert context["recommendation"] == "BUY_NOW"
    assert context["opportunity_score"] == "71.9"
    assert context["confidence_pct"] == "78.9"


def test_persisted_scanner_trade_plan_is_preferred_without_recalculation():
    row = _row(trade_target_1=118.0, trade_target_2=127.0)
    before = copy.deepcopy(row)
    plan = build_trade_plan(row, {"price": 100.0})
    assert row == before
    assert plan["source"] == "Persisted scanner trade plan"
    assert (plan["entry_low"], plan["entry_high"], plan["stop_loss"]) == (96.0, 101.0, 90.0)
    assert (plan["target_1"], plan["target_2"], plan["risk_reward_target_1"]) == (118.0, 127.0, 1.8)
    assert plan["atlas_target"] is None


def test_legacy_explicit_target_1_is_supported_but_generic_target_is_not():
    plan = scanner_trade_plan(_row(target=999, trade_target_1=None))
    assert plan["trade_target_1"] == 118.0
    assert plan["trade_target_2"] == 127.0


def test_authoritative_v103_scores_pass_through_full_research(monkeypatch):
    monkeypatch.setattr("engines.atlas_research_builder_v2.attach_price_history", lambda row: dict(row))
    report = build_atlas_research_v2(_row())
    assert report["opportunity_score"] == 71.9
    assert report["confidence_pct"] == 78.9
    assert report["validated_fair_value"] == 130.0
    assert report["atlas_expected_return_pct"] == 30.0
    assert [case["fair_value"] for case in report["fair_value_cases"]] == [85.0, 125.0, 155.0]


def test_analyst_actions_preserve_identity_direction_math_and_date_order():
    actions = normalize_analyst_actions([
        {"firm": "Firm A", "date": "2026-08-08", "newGrade": "Buy", "previousGrade": "Hold", "priceTarget": 125, "previousPriceTarget": 100},
        {"analyst_name": "Jane Doe", "firm": "Firm B", "date": "2026-08-10", "action": "reiterated", "rating": "Outperform", "priceTarget": 140},
        {"firm": "Missing Date", "priceTarget": 150},
    ])
    assert [item["date"] for item in actions] == ["2026-08-10", "2026-08-08"]
    assert actions[0]["analyst_name"] == "Jane Doe"
    assert actions[1]["analyst_name"] is None
    assert actions[1]["firm"] == "Firm A"
    assert actions[1]["previous_rating"] == "Hold"
    assert actions[1]["current_rating"] == "Buy"
    assert actions[1]["target_change"] == 25.0
    assert actions[1]["target_change_pct"] == 25.0
    assert "Top Analyst" not in repr(actions)


def test_company_news_filters_substrings_unrelated_entities_duplicates_and_missing_provenance():
    row = {"ticker": "ELF", "company": "e.l.f. Beauty, Inc."}
    items = [
        {"headline": "e.l.f. Beauty launches a verified new product", "publisher": "Reuters", "date": "2026-08-10", "sentiment": "Positive"},
        {"headline": "e.l.f. Beauty launches a verified new product", "publisher": "Syndicate", "date": "2026-08-10"},
        {"headline": "Hackaday: ELF binary tools explained", "publisher": "Hackaday", "date": "2026-08-10"},
        {"headline": "Unrelated beauty company reports results", "publisher": "Wire", "date": "2026-08-10"},
        {"headline": "e.l.f. Beauty item without source", "date": "2026-08-10"},
    ]
    accepted = accepted_company_news(row, items)
    assert len(accepted) == 1
    assert accepted[0]["publisher"] == "Reuters"
    assert accepted[0]["relevance"] == "Accepted company/ticker match"


def test_stale_or_missing_publisher_news_is_rejected_and_cannot_create_catalyst():
    row = _row(
        company="Test Systems Inc.",
        news=[
            {"headline": "Test Systems faces a material investigation", "publisher": "Reuters", "date": "2025-01-01", "sentiment": "Negative"},
            {"headline": "Test Systems announces a product", "date": "2026-08-10", "sentiment": "Positive"},
        ],
        next_earnings_date=None,
    )
    assert accepted_company_news(row) == []
    assert build_guidance_summary(row)["next_catalyst"]["verification_status"] == "Unavailable"


def test_legitimate_negative_company_article_remains_negative_context():
    row = _row(company="Test Systems Inc.")
    accepted = accepted_company_news(row, [{
        "headline": "Test Systems faces regulatory investigation",
        "publisher": "Reuters", "date": "2026-08-10", "sentiment": "Negative",
        "classification": "Legal",
    }])
    assert len(accepted) == 1
    assert accepted[0]["sentiment"] == "Negative"
    assert accepted[0]["classification"] == "Legal"


def test_numeric_political_score_alone_does_not_create_policy_evidence():
    section = build_political_section({"ticker": "TEST", "political_score": 55})
    assert section["data"]["political_component_score"] == 55
    assert section["data"].get("policy_evidence") is None


def test_verified_policy_event_preserves_source_date_jurisdiction_and_impact():
    section = build_political_section({
        "policy_evidence": [{
            "event": "Regulator approved the company product", "date": "2026-08-10",
            "source": "Agency release", "jurisdiction": "US", "category": "Regulatory approval",
            "impact": "Supportive", "company_relevance": "Approval permits commercialization",
        }]
    })
    event = section["data"]["policy_evidence"][0]
    assert (event["source"], event["date"], event["jurisdiction"], event["impact"]) == ("Agency release", "2026-08-10", "US", "Supportive")
