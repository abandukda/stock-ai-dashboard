from __future__ import annotations

import ast
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from engines.home_guidance_story_v1 import HOME_FIELD_AUTHORITY, build_home_guidance_candidate, build_home_guidance_story


ROOT = Path(__file__).resolve().parents[1]


def row(ticker: str, conviction: float = 80, **extra):
    base = {
        "ticker": ticker, "company": ticker + " Inc.", "price": 100,
        "scan_time": "2026-09-01T12:00:00+00:00", "conviction": conviction,
        "forward_eps": 5, "forward_eps_source": "CANONICAL_ESTIMATE",
        "revenue_growth": 10, "revenue_growth_source": "CANONICAL_FINANCIALS",
        "revenue_growth_horizon": "TTM", "operating_profit_margin": .2,
        "risk_reward": 1.8, "entry_low": 95, "entry_high": 105,
        "stop_loss": 90, "target_1": 120, "analyst_target_mean": 115,
        "analyst_target_low": 90, "analyst_target_high": 140,
        "analyst_count": 12, "recommendation_key": "strong_buy",
    }
    base.update(extra)
    return base


def canonical_evaluation(*, guidance="DATA_LIMITED", opportunity=None, confidence=None, fv=None, expected=None):
    return {
        "version": "CANONICAL_INVESTMENT_EVALUATION_V1", "evaluated_at": "2026-09-02T12:00:00+00:00",
        "methodology_version": "FOUNDER_GUIDANCE_V1", "opportunity": opportunity,
        "decision_confidence": confidence,
        "guidance": {"state": guidance, "status": "AVAILABLE" if guidance != "DATA_LIMITED" else "DATA_UNAVAILABLE", "reason_codes": ("CURRENT_MARKET_EVIDENCE_UNAVAILABLE",)},
        "actionability": {"status": "ACTIONABLE" if guidance in {"BUY_NOW", "ACCUMULATE"} else "UNAVAILABLE" if guidance == "DATA_LIMITED" else "NOT_ACTIONABLE"},
        "market_snapshot": {"source_type": "LAST_KNOWN", "customer_label": "Last known price"},
        "technical_confirmation": {"status": "DATA_UNAVAILABLE", "state": "UNAVAILABLE"},
        "volume_intelligence": {"status": "DATA_UNAVAILABLE", "state": "UNAVAILABLE"},
        "fundamentals": {"status": "AVAILABLE"}, "risk": {"status": "AVAILABLE"},
        "atlas_valuation": {"status": "PUBLISHED" if fv is not None else "REJECTED_EXTREME_UPSIDE", "fair_value": fv, "expected_return": expected},
        "trade_plan": {"entry_low": 95, "entry_high": 105, "stop": 90, "target_1": 120},
    }


def test_artifact_order_is_immutable_production_rank_and_never_resorted():
    story = build_home_guidance_story([row("AAA", 1), row("BBB", 99), row("CCC", 50)], [])
    assert [(card["ticker"], card["production_rank"]) for card in story["cards"]] == [
        ("AAA", 1), ("BBB", 2), ("CCC", 3),
    ]


def test_recovery_joins_exact_ticker_without_full_scan_recovery_alias():
    story = build_home_guidance_story(
        [row("MU")],
        [{"ticker": "MU", "recovery_score": 69, "recovery_label": "Recovery Candidate", "scan_time": "2026-09-01"}],
    )
    assert story["cards"][0]["recovery"]["score"] == 69
    assert story["recovery_cards"][0]["ticker"] == "MU"


def test_rejected_fv_suppresses_atlas_expected_return_but_preserves_wall_street():
    card = build_home_guidance_candidate(
        row("MU", atlas_valuation_status="REJECTED_EXTREME_UPSIDE", expected_upside_pct=107.8),
        production_rank=1, current_evaluation=canonical_evaluation(fv=None, expected=107.8),
    )
    assert card["atlas_fair_value"] is None
    assert card["atlas_expected_return"] is None
    assert card["atlas_expected_return_status"] == "DATA_UNAVAILABLE"
    assert card["wall_street"]["mean_target"] == 115


