
from engines.daily_opportunities_engine import (
    build_today_opportunities,
    build_volume_momentum,
)


ROWS = [
    {
        "ticker": "BUY",
        "committee_verdict": "BUY_NOW",
        "confidence_pct": 75,
        "opportunity_score": 72,
        "expected_return_pct": 20,
        "volume_ratio": 1.4,
        "change_pct": 2,
        "positive_drivers": ["Strong support"],
        "reasons_to_wait": ["Normal risk"],
    },
    {
        "ticker": "ACC",
        "committee_verdict": "ACCUMULATE",
        "confidence_pct": 70,
        "opportunity_score": 75,
        "expected_return_pct": 25,
        "volume_ratio": 2.2,
        "change_pct": -4,
    },
    {
        "ticker": "AVD",
        "committee_verdict": "AVOID",
        "confidence_pct": 90,
        "opportunity_score": 95,
        "volume_ratio": 5,
        "change_pct": 8,
    },
]


def test_today_opportunities_prioritize_actionable_verdicts():
    results = build_today_opportunities(ROWS)
    assert [item["ticker"] for item in results] == ["BUY", "ACC"]


def test_volume_engine_labels_distribution():
    results = build_volume_momentum(ROWS)
    acc = next(item for item in results if item["ticker"] == "ACC")
    assert acc["volume_signal"] == "Potential distribution"


def test_volume_engine_does_not_change_committee_verdict():
    results = build_volume_momentum(ROWS)
    avoid = next(item for item in results if item["ticker"] == "AVD")
    assert avoid["committee_verdict"] == "AVOID"
