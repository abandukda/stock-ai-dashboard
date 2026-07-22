
from utils.evidence_coverage_v1046 import calculate_evidence_coverage
from utils.validated_return_v1046 import calculate_validated_return
from ui.research_report_v105 import render_v105_research_report
from ui.research_report_v104 import render_candidate_card, render_full_research_report
from ui.home_v104 import render_v104_home
from ui.market_briefing_v104 import render_v104_earnings_briefing, _first, _DATE_KEYS

def sample():
    return {
        "ticker":"TEST","current_price":100,"validated_fair_value":125,"investment_thesis":"Thesis",
        "components":{"fundamentals":80,"valuation":70,"technical":75,"analyst":65,"institutional":None,"political":60,"insider":None,"risk":72,"macro":68},
        "raw":{"latest_news_headline":"Catalyst","Next Earnings":"2026-08-01"},
    }

def test_dynamic_coverage():
    result=calculate_evidence_coverage(sample())
    assert result["coverage_pct"] != 80.0

def test_validated_return():
    assert calculate_validated_return(sample())["return_pct"] == 25.0

def test_nested_earnings_date():
    assert _first(sample(),_DATE_KEYS) == "2026-08-01"

def test_exports():
    for fn in (render_v105_research_report,render_candidate_card,render_full_research_report,render_v104_home,render_v104_earnings_briefing):
        assert callable(fn)
