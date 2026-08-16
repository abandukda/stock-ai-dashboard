"""Centralized provisional Phase 8B thresholds and independent-family weights."""

from dataclasses import dataclass, field


TECHNICAL_MODEL_VERSION = "BULL_RUN_RADAR_V1_PROVISIONAL"


@dataclass(frozen=True)
class TechnicalConfig:
    """Thresholds are provisional until broad, walk-forward calibration is complete."""

    minimum_history: int = 200
    pivot_lookback: int = 20
    base_lookback: int = 20
    average_volume_lookback: int = 20
    max_calendar_gap_days: int = 4
    base_max_range_pct: float = 0.18
    atr_contraction_ratio: float = 0.90
    width_contraction_ratio: float = 0.90
    near_breakout_distance_pct: float = 0.035
    breakout_max_distance_pct: float = 0.06
    breakout_relative_volume: float = 1.40
    breakout_confirmation_bars: int = 2
    failed_breakout_buffer_pct: float = 0.015
    extended_from_pivot_pct: float = 0.12
    extended_atr_from_sma20: float = 2.5
    minimum_average_dollar_volume: float = 2_000_000.0
    state_score_forming: float = 45.0
    state_score_near: float = 58.0
    family_weights: dict[str, float] = field(default_factory=lambda: {
        "trend": 25.0,
        "base": 20.0,
        "breakout": 20.0,
        "volume": 15.0,
        "momentum": 10.0,
        "relative_strength": 10.0,
    })

    def __post_init__(self) -> None:
        if round(sum(self.family_weights.values()), 8) != 100.0:
            raise ValueError("technical family weights must total 100")
