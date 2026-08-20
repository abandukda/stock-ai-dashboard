"""Canonical, provider-neutral customer entities for ATLAS Phase 9D."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any, Mapping

from services.live_market.models import SecurityType, normalize_ticker


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


class PlanTier(str, Enum):
    FREE = "FREE"
    PREMIUM = "PREMIUM"
    PRO = "PRO"
    ADMIN = "ADMIN"


class Capability(str, Enum):
    HOME = "HOME"
    TODAYS_OPPORTUNITIES = "TODAYS_OPPORTUNITIES"
    FULL_RESEARCH = "FULL_RESEARCH"
    ASK_ATLAS = "ASK_ATLAS"
    FULL_EARNINGS_INTELLIGENCE = "FULL_EARNINGS_INTELLIGENCE"
    ADVANCED_ALERTS = "ADVANCED_ALERTS"
    MARKET_MOVING_NEWS = "MARKET_MOVING_NEWS"
    BULL_RUN_RADAR = "BULL_RUN_RADAR"
    PORTFOLIO_INTELLIGENCE = "PORTFOLIO_INTELLIGENCE"
    EXPORT = "EXPORT"
    API_ACCESS = "API_ACCESS"
    ADMIN_CONTROLS = "ADMIN_CONTROLS"


class AlertType(str, Enum):
    RECOMMENDATION_CHANGED = "RECOMMENDATION_CHANGED"
    BUY_NOW_ENTERED = "BUY_NOW_ENTERED"
    BUY_NOW_EXITED = "BUY_NOW_EXITED"
    OPPORTUNITY_THRESHOLD = "OPPORTUNITY_THRESHOLD"
    CONFIDENCE_THRESHOLD = "CONFIDENCE_THRESHOLD"
    ATLAS_FV_PUBLISHED = "ATLAS_FV_PUBLISHED"
    EXPECTED_RETURN_THRESHOLD = "EXPECTED_RETURN_THRESHOLD"
    EARNINGS_APPROACHING = "EARNINGS_APPROACHING"
    EARNINGS_RESULT_AVAILABLE = "EARNINGS_RESULT_AVAILABLE"
    EARNINGS_TREND_CHANGED = "EARNINGS_TREND_CHANGED"
    ANALYST_ACTION_CHANGED = "ANALYST_ACTION_CHANGED"
    MATERIAL_COMPANY_NEWS = "MATERIAL_COMPANY_NEWS"
    RADAR_TRANSITION = "RADAR_TRANSITION"
    PRICE_THRESHOLD = "PRICE_THRESHOLD"


class NotificationChannel(str, Enum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    PUSH = "PUSH"


class AlertFrequency(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    DAILY_DIGEST = "DAILY_DIGEST"


@dataclass(frozen=True)
class Entitlements:
    version: str
    plan: PlanTier
    capabilities: frozenset[Capability]
    max_watchlists: int
    max_symbols_per_watchlist: int
    ask_atlas_daily_limit: int | None
    historical_earnings_quarters: int
    allowed_alert_types: frozenset[AlertType]
    delayed_market_data_only: bool

    def allows(self, capability: Capability) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class User:
    user_id: str
    auth_subject: str
    created_at: datetime
    disabled: bool = False

    def __post_init__(self) -> None:
        if not self.user_id or not self.auth_subject:
            raise ValueError("stable user_id and auth_subject are required")
        object.__setattr__(self, "created_at", utc(self.created_at))


@dataclass(frozen=True)
class AccountProfile:
    account_id: str
    user_id: str
    plan: PlanTier
    display_name: str = ""
    beta_cohort: str | None = None
    beta_enabled: bool = False


@dataclass(frozen=True)
class SecurityIdentity:
    security_id: str
    ticker: str
    security_type: SecurityType = SecurityType.UNKNOWN

    def __post_init__(self) -> None:
        if not self.security_id:
            raise ValueError("stable security_id is required")
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))


@dataclass(frozen=True)
class Watchlist:
    watchlist_id: str
    user_id: str
    name: str
    created_at: datetime
    is_default: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("watchlist name is required")
        object.__setattr__(self, "created_at", utc(self.created_at))


@dataclass(frozen=True)
class WatchlistSymbol:
    watchlist_id: str
    user_id: str
    security: SecurityIdentity
    added_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "added_at", utc(self.added_at))


@dataclass(frozen=True)
class QuietHours:
    start: time
    end: time
    timezone_name: str


@dataclass(frozen=True)
class NotificationPreferences:
    user_id: str
    enabled_channels: frozenset[NotificationChannel] = frozenset({NotificationChannel.IN_APP})
    default_frequency: AlertFrequency = AlertFrequency.IMMEDIATE
    quiet_hours: QuietHours | None = None


@dataclass(frozen=True)
class AlertPreference:
    preference_id: str
    user_id: str
    alert_type: AlertType
    enabled: bool = True
    ticker: str | None = None
    threshold: float | None = None
    frequency: AlertFrequency = AlertFrequency.IMMEDIATE
    channels: frozenset[NotificationChannel] = frozenset({NotificationChannel.IN_APP})

    def __post_init__(self) -> None:
        if self.ticker is not None:
            object.__setattr__(self, "ticker", normalize_ticker(self.ticker))


@dataclass(frozen=True)
class CustomerAlertEvent:
    event_id: str
    ticker: str
    alert_type: AlertType
    occurred_at: datetime
    evidence: Mapping[str, Any]
    event_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))
        object.__setattr__(self, "occurred_at", utc(self.occurred_at))


@dataclass(frozen=True)
class AlertDelivery:
    delivery_id: str
    event_fingerprint: str
    user_id: str
    channel: NotificationChannel
    status: str = "PENDING"
    attempts: int = 0


@dataclass(frozen=True)
class SavedResearch:
    saved_research_id: str
    user_id: str
    security: SecurityIdentity
    saved_at: datetime
    label: str = ""
    note: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "saved_at", utc(self.saved_at))


@dataclass(frozen=True)
class FeatureDefinition:
    feature_key: str
    rollout_percentage: int = 0
    cohort: str | None = None
    admin_only: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.rollout_percentage <= 100:
            raise ValueError("rollout percentage must be 0..100")


@dataclass(frozen=True)
class FeatureOverride:
    user_id: str
    feature_key: str
    enabled: bool
    set_by_user_id: str