def test_zero_and_negative_canonical_values_are_not_treated_as_missing():
    card = build_home_guidance_candidate(
        row("ZERO", conviction=0), production_rank=1,
        current_evaluation=canonical_evaluation(opportunity=0, confidence=-1, fv=100, expected=0),
    )
    assert card["opportunity"] == 0
    assert card["decision_confidence"] == -1
    assert card["scan_conviction"] == 0
    assert card["atlas_expected_return"] == 0


def test_home_authority_table_covers_every_customer_decision_field():
    assert set(HOME_FIELD_AUTHORITY) == {
        "production_rank", "guidance", "actionability", "opportunity",
        "decision_confidence", "scan_conviction", "atlas_fair_value",
        "atlas_expected_return", "technical_state", "volume_state",
        "recovery_score", "analyst_consensus", "trade_plan",
    }


def test_preview_is_explicit_and_data_limited_remains_truthful(monkeypatch):
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "false")
    story = build_home_guidance_story([row("MU", 97)], [])
    assert story["mode"] == "PREVIEW"
    assert story["status_label"] == "Founder Guidance Preview"
    assert story["cards"][0]["guidance"] == "DATA_LIMITED"
    assert story["cards"][0]["actionability"] == "UNAVAILABLE"
    assert "CURRENT_MARKET_EVIDENCE_UNAVAILABLE" in story["cards"][0]["reason_codes"]


def test_active_mode_uses_governed_evaluation_without_changing_home_structure(monkeypatch):
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "true")
    evaluation = canonical_evaluation(guidance="WAIT_FOR_CONFIRMATION", opportunity=0, confidence=-1, fv=100, expected=0)
    story = build_home_guidance_story([row("MU")], [], current_evaluations={"MU": evaluation})
    assert story["mode"] == "ACTIVE"
    assert story["cards"][0]["guidance"] == "WAIT_FOR_CONFIRMATION"
    assert story["cards"][0]["actionability"] == "NOT_ACTIONABLE"
    assert story["cards"][0]["opportunity"] == 0
    assert story["cards"][0]["decision_confidence"] == -1


def test_not_applicable_evidence_is_not_collapsed_to_unavailable():
    evaluation = canonical_evaluation()
    evaluation["technical_confirmation"] = {"status": "NOT_APPLICABLE", "state": "NOT_APPLICABLE"}
    evaluation["volume_intelligence"] = {"status": "NOT_APPLICABLE", "state": "NOT_APPLICABLE"}
    evaluation["fundamentals"] = {"status": "NOT_APPLICABLE"}
    card = build_home_guidance_candidate(row("SPY"), production_rank=1, current_evaluation=evaluation)
    assert card["technical_status"] == "NOT_APPLICABLE"
    assert card["technical_state"] == "NOT_APPLICABLE"
    assert card["volume_status"] == "NOT_APPLICABLE"
    assert card["volume_state"] == "NOT_APPLICABLE"
    assert card["fundamentals_status"] == "NOT_APPLICABLE"


