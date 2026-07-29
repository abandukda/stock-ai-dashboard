
from engines.ask_atlas_engine import ask_atlas


def sample_report():
    return {
        "ticker": "TEST",
        "company": "Test Company",
        "committee_verdict": "ACCUMULATE",
        "opportunity_score": 67,
        "confidence_pct": 63,
        "expected_return_pct": 18,
        "generated_at": "2026-07-28T00:00:00Z",
        "sections": {
            "financials": {
                "status": "available",
                "interpretation": "Financial quality is constructive.",
            },
            "earnings": {
                "status": "partial",
                "interpretation": "Earnings evidence is mixed.",
            },
            "analysts": {"status": "available"},
            "news": {"status": "unavailable", "data": []},
            "political": {"status": "unavailable"},
            "ownership": {"status": "partial"},
            "technical": {
                "status": "available",
                "data": {"volume_ratio": 1.5},
                "interpretation": "Momentum is constructive.",
            },
            "risk": {
                "status": "available",
                "interpretation": "Volatility requires measured sizing.",
            },
        },
        "quote": {"change_pct": -2.5},
        "bull_case": ["Cash flow is positive."],
        "bear_case": ["Valuation requires execution."],
        "trade_plan": {"actionable": True},
    }


def test_ask_atlas_answers_rating_question():
    result = ask_atlas("Why is this rated Accumulate?", sample_report())
    assert result["answer"]
    assert result["mode"] in {
        "deterministic", "deterministic_fallback", "llm_grounded"
    }


def test_ask_atlas_discloses_data_sections():
    result = ask_atlas("What are the risks?", sample_report())
    assert "financials" in result["sources_used"]
    assert "news" not in result["sources_used"]
