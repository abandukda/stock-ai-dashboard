from copy import deepcopy

from engines.analyst_intelligence import (
    WALL_STREET_STATUSES, build_analyst_intelligence, wall_street_view_text,
)
from services.atlas_view_summary import (
    PILLAR_101, build_summary_payload, generate_summaries, summary_evidence_map,
)


def _row(**updates):
    row = {
        "ticker": "TGT", "company": "Target", "current_price": 162.71,
        "analyst_target_mean": 190.0, "analyst_target_median": 185.0,
        "analyst_target_low": 150.0, "analyst_target_high": 230.0,
        "analyst_count": 5, "strong_buy": 1, "buy": 2, "hold": 2,
        "sell": 0, "strong_sell": 0, "recommendation_key": "BUY",
        "atlas_fair_value": 247.10, "atlas_fv_upside_pct": 51.9,
        "forward_eps": 10.0, "forward_eps_source": "TWELVE_DATA",
        "forward_estimate_evidence": {"eps": {"avg_estimate": 10.0, "date": "2027-01-31"}, "evidence_ids": ("TD-EPS",)},
    }
    row.update(updates)
    return row


def _card(**updates):
    analysis = build_analyst_intelligence(_row())["wall_street_analysis"]
    card = {
        "ticker": "TGT", "company": "Target", "display_price": 162.71,
        "company_evidence": {"business_summary": "Target operates general merchandise stores.", "primary_risk": "consumer demand may weaken"},
        "fundamentals_evidence": {"revenue_growth": .04, "free_cash_flow": 1},
        "atlas_valuation_status": "PUBLISHED", "atlas_fair_value": 247.10, "atlas_expected_return": 51.9,
        "wall_street_analysis": analysis,
        "wall_street": {"mean_target": 190.0, "display_scope": "INTERNAL_TRIAL"},
        "customer_action": {"label": "BUY NOW"}, "guidance": "BUY_NOW",
        "evaluation": {"volume_quality": {"status": "AVAILABLE", "score": 35}},
        "risk_status": "AVAILABLE", "technical_status": "AVAILABLE",
    }
    card.update(updates)
    return card


def test_every_equity_receives_semantic_wall_street_state_without_fabrication():
    cases = [
        build_analyst_intelligence(_row()),
        build_analyst_intelligence({"ticker": "SMALL", "security_type": "Common Stock"}),
        build_analyst_intelligence({"ticker": "SPY", "security_type": "ETF"}),
        build_analyst_intelligence({"ticker": "ZERO", "analyst_count": 0, "analyst_coverage_evidence_id": "TD-ZERO"}),
    ]
    assert {case["wall_street_analysis"]["status"] for case in cases} <= WALL_STREET_STATUSES
    assert cases[1]["wall_street_analysis"]["status"] == "WALL_STREET_DATA_UNAVAILABLE"
    assert cases[2]["wall_street_analysis"]["status"] == "WALL_STREET_NOT_APPLICABLE"
    assert cases[3]["wall_street_analysis"]["status"] == "WALL_STREET_NOT_COVERED"
    assert cases[1]["wall_street_analysis"]["consensus"]["target_mean"] is None


def test_mean_never_uses_median_and_distribution_reconciles():
    model = build_analyst_intelligence(_row(analyst_target_mean=None, analyst_target_median=185))
    contract = model["wall_street_analysis"]
    assert contract["consensus"]["target_mean"] is None
    assert contract["consensus"]["target_median"] == 185
    assert build_analyst_intelligence(_row())["wall_street_analysis"]["rating_distribution"]["reconciles"] is True


def test_governed_twelve_forward_estimate_is_reused_with_evidence_id():
    context = build_analyst_intelligence(_row())["wall_street_analysis"]["estimate_context"]
    assert context["forward_eps"] == 10
    assert context["source_evidence_ids"] == ("TD-EPS",)


def test_wall_street_context_does_not_mutate_any_atlas_output():
    base = _row()
    locked = {key: base[key] for key in ("atlas_fair_value", "atlas_fv_upside_pct")}
    build_analyst_intelligence(base)
    changed = deepcopy(base); changed["analyst_target_mean"] = 9999
    build_analyst_intelligence(changed)
    assert {key: base[key] for key in locked} == locked
    assert {key: changed[key] for key in locked} == locked


def test_101_tgt_summary_is_plain_grounded_and_mentions_weak_volume():
    payload = build_summary_payload(_card())
    result = generate_summaries([payload], llm=lambda _: None)[0]
    text = result["text"]
    assert 90 <= len(text.split()) <= 160
    assert "$247.10" in text and "51.9%" in text and "BUY NOW" in text
    assert "trading activity" in text
    assert not any(term in text for term in ("rerate", "operating leverage", "EV/EBITDA", "net-debt bridge", "WACC", "FCF"))
    assert result["evidence_map"] == summary_evidence_map(payload)
    assert result["professional_detail"]["six_pillars"]


def test_missing_wall_street_is_explicit_not_neutral_or_raw_status():
    analysis = build_analyst_intelligence({"ticker": "SMALL"})["wall_street_analysis"]
    copy = wall_street_view_text(analysis)
    assert "No verified Wall Street consensus" in copy
    assert "DATA_UNAVAILABLE" not in copy and "neutral" not in copy.lower()


def test_six_pillar_customer_questions_are_complete():
    assert len(PILLAR_101) == 6
    assert all(text.endswith("?") for text in PILLAR_101.values())
