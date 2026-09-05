from datetime import datetime, timezone

import pytest

from engines.atlas_guidance_v1 import evaluate_guidance
from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation
from services.canonical_market_snapshot import build_market_snapshot
from services.on_demand_evaluation_service import evaluate_on_demand
from services.live_market.twelve_data_phase1 import (
    Phase1Policy, TwelveDataPhase1Adapter, build_adapter_if_enabled, build_phase1_bundle,
    normalize_websocket_price, quote_as_non_authoritative, validate_time_series,
)


NOW = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
POLICY = Phase1Policy(websocket_receipt_freshness_seconds=15, completed_bar_publication_safety_seconds=90)


def _event(symbol="NVDA", price=180.25, timestamp=1788533940):
    return {"event": "price", "symbol": symbol, "price": price, "timestamp": timestamp}


def _bars(*dates):
    return {"meta": {"exchange_timezone": "America/New_York"}, "values": [
        {"datetime": value, "open": "100", "high": "102", "low": "99", "close": "101", "volume": "1000"}
        for value in dates
    ]}


def test_quote_can_never_be_current_price_authority():
    quote = quote_as_non_authoritative("NVDA", {"close": 180, "timestamp": 1788533940})
    assert quote["current_price_authority"] is False
    assert quote["source_type"] == "TWELVE_DATA_QUOTE_CONTEXT_ONLY"
    assert build_market_snapshot("NVDA", quote, now=NOW)["fresh_current_price"] is False


def test_fresh_per_symbol_websocket_event_is_current_price_candidate():
    result = normalize_websocket_price(
        "NVDA", _event(), received_timestamp=NOW, now=NOW, policy=POLICY,
    )
    assert result["status"] == "AVAILABLE"
    assert result["source_type"] == "TWELVE_DATA_WEBSOCKET"
    assert result["receipt_age_seconds"] == 0
    assert build_market_snapshot("NVDA", result, now=NOW)["fresh_current_price"] is True


@pytest.mark.parametrize("event,received", [(_event(symbol="AAPL"), NOW), (_event(), datetime(2026, 9, 4, 14, 59, tzinfo=timezone.utc))])
def test_missing_or_stale_websocket_event_fails_closed(event, received):
    result = normalize_websocket_price("NVDA", event, received_timestamp=received, now=NOW, policy=POLICY)
    assert result["status"] == "DATA_UNAVAILABLE"
    assert result["price"] is None


def test_completed_bar_requires_configured_publication_safety_window():
    payload = _bars("2026-09-04 10:57:00", "2026-09-04 10:58:00")
    result = validate_time_series("NVDA", payload, received_timestamp=NOW, now=NOW, policy=POLICY)
    assert result["latest_completed_bar"]["timestamp"].endswith("14:57:00+00:00")
    assert result["latest_completed_bar"]["completed"] is True
    assert result["bars"][-1]["completed"] is False
    assert result["publication_policy_version"]


def test_gaps_and_duplicates_are_preserved_and_fail_closed_without_fill():
    payload = _bars("2026-09-04 10:50:00", "2026-09-04 10:52:00", "2026-09-04 10:52:00")
    result = validate_time_series("NVDA", payload, received_timestamp=NOW, now=NOW, policy=POLICY)
    assert len(result["bars"]) == 2
    assert result["duplicate_count"] == 1
    assert result["gap_metadata"][0]["missing_minutes"] == 1
    assert result["gap_metadata"][0]["classification"] == "UNKNOWN_REGULAR_SESSION_GAP"
    assert result["confirmation_allowed"] is False


def test_bundle_keeps_volume_and_breakout_confirmation_unavailable():
    bundle = build_phase1_bundle(
        "MU", websocket_event=_event(symbol="MU", price=150),
        time_series_payload=_bars("2026-09-04 10:50:00"),
        received_timestamp=NOW, now=NOW, policy=POLICY,
    )
    assert bundle["intraday_volume"]["status"] == "DATA_UNAVAILABLE"
    assert bundle["breakout_volume_confirmation"]["status"] == "DATA_UNAVAILABLE"
    assert bundle["intraday_volume"]["authority"] is False
    assert bundle["last_known_market"]["source_type"] == "TWELVE_DATA_LATEST_COMPLETED_BAR"
    assert bundle["last_known_market"]["stale"] is True


def _guidance(state="NEAR_BREAKOUT", *, extended=False):
    return {
        "methodology_version": "FOUNDER_GUIDANCE_V1", "threshold_version": "TEST",
        "market_snapshot": {"price": 105 if not extended else 130, "provider_timestamp": "x", "fresh_current_price": True},
        "technical": {"status": "AVAILABLE", "state": "EXTENDED" if extended else state, "score": 80},
        "volume": {"status": "DATA_UNAVAILABLE", "volume_confirmed": False},
        "fundamentals": {"status": "AVAILABLE", "score": 80}, "risk": {"status": "AVAILABLE"},
        "valuation": {"status": "PUBLISHED", "fair_value": 130, "expected_return": 20, "score": 80},
        "trade_plan": {"entry_low": 100, "entry_high": 110, "stop": 90, "target": 130},
        "opportunity": 80, "decision_confidence": 80, "coverage": 80,
        "positive_action_volume_authority_required": True,
    }


def test_positive_states_cannot_pass_without_phase1_volume_authority_but_waits_can():
    pending = evaluate_guidance(_guidance("NEAR_BREAKOUT"))
    assert pending["state"] == "WAIT_FOR_CONFIRMATION"
    assert "VOLUME_CONFIRMATION_UNAVAILABLE" in pending["reason_codes"]
    assert evaluate_guidance(_guidance(extended=True))["state"] == "WAIT_FOR_ENTRY"


