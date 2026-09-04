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


def test_recovery_only_membership_never_invents_full_scan_rank():
    story = build_home_guidance_story(
        [row("AAA")],
        [{"ticker": "MU", "recovery_score": 69, "recovery_label": "Recovery Candidate", "scan_time": "2026-09-03"}],
    )
    assert [card["ticker"] for card in story["cards"]] == ["AAA"]
    recovery = story["recovery_cards"][0]
    assert recovery["ticker"] == "MU"
    assert recovery["production_rank"] is None
    assert recovery["snapshot_membership"] == "CURRENT_RECOVERY_ONLY"
    assert recovery["recovery"]["source_artifact"] == "recovery_scan.json"


def test_current_candidates_retain_one_snapshot_identity_and_artifact_rank():
    story = build_home_guidance_story(
        [row("AAA"), row("BBB")], [], scan_timestamp="2026-09-03T01:00:00+00:00",
    )
    assert story["production_source_artifact"] == "market_full_scan.json"
    assert story["production_snapshot_id"]
    for rank, card in enumerate(story["cards"], 1):
        assert card["production_rank"] == rank
        assert card["production_snapshot_id"] == story["production_snapshot_id"]
        assert card["production_snapshot_timestamp"] == story["scan_timestamp"]
        assert card["production_source_artifact"] == "market_full_scan.json"
        assert card["snapshot_membership"] == "CURRENT_FULL_SCAN"


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
        "last_known_price", "technical_evidence", "volume_evidence",
        "fundamentals_evidence", "snapshot_evidence_health",
    }


def test_snapshot_evidence_never_promotes_raw_indicators_or_price_to_canonical_states():
    card = build_home_guidance_candidate(
        row("MU", current_price=0, rsi=0, sma20=95, sma50=110, sma200=120,
            volume_ratio=0, avg_volume_20d=0, dollar_volume=-1),
        production_rank=1, current_evaluation=canonical_evaluation(),
    )
    assert card["last_known_price"] == 0
    assert card["last_known_price_label"] == "Persisted / last-known price"
    assert card["technical_state"] == "UNAVAILABLE"
    assert card["technical_status"] == "DATA_UNAVAILABLE"
    assert card["technical_evidence"] == {
        "price": 0.0, "rsi": 0.0, "sma20": 95.0, "sma50": 110.0,
        "sma200": 120.0, "support": None, "resistance": None,
        "breakout_setup": None,
    }
    assert card["volume_state"] == "UNAVAILABLE"
    assert card["volume_status"] == "DATA_UNAVAILABLE"
    assert card["volume_evidence"]["relative_volume"] == 0
    assert card["volume_evidence"]["average_volume"] == 0
    assert card["volume_evidence"]["average_dollar_volume"] == -1


def test_snapshot_authorities_remain_separate_and_missing_stays_missing():
    card = build_home_guidance_candidate(
        row("MU", price=80, analyst_target_mean=125, expected_upside_pct=107.8,
            atlas_valuation_status="REJECTED_EXTREME_UPSIDE"),
        production_rank=1, current_evaluation=canonical_evaluation(fv=None, expected=107.8),
    )
    assert card["last_known_price"] == 80
    assert card["wall_street"]["mean_target"] == 125
    assert card["atlas_fair_value"] is None
    assert card["atlas_expected_return"] is None
    assert card["technical_evidence"]["rsi"] is None
    assert card["volume_evidence"]["relative_volume"] is None


