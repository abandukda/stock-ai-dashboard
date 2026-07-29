from engines.morning_brief_engine import build_morning_brief


def test_buy_now_and_accumulate_are_top_opportunities():
    rows = [
        {
            "ticker": "BUY",
            "committee_verdict": "BUY_NOW",
            "confidence_pct": 75,
            "opportunity_score": 72,
            "sector": "Technology",
        },
        {
            "ticker": "ACC",
            "committee_verdict": "ACCUMULATE",
            "confidence_pct": 70,
            "opportunity_score": 75,
            "sector": "Healthcare",
        },
        {
            "ticker": "AVD",
            "committee_verdict": "AVOID",
            "confidence_pct": 90,
            "opportunity_score": 95,
            "sector": "Technology",
        },
    ]

    result = build_morning_brief(rows)
    assert [
        row["ticker"]
        for row in result["top_opportunities"]
    ] == ["BUY", "ACC"]
    assert result["counts"]["avoid"] == 1


def test_empty_universe_is_supported():
    result = build_morning_brief([])
    assert result["top_opportunities"] == []
    assert result["market_bias"] == "Selective"
