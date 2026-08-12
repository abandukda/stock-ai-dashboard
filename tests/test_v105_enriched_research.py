from engines.research_enrichment_v105 import build_enriched_research_report, validate_enriched_report
from agents.research_completeness_agent_v105 import audit_research_completeness
from ui.research_report_enriched_v105 import render_v105_enriched_research

def sample():
    return {
        "ticker":"TEST","company":"Test Co","sector":"Technology",
        "committee_verdict":"BUY_NOW","opportunity_score":81,"confidence_pct":77,
        "position_size_range":"3–5%","investment_thesis":"A concise thesis.",
        "positive_drivers":["Strong growth"],"reasons_to_wait":["Valuation risk"],
        "financials":{"revenue_growth_pct":18,"gross_margin_pct":72,"free_cash_flow":1000000},
        "analysts":{"analyst_consensus":"Buy","analyst_target_mean":125,"analyst_target_high":145},
        "earnings":{"next_earnings_date":"2026-08-20","guidance":"Raised"},
        "news":[{"headline":"New contract","sentiment":"Positive"}],
        "political":{"political_score":65},
        "ownership":{"institutional_ownership_pct":78},
        "technical":{"rsi":58,"sma50":100},
    }

def test_enriched_contract():
    report=build_enriched_research_report(sample())
    assert validate_enriched_report(report)==[]
    assert report["financials"]["status"]=="available"
    assert report["analysts"]["data"]["average_target"]==125

def test_completeness_agent():
    audit=audit_research_completeness(sample())
    assert audit["version"]=="V105"
    # A headline without publisher/date and company association is not
    # accepted as verified company news merely to inflate completeness.
    assert audit["coverage_pct"]<100.0
    assert any(item["section"]=="news" and item["issue"]=="Section is unavailable" for item in audit["findings"])

def test_ui_export():
    assert callable(render_v105_enriched_research)
