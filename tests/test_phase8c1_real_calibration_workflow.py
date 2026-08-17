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
    DEFAULT_REQUEST_CAP, MAX_RETRIES, RequestBudget, fetch_daily_bars, run,
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
    assert set(result) == {"NVDA", "SPY"}


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
