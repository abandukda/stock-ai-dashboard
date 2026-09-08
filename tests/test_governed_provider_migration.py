from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.audit_production_yahoo_dependencies import audit
from services.governed_discovery_data import fetch_twelve_daily_batch, load_governed_universe
from overnight_market_scan import compare_governed_universe


ROOT = Path(__file__).resolve().parents[1]


class Response:
    status_code = 200
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


def test_production_yahoo_dependency_count_is_zero():
    result = audit(ROOT)
    assert result["PRODUCTION_YAHOO_DEPENDENCY_COUNT"] == 0, result["production_files"]


def test_governed_universe_validates_supported_listings():
    class Client:
        def get(self, family, _params):
            payload = ([{"symbol": "MSFT", "exchangeShortName": "NASDAQ", "isActivelyTrading": True},
                        {"symbol": "OLD", "exchangeShortName": "NYSE", "isActivelyTrading": False},
                        {"symbol": "BAD.L", "exchangeShortName": "LSE", "isActivelyTrading": True}]
                       if family == "stock-list" else [{"symbol": "SPY", "exchangeShortName": "ARCA"}])
            return type("R", (), {"payload": payload, "outcome": "SUCCESS", "attempts": 1})()
    result = load_governed_universe(fmp_key="secret", client=Client())
    assert result["symbols"] == ["MSFT", "SPY"]
    assert result["provider"] == "FMP"


def test_twelve_batch_normalizes_completed_daily_history():
    payload = {"MSFT": {"values": [{"datetime": "2026-09-04", "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10"}]}}
    frame = fetch_twelve_daily_batch(["MSFT"], api_key="secret", get=lambda *_a, **_k: Response(payload))
    assert isinstance(frame, pd.DataFrame) and not frame.empty
    assert float(frame["MSFT"]["Close"].iloc[-1]) == 101.0


def test_universe_comparison_never_hides_a_loss():
    result = compare_governed_universe(["A", "B"], ["B", "C"])
    assert result["old_count"] == 2 and result["new_count"] == 2 and result["overlap"] == 1
    assert result["only_old"] == result["unexplained_losses"] == ["A"]
