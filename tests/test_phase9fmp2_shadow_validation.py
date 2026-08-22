from __future__ import annotations

import copy
import json

import pandas as pd

import overnight_market_scan as scanner
import services.deep_research_cache as research_cache
from engines.fmp_normalization import normalize_fund_disclosure
from services.fmp_shadow_research import (
    FMP_SHADOW_MAX_REQUESTS_PER_SYMBOL,
    FMP_SHADOW_TTLS,
    build_fmp_shadow_research,
    build_provider_comparison,
)


class _Result:
    def __init__(self, payload, fetched_at="2026-08-22T12:00:00Z"):
        self.payload = payload
        self.fetched_at = fetched_at
        self.outcome = "SUCCESS" if payload else "AUTHORIZED_EMPTY"


class _Client:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        return _Result(self.payloads.get(endpoint, []))


class _FailClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        return type("FailedResult", (), {
            "payload": None, "fetched_at": "2026-08-23T12:00:00Z",
            "outcome": "TIMEOUT_OR_NETWORK_FAILURE",
        })()


def _payloads():
    return {
        "analyst-estimates": [{
            "date": "2027-01-31", "epsAvg": 0, "epsHigh": 1, "epsLow": -1,
            "revenueAvg": -10, "revenueHigh": 0, "revenueLow": -20,
            "numAnalystsEps": 0, "numAnalystsRevenue": 12,
        }],
        "grades-consensus": [{"strongBuy": 2, "buy": 1, "hold": 0, "sell": 0, "strongSell": 0, "consensus": "Buy"}],
        "grades": [{"date": "2026-08-01", "gradingCompany": "Example Firm", "previousGrade": "Hold", "newGrade": "Buy", "action": "upgrade"}],
        "price-target-consensus": [{"targetConsensus": 100, "targetHigh": 120, "targetLow": 80, "analystCount": 0}],
        "price-target-summary": [{"lastMonthAvgPriceTarget": 99, "lastQuarterAvgPriceTarget": 98}],
        "institutional-ownership/symbol-positions-summary": [{
            "symbol": "NVDA", "investorsHolding": 0, "ownershipPercent": 0,
            "date": "2026-06-30", "filingDate": "2026-08-14",
        }],
        "funds/disclosure-holders-latest": [{
            "investorName": "Example Fund", "cik": "1", "symbol": "NVDA",
            "securityName": "NVIDIA", "securityCusip": "000", "sharesNumber": 0,
            "weight": -0.1, "marketValue": 0, "date": "2026-06-30",
            "filingDate": "2026-08-14",
        }],
        "news/stock": [{
            "symbol": "NVDA", "title": "NVIDIA launches verified product",
            "site": "Example News", "publishedDate": "2026-08-20",
            "url": "https://example.test/nvda-news",
        }],
        "news/press-releases": [{
            "symbol": "NVDA", "title": "NVIDIA announces quarterly event",
            "site": "NVIDIA", "publishedDate": "2026-08-21",
            "url": "https://example.test/nvda-release",
        }],
    }


def _relevant(title, description, symbol, company_name):
    return symbol.lower() in title.lower() or company_name.lower() in title.lower()


def test_shadow_fetches_exact_bounded_families_and_preserves_signed_values(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    client = _Client(_payloads())
    result = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=client
    )
    assert len(client.calls) == FMP_SHADOW_MAX_REQUESTS_PER_SYMBOL == 9
    assert {name for name, _ in client.calls} == set(_payloads())
    analyst = result["families"]["fmp_shadow_analyst"]
    estimate = analyst["estimates"][0]
    assert estimate["eps_estimate_avg"] == 0
    assert estimate["eps_estimate_low"] == -1
    assert estimate["revenue_estimate_avg"] == -10
    assert estimate["eps_analyst_count"] == 0
    assert estimate["estimate_vintage_status"] == "NOT_POINT_IN_TIME_VINTAGE"
    assert estimate["provenance"]["provider"] == "FMP"
    assert analyst["actions"][0]["firm"] == "Example Firm"
    assert analyst["targets"][0]["analyst_count"] == 0
    assert analyst["target_summary"][0]["last_month_average_target"] == 99


def test_ownership_is_separate_from_insider_and_filing_date_gates_availability(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    result = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=_Client(_payloads())
    )
    summary = result["families"]["fmp_shadow_ownership_summary"]["summary"][0]
    holder = result["families"]["fmp_shadow_fund_disclosures"]["holders"][0]
    assert summary["reporting_date"] == "2026-06-30"
    assert summary["filing_date"] == summary["evidence_available_from"] == "2026-08-14"
    assert summary["institutional_ownership_pct"] == 0
    assert holder["shares"] == 0 and holder["weight"] == -0.1 and holder["market_value"] == 0
    assert holder["evidence_type"] == "INSTITUTIONAL_FUND_HOLDING"
    assert "insider" not in json.dumps(result).lower()
    unavailable = normalize_fund_disclosure({
        "investorName": "Example", "symbol": "NVDA", "date": "2026-06-30",
    })
    assert unavailable["evidence_available_from"] is None
    assert unavailable["provenance"]["semantic_status"] == "DATA_UNAVAILABLE"


