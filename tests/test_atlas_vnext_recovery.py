from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from engines.recovery_decision_story import (
    ESTIMATE_ACCUMULATION_MESSAGE,
    RECOVERY_DECISION_STORY_VERSION,
    build_recovery_decision_story,
)
from ui.recovery_vnext import (
    RECOVERY_VNEXT_SECTIONS, RECOVERY_VNEXT_VERSION,
    _deep_mapping_rows, _growth_pct, _literal_currency_markdown,
)


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


def test_currency_ranges_are_markdown_safe_without_changing_values():
    original = "$120 - $145"
    assert _literal_currency_markdown(original) == r"\$120 - \$145"
    assert original == "$120 - $145"
    source = (ROOT / "ui" / "recovery_vnext.py").read_text(encoding="utf-8")
    assert "st.markdown(_literal_currency_markdown(" in source
    assert "st.caption(_literal_currency_markdown(target_range))" in source
    assert "st.caption(_literal_currency_markdown(trade_boundary))" in source


def test_deep_financial_evidence_is_human_readable_and_preserves_zero():
    rows = _deep_mapping_rows("financials", {
        "revenue_growth": 98.602,
        "operating_margin": 0,
        "free_cash_flow": 0,
        "internal_unknown_object": {"raw": "not customer-facing"},
    })
    assert {row["Evidence"] for row in rows} == {"Revenue growth", "Operating margin", "Free cash flow"}
    assert next(row["Value"] for row in rows if row["Evidence"] == "Revenue growth") == "+9,860.2%"
    assert next(row["Value"] for row in rows if row["Evidence"] == "Operating margin") == "0.0%"
    assert next(row["Value"] for row in rows if row["Evidence"] == "Free cash flow") == "$0.00"
    assert _growth_pct(98.602) == "+9,860.2%"
    source = (ROOT / "ui" / "recovery_vnext.py").read_text(encoding="utf-8")
    assert "st.json(value)" not in source


def test_recovery_mobile_css_compacts_only_recovery_route_and_keeps_host_safety():
    source = (ROOT / "ui" / "recovery_vnext.py").read_text(encoding="utf-8")
    assert "body:has([data-atlas-recovery-version])" in source
    assert "@media (max-width:480px)" in source
    assert "margin-top:.35rem !important" in source
    assert ".atlas-recovery-section-title { margin:.35rem 0 .2rem !important" in source
    assert ".atlas-recovery-section-recovery-snapshot" in source
    assert "font-size:1rem !important" in source
    assert ".atlas-recovery-metric:first-child { grid-column:1 / -1; }" in source
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in source
    assert "overflow-x:hidden" in source
    assert "margin-right:5.25rem" in source


def test_recovery_mobile_snapshot_prioritizes_primary_state_and_cta_before_secondary_metrics():
    source = (ROOT / "ui" / "recovery_vnext.py").read_text(encoding="utf-8")
    snapshot = source.split("def _render_snapshot", 1)[1].split("def _render_phase1_controls", 1)[0]
    assert snapshot.index("st.markdown(f\"## {story['ticker']}") < snapshot.index("primary_metrics =")
    assert snapshot.index("primary_metrics =") < snapshot.index("atlas-recovery-metric-grid")
    assert snapshot.index("atlas-recovery-metric-grid") < snapshot.index("View Investment Case")
    assert snapshot.index("View Investment Case") < snapshot.index("atlas-recovery-secondary-mobile")
    assert snapshot.index("atlas-recovery-secondary-mobile") < snapshot.index("cols = st.columns(3)")
    assert snapshot.index("View Investment Case") < snapshot.index("cols = st.columns(3)")
    assert "atlas-recovery-evidence-inline" in snapshot
    render = source.split("def render_recovery_vnext", 1)[1]
    active_story = render.split("_render_snapshot(story, open_research)", 1)[1]
    assert active_story.index('emit_page_interactive(st, "Recovery")') < active_story.index('_section("Why It Fell")')
