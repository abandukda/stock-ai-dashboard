from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import inspect
import math

import pytest

from services.live_market.models import FeedHealth, SecurityType, TechnicalState
from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION, TechnicalConfig
from services.technical_intelligence.engine import DailyBar, MarketRegimeContext, TechnicalIntelligenceEngine
from services.technical_intelligence.evaluation import evaluate_historical_events


UTC = timezone.utc


def business_days(count: int, start: datetime | None = None):
    day = start or datetime(2025, 1, 2, 21, tzinfo=UTC)
    result = []
    while len(result) < count:
        if day.weekday() < 5:
            result.append(day)
        day += timedelta(days=1)
    return result


def setup_bars(ticker="NVDA", count=220, *, volume=1_000_000.0):
    dates = business_days(count)
    prices = []
    for index in range(count - 25):
        prices.append(50.0 * (1.0031 ** index))
    anchor = prices[-1] * 1.025
    for index in range(25):
        amplitude = 0.035 * (1.0 - index / 35.0)
        prices.append(anchor * (1.0 + amplitude * math.sin(index * math.pi / 2)))
    bars = []
    for index, (stamp, close) in enumerate(zip(dates, prices)):
        spread = close * max(0.006, 0.018 - max(0, index - (count - 25)) * 0.00045)
        current_volume = volume * (1.0 if index < count - 20 else 0.72 - (index - count + 20) * 0.008)
        bars.append(DailyBar(ticker, stamp, close * 0.998, close + spread, close - spread, close, current_volume))
    return bars


def benchmark_bars(count=220):
    dates = business_days(count)
    return [DailyBar("SPY", stamp, close, close * 1.005, close * 0.995, close, 10_000_000) for stamp, close in zip(dates, (100 - i * 0.02 for i in range(count)))]


def breakout_bars(*, high_volume=True, extension=0.02):
    bars = setup_bars()
    pivot = max(bar.high for bar in bars[-22:-2])
    multiplier = 1.0 + extension
    for offset, fraction in ((-2, multiplier - 0.008), (-1, multiplier)):
        close = pivot * fraction
        bars[offset] = replace(
            bars[offset], open=close * 0.995, high=close * 1.006, low=close * 0.99,
            close=close, volume=2_000_000 if high_volume else 500_000,
        )
    return bars


def engine():
    return TechnicalIntelligenceEngine()


def test_insufficient_history_fails_closed():
    analysis = engine().evaluate(setup_bars(count=100))
    assert analysis.result.new_state == TechnicalState.NO_SETUP
    assert analysis.result.evidence["fail_closed_reason"] == "INSUFFICIENT_HISTORY"
    assert analysis.result.score == 0


def test_trend_alignment_is_numeric_and_scored():
    analysis = engine().evaluate(setup_bars(), benchmark_bars=benchmark_bars())
    assert analysis.component_scores["trend"] >= 50
    assert analysis.result.evidence["sma50"] > analysis.result.evidence["sma200"]
    assert "sma50_above_sma200" in analysis.supporting_signals


def test_base_formation_and_tightening_range_are_detected():
    analysis = engine().evaluate(setup_bars(), benchmark_bars=benchmark_bars())
    assert analysis.component_scores["base"] >= 60
    assert analysis.result.evidence["base_range_pct"] <= TechnicalConfig().base_max_range_pct
    assert "tightening_closes" in analysis.supporting_signals
    assert analysis.result.new_state in {TechnicalState.SETUP_FORMING, TechnicalState.NEAR_BREAKOUT}


def test_resistance_is_prior_completed_bar_high_not_current_wick():
    bars = breakout_bars()
    expected = max(bar.high for bar in bars[-22:-2])
    analysis = engine().evaluate(bars)
    assert analysis.result.pivot == pytest.approx(expected, abs=0.0001)
    assert analysis.result.pivot < bars[-1].high


def test_near_breakout_uses_completed_close_proximity():
    bars = setup_bars()
    pivot = max(bar.high for bar in bars[-22:-2])
    close = pivot * 0.985
    bars[-1] = replace(bars[-1], open=close, high=close * 1.005, low=close * 0.995, close=close)
    analysis = engine().evaluate(bars, benchmark_bars=benchmark_bars())
    assert analysis.result.new_state == TechnicalState.NEAR_BREAKOUT
    assert 0 <= analysis.result.evidence["distance_to_pivot_pct"] <= 3.5
    assert analysis.result.urgency == "SIGNAL"


