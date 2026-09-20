from pathlib import Path

from services.vnext_presentation_contract import (
    CUSTOMER_EVIDENCE_STATES,
    HOME_CUSTOMER_HIERARCHY,
    HOME_INDICATOR_CLASSIFICATION,
    PRESENTATION_TRUST_TIERS,
    RESEARCH_CUSTOMER_HIERARCHY,
    validate_home_indicator_slots,
    validate_surface_hierarchy,
)
from ui.home_guidance_vnext import _customer_evidence_state


ROOT = Path(__file__).resolve().parents[1]


def test_home_action_first_hierarchy_is_enforced():
    result = validate_surface_hierarchy("HOME", list(HOME_CUSTOMER_HIERARCHY))
    assert result["valid"] is True
    assert validate_surface_hierarchy("HOME", ["worth_watching", "best_opportunities"])["valid"] is False


def test_research_certified_content_precedes_context():
    result = validate_surface_hierarchy("RESEARCH", list(RESEARCH_CUSTOMER_HIERARCHY))
    assert result["valid"] is True
    assert RESEARCH_CUSTOMER_HIERARCHY.index("atlas_fair_value") < RESEARCH_CUSTOMER_HIERARCHY.index("wall_street_context")


def test_home_contract_excludes_deep_and_external_modules():
    redundant = set(HOME_INDICATOR_CLASSIFICATION["redundant"])
    assert {"wall_street_context", "professional_detail", "full_chart", "earnings_call_intelligence"} <= redundant
    result = validate_home_indicator_slots(list(HOME_INDICATOR_CLASSIFICATION["customer_primary"]))
    assert result["valid"] is True


def test_customer_evidence_states_are_fail_closed():
    assert tuple(CUSTOMER_EVIDENCE_STATES) == ("Evidence Complete", "Evidence Limited", "Data Unavailable")
    assert _customer_evidence_state({"certified_customer_evaluation": {"customer_publication_allowed": True}}) == "Evidence Complete"
    assert _customer_evidence_state({"certified_customer_evaluation": {"customer_publication_allowed": False}}) == "Evidence Limited"
    assert _customer_evidence_state({"evidence_status": "DATA_UNAVAILABLE"}) == "Data Unavailable"
    assert _customer_evidence_state({}) == "Evidence Limited"


def test_home_active_shell_has_no_deep_module_calls():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    active = source[source.index("def render_home_guidance_vnext"):]
    for forbidden in ("_wall_street_view(", "_mini_chart(", "Professional Detail", "_full_evidence("):
        assert forbidden not in active
    assert active.index("_action_counts(story)") < active.index("_render_groups(story")


def test_research_trust_tiers_and_collapsed_context_are_explicit():
    source = (ROOT / "ui" / "research_vnext.py").read_text(encoding="utf-8")
    assert set(PRESENTATION_TRUST_TIERS) == {
        "CERTIFIED_ATLAS", "EXTERNAL_ANALYST_CONTEXT", "LIVE_MARKET_CONTEXT", "CONTEXTUAL_INTELLIGENCE",
    }
    for label in ("Wall Street Context", "External Analyst Data", "Ownership & Filings", "Company Communications", "Full Investment Case — deep dive"):
        assert f'with st.expander("{label}", expanded=False)' in source
    assert "External analyst context — not used in ATLAS scoring." in source
    assert "Live market context — partial real-time data for reference." in source


def test_mobile_keeps_actionable_cards_before_watching():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    group = source[source.index("def _render_groups"):source.index("def _action_counts")]
    assert group.index("for index, card in enumerate(actionable)") < group.index('with st.expander(f"Worth Watching')
    assert "@media(max-width:700px)" in source

