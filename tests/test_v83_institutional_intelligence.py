from engines.institutional_intelligence_engine import (
    company_specific_risks,
    evidence_scorecard,
    home_guidance,
    institutional_decision,
    institutional_evidence,
    market_calendar_intelligence,
)


def quality_row():
    return {
        "Ticker":"MSFT","Company":"Microsoft Corporation","Sector":"Technology","Industry":"Software",
        "Quality":90,"Financial Health":88,"Valuation Score":78,"Technical Score":76,"Confidence":82,
        "News Score":75,"Smart Money Score":70,"Macro Score":65,"Expected Return":18,
        "Revenue Growth":16,"Earnings Growth":19,"Operating Margin":42,"Free Cash Flow":40000000000,
        "Forward PE":32,"RSI":58,"Analyst Target":560,"analyst_target_high":620,"analyst_target_low":480,
        "Analyst Count":38,"latest_news_headline":"Microsoft expands enterprise AI capacity",
        "guidance_summary":"Management maintained double-digit cloud growth guidance.",
        "political_support_summary":"Federal AI infrastructure spending supports enterprise demand.",
    }


def test_scorecard_and_decision_are_auditable():
    row=quality_row(); card=evidence_scorecard(row); decision=institutional_decision(row)
    assert card["Evidence Score"] > 70
    assert decision["label"] in {"HIGH CONVICTION BUY","BUY NOW","BUY ON WEAKNESS"}
    assert decision["scorecard"]["Business"] == 90


def test_evidence_is_multifactor_and_company_specific():
    evidence=institutional_evidence(quality_row(),8)
    joined=" ".join(evidence).lower()
    assert len(evidence) >= 5
    assert "wall street" in joined or "target range" in joined
    assert "catalyst" in joined
    assert "guidance" in joined


def test_missing_current_ratio_does_not_create_false_zero_risk():
    row=quality_row(); row["Current Ratio"]=0
    risks=company_specific_risks(row,4)
    assert all("0.00" not in risk for risk in risks)
    assert len(risks) >= 1


def test_home_guidance_explains_movement():
    row=quality_row(); row.update({"prior_rank":20,"dynamic_rank":4})
    guide=home_guidance(row)
    assert "#20" in guide["movement"] and "#4" in guide["movement"]
    assert guide["why_today"]
    assert guide["primary_risk"]


def test_calendar_adds_plain_language_impact():
    result=market_calendar_intelligence("Initial Jobless Claims",215,218,217)
    assert result["confidence"] == "High"
    assert result["impact_score"] >= 4
    assert "consensus" in result["plain_language"].lower()
    assert result["supports"]
