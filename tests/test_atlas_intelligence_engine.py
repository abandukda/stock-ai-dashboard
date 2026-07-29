
from engines.atlas_intelligence_engine import (
    build_executive_intelligence,
    build_today_move,
)


def report():
    return {
        "ticker": "TEST",
        "committee_verdict": "ACCUMULATE",
        "opportunity_score": 68,
        "confidence_pct": 64,
        "expected_return_pct": 22,
        "quote": {"change_pct": -4.5},
        "bull_case": ["Revenue growth remains constructive."],
        "bear_case": ["Valuation still requires execution."],
        "sections": {
            "financials": {"interpretation": "Revenue and cash flow are supportive."},
            "earnings": {"interpretation": "The company beat earnings expectations."},
            "analysts": {"interpretation": "Wall Street remains constructive."},
            "news": {
                "data": [
                    {
                        "headline": "Analyst raises price target",
                        "sentiment": "positive",
                    }
                ],
                "interpretation": "News flow is supportive.",
            },
            "technical": {
                "data": {"volume_ratio": 2.1},
                "interpretation": "Technical momentum is mixed.",
            },
            "risk": {"interpretation": "Position size should reflect volatility."},
        },
        "trade_plan": {"actionable": True},
    }


def test_today_move_separates_facts_from_inference():
    result = build_today_move(report())
    assert result["verified_facts"]
    assert result["atlas_inferences"]
    assert result["explanation_confidence_pct"] >= 70


def test_executive_intelligence_has_triggers():
    result = build_executive_intelligence(report())
    assert "Accumulate" in result["executive_summary"]
    assert result["upgrade_triggers"]
    assert result["downgrade_triggers"]
