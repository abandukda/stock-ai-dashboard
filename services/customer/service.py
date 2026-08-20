"""Customer application service enforcing ownership and entitlements."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from typing import Callable
from uuid import uuid4

from services.live_market.models import MonitoringTier, SecurityType

from .entitlements import entitlements_for
from .models import (
    AccountProfile, AlertPreference, AlertType, Capability, FeatureDefinition,
    FeatureOverride, NotificationPreferences, PlanTier, SavedResearch,
    SecurityIdentity, User, Watchlist, WatchlistSymbol,
)
from .repository import CustomerRepository


Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


class EntitlementError(PermissionError):
    pass


class CustomerService:
    def __init__(self, repository: CustomerRepository, *, clock: Clock | None = None, id_factory: IdFactory | None = None) -> None:
        self.repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id = id_factory or (lambda: str(uuid4()))

    def register(self, auth_subject: str, *, plan: PlanTier = PlanTier.FREE, display_name: str = "") -> tuple[User, AccountProfile]:
        existing = self.repository.user_by_auth_subject(auth_subject)
        if existing is not None:
            return existing
        user_id = self._id()
        user = User(user_id, str(auth_subject), self._clock())
        profile = AccountProfile(self._id(), user_id, plan, display_name)
        self.repository.put_user(user, profile)
        self.repository.put_notification_preferences(NotificationPreferences(user_id))
        return user, profile

    def account(self, user_id: str) -> tuple[User, AccountProfile]:
        return self.repository.get_user(user_id)

    def entitlements(self, user_id: str):
        return entitlements_for(self.account(user_id)[1].plan)

    def allows(self, user_id: str, capability: Capability) -> bool:
        return self.entitlements(user_id).allows(capability)

    def create_watchlist(self, user_id: str, name: str, *, make_default: bool = False) -> Watchlist:
        items = self.repository.list_watchlists(user_id)
        limits = self.entitlements(user_id)
        if len(items) >= limits.max_watchlists:
            raise EntitlementError("watchlist limit reached")
        if any(item.name.casefold() == str(name).strip().casefold() for item in items):
            raise ValueError("watchlist name already exists")
        make_default = bool(make_default or not items)
        if make_default:
            for item in items:
                if item.is_default:
                    self.repository.put_watchlist(replace(item, is_default=False))
        watchlist = Watchlist(self._id(), user_id, str(name).strip(), self._clock(), make_default)
        self.repository.put_watchlist(watchlist)
        return watchlist

    def rename_watchlist(self, user_id: str, watchlist_id: str, name: str) -> Watchlist:
        current = self.repository.get_watchlist(user_id, watchlist_id)
        clean = str(name).strip()
        if not clean:
            raise ValueError("watchlist name is required")
        if any(item.watchlist_id != watchlist_id and item.name.casefold() == clean.casefold() for item in self.repository.list_watchlists(user_id)):
            raise ValueError("watchlist name already exists")
        updated = replace(current, name=clean)
        self.repository.put_watchlist(updated)
        return updated

    def delete_watchlist(self, user_id: str, watchlist_id: str) -> None:
        current = self.repository.get_watchlist(user_id, watchlist_id)
        self.repository.delete_watchlist(user_id, watchlist_id)
        remaining = self.repository.list_watchlists(user_id)
        if current.is_default and remaining:
            self.repository.put_watchlist(replace(remaining[0], is_default=True))

    def set_default_watchlist(self, user_id: str, watchlist_id: str) -> Watchlist:
        selected = self.repository.get_watchlist(user_id, watchlist_id)
        for item in self.repository.list_watchlists(user_id):
            self.repository.put_watchlist(replace(item, is_default=item.watchlist_id == watchlist_id))
        return replace(selected, is_default=True)

    def add_symbol(self, user_id: str, watchlist_id: str, *, security_id: str, ticker: str, security_type: SecurityType = SecurityType.UNKNOWN) -> WatchlistSymbol:
        self.repository.get_watchlist(user_id, watchlist_id)
        existing = self.repository.list_watchlist_symbols(user_id, watchlist_id)
        if len(existing) >= self.entitlements(user_id).max_symbols_per_watchlist:
            raise EntitlementError("watchlist symbol limit reached")
        value = WatchlistSymbol(watchlist_id, user_id, SecurityIdentity(security_id, ticker, security_type), self._clock())
        if not self.repository.put_watchlist_symbol(value):
            raise ValueError("symbol already exists in watchlist")
        return value

    def remove_symbol(self, user_id: str, watchlist_id: str, security_id: str) -> None:
        self.repository.delete_watchlist_symbol(user_id, watchlist_id, security_id)

    def list_symbols(self, user_id: str, watchlist_id: str) -> tuple[WatchlistSymbol, ...]:
        return self.repository.list_watchlist_symbols(user_id, watchlist_id)

    def save_research(self, user_id: str, *, security_id: str, ticker: str, label: str = "", note: str = "", security_type: SecurityType = SecurityType.UNKNOWN) -> SavedResearch:
        value = SavedResearch(self._id(), user_id, SecurityIdentity(security_id, ticker, security_type), self._clock(), str(label), str(note))
        if not self.repository.put_saved_research(value):
            raise ValueError("research already saved")
        return value

    def set_notifications(self, user_id: str, value: NotificationPreferences) -> None:
        if value.user_id != user_id:
            raise PermissionError("notification owner mismatch")
        self.repository.put_notification_preferences(value)

    def set_alert_preference(self, user_id: str, value: AlertPreference) -> None:
        if value.user_id != user_id:
            raise PermissionError("alert owner mismatch")
        if value.alert_type not in self.entitlements(user_id).allowed_alert_types:
            raise EntitlementError("alert type is not included in this plan")
        self.repository.put_alert_preference(value)

    def set_beta(self, actor_user_id: str, target_user_id: str, *, enabled: bool, cohort: str | None = None) -> AccountProfile:
        if self.account(actor_user_id)[1].plan != PlanTier.ADMIN:
            raise PermissionError("admin required")
        profile = self.account(target_user_id)[1]
        updated = replace(profile, beta_enabled=bool(enabled), beta_cohort=cohort)
        self.repository.update_profile(updated)
        return updated

    def set_feature_override(self, actor_user_id: str, target_user_id: str, feature_key: str, enabled: bool) -> None:
        if self.account(actor_user_id)[1].plan != PlanTier.ADMIN:
            raise PermissionError("admin required")
        self.repository.put_feature_override(FeatureOverride(target_user_id, feature_key, bool(enabled), actor_user_id))

    def feature_enabled(self, user_id: str, definition: FeatureDefinition) -> bool:
        _, profile = self.account(user_id)
        override = self.repository.get_feature_override(user_id, definition.feature_key)
        if override is not None:
            return override.enabled
        if profile.plan == PlanTier.ADMIN:
            return True
        if definition.admin_only or not profile.beta_enabled:
            return False
        if definition.cohort and profile.beta_cohort != definition.cohort:
            return False
        bucket = int(hashlib.sha256(f"{definition.feature_key}:{user_id}".encode()).hexdigest()[:8], 16) % 100
        return bucket < definition.rollout_percentage

    def active_symbol_union(self) -> set[str]:
        result: set[str] = set()
        # Repository protocol intentionally avoids an unscoped customer-data
        # listing. The local adapter can expose safe aggregate demand only.
        aggregate = getattr(self.repository, "active_symbol_union", None)
        if callable(aggregate):
            result.update(aggregate())
        return result

    def apply_phase8a_demand(self, manager) -> None:
        """One demand source; Phase 8A remains the subscription authority."""
        manager.replace_source("customer-watchlists", MonitoringTier.ACTIVE_CUSTOMER, self.active_symbol_union())


__all__ = ["CustomerService", "EntitlementError"]
