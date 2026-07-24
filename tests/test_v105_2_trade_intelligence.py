from engines.trade_plan_v1052 import build_trade_plan, validate_trade_plan, classify_horizon
from engines.individualized_scoring_v1052 import calculate_individualized_scores
from engines.evidence_synthesis_v1052 import build_ai_guidance
from agents.trade_plan_audit_v1052 import audit_trade_plan
from ui.live_trade_plan_v1052 import render_trade_plan_panel

def row(ticker="AAA"):
    return {
        "ticker":ticker,
        "validated_fair_value":125,
        "analyst_target_mean":118,
        "atr":3,
        "support":98,
        "resistance":110,
        "revenue_growth_pct":15,
        "components":{
            "fundamentals":82,"valuation":70,"technical":74,"analyst":66,
            "news":62,"political":55,"institutional":68,"earnings":76,
            "macro":60,"risk":72,
        },
        "component_coverage_pct":84,
        "freshness_score":90,
    }

def quote():
    return {"price":102,"price_as_of":"2026-07-23T10:00:00-04:00","quote_source":"TEST","market_status":"OPEN"}

def test_trade_plan_contract():
    plan=build_trade_plan(row(),quote())
    assert plan["actionable"] is True
    assert validate_trade_plan(plan)==[]
    assert plan["stop_loss"]<plan["entry_low"]<plan["target_1"]

def test_scores_vary():
    a=calculate_individualized_scores(row("AAA"))
    b=calculate_individualized_scores(row("BBB"))
    assert a["opportunity_score"] != b["opportunity_score"]
    assert a["confidence_pct"] != b["confidence_pct"]

def test_horizon():
    result=classify_horizon(row())
    assert result["primary"] in {"Swing","Position","Long-Term"}

def test_guidance():
    report={"committee_verdict":"BUY_NOW","financials":{"status":"available"},"analysts":{"status":"available"}}
    plan=build_trade_plan(row(),quote())
    scores=calculate_individualized_scores(row())
    result=build_ai_guidance(report,plan,scores)
    assert "opportunity score" in result["summary"]

def test_audit_and_ui_exports():
    plan=build_trade_plan(row(),quote())
    assert audit_trade_plan(plan)["version"]=="V105.2"
    assert callable(render_trade_plan_panel)
