from engines.research_engine_v105 import (
    build_institutional_research,
    validate_research_contract,
)
from ui.research_report_v105 import render_v105_research_report


def candidate():
    return {
        "ticker": "TEST",
        "company": "Test Company",
        "sector": "Technology",
        "committee_verdict": "BUY_NOW",
        "opportunity_score": 82,
        "confidence_pct": 84,
        "current_price": 100,
        "validated_fair_value": 125,
        "expected_return_pct": 25,
        "position_size_range": "3–5%",
        "positive_drivers": [
            "Strong fundamental quality",
            "Positive technical confirmation",
        ],
        "reasons_to_wait": [
            "Valuation remains above the sector median."
        ],
        "primary_blocker": "Valuation remains above the sector median.",
        "investment_thesis": "Test investment thesis.",
        "components": {
            "fundamentals": 85,
            "valuation": 68,
            "technical": 82,
            "analyst": 75,
            "institutional": 70,
            "political": 62,
            "insider": 55,
            "risk": 72,
            "macro": 65,
        },
        "raw": {
            "eps_surprise_pct": 8,
            "revenue_surprise_pct": 5,
            "guidance": "Guidance raised.",
            "analyst_buy_count": 20,
            "analyst_hold_count": 4,
            "analyst_sell_count": 1,
            "analyst_target_high": 140,
            "analyst_target_low": 105,
        },
    }


def test_v105_research_contract():
    report = build_institutional_research(candidate())
    assert validate_research_contract(report) == []
    assert report["version"] == "V105"
    assert len(report["fair_value_cases"]) == 3


def test_v105_cases_total_100():
    report = build_institutional_research(candidate())
    total = sum(
        case["probability_pct"]
        for case in report["fair_value_cases"]
    )
    assert round(total, 1) == 100.0


def test_v105_ui_export_exists():
    assert callable(render_v105_research_report)
