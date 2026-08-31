"""Bounded UX-3B content, presentation, and retained-QA contracts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from engines.atlas_research_builder_v2 import _risk_interpretations
from engines.ask_atlas_engine import ask_atlas, customer_evidence_label
from engines.guidance_summary import build_guidance_summary
from tests.test_atlas_vnext_ux3b_research_ask import _report
from ui.research_vnext import (
    _canonical_financial_value,
    _customer_event_label,
    _clean_customer_prose,
    technical_availability,
)


ROOT = Path(__file__).resolve().parents[1]


def test_unpublished_technical_state_never_becomes_monitor_presentation():
    report = _report(status="DATA_UNAVAILABLE")
    report["technical_state"] = None
    report["sections"]["technical"]["data"] = {"rsi": 51.0}
    availability = technical_availability(report)
    assert availability["state"] is None
    assert availability["label"] == "Technical evidence available · State not published"
    source = (ROOT / "ui/research_vnext.py").read_text(encoding="utf-8")
    assert "No actionable technical state is currently published." in source
    assert 'technical_state in {"MONITOR", "WATCH"}' in source


def test_risk_interpretation_is_evidence_only():
    rendered = _risk_interpretations([{"factor": "Execution risk", "level": "Elevated"}])[0]["atlas_interpretation"]
    assert "recommends" not in rendered.lower()
    assert "smaller position" not in rendered.lower()
    assert "risk profile" in rendered.lower()


def test_event_direction_uses_date_without_mutating_it():
    assert _customer_event_label("Next scheduled earnings report", "2026-07-29", today=date(2026, 8, 31)) == "Latest scheduled/reported earnings report"
    assert _customer_event_label("Next scheduled earnings report", "2026-09-29", today=date(2026, 8, 31)) == "Next scheduled earnings report"
    assert _customer_event_label("Scheduled earnings report", "not-a-date", today=date(2026, 8, 31)) == "Scheduled earnings report"
    past = build_guidance_summary({"ticker": "MSFT", "next_earnings_date": "2020-07-29"})["next_catalyst"]
    assert past["date"] == "2020-07-29"
    assert past["event"] == "Latest scheduled/reported earnings report"


def test_cash_alias_is_consistent_and_preserves_zero_and_negative_values():
    assert _canonical_financial_value({"total_cash": 78_200_000_000}, {}, "cash", "total_cash") == 78_200_000_000
    assert _canonical_financial_value({"total_cash": 12}, {"cash": 0}, "cash", "total_cash") == 0
    assert _canonical_financial_value({"total_cash": 12}, {"cash": -3}, "cash", "total_cash") == -3


def test_customer_prose_repairs_known_deterministic_grammar_only():
    assert _clean_customer_prose("Atlas views revenue growth is 17.7% as supportive.") == "ATLAS views revenue growth of 17.7% as supportive."


def test_ask_missing_evidence_uses_customer_labels_not_raw_status_tokens():
    assert customer_evidence_label("guidance:DATA_UNAVAILABLE") == "Management guidance: data unavailable"
    result = ask_atlas("What is the ATLAS view?", _report(status="DATA_UNAVAILABLE"))
    assert "guidance:DATA_UNAVAILABLE" not in result["answer"]


def test_ask_retained_marker_preserves_sanitized_decision_and_context_digests():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"data-atlas-context-digest": grounding.get("context_digest", "")' in source
    assert '"data-atlas-decision-digest": grounding.get("canonical_decision_digest", "")' in source
    assert 'st.session_state["ask_ai_grounding"].update(' in source
    assert "_customer_evidence_label(item)" in source
    assert "guidance:DATA_UNAVAILABLE" not in source


def test_mobile_cleanup_is_targeted_not_a_global_page_gutter():
    research = (ROOT / "ui/research_vnext.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '[class*="st-key-vnext_ask_atlas"]' in research
    assert '[data-testid="stAlert"]' in research
    assert ".v74-topbar { display:none !important; }" in app
    assert '[class*="st-key-ask_suggestion"]' in app
    assert 'if selected_page == "Ask AI":' in app
    assert 'with st.expander("Market context", expanded=False):' in app