def test_current_production_representatives_keep_artifact_rank_and_authority_separation(monkeypatch):
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "false")
    payload = json.loads((ROOT / "market_full_scan.json").read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("data") or []
    story = build_home_guidance_story(rows, [])
    cards = {card["ticker"]: card for card in story["cards"]}
    for ticker in ("MU", "NVDA", "INTU", "BZ"):
        if ticker not in cards:
            continue
        raw_rank = next(index for index, item in enumerate(rows, 1) if str(item.get("ticker") or item.get("symbol")).upper() == ticker)
        assert cards[ticker]["production_rank"] == raw_rank
        assert cards[ticker]["guidance"] == "DATA_LIMITED"
        assert cards[ticker]["atlas_expected_return"] is None or cards[ticker]["atlas_fair_value"] is not None
        assert isinstance(cards[ticker]["wall_street"], dict)
        assert cards[ticker]["wall_street"].get("consensus") != cards[ticker]["guidance"]


def test_final_renderer_first_card_precedes_page_interactive_and_secondary_context():
    source = '''
import streamlit as st
from engines.home_guidance_story_v1 import build_home_guidance_story
from ui.home_guidance_vnext import render_home_guidance_vnext
rows = [{"ticker":"MU","company":"Micron","price":100,"scan_time":"2026-09-01T12:00:00+00:00","conviction":97,"forward_eps":5,"forward_eps_source":"CANONICAL_ESTIMATE","revenue_growth":10,"revenue_growth_source":"CANONICAL_FINANCIALS","revenue_growth_horizon":"TTM","operating_profit_margin":.2,"risk_reward":1.8,"entry_low":95,"entry_high":105,"stop_loss":90,"target_1":120,"analyst_target_mean":115}]
story = build_home_guidance_story(rows, [{"ticker":"MU","recovery_score":69}])
render_home_guidance_vnext(story, emit_interactive=lambda: st.markdown('<span data-atlas-page-interactive="true">interactive</span>', unsafe_allow_html=True))
'''
    app = AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    rendered = "\n".join(str(item.value) for item in app.markdown)
    assert rendered.index('data-atlas-first="true"') < rendered.index('data-atlas-page-interactive="true"')
    assert rendered.index('data-atlas-page-interactive="true"') < rendered.index('data-atlas-section="atlas-vs-wall-street"')
    assert rendered.count('data-atlas-page-interactive="true"') == 1
    assert "Founder Guidance Preview" in rendered
    assert "Snapshot Guidance — based on latest available ATLAS evidence" in "\n".join(str(item.value) for item in app.markdown) + "\n".join(str(item.value) for item in app.text)


def test_final_app_home_function_wires_vnext_without_v104_pipeline_authority():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    active = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "v810_render_dynamic_home"][-1]
    body = ast.get_source_segment(source, active) or ""
    assert "build_home_guidance_story" in body
    assert "render_home_guidance_vnext" in body
    assert "market_full_scan.json" in body and "recovery_scan.json" in body
    assert "v104_pipeline_from_df" not in body
    assert "_render_market_tape" not in body
    assert "render_v811_market_calendar_terminal" not in body


def test_final_active_app_home_route_exposes_visible_vnext_dom():
    source = '''
import app
full = [{"ticker":"MU","company":"Micron","price":100,"scan_time":"2026-09-01T12:00:00+00:00","conviction":97,"forward_eps":5,"forward_eps_source":"CANONICAL_ESTIMATE","revenue_growth":10,"revenue_growth_source":"CANONICAL_FINANCIALS","revenue_growth_horizon":"TTM","operating_profit_margin":.2,"risk_reward":1.8,"entry_low":95,"entry_high":105,"stop_loss":90,"target_1":120,"analyst_target_mean":115}]
recovery = [{"ticker":"MU","recovery_score":69,"recovery_label":"Recovery Candidate"}]
app.read_json_file = lambda path: recovery if str(path).endswith("recovery_scan.json") else full
app.read_watchlist_symbols = lambda: ["MU"]
app.read_state = lambda: {"generated_at":"2026-09-01T12:00:00+00:00"}
app.v810_render_dynamic_home()
'''
    app_test = AppTest.from_string(source, default_timeout=30).run()
    assert not app_test.exception
    rendered = "\n".join(str(item.value) for item in app_test.markdown)
    assert 'data-atlas-qa="home-guidance-vnext"' in rendered
    assert 'data-atlas-production-rank="1"' in rendered
    assert 'data-atlas-page-interactive="true"' in rendered
    assert rendered.index('data-atlas-production-rank="1"') < rendered.index('data-atlas-page-interactive="true"')


def test_research_cta_uses_exact_ticker_handoff_contract():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert "begin_research_entry" in source
    assert 'source="HOME_GUIDANCE_VNEXT"' in source
    assert 'View Investment Case — {ticker}' in source
