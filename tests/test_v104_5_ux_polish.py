
from utils.evidence_coverage_v1045 import calculate_evidence_coverage
from utils.validated_return_v1045 import calculate_validated_return
from ui.home_v104 import render_v104_home
from ui.research_report_v104 import render_candidate_card, render_full_research_report
from ui.market_briefing_v104 import render_v104_earnings_briefing

def sample():
    return {
        "ticker": "TEST",
        "current_price": 100,
        "validated_fair_value": 125,
        "investment_thesis": "Thesis",
        "components": {
            "fundamentals": 80,
            "valuation": 70,
            "technical": 75,
            "analyst": 65,
            "institutional": None,
            "political": 60,
            "insider": None,
            "risk": 72,
            "macro": 68,
        },
        "raw": {
            "latest_news_headline": "Catalyst",
            "guidance": "Raised",
        },
    }

def test_dynamic_coverage_is_not_fixed():
    result = calculate_evidence_coverage(sample())
    assert result["coverage_pct"] != 80.0
    assert result["available_count"] < result["total_count"]

def test_validated_return():
    result = calculate_validated_return(sample())
    assert result["status"] == "VALIDATED"
    assert result["return_pct"] == 25.0

def test_extreme_target_requires_validation():
    row = sample()
    row["validated_fair_value"] = 250
    result = calculate_validated_return(row)
    assert result["status"] == "OUTLIER"
    assert result["return_pct"] is None

def test_v1045_public_exports():
    assert callable(render_v104_home)
    assert callable(render_candidate_card)
    assert callable(render_full_research_report)
    assert callable(render_v104_earnings_briefing)
