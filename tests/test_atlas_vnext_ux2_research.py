"""UX-2 Research hierarchy, migration, and immutable-output contracts."""

from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agents.atlas_visual_crawler_v1 import RESEARCH_VNEXT_SECTIONS as CRAWLER_SECTIONS
from engines.research_context import build_production_decision
from services.vnext_presentation_contract import (
    CURRENT_RESEARCH_TABS, MIGRATION_BASELINE_VERSION,
    PROTECTED_EVIDENCE_FAMILIES, PROTECTED_INVESTMENT_OUTPUTS,
)
from ui.research_vnext import (
    RESEARCH_EVIDENCE_MIGRATION, RESEARCH_VNEXT_SECTIONS,
    RESEARCH_VNEXT_VERSION, build_research_decision_view,
)
from ui.research_report_v2 import _money, _pct


ROOT = Path(__file__).resolve().parents[1]


def _render_app(ticker: str, verdict: str, completeness: float) -> AppTest:
    source = f'''
import streamlit as st
from tests.test_atlas_vnext_ux2_research import report_fixture
from ui.research_vnext import render_research_vnext
def meta(section): st.caption("Status metadata")
def metric_grid(data, **kwargs):
    for key, value in data.items():
        if not isinstance(value, (dict, list, tuple, set)): st.metric(str(key), str(value))
def interpretation(text): st.info(text or "Unavailable")
def valuation(report): st.metric("Atlas Quant Fair Value", "$120.00")
def analyst(value): st.write("Analyst evidence")
def trade_plan(report): st.write("Canonical actionable trade plan")
def price_chart(report): st.line_chart([1, 2, 3])
def policy(value): st.write("Contextual policy evidence")
report = report_fixture(ticker={ticker!r}, verdict={verdict!r}, completeness={completeness!r})
if {ticker!r} == "CRC":
    report["opportunity_score"] = None
    report["confidence_pct"] = None
    report["atlas_fair_value"] = None
    report["atlas_expected_return_pct"] = None
    report["guidance_summary"]["unavailable_evidence"] = ["Atlas FV", "Confidence"]
render_research_vnext(report, legacy={{"meta": meta, "metric_grid": metric_grid, "interpretation": interpretation, "valuation": valuation, "analyst": analyst, "trade_plan": trade_plan, "price_chart": price_chart, "policy": policy}})
'''
    return AppTest.from_string(source, default_timeout=20).run()


def report_fixture(*, ticker: str = "NVDA", verdict: str = "BUY_NOW", completeness: float = 92.0) -> dict:
    return {
        "ticker": ticker, "company": f"{ticker} Example",
        "committee_verdict": verdict, "opportunity_score": 84.0,
        "confidence_pct": 78.0, "research_completeness_pct": completeness,
        "current_price": 100.0, "atlas_fair_value": 120.0,
        "atlas_expected_return_pct": 20.0,
        "trade_plan": {
            "actionable": True, "current_price": 100.0, "entry_low": 98.0,
            "entry_high": 102.0, "stop_loss": 94.0, "target_1": 112.0,
            "target_2": 120.0, "risk_reward_target_1": "2.0×",
        },
        "guidance_summary": {
            "action_now": {"current_action": "Buy Now"},
            "supporting_facts": [{"fact": "Revenue growth", "why_it_matters": "Demand remains strong."}],
            "key_risks": [{"risk": "Valuation", "consequence": "Multiple compression could reduce upside."}],
            "unavailable_evidence": [],
            "next_catalyst": {"event": "Earnings", "date": "2026-09-01", "what_atlas_will_watch": "Guidance"},
            "thesis_change_conditions": {"strengthen": ["Higher guidance"], "weaken": ["Margin compression"], "invalidate": ["Demand reversal"]},
        },
        "technical_state": "NEAR_BREAKOUT",
        "sections": {
            "financials": {"status": "available", "semantic_status": "AVAILABLE", "completeness_pct": 100, "data": {"revenue_growth_pct": 20.0}},
            "earnings": {"status": "available", "semantic_status": "AVAILABLE", "completeness_pct": 100, "data": {}},
            "analysts": {"status": "available", "semantic_status": "AVAILABLE", "completeness_pct": 100, "data": {}},
            "technical": {"status": "available", "semantic_status": "AVAILABLE", "completeness_pct": 100, "data": {"technical_state": "NEAR_BREAKOUT"}},
            "risk": {"status": "available", "semantic_status": "AVAILABLE", "completeness_pct": 100, "data": [{"factor": "Valuation", "level": "Medium"}]},
            "news": {"status": "available", "semantic_status": "AVAILABLE", "completeness_pct": 100, "data": [{"headline": "Company update"}]},
            "ownership": {"status": "available", "semantic_status": "AVAILABLE", "completeness_pct": 100, "data": {"major_holders": [], "insider_transactions": []}},
            "political": {"status": "unavailable", "semantic_status": "DATA_UNAVAILABLE", "completeness_pct": 0, "data": {}},
        },
        "research_context": {
            "limitations": [],
            "evidence_families": {
                "financial_statements": {"cache_status": "FRESH_CACHE", "provider": "FMP", "evidence_ids": ["ev_financials"]},
            },
        },
        "evidence_registry": {"financials": {"status": "available"}},
        "earnings_intelligence": {"semantic_status": "AVAILABLE", "latest_quarter": {"fiscal_period": "Q2 2026"}, "history": []},
        "earnings_summary": {"summary": "Reported earnings available", "watch_next": "Guidance"},
        "management_guidance": {"semantic_status": "DATA_UNAVAILABLE"},
        "transcript_intelligence": {"semantic_status": "DATA_UNAVAILABLE"},
        "analyst_intelligence": {"wall_street_mean_target": 118.0, "wall_street_implied_upside_pct": 18.0, "analyst_coverage": 20},
        "bull_case": ["Demand remains strong"], "bear_case": ["Valuation remains elevated"],
        "executive_summary": "Canonical summary", "investment_thesis": "Canonical thesis",
    }