def test_true_breakout_requires_two_closes_volume_trend_and_liquidity():
    analysis = engine().evaluate(breakout_bars(), benchmark_bars=benchmark_bars())
    assert analysis.result.new_state == TechnicalState.BREAKOUT_CONFIRMED
    assert analysis.result.volume_confirmed is True
    assert analysis.result.urgency == "URGENT"


def test_low_volume_fake_breakout_is_not_confirmed():
    analysis = engine().evaluate(breakout_bars(high_volume=False), benchmark_bars=benchmark_bars())
    assert analysis.result.new_state != TechnicalState.BREAKOUT_CONFIRMED
    assert analysis.result.volume_confirmed is False
    assert "breakout_volume" in analysis.conflicting_signals


def test_immediate_failed_breakout_has_precedence():
    bars = setup_bars()
    pivot = max(bar.high for bar in bars[-22:-2])
    close = pivot * 0.96
    bars[-1] = replace(bars[-1], open=close * 1.01, high=close * 1.015, low=close * 0.99, close=close)
    analysis = engine().evaluate(bars, previous_state=TechnicalState.BREAKOUT_CONFIRMED)
    assert analysis.result.new_state == TechnicalState.FAILED_BREAKOUT
    assert analysis.result.urgency == "URGENT"


def test_failure_uses_persisted_prior_pivot_when_available():
    bars = setup_bars()
    explicit_pivot = bars[-1].close * 1.10
    analysis = engine().evaluate(
        bars, previous_state=TechnicalState.NEAR_BREAKOUT, prior_pivot=explicit_pivot,
    )
    assert analysis.result.new_state == TechnicalState.FAILED_BREAKOUT
    assert analysis.result.evidence["invalidation_pivot"] == pytest.approx(explicit_pivot, abs=0.0001)


def test_extension_is_not_called_fresh_breakout():
    analysis = engine().evaluate(breakout_bars(extension=0.16))
    assert analysis.result.new_state == TechnicalState.EXTENDED
    assert analysis.result.urgency == "WATCH"


def test_relative_strength_improvement_is_benchmark_evidence():
    analysis = engine().evaluate(setup_bars(), benchmark_bars=benchmark_bars())
    assert analysis.result.relative_strength == "IMPROVING"
    assert analysis.component_scores["relative_strength"] > 0


def test_missing_benchmark_reduces_coverage_without_neutral_default():
    analysis = engine().evaluate(setup_bars())
    assert analysis.result.relative_strength == "UNAVAILABLE"
    assert analysis.evidence_coverage == 0.9
    assert analysis.result.state_confidence == pytest.approx(analysis.result.score * 0.9, abs=0.02)


def test_etf_preserves_security_type_without_fundamental_inputs():
    bars = [replace(bar, ticker="XLK") for bar in setup_bars()]
    analysis = engine().evaluate(bars, security_type=SecurityType.ETF, benchmark_bars=benchmark_bars())
    assert analysis.result.security_type == SecurityType.ETF
    assert analysis.result.evidence["sector_relative_strength_20d"] is None


def test_stale_feed_suppresses_breakout_confirmation():
    analysis = engine().evaluate(breakout_bars(), feed_health=FeedHealth.DEGRADED)
    assert analysis.result.new_state == TechnicalState.NO_SETUP
    assert analysis.result.evidence["fail_closed_reason"] == "STALE_OR_UNHEALTHY_FEED"


def test_incomplete_current_bar_cannot_confirm_breakout():
    bars = breakout_bars()
    bars[-1] = replace(bars[-1], completed=False)
    analysis = engine().evaluate(bars)
    assert analysis.result.new_state == TechnicalState.NO_SETUP
    assert analysis.result.evidence["fail_closed_reason"] == "INCOMPLETE_BAR"


def test_missing_volume_fails_closed():
    bars = setup_bars()
    bars[-1] = replace(bars[-1], volume=0)
    analysis = engine().evaluate(bars)
    assert analysis.result.new_state == TechnicalState.NO_SETUP
    assert analysis.result.evidence["fail_closed_reason"] == "MISSING_REQUIRED_VOLUME"


