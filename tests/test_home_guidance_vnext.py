from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from engines.home_guidance_story_v1 import HOME_FIELD_AUTHORITY, build_home_guidance_candidate, build_home_guidance_story
from services.on_demand_evaluation_service import evaluate_on_demand


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
        "analyst_targets_commercial_display_allowed": True,
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


@pytest.mark.parametrize(("guidance", "label", "stars"), [
    ("BUY_NOW", "BUY NOW", "★★★★★"),
    ("ACCUMULATE", "BUILD A POSITION", "★★★★½"),
    ("WAIT_FOR_ENTRY", "WAIT FOR A BETTER ENTRY", "★★★★☆"),
    ("WAIT_FOR_CONFIRMATION", "WAIT FOR CONFIRMATION", "★★★½☆"),
    ("DATA_LIMITED", "WATCH — NOT READY YET", "★★½☆☆"),
    ("AVOID", "AVOID", "★☆☆☆☆"),
])
def test_canonical_guidance_maps_to_customer_action_without_mutating_guidance(guidance, label, stars):
    card = build_home_guidance_candidate(row("MU"), production_rank=1, current_evaluation=canonical_evaluation(guidance=guidance))
    assert card["guidance"] == guidance
    assert card["customer_action"]["label"] == label
    assert card["customer_action"]["stars"] == stars


def test_wall_street_and_catalysts_fail_closed_without_commercial_display_rights():
    source = row("MU", analyst_targets_commercial_display_allowed=False, analyst_target_mean=150)
    source["recent_catalysts"] = [{"headline": "Material event", "evidence_id": "NEWS-1"}]
    card = build_home_guidance_candidate(source, production_rank=1, current_evaluation=canonical_evaluation())
    assert card["wall_street"]["mean_target"] is None
    assert card["wall_street"]["commercial_display_status"] == "COMMERCIAL_LICENSE_UNCONFIRMED"
    assert card["recent_catalysts"] == ()


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
    assert "ATLAS Investment View" in rendered
    assert "What ATLAS sees" not in rendered
    assert "What ATLAS needs" not in rendered
    assert 'data-atlas-qa="home-guidance-summary"' in rendered
    assert rendered.index("home-decisive-reason") < rendered.index("home-guidance-research-cta")
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


