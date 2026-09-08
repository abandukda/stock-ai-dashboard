from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.audit_production_yahoo_dependencies import audit
from services.governed_discovery_data import fetch_twelve_daily_batch, load_governed_universe
from overnight_market_scan import compare_governed_universe


ROOT = Path(__file__).resolve().parents[1]


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
    def json(self): return self.payload


def test_production_yahoo_dependency_count_is_zero():
    result = audit(ROOT)
    assert result["PRODUCTION_YAHOO_DEPENDENCY_COUNT"] == 0, result["production_files"]


def test_governed_universe_validates_supported_listings():
    class Client:
        def get(self, family, params):
            payload = ([{"symbol": "MSFT", "exchangeShortName": "NASDAQ", "isActivelyTrading": True},
                        {"symbol": "OLD", "exchangeShortName": "NYSE", "isActivelyTrading": False},
                        {"symbol": "BAD.L", "exchangeShortName": "LSE", "isActivelyTrading": True}]
                       if params["exchange"] == "NASDAQ" and params["isEtf"] == "false"
                       else ([{"symbol": "SPY", "exchangeShortName": "ARCA", "isEtf": True}]
                             if params["exchange"] == "NASDAQ" else []))
            return type("R", (), {"payload": payload, "outcome": "SUCCESS", "attempts": 1})()
    result = load_governed_universe(fmp_key="secret", client=Client())
    assert result["symbols"] == ["MSFT", "SPY"]
    assert result["provider"] == "FMP"


def test_twelve_batch_normalizes_completed_daily_history():
    payload = {"MSFT": {"values": [{"datetime": "2026-09-04", "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10"}]}}
    frame = fetch_twelve_daily_batch(["MSFT"], api_key="secret", get=lambda *_a, **_k: Response(payload))
    assert isinstance(frame, pd.DataFrame) and not frame.empty
    assert float(frame["MSFT"]["Close"].iloc[-1]) == 101.0


def test_twelve_batch_deduplicates_dates_without_poisoning_other_symbols():
    payload = {
        "GOOD": {"values": [{"datetime": "2026-09-04", "open": "9", "high": "11", "low": "8", "close": "10", "volume": "100"}]},
        "DUP": {"values": [
            {"datetime": "2026-09-04", "open": "19", "high": "21", "low": "18", "close": "20", "volume": "200"},
            {"datetime": "2026-09-04", "open": "20", "high": "22", "low": "19", "close": "21", "volume": "210"},
        ]},
        "BAD": {"values": [{"datetime": "not-a-date", "open": "x"}]},
    }
    frame = fetch_twelve_daily_batch(["GOOD", "DUP", "BAD"], api_key="secret", get=lambda *_a, **_k: Response(payload))
    assert list(frame.columns.get_level_values(0).unique()) == ["GOOD", "DUP"]
    assert frame["DUP"].index.is_unique and float(frame["DUP"]["Close"].iloc[-1]) == 21
    diagnostics = frame.attrs["governed_market_diagnostics"]
    assert diagnostics["market_history_success"] == 2
    assert diagnostics["market_history_duplicate_index_failure"] == 1
    assert diagnostics["market_history_schema_failure"] == 1


def test_twelve_batch_retains_sanitized_http_failure_details():
    frame = fetch_twelve_daily_batch(
        ["MISS"], api_key="top-secret",
        get=lambda *_a, **_k: Response({"message": "symbol unsupported top-secret"}, 400),
    )
    diagnostics = frame.attrs["governed_market_diagnostics"]
    record = diagnostics["per_symbol_records"]["MISS"]
    assert record["http_status"] == 400
    assert record["failure_stage"] == "HTTP_RESPONSE"
    assert record["provider_error_message"] == "symbol unsupported [REDACTED]"
    assert "top-secret" not in str(diagnostics)


def test_universe_comparison_never_hides_a_loss():
    result = compare_governed_universe(["A", "B"], ["B", "C"])
    assert result["old_count"] == 2 and result["new_count"] == 2 and result["overlap"] == 1
    assert result["only_old"] == result["unexplained_losses"] == ["A"]