def test_corrupt_timestamp_and_unrepairable_gap_fail_closed():
    bars = setup_bars()
    bars[-1] = replace(bars[-1], timestamp=bars[-2].timestamp)
    assert engine().evaluate(bars).result.evidence["fail_closed_reason"] == "CORRUPTED_TIMESTAMPS"
    bars = setup_bars()
    bars[-1] = replace(bars[-1], timestamp=bars[-2].timestamp + timedelta(days=8))
    assert engine().evaluate(bars).result.evidence["fail_closed_reason"] == "UNREPAIRABLE_BAR_GAP"


def test_deterministic_reproducibility_and_fingerprint_stability():
    first = engine().evaluate(breakout_bars(), benchmark_bars=benchmark_bars())
    second = engine().evaluate(breakout_bars(), benchmark_bars=benchmark_bars())
    assert first == second
    assert first.result.fingerprint == second.result.fingerprint


def test_regime_is_reported_but_does_not_change_raw_state_or_score():
    bars = breakout_bars()
    risk_on = engine().evaluate(bars, regime=MarketRegimeContext("RISK_ON", 10))
    risk_off = engine().evaluate(bars, regime=MarketRegimeContext("RISK_OFF", -10))
    assert (risk_on.result.score, risk_on.result.new_state) == (risk_off.result.score, risk_off.result.new_state)
    assert risk_off.result.evidence["regime_adjustment_applied"] is False


def test_historical_evaluation_keeps_outcomes_out_of_signal_prefix(monkeypatch):
    bars = breakout_bars()
    price = bars[-1].close
    for stamp in business_days(65, bars[-1].timestamp + timedelta(days=1)):
        price *= 1.001
        bars.append(DailyBar("NVDA", stamp, price * 0.997, price * 1.006, price * 0.994, price, 900_000))
    seen_lengths = []
    model = engine()
    original = model.evaluate

    def recording(prefix, **kwargs):
        seen_lengths.append(len(prefix))
        return original(prefix, **kwargs)

    monkeypatch.setattr(model, "evaluate", recording)
    events = evaluate_historical_events(bars, engine=model)
    assert seen_lengths
    assert max(seen_lengths) < len(bars)
    assert events
    assert set(events[-1].forward_returns) == {1, 5, 10, 20, 60}
    assert events[-1].maximum_favorable_excursion is not None
    assert events[-1].maximum_adverse_excursion is not None


def test_no_llm_state_authority_or_production_methodology_imports():
    import services.technical_intelligence.engine as module

    source = inspect.getsource(module)
    forbidden = ("openai", "anthropic", "recommendation", "opportunity_score", "atlas_fair_value", "trade_plan")
    assert not any(term in source.lower() for term in forbidden)
    assert TECHNICAL_MODEL_VERSION.endswith("PROVISIONAL")


def test_component_families_are_independently_capped_and_total_100():
    config = TechnicalConfig()
    assert sum(config.family_weights.values()) == 100
    analysis = engine().evaluate(breakout_bars(), benchmark_bars=benchmark_bars())
    assert all(0 <= value <= 100 for value in analysis.component_scores.values())
    assert 0 <= analysis.result.score <= 100


@pytest.mark.parametrize("ticker,security_type", [
    ("MSFT", SecurityType.STOCK),       # large-cap growth
    ("NVDA", SecurityType.STOCK),       # semiconductor
    ("UNH", SecurityType.STOCK),        # healthcare
    ("CAT", SecurityType.STOCK),        # industrial
    ("XOM", SecurityType.STOCK),        # energy
    ("WPM", SecurityType.STOCK),        # metals/mining
    ("KO", SecurityType.STOCK),         # lower volatility
    ("SPY", SecurityType.ETF),          # broad-market ETF
    ("XLK", SecurityType.ETF),          # sector ETF
])
def test_bounded_representative_stock_and_etf_universe(ticker, security_type):
    bars = [replace(bar, ticker=ticker) for bar in setup_bars()]
    analysis = engine().evaluate(bars, security_type=security_type, benchmark_bars=benchmark_bars())
    assert analysis.result.ticker == ticker
    assert analysis.result.security_type == security_type
    assert 0 <= analysis.result.score <= 100
