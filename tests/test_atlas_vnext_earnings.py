from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from engines.earnings_decision_story import (
    EARNINGS_DECISION_STORY_VERSION,
    build_earnings_decision_story,
    normalized_earnings_history,
)
from ui.earnings_vnext import EARNINGS_VNEXT_SECTIONS, EARNINGS_VNEXT_VERSION, _stories


ROOT = Path(__file__).resolve().parents[1]


def _row(*, eps_actual=1.2, eps_estimate=1.0, revenue_actual=110.0, revenue_estimate=100.0, recommendation="BUY NOW"):
    return {
        "ticker": "TEST", "company": "Test Corp", "Recommendation": recommendation,
        "Opportunity": 82, "Confidence": 74, "atlas_fair_value": 140,
        "decision_expected_return_pct": 18,
        "earnings_history": [{
            "fiscal_period": "Q2 2026", "report_date": "2026-07-29",
            "eps_actual": eps_actual, "eps_estimate": eps_estimate,
            "revenue_actual": revenue_actual, "revenue_estimate": revenue_estimate,
            "provider": "fixture", "evidence_timestamp": "2026-07-29T20:00:00Z",
        }],
    }


def test_contract_has_nine_decision_sections():
    assert EARNINGS_DECISION_STORY_VERSION == "EARNINGS_DECISION_STORY_V1"
    assert EARNINGS_VNEXT_VERSION == "ATLAS_EARNINGS_VNEXT_V1"
    assert len(EARNINGS_VNEXT_SECTIONS) == 9
    assert EARNINGS_VNEXT_SECTIONS[0] == "Earnings Snapshot"
    assert EARNINGS_VNEXT_SECTIONS[-1] == "Deep Evidence"


def test_full_beat_miss_met_and_mixed_quarters():
    assert build_earnings_decision_story(_row())["event_result"] == "BEAT"
    assert build_earnings_decision_story(_row(eps_actual=.8, revenue_actual=90))["event_result"] == "MISS"
    assert build_earnings_decision_story(_row(eps_actual=1, revenue_actual=100))["event_result"] == "MET"
    assert build_earnings_decision_story(_row(eps_actual=1.2, revenue_actual=90))["event_result"] == "MIXED"


def test_partial_zero_negative_and_missing_evidence_are_safe():
    eps_only = build_earnings_decision_story(_row(revenue_actual=None, revenue_estimate=None))
    assert eps_only["latest_quarter"]["revenue_actual"] is None
    revenue_only = build_earnings_decision_story(_row(eps_actual=None, eps_estimate=None))
    assert revenue_only["latest_quarter"]["eps_actual"] is None
    zero = build_earnings_decision_story(_row(eps_actual=0, eps_estimate=0, revenue_actual=-5, revenue_estimate=-5))
    assert zero["latest_quarter"]["eps_actual"] == 0
    assert zero["latest_quarter"]["revenue_actual"] == -5
    malformed = build_earnings_decision_story({"ticker": "BAD", "earnings_history": [{"eps_actual": [], "revenue_actual": {}}]})
    assert malformed["semantic_status"] == "DATA_UNAVAILABLE"


def test_future_estimate_only_row_is_not_reported_history():
    row = _row()
    row["earnings_history"].insert(0, {"fiscal_period": "Q3 2026", "report_date": "2026-10-29", "eps_estimate": 1.4})
    story = build_earnings_decision_story(row)
    assert len(story["history"]) == 1
    assert story["history"][0]["fiscal_period"] == "Q2 2026"


def test_guidance_transcript_revision_and_reaction_boundaries():
    unavailable = build_earnings_decision_story(_row())
    assert unavailable["management_guidance"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert unavailable["transcript_intelligence"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert unavailable["estimate_revisions_status"] == "DATA_UNAVAILABLE"
    assert unavailable["market_reaction"]["semantic_status"] == "DATA_UNAVAILABLE"
    verified = _row()
    verified["management_guidance"] = {"source": "filing", "date": "2026-07-29", "revenue_guidance": "100-110"}
    verified["transcript_intelligence"] = {"verified_source": "filing", "call_date": "2026-07-29", "management_themes": ["Demand"]}
    story = build_earnings_decision_story(verified)
    assert story["management_guidance"]["semantic_status"] == "AVAILABLE"
    assert story["transcript_intelligence"]["semantic_status"] == "AVAILABLE"


def test_etf_is_not_applicable_and_not_listed_as_corporate_event():
    row = _row()
    row["security_type"] = "ETF"
    story = build_earnings_decision_story(row)
    assert story["semantic_status"] == "NOT_APPLICABLE"
    reported, upcoming = _stories(pd.DataFrame([row]))
    assert reported == [] and upcoming == []


def test_decision_authority_and_field_separation_are_preserved():
    row = _row(recommendation=None)
    row["analyst_target_mean"] = 155
    story = build_earnings_decision_story(row)
    assert story["production_decision"]["recommendation"] is None
    assert story["production_decision"]["semantic_status"] == "AVAILABLE"
    assert story["production_decision"]["opportunity"] == 82
    assert story["production_decision"]["confidence"] == 74
    assert story["production_decision"]["atlas_fair_value"] == 140
    assert story["wall_street_consensus"] == 155


def test_active_final_route_invokes_vnext_and_leaves_legacy_unreachable():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    final_main = source[source.rfind("def main():"):]
    assert 'render_earnings_vnext(full_df, open_research=v784_open_research)' in final_main
    assert 'render_v73_earnings_page(full_df,source_df)' not in final_main
    assert source.count("def render_v73_earnings_page") >= 2


def test_real_streamlit_renderer_exposes_reported_upcoming_and_research_cta():
    harness = r'''
import pandas as pd
from ui.earnings_vnext import render_earnings_vnext
rows = [{
    "ticker": "BEAT", "company": "Beat Corp", "Recommendation": "BUY NOW",
    "Opportunity": 81, "Confidence": 72,
    "earnings_history": [{"fiscal_period": "Q2 2026", "report_date": "2026-07-29", "eps_actual": 1.2, "eps_estimate": 1.0, "revenue_actual": 110, "revenue_estimate": 100}],
    "next_earnings_date": "2026-10-29",
}]
render_earnings_vnext(pd.DataFrame(rows), open_research=lambda ticker: None)
'''
    app = AppTest.from_string(harness, default_timeout=10).run()
    assert not app.exception
    markdown = "\n".join(item.value for item in app.markdown)
    titles = [item.value for item in app.title]
    assert "Earnings Intelligence" in titles
    assert "Recently Reported" in markdown
    assert "Upcoming Earnings" in markdown
    assert any(button.label == "View Investment Case — BEAT" for button in app.button)


def test_normalizer_accepts_raw_aliases_without_inventing_values():
    history = normalized_earnings_history({"earnings_history": [{
        "date": "2026-07-29", "epsActual": -0.5, "epsEstimated": 0,
        "revenueActual": 0, "revenueEstimated": None,
    }]})
    assert history[0]["eps_actual"] == -0.5
    assert history[0]["eps_estimate"] == 0
    assert history[0]["revenue_actual"] == 0
    assert history[0]["revenue_estimate"] is None
