from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest

import overnight_market_scan as scanner
import services.deep_research_cache as deep_cache
from engines.atlas_research_builder_v2 import _earnings_history
from engines.deep_research_evidence import (
    build_earnings_comparisons,
    normalize_earnings_history,
    normalize_guidance_evidence,
    normalize_news_articles,
    normalize_transcript_evidence,
    select_deep_enrichment_symbols,
)


@pytest.fixture(autouse=True)
def isolated_deep_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(deep_cache, "CACHE_ROOT", tmp_path / "deep-cache")
    scanner._FINALIST_ENRICHMENT_CACHE.clear()
    scanner._ETF_RESEARCH_CACHE.clear()


def test_deep_enrichment_union_is_stable_and_deduplicated():
    rows = [
        {"symbol": "TOP", "recommendation": "MONITOR", "v42_tier": "light"},
        {"symbol": "BUY", "recommendation": "BUY NOW", "v42_tier": "light"},
        {"symbol": "TIER", "recommendation": "MONITOR", "v42_tier": "full"},
        {"symbol": "WATCH", "recommendation": "MONITOR", "v42_tier": "light"},
    ]
    symbols, reasons = select_deep_enrichment_symbols(rows, top_limit=2, watchlist={"WATCH", "BUY"})
    assert symbols == ["TOP", "BUY", "TIER", "WATCH"]
    assert reasons["BUY"] == ["TOP_15", "BUY_NOW", "WATCHLIST"]


def test_earnings_history_chronology_dedupes_and_preserves_zero_negative():
    rows = [
        {"fiscalPeriod": "Q1", "date": "2026-05-01", "epsActual": 0, "epsEstimated": -0.2,
         "revenueActual": 90, "revenueEstimated": 100},
        {"fiscalPeriod": "Q1", "date": "2026-05-01", "epsActual": 0, "epsEstimated": -0.2,
         "revenueActual": 90, "revenueEstimated": 100},
        {"fiscalPeriod": "Q4", "date": "2026-02-01", "epsActual": -0.4, "epsEstimated": -0.3},
    ]
    history = normalize_earnings_history(rows, provider="FMP", captured_at="2026-05-02T00:00:00Z")
    assert len(history) == 2
    assert history[0]["eps_actual"] == 0
    assert history[0]["eps_surprise_pct"] == 100.0
    assert history[0]["revenue_surprise_pct"] == -10.0
    assert history[1]["eps_actual"] == -0.4
    assert build_earnings_comparisons(history)["eps_surprise_trend"] == "IMPROVING"


def test_research_builder_preserves_same_fiscal_quarter_across_years_and_provenance():
    history = _earnings_history({"earnings_history": [
        {"fiscal_period": "Q1", "report_date": "2026-05-01", "eps_actual": 0,
         "eps_surprise_pct": -2, "provider": "FMP", "evidence_timestamp": "2026-05-02"},
        {"fiscal_period": "Q1", "report_date": "2025-05-01", "eps_actual": -1,
         "eps_surprise_pct": 3, "provider": "FMP", "evidence_timestamp": "2025-05-02"},
    ]})
    assert len(history) == 2
    assert history[0]["eps_actual"] == 0
    assert history[0]["provider"] == "FMP"


def test_guidance_rejects_analyst_estimates_and_requires_source_date():
    rows = [
        {"category": "eps", "source_type": "ANALYST", "source": "Consensus", "date": "2026-01-01", "value": 2},
        {"category": "revenue", "source_type": "MANAGEMENT", "source": "Company release", "date": "2026-01-02", "low": 10, "high": 11},
        {"category": "margin", "source_type": "COMPANY", "value": 0.2},
    ]
    assert normalize_guidance_evidence(rows) == [{
        "category": "revenue", "low": 10, "high": 11, "source": "Company release",
        "date": "2026-01-02", "source_type": "MANAGEMENT",
    }]


def test_transcript_evidence_fails_closed_without_period_date_and_source():
    rows = [
        {"fiscal_period": "Q1", "date": "2026-01-01", "source": "FMP", "themes": ["demand", "margin"]},
        {"fiscal_period": "Q2", "themes": ["invented"]},
    ]
    assert normalize_transcript_evidence(rows) == [{
        "fiscal_period": "Q1", "date": "2026-01-01", "source": "FMP",
        "source_url": None, "themes": ["demand", "margin"],
    }]


def test_news_provenance_keeps_clickable_url_without_article_body():
    evidence = normalize_news_articles([{
        "title": "Acme raises guidance", "source": "Wire", "published_at": "2026-01-01",
        "url": "https://example.test/story", "description": "must not persist",
    }], symbol="ACME")
    assert evidence[0]["url"] == "https://example.test/story"
    assert evidence[0]["ticker"] == "ACME"
    assert "description" not in evidence[0]


def test_sma200_uses_existing_history_and_requires_200_bars():
    def frame(size):
        values = list(range(1, size + 1))
        return pd.DataFrame({"Close": values, "High": values, "Low": values, "Volume": [1000] * size})

    assert scanner.compute_indicators(frame(199))["sma200"] is None
    assert scanner.compute_indicators(frame(200))["sma200"] == 100.5