def test_live_price_and_provenance_are_separate_from_persisted_last_known_price():
    evaluation = canonical_evaluation(guidance="WAIT_FOR_CONFIRMATION")
    evaluation["market_snapshot"] = {
        "price": 105, "fresh_current_price": True, "customer_label": "Current quote",
        "provider": "TWELVE_DATA", "source_type": "TWELVE_DATA_WEBSOCKET",
        "provider_timestamp": "2026-09-04T15:00:00+00:00",
        "received_timestamp": "2026-09-04T15:00:01+00:00", "freshness_age_seconds": 1,
        "feed_health": "HEALTHY", "evidence_id": "TD1-example",
        "source_methodology_version": "TWELVE_DATA_PHASE1_ADAPTER_V1",
    }
    card = build_home_guidance_candidate(row("NVDA", price=100), production_rank=1, current_evaluation=evaluation)
    assert card["current_price"] == 105
    assert card["display_price"] == 105
    assert card["display_price_label"] == "Current Price"
    assert card["last_known_price"] == 100
    assert card["market_evidence"]["status"] == "LIVE"
    assert card["market_evidence"]["evidence_id"] == "TD1-example"


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
    assert 'data-atlas-section="technical-opportunities"' not in rendered
    assert "Recovery Score" not in rendered
    assert "Guidance Preview" not in rendered
    assert rendered.count('data-atlas-page-interactive="true"') == 1
    assert 'data-atlas-qa="home-guidance-quick-evidence"' not in rendered
    assert "Full Evidence" in "\n".join(str(item.label) for item in app.expander)
    assert "Founder Guidance Preview" not in rendered
    assert "ATLAS Decision Dashboard" in rendered
    assert "High-conviction setups, current stance, and the evidence that matters." in rendered


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
    assert 'View Full Investment Case — {ticker}' in source


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
    assert "_atlas_score(card)" not in summary
    assert "_action_card(card)" in summary
    assert 'data-atlas-score-source="SCAN_CONVICTION"' in (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert "_key_numbers(card)" not in summary
    assert "_target_tiles(card)" in summary
    assert 'data-atlas-qa="home-evidence-status"' not in summary
    assert '_metric("Atlas FV"' not in summary
    assert '_metric("Wall Street Target"' not in summary
    assert "_full_evidence(card)" in full
    full_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_full_evidence")
    full_body = ast.get_source_segment(source, full_fn) or ""
    assert '_metric("Opportunity"' in full_body
    assert '_metric("Decision Confidence"' in full_body


def test_data_limited_summary_is_bounded_and_reason_grounded():
    from ui.home_guidance_vnext import _atlas_summary, _quick_needs

    card = {
        "guidance": "DATA_LIMITED",
        "technical_evidence": {"price": 100, "rsi": 50.9, "sma20": 90, "sma50": 80, "sma200": 70},
        "volume_evidence": {"relative_volume": .8},
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
    summary = _atlas_summary(card)
    assert summary.count(". ") <= 2
    assert "developing technical opportunity" in summary
    assert "watch — not ready yet" in summary.lower()
    assert "Data Limited" not in summary


@pytest.mark.parametrize(("value", "band", "tone", "stars"), [
    (100, "Exceptional", "exceptional", "★★★★★"),
    (90, "Exceptional", "exceptional", "★★★★★"),
    (89, "Strong", "strong", "★★★★☆"),
    (80, "Strong", "strong", "★★★★☆"),
    (79, "Constructive", "constructive", "★★★☆☆"),
    (70, "Constructive", "constructive", "★★★☆☆"),
    (69, "Developing", "developing", "★★☆☆☆"),
    (60, "Developing", "developing", "★★☆☆☆"),
    (59, "Weak", "weak", "★☆☆☆☆"),
])
def test_atlas_score_band_and_stars_are_display_only(value, band, tone, stars):
    from ui.home_guidance_vnext import _atlas_score_presentation

    result = _atlas_score_presentation(value)
    assert result["display"] == f"{value} / 100"
    assert result["band"] == band
    assert result["tone"] == tone
    assert result["stars"] == stars
    assert result["star_fill_percent"] == value


def test_atlas_score_preserves_real_decimal_precision_without_inventing_it():
    from ui.home_guidance_vnext import _atlas_score_presentation

    assert _atlas_score_presentation(97)["display"] == "97 / 100"
    assert _atlas_score_presentation(97.36)["display"] == "97.4 / 100"
    assert _atlas_score_presentation(97.36)["star_fill_percent"] == 97.36


def test_atlas_score_is_scan_conviction_alias_without_guidance_or_actionability_remap():
    from ui.home_guidance_vnext import _atlas_score

    card = {
        "scan_conviction": 97, "guidance": "DATA_LIMITED",
        "actionability": "UNAVAILABLE", "opportunity": 12,
    }
    rendered = _atlas_score(card)
    assert 'data-atlas-score-source="SCAN_CONVICTION"' in rendered
    assert 'data-atlas-score-value="97"' in rendered
    assert 'data-atlas-score-band="Exceptional"' in rendered
    assert 'data-atlas-display-only="true"' in rendered
    assert "ATLAS Setup Score" in rendered
    assert "97 / 100" in rendered
    assert "Exceptional Setup" in rendered
    assert "Exceptional setup quality, but not yet actionable." in rendered
    assert "DATA_LIMITED" not in rendered
    assert "UNAVAILABLE" not in rendered
    assert "12" not in rendered


def test_home_primary_uses_action_rating_and_keeps_setup_score_out_of_first_view():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    card_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_card")
    body = ast.get_source_segment(source, card_fn) or ""
    assert "_atlas_score(card)" not in body
    assert body.index("_action_card(card)") < body.index("Price Chart")
    assert body.index("Price Outlook") < body.index("ATLAS Investment View")
    assert "_key_numbers(card)" not in body
    assert "_decisive_reason(card)" in body
    assert '_metric("Atlas FV"' not in body
    assert '_metric("Wall Street Target"' not in body
    assert 'data-atlas-scan-conviction=' in body


def test_live_market_badge_never_calls_stale_or_missing_evidence_live():
    from ui.home_guidance_vnext import _market_evidence_badge

    live = _market_evidence_badge({"market_evidence": {
        "status": "LIVE", "source_type": "TWELVE_DATA_WEBSOCKET", "freshness_age_seconds": 3,
    }})
    stale = _market_evidence_badge({"market_evidence": {"status": "STALE"}})
    missing = _market_evidence_badge({"market_evidence": {"status": "UNAVAILABLE"}})
    assert ">LIVE<" in live and "Updated 3.0 seconds ago" in live
    assert ">STALE<" in stale and ">LIVE<" not in stale
    assert "PRICE UNAVAILABLE" in missing and ">LIVE<" not in missing


def test_completed_after_hours_bar_is_last_known_and_never_labeled_live():
    from ui.home_guidance_vnext import _market_evidence_badge

    badge = _market_evidence_badge({"market_evidence": {
        "status": "LAST_KNOWN", "market_session": "AFTER_HOURS",
        "provider_timestamp": "2026-09-04T23:59:00+00:00",
        "source_type": "TWELVE_DATA_LATEST_COMPLETED_BAR", "stale": True,
    }})
    assert ">LAST KNOWN<" in badge
    assert "After Hours" in badge
    assert "Sep 4, 7:59 PM ET" in badge
    assert "2026-09-04T23:59:00+00:00" not in badge
    assert "Last known" in badge
    assert ">LIVE<" not in badge


def test_summary_leads_with_freshest_approved_last_known_bar_without_calling_it_live():
    from ui.home_guidance_vnext import _atlas_summary

    card = {
        "ticker": "NVDA", "production_rank": 2, "scan_conviction": 97,
        "guidance": "DATA_LIMITED", "display_price": 229.5,
        "display_price_label": "Latest completed after-hours bar",
        "market_evidence": {"source_type": "TWELVE_DATA_LATEST_COMPLETED_BAR"},
        "technical_evidence": {"price": 220, "sma20": 210, "sma50": 200, "sma200": 190},
        "volume_evidence": {}, "recovery": {},
        "atlas_valuation_status": "REJECTED_EXTREME_UPSIDE",
        "reason_codes": ("CURRENT_MARKET_EVIDENCE_UNAVAILABLE", "TECHNICAL_STRUCTURE_UNAVAILABLE"),
    }
    summary = _atlas_summary(card)
    assert summary.startswith("NVDA offers a developing technical opportunity")
    assert "97" not in summary and "DATA_LIMITED" not in summary
    assert "live" not in summary.lower()


def test_home_card_preserves_completed_bar_and_entry_relationship_as_presentation_evidence():
    evaluation = evaluate_on_demand(row("MU", 97))
    evaluation["phase1_completed_bar"] = {
        "timestamp": "2026-09-04T23:59:00+00:00", "open": 100, "high": 102,
        "low": 99, "close": 101, "volume": 1000, "session": "AFTER_HOURS", "completed": True,
    }
    evaluation["phase1_bar_quality"] = {"status": "AVAILABLE", "evidence_id": "TD1-test"}
    card = build_home_guidance_story([row("MU", 97)], [], current_evaluations={"MU": evaluation})["cards"][0]
    assert card["latest_completed_bar"]["close"] == 101
    assert card["completed_bar_quality"]["evidence_id"] == "TD1-test"
    assert card["entry_relationship"] in {"WITHIN_ENTRY_RANGE", "BELOW_ENTRY_RANGE", "ABOVE_ENTRY_RANGE", "DATA_UNAVAILABLE"}


def _bcrx_customer_card():
    return {
        "ticker": "BCRX", "company": "BioCryst Pharmaceuticals, Inc.",
        "production_rank": 4, "scan_conviction": 97,
        "display_price": 10.02, "display_price_label": "Latest completed after-hours bar",
        "market_evidence": {
            "status": "LAST_KNOWN", "market_session": "AFTER_HOURS",
            "provider_timestamp": "2026-09-04T23:30:00+00:00",
            "source_type": "TWELVE_DATA_LATEST_COMPLETED_BAR",
        },
        "completed_bar_quality": {
            "status": "DEGRADED", "reason_codes": ("REGULAR_SESSION_GAPS_PRESENT",),
        },
        "guidance": "DATA_LIMITED", "guidance_status": "DATA_UNAVAILABLE",
        "actionability": "UNAVAILABLE", "evidence_health": "PARTIAL",
        "reason_codes": ("CURRENT_MARKET_EVIDENCE_UNAVAILABLE", "TECHNICAL_STRUCTURE_UNAVAILABLE"),
        "technical_state": "UNAVAILABLE", "technical_status": "DATA_UNAVAILABLE",
        "technical_evidence": {
            "price": 9.99, "rsi": 51.2, "sma20": 9.91, "sma50": 9.75,
            "sma200": 8.57, "resistance": 10.68,
        },
        "volume_state": "UNAVAILABLE", "volume_status": "DATA_UNAVAILABLE",
        "volume_evidence": {"relative_volume": .08},
        "recovery": {"score": 69, "state": "Recovery Watchlist"},
        "trade_plan": {"entry_low": 9.83, "entry_high": 10.07, "stop": 9.54, "target_1": 10.8, "target_2": 11.2},
        "entry_relationship": "WITHIN_ENTRY_RANGE",
        "atlas_fair_value": None, "atlas_valuation_status": "REJECTED_EXTREME_UPSIDE",
        "opportunity": None, "decision_confidence": None,
    }


def test_bcrx_customer_hierarchy_is_grounded_and_keeps_governed_status():
    from ui.home_guidance_vnext import _atlas_summary, _guidance_explanation, _what_changes_call

    card = _bcrx_customer_card()
    assert card["guidance"] == "DATA_LIMITED"
    assert card["actionability"] == "UNAVAILABLE"
    summary = _atlas_summary(card)
    assert summary.startswith("BCRX offers a developing technical opportunity")
    assert "watch — not ready yet" in summary.lower()
    assert "97" not in summary and "Data Limited" not in summary
    assert _guidance_explanation(card) == "The opportunity is worth watching, but ATLAS needs fresher market evidence before recommending a position."
    assert _what_changes_call(card) == (
        "Guidance can advance only after fresh exact-symbol current-price authority and canonical technical state are available; "
        "remaining confirmation gates would then be evaluated normally."
    )


def test_bcrx_key_numbers_are_populated_only_and_authority_separation_is_explicit():
    from ui.home_guidance_vnext import _key_numbers, _market_evidence_badge, _quick_known, _quick_needs

    card = _bcrx_customer_card()
    numbers = _key_numbers(card)
    for expected in ("$10.02", "$9.83–$10.07", "51.2", "69.0", "0.08×", "$10.68", "$9.54 / $10.80"):
        assert expected in numbers
    assert "Atlas FV" not in numbers
    assert "Opportunity" not in numbers
    assert "Decision Confidence" not in numbers
    assert _quick_needs(card) == ("Fresh exact-symbol current-price authority", "Canonical technical state")
    assert len(_quick_known(card)) == 4
    assert "Persisted price structure" in _quick_known(card)[1]
    assert "Persisted contextual relative volume is 0.08×" in _quick_known(card)
    badge = _market_evidence_badge(card)
    assert ">LAST KNOWN<" in badge
    assert "Limited bar continuity" not in badge
    assert card["technical_state"] == "UNAVAILABLE"
    assert card["volume_state"] == "UNAVAILABLE"


def test_mobile_customer_hierarchy_suppresses_diagnostic_matrix_and_evidence_status():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert ".atlas-home-key-numbers{grid-template-columns:repeat(2,minmax(0,1fr))" in source
    assert ".atlas-home-evidence-status{display:inline-flex" in source
    card_body = source[source.index("def _card("):source.index("def _section_marker")]
    assert card_body.index("_action_card(card)") < card_body.index("ATLAS Investment View")
    assert "home-evidence-status" not in card_body
    assert "_key_numbers(card)" not in card_body
    assert card_body.index("Price Chart") < card_body.index("ATLAS Investment View")


def test_premium_decision_card_uses_governed_action_chart_and_separate_target_authorities():
    from ui.home_guidance_vnext import _action_card, _mini_chart, _target_tiles

    card = {
        "guidance": "WAIT_FOR_CONFIRMATION", "guidance_status": "AVAILABLE",
        "customer_action": {"label": "WAIT FOR CONFIRMATION", "stars": "★★★½☆", "rating": 3.5, "tone": "wait"},
        "technical_state": "NEAR_BREAKOUT", "reason_codes": ("VOLUME_CONFIRMATION_UNAVAILABLE",),
        "atlas_valuation_status": "PUBLISHED", "atlas_fair_value": 120,
        "atlas_expected_return": 20, "wall_street": {"mean_target": 115, "implied_upside": 15},
        "home_chart": {
            "status": "AVAILABLE", "provider": "TWELVE_DATA", "range": "3M", "interval": "1day",
            "adjustment_mode": "splits", "newest_completed_bar_timestamp": "2026-09-04T20:00:00+00:00",
            "evidence_id": "TD-test", "bars": ({"close": 100}, {"close": 105}),
        },
    }
    action = _action_card(card)
    assert "WAIT FOR CONFIRMATION" in action and 'data-atlas-action-tone="wait"' in action
    pending = _action_card({**card, "guidance": "DATA_LIMITED", "customer_action": {"label": "WATCH — NOT READY YET", "stars": "★★½☆☆", "rating": 2.5, "tone": "watch"}})
    assert "WATCH — NOT READY YET" in pending and "DATA_LIMITED" not in pending
    chart = _mini_chart(card)
    assert "Near breakout" in chart and "Twelve Data" in chart and "split-adjusted daily bars" in chart
    comparison = _target_tiles(card)
    assert "$120.00" in comparison and "$115.00" in comparison
    assert "does not determine the ATLAS rating" in comparison


def test_quick_evidence_is_four_items_and_trade_plan_stays_in_full_evidence():
    from ui.home_guidance_vnext import _quick_known

    card = {
        "technical_evidence": {"price": 100, "rsi": 50.9, "sma20": 90, "sma50": 80, "sma200": 70},
        "volume_evidence": {"relative_volume": .8},
        "recovery": {"score": 69},
        "trade_plan": {"entry_low": 95, "entry_high": 100, "stop": 90, "target_1": 120},
    }
    assert _quick_known(card) == (
        "Persisted price structure is above SMA20 / SMA50 / SMA200",
        "Recovery Score is 69.0",
        "Persisted contextual relative volume is 0.8×",
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
