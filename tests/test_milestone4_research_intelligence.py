from copy import deepcopy

from services.home_market_intelligence import build_home_market_intelligence
from services.institutional_research_report import build_institutional_research_report


def research_page():
    return {
        "status": "AVAILABLE", "ticker": "NVDA", "company": "NVIDIA Corporation", "sector": "Technology",
        "identity": {"ticker": "NVDA"},
        "evidence": {
            "evaluation_snapshot_id": "snapshot", "candidate_digest": "candidate",
            "publication_digest": "publication", "source_sha": "source",
        },
        "about": {"industry": "Semiconductors", "profile": {
            "description": "NVIDIA designs accelerated computing platforms."
        }},
        "summary": {
            "why_rating": ["Revenue growth is 18.0% for FY2026."],
            "risks": ["Customer concentration is material."],
            "watch_conditions": {
                "strengthen": ["Verified margin expansion continues."],
                "weaken": ["Verified margins contract."],
                "invalidate": ["Certified evidence deteriorates."],
            },
        },
        "header": {
            "fair_value": 200.0, "price": 160.0, "fair_value_gap_pct": 25.0,
            "price_timestamp": "2026-10-15T20:00:00Z",
        },
        "financial_trend": {
            "status": "AVAILABLE", "periods": ["FY2025", "FY2026"],
            "series": {"Revenue": [100.0, 118.0], "Operating Margin": [31.0, 30.0]},
            "provenance": {"evidence_ids": ["finnhub:basic-financials:nvda"]},
        },
        "wall_street": {"status": "DISABLED"},
        "catalysts": {"status": "AVAILABLE", "events": [{"date": "2026-11-18", "type": "earnings"}]},
    }


def test_institutional_report_is_source_bound_non_scoring_and_does_not_mutate_input():
    page = research_page(); before = deepcopy(page)
    result = build_institutional_research_report(page)
    assert result["status"] == "AVAILABLE"
    assert result["classification"] == "CONTEXTUAL_NON_SCORING"
    assert result["external_model_active"] is False
    assert result["business"]["description"] == "NVIDIA designs accelerated computing platforms."
    assert result["financial_story"]["metrics"][0]["direction"] == "Improving"
    assert result["financial_story"]["metrics"][1]["direction"] == "Deteriorating"
    assert result["valuation"]["named_institution_opinions"] == ()
    assert result["scenarios"]["bull"] == ("Verified margin expansion continues.",)
    assert page == before


def test_institutional_report_fails_closed_on_missing_identity_and_never_invents_detail():
    page = research_page(); page["evidence"]["publication_digest"] = ""
    assert build_institutional_research_report(page) == {
        "contract": "ATLAS_INSTITUTIONAL_RESEARCH_REPORT_V1",
        "status": "UNAVAILABLE", "reason": "PUBLICATION_IDENTITY_INCOMPLETE",
    }
    page = research_page(); page["about"]["profile"] = {}; page["financial_trend"] = {"status": "UNAVAILABLE"}
    result = build_institutional_research_report(page)
    assert "classified in Semiconductors" in result["business"]["description"]
    assert result["financial_story"]["status"] == "UNAVAILABLE"


def test_home_market_intelligence_admits_only_dated_governed_context():
    story = {"scan_timestamp": "2026-10-16T20:00:00Z", "market_today": {
        "as_of": "2026-10-16T20:00:00Z", "market_session": "LATEST_REGULAR_CLOSE",
        "interpretation": "Broad indexes finished mixed.",
        "instruments": [
            {"symbol": "SPY", "label": "S&P 500 · SPY", "price": 680.0, "change_pct": .2},
            {"symbol": "QQQ", "label": "Nasdaq 100 · QQQ", "price": None, "change_pct": None},
        ],
        "sector_performance": [
            {"sector": "Technology", "change_pct": .4, "as_of": "2026-10-16"},
            {"sector": "Energy", "change_pct": .5},
        ],
        "official_macro_evidence": [{
            "label": "CPI", "agency_label": "BLS", "source_url": "https://bls.gov/cpi",
            "observation_period": "September 2026", "value": 1,
        }],
        "upcoming_events": [{"label": "CPI release", "scheduled_at": "2026-11-12", "source": "BLS"}],
        "historical_analogues": [{"label": "invalid"}, {
            "label": "Rates-and-inflation cohort", "criteria": "same signed regime fields",
            "sample_size": 12, "observation_window": "20 sessions",
            "outcome_dispersion": "-8% to +9%", "source_evidence_ids": ["macro:cohort:1"],
        }],
        "conditional_watchpoints": ["If yields rise, monitor rate-sensitive sectors."],
    }}
    result = build_home_market_intelligence(story)
    assert result["status"] == "AVAILABLE"
    assert [item["symbol"] for item in result["indices"]] == ["SPY"]
    assert [item["sector"] for item in result["sectors"]] == ["Technology"]
    assert len(result["historical_analogues"]) == 1
    assert result["external_model_active"] is False
    assert result["classification"] == "CONTEXTUAL_NON_SCORING"


def test_home_market_intelligence_discloses_missing_analogues_and_context():
    result = build_home_market_intelligence({"scan_timestamp": "2026-10-16T20:00:00Z", "market_today": {}})
    assert result["status"] == "LIMITED"
    assert "No reproducible historical analogue" in result["analogue_limitation"]
    assert "Verified index context is unavailable." in result["limitations"]