def test_finalist_cache_adds_no_provider_calls_and_does_not_cross_tickers(monkeypatch):
    scanner._FINALIST_ENRICHMENT_CACHE.clear()
    calls = []

    def profile(symbol):
        calls.append(("profile", symbol))
        return {"company_name": symbol}

    monkeypatch.setattr(scanner, "get_fmp_data", profile)
    monkeypatch.setattr(scanner, "get_fmp_financial_intelligence", lambda symbol: {})
    monkeypatch.setattr(scanner, "get_finnhub_research", lambda symbol: {})
    monkeypatch.setattr(scanner, "get_finnhub_insider_activity", lambda symbol: {})
    monkeypatch.setattr(scanner, "get_news_research", lambda symbol, company_name="": {})
    first, categories = scanner.get_finalist_enrichment("AAA")
    second, cached = scanner.get_finalist_enrichment("AAA")
    third, _ = scanner.get_finalist_enrichment("BBB")
    assert first["company_name"] == second["company_name"] == "AAA"
    assert third["company_name"] == "BBB"
    assert first["_evidence_freshness"]["profile"]["status"] == "FETCHED"
    assert calls == [("profile", "AAA"), ("profile", "BBB")]
    assert categories["cache"] == "miss" and cached["cache"] == "hit"


def test_persistent_family_cache_preserves_fetch_time_and_marks_stale_fallback():
    calls = []

    def fetch():
        calls.append(1)
        return {"value": 0, "provider": "TEST"}

    first, first_meta = deep_cache.cached_evidence("AAA", "fundamentals", 100, fetch, now_epoch=1000)
    second, second_meta = deep_cache.cached_evidence("AAA", "fundamentals", 100, fetch, now_epoch=1050)
    stale, stale_meta = deep_cache.cached_evidence("AAA", "fundamentals", 100, lambda: {}, now_epoch=1200)
    assert first == second == stale == {"value": 0, "provider": "TEST"}
    assert len(calls) == 1
    assert first_meta["status"] == "FETCHED"
    assert second_meta["status"] == "FRESH_CACHE"
    assert stale_meta["status"] == "STALE_FALLBACK"
    assert first_meta["fetched_at"] == second_meta["fetched_at"] == stale_meta["fetched_at"]


def test_missing_cache_and_provider_failure_is_explicitly_unavailable():
    payload, metadata = deep_cache.cached_evidence("NONE", "news", 60, lambda: {}, now_epoch=1000)
    assert payload == {}
    assert metadata == {
        "status": "TEMPORARILY_UNAVAILABLE", "fetched_at": None,
        "age_seconds": None, "ttl_seconds": 60,
    }


def test_cache_invalidates_when_provider_source_version_changes():
    first, _ = deep_cache.cached_evidence(
        "VERS", "profile", 1000, lambda: {"company_name": "old"},
        now_epoch=1000, source_version="provider.v1",
    )
    second, metadata = deep_cache.cached_evidence(
        "VERS", "profile", 1000, lambda: {"company_name": "new"},
        now_epoch=1001, source_version="provider.v2",
    )
    assert first["company_name"] == "old"
    assert second["company_name"] == "new"
    assert metadata["status"] == "FETCHED"


def test_workflow_persists_only_ignored_versioned_cache():
    workflow = Path(".github/workflows/overnight_scan.yml").read_text(encoding="utf-8")
    ignored = Path(".gitignore").read_text(encoding="utf-8")
    assert "actions/cache@v4" in workflow
    assert "path: .atlas_research_cache/deep_v1" in workflow
    assert "atlas-deep-research-v1-${{ github.run_id }}" in workflow
    assert ".atlas_research_cache/" in ignored


def test_provider_failure_leaves_ranked_row_unchanged(monkeypatch):
    scanner._FINALIST_ENRICHMENT_CACHE.clear()
    for name in (
        "get_fmp_data", "get_fmp_financial_intelligence", "get_finnhub_research",
        "get_finnhub_insider_activity",
    ):
        monkeypatch.setattr(scanner, name, lambda symbol: {})
    monkeypatch.setattr(scanner, "get_news_research", lambda symbol, company_name="": {})
    row = {"symbol": "SAFE", "conviction": 77, "rank": 4}
    before = copy.deepcopy(row)
    payload, _ = scanner.get_finalist_enrichment("SAFE")
    assert payload == {}
    assert row == before


def test_expansion_only_evidence_cannot_mutate_investment_inputs():
    row = {"symbol": "NEW", "conviction": 71, "revenue_growth": None, "atlas_fair_value": None}
    before = copy.deepcopy(row)
    scanner.merge_finalist_enrichment(
        "NEW", row, {}, {"price": 10},
        {"revenue_growth": 0.5, "atlas_fair_value": 18, "earnings_history": [{"date": "2026-01-01"}]},
        evidence_only=True,
    )
    assert row["conviction"] == before["conviction"]
    assert row["revenue_growth"] is None and row["atlas_fair_value"] is None
    assert row["deep_research_evidence"]["revenue_growth"] == 0.5


def test_etf_fields_are_semantically_isolated_from_corporate_evidence():
    row = scanner.score_etf_row("SPY", {
        "company_name": "SPDR S&P 500 ETF", "fund_family": "State Street",
        "expense_ratio": 0.0009, "distribution_yield": 0.012,
    }, {
        "price": 500, "dollar_volume": 100_000_000, "sma20": 490, "sma50": 480,
        "sma200": 450, "twenty_day_pct": 3, "sixty_day_pct": 8, "rsi": 55,
        "atr_pct": 2, "volume_ratio": 1, "avg_volume_20d": 1_000_000,
    })
    assert row["etf_research"]["fund_family"] == "State Street"
    assert "earnings_history" not in row and "management_guidance" not in row
