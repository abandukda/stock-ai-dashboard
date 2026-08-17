from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from analysis.phase8b_calibration.calibration import AssetMetadata, HistoricalDataset, build_calibration_report
from analysis.phase8b_calibration.real_alpaca_runner import (
    DEFAULT_REQUEST_CAP, MAX_RETRIES, BarIngestionError, CoverageError,
    IngestionResult, RequestBudget, _parse_bar, fetch_daily_bars, run,
    validate_calibration_coverage,
)
from services.live_market.models import SecurityType
from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION
from services.technical_intelligence.engine import DailyBar
from tests.test_phase8b_calibration import dataset


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phase8c1-real-alpaca-calibration.yml"
UNIVERSE = ROOT / "analysis/phase8b_calibration/universe_v1.json"


def test_workflow_is_manual_only_and_cannot_write_repository():
    text = WORKFLOW.read_text()
    trigger = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger
    assert "schedule:" not in trigger
    assert "push:" not in trigger
    assert "pull_request:" not in trigger
    assert "workflow_call:" not in trigger
    assert "contents: read" in text
    assert "git commit" not in text and "git push" not in text
    assert "overnight_market_scan" not in text
    assert "python -m analysis.phase8b_calibration.real_alpaca_runner" in text
    assert "python analysis/phase8b_calibration/real_alpaca_runner.py" not in text


def test_github_style_repository_root_module_execution_imports_successfully():
    environment = dict(os.environ)
    environment.pop("APCA_API_KEY_ID", None)
    environment.pop("APCA_API_SECRET_KEY", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "analysis.phase8b_calibration.real_alpaca_runner"],
        cwd=ROOT, env=environment, text=True, capture_output=True, timeout=15,
        check=False,
    )
    assert completed.returncode == 2
    assert "MISSING_CREDENTIALS_ZERO_NETWORK_CALLS" in completed.stdout
    assert "ModuleNotFoundError" not in completed.stderr


def test_workflow_masks_environment_only_secrets_and_uploads_allowlist():
    text = WORKFLOW.read_text()
    assert "${{ secrets.APCA_API_KEY_ID }}" in text
    assert "${{ secrets.APCA_API_SECRET_KEY }}" in text
    assert "::add-mask::${APCA_API_KEY_ID}" in text
    assert "::add-mask::${APCA_API_SECRET_KEY}" in text
    assert "audit_results/phase8c1/summary.json" in text
    assert "raw" not in text.lower()
    assert "*.json" not in text and "audit_results/phase8c1/" + "\n" not in text


def test_versioned_universe_is_broad_deterministic_and_consistent():
    payload = json.loads(UNIVERSE.read_text())
    assets = payload["assets"]
    stocks = [item for item in assets if item["type"] == "STOCK"]
    etfs = [item for item in assets if item["type"] == "ETF"]
    assert payload["version"] == "ATLAS_RADAR_CALIBRATION_UNIVERSE_V1"
    assert payload["feed"] == "iex" and payload["adjustment"] == "all"
    assert len(stocks) == 60
    assert len(etfs) >= 10
    assert len({item["ticker"] for item in assets}) == len(assets)
    assert {"LARGE", "MID", "SMALL"} <= {item["cap"] for item in stocks}
    assert {"SPY", *payload["sector_benchmarks"].values()} <= {item["ticker"] for item in etfs}
    assert "survivorship" in payload["survivorship_note"].lower()


def test_request_budget_and_retry_bounds_are_hard():
    budget = RequestBudget(999)
    assert budget.cap == DEFAULT_REQUEST_CAP == 80
    budget.used = budget.cap
    with pytest.raises(RuntimeError, match="REQUEST_CAP"):
        budget.consume()
    assert MAX_RETRIES == 2


