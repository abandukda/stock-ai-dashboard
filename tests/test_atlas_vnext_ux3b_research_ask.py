"""UX-3B Research decision-story and Ask authority contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from engines.ask_atlas_engine import ask_atlas, canonical_ask_decision
from agents.runtime_qa_architecture import protected_decision_digest
from tests.test_atlas_vnext_ux2_research import report_fixture
from ui.research_vnext import (
    RESEARCH_VNEXT_SECTIONS, build_investment_brief,
    build_research_decision_view, risk_evidence_availability,
    technical_availability,
)


ROOT = Path(__file__).resolve().parents[1]


def _report(state: str = "BUY_NOW", status: str = "AVAILABLE") -> dict:
    report = report_fixture()
    report["research_context"]["production_decision"] = {
        "semantic_status": status,
        "recommendation": state if status == "AVAILABLE" else None,
        "opportunity": 84.0 if status == "AVAILABLE" else None,
        "confidence": 78.0 if status == "AVAILABLE" else None,
        "atlas_fair_value": 120.0 if status == "AVAILABLE" else None,
        "decision_expected_return": 20.0 if status == "AVAILABLE" else None,
        "stop": 94.0 if status == "AVAILABLE" else None,
    }
    return report


def test_ask_decision_uses_only_research_context_authority():
    report = _report("BUY_NOW")
    report["committee_verdict"] = "MONITOR"
    resolved = canonical_ask_decision(report)
    assert resolved["state"] == "BUY_NOW"
    answer = ask_atlas("Is this actionable now?", report)
    assert answer["canonical_decision_state"] == "BUY_NOW"
    assert "BUY NOW" in answer["answer"]
    assert resolved["digest"] == answer["canonical_decision_digest"]
    assert resolved["digest"] == protected_decision_digest(report["research_context"]["production_decision"])


def test_missing_production_decision_is_data_unavailable_not_monitor():
    report = _report(status="DATA_UNAVAILABLE")
    report["committee_verdict"] = "MONITOR"
    result = ask_atlas("What should I do?", report)
    assert result["canonical_decision_state"] == "DATA_UNAVAILABLE"
    assert "DATA_UNAVAILABLE" in result["answer"]
    assert "No actionable recommendation" in result["answer"]


def test_technical_evidence_and_state_are_separate():
    report = _report()
    report["technical_state"] = None
    report["sections"]["technical"]["data"] = {"rsi": 51.0}
    result = technical_availability(report)
    assert result["evidence_status"] == "AVAILABLE"
    assert result["state"] is None
    assert result["label"] == "Technical evidence available · State not published"


def test_risk_availability_preserves_zero_and_negative_evidence():
    report = _report()
    report["sections"]["financials"]["data"] = {"revenue_growth_pct": 0, "margin_change_pct": -2.5}
    statuses = risk_evidence_availability(report)
    assert statuses["Financial"] == "AVAILABLE"
    assert statuses["Technical"] == "AVAILABLE"


def test_decision_story_and_brief_do_not_mutate_canonical_values():
    report = _report()
    before = deepcopy(report)
    view = build_research_decision_view(report)
    brief = build_investment_brief(report)
    assert view["header"].recommendation == "BUY_NOW"
    assert 1 <= len(brief.split()) <= 100
    assert report == before


def test_research_keeps_exact_five_sections_and_ux3b_story_contracts():
    source = (ROOT / "ui/research_vnext.py").read_text(encoding="utf-8")
    assert len(RESEARCH_VNEXT_SECTIONS) == 5
    assert "60-Second Investment Brief" in source
    assert "Why ATLAS Likes It" in source
    assert "What Stops ATLAS" in source
    assert "What Changes the Thesis" in source
    assert "What I’m Watching Next" in source
    assert "Risk Evidence Availability" in source
    assert "Ask Atlas AI" not in RESEARCH_VNEXT_SECTIONS


def test_active_ask_path_cannot_overwrite_canonical_decision_aliases():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    forbidden = (
        '"committee_verdict": matched.get',
        '"opportunity_score": matched.get',
        '"confidence_pct": matched.get',
    )
    assert not any(item in source for item in forbidden)
    assert 'canonical_row["ticker"] = ticker' in source
    assert "Supporting evidence" in source
    assert "Missing evidence & limitations" in source


def test_crawler_retains_five_sections_and_adds_decision_story_contract():
    source = (ROOT / "agents/atlas_visual_crawler_v1.py").read_text(encoding="utf-8")
    assert "decision_story" in source
    assert "research-ux3b-block" in source
    assert "ATLAS_RESEARCH_VNEXT_UX2" in source