def test_v1_twelve_tabs_are_intentionally_replaced_by_five_section_baseline():
    assert MIGRATION_BASELINE_VERSION == "ATLAS_VNEXT_UX2_RESEARCH_MIGRATION_BASELINE"
    assert CURRENT_RESEARCH_TABS == RESEARCH_VNEXT_SECTIONS
    assert len(RESEARCH_VNEXT_SECTIONS) == 5
    assert tuple(CRAWLER_SECTIONS) == (
        "decision", "fundamentals-and-valuation", "technical-and-trade-state",
        "catalysts-and-sentiment", "risk-and-evidence",
    )


def test_complete_v1_research_evidence_has_an_explicit_vnext_destination():
    required = {
        "Executive Summary", "Investment Thesis", "Bull Case", "Bear Case",
        "Final Atlas Guidance", "Recommendation / Verdict", "Evidence-gap warning",
        "Strengthen / Weaken / Invalidate", "Atlas Quant FV", "Atlas-FV upside",
        "Wall Street consensus / range", "Financial metrics / interpretation",
        "Earnings history / trend", "Deterministic technical state",
        "Current price / entry / targets / stop", "Technical metrics / interpretation",
        "Historical price chart / records", "Company news / materiality",
        "Analyst sentiment / trend / actions", "Management guidance",
        "Policy developments", "Transcript intelligence", "Risk factors / interpretation",
        "Ownership / major holders / insiders", "Political transaction evidence",
        "Score attribution", "Provenance / evidence IDs / freshness",
        "AI assumptions / evidence gaps", "Limitations / stale / unavailable states",
        "Ask Atlas AI tab",
    }
    assert required <= set(RESEARCH_EVIDENCE_MIGRATION)
    destinations = set(RESEARCH_EVIDENCE_MIGRATION.values())
    assert set(RESEARCH_VNEXT_SECTIONS) <= destinations
    assert "Persistent contextual CTA" in destinations


def test_high_evidence_decision_view_preserves_canonical_values_and_risk_symmetry():
    report = report_fixture()
    before = deepcopy(report)
    view = build_research_decision_view(report)
    assert view["monitor_or_incomplete"] is False
    assert view["header"].recommendation == "BUY_NOW"
    assert view["header"].confidence == 78.0
    assert view["header"].research_completeness == 92.0
    assert view["technical_badge"].canonical_value == "NEAR_BREAKOUT"
    assert view["prices"].current_price.exact_value == 100.0
    assert view["prices"].invalidation.exact_value == 94.0
    assert view["evidence"].support.startswith("Revenue growth")
    assert view["evidence"].contradiction_or_risk.startswith("Valuation")
    assert report == before


def test_monitor_incomplete_state_is_non_actionable_and_preserves_scenario_levels():
    report = report_fixture(ticker="CRC", verdict="MONITOR", completeness=40.0)
    report["opportunity_score"] = None
    report["confidence_pct"] = None
    report["atlas_fair_value"] = None
    report["atlas_expected_return_pct"] = None
    report["guidance_summary"]["unavailable_evidence"] = ["Atlas FV", "Confidence"]
    view = build_research_decision_view(report)
    assert view["monitor_or_incomplete"] is True
    assert view["header"].actionability_label == "Monitor — Not currently actionable"
    assert view["header"].confidence is None
    assert view["header"].research_completeness == 40.0
    assert view["prices"].entry_low.exact_value == 98.0
    assert view["prices"].invalidation.exact_value == 94.0
    assert view["critical_gaps"] == ("Atlas FV", "Confidence")


