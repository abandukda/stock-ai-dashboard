"""Provider-neutral schemas for the centralized ATLAS live-market gateway."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, time, timezone
from enum import Enum, IntEnum
import hashlib
import json
from typing import Any, Mapping
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")


class SecurityType(str, Enum):
    STOCK = "STOCK"
    ETF = "ETF"
    UNKNOWN = "UNKNOWN"


class MarketSession(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"
    OVERNIGHT = "OVERNIGHT"
    CLOSED = "CLOSED"


class FeedHealth(str, Enum):
    CONNECTING = "CONNECTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    UNAVAILABLE = "UNAVAILABLE"


class MonitoringTier(IntEnum):
    ACTIVE_CUSTOMER = 1
    ATLAS_ACTIONABLE = 2
    SCANNER_UNIVERSE = 3
    ON_DEMAND = 4


class TechnicalState(str, Enum):
    NO_SETUP = "NO_SETUP"
    SETUP_FORMING = "SETUP_FORMING"
    NEAR_BREAKOUT = "NEAR_BREAKOUT"
    BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
    EXTENDED = "EXTENDED"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def normalize_ticker(value: str) -> str:
    ticker = str(value or "").strip().upper()
    if not ticker or len(ticker) > 16 or not all(char.isalnum() or char in ".-" for char in ticker):
        raise ValueError("invalid ticker")
    return ticker


def classify_market_session(timestamp: datetime) -> MarketSession:
    local = _utc(timestamp).astimezone(EASTERN)
    if local.weekday() >= 5:
        return MarketSession.CLOSED
    wall = local.time().replace(tzinfo=None)
    if time(4, 0) <= wall < time(9, 30):
        return MarketSession.PRE_MARKET
    if time(9, 30) <= wall < time(16, 0):
        return MarketSession.REGULAR
    if time(16, 0) <= wall < time(20, 0):
        return MarketSession.AFTER_HOURS
    if wall >= time(20, 0) or wall < time(4, 0):
        return MarketSession.OVERNIGHT
    return MarketSession.CLOSED


@dataclass(frozen=True)
class MinuteBar:
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int | None = None
    vwap: float | None = None
    feed: str = "UNKNOWN"
    completed: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))
        object.__setattr__(self, "timestamp", _utc(self.timestamp))
        if min(self.open, self.high, self.low, self.close) <= 0 or self.volume < 0:
            raise ValueError("invalid OHLCV bar")
        if self.high < max(self.open, self.low, self.close) or self.low > min(self.open, self.high, self.close):
            raise ValueError("inconsistent OHLC bar")


@dataclass(frozen=True)
class MarketEvent:
    ticker: str
    event_type: str
    market_timestamp: datetime
    received_timestamp: datetime
    feed: str
    security_type: SecurityType = SecurityType.UNKNOWN
    sequence: int | None = None
    price: float | None = None
    bar: MinuteBar | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))
        object.__setattr__(self, "market_timestamp", _utc(self.market_timestamp))
        object.__setattr__(self, "received_timestamp", _utc(self.received_timestamp))
        if self.event_type not in {"trade", "bar"}:
            raise ValueError("unsupported market event")
        if self.event_type == "trade" and (self.price is None or self.price <= 0):
            raise ValueError("trade event requires a positive price")
        if self.event_type == "bar" and (self.bar is None or not self.bar.completed):
            raise ValueError("bar event requires a completed bar")

    @property
    def fingerprint(self) -> str:
        bar = self.bar
        payload = {
            "ticker": self.ticker,
            "type": self.event_type,
            "market_timestamp": self.market_timestamp.isoformat(),
            "feed": self.feed,
            "sequence": self.sequence,
            "price": self.price,
            "bar": None if bar is None else {
                "timestamp": bar.timestamp.isoformat(), "open": bar.open,
                "high": bar.high, "low": bar.low, "close": bar.close,
                "volume": bar.volume, "feed": bar.feed,
            },
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class LiveMarketState:
    """Live state only; scanner signal price and investment targets never enter this object."""

    ticker: str
    security_type: SecurityType
    live_price: float | None
    market_timestamp: datetime | None
    received_timestamp: datetime | None
    market_session: MarketSession
    feed: str
    freshness_age_seconds: float
    stale: bool
    last_completed_minute_bar: MinuteBar | None
    feed_health: FeedHealth
    last_sequence: int | None = None

    @property
    def alerts_allowed(self) -> bool:
        return not self.stale and self.feed_health == FeedHealth.HEALTHY

    def at_time(self, now: datetime, stale_after_seconds: float) -> "LiveMarketState":
        age = float("inf") if self.received_timestamp is None else max(0.0, (_utc(now) - self.received_timestamp).total_seconds())
        stale = self.stale or age > stale_after_seconds or self.feed_health != FeedHealth.HEALTHY
        health = FeedHealth.DEGRADED if stale and self.feed_health == FeedHealth.HEALTHY else self.feed_health
        return replace(self, freshness_age_seconds=age, stale=stale, feed_health=health)


def empty_live_state(ticker: str, security_type: SecurityType = SecurityType.UNKNOWN) -> LiveMarketState:
    return LiveMarketState(
        ticker=normalize_ticker(ticker), security_type=security_type, live_price=None,
        market_timestamp=None, received_timestamp=None, market_session=MarketSession.CLOSED,
        feed="UNAVAILABLE", freshness_age_seconds=float("inf"), stale=True,
        last_completed_minute_bar=None, feed_health=FeedHealth.UNAVAILABLE,
    )


def live_status_label(state: LiveMarketState, now: datetime, stale_after_seconds: float = 15.0) -> str:
    current = state.at_time(now, stale_after_seconds)
    if current.alerts_allowed:
        return f"LIVE • Updated {int(current.freshness_age_seconds)} sec ago"
    if current.market_timestamp is None:
        return "DATA UNAVAILABLE"
    stamp = current.market_timestamp.astimezone(EASTERN).strftime("%I:%M:%S %p ET").lstrip("0")
    return f"DATA DELAYED • Last update {stamp}"


@dataclass(frozen=True)
class TechnicalStateResult:
    ticker: str
    previous_state: TechnicalState
    new_state: TechnicalState
    event_timestamp: datetime
    evidence: Mapping[str, Any]
    feed_health: FeedHealth
    security_type: SecurityType = SecurityType.UNKNOWN
    score: float = 0.0
    state_confidence: float = 0.0
    pivot: float | None = None
    support: float | None = None
    volume_confirmed: bool = False
    relative_strength: str = "UNAVAILABLE"
    urgency: str = "WATCH"

    @property
    def fingerprint(self) -> str:
        """Stable deterministic transition identity; explanations are excluded."""
        payload = {
            "ticker": normalize_ticker(self.ticker),
            "security_type": self.security_type.value,
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "event_timestamp": _utc(self.event_timestamp).isoformat(),
            "score": round(float(self.score), 6),
            "pivot": None if self.pivot is None else round(float(self.pivot), 8),
            "support": None if self.support is None else round(float(self.support), 8),
            "volume_confirmed": bool(self.volume_confirmed),
            "relative_strength": self.relative_strength,
            "urgency": self.urgency,
            "evidence": dict(self.evidence),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


@dataclass(frozen=True)
class AlertEvent:
    event_id: str
    ticker: str
    previous_state: TechnicalState
    new_state: TechnicalState
    event_timestamp: datetime
    evidence: Mapping[str, Any]
    urgency: str
    event_fingerprint: str
    feed_health: FeedHealth
    recipients: tuple[str, ...] = field(default_factory=tuple)
