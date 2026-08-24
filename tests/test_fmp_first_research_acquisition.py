from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import inspect
from pathlib import Path

import pytest

from services.fmp_research_acquisition import (
    MAX_ANALYST_ACTIONS, MAX_EXPLICIT_RESEARCH_REQUESTS,
    MAX_INSTITUTIONAL_HOLDERS, acquire_explicit_fmp_research,
)
from services.fmp_stable_client import FMPResponse, SUCCESS
from services.provider_ownership import (
    COMMERCIAL_LICENSE_PENDING, EXPLICIT_RESEARCH_FMP_PRIMARY, FMP,
    FMP_PRIMARY_YAHOO_FALLBACK,
)
from services.research_family_cache import save_family_envelope
from services.yahoo_dependency_registry import (
    LEGACY_PENDING_REMOVAL, YAHOO_DEPENDENCIES, yahoo_migration_metrics,
)
from engines.ask_atlas_engine import _compact_context
from engines import atlas_research_builder_v2


NOW = "2026-08-23T12:00:00+00:00"


class FakeFMP:
    def __init__(self, *, fail: set[str] | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail or set()

    def get(self, endpoint_family, params=None, **_kwargs):
        self.calls.append((endpoint_family, dict(params or {})))
        if endpoint_family in self.fail:
            return FMPResponse(None, "TIMEOUT_OR_NETWORK_FAILURE", endpoint_family, NOW, attempts=1)
        symbol = (params or {}).get("symbol", "NVDA")
        payload = self.payload(endpoint_family, symbol)
        return FMPResponse(payload, SUCCESS, endpoint_family, NOW, 200, 1)

    @staticmethod
    def payload(endpoint, symbol):
        if endpoint == "profile":
            return [{"symbol": symbol, "companyName": "NVIDIA Corporation", "sector": "Technology", "industry": "Semiconductors", "marketCap": 1, "type": "stock"}]
        if endpoint == "stock-peers":
            return [{"symbol": symbol, "peers": ["AMD", "AVGO"]}]
        if endpoint == "income-statement":
            return [{"date": "2026-06-30", "revenue": 0, "operatingIncome": -2, "netIncome": -1, "eps": -0.1, "filingDate": "2026-08-01"}]
        if endpoint == "balance-sheet-statement":
            return [{"date": "2026-06-30", "cashAndCashEquivalents": 0, "totalDebt": 4, "totalAssets": 10, "filingDate": "2026-08-01"}]
        if endpoint == "cash-flow-statement":
            return [{"date": "2026-06-30", "operatingCashFlow": 2, "capitalExpenditure": -1, "freeCashFlow": 1, "filingDate": "2026-08-01"}]
        if endpoint == "key-metrics":
            return [{"date": "2026-06-30", "marketCap": 1, "returnOnInvestedCapital": -0.1, "freeCashFlowYield": 0}]
        if endpoint == "ratios":
            return [{"date": "2026-06-30", "returnOnEquity": -0.2, "currentRatio": 0, "operatingProfitMargin": -0.1}]
        if endpoint == "financial-growth":
            return [{"date": "2026-06-30", "growthRevenue": 0, "growthEPS": -0.2}]
        if endpoint == "earnings":
            return [
                {"date": "2026-05-20", "fiscalDateEnding": "2026-Q1", "epsActual": 1, "epsEstimated": 0.9, "revenueActual": 10, "revenueEstimated": 9},
                {"date": "2026-09-20", "fiscalDateEnding": "2026-Q2", "epsEstimated": 1.1, "revenueEstimated": 11},
            ]
        if endpoint == "analyst-estimates":
            return [{"date": "2027-01-31", "epsAvg": -0.1, "revenueAvg": 0, "numAnalystsEps": 4}]
        if endpoint == "grades-consensus":
            return [{"consensus": "Buy", "buy": 5, "hold": 1}]
        if endpoint == "price-target-consensus":
            return [{"targetConsensus": 123, "targetHigh": 150, "targetLow": 90}]
        if endpoint == "price-target-summary":
            return [{"lastMonthAvgPriceTarget": 120, "analystCount": 8}]
        if endpoint == "grades":
            return [{"date": f"2026-08-{(index % 28) + 1:02d}", "gradingCompany": f"Firm {index}", "action": "upgrade", "newGrade": "Buy", "previousGrade": "Hold"} for index in range(40)]
        if endpoint == "institutional-ownership/symbol-positions-summary":
            return [{"symbol": symbol, "investorsHolding": 2, "reportingDate": "2026-06-30", "filingDate": "2026-08-15"}]
        if endpoint == "funds/disclosure-holders-latest":
            return [{"investorName": f"Fund {index}", "securitySymbol": symbol, "sharesNumber": index, "weightPercent": index / 1000, "marketValue": index * 10, "reportingDate": "2026-06-30", "filingDate": "2026-08-15"} for index in range(60)]
        if endpoint in {"news/stock", "news/press-releases"}:
            return [
                {"symbol": symbol, "title": f"{symbol} launches product", "site": "Example", "publishedDate": "2026-08-20", "url": "https://example.test/a"},
                {"symbol": "OTHER", "title": "Unrelated company", "site": "Example", "publishedDate": "2026-08-20", "url": "https://example.test/b"},
            ]
        raise AssertionError(endpoint)


def production_row():
    return {"ticker": "NVDA", "security_type": "EQUITY", "Recommendation": "BUY NOW", "Opportunity": 88, "Confidence": 77, "atlas_fair_value": None}


def test_cold_explicit_research_is_bounded_normalized_and_decision_immutable(tmp_path):
    client = FakeFMP()
    result = acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=client, cache_root=tmp_path)
    context = result["research_context"]
    diagnostics = result["diagnostics"]
    assert diagnostics["requests"] == 18
    assert diagnostics["requests"] <= MAX_EXPLICIT_RESEARCH_REQUESTS
    assert {params.get("symbol") or params.get("symbols") for _, params in client.calls} == {"NVDA"}
    assert not any("transcript" in endpoint for endpoint, _ in client.calls)
    assert context["production_decision"]["opportunity"] == 88
    with pytest.raises(TypeError):
        context["production_decision"]["opportunity"] = 1
    statements = context["evidence_families"]["financial_statements"]["data"]
    assert statements["income_statement"][0]["revenue"] == 0
    assert statements["income_statement"][0]["operating_income"] == -2
    assert len(context["evidence_families"]["earnings_history"]["data"]["earnings_intelligence"]["history"]) == 1
    assert len(context["evidence_families"]["analyst_actions"]["data"]["actions"]) == MAX_ANALYST_ACTIONS
    assert len(context["evidence_families"]["institutional_ownership"]["data"]["holders"]) == MAX_INSTITUTIONAL_HOLDERS
    estimates = context["evidence_families"]["analyst_estimates"]["data"]
    assert estimates["estimate_vintage_status"] == "NOT_POINT_IN_TIME_VINTAGE"
    assert estimates["estimates"][0]["eps_estimate_avg"] == -0.1
    assert estimates["estimates"][0]["revenue_estimate_avg"] == 0
    assert context["evidence_families"]["analyst_consensus_targets"]["data"]
    assert context["production_decision"]["atlas_fair_value"] is None


