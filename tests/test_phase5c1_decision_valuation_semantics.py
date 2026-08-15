from __future__ import annotations

import copy
import inspect

from engines.ask_atlas_engine import _compact_context
from engines.analyst_intelligence import build_analyst_intelligence
from services.ai_synthesis import _llm_prompt, build_ticker_context, deterministic_ticker_answer
from ui import daily_opportunities, home_v104, research_report_v2, research_report_v104


def _row(**updates):
    row = {
        "ticker": "TEST",
        "current_price": 100.0,
        "atlas_fair_value": 80.0,
        "analyst_target_mean": 130.0,
        "decision_valuation_target": 130.0,
        "decision_target_source": "wall_street_mean",
        "decision_expected_return_pct": 30.0,
        "expected_return_pct": 30.0,
        "opportunity_score": 71.8,
        "confidence_pct": 72.1,
        "committee_verdict": "BUY_NOW",
    }
    row.update(updates)
    return row


def test_ai_context_keeps_all_valuation_families_explicit_and_separate():
    context = build_ticker_context(_row())
    assert context["atlas_fair_value"] == "$80.00"
    assert context["atlas_fv_upside_pct"] == "-20.0%"
    assert context["analyst_consensus"] == "$130.00"
    assert context["wall_street_implied_upside_pct"] == "30.0%"
    assert context["decision_target"] == "$130.00"
    assert context["decision_target_source"] == "wall_street_mean"
    assert context["decision_target_implied_upside_pct"] == "30.0%"


def test_missing_or_rejected_atlas_fv_cannot_be_replaced_by_consensus():
    context = build_ticker_context(_row(atlas_fair_value=None, atlas_valuation_status="REJECTED_EXTREME_UPSIDE"))
    assert context["atlas_fair_value"] == "Unavailable"
    assert context["atlas_fv_upside_pct"] == "Unavailable"
    assert context["analyst_consensus"] == "$130.00"
    assert context["decision_target"] == "$130.00"


def test_deterministic_answer_uses_source_specific_customer_labels():
    answer = deterministic_ticker_answer("What does Atlas think?", build_ticker_context(_row()))
    assert "Atlas-FV Implied Upside:** -20.0%" in answer
    assert "Wall Street Implied Upside:** 30.0%" in answer
    assert "Atlas expected return" not in answer
    assert "Analyst upside" not in answer


def test_llm_prompt_forbids_cross_labeling_and_calculation():
    prompt = _llm_prompt("Explain valuation", build_ticker_context(_row()))[0]["content"]
    assert "Never call Wall Street implied upside Atlas expected return" in prompt
    assert "Do not calculate valuation or upside values" in prompt


def test_ask_atlas_context_preserves_internal_outputs_without_mutation():
    row = _row()
    before = copy.deepcopy(row)
    context = _compact_context(row)
    assert row == before
    assert context["atlas_fv_upside_pct"] == -20.0
    assert context["wall_street_implied_upside_pct"] == 30.0
    assert context["decision_target_implied_upside_pct"] == 30.0
    for key in (
        "opportunity_score", "confidence_pct", "committee_verdict",
        "decision_valuation_target", "decision_expected_return_pct",
    ):
        assert row[key] == before[key]


def test_active_ui_uses_source_specific_upside_labels():
    home_source = inspect.getsource(home_v104._render_discovery_card)
    candidate_source = inspect.getsource(research_report_v104.render_candidate_card)
    research_source = inspect.getsource(research_report_v2.render_atlas_research_v2)
    analyst_source = inspect.getsource(research_report_v2._analyst_intelligence_html)
    daily_source = inspect.getsource(daily_opportunities._card)
    assert "Atlas-FV Upside" in home_source
    assert "Wall Street Implied Upside" in home_source
    assert "Wall Street Implied Upside" in candidate_source
    assert "Atlas-FV Implied Upside" in research_source
    assert "Wall Street Implied Upside" in analyst_source
    assert "Wall Street Implied Upside" in daily_source
    assert "Decision-Target Implied Upside" in daily_source


def test_cien_style_material_divergence_names_both_sources():
    model = build_analyst_intelligence(_row())
    assert model["atlas_street_relationship"] == "MATERIAL DIVERGENCE"
    assert "Atlas-FV implied upside is -20.0%" in model["atlas_street_divergence_message"]
    assert "Wall Street implied upside is +30.0%" in model["atlas_street_divergence_message"]
