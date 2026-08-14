from __future__ import annotations

import pandas as pd
import pytest

import overnight_market_scan as scan
from engines.component_builder import build_components
from engines.investment_committee_v104 import build_committee_verdict
from engines.live_research_engine import _earnings_context, _fair_value_complete
from engines.research_engine import research_navigation_state
from ui import research_report_v104


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.25, 0.25), (0.0, 0.0), (-0.12, -0.12)],
)
def test_scanner_earnings_growth_alias_preserves_signed_values(value, expected):
    fundamentals = build_components({"earnings_growth": value})["fundamentals"]
    assert fundamentals["data"]["eps_growth_pct"] == expected
    assert "eps_growth_pct" not in fundamentals["missing_fields"]


def test_presentation_earnings_growth_alias_is_supported():
    fundamentals = build_components({"Earnings Growth": 18.5})["fundamentals"]
    assert fundamentals["data"]["eps_growth_pct"] == 18.5


def test_genuinely_missing_earnings_growth_remains_unavailable():
    fundamentals = build_components({})["fundamentals"]
    assert fundamentals["data"]["eps_growth_pct"] is None
    assert "eps_growth_pct" in fundamentals["missing_fields"]


def test_available_earnings_growth_removes_false_committee_warning():
    components = build_components({"earnings_growth": 0.22})
    row = {
        "component_details": components,
        "components": {name: item.get("score") for name, item in components.items()},
        "component_coverage_pct": 60,
        "opportunity_score": 60,
        "confidence_pct": 60,
    }
    verdict = build_committee_verdict(row)
    assert all("eps growth pct" not in reason.lower() for reason in verdict["reasons_to_wait"])