def test_missing_credentials_make_zero_network_calls(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    monkeypatch.setenv("PHASE8C_OUTPUT_DIR", str(tmp_path))
    assert run() == 2
    assert not list(tmp_path.iterdir())
    assert "ZERO_NETWORK_CALLS" in capsys.readouterr().out


def test_bulk_fetch_paginates_in_memory_without_file_writes():
    calls = []
    stamp = "2025-01-02T05:00:00Z"

    def requester(path, params, **kwargs):
        calls.append((path, dict(params)))
        token = params.get("page_token")
        return {
            "bars": {symbol: [{"t": stamp, "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 1000}] for symbol in params["symbols"].split(",")},
            "next_page_token": None if token else "second",
        }

    budget = RequestBudget(10)
    result = fetch_daily_bars(
        ("NVDA", "SPY"), start="2025-01-01", end="2025-01-03", feed="iex",
        adjustment="all", key_id="secret", secret_key="secret", budget=budget,
        requester=requester,
    )
    assert budget.used == 0  # injected requester owns no real request budget
    assert len(calls) == 2 and calls[1][1]["page_token"] == "second"
    assert set(result.bars) == {"NVDA", "SPY"}
    assert result.bars_downloaded == 4
    assert result.bars_accepted == 4


@pytest.mark.parametrize("field,value,invariant", [
    ("o", 0, "NON_POSITIVE_PRICE"),
    ("h", -1, "NON_POSITIVE_PRICE"),
    ("l", float("nan"), "NON_FINITE_VALUE"),
    ("c", None, "MISSING_REQUIRED_FIELD"),
    ("v", -1, "NEGATIVE_VOLUME"),
])
def test_real_bar_rejection_is_sanitized_and_field_specific(field, value, invariant):
    row = {"t": "2020-03-04T05:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 1000}
    row[field] = value
    with pytest.raises(BarIngestionError) as caught:
        _parse_bar("CIVI", row)
    error = caught.value
    assert error.ticker == "CIVI"
    assert error.bar_date == "2020-03-04"
    assert error.invariant == invariant
    assert error.field == {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}[field]
    assert "10.5" not in str(error)


@pytest.mark.parametrize("field,value,invariant", [
    ("h", 9.5, "HIGH_BELOW_OPEN"),
    ("l", 10.25, "LOW_ABOVE_OPEN"),
])
def test_ohlc_ordering_rejections_have_precise_categories(field, value, invariant):
    row = {"t": "2020-03-04T05:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 1000}
    row[field] = value
    with pytest.raises(BarIngestionError, match=invariant):
        _parse_bar("CIVI", row)


def test_zero_volume_and_zero_optional_fields_are_legitimate_at_ingestion():
    row = {"t": "2020-03-04T05:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 0, "n": 0, "vw": 0}
    bar = _parse_bar("CIVI", row)
    assert bar.volume == 0


def test_one_invalid_bar_quarantines_entire_security_without_deleting_only_that_bar(capsys):
    def requester(path, params, **kwargs):
        return {"bars": {"CIVI": [
            {"t": "2020-03-03T05:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 100},
            {"t": "2020-03-04T05:00:00Z", "o": 0, "h": 1, "l": 0, "c": 0.5, "v": 100},
            {"t": "2020-03-05T05:00:00Z", "o": 11, "h": 12, "l": 10, "c": 11.5, "v": 110},
        ]}, "next_page_token": None}

    result = fetch_daily_bars(
        ("CIVI",), start="2020-01-01", end="2020-04-01", feed="iex",
        adjustment="all", key_id="secret", secret_key="secret",
        budget=RequestBudget(2), requester=requester,
    )
    assert "CIVI" not in result.bars
    assert result.bars_downloaded == 3
    assert result.bars_accepted == 0
    assert result.securities_quarantined == 1
    assert len(result.violations) == 1
    output = capsys.readouterr().out
    assert '"ticker": "CIVI"' in output
    assert '"bar_date": "2020-03-04"' in output
    assert '"invariant": "NON_POSITIVE_PRICE"' in output
    assert '"action": "QUARANTINE_SECURITY_FAIL_CLOSED"' in output
    assert '"open":' not in output and '"close":' not in output


def test_multiple_invalid_securities_are_discovered_in_one_complete_pass():
    def requester(path, params, **kwargs):
        return {"bars": {
            "AAA": [{"t": "2020-01-02T05:00:00Z", "o": 0, "h": 1, "l": 0.5, "c": 0.8, "v": 10}],
            "BBB": [{"t": "2020-01-02T05:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10, "v": -1}],
            "CCC": [{"t": "2020-01-02T05:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10, "v": 10}],
        }, "next_page_token": None}

    result = fetch_daily_bars(
        ("AAA", "BBB", "CCC"), start="2020-01-01", end="2020-01-03", feed="iex",
        adjustment="all", key_id="secret", secret_key="secret",
        budget=RequestBudget(2), requester=requester,
    )
    assert result.quarantined_tickers == ("AAA", "BBB")
    assert set(result.bars) == {"CCC"}
    assert [item["invariant"] for item in result.violations] == ["NON_POSITIVE_PRICE", "NEGATIVE_VOLUME"]


def test_valid_security_history_remains_unchanged_after_other_ticker_quarantine():
    valid_rows = [
        {"t": "2020-01-02T05:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10, "v": 10},
        {"t": "2020-01-03T05:00:00Z", "o": 11, "h": 12, "l": 10, "c": 11, "v": 20},
    ]
    def requester(path, params, **kwargs):
        return {"bars": {
            "VALID": valid_rows,
            "BAD": [{"t": "2020-01-02T05:00:00Z", "o": 0, "h": 1, "l": 0, "c": 1, "v": 10}],
        }, "next_page_token": None}

    result = fetch_daily_bars(
        ("VALID", "BAD"), start="2020-01-01", end="2020-01-04", feed="iex",
        adjustment="all", key_id="secret", secret_key="secret",
        budget=RequestBudget(2), requester=requester,
    )
    assert [bar.close for bar in result.bars["VALID"]] == [10, 11]
    assert "BAD" not in result.bars


def test_quarantine_is_independent_of_future_outcomes():
    first = {"t": "2020-01-02T05:00:00Z", "o": 0, "h": 1, "l": 0, "c": 1, "v": 10}
    def collect(future_close):
        def requester(path, params, **kwargs):
            return {"bars": {"AAA": [first, {"t": "2020-01-03T05:00:00Z", "o": future_close, "h": future_close + 1, "l": future_close - 1, "c": future_close, "v": 10}]}, "next_page_token": None}
        return fetch_daily_bars(
            ("AAA",), start="2020-01-01", end="2020-01-04", feed="iex",
            adjustment="all", key_id="secret", secret_key="secret",
            budget=RequestBudget(2), requester=requester,
        )
    assert collect(10).quarantined_tickers == collect(1000).quarantined_tickers == ("AAA",)


def _coverage_fixture():
    universe = json.loads(UNIVERSE.read_text())
    bars = {item["ticker"]: [object()] * 200 for item in universe["assets"]}
    return universe, bars


def _ingestion_for_coverage(bars, violations=()):
    return IngestionResult(
        bars=bars, securities_requested=73, securities_downloaded=73,
        securities_accepted=len(bars), securities_quarantined=len({item["ticker"] for item in violations}),
        bars_downloaded=73 * 200, bars_accepted=sum(len(rows) for rows in bars.values()),
        violations=tuple(violations),
    )


def test_spy_invalidity_fails_complete_calibration():
    universe, bars = _coverage_fixture()
    bars.pop("SPY")
    with pytest.raises(CoverageError, match="SPY"):
        validate_calibration_coverage(universe, _ingestion_for_coverage(bars))


def test_required_sector_benchmark_invalidity_fails_complete_calibration():
    universe, bars = _coverage_fixture()
    bars.pop("XLK")
    with pytest.raises(CoverageError, match="REQUIRED_BENCHMARK:XLK"):
        validate_calibration_coverage(universe, _ingestion_for_coverage(bars))


def test_insufficient_post_quarantine_equity_coverage_fails_closed():
    universe, bars = _coverage_fixture()
    equities = [item["ticker"] for item in universe["assets"] if item["type"] == "STOCK"]
    for ticker in equities[:7]:
        bars.pop(ticker)
    with pytest.raises(CoverageError, match="INSUFFICIENT_ACCEPTED_EQUITIES:53<54"):
        validate_calibration_coverage(universe, _ingestion_for_coverage(bars))


def test_insufficient_sector_representation_fails_even_when_total_is_adequate():
    universe, bars = _coverage_fixture()
    technology = [item["ticker"] for item in universe["assets"] if item["type"] == "STOCK" and item["sector"] == "Technology"]
    for ticker in technology[:-1]:
        bars.pop(ticker)
    with pytest.raises(CoverageError, match="Technology=1"):
        validate_calibration_coverage(universe, _ingestion_for_coverage(bars))


def test_quarantine_audit_metadata_contains_no_ohlcv_values():
    violation = {"kind": "bar_ingestion_rejection", "ticker": "AAA", "bar_date": "2020-01-02", "invariant": "NON_POSITIVE_PRICE", "field": "low", "action": "QUARANTINE_SECURITY_FAIL_CLOSED"}
    result = _ingestion_for_coverage({"SPY": [object()] * 200}, (violation,))
    serialized = json.dumps(result.audit_metadata(), sort_keys=True)
    assert '"ticker": "AAA"' in serialized and '"bar_date": "2020-01-02"' in serialized
    assert not any(name in serialized for name in ('"open"', '"high"', '"low":', '"close"', '"volume"'))
    assert result.audit_metadata() == {
        "securities_requested": 73,
        "securities_downloaded": 73,
        "securities_accepted": 1,
        "securities_quarantined": 1,
        "bars_downloaded": 14600,
        "bars_accepted": 200,
        "invalid_bar_count": 1,
        "violations_by_invariant": {"NON_POSITIVE_PRICE": 1},
        "quarantined_tickers": ["AAA"],
        "violations": [violation],
    }


def test_no_ticker_is_hard_coded_into_quarantine_policy():
    import analysis.phase8b_calibration.real_alpaca_runner as module
    source = inspect.getsource(module)
    assert 'ticker == "T"' not in source
    assert 'ticker in {"T"' not in source


def test_later_ipo_history_aligns_to_spy_by_timestamp_without_future_leakage():
    original = dataset()
    later = original.bars["NVDA"][20:]
    data = HistoricalDataset(
        bars={"NVDA": later, "SPY": original.bars["SPY"]},
        assets={
            "NVDA": original.assets["NVDA"],
            "SPY": original.assets["SPY"],
        },
    )
    report = build_calibration_report(data)
    assert report.events
    assert all(event.timestamp >= later[0].timestamp for event in report.events)


def test_aggregate_schema_contains_required_dimensions():
    report = build_calibration_report(dataset())
    assert report.state_outcomes and report.score_buckets
    assert report.security_type_outcomes and report.sector_outcomes and report.regime_outcomes
    assert report.liquidity_outcomes and report.volatility_outcomes and report.market_cap_outcomes
    sample = next(iter(report.state_outcomes.values()))
    for horizon in (1, 5, 10, 20, 60):
        assert f"mean_return_{horizon}d" in sample
        assert f"spy_beating_rate_{horizon}d" in sample
        assert f"sector_beating_rate_{horizon}d" in sample
    assert {"failure_rate_5d", "failure_rate_10d", "failure_rate_20d", "mean_mfe_60", "mean_mae_60"} <= set(sample)


def test_baseline_runner_does_not_execute_threshold_alternatives():
    source = inspect.getsource(run)
    assert "compare_thresholds" not in source
    assert "DEFERRED_UNTIL_UNTOUCHED_V1_BASELINE_REVIEW" in source
    assert TECHNICAL_MODEL_VERSION == "BULL_RUN_RADAR_V1_PROVISIONAL"


def test_runner_has_no_production_integration_or_raw_persistence():
    import analysis.phase8b_calibration.real_alpaca_runner as module

    source = inspect.getsource(module).lower()
    forbidden = ("streamlit", "overnight_market_scan", "recommendation", "opportunity_score", "atlas_fair_value", "send_email", "git push", "git commit")
    assert not any(term in source for term in forbidden)
    assert ".parquet" not in source and "raw_payload" not in source
