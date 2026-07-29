
from engines.atlas_intelligence_engine import build_executive_intelligence


def test_intelligence_output_shape_is_stable():
    report = {
        "ticker": "TEST",
        "committee_verdict": "MONITOR",
        "opportunity_score": 60,
        "confidence_pct": 58,
        "sections": {
            "financials": {},
            "earnings": {},
            "analysts": {},
            "news": {"data": []},
            "technical": {"data": {}},
            "risk": {},
        },
        "trade_plan": {},
    }
    result = build_executive_intelligence(report)
    assert "executive_summary" in result
    assert "today_move" in result
    assert "why_atlas_supports_it" in result
