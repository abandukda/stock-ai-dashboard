from engines.decision_intelligence_engine import evidence_pack, primary_risk, decision, movement_explanation, macro_interpretation


def test_missing_current_ratio_is_not_false_risk():
    row={"Ticker":"ABC","Current Ratio":0,"Forward PE":60,"Revenue Growth":20}
    risk=primary_risk(row)
    assert "current ratio is 0.00" not in risk.lower()
    assert "valuation" in risk.lower() or "forward earnings" in risk.lower()


def test_company_evidence_is_multi_factor():
    row={"Ticker":"ABC","Revenue Growth":22,"Operating Margin":28,"Free Cash Flow":1_000_000,"Expected Return":18,"RSI":57,"latest_news_headline":"Company raises full-year guidance"}
    evidence=evidence_pack(row,7)
    assert len(evidence)>=5
    assert any("Recent catalyst" in x for x in evidence)
    assert any("Revenue" in x for x in evidence)


def test_buy_now_can_exist_when_evidence_aligns():
    row={"Quality":88,"Opportunity":87,"Research Confidence":86,"Expected Return":22,"Technical Score":76,"Catalyst Score":70,"Atlas Fair Value":122,"Price":100,"Free Cash Flow":100,"Revenue Growth":18}
    assert decision(row)["label"] in {"HIGH CONVICTION BUY","BUY NOW"}


def test_movement_is_plain_language():
    row={"prior_rank":25,"dynamic_rank":5,"rank_change":20,"why_today":["Earnings estimates improved."]}
    output=movement_explanation(row)
    assert "#25" in output["label"] and "#5" in output["label"]


def test_macro_summary_explains_market_effect():
    result=macro_interpretation("CPI Inflation",2.5,2.8,2.9)
    assert "below consensus" in result["summary"]
    assert result["impact"] != "Neutral / unclear"
