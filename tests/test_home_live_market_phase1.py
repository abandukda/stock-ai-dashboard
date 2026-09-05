from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from services.home_live_market_phase1 import acquire_home_phase1_evaluations


NOW = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)


class Response:
    def __init__(self, interval="1min"):
        self.interval = interval

    def raise_for_status(self):
        return None

    def json(self):
        if self.interval == "1day":
            day = datetime(2025, 10, 20)
            values = []
            while len(values) < 220:
                if day.weekday() < 5:
                    close = 80 + len(values) * .1
                    values.append({"datetime": day.date().isoformat(), "open": close - .2, "high": close + .5, "low": close - .5, "close": close, "volume": 1_000_000})
                day += timedelta(days=1)
            return {"meta": {"symbol": "NVDA", "exchange_timezone": "America/New_York"}, "values": values}
        return {"meta": {"exchange_timezone": "America/New_York"}, "values": [
            {"datetime": "2026-09-04 10:50:00", "open": "100", "high": "102", "low": "99", "close": "101", "volume": "1000"},
        ]}


class Socket:
    def __init__(self, events):
        self.events = list(events)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def send(self, message):
        assert "subscribe" in message

    def recv(self, timeout=None):
        if not self.events:
            raise TimeoutError
        return json.dumps(self.events.pop(0))


def _row(ticker="NVDA"):
    return {
        "ticker": ticker, "price": 100, "scan_time": "2026-09-04T14:00:00+00:00",
        "canonical_technical": {"status": "AVAILABLE", "state": "NEAR_BREAKOUT", "score": 80, "completed_bar": True},
        "primary_risk": "Execution risk", "canonical_on_demand_opportunity": 80,
        "canonical_on_demand_decision_confidence": 80, "canonical_on_demand_component_coverage": 80,
        "canonical_on_demand_trade_plan": {"entry_low": 100, "entry_high": 110, "stop": 90, "target": 130},
    }


def test_disabled_home_acquisition_has_zero_calls_and_does_not_read_key():
    calls = []
    result = acquire_home_phase1_evaluations(
        [_row()], get=lambda *args, **kwargs: calls.append((args, kwargs)),
        secrets={"TWELVE_DATA_ENABLED": "false"}, environ={}, now=NOW,
    )
    assert result == {"version": "HOME_TWELVE_DATA_PHASE1_V1", "status": "DISABLED", "evaluations": {}, "provider_calls": 0}
    assert calls == []


def test_enabled_home_acquisition_uses_websocket_and_time_series_but_keeps_volume_closed():
    calls = []
    event = {"event": "price", "symbol": "NVDA", "price": 105, "timestamp": 1788533940}
    result = acquire_home_phase1_evaluations(
        [_row()], get=lambda *args, **kwargs: calls.append((args, kwargs)) or Response(kwargs["params"]["interval"]),
        connector=lambda *args, **kwargs: Socket([event]),
        secrets={"TWELVE_DATA_ENABLED": "true", "TWELVE_DATA_API_KEY": "test-secret"},
        environ={}, now=NOW,
    )
    assert result["provider_calls"] == 3
    assert len(calls) == 2 and all(call[0][0].endswith("/time_series") for call in calls)
    assert calls[0][1]["params"]["interval"] == "1min"
    assert calls[1][1]["params"]["interval"] == "1day"
    assert calls[1][1]["params"]["adjust"] == "splits"
    evaluation = result["evaluations"]["NVDA"]
    assert evaluation["market_snapshot"]["source_type"] == "TWELVE_DATA_WEBSOCKET"
    assert evaluation["market_snapshot"]["evidence_id"].startswith("TD1-")
    assert evaluation["volume_intelligence"]["status"] == "DATA_UNAVAILABLE"
    assert evaluation["guidance"]["state"] not in {"BUY_NOW", "ACCUMULATE"}
    assert evaluation["phase1_completed_bar"]["completed"] is True
    assert evaluation["phase1_bar_quality"]["evidence_id"].startswith("TD1-")
    assert evaluation["technical_confirmation"]["status"] == "AVAILABLE"
    assert evaluation["technical_confirmation"]["state"] in {"NO_SETUP", "SETUP_FORMING", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED", "EXTENDED", "FAILED_BREAKOUT"}
    assert evaluation["phase1_home_chart"]["provider"] == "TWELVE_DATA"
    assert evaluation["phase1_home_chart"]["range"] == "3M"
    assert evaluation["phase1_home_chart"]["interval"] == "1day"
    assert evaluation["phase1_home_chart"]["adjustment_mode"] == "splits"
    assert len(evaluation["phase1_home_chart"]["bars"]) == 66


def test_wrong_symbol_and_provider_failure_leave_home_fail_closed():
    event = {"event": "price", "symbol": "AAPL", "price": 105, "timestamp": 1788533940}
    result = acquire_home_phase1_evaluations(
        [_row()], get=lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
        connector=lambda *args, **kwargs: Socket([event]),
        secrets={"TWELVE_DATA_ENABLED": "true", "TWELVE_DATA_API_KEY": "test-secret"},
        environ={}, now=NOW,
    )
    assert result["evaluations"] == {}
    assert result["diagnostics"]["NVDA"]["status"] == "DATA_UNAVAILABLE"


def test_home_provider_work_is_after_renderer_page_interactive_seam():
    app = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    start = app.index("def v810_render_dynamic_home")
    body = app[start:]
    assert body.index("render_home_guidance_vnext(story") < body.index("acquire_home_phase1_evaluations(")


def test_default_home_cohort_is_bounded_to_current_top_ten():
    import services.home_live_market_phase1 as phase1
    assert phase1.DEFAULT_MAX_SYMBOLS == 10


def test_daily_technical_history_is_session_cached_by_authority_key():
    calls = []
    get = lambda *args, **kwargs: calls.append((args, kwargs)) or Response(kwargs["params"]["interval"])
    first = acquire_home_phase1_evaluations(
        [_row()], get=get, connector=lambda *args, **kwargs: Socket([]),
        secrets={"TWELVE_DATA_ENABLED": "true", "TWELVE_DATA_API_KEY": "test-secret"}, environ={}, now=NOW,
    )
    assert len(calls) == 2
    calls.clear()
    second = acquire_home_phase1_evaluations(
        [_row()], get=get, connector=lambda *args, **kwargs: Socket([]),
        secrets={"TWELVE_DATA_ENABLED": "true", "TWELVE_DATA_API_KEY": "test-secret"}, environ={}, now=NOW,
        daily_history_cache=first["daily_history_cache"],
    )
    assert len(calls) == 1
    assert calls[0][1]["params"]["interval"] == "1min"
    assert second["provider_calls"] == 2
    assert "|TWELVE_DATA|1Y|1day|REGULAR|splits|" in next(iter(second["daily_history_cache"]))
