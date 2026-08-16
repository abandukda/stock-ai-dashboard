"""Shared watchlist union and dynamic monitoring-tier management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping
from uuid import uuid4

from .models import MonitoringTier, normalize_ticker


@dataclass(frozen=True)
class AlertPreference:
    enabled: bool = True
    channels: tuple[str, ...] = ()
    minimum_urgency: str = "NORMAL"


@dataclass
class Watchlist:
    watchlist_id: str
    user_id: str
    name: str
    active: bool = True
    symbols: dict[str, AlertPreference] = field(default_factory=dict)


class WatchlistRegistry:
    """In-memory contract; production persistence is defined in storage.sql."""

    def __init__(self) -> None:
        self._lists: dict[str, Watchlist] = {}

    def create(self, user_id: str, name: str) -> Watchlist:
        item = Watchlist(str(uuid4()), str(user_id), str(name))
        self._lists[item.watchlist_id] = item
        return item

    def add_symbol(self, watchlist_id: str, ticker: str, preference: AlertPreference | None = None) -> None:
        self._lists[watchlist_id].symbols[normalize_ticker(ticker)] = preference or AlertPreference()

    def remove_symbol(self, watchlist_id: str, ticker: str) -> None:
        self._lists[watchlist_id].symbols.pop(normalize_ticker(ticker), None)

    def set_active(self, watchlist_id: str, active: bool) -> None:
        self._lists[watchlist_id].active = bool(active)

    def active_symbol_union(self) -> set[str]:
        return {ticker for item in self._lists.values() if item.active for ticker in item.symbols}

    def recipients_for(self, ticker: str) -> tuple[str, ...]:
        symbol = normalize_ticker(ticker)
        return tuple(sorted({item.user_id for item in self._lists.values() if item.active and symbol in item.symbols and item.symbols[symbol].enabled}))


@dataclass(frozen=True)
class SubscriptionDelta:
    subscribe: frozenset[str]
    unsubscribe: frozenset[str]
    desired: Mapping[str, MonitoringTier]


class SubscriptionManager:
    """Unions every demand source and assigns each symbol its highest priority."""

    def __init__(self) -> None:
        self._sources: dict[str, tuple[MonitoringTier, frozenset[str]]] = {}
        self._applied: set[str] = set()

    def replace_source(self, source_id: str, tier: MonitoringTier, symbols: Iterable[str]) -> None:
        self._sources[str(source_id)] = (tier, frozenset(normalize_ticker(item) for item in symbols))

    def remove_source(self, source_id: str) -> None:
        self._sources.pop(str(source_id), None)

    def desired(self) -> dict[str, MonitoringTier]:
        result: dict[str, MonitoringTier] = {}
        for tier, symbols in self._sources.values():
            for symbol in symbols:
                result[symbol] = min(result.get(symbol, tier), tier)
        return result

    def delta(self) -> SubscriptionDelta:
        desired = self.desired()
        symbols = set(desired)
        return SubscriptionDelta(frozenset(symbols - self._applied), frozenset(self._applied - symbols), desired)

    def mark_applied(self, delta: SubscriptionDelta) -> None:
        self._applied.difference_update(delta.unsubscribe)
        self._applied.update(delta.subscribe)

    def reset_applied(self) -> None:
        """A new provider connection starts with no server-side subscriptions."""
        self._applied.clear()

    @property
    def applied_symbols(self) -> frozenset[str]:
        return frozenset(self._applied)