def test_fmp_news_and_press_releases_coexist_with_newsapi_without_winner_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    shadow = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=_Client(_payloads())
    )
    current = {
        "source_newsapi": True,
        "news_evidence": [{"headline": "Existing", "url": "https://newsapi.test/a", "published_at": "2026-08-19"}],
        "source_finnhub_recommendation": True,
        "source_finnhub_target": True,
        "source_finnhub_analyst_actions": True,
        "source_finnhub_insider": True,
    }
    comparison = build_provider_comparison(current, shadow)
    assert comparison["mode"] == "DIAGNOSTIC_NO_WINNER_SELECTION"
    assert comparison["analyst"]["selection_policy"] == "NO_AUTOMATIC_WINNER_OR_DISAGREEMENT_RESOLUTION"
    assert comparison["analyst"]["recommendation_consensus"] == "BOTH_AVAILABLE"
    assert comparison["analyst"]["target"] == "BOTH_AVAILABLE"
    assert comparison["analyst"]["actions"] == "BOTH_AVAILABLE"
    assert comparison["analyst"]["estimates"] == "ONLY_FMP_AVAILABLE"
    assert comparison["news"]["availability"] == "BOTH_AVAILABLE"
    assert comparison["news"]["selection_policy"] == "NEWSAPI_REMAINS_AUTHORITATIVE_FMP_IS_SHADOW_ONLY"
    assert comparison["news"]["newsapi_url_count"] == 1
    assert comparison["news"]["fmp_url_count"] == 2
    assert comparison["ownership"]["semantic_note"] == "INSTITUTIONAL_AND_INSIDER_EVIDENCE_REMAIN_SEPARATE"


def test_relevance_filter_rejects_unrelated_fmp_articles(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    payloads = _payloads()
    payloads["news/stock"] = [{
        "title": "ELF microcontroller project", "site": "Unrelated",
        "publishedDate": "2026-08-20", "url": "https://example.test/unrelated",
    }]
    shadow = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=_Client(payloads)
    )
    news = shadow["families"]["fmp_shadow_company_news"]
    assert news["accepted_relevance_count"] == 0
    assert news["relevance_rejected_count"] == 1
    assert news["articles"] == []


def test_persistent_family_cache_uses_existing_freshness_states_and_avoids_duplicate_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    client = _Client(_payloads())
    first = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=client
    )
    assert len(client.calls) == 9
    second = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=client
    )
    assert len(client.calls) == 9
    assert set(FMP_SHADOW_TTLS) == set(first["freshness"]) == set(second["freshness"])
    assert {item["status"] for item in first["freshness"].values()} == {"FETCHED"}
    assert {item["status"] for item in second["freshness"].values()} == {"FRESH_CACHE"}


def test_expired_provider_failure_uses_explicit_stale_fallback_without_restamping(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(research_cache.time, "time", lambda: 1_000.0)
    first = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=_Client(_payloads())
    )
    original_times = {family: meta["fetched_at"] for family, meta in first["freshness"].items()}
    monkeypatch.setattr(research_cache.time, "time", lambda: 1_000.0 + (25 * 60 * 60))
    failed = _FailClient()
    second = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=failed
    )
    assert len(failed.calls) == 9
    assert {item["status"] for item in second["freshness"].values()} == {"STALE_FALLBACK"}
    assert {family: meta["fetched_at"] for family, meta in second["freshness"].items()} == original_times


def test_missing_credentials_make_no_shadow_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    client = _Client(_payloads())
    assert build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="", relevance_check=_relevant, client=client
    ) == {}
    assert client.calls == []


def test_scheduled_shadow_namespace_does_not_change_investment_fields(monkeypatch):
    investment_keys = (
        "opportunity_score", "confidence_pct", "recommendation", "atlas_fair_value",
        "decision_expected_return_pct", "decision_valuation_target", "entry_price",
        "stop_loss", "target_1", "target_2", "position_size_pct",
    )
    row = {"ticker": "NVDA", **{key: index for index, key in enumerate(investment_keys)}}
    before = {key: copy.deepcopy(row[key]) for key in investment_keys}
    monkeypatch.setattr(scanner, "FAST_CRON_MODE", True)
    monkeypatch.setattr(scanner, "FAST_CRON_SKIP_PRE_RANK_DEEP_APIS", True)
    monkeypatch.setattr(scanner, "v421_should_run_full_research", lambda symbol, candidate: True)
    monkeypatch.setattr(scanner, "get_finalist_enrichment", lambda *args: ({"source_finnhub_target": True}, {}))
    shadow = {"provider": "FMP", "mode": "RESEARCH_ONLY_SHADOW", "families": {}, "freshness": {}}
    monkeypatch.setattr(scanner, "build_fmp_shadow_research", lambda *args, **kwargs: shadow)
    monkeypatch.setattr(scanner, "build_provider_comparison", lambda *args: {"mode": "DIAGNOSTIC_NO_WINNER_SELECTION"})
    monkeypatch.setattr(scanner, "merge_finalist_enrichment", lambda *args, **kwargs: None)
    monkeypatch.setattr(scanner, "v42_build_committee_safe", lambda symbol, candidate, meta, ind, hist: candidate)
    monkeypatch.setattr(scanner, "v42_apply_investor_translations_safe", lambda candidate: candidate)
    result = scanner.v421_apply_tiered_committee("NVDA", row, {"company_name": "NVIDIA"}, {}, pd.DataFrame())
    assert {key: result[key] for key in investment_keys} == before
    assert result["fmp_shadow_research"] == shadow
    assert result["provider_comparison_diagnostics"]["mode"] == "DIAGNOSTIC_NO_WINNER_SELECTION"


def test_shadow_objects_do_not_contain_credentials_payloads_or_provider_winner(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    result = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="do-not-leak", relevance_check=_relevant, client=_Client(_payloads())
    )
    rendered = json.dumps(result)
    assert "do-not-leak" not in rendered
    assert "raw_payload" not in rendered
    assert "winner" not in rendered.lower()
    assert result["mode"] == "RESEARCH_ONLY_SHADOW"
