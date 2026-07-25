
from engines.atlas_research_builder_v2 import (
    build_atlas_research_v2,
    validate_atlas_research_v2,
)
from agents.research_audit_v2 import audit_research_row
from ui.research_report_v2 import render_atlas_research_v2
from ui.research_report_v104 import (
    render_candidate_card,
    render_full_research_report,
)
from ui.home_v104 import render_v104_home


def sample_row():
    return {
        "ticker": "TEST",
        "company": "Test Company",
        "sector": "Technology",
        "committee_verdict": "BUY_NOW",
        "validated_fair_value": 130,
        "current_price": 100,
        "position_size_range": "3–5%",
        "investment_thesis": "Test thesis.",
        "positive_drivers": ["Strong growth"],
        "reasons_to_wait": ["Premium valuation"],
        "revenue_growth_pct": 20,
        "eps_growth_pct": 25,
        "gross_margin_pct": 70,
        "operating_margin_pct": 30,
        "free_cash_flow": 1000000,
        "forward_pe": 28,
        "analyst_target_mean": 122,
        "analyst_buy_count": 15,
        "analyst_hold_count": 3,
        "analyst_sell_count": 1,
        "eps_surprise_pct": 8,
        "revenue_surprise_pct": 5,
        "guidance": "Raised",
        "transcript_summary": "Demand remains strong.",
        "news": [
            {
                "headline": "New contract",
                "sentiment": "Positive",
                "impact": 80,
            }
        ],
        "political": {
            "political_score": 60,
            "political_buyers": 2,
            "political_sellers": 0,
            "transactions": [
                {
                    "politician": "Sample",
                    "transaction": "Purchase",
                }
            ],
        },
        "ownership": {
            "institutional_ownership_pct": 75,
            "major_holders": [{"holder": "Fund A"}],
        },
        "technical": {
            "atr": 3,
            "support": 96,
            "resistance": 112,
            "sma50": 98,
            "sma200": 85,
            "rsi": 58,
            "volume_confirmation": "Positive",
        },
        "components": {
            "fundamentals": 85,
            "valuation": 70,
            "technical": 75,
            "analyst": 78,
            "news": 72,
            "political": 60,
            "institutional": 75,
            "earnings": 82,
            "macro": 65,
            "risk": 72,
        },
        "component_coverage_pct": 90,
        "freshness_score": 90,
    }


def test_v2_contract():
    report = build_atlas_research_v2(sample_row())
    assert validate_atlas_research_v2(report) == []
    assert report["ticker"] == "TEST"
    assert report["opportunity_score"] != report["confidence_pct"]
    assert report["sections"]["financials"]["status"] == "available"


def test_v2_trade_plan():
    report = build_atlas_research_v2(sample_row())
    assert report["trade_plan"]["actionable"] is True
    assert report["trade_plan"]["stop_loss"] < report["trade_plan"]["entry_low"]
    assert report["trade_plan"]["target_1"] > report["trade_plan"]["entry_high"]


def test_v2_audit():
    result = audit_research_row(sample_row())
    assert result["version"] == "V2.0-PHASE1"


def test_v2_exports():
    for function in (
        render_atlas_research_v2,
        render_candidate_card,
        render_full_research_report,
        render_v104_home,
    ):
        assert callable(function)
