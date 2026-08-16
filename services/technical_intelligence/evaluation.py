"""Offline no-look-ahead evaluation of deterministic technical transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from services.live_market.models import FeedHealth, SecurityType, TechnicalState

from .engine import DailyBar, TechnicalIntelligenceEngine


@dataclass(frozen=True)
class EvaluationEvent:
    ticker: str
    signal_index: int
    signal_timestamp: object
    state: TechnicalState
    score: float
    forward_returns: dict[int, float | None]
    maximum_favorable_excursion: float | None
    maximum_adverse_excursion: float | None
    spy_relative_returns: dict[int, float | None]
    failed_breakout_within_20d: bool


def evaluate_historical_events(
    bars: Sequence[DailyBar],
    *,
    benchmark_bars: Sequence[DailyBar] | None = None,
    security_type: SecurityType = SecurityType.STOCK,
    engine: TechnicalIntelligenceEngine | None = None,
    signal_states: Iterable[TechnicalState] = (TechnicalState.NEAR_BREAKOUT, TechnicalState.BREAKOUT_CONFIRMED),
) -> list[EvaluationEvent]:
    """Replay prefixes only; future outcome bars never enter signal calculation."""
    model = engine or TechnicalIntelligenceEngine()
    states = set(signal_states)
    events: list[EvaluationEvent] = []
    previous_state = TechnicalState.NO_SETUP
    horizons = (1, 5, 10, 20, 60)
    for index in range(model.config.minimum_history - 1, len(bars) - 1):
        prefix = bars[:index + 1]
        benchmark_prefix = benchmark_bars[:index + 1] if benchmark_bars else None
        analysis = model.evaluate(
            prefix, security_type=security_type, previous_state=previous_state,
            benchmark_bars=benchmark_prefix, feed_health=FeedHealth.HEALTHY,
        )
        state = analysis.result.new_state
        transitioned = state != previous_state
        if transitioned and state in states:
            signal_close = bars[index].close
            forward = {
                horizon: (bars[index + horizon].close / signal_close - 1.0) if index + horizon < len(bars) else None
                for horizon in horizons
            }
            relative = {}
            for horizon in horizons:
                if benchmark_bars and index + horizon < len(bars) and index + horizon < len(benchmark_bars):
                    stock_return = forward[horizon]
                    spy_return = benchmark_bars[index + horizon].close / benchmark_bars[index].close - 1.0
                    relative[horizon] = None if stock_return is None else stock_return - spy_return
                else:
                    relative[horizon] = None
            future = bars[index + 1:min(len(bars), index + 61)]
            mfe = max((bar.high / signal_close - 1.0 for bar in future), default=None)
            mae = min((bar.low / signal_close - 1.0 for bar in future), default=None)
            failed = any(bar.close < (analysis.result.pivot or signal_close) * (1.0 - model.config.failed_breakout_buffer_pct) for bar in future[:20])
            events.append(EvaluationEvent(
                bars[index].ticker, index, bars[index].timestamp, state, analysis.result.score,
                forward, mfe, mae, relative, failed,
            ))
        previous_state = state
    return events
