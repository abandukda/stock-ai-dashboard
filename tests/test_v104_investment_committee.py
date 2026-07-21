from engines.investment_committee_v104 import build_committee_verdict


def row(score, confidence, coverage, upside):
    return {
        "opportunity_score": score,
        "confidence_pct": confidence,
        "component_coverage_pct": coverage,
        "expected_return_pct": upside,
        "components": {
            "fundamentals": 75,
            "technical": 72,
            "valuation": 70,
        },
    }


def test_buy_now_can_trigger():
    verdict = build_committee_verdict(row(75, 74, 80, 35))
    assert verdict["committee_verdict"] == "BUY_NOW"


def test_extreme_upside_is_not_buy_now():
    verdict = build_committee_verdict(row(78, 76, 80, 75))
    assert verdict["committee_verdict"] != "BUY_NOW"
    assert "unusually high" in verdict["primary_blocker"]
