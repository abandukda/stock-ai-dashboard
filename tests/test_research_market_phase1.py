from datetime import datetime, timedelta, timezone

from engines.atlas_research_builder_v2 import build_atlas_research_v2
from services.live_market.twelve_data_phase1 import Phase1Policy, build_phase1_bundle
from services.research_market_phase1 import acquire_research_phase1, apply_research_phase1
from ui.market_timestamp import format_market_timestamp_et


NOW = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
POLICY = Phase1Policy(websocket_receipt_freshness_seconds=15, completed_bar_publication_safety_seconds=90)


def test_customer_market_timestamp_is_concise_et_and_canonical_value_is_unchanged():
    canonical = "2026-09-04T23:30:00+00:00"
    assert format_market_timestamp_et(canonical) == "Sep 4, 7:30 PM ET"
    assert canonical == "2026-09-04T23:30:00+00:00"


def _bars(symbol="NVDA"):
    return {"meta": {"symbol": symbol, "exchange_timezone": "America/New_York"}, "values": [
        {"datetime": "2026-09-04 10:50:00", "open": "100", "high": "102", "low": "99", "close": "101", "volume": "1000"},
        {"datetime": "2026-09-04 10:51:00", "open": "101", "high": "103", "low": "100", "close": "102", "volume": "1100"},
    ]}


def _bundle(event=None, payload=None):
    return build_phase1_bundle(
        "NVDA", websocket_event=event or {}, time_series_payload=payload or _bars(),
        received_timestamp=NOW, now=NOW, policy=POLICY,
    )


def _daily():
    day = datetime(2025, 10, 20)
    values = []
    while len(values) < 220:
        if day.weekday() < 5:
            close = 80 + len(values) * .1
            values.append({"datetime": day.date().isoformat(), "open": close - .2, "high": close + .5, "low": close - .5, "close": close, "volume": 1_000_000})
        day += timedelta(days=1)
    return {"meta": {"symbol": "NVDA", "exchange_timezone": "America/New_York"}, "values": values}


def test_research_uses_fresh_websocket_for_current_and_completed_bars_for_chart():
    event = {"event": "price", "symbol": "NVDA", "price": 180.25, "timestamp": 1788533940}
    result = apply_research_phase1({"Ticker": "NVDA", "Price": 170}, _bundle(event))
    assert result["current_price"] == 180.25
    assert result["canonical_market_snapshot"]["source_type"] == "TWELVE_DATA_WEBSOCKET"
    assert result["price_history"][-1]["close"] == 102
    assert result["history_provenance"]["adjustment_mode"] == "splits"
    assert result["canonical_chart_contract"]["newest_completed_bar_timestamp"]


def test_completed_bar_is_last_known_and_never_promoted_to_current_price():
    result = apply_research_phase1({"Ticker": "NVDA", "Price": 170}, _bundle())
    assert "current_price" not in result
    assert result["Price"] == 170
    assert result["canonical_market_snapshot"]["price"] == 102
    assert result["canonical_market_snapshot"]["fresh_current_price"] is False


def test_stale_wrong_symbol_websocket_fails_closed_but_chart_remains_available():
    wrong = {"event": "price", "symbol": "AAPL", "price": 999, "timestamp": 1788533940}
    result = apply_research_phase1({"Ticker": "NVDA", "Price": 170}, _bundle(wrong))
    assert result["canonical_market_snapshot"]["source_type"] == "TWELVE_DATA_LATEST_COMPLETED_BAR"
    assert result["canonical_chart_contract"]["quality_status"] == "AVAILABLE"


def test_existing_newer_history_remains_graceful_fallback():
    row = {"Ticker": "NVDA", "price_history": [{"date": "2026-09-05T00:00:00+00:00", "close": 170}]}
    result = apply_research_phase1(row, _bundle())
    assert result["price_history"] == row["price_history"]
    assert "history_provenance" not in result


def test_research_builder_preserves_twelve_chart_contract_and_provenance():
    enriched = apply_research_phase1({"Ticker": "NVDA", "Price": 170}, _bundle())
    report = build_atlas_research_v2(enriched)
    provenance = report["sections"]["technical"]["history_provenance"]
    assert provenance["source"] == "Twelve Data /time_series"
    assert provenance["evidence_id"].startswith("TD1-")
    assert report["canonical_chart_contract"]["session"] == "REGULAR"
    assert report["canonical_market_snapshot"]["fresh_current_price"] is False
    assert set(report["canonical_chart_ranges"]) == {"1D", "5D", "1M", "3M", "6M", "1Y"}


def test_research_reconciles_fresh_market_and_daily_canonical_technical_evaluation():
    event = {"event": "price", "symbol": "NVDA", "price": 105, "timestamp": 1788533940}
    bundle = build_phase1_bundle(
        "NVDA", websocket_event=event, time_series_payload=_bars(), daily_time_series_payload=_daily(),
        received_timestamp=NOW, now=NOW, policy=POLICY,
    )
    result = apply_research_phase1({
        "Ticker": "NVDA", "Price": 100, "primary_risk": "Execution risk",
        "canonical_on_demand_trade_plan": {"entry_low": 100, "entry_high": 110, "stop": 90, "target": 130},
    }, bundle)
    evaluation = result["research_context"]["current_evaluation"]
    assert evaluation["market_snapshot"] == result["canonical_market_snapshot"]
    assert evaluation["technical_confirmation"]["status"] == "AVAILABLE"
    assert result["canonical_technical"] == evaluation["technical_confirmation"]
    assert result["canonical_guidance"] == evaluation["guidance"]
    assert result["atlas_ai_view"]["text"]
    assert len(result["canonical_chart_ranges"]["1Y"]["bars"]) == 220


def test_research_acquisition_calls_time_series_only():
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return _bars()
    def get(url, **kwargs):
        calls.append((url, kwargs)); return Response()
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def send(self, _): pass
        def recv(self, **_): raise TimeoutError
    result = acquire_research_phase1(
        "NVDA", now=NOW, policy=POLICY, get=get, connector=lambda *a, **k: Socket(),
        secrets={"TWELVE_DATA_ENABLED": "true", "TWELVE_DATA_API_KEY": "test"}, environ={},
    )
    assert result["status"] == "AVAILABLE"
    assert len(calls) == 2 and all(call[0].endswith("/time_series") for call in calls)
    assert [call[1]["params"]["interval"] for call in calls] == ["1min", "1day"]
    assert calls[0][1]["params"]["outputsize"] == 5000
    assert calls[1][1]["params"]["outputsize"] == 260
    assert calls[1][1]["params"]["prepost"] == "false"
    assert all(call[1]["params"]["adjust"] == "splits" for call in calls)
    assert all("/quote" not in call[0] for call in calls)
