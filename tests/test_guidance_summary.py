from __future__ import annotations

from engines.guidance_summary import build_guidance_summary, guidance_summary_text


def rich_row():
    return {
        "ticker": "CRM",
        "company": "Salesforce",
        "committee_verdict": "ACCUMULATE",
        "confidence_pct": 72.5,
        "position_size_range": "2–4%",
        "entry_status": "Wait for preferred entry zone",
        "current_price": 200.0,
        "atlas_fair_value": 324.22,
        "expected_return_pct": 62.1,
        "revenue_growth": 0.133,
        "earnings_growth": 0.522,
        "operating_profit_margin": 0.218,
        "free_cash_flow": 6_556_000_000,
        "latest_earnings_date": "2026-05-27",
        "next_earnings_date": "2026-08-26T20:00:00+00:00",
        "eps_surprise_pct": 23.96,
        "analyst_target_mean": 241.72,
        "analyst_count": 53,
        "latest_news_headline": "Salesforce launches verified new enterprise product",
        "generated_at": "2026-08-11T12:07:35+00:00",
        "components": {"fundamentals": 69.0, "technical": 75.1},
    }


def test_rich_evidence_prioritizes_company_facts_over_score_narration():
    guidance = build_guidance_summary(rich_row())
    substance = " ".join(item["fact"] for item in guidance["supporting_facts"])

    assert "revenue growth is 13.3%" in substance
    assert "earnings growth is 52.2%" in substance
    assert "EPS beat estimates by 24.0%" in substance
    assert "$6.6B" in substance
    assert "69.0/100" not in guidance_summary_text(guidance)
    assert "75.1/100" not in guidance_summary_text(guidance)


def test_sparse_evidence_is_honestly_labeled_technical_or_analyst_heavy():
    guidance = build_guidance_summary({
        "ticker": "SPARSE",
        "committee_verdict": "MONITOR",
        "current_price": 20,
        "analyst_target_mean": 24,
        "sma50": 18,
    })

    assert guidance["evidence_limited"] is True
    assert "evidence-limited" in guidance["atlas_view"]["interpretation"]
    assert "Revenue and earnings growth" in guidance["unavailable_evidence"]
    assert "Canonical Atlas Fair Value" in guidance["unavailable_evidence"]


def test_catalyst_requires_a_verified_date_and_never_invents_one():
    invalid = build_guidance_summary({"ticker": "TEST", "next_earnings_date": "sometime next quarter"})
    valid = build_guidance_summary({"ticker": "TEST", "next_earnings_date": "2026-09-14T20:00:00Z"})

    assert invalid["next_catalyst"]["date"] is None
    assert invalid["next_catalyst"]["verification_status"] == "Unavailable"
    assert valid["next_catalyst"]["date"] == "2026-09-14"
    assert valid["next_catalyst"]["verification_status"] == "Verified provider date"


def test_missing_evidence_is_not_fabricated():
    guidance = build_guidance_summary({"ticker": "TEST", "committee_verdict": "MONITOR"})

    assert guidance["supporting_facts"] == []
    assert guidance["key_risks"] == []
    assert guidance["next_catalyst"]["event"] == "No verified next catalyst is available"
    assert guidance["action_now"]["entry_timing_context"] == "No verified entry/timing instruction is available."


def test_canonical_fair_value_and_analyst_target_remain_distinct():
    guidance = build_guidance_summary({
        "ticker": "TEST",
        "current_price": 100,
        "atlas_fair_value": 140,
        "validated_fair_value": 125,
        "analyst_target_mean": 110,
        "ai_base_target": 160,
        "target": 170,
    })
    facts = [item["fact"] for item in guidance["supporting_facts"]]

    assert any("Canonical Atlas Fair Value is $140.00" in fact for fact in facts)
    assert any("Wall Street's average target is $110.00" in fact for fact in facts)
    assert all("$125.00" not in fact and "$160.00" not in fact and "$170.00" not in fact for fact in facts)


def test_legacy_target_is_not_presented_as_canonical_fair_value():
    guidance = build_guidance_summary({
        "ticker": "TEST",
        "current_price": 100,
        "validated_fair_value": 125,
        "ai_base_target": 130,
        "target": 135,
    })

    assert "Canonical Atlas Fair Value" in guidance["unavailable_evidence"]
    assert all("Canonical Atlas Fair Value is" not in item["fact"] for item in guidance["supporting_facts"])


def test_verdict_and_trade_action_fields_pass_through_unchanged():
    guidance = build_guidance_summary(rich_row())

    assert guidance["atlas_view"]["verdict"] == "ACCUMULATE"
    assert guidance["atlas_view"]["confidence"] == 72.5
    assert guidance["action_now"] == {
        "current_action": "Accumulate",
        "entry_timing_context": "Wait for preferred entry zone",
        "position_size_guidance": "2–4%",
    }


def test_same_evidence_is_deterministic():
    assert build_guidance_summary(rich_row()) == build_guidance_summary(dict(rich_row()))


def test_different_evidence_produces_materially_different_substance():
    crm = guidance_summary_text(build_guidance_summary(rich_row()))
    sparse = guidance_summary_text(build_guidance_summary({
        "ticker": "SPARSE",
        "committee_verdict": "MONITOR",
        "analyst_target_mean": 25,
    }))

    assert crm != sparse
    assert "13.3%" in crm
    assert "13.3%" not in sparse
    assert "evidence-limited" in sparse
