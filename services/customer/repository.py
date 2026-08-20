"""Customer-state repository protocol and deterministic local implementation.

The protocol is intentionally relational/PostgreSQL-friendly.  The in-memory
implementation is for tests and local beta validation only.
"""

from __future__ import annotations

from typing import Protocol

from .models import (
    AccountProfile, AlertDelivery, AlertPreference, CustomerAlertEvent,
    FeatureOverride, NotificationPreferences, SavedResearch, User, Watchlist,
    WatchlistSymbol,
)


class CustomerRepository(Protocol):
    def put_user(self, user: User, profile: AccountProfile) -> None: ...
    def user_by_auth_subject(self, auth_subject: str) -> tuple[User, AccountProfile] | None: ...
    def get_user(self, user_id: str) -> tuple[User, AccountProfile]: ...
    def update_profile(self, profile: AccountProfile) -> None: ...
    def list_watchlists(self, user_id: str) -> tuple[Watchlist, ...]: ...
    def get_watchlist(self, user_id: str, watchlist_id: str) -> Watchlist: ...
    def put_watchlist(self, watchlist: Watchlist) -> None: ...
    def delete_watchlist(self, user_id: str, watchlist_id: str) -> None: ...
    def list_watchlist_symbols(self, user_id: str, watchlist_id: str) -> tuple[WatchlistSymbol, ...]: ...
    def put_watchlist_symbol(self, symbol: WatchlistSymbol) -> bool: ...
    def delete_watchlist_symbol(self, user_id: str, watchlist_id: str, security_id: str) -> None: ...
    def put_notification_preferences(self, value: NotificationPreferences) -> None: ...
    def get_notification_preferences(self, user_id: str) -> NotificationPreferences | None: ...
    def put_alert_preference(self, value: AlertPreference) -> None: ...
    def list_alert_preferences(self, user_id: str) -> tuple[AlertPreference, ...]: ...
    def put_saved_research(self, value: SavedResearch) -> bool: ...
    def list_saved_research(self, user_id: str) -> tuple[SavedResearch, ...]: ...
    def delete_saved_research(self, user_id: str, saved_research_id: str) -> None: ...
    def put_feature_override(self, value: FeatureOverride) -> None: ...
    def get_feature_override(self, user_id: str, feature_key: str) -> FeatureOverride | None: ...
    def insert_event_if_absent(self, value: CustomerAlertEvent) -> bool: ...
    def insert_delivery_if_absent(self, value: AlertDelivery) -> bool: ...
    def list_deliveries(self, user_id: str) -> tuple[AlertDelivery, ...]: ...
    def active_symbol_union(self) -> set[str]: ...


