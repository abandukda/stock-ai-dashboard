from copy import deepcopy

import pytest

from engines.decision_metrics_v1 import METHODOLOGY_VERSION, build_decision_metrics, valuation_quality


def inputs():
    return {
        "technical": {"status": "AVAILABLE", "score": 80, "state": "NEAR_BREAKOUT", "feed_health": "HEALTHY", "fingerprint": "TECH-1"},
        "fundamentals": {"status": "PARTIAL", "score": 70, "data": {
            "revenue_growth_pct": 12, "eps_growth_pct": 9, "operating_margin_pct": 18,
            "free_cash_flow": 10, "operating_cash_flow": 12,
        }},
        "valuation": {"status": "PUBLISHED", "fair_value": 120, "expected_return": 20, "validation_passed": True},
        "risk": {"status": "AVAILABLE", "net_debt_to_ebitda": 1.5, "evidence": {"drawdown_risk": "moderate"}},
        "trade_plan": {"entry_low": 98, "entry_high": 102, "stop": 90, "target": 126, "risk_reward": 2.0},
        "volume": {"status": "AVAILABLE", "relative_volume": 1.25, "completed_daily_evidence": True,
                   "valid_daily_volume_baseline": True, "feed_health": "HEALTHY", "statistic": "DAILY_RELATIVE_VOLUME"},
        "market_snapshot": {"price": 100, "fresh_current_price": True},
    }


def test_six_pillars_publish_governed_values_and_partial_coverage():
    result = build_decision_metrics(**inputs())
    assert result["decision_metrics_methodology"] == METHODOLOGY_VERSION
    assert result["technical_quality"]["score"] == 80
    assert result["fundamental_quality"]["score"] == 70
    assert result["fundamental_quality"]["coverage_fraction"] == .8
    assert result["fundamental_quality"]["effective_weight"] == 16
    assert result["valuation_quality"]["score"] == 70
    assert result["risk_quality"]["coverage_fraction"] == 1
    assert result["entry_quality"]["score"] == 100
    assert result["volume_quality"]["score"] == 80
    assert result["component_coverage"] == 96
    assert result["opportunity"] is not None
    assert result["decision_confidence"] is not None


@pytest.mark.parametrize("expected,score", [(-1, 0), (0, 0), (5, 30), (7.5, 40), (15, 60), (35, 87), (50, 100), (80, 100)])
def test_valuation_interpolation(expected, score):
    assert valuation_quality({"status": "PUBLISHED", "fair_value": 1, "expected_return": expected})["score"] == score


def test_unavailable_is_not_zero_but_legitimate_zero_is_covered():
    rejected = valuation_quality({"status": "REJECTED_EXTREME_UPSIDE", "fair_value": None, "expected_return": None})
    zero = valuation_quality({"status": "PUBLISHED", "fair_value": 100, "expected_return": 0})
    assert rejected["score"] is None and rejected["effective_weight"] == 0
    assert zero["score"] == 0 and zero["effective_weight"] == 20


def test_partial_fundamentals_need_three_families_and_are_proportional():
    source = inputs()
    source["fundamentals"] = {"status": "PARTIAL", "score": 55, "data": {"revenue_growth_pct": 0, "eps_growth_pct": -2}}
    unavailable = build_decision_metrics(**source)["fundamental_quality"]
    assert unavailable["score"] is None and unavailable["effective_weight"] == 0
    source["fundamentals"]["data"]["current_ratio"] = 0
    available = build_decision_metrics(**source)["fundamental_quality"]
    assert available["score"] == 55 and available["effective_weight"] == 12


def test_phase2_or_degraded_volume_cannot_enter_volume_quality():
    for mutation in (
        {"statistic": "TIME_ALIGNED_RVOL_V1"}, {"completed_daily_evidence": False},
        {"valid_daily_volume_baseline": False}, {"feed_health": "DEGRADED"},
    ):
        source = inputs(); source["volume"].update(mutation)
        volume = build_decision_metrics(**source)["volume_quality"]
        assert volume["score"] is None and volume["effective_weight"] == 0


def test_prohibited_context_cannot_change_any_decision_metric():
    base = inputs()
    first = build_decision_metrics(**base)
    prohibited = {
        "scan_conviction": 1, "relative_rank_score": 999, "wall_street_target": 9999,
        "analyst_rating": "strong_buy", "insider_activity": "buy", "institutional_ownership": 99,
        "political_evidence": "supportive", "news_sentiment": 100, "llm_output": "BUY NOW",
    }
    mutated = deepcopy(base)
    for contract in mutated.values():
        if isinstance(contract, dict):
            contract.update(prohibited)
    changed = build_decision_metrics(**mutated)
    assert changed == first


def test_canonical_evaluation_publishes_one_shared_decision_metrics_contract():
    from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation
    source = inputs()
    result = build_canonical_evaluation(
        "NVDA", evaluation_mode="ON_DEMAND", market_snapshot=source["market_snapshot"],
        technical=source["technical"], fundamentals=source["fundamentals"], risk=source["risk"],
        trade_plan=source["trade_plan"], valuation_inputs={"forward_eps": 10, "revenue_growth": 10,
        "operating_margin": 20}, evidence_ids=["E-1"],
    )
    assert result["decision_metrics_methodology"] == METHODOLOGY_VERSION
    assert result["opportunity"] == result["decision_metrics"]["opportunity"]
    assert result["decision_confidence"] == result["decision_metrics"]["decision_confidence"]
    assert result["component_coverage"] == result["decision_metrics"]["component_coverage"]
    for key in ("technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality"):
        assert result[key] == result["decision_metrics"][key]


def test_opportunity_and_confidence_publication_thresholds():
    source = inputs()
    source["valuation"] = {"status": "REJECTED_EXTREME_UPSIDE"}
    source["volume"] = {"status": "DATA_UNAVAILABLE"}
    result = build_decision_metrics(**source)
    assert result["component_coverage"] == 66
    assert result["opportunity"] is not None
    assert result["decision_confidence"] is not None
    source["trade_plan"] = {}
    result = build_decision_metrics(**source)
    # Cash-flow evidence still contributes 25% of the 15-point Risk pillar.
    assert result["component_coverage"] == 52.25
    assert result["opportunity"] is None
    assert result["decision_confidence"] is None
