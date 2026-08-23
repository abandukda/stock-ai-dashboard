from __future__ import annotations

import copy
import json

import pandas as pd

import overnight_market_scan as scanner
import services.deep_research_cache as research_cache
from engines.fmp_normalization import normalize_fund_disclosure
from services.fmp_shadow_research import (
    FMP_SHADOW_MAX_ANALYST_ACTIONS,
    FMP_SHADOW_MAX_INSTITUTIONAL_HOLDERS,
    build_fmp_shadow_research,
    build_provider_comparison,
)


class _Result:
    def __init__(self, payload, outcome="SUCCESS"):
        self.payload = payload
        self.outcome = outcome
        self.fetched_at = "2026-08-22T12:00:00Z"
        self.attempts = 1


class _Client:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        value = self.payloads.get(endpoint, [])
        return value if isinstance(value, _Result) else _Result(value)


def _relevant(*_args):
    return True


def _payloads(action_count=80, holder_count=120):
    actions = [
        {
            "date": f"2026-{1 + (index % 8):02d}-{1 + (index % 27):02d}",
            "gradingCompany": f"Firm {index:03d}",
            "action": "upgrade",
            "previousGrade": "Hold",
            "newGrade": "Buy",
        }
        for index in range(action_count)
    ]
    holders = [
        {
            "investor": f"Fund {index:03d}",
            "holderCik": f"{index:010d}",
            "ticker": "NVDA",
            "issuerName": "NVIDIA",
            "cusipNumber": f"CUSIP{index:04d}",
            "sharesHeld": index * 10,
            "portfolioWeightPercentage": None if index % 3 == 0 else index / 1000,
            "marketValueUSD": None if index % 5 == 0 else index * 1000,
            "reportingPeriod": "2026-06-30",
            "filedAt": "2026-08-14",
        }
        for index in range(holder_count)
    ]
    return {
        "analyst-estimates": [{"date": "2027-01-31", "epsAvg": 1}],
        "grades-consensus": [{"consensus": "Buy"}],
        "grades": actions,
        "price-target-consensus": [{"targetConsensus": 100}],
        "price-target-summary": [{"lastMonthAvgPriceTarget": 99}],
        "institutional-ownership/symbol-positions-summary": [],
        "funds/disclosure-holders-latest": holders,
        "news/stock": [],
        "news/press-releases": [],
    }


def test_actions_and_holders_are_deterministically_bounded_after_normalization(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    result = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant,
        client=_Client(_payloads()),
    )
    analyst = result["families"]["fmp_shadow_analyst"]
    ownership = result["families"]["fmp_shadow_fund_disclosures"]
    assert len(analyst["actions"]) == FMP_SHADOW_MAX_ANALYST_ACTIONS == 25
    assert len(ownership["holders"]) == FMP_SHADOW_MAX_INSTITUTIONAL_HOLDERS == 50
    assert analyst["actions"] == sorted(
        analyst["actions"],
        key=lambda item: (item["date"], item["firm"], item["action"], item["from_grade"], item["to_grade"]),
        reverse=True,
    )
    assert ownership["holders"][0]["weight"] is not None
    action_counts = result["diagnostics"]["families"]["fmp_shadow_analyst"]["row_counts"]["actions"]
    holder_counts = result["diagnostics"]["families"]["fmp_shadow_fund_disclosures"]["row_counts"]["holders"]
    assert action_counts == {
        "provider_rows_returned": 80, "normalized_rows": 80,
        "retained_rows": 25, "discarded_by_cap": 55,
    }
    assert holder_counts == {
        "provider_rows_returned": 120, "normalized_rows": 120,
        "retained_rows": 50, "discarded_by_cap": 70,
    }


def test_phase2b_ownership_aliases_preserve_filing_gate_and_missing_is_not_invented():
    row = normalize_fund_disclosure({
        "investor": "Example Fund", "holderCik": "123", "ticker": "NVDA",
        "issuerName": "NVIDIA", "cusipNumber": "67066G104", "sharesHeld": 0,
        "portfolioWeightPercentage": 0, "marketValueUSD": -1,
        "reportingPeriod": "2026-06-30", "filedAt": "2026-08-14",
    })
    assert row["investor_name"] == "Example Fund"
    assert row["security_symbol"] == "NVDA"
    assert row["shares"] == 0 and row["weight"] == 0 and row["market_value"] == -1
    assert row["reporting_date"] == "2026-06-30"
    assert row["filing_date"] == row["evidence_available_from"] == "2026-08-14"
    assert row["provenance"]["semantic_status"] == "AVAILABLE"
    missing = normalize_fund_disclosure({
        "investor": "Example Fund", "ticker": "NVDA", "reportingPeriod": "2026-06-30",
    })
    assert missing["filing_date"] is None
    assert missing["evidence_available_from"] is None
    assert missing["provenance"]["semantic_status"] == "DATA_UNAVAILABLE"
    proven_current = normalize_fund_disclosure({
        "holder": "Current Stable Fund", "cik": "123", "shares": 10,
        "dateReported": "2026-06-30", "weightPercent": 1.25,
    })
    assert proven_current["reporting_date"] == "2026-06-30"
    assert proven_current["weight"] == 1.25
    assert proven_current["filing_date"] is None
    assert proven_current["availability_limitation"] == "FILING_DATE_UNAVAILABLE"
    assert proven_current["provenance"]["semantic_status"] == "DATA_UNAVAILABLE"


