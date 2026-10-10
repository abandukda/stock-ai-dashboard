
from engines.ask_atlas_engine import _compact_context, ask_atlas


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


def test_ask_uses_same_certified_customer_projection_as_research():
    report = sample_report()
    report.update({
        "candidate_digest": "candidate", "publication_digest": "publication", "source_sha": "source",
        "certified_customer_evaluation": {
            "ticker": "TEST", "customer_publication_allowed": True,
            "decision": {"action": "BUY_NOW", "opportunity": 67, "decision_confidence": 88},
            "fields": {
                "price": {"value": 10, "certification_status": "CERTIFIED", "source": "ARCHIVE", "as_of": "2026-10-08T20:00:00Z", "evidence_ids": ["price:1"]},
                "atlas_fair_value": {"value": 15, "certification_status": "CERTIFIED", "source": "ATLAS", "as_of": "2026-10-08T20:00:00Z", "evidence_ids": ["fv:1"]},
            },
            "digests": {"evaluation_snapshot_id": "snapshot"},
        },
        "publication_certification": {"publication_digest": "publication", "source_sha": "source"},
        "canonical_investment_evaluation": {"evidence_ids": ["decision:1"]},
        "intelligence": {"why_atlas_supports_it": ["Certified support."], "key_risks": ["Certified risk."]},
    })
    context = _compact_context(report)
    assert context["current_price"] == 10
    assert context["price_label"] == "Last Certified Close"
    assert context["evidence_as_of"] == "Oct 8, 2026"
    assert context["evidence_confidence"] == 88
    assert context["evidence_confidence_band"] == "High"
    assert context["atlas_fair_value"] == 15
