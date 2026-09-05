from datetime import datetime, timezone
import json
from pathlib import Path

from services.home_live_market_phase1 import acquire_home_phase1_evaluations


NOW = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)


class Response:
    def raise_for_status(self):
        return None

    def json(self):
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
        [_row()], get=lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
        connector=lambda *args, **kwargs: Socket([event]),
        secrets={"TWELVE_DATA_ENABLED": "true", "TWELVE_DATA_API_KEY": "test-secret"},
        environ={}, now=NOW,
    )
    assert result["provider_calls"] == 2
    assert len(calls) == 1 and calls[0][0][0].endswith("/time_series")
    evaluation = result["evaluations"]["NVDA"]
    assert evaluation["market_snapshot"]["source_type"] == "TWELVE_DATA_WEBSOCKET"
    assert evaluation["market_snapshot"]["evidence_id"].startswith("TD1-")
    assert evaluation["volume_intelligence"]["status"] == "DATA_UNAVAILABLE"
    assert evaluation["guidance"]["state"] not in {"BUY_NOW", "ACCUMULATE"}
    assert evaluation["phase1_completed_bar"]["completed"] is True
    assert evaluation["phase1_bar_quality"]["evidence_id"].startswith("TD1-")


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
    assert body.index("render_home_guidance_vnext(story") < body.index("acquire_home_phase1_evaluations(full_payload)")


def test_default_home_cohort_is_bounded_to_current_top_ten():
    import services.home_live_market_phase1 as phase1
    assert phase1.DEFAULT_MAX_SYMBOLS == 10
