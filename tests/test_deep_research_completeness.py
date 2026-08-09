import pandas as pd

import overnight_market_scan as scan
from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines.live_research_engine import _company_news_relevant
from engines.research_enrichment_v105 import build_enriched_research_report


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_fmp_profile_uses_stable_schema(monkeypatch):
    calls = []
    monkeypatch.setattr(scan, "FMP_API_KEY", "test")

    def request(url, params, timeout):
        calls.append((url, params))
        return _Response([{
            "symbol": "CRM", "companyName": "Salesforce, Inc.",
            "marketCap": 250_000_000_000, "price": 200.0,
            "sector": "Technology", "lastDividend": 0.0,
        }])

    monkeypatch.setattr(scan.requests, "get", request)
    result = scan.get_fmp_data("crm")

    assert calls[0][0].endswith("/stable/profile")
    assert calls[0][1]["symbol"] == "CRM"
    assert result["market_cap"] == 250_000_000_000
    assert result["last_dividend"] == 0.0
    assert result["source_fmp_profile"] is True


def test_fmp_financials_parse_partial_zero_and_earnings(monkeypatch):
    monkeypatch.setattr(scan, "FMP_API_KEY", "test")
    payloads = {
        "income-statement": [
            {"date": "2026-06-30", "revenue": 120, "eps": 1.2, "grossProfitRatio": 0.7, "operatingIncomeRatio": 0.2, "netIncomeRatio": 0.15},
            {"revenue": 110, "eps": 1.1}, {}, {}, {"revenue": 100, "eps": 1.0},
        ],
        "balance-sheet-statement": [{"totalDebt": 0, "totalAssets": 500, "totalStockholdersEquity": 300, "cashAndCashEquivalents": 80}],
        "cash-flow-statement": [{"operatingCashFlow": 40, "freeCashFlow": 30, "capitalExpenditure": -10}],
        "ratios": [{"currentRatio": 1.5, "returnOnEquity": 0.18}],
        "key-metrics": [{"roic": 0.16}],
        "earnings": [{"date": "2026-06-30", "epsActual": 0.0, "epsEstimated": 0.0, "revenueActual": 120, "revenueEstimated": 100}],
        "stock-peers": [{"peersList": ["ORCL"]}],
    }

    def fake_get(url, params=None, timeout=0):
        return payloads[url.rsplit("/", 1)[-1]]

    monkeypatch.setattr(scan, "http_get_json", fake_get)
    result = scan.get_fmp_financial_intelligence("CRM")

    assert result["total_debt"] == 0
    assert result["reported_eps"] == 0
    assert result["eps_estimate"] == 0
    assert result["revenue_surprise_pct"] == 20.0
    assert result["revenue_growth"] == 0.2
    assert result["roic"] == 0.16


def test_partial_finalist_enrichment_is_propagated(monkeypatch):
    monkeypatch.setattr(scan, "get_fmp_data", lambda symbol: {})
    monkeypatch.setattr(scan, "get_fmp_financial_intelligence", lambda symbol: {"free_cash_flow": 0, "source_fmp_financials": True})
    monkeypatch.setattr(scan, "get_finnhub_research", lambda symbol: {"finnhub_target_mean": 220.0})
    monkeypatch.setattr(scan, "get_finnhub_insider_activity", lambda symbol: {})
    monkeypatch.setattr(scan, "get_news_research", lambda symbol, company: {})

    enrichment, categories = scan.get_finalist_enrichment("CRM", "Salesforce")

    assert enrichment["free_cash_flow"] == 0
    assert categories["profile"] == "no"
    assert categories["fundamentals"] == "yes"
    assert categories["analysts"] == "yes"


def test_ranked_finalist_force_runs_bounded_enrichment(monkeypatch):
    monkeypatch.setattr(scan, "FAST_CRON_MODE", True)
    monkeypatch.setattr(scan, "FAST_CRON_SKIP_PRE_RANK_DEEP_APIS", True)
    monkeypatch.setattr(scan, "v421_should_run_full_research", lambda symbol, row: False)
    monkeypatch.setattr(scan, "get_finalist_enrichment", lambda symbol, company: (
        {"reported_eps": 2.5, "source_fmp_earnings_surprises": True},
        {"profile": "no", "fundamentals": "yes", "analysts": "no", "ownership": "no", "news": "no", "earnings": "yes", "valuation_inputs": "no"},
    ))
    monkeypatch.setattr(scan, "v42_build_committee_safe", lambda symbol, row, meta, ind, hist: row)
    monkeypatch.setattr(scan, "v42_apply_investor_translations_safe", lambda row: row)
    row = {"ticker": "CRM", "company_name": "Salesforce", "conviction": 97}

    result = scan.v421_apply_tiered_committee(
        "CRM", row, {}, {}, pd.DataFrame(), force_full=True
    )

    assert result["reported_eps"] == 2.5
    assert result["v42_tier"] == "full"


def test_saved_fields_map_to_research_page_without_fake_guidance():
    row = {
        "ticker": "CRM", "company": "Salesforce", "current_price": 200,
        "revenue_growth": 0.12, "earnings_growth": 0.0,
        "gross_profit_margin": 0.74, "operating_profit_margin": 0.2,
        "free_cash_flow": 0, "operating_cash_flow": 10,
        "cash_and_equivalents": 20, "total_debt": 0,
        "return_on_equity": 0.18, "roic": 0.16,
        "reported_eps": 0, "eps_estimate": 0, "eps_surprise_pct": 0,
        "latest_earnings_date": "2026-06-30", "next_earnings_date": "2026-09-01",
        "guidance": "Preferred entry is $190-$195 with a chart stop.",
        "analyst_target_mean": 225, "analyst_target_high": 250,
        "analyst_target_low": 180, "analyst_count": 40,
        "recent_headlines": [{"title": "Salesforce reports results", "source": "Wire"}],
    }
    report = build_enriched_research_report(row)

    assert report["financials"]["data"]["revenue_growth_pct"] == 12
    assert report["financials"]["data"]["eps_growth_pct"] == 0
    assert report["financials"]["data"]["free_cash_flow"] == 0
    assert report["earnings"]["data"]["reported_eps"] == 0
    assert report["earnings"]["data"]["eps_surprise_pct"] == 0
    assert "guidance" not in report["earnings"]["data"]
    assert report["news"]["data"][0]["headline"] == "Salesforce reports results"


def test_ambiguous_elf_news_is_rejected_and_company_news_is_accepted():
    bad = "This Filesystem is Born to Fail"
    good = "e.l.f. Beauty raises full-year outlook"

    assert scan.news_item_is_company_relevant(bad, "Hackaday filesystem article", "ELF", "e.l.f. Beauty, Inc.") is False
    assert scan.news_item_is_company_relevant(good, "Cosmetics demand remains strong", "ELF", "e.l.f. Beauty, Inc.") is True
    assert _company_news_relevant(bad, "Hackaday filesystem article", "ELF", "e.l.f. Beauty, Inc.") is False
    assert _company_news_relevant(good, "Cosmetics demand remains strong", "ELF", "e.l.f. Beauty, Inc.") is True


def test_evidence_registry_does_not_change_existing_recommendation():
    report = build_atlas_research_v2({
        "ticker": "TEST", "company": "Test", "committee_verdict": "BUY_NOW",
        "current_price": 100, "sma20": 98, "sma50": 95, "rsi": 55,
    })

    assert report["committee_verdict"] == "BUY_NOW"
    assert report["evidence_coverage_pct"] == report["research_completeness_pct"]
    assert report["evidence_registry"]["policy"]["status"] == "not_applicable"
    assert "recommendation_integrity_missing" not in report