def test_renderer_uses_summary_first_evidence_then_full_detail_after_cta():
    source = '''
import streamlit as st
from engines.home_guidance_story_v1 import build_home_guidance_story
from ui.home_guidance_vnext import render_home_guidance_vnext
rows = [{"ticker":"MU","company":"Micron","price":80,"conviction":97,"rsi":55,"sma20":75,"volume_ratio":1.2,"avg_volume_20d":1000000,"dollar_volume":80000000,"forward_eps":5,"forward_eps_source":"CANONICAL_ESTIMATE","revenue_growth":10,"revenue_growth_source":"CANONICAL_FINANCIALS","revenue_growth_horizon":"TTM","operating_profit_margin":.2,"risk_reward":1.8,"entry_low":75,"entry_high":82,"stop_loss":70,"target_1":100,"analyst_target_mean":115}]
render_home_guidance_vnext(build_home_guidance_story(rows, [{"ticker":"MU","recovery_score":69}]), emit_interactive=lambda: None)
'''
    app = AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    rendered = "\n".join(str(item.value) for item in app.markdown)
    assert 'data-atlas-qa="home-guidance-full-evidence"' in rendered
    assert "Technical State:</b> Unavailable" in rendered
    assert "Technical Evidence:</b> RSI 55.0" in rendered
    assert "Volume State:</b> Unavailable" in rendered
    assert "Volume Evidence:</b> Relative volume 1.2×" in rendered
    assert "What ATLAS knows" in rendered
    assert "What ATLAS needs" in rendered
    assert 'data-atlas-qa="home-guidance-summary"' in rendered
    assert rendered.index("home-guidance-quick-evidence") < rendered.index("home-guidance-research-cta")
    assert rendered.index("home-guidance-research-cta") < rendered.index("home-guidance-full-evidence")
    assert "Full Evidence" in "\n".join(str(item.label) for item in app.expander)


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