def test_missing_change_is_not_fabricated():
    view = build_research_decision_view(report_fixture())
    assert view["material_change"] is None
    report = report_fixture()
    report["change_since_last_scan"] = "Technical state changed to Near Breakout"
    assert build_research_decision_view(report)["material_change"] == "Technical state changed to Near Breakout"


def test_reused_research_metrics_follow_canonical_customer_formatting():
    assert _money(52.94) == "$52.94"
    assert _money(41_809_874_944) == "$41.8B"
    assert _pct(23.8, signed=True) == "+23.8%"
    assert _money(None) == "Unavailable"


def test_immutable_production_decision_is_byte_value_equivalent_after_view_build():
    source = {
        "Recommendation": "BUY NOW", "Opportunity": 84.0, "Confidence": 78.0,
        "rank": 2, "atlas_fair_value": 120.0, "expected_return_pct": 20.0,
        "entry_low": 98.0, "entry_high": 102.0, "target_1": 112.0,
        "target_2": 120.0, "stop": 94.0, "position_sizing": "2–3%",
    }
    before = dict(build_production_decision(source))
    build_research_decision_view(report_fixture())
    assert dict(build_production_decision(source)) == before
    assert {"recommendation", "ranking", "score", "atlas_fair_value", "stop", "position_sizing"} <= set(PROTECTED_INVESTMENT_OUTPUTS)
    assert "political_context" in PROTECTED_EVIDENCE_FAMILIES


def test_active_research_renderer_uses_vnext_and_returns_before_legacy_tabs():
    source = (ROOT / "ui/research_report_v2.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    active = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_atlas_research_v2")
    rendered = ast.unparse(active)
    assert "render_research_vnext" in rendered
    assert rendered.index("render_research_vnext") < rendered.index("tabs = st.tabs")
    assert RESEARCH_VNEXT_VERSION == "ATLAS_RESEARCH_VNEXT_UX2"


def test_monitor_trade_levels_are_only_inside_collapsed_technical_scenario_contract():
    source = (ROOT / "ui/research_vnext.py").read_text(encoding="utf-8")
    assert 'with st.expander(scenario.label, expanded=False)' in source
    assert "do not represent a high-confidence ATLAS recommendation" in (ROOT / "ui/vnext_presentation.py").read_text(encoding="utf-8")
    assert 'technical_state in {"MONITOR", "WATCH"}' in source
    assert "No actionable technical state is currently published." in source


def test_ask_is_contextual_cta_not_sixth_research_tab():
    source = (ROOT / "ui/research_vnext.py").read_text(encoding="utf-8")
    assert 'st.button("Ask ATLAS about this research"' in source
    assert 'st.session_state["v79_pending_page"] = "Ask AI"' in source
    assert "Ask Atlas AI" not in RESEARCH_VNEXT_SECTIONS


def test_invalid_ticker_contract_remains_pre_acquisition_and_outside_renderer():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    active = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_research_any_ticker"][-1]
    rendered = ast.unparse(active)
    assert rendered.index("re.fullmatch") < rendered.index("build_live_research_row")
    assert "INVALID123" not in RESEARCH_EVIDENCE_MIGRATION


@pytest.mark.parametrize("ticker", ("NVDA", "CRC", "SPY"))
def test_representative_structural_views_do_not_mutate_or_invent(ticker):
    verdict, completeness = ("MONITOR", 40.0) if ticker == "CRC" else ("MONITOR", 80.0) if ticker == "SPY" else ("BUY_NOW", 92.0)
    report = report_fixture(ticker=ticker, verdict=verdict, completeness=completeness)
    if ticker == "SPY":
        report["earnings_intelligence"] = {"semantic_status": "NOT_APPLICABLE"}
    before = deepcopy(report)
    view = build_research_decision_view(report)
    assert view["header"].recommendation == verdict
    assert report == before


def test_real_streamlit_high_evidence_renderer_has_five_sections_and_ask_cta():
    app = _render_app("NVDA", "BUY_NOW", 92.0)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == list(RESEARCH_VNEXT_SECTIONS)
    assert any(button.label == "Ask ATLAS about this research" for button in app.button)
    assert any(metric.label == "Confidence" and metric.value == "78.0%" for metric in app.metric)
    # UX-3B intentionally limits the executive strip to five decision metrics;
    # completeness remains visible in Evidence Health rather than as a sixth metric.
    assert not any(metric.label == "Research Completeness" for metric in app.metric)


def test_real_streamlit_monitor_renderer_collapses_technical_scenario():
    app = _render_app("CRC", "MONITOR", 40.0)
    assert not app.exception
    assert any("Monitor — Not currently actionable" in markdown.value for markdown in app.markdown)
    assert any(expander.label == "Technical Scenario" for expander in app.expander)
    assert not any(text.value == "Canonical actionable trade plan" for text in app.text)
    assert any(metric.label == "Confidence" and metric.value == "Unavailable" for metric in app.metric)