def test_raw_persisted_volume_cannot_reenable_phase1_volume_authority():
    result = build_canonical_evaluation(
        "NVDA", evaluation_mode="ON_DEMAND",
        market_snapshot={"price": 105, "provider_timestamp": "2026-09-04T15:00:00+00:00", "fresh_current_price": True},
        technical={
            "status": "AVAILABLE", "state": "BREAKOUT_CONFIRMED", "score": 80,
            "feed_health": "HEALTHY", "completed_bar": True,
            "evidence": {"relative_volume": 2.5, "average_dollar_volume": 10_000_000},
        },
        fundamentals={"status": "AVAILABLE", "score": 80}, risk={"status": "AVAILABLE"},
        trade_plan={"entry_low": 100, "entry_high": 110, "stop": 90, "target": 130},
        opportunity=80, decision_confidence=80, coverage=80,
        valuation_inputs={"price": 105, "analyst_target": 130}, valuation_component_score=80,
        positive_action_volume_authority_required=True,
    )
    assert result["volume_intelligence"]["status"] == "DATA_UNAVAILABLE"
    assert result["volume_intelligence"]["relative_volume"] is None
    assert result["guidance"]["state"] not in {"BUY_NOW", "ACCUMULATE"}


def test_disabled_adapter_cannot_acquire_or_expose_key():
    calls = []
    with pytest.raises(RuntimeError, match="TWELVE_DATA_ENABLED is false"):
        TwelveDataPhase1Adapter("secret", enabled=False, get=lambda *args, **kwargs: calls.append((args, kwargs)))
    assert calls == []


def test_flag_off_factory_reads_no_key_and_makes_no_call():
    class Secrets(dict):
        def get(self, key, default=None):
            if key == "TWELVE_DATA_API_KEY":
                raise AssertionError("key must not be read while disabled")
            return super().get(key, default)

    calls = []
    adapter = build_adapter_if_enabled(
        get=lambda *args, **kwargs: calls.append((args, kwargs)),
        secrets=Secrets(TWELVE_DATA_ENABLED="false"), environ={},
    )
    assert adapter is None
    assert calls == []


def test_enabled_rest_adapter_calls_time_series_only_and_never_quote():
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return _bars("2026-09-04 10:50:00")

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    adapter = build_adapter_if_enabled(
        get=get,
        secrets={"TWELVE_DATA_ENABLED": "true", "TWELVE_DATA_API_KEY": "redacted-test-key"},
        environ={},
    )
    assert adapter is not None
    adapter.fetch_time_series("NVDA")
    assert len(calls) == 1
    assert calls[0][0].endswith("/time_series")
    assert "/quote" not in calls[0][0]
    assert "apikey" not in calls[0][0]
    assert calls[0][1]["params"]["prepost"] == "true"
    assert calls[0][1]["params"]["adjust"] == "splits"


def test_zero_websocket_event_uses_completed_bar_as_explicit_last_known_not_current(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_ENABLED", "true")
    bundle = build_phase1_bundle(
        "NVDA", websocket_event={}, time_series_payload=_bars("2026-09-04 10:50:00"),
        received_timestamp=NOW, now=NOW, policy=POLICY,
    )
    result = evaluate_on_demand(
        {"ticker": "NVDA", "price": 99}, twelve_data_phase1=bundle,
    )
    market = result["market_snapshot"]
    assert market["price"] == 101
    assert market["source_type"] == "TWELVE_DATA_LATEST_COMPLETED_BAR"
    assert market["fresh_current_price"] is False
    assert market["customer_label"] == "Latest completed regular-session bar"


def test_on_demand_path_ignores_phase1_bundle_while_flag_is_off(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_ENABLED", "false")
    bundle = build_phase1_bundle(
        "NVDA", websocket_event=_event(), time_series_payload=_bars("2026-09-04 10:50:00"),
        received_timestamp=NOW, now=NOW, policy=POLICY,
    )
    result = evaluate_on_demand(
        {"ticker": "NVDA", "price": 170, "scan_time": "2026-09-04T14:00:00+00:00"},
        twelve_data_phase1=bundle,
    )
    assert result["market_snapshot"]["source_type"] == "LAST_KNOWN"
    assert result["market_snapshot"]["fresh_current_price"] is False


def test_on_demand_path_consumes_validated_bundle_only_when_flag_is_on(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_ENABLED", "true")
    monkeypatch.setattr(
        "services.live_market.twelve_data_phase1.twelve_data_enabled", lambda: True,
    )
    bundle = build_phase1_bundle(
        "NVDA", websocket_event=_event(), time_series_payload=_bars("2026-09-04 10:50:00"),
        received_timestamp=NOW, now=NOW, policy=POLICY,
    )
    result = evaluate_on_demand(
        {
            "ticker": "NVDA", "price": 170, "scan_time": "2026-09-04T14:00:00+00:00",
            "canonical_technical": {
                "status": "AVAILABLE", "state": "NEAR_BREAKOUT", "score": 60,
                "completed_bar": True, "feed_health": "HEALTHY", "evidence": {"relative_volume": 3.0},
            },
        },
        twelve_data_phase1=bundle,
    )
    assert result["market_snapshot"]["source_type"] == "TWELVE_DATA_WEBSOCKET"
    assert result["market_snapshot"]["fresh_current_price"] is True
    assert result["volume_intelligence"]["status"] == "DATA_UNAVAILABLE"
    assert result["guidance"]["state"] not in {"BUY_NOW", "ACCUMULATE"}