def test_warm_family_cache_uses_zero_provider_calls(tmp_path):
    first = FakeFMP()
    acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=first, cache_root=tmp_path)
    warm = FakeFMP()
    result = acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=warm, cache_root=tmp_path)
    assert result["diagnostics"]["requests"] == 0
    assert not warm.calls
    assert result["diagnostics"]["fresh_cache_hits"] == 12


def test_failure_is_family_scoped_and_stale_cache_preserves_timestamp(tmp_path):
    initial = FakeFMP()
    acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=initial, cache_root=tmp_path)
    path = tmp_path / "company_news" / "NVDA.latest.json"
    payload = json.loads(path.read_text())
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    payload["fetched_at"] = old
    path.write_text(json.dumps(payload))
    failing = FakeFMP(fail={"news/stock"})
    result = acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=failing, cache_root=tmp_path)
    news = result["research_context"]["evidence_families"]["company_news"]
    assert news["cache_status"] == "STALE_FALLBACK"
    assert news["fetched_at"] == old
    assert result["research_context"]["evidence_families"]["profile"]["semantic_status"] == "AVAILABLE"


def test_missing_production_ticker_keeps_evidence_but_no_decision(tmp_path):
    result = acquire_explicit_fmp_research("NVDA", production_row=None, client=FakeFMP(), cache_root=tmp_path)
    assert result["research_context"]["production_decision"] == {"semantic_status": "DATA_UNAVAILABLE"}
    assert result["research_context"]["evidence_families"]["profile"]["semantic_status"] == "AVAILABLE"