class InMemoryCustomerRepository:
    """Isolated by user ID; every customer-owned lookup requires ownership."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._profiles: dict[str, AccountProfile] = {}
        self._auth_index: dict[str, str] = {}
        self._watchlists: dict[str, Watchlist] = {}
        self._symbols: dict[tuple[str, str], WatchlistSymbol] = {}
        self._notifications: dict[str, NotificationPreferences] = {}
        self._alert_preferences: dict[str, AlertPreference] = {}
        self._saved: dict[str, SavedResearch] = {}
        self._overrides: dict[tuple[str, str], FeatureOverride] = {}
        self._events: dict[str, CustomerAlertEvent] = {}
        self._deliveries: dict[tuple[str, str, str], AlertDelivery] = {}

    def _require_user(self, user_id: str) -> None:
        if user_id not in self._users:
            raise KeyError("customer not found")

    def put_user(self, user: User, profile: AccountProfile) -> None:
        existing = self._auth_index.get(user.auth_subject)
        if existing and existing != user.user_id:
            raise ValueError("authentication subject already registered")
        if profile.user_id != user.user_id:
            raise ValueError("profile owner mismatch")
        self._users[user.user_id] = user
        self._profiles[user.user_id] = profile
        self._auth_index[user.auth_subject] = user.user_id

    def user_by_auth_subject(self, auth_subject: str) -> tuple[User, AccountProfile] | None:
        user_id = self._auth_index.get(str(auth_subject))
        return None if user_id is None else self.get_user(user_id)

    def get_user(self, user_id: str) -> tuple[User, AccountProfile]:
        self._require_user(user_id)
        return self._users[user_id], self._profiles[user_id]

    def update_profile(self, profile: AccountProfile) -> None:
        self._require_user(profile.user_id)
        self._profiles[profile.user_id] = profile

    def list_watchlists(self, user_id: str) -> tuple[Watchlist, ...]:
        self._require_user(user_id)
        return tuple(sorted((item for item in self._watchlists.values() if item.user_id == user_id), key=lambda x: (not x.is_default, x.created_at, x.watchlist_id)))

    def get_watchlist(self, user_id: str, watchlist_id: str) -> Watchlist:
        self._require_user(user_id)
        item = self._watchlists.get(watchlist_id)
        if item is None or item.user_id != user_id:
            raise KeyError("watchlist not found")
        return item

    def put_watchlist(self, watchlist: Watchlist) -> None:
        self._require_user(watchlist.user_id)
        current = self._watchlists.get(watchlist.watchlist_id)
        if current is not None and current.user_id != watchlist.user_id:
            raise PermissionError("watchlist owner mismatch")
        self._watchlists[watchlist.watchlist_id] = watchlist

    def delete_watchlist(self, user_id: str, watchlist_id: str) -> None:
        self.get_watchlist(user_id, watchlist_id)
        del self._watchlists[watchlist_id]
        for key in [key for key, item in self._symbols.items() if item.watchlist_id == watchlist_id]:
            del self._symbols[key]

    def list_watchlist_symbols(self, user_id: str, watchlist_id: str) -> tuple[WatchlistSymbol, ...]:
        self.get_watchlist(user_id, watchlist_id)
        return tuple(sorted((item for item in self._symbols.values() if item.watchlist_id == watchlist_id and item.user_id == user_id), key=lambda x: x.security.ticker))

    def put_watchlist_symbol(self, symbol: WatchlistSymbol) -> bool:
        self.get_watchlist(symbol.user_id, symbol.watchlist_id)
        key = (symbol.watchlist_id, symbol.security.security_id)
        if key in self._symbols or any(
            item.watchlist_id == symbol.watchlist_id
            and item.security.ticker == symbol.security.ticker
            for item in self._symbols.values()
        ):
            return False
        self._symbols[key] = symbol
        return True

    def delete_watchlist_symbol(self, user_id: str, watchlist_id: str, security_id: str) -> None:
        self.get_watchlist(user_id, watchlist_id)
        self._symbols.pop((watchlist_id, security_id), None)

    def put_notification_preferences(self, value: NotificationPreferences) -> None:
        self._require_user(value.user_id)
        self._notifications[value.user_id] = value

    def get_notification_preferences(self, user_id: str) -> NotificationPreferences | None:
        self._require_user(user_id)
        return self._notifications.get(user_id)

    def put_alert_preference(self, value: AlertPreference) -> None:
        self._require_user(value.user_id)
        existing = self._alert_preferences.get(value.preference_id)
        if existing is not None and existing.user_id != value.user_id:
            raise PermissionError("alert preference owner mismatch")
        self._alert_preferences[value.preference_id] = value

    def list_alert_preferences(self, user_id: str) -> tuple[AlertPreference, ...]:
        self._require_user(user_id)
        return tuple(item for item in self._alert_preferences.values() if item.user_id == user_id)

    def put_saved_research(self, value: SavedResearch) -> bool:
        self._require_user(value.user_id)
        for item in self._saved.values():
            if item.user_id == value.user_id and item.security.security_id == value.security.security_id:
                return False
        self._saved[value.saved_research_id] = value
        return True

    def list_saved_research(self, user_id: str) -> tuple[SavedResearch, ...]:
        self._require_user(user_id)
        return tuple(sorted((item for item in self._saved.values() if item.user_id == user_id), key=lambda x: x.saved_at, reverse=True))

    def delete_saved_research(self, user_id: str, saved_research_id: str) -> None:
        self._require_user(user_id)
        item = self._saved.get(saved_research_id)
        if item is None or item.user_id != user_id:
            raise KeyError("saved research not found")
        del self._saved[saved_research_id]

    def put_feature_override(self, value: FeatureOverride) -> None:
        self._require_user(value.user_id)
        self._overrides[(value.user_id, value.feature_key)] = value

    def get_feature_override(self, user_id: str, feature_key: str) -> FeatureOverride | None:
        self._require_user(user_id)
        return self._overrides.get((user_id, feature_key))

    def insert_event_if_absent(self, value: CustomerAlertEvent) -> bool:
        if value.event_fingerprint in self._events:
            return False
        self._events[value.event_fingerprint] = value
        return True

    def insert_delivery_if_absent(self, value: AlertDelivery) -> bool:
        self._require_user(value.user_id)
        key = (value.event_fingerprint, value.user_id, value.channel.value)
        if key in self._deliveries:
            return False
        self._deliveries[key] = value
        return True

    def list_deliveries(self, user_id: str) -> tuple[AlertDelivery, ...]:
        self._require_user(user_id)
        return tuple(item for item in self._deliveries.values() if item.user_id == user_id)

    def active_symbol_union(self) -> set[str]:
        """Privacy-safe aggregate used solely for Phase 8A subscription demand."""
        return {item.security.ticker for item in self._symbols.values()}


__all__ = ["CustomerRepository", "InMemoryCustomerRepository"]
