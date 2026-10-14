
from engines.ask_atlas_engine import _compact_context, ask_atlas, canonical_ask_decision
from services.customer_research_view import build_customer_research_view
from tests.test_customer_research_v2 import report as certified_report


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


def test_ask_availability_and_authority_are_exact_customer_view_parity():
    source = certified_report()
    view = build_customer_research_view(source)
    resolved = canonical_ask_decision(source)

    assert resolved["authority_source"] == "CUSTOMER_RESEARCH_VIEW"
    assert resolved["state"] == view.surface["action"]
    assert resolved["production_decision"]["atlas_fair_value"] == view.surface["fair_value"]
    assert resolved["production_decision"]["opportunity"] == view.surface["opportunity"]
    assert resolved["production_decision"]["confidence"] == view.surface["confidence"]
    assert resolved["production_decision"]["evidence_availability"] == dict(
        view.surface["evidence_availability"]
    )


def test_ask_surface_has_readable_responsive_answer_contract():
    source = __import__("pathlib").Path("app.py").read_text(encoding="utf-8")
    ask = source[source.index("def render_chat_helper"):source.index("# =========================\n# MAIN APP")]
    assert '[data-testid="stMarkdownContainer"] blockquote' in ask
    assert "line-height:1.65" in ask
    assert "overflow-wrap:anywhere" in ask
    assert "margin-right:6.5rem" not in ask
