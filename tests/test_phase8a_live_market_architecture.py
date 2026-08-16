from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.live_market.alerts import InMemoryAlertRepository, create_alert_event
from services.live_market.gateway import InMemoryLiveStateStore, LiveMarketGateway
from services.live_market.models import (
    FeedHealth, MarketEvent, MarketSession, MinuteBar, MonitoringTier,
    SecurityType, TechnicalState, TechnicalStateResult, classify_market_session,
    live_status_label,
)
from services.live_market.subscriptions import SubscriptionManager, WatchlistRegistry


UTC = timezone.utc


class FakeClient:
    def __init__(self):
        self.connections = 0
        self.subscribed: list[tuple[str, ...]] = []
        self.unsubscribed: list[tuple[str, ...]] = []
        self.repairs: list[tuple[str, datetime, datetime]] = []
        self.repair_rows: list[MinuteBar] = []

    async def connect(self, feed): self.connections += 1
    async def disconnect(self): return None
    async def subscribe(self, symbols): self.subscribed.append(tuple(symbols))
    async def unsubscribe(self, symbols): self.unsubscribed.append(tuple(symbols))
    async def repair_completed_bars(self, ticker, start, end):
        self.repairs.append((ticker, start, end))
        return list(self.repair_rows)
    async def events(self):
        if False:
            yield None


class RecordingTechnicalSink:
    def __init__(self): self.bars = []
    async def on_completed_bar(self, bar, live_state): self.bars.append((bar, live_state))


def moment(hour, minute=0, day=14):
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


def trade(ticker="NVDA", at=None, received=None, price=100.0, kind=SecurityType.STOCK, sequence=1):
    at = at or moment(15)
    return MarketEvent(ticker, "trade", at, received or at, "iex", kind, sequence, price)


def bar(ticker, at, close=100.0, kind=SecurityType.STOCK):
    item = MinuteBar(ticker, at, close - 1, close + 1, close - 2, close, 1000, feed="iex")
    return MarketEvent(ticker, "bar", at, at + timedelta(seconds=1), "iex", kind, bar=item)


def test_many_users_share_one_symbol_and_one_provider_subscription():
    watchlists = WatchlistRegistry()
    for index in range(1000):
        item = watchlists.create(f"user-{index}", "Primary")
        watchlists.add_symbol(item.watchlist_id, "NVDA")
    manager = SubscriptionManager()
    manager.replace_source("customer-watchlists", MonitoringTier.ACTIVE_CUSTOMER, watchlists.active_symbol_union())
    client = FakeClient()
    gateway = LiveMarketGateway(client, manager)
    asyncio.run(gateway.connect_once())
    assert client.connections == 1
    assert client.subscribed == [("NVDA",)]


def test_many_unique_symbols_are_subscribed_once_each():
    manager = SubscriptionManager()
    symbols = {f"S{index}" for index in range(650)}
    manager.replace_source("broad", MonitoringTier.SCANNER_UNIVERSE, symbols)
    client = FakeClient()
    gateway = LiveMarketGateway(client, manager)
    asyncio.run(gateway.sync_subscriptions())
    assert len(client.subscribed[0]) == 650
    assert len(set(client.subscribed[0])) == 650


def test_dynamic_add_remove_and_tier_promotion_need_no_restart():
    manager = SubscriptionManager()
    manager.replace_source("scanner", MonitoringTier.SCANNER_UNIVERSE, {"NVDA", "SPY"})
    client = FakeClient()
    gateway = LiveMarketGateway(client, manager)
    asyncio.run(gateway.sync_subscriptions())
    manager.replace_source("scanner", MonitoringTier.SCANNER_UNIVERSE, {"SPY", "QQQ"})
    manager.replace_source("customers", MonitoringTier.ACTIVE_CUSTOMER, {"SPY"})
    asyncio.run(gateway.sync_subscriptions())
    assert client.unsubscribed[-1] == ("NVDA",)
    assert client.subscribed[-1] == ("QQQ",)
    assert manager.desired()["SPY"] == MonitoringTier.ACTIVE_CUSTOMER
    assert client.connections == 0


def test_disconnect_retains_price_marks_stale_and_suppresses_alerts():
    client, manager = FakeClient(), SubscriptionManager()
    gateway = LiveMarketGateway(client, manager)
    asyncio.run(gateway.process_event(trade()))
    gateway.mark_disconnected()
    state = gateway.state_store.get("NVDA")
    assert state.live_price == 100.0
    assert state.stale is True
    assert state.feed_health == FeedHealth.DISCONNECTED
    assert state.alerts_allowed is False
    assert live_status_label(state, moment(15, 1)).startswith("DATA DELAYED")


def test_duplicate_and_out_of_order_events_are_ignored():
    gateway = LiveMarketGateway(FakeClient(), SubscriptionManager())
    event = trade(sequence=10)
    assert asyncio.run(gateway.process_event(event)) is True
    assert asyncio.run(gateway.process_event(event)) is False
    assert asyncio.run(gateway.process_event(trade(at=moment(14, 59), sequence=9, price=99))) is False
    assert gateway.duplicate_events == 1
    assert gateway.out_of_order_events == 1
    assert gateway.state_store.get("NVDA").live_price == 100.0


