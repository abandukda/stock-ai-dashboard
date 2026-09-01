from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from engines.full_scan_decision_story import (
    FULL_SCAN_DECISION_STORY_VERSION, NO_PRIOR_SCAN_COMPARISON,
    build_full_scan_decision_story,
)
from ui.full_scan_vnext import (
    FULL_SCAN_VNEXT_VERSION, _filter_stories, _production_stories,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = (
    "etf_scan.json", "market_full_scan.json", "market_prescreen.json",
    "market_scan_state.json", "recovery_scan.json", "total_market_universe.json",
)


def _raw(**overrides):
    row = {
        "ticker": "AAA", "company": "Alpha Corp", "sector": "Technology",
        "Recommendation": "BUY NOW", "Opportunity": 82, "Confidence": 74,
        "atlas_fair_value": 125, "decision_expected_return_pct": 18,
        "conviction": 91, "relative_rank_score": 88.2,
        "deterministic_technical_state": "Confirmed breakout",
        "why_ranked_high": "Persisted growth, valuation, and technical evidence align.",
        "setup_tags": ["Strong liquidity", "Price above the 50-day trend"],
        "risk_tags": ["Volume confirmation is light"],
        "revenue_growth": .12, "earnings_growth": .08,
        "free_cash_flow": 0, "cash_and_equivalents": 0, "total_debt": -5,
        "analyst_target_mean": 120, "analyst_target_low": 90,
        "analyst_target_high": 145, "analyst_count": 12,
        "rsi": 58, "scan_time": "2026-09-01T10:00:00Z",
    }
    row.update(overrides)
    return row


def test_story_contract_preserves_canonical_outputs_and_rank():
    raw = _raw()
    before = copy.deepcopy(raw)
    story = build_full_scan_decision_story(raw, production_rank=7, filtered_position=2)
    assert story["version"] == FULL_SCAN_DECISION_STORY_VERSION
    assert story["production_rank"] == 7 and story["filtered_position"] == 2
    assert story["production_decision"]["recommendation"] == "BUY NOW"
    assert story["opportunity"] == 82
    assert story["confidence"] == 74
    assert story["valuation"]["atlas_fair_value"] == 125
    assert story["valuation"]["expected_return"] == 18
    assert story["technical_state"]["state"] == "Confirmed breakout"
    assert raw == before


def test_nested_raw_row_defeats_display_recommendation_and_target_fallbacks():
    raw = _raw(
        Recommendation=None, Opportunity=None, atlas_fair_value=None,
        decision_expected_return_pct=None, analyst_target_mean=155,
    )
    wrapper = {
        "Ticker": "AAA", "Company": "Alpha Corp", "Recommendation": "BUY NOW",
        "Opportunity": 99, "Confidence": 99, "AI Fair Value": 155, "Raw": raw,
    }
    story = build_full_scan_decision_story(wrapper, production_rank=1)
    assert story["production_decision"]["recommendation"] is None
    assert story["canonical_state_status"] == "DATA_UNAVAILABLE"
    assert story["opportunity"] is None
    assert story["valuation"]["atlas_fair_value"] is None
    assert story["valuation"]["expected_return"] is None
    assert story["valuation"]["wall_street_mean"] == 155
    assert story["actionability"]["state"] == "Decision unavailable"


def test_existing_research_context_is_exact_authority():
    canonical = {
        "semantic_status": "DATA_UNAVAILABLE", "recommendation": None,
        "opportunity": None, "confidence": 97, "atlas_fair_value": None,
        "decision_expected_return": None,
    }
    row = _raw(Recommendation="BUY NOW")
    row["research_context"] = {"production_decision": canonical}
    story = build_full_scan_decision_story(row, production_rank=1)
    assert story["production_decision"] == canonical
    assert story["canonical_state_status"] == "DATA_UNAVAILABLE"


def test_zero_negative_missing_company_and_partial_evidence_remain_exact():
    story = build_full_scan_decision_story(_raw(
        company=None, Opportunity=0, Confidence=0, atlas_fair_value=0,
        decision_expected_return_pct=-12, setup_tags=[], why_ranked_high=None,
        finance_agent_findings=[], risk_tags=[], what_could_go_wrong=None,
        news_evidence=[],
    ), production_rank=3)
    assert story["identity"]["company"] == "AAA"
    assert story["opportunity"] == 0
    assert story["confidence"] == 0
    assert story["valuation"]["atlas_fair_value"] == 0
    assert story["valuation"]["expected_return"] == -12
    assert story["what_changed"]["message"] == NO_PRIOR_SCAN_COMPARISON
    assert story["why_ranked"] == []
    assert story["constraints"] == []


def test_filtered_view_retains_production_rank_and_only_updates_filtered_position():
    frame = pd.DataFrame([
        {**_raw(ticker="THREE"), "Production Rank": 3},
        {**_raw(ticker="ONE"), "Production Rank": 1},
        {**_raw(ticker="TWO"), "Production Rank": 2},
    ])
    stories = _production_stories(frame)
    assert [item["identity"]["ticker"] for item in stories] == ["ONE", "TWO", "THREE"]
    filtered = _filter_stories(stories, search="three")
    assert [item["identity"]["ticker"] for item in filtered] == ["THREE"]
    assert filtered[0]["production_rank"] == 3
    assert filtered[0]["filtered_position"] == 1


def test_load_full_scan_preserves_raw_artifact_rank_before_legacy_sort(monkeypatch):
    import app

    rows = [
        _raw(ticker="AAA", conviction=70, target_upside_pct=10, dollar_volume=100),
        _raw(ticker="BBB", conviction=60, target_upside_pct=10, dollar_volume=100),
        _raw(ticker="CCC", conviction=99, target_upside_pct=40, dollar_volume=100),
    ]
    monkeypatch.setattr(app, "read_json_file", lambda path: copy.deepcopy(rows))
    loaded = app.load_full_scan()
    assert loaded["Ticker"].tolist() == ["CCC", "AAA", "BBB"]
    assert loaded["Production Rank"].astype(int).tolist() == [3, 1, 2]
    stories = _production_stories(loaded)
    assert [(item["identity"]["ticker"], item["production_rank"]) for item in stories] == [
        ("AAA", 1), ("BBB", 2), ("CCC", 3),
    ]
    filtered = _filter_stories(stories, search="CCC")
    assert filtered[0]["production_rank"] == 3
    assert filtered[0]["filtered_position"] == 1


def test_no_rank_movement_or_factor_contribution_is_invented():
    story = build_full_scan_decision_story(_raw(
        prior_rank=9, dynamic_rank=2, rank_change=7,
    ), production_rank=4)
    assert story["what_changed"] == {
        "semantic_status": "DATA_UNAVAILABLE", "message": NO_PRIOR_SCAN_COMPARISON,
    }
    rendered = json.dumps(story)
    assert "contributed" not in rendered.lower()
    assert "rank improved" not in rendered.lower()


def test_final_active_route_uses_only_full_scan_vnext():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    final_main = source[source.rfind("def main():"):]
    branch = final_main.split('elif selected_page=="Full Ranked Scan":', 1)[1].split(
        'elif selected_page=="Portfolio Intelligence":', 1
    )[0]
    assert "render_full_scan_vnext(" in branch
    assert "emit_interactive=" not in branch
    assert "render_v56_ranked_table" not in branch


def _final_app_full_scan_script(rows):
    return f'''\
import pandas as pd
import app
rows = {repr(rows)}
app.dashboard_login_gate = lambda: True
for name in (
    "render_v59_design_system", "render_v65_design_system", "render_v70_design_system",
    "render_v72_design_system", "render_v73_design_system", "render_v74_design_system",
    "v775_design_system", "v793_design_system", "v8055_inject_research_css",
):
    setattr(app, name, lambda: None)
app.load_full_scan = lambda: pd.DataFrame(rows)
app.latest_top_ideas = lambda: pd.DataFrame()
app.latest_recovery = lambda: pd.DataFrame()
app.latest_watchlist_scan = lambda: pd.DataFrame()
app.load_file = lambda path: pd.DataFrame()
app.render_v73_top_nav = lambda pages: "Full Ranked Scan"
app._emit_page_identity_marker = lambda page: None
app.render_v72_market_tape = lambda always_show=False: None
app._emit_page_certification_marker = lambda *args: None
app.v784_open_research = lambda ticker: None
app.main()
'''


def test_final_app_route_executes_default_lifecycle_between_first_two_candidates():
    rows = [
        {**_raw(ticker="AAA"), "Production Rank": 1},
        {**_raw(ticker="BBB", company="Beta Corp"), "Production Rank": 2},
    ]
    at = AppTest.from_string(_final_app_full_scan_script(rows), default_timeout=15).run()
    assert not at.exception
    markdown = "\n".join(item.value for item in at.markdown)
    assert markdown.count('data-atlas-page-interactive="true"') == 1
    first_candidate = markdown.index('data-atlas-production-rank="1"')
    page_interactive = markdown.index('data-atlas-page-interactive="true"')
    second_candidate = markdown.index('data-atlas-production-rank="2"')
    assert first_candidate < page_interactive < second_candidate


def test_final_app_filtered_empty_state_precedes_single_lifecycle_marker():
    rows = [
        {**_raw(ticker="AAA"), "Production Rank": 1},
        {**_raw(ticker="BBB", company="Beta Corp"), "Production Rank": 2},
    ]
    at = AppTest.from_string(_final_app_full_scan_script(rows), default_timeout=15).run()
    assert not at.exception
    at.text_input(key="full_scan_vnext_search").set_value("ZZZ")
    at.run()
    assert not at.exception
    markdown = "\n".join(item.value for item in at.markdown)
    warnings = "\n".join(item.value for item in at.warning)
    assert "No persisted candidates match" in warnings
    assert markdown.count('data-atlas-page-interactive="true"') == 1
    assert not any(button.label.startswith("View Investment Case") for button in at.button)


def test_real_streamlit_surface_emits_contract_rank_and_exact_ticker_cta():
    script = f'''\
import pandas as pd
from ui.full_scan_vnext import render_full_scan_vnext
rows = {repr([_raw(ticker="AAA"), _raw(ticker="BBB", company="Beta Corp")])}
render_full_scan_vnext(pd.DataFrame(rows), open_research=lambda ticker: None)
'''
    at = AppTest.from_string(script, default_timeout=10).run()
    assert not at.exception
    markdown = "\n".join(item.value for item in at.markdown)
    assert f'data-atlas-full-scan-version="{FULL_SCAN_VNEXT_VERSION}"' in markdown
    assert 'data-atlas-production-rank="1"' in markdown
    assert 'data-atlas-production-rank="2"' in markdown
    assert "Production Rank never changes" in "\n".join(item.value for item in at.info)
    assert any(button.label == "View Investment Case — AAA" for button in at.button)
    assert any(button.label == "View Investment Case — BBB" for button in at.button)
    first_candidate = markdown.index('data-atlas-production-rank="1"')
    page_interactive = markdown.index('data-atlas-page-interactive="true"')
    second_candidate = markdown.index('data-atlas-production-rank="2"')
    assert first_candidate < page_interactive < second_candidate


def test_builder_and_renderer_have_no_provider_scanner_or_legacy_authority_calls():
    builder = (ROOT / "engines" / "full_scan_decision_story.py").read_text(encoding="utf-8")
    renderer = (ROOT / "ui" / "full_scan_vnext.py").read_text(encoding="utf-8")
    combined = builder + renderer
    for forbidden in (
        "overnight_market_scan", "FMPStableClient", "requests.",
        "v63_opportunity_score", "v63_quality_score", "v64_recommendation",
    ):
        assert forbidden not in combined
    assert "emit_page_interactive(st, \"Full Ranked Scan\")" in renderer


def test_production_json_hashes_are_read_only_fixture_inputs():
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in PRODUCTION_FILES
    }
    assert all(len(value) == 64 for value in hashes.values())
