from __future__ import annotations

import ast
from pathlib import Path

from engines.ask_atlas_engine import format_customer_financial_numbers
from engines.research_context import build_production_decision
from engines.research_engine import begin_research_entry
from ui.home_v104 import _canonical_home_row
from ui.research_vnext import build_research_decision_view


ROOT = Path(__file__).resolve().parents[1]


def _context(*, opportunity=None, confidence=97, recommendation=None, technical_state=None):
    families = {}
    if technical_state is not None:
        families["technicals"] = {
            "semantic_status": "AVAILABLE",
            "data": {"technical_state": technical_state},
        }
    return {
        "context_version": "RESEARCH_CONTEXT_V1",
        "production_decision": {
            "semantic_status": "AVAILABLE",
            "recommendation": recommendation,
            "opportunity": opportunity,
            "confidence": confidence,
        },
        "evidence_families": families,
    }


def test_crc_opportunity_unavailable_does_not_consume_confidence():
    report = {
        "ticker": "CRC", "committee_verdict": "BUY_NOW",
        "opportunity_score": 97, "confidence_pct": None,
        "research_completeness_pct": 45,
        "research_context": _context(),
    }
    view = build_research_decision_view(report)
    assert view["header"].opportunity is None
    assert view["header"].confidence == 97
    assert view["header"].recommendation is None
    assert view["monitor_or_incomplete"] is True


def test_actionable_opportunity_and_confidence_remain_distinct():
    report = {
        "ticker": "NVDA", "research_completeness_pct": 95,
        "research_context": _context(
            opportunity=84, confidence=78, recommendation="BUY_NOW",
            technical_state="NEAR_BREAKOUT",
        ),
    }
    view = build_research_decision_view(report)
    assert view["header"].opportunity == 84
    assert view["header"].confidence == 78
    assert view["header"].recommendation == "BUY_NOW"
    assert view["technical_badge"].canonical_value == "NEAR_BREAKOUT"


def test_generic_score_is_not_canonical_opportunity():
    decision = build_production_decision({"ticker": "CRC", "score": 97, "confidence": 97})
    assert decision["opportunity"] is None
    assert decision["confidence"] == 97


def test_home_uses_same_immutable_decision_authority_as_research():
    row = {
        "ticker": "BZ", "committee_verdict": "BUY_NOW",
        "opportunity_score": 96, "confidence_pct": None,
        "raw": {"ticker": "BZ", "confidence": 96, "score": 96},
    }
    presented = _canonical_home_row(row)
    assert presented["committee_verdict"] == "MONITOR"
    assert presented["opportunity_score"] is None
    assert presented["confidence_pct"] == 96
    assert presented["buy_now"] is False


def test_supporting_navigation_creates_fresh_exact_ticker_lifecycle():
    state = {"authenticated": True, "role": "viewer", "active_research_ticker": "NVDA"}
    first = begin_research_entry(state, "EXEL", source="EARNINGS_INTELLIGENCE")
    second = begin_research_entry(state, "GS", source="POLITICAL_INTELLIGENCE")
    assert first["ticker"] == "EXEL"
    assert second["ticker"] == "GS"
    assert first["request_id"] != second["request_id"]
    assert state["v79_pending_page"] == "Research Any Ticker"
    assert state["v79_pending_research_ticker"] == "GS"
    assert state["active_research_ticker"] == "GS"
    assert state["authenticated"] is True


def test_active_earnings_and_political_paths_use_canonical_entry_helper():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert 'begin_research_entry(st.session_state, ticker, source="SUPPORTING_PAGE_RESEARCH")' in source
    assert 'source="POLITICAL_INTELLIGENCE"' in source
    assert "research_navigation_state(selected)" not in source


def test_ask_customer_number_formatting_is_presentation_only():
    assert format_customer_financial_numbers("Revenue was $38,860,000,000") == "Revenue was $38.86B"
    assert format_customer_financial_numbers("Shares were 22,443,000,000") == "Shares were 22.44B"
    assert format_customer_financial_numbers("EPS was -2 and cash was 0") == "EPS was -2 and cash was 0"


def test_crawler_requires_completed_requested_vnext_report_and_fresh_tabs():
    source = (ROOT / "agents/atlas_visual_crawler_v1.py").read_text(encoding="utf-8")
    assert "async def _completed_research" in source
    assert 'data-atlas-status=\"complete\"' in source
    assert 'architecture["version"] == "ATLAS_RESEARCH_VNEXT_UX2"' in source
    assert "completion.get(\"complete\")" in source
    assert "refreshed_tab = await self._fresh_visible_tab(page, name)" in source
    assert "section-evidence" in source
    assert '"NEEDS_REVIEW"' in source


def test_political_mobile_cards_preserve_all_evidence_fields():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    for label in ("Politician", "Trade Date", "Disclosure Date", "Amount", "Provider"):
        assert label in source
    assert "atlas-political-mobile-card" in source
