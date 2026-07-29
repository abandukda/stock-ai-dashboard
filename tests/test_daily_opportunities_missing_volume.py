
from engines.daily_opportunities_engine import build_volume_momentum


def test_missing_volume_is_not_fabricated():
    results = build_volume_momentum(
        [
            {
                "ticker": "TEST",
                "committee_verdict": "MONITOR",
                "opportunity_score": 60,
            }
        ]
    )
    assert results == []
