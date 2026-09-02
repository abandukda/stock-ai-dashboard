from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from engines.earnings_decision_story import (
    EARNINGS_DECISION_STORY_VERSION,
    build_earnings_decision_story,
    normalized_earnings_history,
)
from ui.earnings_vnext import (
    EARNINGS_VNEXT_SECTIONS, EARNINGS_VNEXT_VERSION, _markdown_money,
    _row_payload, _stories, _unsigned_pct,
)


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
    assert story["production_decision"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert story["decision_availability"]["reason_code"] == "CANONICAL_RECOMMENDATION_NOT_PUBLISHED"
    assert story["production_decision"]["opportunity"] == 82
    assert story["production_decision"]["confidence"] == 74
    assert story["production_decision"]["atlas_fair_value"] == 140
    assert story["wall_street_consensus"] == 155


def test_nested_production_row_defeats_display_buy_fallback():
    canonical = _row(recommendation=None)
    canonical.update({
        "ticker": "GAP", "company": "Gap Inc.", "Opportunity": None,
        "Confidence": 97, "atlas_fair_value": 39.86,
        "decision_expected_return_pct": 76.6,
    })
    wrapper = {
        "ticker": "GAP", "company": "Gap Inc.", "Recommendation": "buy",
        "Opportunity": None, "Confidence": None, "atlas_fair_value": None,
        "decision_expected_return_pct": None, "Raw": canonical,
    }
    story = build_earnings_decision_story(wrapper)
    decision = story["production_decision"]
    assert decision["recommendation"] is None
    assert decision["opportunity"] is None
    assert decision["confidence"] == 97
    assert decision["atlas_fair_value"] == 39.86
    assert decision["decision_expected_return"] == 76.6
    assert _row_payload(wrapper)["Raw"] is canonical


def test_existing_research_context_is_the_exact_decision_authority():
    canonical = {
        "semantic_status": "DATA_UNAVAILABLE", "recommendation": None,
        "opportunity": None, "confidence": 97, "atlas_fair_value": 39.86,
        "decision_expected_return": 76.6, "decision_digest": "gap-canonical",
    }
    row = _row(recommendation="buy")
    row["research_context"] = {"production_decision": canonical}
    story = build_earnings_decision_story(row)
    assert story["production_decision"] == canonical


def test_deep_evidence_is_progressive_and_never_invented():
    available = _row()
    available.update({
        "analyst_target_mean": 145, "analyst_target_low": 120,
        "analyst_target_high": 170, "analyst_count": 12,
        "analyst_actions": [{"firm": "Example", "action": "Reiterated", "date": "2026-07-30"}],
        "news_evidence": [{"title": "Quarter reported", "source": "filing", "date": "2026-07-29"}],
        "institutional_ownership_pct": 61.2,
        "congressional_transactions": [{"member": "Example", "transaction_type": "Purchase", "date": "2026-07-01"}],
    })
    deep = build_earnings_decision_story(available)["deep_evidence"]
    assert deep["analyst"]["semantic_status"] == "AVAILABLE"
    assert deep["news"]["semantic_status"] == "AVAILABLE"
    assert deep["ownership"]["semantic_status"] == "AVAILABLE"
    assert deep["political"]["semantic_status"] == "AVAILABLE"
    assert deep["political"]["scoring_authority"] == "CONTEXT_ONLY"

    unavailable = build_earnings_decision_story(_row())["deep_evidence"]
    assert unavailable["news"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert unavailable["ownership"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert unavailable["political"]["semantic_status"] == "DATA_UNAVAILABLE"

    canonical = _row()
    canonical["research_context"] = {"evidence_families": {
        "analyst_consensus_targets": {"data": {"mean": 0, "low": -5, "high": 8, "count": 3}},
        "company_news": {"data": {"items": [{"title": "Filed update", "source": "filing"}]}},
        "institutional_ownership": {"data": {"institutional_pct": 0, "insider_pct": -1}},
    }}
    deep = build_earnings_decision_story(canonical)["deep_evidence"]
    assert deep["analyst"]["consensus"]["mean_target"] == 0
    assert deep["analyst"]["consensus"]["low_target"] == -5
    assert deep["news"]["items"][0]["title"] == "Filed update"
    assert deep["ownership"]["institutional_ownership_pct"] == 0
    assert deep["ownership"]["insider_ownership_pct"] == -1


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


def test_renderer_exposes_progressive_evidence_and_targeted_mobile_safe_zone():
    harness = r'''
import pandas as pd
from ui.earnings_vnext import render_earnings_vnext
rows = [{
    "ticker": "DEEP", "company": "Deep Evidence Corp", "Recommendation": None,
    "Confidence": 71, "analyst_target_mean": 125, "institutional_ownership_pct": 62,
    "earnings_history": [{"report_date": "2026-07-29", "eps_actual": 1.2, "eps_estimate": 1.0, "revenue_actual": 110, "revenue_estimate": 100}],
    "news_evidence": [{"title": "Quarter reported", "source": "filing", "date": "2026-07-29"}],
    "congressional_transactions": [{"member": "Example", "transaction_type": "Purchase", "date": "2026-07-01"}],
}]
render_earnings_vnext(pd.DataFrame(rows), open_research=lambda ticker: None)
'''
    app = AppTest.from_string(harness, default_timeout=10).run()
    assert not app.exception
    markdown = "\n".join(item.value for item in app.markdown)
    assert "Analyst evidence" in markdown
    assert "Relevant company news" in markdown
    assert "Ownership" in markdown
    assert "Political context · non-scoring" in markdown
    source = (ROOT / "ui" / "earnings_vnext.py").read_text(encoding="utf-8")
    assert "atlas-earnings-card-anchor" in source
    assert "@media (max-width:700px)" in source
    assert '[data-testid="stRadio"] [role="radiogroup"]' in source
    assert '[data-testid="stRadio"]:has([role="radiogroup"])' in source
    assert "top:3.75rem" in source
    assert "margin-top:3rem" in source
    assert '[data-testid="stElementContainer"]:has(style)' in source
    assert ':has([data-atlas-qa][aria-hidden="true"])' in source
    assert "overflow-x:hidden" in source
    assert "padding-right:6.25rem" in source
    assert "font-size:2.1rem" in source
    assert "atlas-earnings-mobile-snapshot" in source
    assert _markdown_money(125) == r"\$125.00"
    assert _unsigned_pct(62) == "62.0%"


def test_analyst_action_dates_are_readable_without_mutating_or_reordering_evidence():
    from ui.earnings_vnext import _analyst_actions_for_display

    actions = [
        {"date": 1787961600, "firm": "First", "action": "Reiterated"},
        {"date": "2026-08-28T13:30:00Z", "firm": "Second", "action": "Raised"},
    ]
    displayed = _analyst_actions_for_display(actions)

    assert [row["firm"] for row in displayed] == ["First", "Second"]
    assert displayed[0]["date"] == "Aug 29, 2026"
    assert displayed[1]["date"] == "Aug 28, 2026"
    assert actions[0]["date"] == 1787961600
    assert actions[1]["date"] == "2026-08-28T13:30:00Z"


def test_normalizer_accepts_raw_aliases_without_inventing_values():
    history = normalized_earnings_history({"earnings_history": [{
        "date": "2026-07-29", "epsActual": -0.5, "epsEstimated": 0,
        "revenueActual": 0, "revenueEstimated": None,
    }]})
    assert history[0]["eps_actual"] == -0.5
    assert history[0]["eps_estimate"] == 0
    assert history[0]["revenue_actual"] == 0
    assert history[0]["revenue_estimate"] is None
