from engines.decision_transparency_engine import (
    build_decision_scorecard,
    build_transparency_report,
    validate_transparency_contract,
)


def buy_row():
    return {
        "Ticker": "TEST",
        "Company": "Test Company",
        "Current Price": 100,
        "Atlas Fair Value": 125,
        "Quality": 80,
        "Financial Health": 78,
        "Valuation Score": 72,
        "Technical Score": 75,
        "earnings_summary": "Beat estimates",
        "latest_news_headline": "Raised guidance",
        "Risk Status": "Pass",
        "v89_decision": {
            "action_code": "BUY_NOW",
            "conviction": 88,
            "research_completeness_pct": 90,
        },
    }


def test_v97_explains_buy_now():
    scorecard = build_decision_scorecard(buy_row())
    assert scorecard["action_code"] == "BUY_NOW"
    assert scorecard["required_pillars_passed"] == scorecard["required_pillars_total"]
    assert scorecard["is_consistent"] is True


def test_v97_flags_inconsistent_buy_now():
    row = buy_row()
    row["Technical Score"] = 25
    scorecard = build_decision_scorecard(row)
    assert scorecard["is_consistent"] is False
    assert "technical" in [
        item["key"] for item in scorecard["failed_pillars"]
    ]


def test_v97_monitor_provides_trigger():
    row = buy_row()
    row["v89_decision"]["action_code"] = "MONITOR"
    row["Resistance"] = 108
    scorecard = build_decision_scorecard(row)
    assert scorecard["trigger"]["price"] == 108
    assert "Close above" in scorecard["trigger"]["condition"]


def test_v97_is_read_only():
    report = build_transparency_report([buy_row()])
    assert validate_transparency_contract(report) == []
    assert report["read_only"] is True
