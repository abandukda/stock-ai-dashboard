"""Final-runtime activation regressions for the UX-2 Research hierarchy."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
SECTIONS = [
    "Decision", "Fundamentals & Valuation", "Technical & Trade State",
    "Catalysts & Sentiment", "Risk & Evidence",
]
LEGACY_TABS = {
    "Thesis", "Growth & Profitability", "Earnings Intelligence", "Risk",
    "Catalysts & Company News", "Ownership", "Political Intelligence Boundary",
    "Earnings Call Boundary", "Chart & Technicals", "Final Decision",
    "AI Intelligence", "Ask Atlas AI",
}


def _active_app(ticker: str, *, monitor: bool = False, mobile: bool = False) -> AppTest:
    source = f'''
import streamlit as st
import engines.atlas_research_builder_v2 as builder
import ui.research_report_v2 as legacy
from tests.test_atlas_vnext_ux2_research import report_fixture

report = report_fixture(ticker={ticker!r}, verdict={"MONITOR" if monitor else "BUY_NOW"!r}, completeness={40.0 if monitor else 92.0!r})
if {monitor!r}:
    report["opportunity_score"] = None
    report["confidence_pct"] = None
    report["atlas_fair_value"] = None
    report["atlas_expected_return_pct"] = None
    report["guidance_summary"]["unavailable_evidence"] = ["Atlas FV", "Confidence"]
builder.build_atlas_research_v2 = lambda row: report
legacy._load_policy_enrichment = lambda symbol, row: {{"metrics": {{}}}}
legacy._load_ai_valuation = lambda symbol, row: {{}}
st.session_state["atlas_test_viewport"] = {"mobile" if mobile else "desktop"!r}
import app
app.render_detail({{"ticker": {ticker!r}, "research_context": {{"evidence_families": {{}}}}}})
'''
    return AppTest.from_string(source, default_timeout=30).run()


def _assert_five_section_dom(app_test: AppTest, ticker: str) -> None:
    assert not app_test.exception
    labels = [tab.label for tab in app_test.tabs]
    assert labels == SECTIONS
    assert not (set(labels) & LEGACY_TABS)
    html = "\n".join(str(markdown.value) for markdown in app_test.markdown)
    assert 'data-atlas-version="ATLAS_RESEARCH_VNEXT_UX2"' in html
    assert f'data-atlas-ticker="{ticker}"' in html
    assert 'data-atlas-section-count="5"' in html
    assert 'data-atlas-qa="research-ask-cta"' in html


def _submitted_final_route(ticker: str) -> AppTest:
    source = f'''
import pandas as pd
import engines.atlas_research_builder_v2 as builder
import ui.research_report_v2 as legacy
from tests.test_atlas_vnext_ux2_research import report_fixture
import app

report = report_fixture(ticker={ticker!r})
builder.build_atlas_research_v2 = lambda row: report
legacy._load_policy_enrichment = lambda symbol, row: {{"metrics": {{}}}}
legacy._load_ai_valuation = lambda symbol, row: {{}}
app.build_live_research_row = lambda symbol, **kwargs: {{
    "ticker": symbol, "company": symbol + " Example", "research_context": {{
        "context_version": "RESEARCH_CONTEXT_V1", "ticker": symbol,
        "production_decision": {{"semantic_status": "AVAILABLE"}},
        "evidence_families": {{}},
    }},
}}
empty = pd.DataFrame()
app.render_research_any_ticker(empty, empty, empty, empty, empty)
'''
    app_test = AppTest.from_string(source, default_timeout=30).run()
    app_test.text_input(key="typed_ticker").set_value(ticker)
    return app_test.button[0].click().run()


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "mobile"])
def test_final_active_app_render_graph_exposes_exactly_five_sections(mobile: bool):
    _assert_five_section_dom(_active_app("NVDA", mobile=mobile), "NVDA")


def test_final_active_app_monitor_is_non_actionable_and_five_section():
    app_test = _active_app("CRC", monitor=True)
    _assert_five_section_dom(app_test, "CRC")
    assert "Monitor — Not currently actionable" in "\n".join(
        str(item.value) for item in app_test.markdown
    )


def test_real_final_research_submission_reaches_five_section_dom():
    _assert_five_section_dom(_submitted_final_route("NVDA"), "NVDA")


def test_home_handoff_and_direct_route_converge_on_final_vnext_adapter():
    app_tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    detail = [node for node in app_tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_detail"][-1]
    detail_source = ast.get_source_segment((ROOT / "app.py").read_text(encoding="utf-8"), detail) or ""
    assert "ui.research_vnext" in detail_source
    assert "render_full_research_vnext" in detail_source

    home_source = (ROOT / "ui" / "home_v104.py").read_text(encoding="utf-8")
    institutional_source = (ROOT / "ui" / "institutional_experience.py").read_text(encoding="utf-8")
    assert "begin_research_entry" in home_source
    assert "begin_research_entry" in institutional_source
    _assert_five_section_dom(_active_app("CRM"), "CRM")


def test_compatibility_renderers_delegate_at_call_time_and_preserve_legacy_source():
    v104 = (ROOT / "ui" / "research_report_v104.py").read_text(encoding="utf-8")
    v2 = (ROOT / "ui" / "research_report_v2.py").read_text(encoding="utf-8")
    assert "from ui.research_report_v2 import render_atlas_research_v2" not in v104
    assert "from ui.research_vnext import render_full_research_vnext" in v104
    assert "from ui.research_vnext import render_full_research_vnext" in v2
    assert "Growth & Profitability" in v2  # rollback source retained
    assert v2.index("render_full_research_vnext(row)") < v2.index("Growth & Profitability")


def test_visual_crawler_certifies_only_the_authoritative_five_sections():
    source = (ROOT / "agents" / "atlas_visual_crawler_v1.py").read_text(encoding="utf-8")
    assert "expected_tabs=RESEARCH_VNEXT_SECTION_LABELS" in source
    for label in SECTIONS:
        assert label in source
    assert "expected_tabs=LEGACY" not in source