def test_current_artifact_membership_and_archetypes_are_resolved_dynamically(monkeypatch):
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "false")
    payload = json.loads((ROOT / "market_full_scan.json").read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("data") or []
    recovery_payload = json.loads((ROOT / "recovery_scan.json").read_text(encoding="utf-8"))
    story = build_home_guidance_story(rows, recovery_payload)
    assert story["cards"][0]["ticker"] == str(rows[0].get("ticker") or rows[0].get("symbol")).upper()
    assert story["cards"][0]["production_rank"] == 1
    assert {card["ticker"] for card in story["cards"]} == {
        str(item.get("ticker") or item.get("symbol")).upper() for item in rows
    }
    assert any(card["atlas_fair_value"] is not None for card in story["cards"])
    assert any(card["atlas_fair_value"] is None for card in story["cards"])
    assert any(card["snapshot_evidence_health"] in {"Low", "Medium", "PARTIAL", "Partial"} for card in story["cards"])


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
    assert 'data-atlas-qa="home-guidance-quick-evidence"' in rendered
    assert "Full Evidence" in "\n".join(str(item.label) for item in app.expander)
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


def test_compact_card_css_preserves_three_and_four_column_strips():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert ".atlas-home-guidance-core" in source
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in source
    assert ".atlas-home-guidance-status" in source
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in source
    assert '.stButton>button[kind="primary"]' in source
    assert ".atlas-home-guidance-unavailable b" in source
    assert ".atlas-home-guidance-status .atlas-home-guidance-metric:nth-child(2)" in source
    assert ".atlas-home-guidance-status .atlas-home-guidance-metric:nth-child(3)" in source


def test_unavailable_metrics_are_subdued_without_remapping_values():
    from ui.home_guidance_vnext import _metric

    unavailable = _metric("Opportunity", "Unavailable")
    available = _metric("Scan Conviction", "0.0%")
    assert "atlas-home-guidance-unavailable" in unavailable
    assert "atlas-home-guidance-unavailable" not in available
    assert ">0.0%</b>" in available


def test_dynamic_card_sections_remain_in_normal_document_flow():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert '[data-testid="stMarkdownContainer"]{margin-bottom:0!important}' in source
    assert "position:absolute" not in source
    assert "translateY(" not in source
    assert "overflow:hidden" not in source
    assert "margin-top:-" not in source
    assert "margin-bottom:-" not in source
    assert ".atlas-home-guidance-primary{min-height:" not in source
    assert ".atlas-home-guidance-core{min-height:" not in source
    assert ".atlas-home-guidance-status{min-height:" not in source
    assert ".atlas-home-guidance-limited{min-height:" not in source
    assert 'details summary{height:' not in source


def test_home_typography_keeps_supporting_evidence_readable():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert ".atlas-home-guidance-core .atlas-home-guidance-metric b{font-size:1.15rem" in source
    assert ".atlas-home-guidance-metric small{font-size:.82rem" in source
    assert ".atlas-home-full-evidence h4{margin:0 0 .4rem;font-size:1rem" in source
    assert ".atlas-home-full-evidence p{margin:.22rem 0;font-size:.875rem;line-height:1.48" in source
    assert ".atlas-home-guidance-limited code{font-size:.78rem" in source
    assert ".atlas-home-full-evidence p,.atlas-home-full-reasons li{font-size:.825rem;line-height:1.45}" in source
    assert ".atlas-home-guidance-limited small{font-size:.8125rem;line-height:1.4}" in source


def test_summary_card_omits_unavailable_secondary_metrics_until_full_evidence():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    card_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_card")
    body = ast.get_source_segment(source, card_fn) or ""
    summary, full = body.split('with st.expander("Full Evidence"', 1)
    assert '_metric("Opportunity"' not in summary
    assert '_metric("Decision Confidence"' not in summary
    assert '_metric("Scan Conviction"' in summary
    assert '_metric("Atlas FV"' in summary
    assert '_metric("Wall Street Target"' in summary
    assert "_full_evidence(card)" in full
    full_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_full_evidence")
    full_body = ast.get_source_segment(source, full_fn) or ""
    assert '_metric("Opportunity"' in full_body
    assert '_metric("Decision Confidence"' in full_body


def test_data_limited_summary_is_bounded_and_reason_grounded():
    from ui.home_guidance_vnext import _atlas_summary, _quick_needs

    card = {
        "guidance": "DATA_LIMITED",
        "what_changes_guidance": (
            "Fresh market evidence is required.",
            "Canonical technical confirmation is required.",
            "Canonical volume confirmation is required.",
            "A fourth item must not appear.",
        ),
    }
    assert _quick_needs(card) == (
        "Fresh market evidence",
        "Canonical technical confirmation",
        "Canonical volume confirmation",
    )
    assert _atlas_summary(card) == (
        "ATLAS has useful snapshot evidence, but fresh market evidence and "
        "canonical technical confirmation are still required."
    )


def test_quick_evidence_is_four_items_and_trade_plan_stays_in_full_evidence():
    from ui.home_guidance_vnext import _quick_known

    card = {
        "technical_evidence": {"price": 100, "rsi": 50.9, "sma20": 90, "sma50": 80, "sma200": 70},
        "volume_evidence": {"relative_volume": .8},
        "recovery": {"score": 69},
        "trade_plan": {"entry_low": 95, "entry_high": 100, "stop": 90, "target_1": 120},
    }
    assert _quick_known(card) == (
        "RSI 50.9",
        "Above SMA20 / SMA50 / SMA200",
        "Relative volume 0.8×",
        "Recovery Score 69.0",
    )
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert 'data-atlas-trade-segment="entry"' in source
    assert 'data-atlas-trade-segment="stop"' in source
    assert 'data-atlas-trade-segment="target"' in source
    assert 'margin-left:auto' not in source


def test_full_evidence_has_one_semantic_hierarchy_and_protected_trade_segments():
    from ui.home_guidance_vnext import _full_evidence

    rendered = _full_evidence({
        "opportunity": None,
        "decision_confidence": None,
        "evidence_health": "PARTIAL",
        "trade_plan": {"entry_low": 932.81, "entry_high": 967.72, "stop": 890.91, "target_1": 1073.39},
    })
    headings = ("Decision Evidence", "Valuation", "Technical &amp; Volume", "External Context", "Trade Plan", "Why ATLAS / What Changes Guidance")
    assert all(heading in rendered for heading in headings)
    assert rendered.index("Decision Evidence") < rendered.index("Valuation") < rendered.index("Technical &amp; Volume")
    assert '<span data-atlas-trade-segment="entry"><b>Entry</b> $932.81–$967.72</span>' in rendered
    assert '<span data-atlas-trade-segment="stop"><b>Stop</b> $890.91</span>' in rendered
    assert '<span data-atlas-trade-segment="target"><b>Target</b> $1,073.39</span>' in rendered
    assert "Trade-plan evidence" not in rendered


def test_full_evidence_css_preserves_natural_flow_and_wrapping():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert ".atlas-home-full-evidence{display:block" in source
    assert ".atlas-home-trade-row{display:flex;flex-wrap:wrap" in source
    assert ".atlas-home-trade-row span{white-space:nowrap}" in source
    assert '.atlas-home-trade-row span+span::before{content:"·"' in source
    assert ".atlas-home-full-metrics{grid-template-columns:1fr" in source