def test_sanitized_outcomes_and_cache_timing_are_reported_without_sensitive_content(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    payloads = _payloads(1, 1)
    payloads["institutional-ownership/symbol-positions-summary"] = _Result(
        None, "AUTHORIZATION_OR_ENTITLEMENT_FAILURE"
    )
    result = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="do-not-leak", relevance_check=_relevant,
        client=_Client(payloads),
    )
    ownership = result["diagnostics"]["families"]["fmp_shadow_ownership_summary"]
    assert ownership["outcomes"] == {
        "institutional-ownership/symbol-positions-summary": "AUTHORIZATION_OR_ENTITLEMENT_FAILURE"
    }
    assert ownership["calls"] == ownership["live_fetches"] == ownership["unavailable"] == 1
    assert result["diagnostics"]["fmp_shadow_seconds"] >= 0
    rendered = json.dumps(result)
    assert "do-not-leak" not in rendered
    assert "raw_payload" not in rendered and "exception" not in rendered.lower()


def test_fresh_cache_has_zero_provider_calls_and_explicit_cache_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    client = _Client(_payloads(1, 1))
    build_fmp_shadow_research("NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=client)
    cached = build_fmp_shadow_research("NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant, client=client)
    assert len(client.calls) == 9
    for diagnostic in cached["diagnostics"]["families"].values():
        assert diagnostic["calls"] == diagnostic["live_fetches"] == 0
        assert diagnostic["fresh_cache_hits"] == 1


def test_bounded_shadow_payload_and_provider_comparison_remain_valid(tmp_path, monkeypatch):
    monkeypatch.setattr(research_cache, "CACHE_ROOT", tmp_path)
    result = build_fmp_shadow_research(
        "NVDA", "NVIDIA", api_key="secret", relevance_check=_relevant,
        client=_Client(_payloads(10_000, 18_000)),
    )
    # Count-bounded structured evidence prevents the Run #291 row explosion.
    assert len(result["families"]["fmp_shadow_analyst"]["actions"]) == 25
    assert len(result["families"]["fmp_shadow_fund_disclosures"]["holders"]) == 50
    assert len(json.dumps(result, sort_keys=True)) < 150_000
    comparison = build_provider_comparison({}, result)
    assert comparison["mode"] == "DIAGNOSTIC_NO_WINNER_SELECTION"
    assert comparison["analyst"]["actions"] == "ONLY_FMP_AVAILABLE"
    assert comparison["ownership"]["semantic_note"] == "INSTITUTIONAL_AND_INSIDER_EVIDENCE_REMAIN_SEPARATE"


def test_scanner_accumulates_fmp_subset_without_changing_investment_fields(monkeypatch):
    investment_keys = (
        "opportunity_score", "confidence_pct", "recommendation", "atlas_fair_value",
        "decision_expected_return_pct", "decision_valuation_target", "entry_price",
        "stop_loss", "target_1", "target_2", "position_size_pct",
    )
    row = {"ticker": "NVDA", **{key: index for index, key in enumerate(investment_keys)}}
    before = copy.deepcopy(row)
    shadow = {
        "provider": "FMP", "mode": "RESEARCH_ONLY_SHADOW", "families": {}, "freshness": {},
        "diagnostics": {"fmp_shadow_seconds": 1.5, "families": {}},
    }
    monkeypatch.setattr(scanner, "FAST_CRON_MODE", True)
    monkeypatch.setattr(scanner, "FAST_CRON_SKIP_PRE_RANK_DEEP_APIS", True)
    monkeypatch.setattr(scanner, "v421_should_run_full_research", lambda *_args: True)
    monkeypatch.setattr(scanner, "get_finalist_enrichment", lambda *_args: ({}, {}))
    monkeypatch.setattr(scanner, "build_fmp_shadow_research", lambda *_args, **_kwargs: shadow)
    monkeypatch.setattr(scanner, "build_provider_comparison", lambda *_args: {"mode": "DIAGNOSTIC_NO_WINNER_SELECTION"})
    monkeypatch.setattr(scanner, "merge_finalist_enrichment", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scanner, "v42_build_committee_safe", lambda _symbol, candidate, *_args: candidate)
    monkeypatch.setattr(scanner, "v42_apply_investor_translations_safe", lambda candidate: candidate)
    before_seconds = scanner._SCAN_TIMINGS["fmp_shadow_seconds"]
    before_finalist = scanner._SCAN_TIMINGS["finalist_provider_seconds"]
    before_reconciliation = scanner._reconcile_scan_timings(100.0)
    output = scanner.v421_apply_tiered_committee("NVDA", row, {"company_name": "NVIDIA"}, {}, pd.DataFrame())
    assert {key: output[key] for key in investment_keys} == {key: before[key] for key in investment_keys}
    assert scanner._SCAN_TIMINGS["fmp_shadow_seconds"] == before_seconds + 1.5
    finalist_delta = scanner._SCAN_TIMINGS["finalist_provider_seconds"] - before_finalist
    assert scanner._reconcile_scan_timings(100.0) == before_reconciliation - finalist_delta
