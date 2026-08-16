"""Backtestable daily-bar Bull Run Radar with deterministic state authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import statistics
from typing import Iterable, Mapping, Sequence

from services.live_market.models import (
    FeedHealth, SecurityType, TechnicalState, TechnicalStateResult, normalize_ticker,
)

from .config import TECHNICAL_MODEL_VERSION, TechnicalConfig


@dataclass(frozen=True)
class DailyBar:
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    completed: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))
        if self.timestamp.tzinfo is None:
            raise ValueError("bar timestamps must be timezone-aware")
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("bar values must be finite")
        if min(self.open, self.high, self.low, self.close) <= 0 or self.volume < 0:
            raise ValueError("invalid OHLCV")
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("inconsistent OHLC")


@dataclass(frozen=True)
class MarketRegimeContext:
    label: str = "UNAVAILABLE"
    score_adjustment: float = 0.0
    evidence: Mapping[str, float | str] | None = None


@dataclass(frozen=True)
class TechnicalAnalysis:
    result: TechnicalStateResult
    component_scores: Mapping[str, float]
    supporting_signals: tuple[str, ...]
    conflicting_signals: tuple[str, ...]
    evidence_coverage: float
    model_version: str = TECHNICAL_MODEL_VERSION


def _sma(values: Sequence[float], length: int) -> float:
    return statistics.fmean(values[-length:])


def _ema_series(values: Sequence[float], length: int) -> list[float]:
    alpha = 2.0 / (length + 1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * float(value) + (1.0 - alpha) * result[-1])
    return result


def _true_ranges(bars: Sequence[DailyBar]) -> list[float]:
    result = [bars[0].high - bars[0].low]
    for prior, current in zip(bars, bars[1:]):
        result.append(max(current.high - current.low, abs(current.high - prior.close), abs(current.low - prior.close)))
    return result


def _rsi(values: Sequence[float], length: int = 14) -> float:
    changes = [b - a for a, b in zip(values[-length - 1:-1], values[-length:])]
    gains = statistics.fmean(max(change, 0.0) for change in changes)
    losses = statistics.fmean(max(-change, 0.0) for change in changes)
    if losses == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + gains / losses))


def _round(value: float | None, places: int = 4) -> float | None:
    return None if value is None else round(float(value), places)


class TechnicalIntelligenceEngine:
    """Pure deterministic evaluator; it has no provider, LLM, UI, or investment imports."""

    def __init__(self, config: TechnicalConfig | None = None) -> None:
        self.config = config or TechnicalConfig()

    def _validate(self, bars: Sequence[DailyBar], feed_health: FeedHealth) -> tuple[bool, str | None]:
        if feed_health != FeedHealth.HEALTHY:
            return False, "STALE_OR_UNHEALTHY_FEED"
        if len(bars) < self.config.minimum_history:
            return False, "INSUFFICIENT_HISTORY"
        if not bars[-1].completed:
            return False, "INCOMPLETE_BAR"
        if any(bar.volume <= 0 for bar in bars[-self.config.average_volume_lookback:]):
            return False, "MISSING_REQUIRED_VOLUME"
        for previous, current in zip(bars, bars[1:]):
            if current.timestamp <= previous.timestamp:
                return False, "CORRUPTED_TIMESTAMPS"
            if (current.timestamp.date() - previous.timestamp.date()).days > self.config.max_calendar_gap_days:
                return False, "UNREPAIRABLE_BAR_GAP"
        if len({bar.ticker for bar in bars}) != 1:
            return False, "MIXED_TICKERS"
        return True, None

    def evaluate(
        self,
        bars: Iterable[DailyBar],
        *,
        security_type: SecurityType = SecurityType.STOCK,
        previous_state: TechnicalState = TechnicalState.NO_SETUP,
        prior_pivot: float | None = None,
        benchmark_bars: Iterable[DailyBar] | None = None,
        sector_bars: Iterable[DailyBar] | None = None,
        feed_health: FeedHealth = FeedHealth.HEALTHY,
        regime: MarketRegimeContext | None = None,
    ) -> TechnicalAnalysis:
        ordered = list(bars)
        ticker = ordered[-1].ticker if ordered else "UNKNOWN"
        event_timestamp = ordered[-1].timestamp if ordered else datetime.now(timezone.utc)
        valid, failure = self._validate(ordered, feed_health)
        if not valid:
            evidence = {"fail_closed_reason": failure, "model_version": TECHNICAL_MODEL_VERSION}
            result = TechnicalStateResult(
                ticker=ticker, previous_state=previous_state, new_state=TechnicalState.NO_SETUP,
                event_timestamp=event_timestamp, evidence=evidence, feed_health=feed_health,
                security_type=security_type, score=0.0, state_confidence=0.0,
                urgency="WATCH",
            )
            return TechnicalAnalysis(result, {name: 0.0 for name in self.config.family_weights}, (), (failure or "INVALID",), 0.0)

        closes = [bar.close for bar in ordered]
        highs = [bar.high for bar in ordered]
        lows = [bar.low for bar in ordered]
        volumes = [bar.volume for bar in ordered]
        latest = ordered[-1]
        sma20, sma50, sma200 = (_sma(closes, n) for n in (20, 50, 200))
        ema20 = _ema_series(closes, 20)[-1]
        atrs = _true_ranges(ordered)
        atr14 = _sma(atrs, 14)
        atr50 = _sma(atrs, 50)
        slope20 = (sma20 / _sma(closes[:-10], 20) - 1.0) if _sma(closes[:-10], 20) else 0.0
        slope50 = (sma50 / _sma(closes[:-20], 50) - 1.0) if _sma(closes[:-20], 50) else 0.0
        trend_flags = {
            "price_above_sma20": latest.close > sma20,
            "price_above_sma50": latest.close > sma50,
            "price_above_sma200": latest.close > sma200,
            "sma50_above_sma200": sma50 > sma200,
            "positive_average_slopes": slope20 > 0 and slope50 > 0,
            "higher_highs_lows": max(highs[-10:]) > max(highs[-20:-10]) and min(lows[-10:]) > min(lows[-20:-10]),
        }
        trend_fraction = sum(trend_flags.values()) / len(trend_flags)

        base_slice = ordered[-self.config.base_lookback:]
        base_range_pct = (max(bar.high for bar in base_slice) - min(bar.low for bar in base_slice)) / latest.close
        base_duration = max((
            length for length in range(10, min(60, len(ordered)) + 1)
            if (max(highs[-length:]) - min(lows[-length:])) / latest.close <= self.config.base_max_range_pct
        ), default=0)
        atr_contraction = atr14 / atr50 if atr50 else float("inf")
        std20 = statistics.pstdev(closes[-20:]) / sma20
        prior_std20 = statistics.pstdev(closes[-40:-20]) / _sma(closes[-40:-20], 20)
        width_contraction = std20 / prior_std20 if prior_std20 else float("inf")
        close_tightening = statistics.pstdev(closes[-5:]) < statistics.pstdev(closes[-20:])
        higher_lows = min(lows[-5:]) > min(lows[-15:-5])
        base_flags = {
            "range_compressed": base_range_pct <= self.config.base_max_range_pct,
            "atr_contracting": atr_contraction <= self.config.atr_contraction_ratio,
            "bandwidth_contracting": width_contraction <= self.config.width_contraction_ratio,
            "tightening_closes": close_tightening,
            "higher_lows": higher_lows,
            "sustained_consolidation": base_duration >= 15,
        }
        base_fraction = sum(base_flags.values()) / len(base_flags)
        base_qualified = base_fraction >= 0.6

        confirmation = self.config.breakout_confirmation_bars
        pivot_window = ordered[-self.config.pivot_lookback - confirmation:-confirmation]
        pivot = max(bar.high for bar in pivot_window)
        support = min(bar.low for bar in base_slice)
        distance_to_pivot = (pivot - latest.close) / pivot
        closes_above = all(bar.close > pivot for bar in ordered[-confirmation:])
        average_volume = _sma(volumes[:-confirmation] if confirmation else volumes[:-1], self.config.average_volume_lookback)
        confirmation_rvol = max(bar.volume / average_volume for bar in ordered[-confirmation:]) if average_volume else 0.0
        latest_rvol = latest.volume / average_volume if average_volume else 0.0
        liquid = statistics.fmean(bar.close * bar.volume for bar in ordered[-20:]) >= self.config.minimum_average_dollar_volume
        volume_confirmed = confirmation_rvol >= self.config.breakout_relative_volume
        breakout_distance = (latest.close - pivot) / pivot
        breakout_confirmed = (
            closes_above and volume_confirmed and liquid and trend_fraction >= 0.67
            and 0.0 < breakout_distance <= self.config.breakout_max_distance_pct
        )
        near_breakout = base_qualified and -0.01 <= distance_to_pivot <= self.config.near_breakout_distance_pct and trend_fraction >= 0.5

        up_volume = sum(bar.volume for prior, bar in zip(ordered[-21:-1], ordered[-20:]) if bar.close > prior.close)
        down_volume = sum(bar.volume for prior, bar in zip(ordered[-21:-1], ordered[-20:]) if bar.close < prior.close)
        dry_volume = _sma(volumes[-5:], 5) < _sma(volumes[-20:], 20)
        volume_flags = {
            "liquid": liquid,
            "constructive_accumulation": up_volume > down_volume,
            "drying_base_volume": dry_volume,
            "breakout_volume": volume_confirmed,
        }

        rsi14 = _rsi(closes)
        ema12 = _ema_series(closes, 12)
        ema26 = _ema_series(closes, 26)
        macd = ema12[-1] - ema26[-1]
        prior_macd = ema12[-6] - ema26[-6]
        roc20 = latest.close / closes[-21] - 1.0
        momentum_flags = {"constructive_rsi": 50 <= rsi14 <= 75, "macd_accelerating": macd > prior_macd, "positive_roc20": roc20 > 0}

        rs_label = "UNAVAILABLE"
        rs_fraction = None
        benchmark = list(benchmark_bars or ())
        if len(benchmark) >= 60 and len(benchmark) == len(ordered):
            ratios = [bar.close / bench.close for bar, bench in zip(ordered, benchmark) if bench.close > 0]
            if len(ratios) == len(ordered):
                rs20 = ratios[-1] / ratios[-21] - 1.0
                rs60 = ratios[-1] / ratios[-61] - 1.0
                rs_fraction = (float(rs20 > 0) + float(rs60 > 0) + float(rs20 > rs60)) / 3.0
                rs_label = "IMPROVING" if rs_fraction >= 2 / 3 else "DECLINING" if rs_fraction <= 1 / 3 else "MIXED"
        sector = list(sector_bars or ())
        sector_rs = None
        if len(sector) == len(ordered) and len(sector) >= 20:
            ratio_now = latest.close / sector[-1].close
            ratio_prior = closes[-21] / sector[-21].close
            sector_rs = ratio_now / ratio_prior - 1.0

        breakout_fraction = statistics.fmean((
            float(base_qualified), float(near_breakout), float(closes_above),
            float(0 < breakout_distance <= self.config.breakout_max_distance_pct),
        ))
        family_fractions = {
            "trend": trend_fraction,
            "base": base_fraction,
            "breakout": breakout_fraction,
            "volume": sum(volume_flags.values()) / len(volume_flags),
            "momentum": sum(momentum_flags.values()) / len(momentum_flags),
            "relative_strength": rs_fraction,
        }
        available_weight = sum(self.config.family_weights[name] for name, value in family_fractions.items() if value is not None)
        weighted = sum(self.config.family_weights[name] * value for name, value in family_fractions.items() if value is not None)
        score = 100.0 * weighted / available_weight if available_weight else 0.0
        coverage = available_weight / 100.0
        component_scores = {
            name: round(100.0 * value, 2) if value is not None else 0.0
            for name, value in family_fractions.items()
        }

        extended = breakout_distance >= self.config.extended_from_pivot_pct or latest.close >= sma20 + self.config.extended_atr_from_sma20 * atr14
        invalidation_pivot = prior_pivot if prior_pivot is not None and prior_pivot > 0 else pivot
        failed = previous_state in {TechnicalState.NEAR_BREAKOUT, TechnicalState.BREAKOUT_CONFIRMED} and latest.close < invalidation_pivot * (1.0 - self.config.failed_breakout_buffer_pct)
        if failed:
            state = TechnicalState.FAILED_BREAKOUT
        elif extended:
            state = TechnicalState.EXTENDED
        elif breakout_confirmed:
            state = TechnicalState.BREAKOUT_CONFIRMED
        elif near_breakout and score >= self.config.state_score_near:
            state = TechnicalState.NEAR_BREAKOUT
        elif base_qualified and score >= self.config.state_score_forming:
            state = TechnicalState.SETUP_FORMING
        else:
            state = TechnicalState.NO_SETUP

        urgency = "URGENT" if state in {TechnicalState.BREAKOUT_CONFIRMED, TechnicalState.FAILED_BREAKOUT} else "SIGNAL" if state == TechnicalState.NEAR_BREAKOUT else "WATCH"
        support_signals = tuple(name for group in (trend_flags, base_flags, volume_flags, momentum_flags) for name, active in group.items() if active)
        conflicts = tuple(name for group in (trend_flags, base_flags, volume_flags, momentum_flags) for name, active in group.items() if not active)
        evidence = {
            "model_version": TECHNICAL_MODEL_VERSION,
            "close": _round(latest.close), "sma20": _round(sma20), "ema20": _round(ema20),
            "sma50": _round(sma50), "sma200": _round(sma200), "slope20": _round(slope20),
            "slope50": _round(slope50), "atr14": _round(atr14), "atr_contraction": _round(atr_contraction),
            "base_range_pct": _round(base_range_pct), "width_contraction": _round(width_contraction),
            "base_duration_bars": base_duration, "pivot": _round(pivot), "support": _round(support),
            "invalidation_pivot": _round(invalidation_pivot),
            "distance_to_pivot_pct": _round(distance_to_pivot * 100), "breakout_distance_pct": _round(breakout_distance * 100),
            "relative_volume": _round(latest_rvol), "confirmation_relative_volume": _round(confirmation_rvol),
            "rsi14": _round(rsi14), "macd": _round(macd), "roc20_pct": _round(roc20 * 100),
            "relative_strength": rs_label, "sector_relative_strength_20d": _round(sector_rs),
            "liquid": liquid, "volume_confirmed": volume_confirmed, "evidence_coverage": _round(coverage),
            "market_regime": (regime or MarketRegimeContext()).label,
            "regime_adjustment_applied": False,
        }
        state_confidence = min(100.0, score * coverage)
        result = TechnicalStateResult(
            ticker=ticker, previous_state=previous_state, new_state=state,
            event_timestamp=event_timestamp, evidence=evidence, feed_health=feed_health,
            security_type=security_type, score=round(score, 2), state_confidence=round(state_confidence, 2),
            pivot=_round(pivot), support=_round(support), volume_confirmed=volume_confirmed,
            relative_strength=rs_label, urgency=urgency,
        )
        return TechnicalAnalysis(result, component_scores, support_signals, conflicts, round(coverage, 4))
