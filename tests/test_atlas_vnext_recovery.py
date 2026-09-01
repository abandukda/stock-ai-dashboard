from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from engines.recovery_decision_story import (
    ESTIMATE_ACCUMULATION_MESSAGE,
    RECOVERY_DECISION_STORY_VERSION,
    build_recovery_decision_story,
)
from ui.recovery_vnext import RECOVERY_VNEXT_SECTIONS, RECOVERY_VNEXT_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _row(**overrides):
    row = {
        "ticker": "RCV", "company": "Recovery Corp",
        "recovery_score": 78, "recovery_label": "Strong Recovery Candidate",
        "twenty_day_pct": -9, "sixty_day_pct": -18, "rsi": 41,
        "recovery_rebound_reason": "Analyst support improved; Price stabilized near support",
        "recovery_risk": "Revenue evidence remains mixed.",
        "analyst_support_score": 70, "news_sentiment_score": 35,
        "revenue_growth": .12, "earnings_growth": .08, "volume_ratio": 1.4,
        "current_price": 50, "Recommendation": "BUY NOW", "Opportunity": 81,
        "Confidence": 76, "atlas_fair_value": 65,
        "decision_expected_return_pct": 30, "v42_support_1": 46,
        "preferred_entry_low": 48, "preferred_entry_high": 51, "stop": 44,
        "trade_target_1": 58, "trade_target_2": 65,
        "analyst_target_mean": 61, "analyst_target_low": 48,
        "analyst_target_high": 72, "analyst_count": 12,
    }
    row.update(overrides)
    return row


def test_recovery_vnext_contract_has_twelve_decision_sections():
    assert RECOVERY_DECISION_STORY_VERSION == "RECOVERY_DECISION_STORY_V1"
    assert RECOVERY_VNEXT_VERSION == "ATLAS_RECOVERY_VNEXT_V1"
    assert len(RECOVERY_VNEXT_SECTIONS) == 12
    assert RECOVERY_VNEXT_SECTIONS[0] == "Recovery Snapshot"
    assert RECOVERY_VNEXT_SECTIONS[-1] == "Deep Evidence"


def test_high_evidence_story_preserves_all_protected_outputs():
    row = _row()
    story = build_recovery_decision_story(row)
    decision = story["production_decision"]
    assert story["recovery_snapshot"]["recovery_score"] == row["recovery_score"]
    assert story["recovery_snapshot"]["recovery_label"] == row["recovery_label"]
    assert decision["recommendation"] == "BUY NOW"
    assert decision["opportunity"] == 81
    assert decision["confidence"] == 76
    assert decision["atlas_fair_value"] == 65
    assert decision["decision_expected_return"] == 30
    assert decision["entry_low"] == 48 and decision["stop"] == 44


def test_partial_evidence_never_invents_decline_cause_or_catalyst():
    story = build_recovery_decision_story(_row(
        recovery_score=48, recovery_label="Early Recovery Setup",
        recovery_drop_reason=None, recovery_rebound_reason=None,
        analyst_support_score=None, news_sentiment_score=None,
        revenue_growth=None, earnings_growth=None, volume_ratio=None,
    ))
    decline = story["decline_evidence"]
    assert decline["causal_status"] == "PRICE_PRESSURE_NOT_CAUSAL_ATTRIBUTION"
    assert "Price pressure" in decline["summary"]
    assert story["recovery_evidence"]["confirmed"] == []
    assert story["recovery_evidence"]["missing_confirmation"]
    assert story["catalysts"] == []


def test_phase1_evidence_is_contextual_and_estimate_history_stays_honest():
    families = {
        "transcript_intelligence": {"semantic_status": "AVAILABLE", "data": {
            "management_themes": ["Demand stabilized"],
            "supported_risks": ["Debt remains elevated"],
            "monitoring_items": ["Monitor renewal rates"],
        }, "evidence_ids": ["transcript-1"]},
        "analyst_price_target_actions": {"semantic_status": "AVAILABLE", "data": {
            "actions": [{"firm_or_publisher": "Firm", "price_target": 60}]
        }, "evidence_ids": ["target-1"]},
        "insider_transactions": {"semantic_status": "AVAILABLE", "data": {
            "transactions": [{"transaction_type": "Acquisition"}]
        }, "evidence_ids": ["insider-1"]},
    }
    story = build_recovery_decision_story(_row(), evidence_families=families)
    context = story["management_analyst_context"]
    assert context["transcript"]["management_themes"] == ["Demand stabilized"]
    assert context["target_actions"][0]["price_target"] == 60
    assert context["estimate_history_status"] == ESTIMATE_ACCUMULATION_MESSAGE
    assert story["deep_evidence"]["insider_transactions"]
    assert "contextual and non-scoring" in " ".join(story["provenance"]["limitations"]).lower()


def test_etf_corporate_evidence_is_not_applicable():
    story = build_recovery_decision_story(_row(security_type="ETF"))
    assert story["security_type"] == "ETF"
    assert story["management_analyst_context"]["transcript"]["semantic_status"] == "NOT_APPLICABLE"
    assert story["management_analyst_context"]["estimate_history_status"] == "NOT_APPLICABLE"


def test_final_active_app_route_uses_recovery_vnext_only():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    final_main = source[source.rfind("def main():"):]
    recovery_branch = final_main.split('elif selected_page=="Recovery":', 1)[1].split(
        'elif selected_page=="ETFs":', 1
    )[0]
    assert "render_recovery_vnext(recovery_df, open_research=v784_open_research)" in recovery_branch
    assert "render_v56_ranked_table" not in recovery_branch


def test_real_streamlit_surface_emits_contract_and_no_exception():
    script = f'''\
import pandas as pd
import ui.recovery_vnext as page
page.load_cached_phase1_families = lambda *args, **kwargs: {{}}
row = {repr(_row())}
page.render_recovery_vnext(pd.DataFrame([row]), open_research=lambda ticker: None)
'''
    at = AppTest.from_string(script, default_timeout=10).run()
    assert not at.exception
    markdown = "\n".join(item.value for item in at.markdown)
    assert 'data-atlas-recovery-version="ATLAS_RECOVERY_VNEXT_V1"' in markdown
    assert markdown.count("data-atlas-recovery-section=") == 12
    assert any(button.label == "View Investment Case — RCV" for button in at.button)


def test_recovery_builder_has_no_provider_or_scanner_dependencies():
    source = (ROOT / "engines" / "recovery_decision_story.py").read_text(encoding="utf-8")
    assert "overnight_market_scan" not in source
    assert "FMPStableClient" not in source
    assert "requests." not in source
    assert "build_recovery_case" not in source
