"""Single-owner provider-neutral live-market gateway orchestration."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Awaitable, Callable, Iterable, Protocol

from .models import (
    FeedHealth, LiveMarketState, MarketEvent, MinuteBar, SecurityType,
    classify_market_session, empty_live_state, normalize_ticker,
)
from .subscriptions import SubscriptionManager


class MarketStreamClient(Protocol):
    async def connect(self, feed: str) -> None: ...
    async def disconnect(self) -> None: ...
    async def subscribe(self, symbols: Iterable[str]) -> None: ...
    async def unsubscribe(self, symbols: Iterable[str]) -> None: ...
    def events(self) -> AsyncIterator[MarketEvent]: ...
    async def repair_completed_bars(self, ticker: str, start: datetime, end: datetime) -> list[MinuteBar]: ...


class TechnicalIntelligenceSink(Protocol):
    async def on_completed_bar(self, bar: MinuteBar, live_state: LiveMarketState) -> None: ...


class LiveStateStore(Protocol):
    def get(self, ticker: str) -> LiveMarketState | None: ...
    def upsert(self, state: LiveMarketState) -> None: ...
    def all(self) -> tuple[LiveMarketState, ...]: ...


class InMemoryLiveStateStore:
    def __init__(self) -> None:
        self._states: dict[str, LiveMarketState] = {}

    def get(self, ticker: str) -> LiveMarketState | None:
        return self._states.get(normalize_ticker(ticker))

    def upsert(self, state: LiveMarketState) -> None:
        self._states[state.ticker] = state

    def all(self) -> tuple[LiveMarketState, ...]:
        return tuple(self._states.values())


class NullTechnicalSink:
    async def on_completed_bar(self, bar: MinuteBar, live_state: LiveMarketState) -> None:
        return None


class LiveMarketGateway:
    """Own exactly one stream client and normalize all users' symbol demand."""

    def __init__(
        self,
        client: MarketStreamClient,
        subscriptions: SubscriptionManager,
        state_store: LiveStateStore | None = None,
        technical_sink: TechnicalIntelligenceSink | None = None,
        *,
        feed: str = "iex",
        stale_after_seconds: float = 15.0,
        dedupe_capacity: int = 50_000,
        max_repair_gap_minutes: int = 30,
    ) -> None:
        self.client = client
        self.subscriptions = subscriptions
        self.state_store = state_store or InMemoryLiveStateStore()
        self.technical_sink = technical_sink or NullTechnicalSink()
        self.feed = feed
        self.stale_after_seconds = stale_after_seconds
        self.dedupe_capacity = dedupe_capacity
        self.max_repair_gap_minutes = max_repair_gap_minutes
        self.feed_health = FeedHealth.DISCONNECTED
        self.connection_attempts = 0
        self.duplicate_events = 0
        self.out_of_order_events = 0
        self.repaired_bars = 0
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._stop = asyncio.Event()

    async def sync_subscriptions(self) -> None:
        delta = self.subscriptions.delta()
        if delta.unsubscribe:
            await self.client.unsubscribe(sorted(delta.unsubscribe))
        if delta.subscribe:
            await self.client.subscribe(sorted(delta.subscribe))
            for ticker in delta.subscribe:
                if self.state_store.get(ticker) is None:
                    self.state_store.upsert(empty_live_state(ticker))
        self.subscriptions.mark_applied(delta)

    def _remember(self, fingerprint: str) -> bool:
        if fingerprint in self._seen:
            self._seen.move_to_end(fingerprint)
            return False
        self._seen[fingerprint] = None
        if len(self._seen) > self.dedupe_capacity:
            self._seen.popitem(last=False)
        return True

    @staticmethod
    def _gap(previous: MinuteBar, current: MinuteBar, maximum_minutes: int) -> tuple[datetime, datetime] | None:
        delta = current.timestamp - previous.timestamp
        same_session = classify_market_session(previous.timestamp) == classify_market_session(current.timestamp)
        same_day = previous.timestamp.astimezone(timezone.utc).date() == current.timestamp.astimezone(timezone.utc).date()
        if same_session and same_day and timedelta(minutes=1) < delta <= timedelta(minutes=maximum_minutes):
            return previous.timestamp + timedelta(minutes=1), current.timestamp - timedelta(minutes=1)
        return None

    async def process_event(self, event: MarketEvent, *, permit_repair: bool = True) -> bool:
        if not self._remember(event.fingerprint):
            self.duplicate_events += 1
            return False
        prior = self.state_store.get(event.ticker) or empty_live_state(event.ticker, event.security_type)
        if prior.market_timestamp and event.market_timestamp < prior.market_timestamp and event.event_type == "trade":
            self.out_of_order_events += 1
            return False

        bar = event.bar if event.event_type == "bar" else prior.last_completed_minute_bar
        if event.event_type == "bar" and event.bar is not None and prior.last_completed_minute_bar is not None:
            if event.bar.timestamp <= prior.last_completed_minute_bar.timestamp:
                self.out_of_order_events += 1
                return False
            gap = self._gap(prior.last_completed_minute_bar, event.bar, self.max_repair_gap_minutes)
            if gap and permit_repair:
                repaired = await self.client.repair_completed_bars(event.ticker, gap[0], gap[1])
                for item in sorted(repaired, key=lambda value: value.timestamp):
                    if item.ticker != event.ticker or not (gap[0] <= item.timestamp <= gap[1]):
                        continue
                    repair_event = MarketEvent(
                        ticker=item.ticker, event_type="bar", market_timestamp=item.timestamp,
                        received_timestamp=event.received_timestamp, feed=item.feed,
                        security_type=event.security_type, bar=item,
                    )
                    if await self.process_event(repair_event, permit_repair=False):
                        self.repaired_bars += 1
                prior = self.state_store.get(event.ticker) or prior

        live_price = event.price if event.event_type == "trade" else (event.bar.close if event.bar else prior.live_price)
        state = LiveMarketState(
            ticker=event.ticker,
            security_type=event.security_type if event.security_type != SecurityType.UNKNOWN else prior.security_type,
            live_price=live_price,
            market_timestamp=event.market_timestamp,
            received_timestamp=event.received_timestamp,
            market_session=classify_market_session(event.market_timestamp),
            feed=event.feed,
            freshness_age_seconds=0.0,
            stale=False,
            last_completed_minute_bar=bar,
            feed_health=FeedHealth.HEALTHY,
            last_sequence=event.sequence if event.sequence is not None else prior.last_sequence,
        )
        self.state_store.upsert(state)
        if event.event_type == "bar" and event.bar is not None:
            await self.technical_sink.on_completed_bar(event.bar, state)
        return True

    def mark_disconnected(self) -> None:
        self.feed_health = FeedHealth.DISCONNECTED
        self.subscriptions.reset_applied()
        for state in self.state_store.all():
            self.state_store.upsert(replace(state, stale=True, feed_health=FeedHealth.DISCONNECTED))

    def evaluate_freshness(self, now: datetime) -> None:
        for state in self.state_store.all():
            self.state_store.upsert(state.at_time(now, self.stale_after_seconds))
        if self.state_store.all() and all(state.stale for state in self.state_store.all()):
            self.feed_health = FeedHealth.DEGRADED

    async def heartbeat_loop(
        self,
        *,
        interval_seconds: float = 5.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Continuously evaluate freshness even when the provider sends nothing."""
        while not self._stop.is_set():
            await asyncio.sleep(max(0.1, interval_seconds))
            self.evaluate_freshness(clock())

    async def connect_once(self) -> None:
        self.connection_attempts += 1
        self.feed_health = FeedHealth.CONNECTING
        await self.client.connect(self.feed)
        self.feed_health = FeedHealth.HEALTHY
        await self.sync_subscriptions()
        async for event in self.client.events():
            if self._stop.is_set():
                break
            await self.process_event(event)

    async def run_forever(
        self,
        *,
        initial_backoff: float = 1.0,
        maximum_backoff: float = 30.0,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        backoff = max(0.1, initial_backoff)
        while not self._stop.is_set():
            heartbeat = asyncio.create_task(self.heartbeat_loop())
            try:
                await self.connect_once()
                if not self._stop.is_set():
                    raise ConnectionError("provider stream ended")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.mark_disconnected()
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
                if not self._stop.is_set():
                    await sleeper(backoff)
                    backoff = min(maximum_backoff, backoff * 2)
            finally:
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass

    def stop(self) -> None:
        self._stop.set()
