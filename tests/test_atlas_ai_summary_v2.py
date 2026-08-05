from agents.ai_content_integrity_v3 import audit_summary_collection
from engines.atlas_intelligence_engine import build_executive_intelligence


def _report(ticker, company, revenue, eps, expected_return, rvol, risk):
    return {
        "ticker": ticker,
        "company": company,
        "sector": "Technology",
        "committee_verdict": "ACCUMULATE",
        "opportunity_score": 70,
        "confidence_pct": 74,
        "expected_return_pct": expected_return,
        "current_price": 100,
        "validated_fair_value": 100 * (1 + expected_return / 100),
        "bull_case": [],
        "bear_case": [risk],
        "sections": {
            "financials": {
                "data": {
                    "revenue_growth_pct": revenue,
                    "eps_growth_pct": eps,
                    "gross_margin_pct": 65,
                    "forward_pe": 25,
                }
            },
            "technical": {
                "data": {
                    "relative_volume": rvol,
                    "rsi": 55,
                    "sma50": 95,
                    "sma200": 85,
                    "price": 100,
                }
            },
            "earnings": {"data": {"eps_surprise_pct": 5}},
            "analysts": {"data": {"average_target": 125, "buy_count": 20, "hold_count": 5}},
            "news": {"data": [{"headline": f"{company} launches a company-specific product", "sentiment": "positive"}]},
            "risk": {"data": [{"factor": "Execution", "level": "Medium", "detail": risk}]},
        },
    }


def test_executive_summary_is_stock_specific_and_numeric():
    output = build_executive_intelligence(
        _report("AAA", "Alpha Systems", 22, 28, 18, 1.4, "Alpha faces product execution risk.")
    )
    summary = output["executive_summary"]
    assert "Alpha Systems (AAA)" in summary
    assert "22.0%" in " ".join(output["why_atlas_supports_it"])
    assert output["narrative_quality"]["numeric_fact_count"] >= 3
    assert output["narrative_quality"]["stock_specific"] is True


def test_different_stocks_do_not_receive_duplicate_summaries():
    alpha = build_executive_intelligence(
        _report("AAA", "Alpha Systems", 22, 28, 18, 1.4, "Alpha faces product execution risk.")
    )
    beta = build_executive_intelligence(
        _report("BBB", "Beta Cloud", 8, 4, 9, 0.7, "Beta faces margin compression risk.")
    )
    report = audit_summary_collection(
        [
            {"ticker": "AAA", "company": "Alpha Systems", "ai_summary": alpha["executive_summary"]},
            {"ticker": "BBB", "company": "Beta Cloud", "ai_summary": beta["executive_summary"]},
        ],
        similarity_threshold=82,
    )
    assert report["duplicate_pairs"] == []


def test_missing_evidence_is_stock_named_not_generic():
    report = {
        "ticker": "XYZ",
        "company": "XYZ Holdings",
        "committee_verdict": "MONITOR",
        "opportunity_score": 50,
        "confidence_pct": 55,
        "sections": {},
        "bull_case": [],
        "bear_case": [],
    }
    output = build_executive_intelligence(report)
    assert "XYZ" in output["executive_summary"]
    assert "XYZ" in output["key_risks"][0]
