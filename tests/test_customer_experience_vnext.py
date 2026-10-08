from pathlib import Path

from services.customer_ai_summary import build_earnings_summary, build_research_summary
from ui.watchlist_vnext import _certified_fields


def _research_report():
    return {
        "ticker": "NVDA",
        "certified_customer_evaluation": {
            "customer_publication_allowed": True,
            "decision": {"action": "BUY_NOW", "opportunity": 85.96, "decision_confidence": 87.46},
        },
        "research_context": {"production_decision": {"recommendation": "BUY_NOW"}},
        "intelligence": {"why_atlas_supports_it": ["Certified growth evidence"], "key_risks": ["Execution risk"]},
        "technical_summary": {"summary": "Technical evidence is constructive."},
        "sections": {"financials": {"interpretation": "Certified financial evidence is supportive."}},
        "guidance_summary": {
            "action_now": {"current_action": "Use the certified entry range."},
            "thesis_change_conditions": {"strengthen": ["Execution improves"], "invalidate": ["Thesis breaks"]},
        },
        "evidence_ids": ["b", "a"],
    }


def test_research_summary_uses_certified_action_and_canonical_evidence():
    summary = build_research_summary(_research_report())
    assert summary["status"] == "AVAILABLE"
    assert summary["sections"]["Investment view"] == "The certified ATLAS Action is BUY NOW."
    assert summary["evidence_ids"] == ["a", "b"]
    assert summary["explanation"] == "AI_GENERATED_EXPLANATION"


def test_research_summary_fails_closed_for_withheld_rating():
    report = _research_report()
    report["certified_customer_evaluation"]["customer_publication_allowed"] = False
    assert build_research_summary(report) == {
        "status": "UNAVAILABLE", "reason": "RATING_NOT_PUBLISHED", "sections": {}, "evidence_ids": []
    }


def test_incomplete_certified_evaluation_cannot_fall_back_to_parallel_action():
    report = _research_report()
    report["certified_customer_evaluation"]["decision"].pop("action")
    assert build_research_summary(report)["reason"] == "CERTIFIED_ACTION_UNAVAILABLE"


def test_earnings_summary_is_contextual_non_scoring_and_traceable():
    story = {"transcript_intelligence": {"semantic_status": "AVAILABLE", "provider": "EarningsCall",
              "evidence_ids": ["call:1"], "data": {"management_themes": [{"text": "Demand remained strong"}],
              "verified_guidance_statements": [{"text": "Guidance was maintained"}]}}}
    result = build_earnings_summary(story)
    assert result["classification"] == "CONTEXTUAL_NON_SCORING"
    assert result["evidence_ids"] == ["call:1"]
    assert "Demand remained strong" in result["sections"]["Management themes"]


def test_unavailable_transcript_never_generates_summary():
    result = build_earnings_summary({"transcript_intelligence": {"semantic_status": "DATA_UNAVAILABLE"}})
    assert result["status"] == "UNAVAILABLE"
    assert result["message"] == "Transcript analysis unavailable"


def test_customer_navigation_and_internal_report_card_boundaries_are_explicit():
    source = Path("app.py").read_text(encoding="utf-8")
    contract = Path("services/customer_navigation_contract.py").read_text(encoding="utf-8")
    assert 'CUSTOMER_ROUTES = ("Home", "Research", "Earnings", "Watchlist", "Ask ATLAS")' in contract
    assert "customer_pages = list(CUSTOMER_ROUTES)" in source
    assert "if not is_viewer():\n        pages.extend(internal_pages)" in source
    assert "ATLAS_INTERNAL_REPORT_CARD_UI_ENABLED" in source


def test_screenshot_identity_is_surface_specific():
    source = Path("agents/atlas_visual_crawler_v1.py").read_text(encoding="utf-8")
    assert 'f"{page_name}|{interaction}|{state}|{ticker}|{viewport}|{state_digest}"' in source


def test_visual_crawler_resolves_customer_navigation_labels():
    source = Path("agents/atlas_visual_crawler_v1.py").read_text(encoding="utf-8")
    assert '"Research Any Ticker": "Research"' in source
    assert '"Earnings Intelligence": "Earnings"' in source
    assert '"Watchlist Intelligence": "Watchlist"' in source
    assert '"Ask AI": "Ask ATLAS"' in source
    assert 'name=customer_label, exact=True' in source


def test_supplementary_qa_is_non_blocking_but_preserved_as_artifact():
    source = Path(".github/workflows/atlas-runtime-qa-v3.yml").read_text(encoding="utf-8")
    block = source.split("- name: Run Atlas Runtime QA supplementary certification", 1)[1]
    assert "continue-on-error: true" in block
    assert "supplementary defects remain visible in the uploaded artifact" in source


def test_watchlist_and_intraday_context_cannot_change_action():
    watch = Path("ui/watchlist_vnext.py").read_text(encoding="utf-8")
    home = Path("ui/home_guidance_vnext.py").read_text(encoding="utf-8")
    assert "Market-state context cannot change the certified Action" in watch
    assert 'data-atlas-non-scoring="true"' in watch
    assert 'data-atlas-non-scoring="true"' in home


def test_watchlist_uses_only_customer_publishable_certified_authority():
    row = {"certified_customer_evaluation": {"customer_publication_allowed": True,
           "ticker": "NVDA",
           "decision": {"action": "BUY_NOW", "opportunity": 85.96, "decision_confidence": 87.46},
           "fields": {"atlas_fair_value": {"value": 123.45, "certification_status": "CERTIFIED"}},
           "digests": {"evaluation_snapshot_id": "snapshot-1"}}}
    assert _certified_fields(row) == ("BUY_NOW", 123.45)
    row["certified_customer_evaluation"]["customer_publication_allowed"] = False
    assert _certified_fields(row) == ("RATING_NOT_PUBLISHED", None)


def test_customer_report_card_remains_internal_and_public_claims_off():
    dashboard = Path("services/report_card_dashboard.py").read_text(encoding="utf-8")
    ui = Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    assert '"customer_visible": False' in dashboard
    assert '"public_performance_claims_allowed": False' in dashboard
    assert "INTERNAL ONLY" in ui


def test_ask_response_lifecycle_is_unique_for_each_question():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'data-atlas-submission-id' in source
    assert 'data-atlas-question-digest' in source
    assert 'st.markdown(f"#### Asked:' in source
