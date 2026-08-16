from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import inspect

import pytest

from analysis.phase8b_calibration.calibration import (
    SCORE_BUCKETS, AssetMetadata, HistoricalDataset, build_calibration_report,
    chronological_split, compare_thresholds, replay_dataset,
)
from services.live_market.models import SecurityType, TechnicalState
from services.technical_intelligence.engine import DailyBar, TechnicalIntelligenceEngine
from tests.test_phase8b_technical_intelligence import benchmark_bars, breakout_bars, business_days, setup_bars


UTC = timezone.utc


def extend(rows, ticker, days=65, daily_return=0.001):
    output = [replace(row, ticker=ticker) for row in rows]
    price = output[-1].close
    for stamp in business_days(days, output[-1].timestamp + timedelta(days=1)):
        price *= 1 + daily_return
        output.append(DailyBar(ticker, stamp, price * 0.997, price * 1.006, price * 0.994, price, 900_000))
    return output


def dataset():
    nvda = extend(breakout_bars(), "NVDA")
    xlk = extend(setup_bars("XLK"), "XLK", daily_return=-0.0004)
    spy = benchmark_bars(len(nvda))
    return HistoricalDataset(
        bars={"NVDA": nvda, "XLK": xlk, "SPY": spy},
        assets={
            "NVDA": AssetMetadata("NVDA", SecurityType.STOCK, "Technology", "LARGE", True, "all"),
            "XLK": AssetMetadata("XLK", SecurityType.ETF, "Technology", None, True, "all"),
            "SPY": AssetMetadata("SPY", SecurityType.ETF, "Broad Market", None, True, "all"),
        },
        sector_benchmarks={"Technology": "XLK"},
    )


def test_chronological_replay_and_no_future_leakage(monkeypatch):
    data = dataset()
    model = TechnicalIntelligenceEngine()
    original = model.evaluate
    observed = []

    def recording(prefix, **kwargs):
        observed.append((prefix[-1].timestamp, len(prefix)))
        return original(prefix, **kwargs)

    monkeypatch.setattr(model, "evaluate", recording)
    events = replay_dataset(data, model)
    assert events and observed
    assert all(event.index + 1 == length for event in events for stamp, length in observed if stamp == event.timestamp)
    assert all(event.timestamp == data.bars[event.ticker][event.index].timestamp for event in events)


def test_adjustment_consistency_fails_closed():
    data = dataset()
    assets = dict(data.assets)
    assets["NVDA"] = replace(assets["NVDA"], adjustment="raw")
    with pytest.raises(ValueError, match="incompatible adjustment"):
        replace(data, assets=assets).validate()


def test_mixed_symbols_and_bad_chronology_fail_closed():
    data = dataset()
    mixed = dict(data.bars)
    mixed["NVDA"] = [*mixed["NVDA"][:-1], replace(mixed["NVDA"][-1], ticker="AMD")]
    with pytest.raises(ValueError, match="mixed symbols"):
        replace(data, bars=mixed).validate()
    reversed_rows = dict(data.bars)
    reversed_rows["NVDA"] = [*reversed_rows["NVDA"][:-2], reversed_rows["NVDA"][-1], reversed_rows["NVDA"][-2]]
    with pytest.raises(ValueError, match="non-chronological"):
        replace(data, bars=reversed_rows).validate()


def test_score_buckets_are_complete_and_non_overlapping():
    assert [label for _, _, label in SCORE_BUCKETS] == ["<45", "45-54", "55-64", "65-74", "75-84", "85-100"]
    for score in range(101):
        assert sum(low <= score < high for low, high, _ in SCORE_BUCKETS) == 1
    report = build_calibration_report(dataset())
    assert set(report.score_buckets) == {item[2] for item in SCORE_BUCKETS}
    assert all(f"mean_return_{horizon}d" in report.score_buckets["75-84"] for horizon in (1, 5, 10, 20, 60))


def test_outcome_maturation_preserves_unavailable_horizons():
    data = dataset()
    shortened = replace(data, bars={ticker: rows[:225] for ticker, rows in data.bars.items()})
    report = build_calibration_report(shortened)
    assert report.events
    early = report.events[0]
    late = report.events[-1]
    assert set(early.forward_returns) == {1, 5, 10, 20, 60}
    assert any(value is None for value in late.forward_returns.values())


def test_walk_forward_split_has_no_temporal_overlap():
    events = build_calibration_report(dataset()).events
    split_at = sorted(event.timestamp for event in events)[len(events) // 2]
    calibration, validation = chronological_split(events, split_at)
    assert all(event.timestamp < split_at for event in calibration)
    assert all(event.timestamp >= split_at for event in validation)
    assert {(event.ticker, event.timestamp) for event in calibration}.isdisjoint(
        {(event.ticker, event.timestamp) for event in validation}
    )


def test_threshold_comparison_is_reproducible_and_does_not_mutate_v1():
    alternatives = {"breakout_relative_volume": (1.2, 1.4), "state_score_near": (55, 58)}
    first = compare_thresholds(dataset(), alternatives)
    second = compare_thresholds(dataset(), alternatives)
    assert first == second
    assert TechnicalIntelligenceEngine().config.breakout_relative_volume == 1.4
    assert TechnicalIntelligenceEngine().config.state_score_near == 58


def test_state_and_transition_counts_reconcile():
    report = build_calibration_report(dataset())
    assert sum(report.state_counts.values()) == len(report.events)
    assert sum(report.transition_counts.values()) == len(report.events)
    assert any("->" in transition for transition in report.transition_counts)


def test_etf_and_sector_segmentation_are_explicit():
    report = build_calibration_report(dataset())
    assert "STOCK" in report.security_type_outcomes
    assert "ETF" in report.security_type_outcomes
    assert "Technology" in report.sector_outcomes
    assert report.liquidity_outcomes and report.volatility_outcomes and report.market_cap_outcomes
    etf_events = [event for event in report.events if event.security_type == SecurityType.ETF]
    assert etf_events


def test_regime_segmentation_and_sector_relative_outcomes_exist():
    report = build_calibration_report(dataset())
    assert report.regime_outcomes
    assert all(event.regime in {"RISK_ON", "NEUTRAL", "RISK_OFF", "UNAVAILABLE"} for event in report.events)
    stock_events = [event for event in report.events if event.ticker == "NVDA"]
    assert any(any(value is not None for value in event.sector_relative_returns.values()) for event in stock_events)


def test_failed_breakout_measurement_and_excursions_are_outcomes_only():
    events = build_calibration_report(dataset()).events
    mature = [event for event in events if event.failure_within[20] is not None]
    assert mature
    assert all(set(event.failure_within) == {5, 10, 20} for event in events)
    assert all(event.mfe_60 is not None and event.mae_60 is not None for event in mature)


def test_component_contribution_and_overlap_matrices_are_complete():
    report = build_calibration_report(dataset())
    families = {"trend", "base", "breakout", "volume", "momentum", "relative_strength"}
    assert set(report.component_correlations_20d) == families
    assert set(report.component_overlap) == families
    assert all(set(row) == families for row in report.component_overlap.values())


def test_no_production_methodology_or_provider_imports():
    import analysis.phase8b_calibration.calibration as module

    source = inspect.getsource(module).lower()
    forbidden = ("overnight_market_scan", "recommendation", "opportunity_score", "atlas_fair_value", "alpaca_trade_api", "requests.get")
    assert not any(term in source for term in forbidden)
