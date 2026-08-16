"""Reproducible walk-forward calibration for BULL_RUN_RADAR_V1_PROVISIONAL.

Raw market data is an external input and is never fetched, embedded, or written
by this module. Signal prefixes and future outcome labels remain separated.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, replace
from datetime import datetime
import math
from pathlib import Path
import statistics
from typing import Iterable, Mapping, Sequence

from services.live_market.models import FeedHealth, SecurityType, TechnicalState
from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION, TechnicalConfig
from services.technical_intelligence.engine import DailyBar, TechnicalIntelligenceEngine


HORIZONS = (1, 5, 10, 20, 60)
SCORE_BUCKETS = ((0, 45, "<45"), (45, 55, "45-54"), (55, 65, "55-64"), (65, 75, "65-74"), (75, 85, "75-84"), (85, 101, "85-100"))
ALLOWED_ADJUSTMENTS = {"raw", "split", "dividend", "all"}


@dataclass(frozen=True)
class AssetMetadata:
    ticker: str
    security_type: SecurityType
    sector: str | None = None
    market_cap_band: str | None = None
    active: bool | None = None
    adjustment: str = "all"


@dataclass(frozen=True)
class HistoricalDataset:
    bars: Mapping[str, Sequence[DailyBar]]
    assets: Mapping[str, AssetMetadata]
    benchmark_symbol: str = "SPY"
    sector_benchmarks: Mapping[str, str] | None = None

    def validate(self) -> None:
        if self.benchmark_symbol not in self.bars:
            raise ValueError("benchmark history is required")
        adjustments = {metadata.adjustment for ticker, metadata in self.assets.items() if ticker in self.bars}
        if len(adjustments) > 1:
            raise ValueError("incompatible adjustment conventions")
        for ticker, rows in self.bars.items():
            if ticker not in self.assets:
                raise ValueError(f"missing metadata for {ticker}")
            if self.assets[ticker].adjustment not in ALLOWED_ADJUSTMENTS:
                raise ValueError(f"unsupported adjustment for {ticker}")
            if any(row.ticker != ticker for row in rows):
                raise ValueError(f"mixed symbols in {ticker}")
            if any(current.timestamp <= previous.timestamp for previous, current in zip(rows, rows[1:])):
                raise ValueError(f"non-chronological bars for {ticker}")


@dataclass(frozen=True)
class CalibrationEvent:
    ticker: str
    security_type: SecurityType
    sector: str | None
    market_cap_band: str | None
    adjustment: str
    index: int
    timestamp: datetime
    prior_state: TechnicalState
    state: TechnicalState
    transition: str
    score: float
    components: Mapping[str, float]
    evidence_coverage: float
    regime: str
    liquidity_band: str
    volatility_band: str
    forward_returns: Mapping[int, float | None]
    spy_relative_returns: Mapping[int, float | None]
    sector_relative_returns: Mapping[int, float | None]
    failure_within: Mapping[int, bool | None]
    mfe_60: float | None
    mae_60: float | None
    time_to_mfe: int | None


@dataclass(frozen=True)
class CalibrationReport:
    model_version: str
    events: tuple[CalibrationEvent, ...]
    state_counts: Mapping[str, int]
    transition_counts: Mapping[str, int]
    state_outcomes: Mapping[str, Mapping[str, float | int | None]]
    score_buckets: Mapping[str, Mapping[str, float | int | None]]
    regime_outcomes: Mapping[str, Mapping[str, float | int | None]]
    security_type_outcomes: Mapping[str, Mapping[str, float | int | None]]
    sector_outcomes: Mapping[str, Mapping[str, float | int | None]]
    liquidity_outcomes: Mapping[str, Mapping[str, float | int | None]]
    volatility_outcomes: Mapping[str, Mapping[str, float | int | None]]
    market_cap_outcomes: Mapping[str, Mapping[str, float | int | None]]
    component_correlations_20d: Mapping[str, float | None]
    component_overlap: Mapping[str, Mapping[str, float | None]]
    survivorship: Mapping[str, int]


def load_alpaca_csv(path: str | Path, ticker: str) -> list[DailyBar]:
    """Load an explicitly adjustment-labeled external Alpaca CSV export."""
    output: list[DailyBar] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            output.append(DailyBar(
                ticker=ticker,
                timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
                open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                close=float(row["close"]), volume=float(row["volume"]),
            ))
    return output


def chronological_split(events: Sequence[CalibrationEvent], split_at: datetime) -> tuple[list[CalibrationEvent], list[CalibrationEvent]]:
    calibration = [event for event in events if event.timestamp < split_at]
    validation = [event for event in events if event.timestamp >= split_at]
    if calibration and validation and max(item.timestamp for item in calibration) >= min(item.timestamp for item in validation):
        raise ValueError("walk-forward overlap")
    return calibration, validation


def _aligned_prefix(reference: Sequence[DailyBar], end: datetime) -> list[DailyBar]:
    return [bar for bar in reference if bar.timestamp <= end]


def _regime(benchmark_prefix: Sequence[DailyBar]) -> str:
    if len(benchmark_prefix) < 200:
        return "UNAVAILABLE"
    closes = [bar.close for bar in benchmark_prefix]
    sma50 = statistics.fmean(closes[-50:])
    sma200 = statistics.fmean(closes[-200:])
    if closes[-1] > sma200 and sma50 > sma200:
        return "RISK_ON"
    if closes[-1] < sma200 and sma50 < sma200:
        return "RISK_OFF"
    return "NEUTRAL"


def _band(value: float, low: float, high: float) -> str:
    return "LOW" if value < low else "HIGH" if value >= high else "MEDIUM"


def _future_return(rows: Sequence[DailyBar], index: int, horizon: int) -> float | None:
    return rows[index + horizon].close / rows[index].close - 1.0 if index + horizon < len(rows) else None


def _relative_return(rows: Sequence[DailyBar], index: int, horizon: int, reference: Sequence[DailyBar]) -> float | None:
    target_time = rows[index + horizon].timestamp if index + horizon < len(rows) else None
    if target_time is None:
        return None
    mapping = {bar.timestamp: bar.close for bar in reference}
    start, end = mapping.get(rows[index].timestamp), mapping.get(target_time)
    if not start or not end:
        return None
    return _future_return(rows, index, horizon) - (end / start - 1.0)


def replay_dataset(dataset: HistoricalDataset, engine: TechnicalIntelligenceEngine | None = None) -> list[CalibrationEvent]:
    dataset.validate()
    model = engine or TechnicalIntelligenceEngine()
    events: list[CalibrationEvent] = []
    benchmark = dataset.bars[dataset.benchmark_symbol]
    interesting = set(TechnicalState) - {TechnicalState.NO_SETUP}
    for ticker, rows in dataset.bars.items():
        if ticker == dataset.benchmark_symbol:
            continue
        metadata = dataset.assets[ticker]
        prior_state = TechnicalState.NO_SETUP
        prior_pivot = None
        for index in range(model.config.minimum_history - 1, len(rows)):
            prefix = rows[:index + 1]
            benchmark_prefix = _aligned_prefix(benchmark, rows[index].timestamp)
            if len(benchmark_prefix) != len(prefix):
                continue
            sector_reference = None
            sector_symbol = (dataset.sector_benchmarks or {}).get(metadata.sector or "")
            sector_full = dataset.bars.get(sector_symbol, ()) if sector_symbol else ()
            if sector_symbol and sector_symbol in dataset.bars:
                sector_reference = _aligned_prefix(sector_full, rows[index].timestamp)
                if len(sector_reference) != len(prefix):
                    sector_reference = None
            analysis = model.evaluate(
                prefix, security_type=metadata.security_type, previous_state=prior_state,
                prior_pivot=prior_pivot, benchmark_bars=benchmark_prefix,
                sector_bars=sector_reference, feed_health=FeedHealth.HEALTHY,
            )
            state = analysis.result.new_state
            transitioned = state != prior_state
            if transitioned and state in interesting:
                forward = {h: _future_return(rows, index, h) for h in HORIZONS}
                spy_relative = {h: _relative_return(rows, index, h, benchmark) for h in HORIZONS}
                sector_relative = {h: _relative_return(rows, index, h, sector_full) for h in HORIZONS}
                failure = {}
                pivot = analysis.result.pivot or rows[index].close
                for horizon in (5, 10, 20):
                    future = rows[index + 1:min(len(rows), index + horizon + 1)]
                    failure[horizon] = None if len(future) < horizon else any(
                        bar.close < pivot * (1.0 - model.config.failed_breakout_buffer_pct) for bar in future
                    )
                future60 = rows[index + 1:min(len(rows), index + 61)]
                excursions = [(offset, bar.high / rows[index].close - 1.0, bar.low / rows[index].close - 1.0) for offset, bar in enumerate(future60, 1)]
                mfe = max((item[1] for item in excursions), default=None)
                mae = min((item[2] for item in excursions), default=None)
                time_to_mfe = max(excursions, key=lambda item: item[1])[0] if excursions else None
                atr_pct = float(analysis.result.evidence.get("atr14") or 0) / rows[index].close
                dollar_volume = statistics.fmean(bar.close * bar.volume for bar in prefix[-20:])
                events.append(CalibrationEvent(
                    ticker, metadata.security_type, metadata.sector, metadata.market_cap_band,
                    metadata.adjustment, index, rows[index].timestamp, prior_state, state,
                    f"{prior_state.value}->{state.value}", analysis.result.score,
                    analysis.component_scores, analysis.evidence_coverage, _regime(benchmark_prefix),
                    _band(dollar_volume, 10_000_000, 100_000_000), _band(atr_pct, 0.02, 0.05),
                    forward, spy_relative, sector_relative, failure, mfe, mae, time_to_mfe,
                ))
            prior_state = state
            prior_pivot = analysis.result.pivot
    return events


def _summary(events: Sequence[CalibrationEvent]) -> dict[str, float | int | None]:
    output: dict[str, float | int | None] = {"n": len(events)}
    for horizon in HORIZONS:
        returns = [event.forward_returns[horizon] for event in events if event.forward_returns[horizon] is not None]
        spy = [event.spy_relative_returns[horizon] for event in events if event.spy_relative_returns[horizon] is not None]
        sector = [event.sector_relative_returns[horizon] for event in events if event.sector_relative_returns[horizon] is not None]
        output.update({
            f"mean_return_{horizon}d": statistics.fmean(returns) if returns else None,
            f"median_return_{horizon}d": statistics.median(returns) if returns else None,
            f"positive_rate_{horizon}d": statistics.fmean(value > 0 for value in returns) if returns else None,
            f"spy_beating_rate_{horizon}d": statistics.fmean(value > 0 for value in spy) if spy else None,
            f"sector_beating_rate_{horizon}d": statistics.fmean(value > 0 for value in sector) if sector else None,
        })
    for horizon in (5, 10, 20):
        failures = [event.failure_within[horizon] for event in events if event.failure_within[horizon] is not None]
        output[f"failure_rate_{horizon}d"] = statistics.fmean(failures) if failures else None
    mfes = [event.mfe_60 for event in events if event.mfe_60 is not None]
    maes = [event.mae_60 for event in events if event.mae_60 is not None]
    times = [event.time_to_mfe for event in events if event.time_to_mfe is not None]
    output.update({
        "mean_mfe_60": statistics.fmean(mfes) if mfes else None,
        "mean_mae_60": statistics.fmean(maes) if maes else None,
        "mean_time_to_mfe": statistics.fmean(times) if times else None,
    })
    return output


def _group(events: Sequence[CalibrationEvent], key) -> dict[str, Mapping[str, float | int | None]]:
    groups: dict[str, list[CalibrationEvent]] = defaultdict(list)
    for event in events:
        groups[str(key(event))].append(event)
    return {name: _summary(rows) for name, rows in sorted(groups.items())}


def _correlation(pairs: Iterable[tuple[float, float]]) -> float | None:
    values = list(pairs)
    if len(values) < 3:
        return None
    xs, ys = zip(*values)
    if statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
        return None
    return sum((x - statistics.fmean(xs)) * (y - statistics.fmean(ys)) for x, y in values) / (len(values) * statistics.pstdev(xs) * statistics.pstdev(ys))


def build_calibration_report(dataset: HistoricalDataset, engine: TechnicalIntelligenceEngine | None = None) -> CalibrationReport:
    events = replay_dataset(dataset, engine)
    buckets = {}
    for low, high, label in SCORE_BUCKETS:
        buckets[label] = _summary([event for event in events if low <= event.score < high])
    correlations = {
        family: _correlation((event.components[family], event.forward_returns[20]) for event in events if event.forward_returns[20] is not None)
        for family in TechnicalConfig().family_weights
    }
    families = tuple(TechnicalConfig().family_weights)
    overlap = {
        left: {
            right: _correlation((event.components[left], event.components[right]) for event in events)
            for right in families
        }
        for left in families
    }
    active = Counter("unknown" if item.active is None else "active" if item.active else "inactive" for item in dataset.assets.values())
    return CalibrationReport(
        TECHNICAL_MODEL_VERSION, tuple(events),
        dict(Counter(event.state.value for event in events)),
        dict(Counter(event.transition for event in events)),
        _group(events, lambda event: event.state.value), buckets,
        _group(events, lambda event: event.regime),
        _group(events, lambda event: event.security_type.value),
        _group(events, lambda event: event.sector or "UNKNOWN"),
        _group(events, lambda event: event.liquidity_band),
        _group(events, lambda event: event.volatility_band),
        _group(events, lambda event: event.market_cap_band or "UNAVAILABLE"),
        correlations, overlap, dict(active),
    )


def compare_thresholds(dataset: HistoricalDataset, alternatives: Mapping[str, Sequence[float | int]]) -> dict[str, Mapping[str, Mapping[str, float | int | None]]]:
    """One-factor-at-a-time sensitivity; never mutates the committed V1 config."""
    output = {}
    baseline = TechnicalConfig()
    for field, values in sorted(alternatives.items()):
        output[field] = {}
        for value in values:
            config = replace(baseline, **{field: value})
            report = build_calibration_report(dataset, TechnicalIntelligenceEngine(config))
            output[field][str(value)] = _summary(report.events)
    return output