@pytest.mark.parametrize("ticker", ["NVDA", "CRM"])
def test_home_cta_uses_canonical_research_navigation(monkeypatch, ticker):
    monkeypatch.setattr(research_report_v104, "inject_v104_polish_css", lambda: None)
    monkeypatch.setattr(research_report_v104, "calculate_evidence_coverage", lambda row: {"coverage_pct": 100})
    monkeypatch.setattr(research_report_v104, "calculate_validated_return", lambda row: {"label": "10.0%"})
    monkeypatch.setattr(research_report_v104, "calculate_individualized_scores", lambda row: {"opportunity_score": 70, "confidence_pct": 70})
    monkeypatch.setattr(research_report_v104, "classify_horizon", lambda row: {"primary": "Position"})
    monkeypatch.setattr(research_report_v104.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(research_report_v104.st, "button", lambda *args, **kwargs: True)
    monkeypatch.setattr(research_report_v104.st, "rerun", lambda: None)
    session = {}
    monkeypatch.setattr(research_report_v104.st, "session_state", session)

    research_report_v104.render_candidate_card({"ticker": ticker}, key_prefix="test")

    assert session == research_navigation_state(ticker)
    assert session["v73_page"] == "Research Any Ticker"
    assert session["active_research_ticker"] == ticker
    assert session["v805_force_live_on_open"] == ticker


def test_direct_research_state_contract_propagates_active_ticker():
    state = research_navigation_state(" nvda ")
    assert state["typed_ticker"] == "NVDA"
    assert state["active_research_ticker"] == "NVDA"
    assert state["v79_pending_page"] == "Research Any Ticker"


def test_live_canonical_value_does_not_masquerade_as_analyst_scenarios():
    fundamentals = {"Forward PE": 20, "Revenue Growth": 15, "Earnings Growth": 20, "Operating Margin": 25}
    analysts = {"analyst_target_mean": 120, "analyst_target_low": 100, "analyst_target_high": 140}
    result = _fair_value_complete(100, {"forwardEps": 5}, fundamentals, analysts)
    assert result["atlas_fair_value"] == 123.75
    assert "ai_bear_target" not in result
    assert "ai_base_target" not in result
    assert "ai_bull_target" not in result


def test_neutral_anchor_cannot_surface_as_canonical_fair_value():
    result = _fair_value_complete(100, {}, {}, {})
    assert result["atlas_fair_value"] is None
    assert result["Atlas Fair Value"] is None
    assert result["fair_value_status"] == "INSUFFICIENT_INPUTS"


class _YahooEarningsTicker:
    calendar = {}

    def get_earnings_dates(self, limit=8):
        index = pd.to_datetime(["2026-08-01T00:00:00Z", "2026-05-01T00:00:00Z"])
        return pd.DataFrame(
            {"Reported EPS": [0.0, -0.4], "EPS Estimate": [0.0, -0.2], "Surprise(%)": [0.0, -100.0]},
            index=index,
        )


def test_legitimate_yahoo_earnings_history_survives_normalization():
    result = _earnings_context(_YahooEarningsTicker())
    assert len(result["earnings_history"]) == 2
    assert result["earnings_history"][0]["eps_actual"] == 0.0
    assert result["earnings_history"][1]["eps_actual"] == -0.4
    assert result["reported_eps"] == 0.0


def test_runtime_timing_schema_includes_requested_aggregates():
    timings = scan._persisted_scan_timings()
    expected = {
        "yahoo_broad_scan_seconds", "yahoo_retry_count", "yahoo_backoff_seconds",
        "finalist_provider_seconds", "etf_processing_seconds", "etf_full_committee_seconds",
        "etf_newsapi_calls", "etf_newsapi_seconds",
        "etf_finnhub_news_calls", "etf_finnhub_news_seconds",
        "etf_fmp_news_calls", "etf_fmp_news_seconds",
        "etf_sec_ticker_map_seconds", "etf_sec_submissions_seconds",
        "sec_ticker_map_downloads", "output_persistence_seconds",
    }
    assert expected.issubset(timings)


def _reset_metadata_timings():
    for key in list(scan._SCAN_TIMINGS):
        scan._SCAN_TIMINGS[key] = 0 if isinstance(scan._SCAN_TIMINGS[key], int) else 0.0
    scan._YAHOO_METADATA_LATENCIES.clear()


class _MetadataTicker:
    calls = 0
    payload = {}
    error = None

    def __init__(self, symbol):
        self.symbol = symbol

    def get_info(self):
        type(self).calls += 1
        if type(self).error:
            raise type(self).error
        return dict(type(self).payload)


@pytest.mark.parametrize(
    ("payload", "error", "outcome"),
    [
        ({"shortName": "Acme", "marketCap": 123, "earningsGrowth": -0.1}, None, "successes"),
        ({}, None, "empty"),
        ({}, RuntimeError("Yahoo unavailable"), "failures"),
    ],
)
def test_metadata_instrumentation_counts_one_call_and_preserves_semantics(
    monkeypatch, payload, error, outcome
):
    _reset_metadata_timings()
    _MetadataTicker.calls = 0
    _MetadataTicker.payload = payload
    _MetadataTicker.error = error
    monkeypatch.setattr(scan.yf, "Ticker", _MetadataTicker)

    result = scan.get_metadata("TEST")

    assert _MetadataTicker.calls == 1
    assert scan._SCAN_TIMINGS["yahoo_metadata_calls"] == 1
    assert scan._SCAN_TIMINGS[f"yahoo_metadata_{outcome}"] == 1
    assert sum(
        scan._SCAN_TIMINGS[key]
        for key in ("yahoo_metadata_successes", "yahoo_metadata_empty", "yahoo_metadata_failures")
    ) == 1
    assert result["company_name"] == ("Acme" if payload else "TEST")
    assert result["market_cap"] == (123.0 if payload else None)
    assert result.get("earnings_growth") == (-0.1 if payload else None)


def test_metadata_slow_max_and_p95_are_diagnostic_only(monkeypatch):
    _reset_metadata_timings()
    _MetadataTicker.calls = 0
    _MetadataTicker.payload = {"shortName": "Acme"}
    _MetadataTicker.error = None
    monkeypatch.setattr(scan.yf, "Ticker", _MetadataTicker)
    clock = iter([10.0, 12.5])
    monkeypatch.setattr(scan.time, "monotonic", lambda: next(clock))

    result = scan.get_metadata("TEST")
    scan._finalize_yahoo_metadata_percentiles()

    assert result["company_name"] == "Acme"
    assert scan._SCAN_TIMINGS["yahoo_metadata_slow_calls"] == 1
    assert scan._SCAN_TIMINGS["yahoo_metadata_max_seconds"] == 2.5
    assert scan._SCAN_TIMINGS["yahoo_metadata_p95_seconds"] == 2.5


def test_runtime_schema_serializes_second_stage_fields():
    timings = scan._persisted_scan_timings()
    expected = {
        "scanner_total_seconds",
        "yahoo_metadata_calls",
        "yahoo_metadata_seconds",
        "yahoo_metadata_successes",
        "yahoo_metadata_failures",
        "yahoo_metadata_empty",
        "yahoo_metadata_slow_calls",
        "yahoo_metadata_max_seconds",
        "yahoo_metadata_p95_seconds",
        "broad_row_processing_seconds",
        "prescreen_ranking_seconds",
        "full_scan_construction_seconds",
        "recovery_processing_seconds",
        "universe_construction_seconds",
        "universe_persistence_seconds",
        "finalist_row_processing_seconds",
        "unattributed_seconds",
    }
    assert expected.issubset(timings)


def test_reconciliation_does_not_double_count_nested_or_retry_timings():
    _reset_metadata_timings()
    scan._SCAN_TIMINGS.update(
        {
            "yahoo_broad_scan_seconds": 40.0,
            "yahoo_backoff_seconds": 5.0,
            "etf_processing_seconds": 10.0,
            "etf_full_committee_seconds": 8.0,
            "etf_sec_ticker_map_seconds": 2.0,
            "broad_row_processing_seconds": 20.0,
        }
    )
    assert scan._reconcile_scan_timings(100.0) == 30.0