def test_missing_completed_bars_are_repaired_before_current_bar():
    client, sink = FakeClient(), RecordingTechnicalSink()
    gateway = LiveMarketGateway(client, SubscriptionManager(), technical_sink=sink)
    first = bar("NVDA", moment(15, 0), 100)
    missing = first.bar.__class__("NVDA", moment(15, 1), 100, 102, 99, 101, 1000, feed="iex")
    client.repair_rows = [missing]
    asyncio.run(gateway.process_event(first))
    asyncio.run(gateway.process_event(bar("NVDA", moment(15, 2), 102)))
    assert client.repairs == [("NVDA", moment(15, 1), moment(15, 1))]
    assert [item[0].timestamp for item in sink.bars] == [moment(15, 0), moment(15, 1), moment(15, 2)]
    assert gateway.repaired_bars == 1


def test_stale_feed_health_is_centralized():
    gateway = LiveMarketGateway(FakeClient(), SubscriptionManager(), stale_after_seconds=10)
    asyncio.run(gateway.process_event(trade(at=moment(15), received=moment(15))))
    gateway.evaluate_freshness(moment(15, 0) + timedelta(seconds=11))
    state = gateway.state_store.get("NVDA")
    assert state.stale is True
    assert state.feed_health == FeedHealth.DEGRADED
    assert gateway.feed_health == FeedHealth.DEGRADED


def test_market_session_transitions_are_deterministic():
    assert classify_market_session(moment(12, 0)) == MarketSession.PRE_MARKET  # 08:00 ET
    assert classify_market_session(moment(15, 0)) == MarketSession.REGULAR     # 11:00 ET
    assert classify_market_session(moment(21, 0)) == MarketSession.AFTER_HOURS # 17:00 ET
    assert classify_market_session(datetime(2026, 8, 15, 15, tzinfo=UTC)) == MarketSession.CLOSED


def test_stock_and_etf_security_types_survive_normalization():
    gateway = LiveMarketGateway(FakeClient(), SubscriptionManager())
    asyncio.run(gateway.process_event(trade("NVDA", kind=SecurityType.STOCK)))
    asyncio.run(gateway.process_event(trade("SPY", price=500, kind=SecurityType.ETF)))
    assert gateway.state_store.get("NVDA").security_type == SecurityType.STOCK
    assert gateway.state_store.get("SPY").security_type == SecurityType.ETF


def test_streamlit_reruns_do_not_create_connections_or_duplicate_demand():
    manager = SubscriptionManager()
    client = FakeClient()
    gateway = LiveMarketGateway(client, manager)
    for _ in range(100):
        manager.replace_source("customer-watchlists", MonitoringTier.ACTIVE_CUSTOMER, {"NVDA", "SPY"})
    asyncio.run(gateway.sync_subscriptions())
    asyncio.run(gateway.sync_subscriptions())
    assert client.connections == 0
    assert client.subscribed == [("NVDA", "SPY")]


def test_alert_fingerprint_is_durable_and_idempotent_and_stale_is_suppressed():
    result = TechnicalStateResult("NVDA", TechnicalState.NEAR_BREAKOUT, TechnicalState.BREAKOUT_CONFIRMED, moment(15), {"close_above_level": True}, FeedHealth.HEALTHY)
    first = create_alert_event(result, ("u2", "u1", "u1"), "URGENT")
    second = create_alert_event(result, ("u1", "u2"), "URGENT")
    repo = InMemoryAlertRepository()
    assert first.event_fingerprint == second.event_fingerprint
    assert first.recipients == ("u1", "u2")
    assert repo.insert_if_absent(first) is True
    assert repo.insert_if_absent(second) is False
    stale = TechnicalStateResult("NVDA", TechnicalState.NEAR_BREAKOUT, TechnicalState.BREAKOUT_CONFIRMED, moment(15), {}, FeedHealth.DISCONNECTED)
    assert create_alert_event(stale, ("u1",), "URGENT") is None


def test_backoff_is_bounded_and_reconnect_marks_attempts():
    class FailingClient(FakeClient):
        async def connect(self, feed):
            self.connections += 1
            raise ConnectionError("offline")

    sleeps = []
    client = FailingClient()
    gateway = LiveMarketGateway(client, SubscriptionManager())

    async def sleeper(delay):
        sleeps.append(delay)
        if len(sleeps) == 4:
            gateway.stop()

    asyncio.run(gateway.run_forever(initial_backoff=1, maximum_backoff=4, sleeper=sleeper))
    assert sleeps == [1, 2, 4, 4]
    assert gateway.connection_attempts == 4
    assert client.connections == 4


def test_clean_stream_end_uses_backoff_instead_of_tight_reconnect_loop():
    client = FakeClient()
    gateway = LiveMarketGateway(client, SubscriptionManager())
    sleeps = []

    async def sleeper(delay):
        sleeps.append(delay)
        gateway.stop()

    asyncio.run(gateway.run_forever(sleeper=sleeper))
    assert client.connections == 1
    assert sleeps == [1.0]
    assert gateway.feed_health == FeedHealth.DISCONNECTED


def test_reconnect_reapplies_unique_symbol_union():
    manager = SubscriptionManager()
    manager.replace_source("customers", MonitoringTier.ACTIVE_CUSTOMER, {"NVDA", "SPY"})
    client = FakeClient()
    gateway = LiveMarketGateway(client, manager)
    asyncio.run(gateway.sync_subscriptions())
    gateway.mark_disconnected()
    asyncio.run(gateway.sync_subscriptions())
    assert client.subscribed == [("NVDA", "SPY"), ("NVDA", "SPY")]
    assert manager.applied_symbols == frozenset({"NVDA", "SPY"})


def test_phase8a_is_not_wired_into_streamlit_or_scanner():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "app.py", root / "overnight_market_scan.py"):
        assert "services.live_market" not in path.read_text()


def test_ai_valuation_gate_remains_closed():
    from engines.ai_valuation import JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED
    assert JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED is False
