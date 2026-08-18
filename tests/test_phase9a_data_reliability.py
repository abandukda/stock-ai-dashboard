from engines.ask_atlas_engine import ask_atlas, extract_requested_ticker
from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines.research_engine import research_navigation_state
from engines.semantic_fields import (
    AVAILABLE, DATA_UNAVAILABLE, NOT_APPLICABLE, NOT_PUBLISHED,
    TEMPORARILY_UNAVAILABLE, evidence_state,
)
from engines.research_enrichment_v105 import accepted_company_news
from pathlib import Path


def _build(monkeypatch, row):
    monkeypatch.setattr(
        "engines.atlas_research_builder_v2.attach_price_history",
        lambda value: dict(value),
    )
    return build_atlas_research_v2(row)


def test_semantic_missing_states_are_explicit_and_zero_is_available():
    assert evidence_state(0) == AVAILABLE
    assert evidence_state(None) == DATA_UNAVAILABLE
    assert evidence_state(False) == DATA_UNAVAILABLE
    assert evidence_state(None, applicable=False) == NOT_APPLICABLE
    assert evidence_state(None, published=False) == NOT_PUBLISHED
    assert evidence_state(None, temporarily_unavailable=True) == TEMPORARILY_UNAVAILABLE


def test_etf_corporate_evidence_is_not_applicable(monkeypatch):
    report = _build(monkeypatch, {"ticker": "SPY", "quote_type": "ETF", "current_price": 500})
    registry = report["evidence_registry"]
    assert report["security_type"] == "ETF"
    assert registry["fundamentals"]["status"] == NOT_APPLICABLE
    assert registry["earnings"]["status"] == NOT_APPLICABLE
    assert registry["guidance"]["status"] == NOT_APPLICABLE
    assert registry["valuation"]["status"] == NOT_APPLICABLE


def test_unpublished_atlas_fv_is_not_data_unavailable(monkeypatch):
    report = _build(monkeypatch, {
        "ticker": "NVDA", "current_price": 180, "atlas_fair_value": None,
        "atlas_valuation_status": "REJECTED_IMPLAUSIBLE_UPSIDE", "analyst_target_mean": 220,
    })
    assert report["atlas_fair_value"] is None
    assert report["evidence_registry"]["valuation"]["status"] == NOT_PUBLISHED


def test_earnings_history_preserves_zero_deduplicates_and_sorts(monkeypatch):
    report = _build(monkeypatch, {
        "ticker": "CRM", "current_price": 200,
        "earnings_history": [
            {"period": "2025-12-31", "eps_actual": 0, "eps_estimate": 0, "revenue_actual": 0},
            {"period": "2026-03-31", "eps_actual": -0.2, "eps_estimate": 0.1},
            {"period": "2025-12-31", "eps_actual": 99},
        ],
    })
    history = report["sections"]["earnings"]["history"]
    assert [item["period"] for item in history] == ["2026-03-31", "2025-12-31"]
    assert history[1]["eps_actual"] == 0
    assert history[1]["eps_estimate"] == 0
    assert history[1]["revenue_actual"] == 0


def test_ask_atlas_exposes_ticker_section_and_grounding(monkeypatch):
    report = _build(monkeypatch, {
        "ticker": "AVGO", "current_price": 300, "reported_eps": 2.0,
        "eps_estimate": 1.8, "committee_verdict": "BUY_NOW",
    })
    result = ask_atlas("What happened in earnings?", report)
    assert result["ticker"] == "AVGO"
    assert result["section"] == "earnings"
    assert result["evidence_used"] == ["earnings"]
    assert result["evidence_missing"] == []
    assert result["generated_at"] == report["generated_at"]
    assert result["framework_version"] == "ASK_ATLAS_GROUNDED_V1"
    assert "NVDA" not in result["answer"]


def test_navigation_contract_is_ticker_isolated_for_stock_and_etf():
    nvda = research_navigation_state("nvda")
    spy = research_navigation_state("spy")
    for key in ("v73_research_ticker", "selected_ticker", "active_research_ticker"):
        assert nvda[key] == "NVDA"
        assert spy[key] == "SPY"
    assert nvda["v73_page"] == spy["v73_page"] == "Research Any Ticker"


def test_all_active_opportunity_links_use_canonical_navigation_contract():
    for path in ("ui/home_v104.py", "ui/daily_opportunities.py", "ui/morning_brief.py"):
        source = Path(path).read_text(encoding="utf-8")
        assert "research_navigation_state(ticker)" in source


def test_verified_company_news_preserves_working_link_metadata():
    item = accepted_company_news(
        {"ticker": "CRM", "company": "Salesforce Inc."},
        [{
            "headline": "Salesforce reports a verified company update",
            "publisher": "Reuters",
            "date": "2026-08-15T12:00:00Z",
            "url": "https://example.com/salesforce-update",
        }],
    )[0]
    assert item["source"] == "Reuters"
    assert item["date"] == "2026-08-15T12:00:00Z"
    assert item["url"] == "https://example.com/salesforce-update"


def test_ask_ai_ticker_matching_is_exact_not_substring_based():
    allowed = ["T", "B", "CRM", "AVGO"]
    assert extract_requested_ticker("What changed for CRM?", allowed) == "CRM"
    assert extract_requested_ticker("Tell me about AVGO earnings", allowed) == "AVGO"
    assert extract_requested_ticker("What is the best stock?", allowed) is None