def test_ownership_summary_failure_does_not_discard_valid_fund_disclosures(tmp_path):
    client = FakeFMP(fail={"institutional-ownership/symbol-positions-summary"})
    result = acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=client, cache_root=tmp_path)
    ownership = result["research_context"]["evidence_families"]["institutional_ownership"]
    assert ownership["semantic_status"] == "AVAILABLE"
    assert ownership["data"]["summary"] == []
    assert len(ownership["data"]["holders"]) == MAX_INSTITUTIONAL_HOLDERS


def test_etf_corporate_families_fail_not_applicable(tmp_path):
    row = {"ticker": "SPY", "security_type": "ETF", "Recommendation": "HOLD"}
    client = FakeFMP()
    result = acquire_explicit_fmp_research("SPY", production_row=row, client=client, cache_root=tmp_path)
    assert [endpoint for endpoint, _ in client.calls] == ["profile"]
    for family in ("financial_statements", "earnings_history", "analyst_estimates", "company_news"):
        assert result["research_context"]["evidence_families"][family]["semantic_status"] == "NOT_APPLICABLE"


def test_sanitized_context_has_no_raw_or_secret_material(tmp_path):
    context = acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=FakeFMP(), cache_root=tmp_path)
    rendered = json.dumps(context)
    for forbidden in ("apikey", "api_key", "authenticated_url", "raw_payload", "response_body", "article body"):
        assert forbidden not in rendered.lower()


def test_first3_governance_and_yahoo_debt_are_explicit():
    assert len(EXPLICIT_RESEARCH_FMP_PRIMARY) == 16
    assert all(item.primary == FMP for item in EXPLICIT_RESEARCH_FMP_PRIMARY)
    assert all(item.authority_status == FMP_PRIMARY_YAHOO_FALLBACK for item in EXPLICIT_RESEARCH_FMP_PRIMARY)
    assert all(item.commercial_status == COMMERCIAL_LICENSE_PENDING for item in EXPLICIT_RESEARCH_FMP_PRIMARY)
    statuses = {item.stable_id: item.current_status for item in YAHOO_DEPENDENCIES}
    assert statuses["YAHOO_EXPLICIT_RESEARCH_ROW"] == LEGACY_PENDING_REMOVAL
    assert statuses["YAHOO_EXPLICIT_RESEARCH_ACTIONS"] == LEGACY_PENDING_REMOVAL
    assert yahoo_migration_metrics() == {
        "total_registered_yahoo_dependencies": 31,
        "active_yahoo_dependencies": 8,
        "active_production_yahoo_dependencies": 8,
        "active_primary_yahoo_dependencies": 7,
        "active_fallback_yahoo_dependencies": 1,
        "legacy_yahoo_dependencies": 23,
    }


def test_missing_credentials_make_zero_network_calls(tmp_path):
    result = acquire_explicit_fmp_research("NVDA", production_row=production_row(), cache_root=tmp_path)
    assert result["diagnostics"]["requests"] == 0
    assert result["research_context"]["production_decision"]["recommendation"] == "BUY NOW"


def test_canonical_context_is_available_to_research_builder_and_ask_without_calculation():
    marker = {"version": "RESEARCH_CONTEXT_V1", "evidence_families": {"profile": {"semantic_status": "AVAILABLE"}}}
    compact = _compact_context({"ticker": "NVDA", "research_context": marker})
    assert compact["research_context"] is marker
    source = inspect.getsource(atlas_research_builder_v2.build_atlas_research_v2)
    assert '"research_context": enriched_row.get("research_context") or {}' in source
