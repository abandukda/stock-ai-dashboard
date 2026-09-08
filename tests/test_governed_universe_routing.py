from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import overnight_market_scan as scan
from services.fmp_stable_client import FMPResponse, SUCCESS
from services.governed_discovery_data import (
    canonical_security_ticker, load_governed_universe, twelve_symbol_route,
)
from services.governed_market_cache import (
    append_history, cache_namespace, load_history, load_negative_cache, write_negative_cache,
)


class Client:
    def __init__(self, stock, etf):
        self.stock, self.etf = stock, etf

    def get(self, family, _params):
        return FMPResponse(self.stock if family == "stock-list" else self.etf,
                           SUCCESS, family, "2026-09-08T00:00:00Z", 200, 1)


def test_pre_acquisition_cleanup_and_separate_etf_routing():
    stock = [
        {"symbol": "LIVE", "exchangeShortName": "NYSE", "type": "Common Stock", "isActivelyTrading": True},
        {"symbol": "OLD", "exchangeShortName": "NYSE", "isActivelyTrading": False},
        {"symbol": "DEL", "exchangeShortName": "NYSE", "isDelisted": True},
        {"symbol": "W", "exchangeShortName": "NASDAQ", "type": "Warrant"},
        {"symbol": "U", "exchangeShortName": "NASDAQ", "type": "Unit"},
        {"symbol": "P", "exchangeShortName": "NYSE", "type": "Preferred Stock"},
        {"symbol": "OTC", "exchangeShortName": "OTCQX", "type": "Common Stock"},
        {"symbol": "ADR", "exchangeShortName": "NYSE", "type": "ADR"},
    ]
    result = load_governed_universe(fmp_key="x", client=Client(stock, [
        {"symbol": "SPY", "exchangeShortName": "ARCA", "isEtf": True},
    ]))
    assert result["stock_symbols"] == ["ADR", "LIVE"]
    assert result["etf_symbols"] == ["SPY"]
    reasons = {row["ticker"]: row["reason"] for row in result["exclusions"]}
    assert reasons == {
        "OLD": "INACTIVE_LISTING", "DEL": "DELISTED_LISTING", "W": "WARRANT_SECURITY",
        "U": "UNIT_SECURITY", "P": "PREFERRED_SECURITY", "OTC": "OTC_OUTSIDE_STOCK_POLICY",
    }


def test_class_share_mapping_is_traceable_and_canonical_without_duplicates():
    aliases = ["BRK-A", "BRK.B", "BF-A", "BF-B", "BH-A", "CALY"]
    canonical = [canonical_security_ticker(value) for value in aliases]
    assert canonical == ["BRK.A", "BRK.B", "BF.A", "BF.B", "BH.A", "CALY"]
    assert twelve_symbol_route("BRK-B", exchange="NYSE")["provider_ticker"] == "BRK.B"
    assert len({canonical_security_ticker(value) for value in ["BRK-B", "BRK.B"]}) == 1


def _empty_result(symbol: str, status: str, *, retryable: bool, http_status: int | None) -> pd.DataFrame:
    result = pd.DataFrame()
    result.attrs["governed_market_diagnostics"] = {
        "per_symbol": {symbol: status},
        "per_symbol_records": {symbol: {"acquisition_status": status, "retryable": retryable,
                                                "http_status": http_status, "failure_stage": "HTTP_RESPONSE"}},
    }
    return result


def _success(symbol: str) -> pd.DataFrame:
    frame = pd.DataFrame({"Close": [10.0]}, index=pd.to_datetime(["2026-09-08"], utc=True))
    result = pd.concat({symbol: frame}, axis=1)
    result.attrs["governed_market_diagnostics"] = {
        "per_symbol": {symbol: "SUCCESS"},
        "per_symbol_records": {symbol: {"acquisition_status": "SUCCESS", "retryable": False,
                                                "http_status": 200, "failure_stage": None}},
    }
    return result


def test_symbol_not_found_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(scan, "fetch_twelve_daily_batch", lambda symbols: calls.append(list(symbols)) or
                        _empty_result(symbols[0], "PERMANENT_SYMBOL_NOT_FOUND", retryable=False, http_status=400))
    monkeypatch.setattr(scan.time, "sleep", lambda _seconds: None)
    result = scan._download_price_batch_network(["MISS"])
    assert calls == [["MISS"]]
    assert result.attrs["governed_market_diagnostics"]["market_history_final_failure"] == 1


def test_429_and_timeout_are_bounded_retries(monkeypatch):
    calls = []

    def fetch(symbols):
        calls.append(list(symbols))
        if len(calls) == 1:
            return _empty_result(symbols[0], "TRANSIENT_RATE_LIMIT", retryable=True, http_status=429)
        return _success(symbols[0])

    monkeypatch.setattr(scan, "fetch_twelve_daily_batch", fetch)
    monkeypatch.setattr(scan.time, "sleep", lambda _seconds: None)
    result = scan._download_price_batch_network(["RATE"])
    assert calls == [["RATE"], ["RATE"]]
    assert not result.empty


def test_timeout_retries_are_bounded(monkeypatch):
    calls = []

    def fetch(_symbols):
        calls.append(1)
        raise TimeoutError("timeout")

    monkeypatch.setattr(scan, "fetch_twelve_daily_batch", fetch)
    monkeypatch.setattr(scan.time, "sleep", lambda _seconds: None)
    result = scan._download_price_batch_network(["TIME"])
    assert result.empty
    assert len(calls) == 3
    assert result.attrs["governed_market_diagnostics"]["per_symbol_records"]["TIME"]["retry_count"] == 2


def test_negative_cache_only_retains_permanent_failures_and_invalidates_namespace(tmp_path):
    path = tmp_path / "negative.json"
    write_negative_cache(path, namespace="n1", records={
        "PERM": {"acquisition_status": "PERMANENT_SYMBOL_NOT_FOUND", "retryable": False},
        "TEMP": {"acquisition_status": "TRANSIENT_RATE_LIMIT", "retryable": True},
    }, now=100)
    assert set(load_negative_cache(path, namespace="n1", now=101)) == {"PERM"}
    assert load_negative_cache(path, namespace="n2", now=101) == {}
    assert load_negative_cache(path, namespace="n1", now=100 + 8 * 86400) == {}
    assert cache_namespace(["A"], provider_policy="p", mapping_version="m") != cache_namespace(
        ["A", "B"], provider_policy="p", mapping_version="m"
    )


def test_history_append_deduplicates_and_retains_completed_bars(tmp_path):
    namespace = "n"
    first = pd.DataFrame({"Close": [10.0, 11.0]}, index=pd.to_datetime(["2026-09-04", "2026-09-05"], utc=True))
    second = pd.DataFrame({"Close": [11.5, 12.0]}, index=pd.to_datetime(["2026-09-05", "2026-09-08"], utc=True))
    append_history(tmp_path, "TEST", first, namespace=namespace)
    combined = append_history(tmp_path, "TEST", second, namespace=namespace)
    assert len(combined) == 3
    assert combined.loc[pd.Timestamp("2026-09-05", tz="UTC"), "Close"] == 11.5
    assert load_history(tmp_path, "TEST", namespace=namespace).equals(combined)


def test_warm_history_fetches_short_append_window(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("ATLAS_GOVERNED_MARKET_CACHE_ENABLED", "true")
    monkeypatch.setattr(scan, "GOVERNED_MARKET_CACHE_ROOT", tmp_path)
    monkeypatch.setattr(scan, "_GOVERNED_CACHE_NAMESPACE", "n")

    def network(symbols, *, outputsize=260):
        calls.append(outputsize)
        periods = 220 if outputsize == 260 else 10
        index = pd.date_range("2025-11-01", periods=periods, freq="B", tz="UTC")
        frame = pd.DataFrame({"Close": [10.0] * periods}, index=index)
        result = pd.concat({symbols[0]: frame}, axis=1)
        result.attrs["governed_market_diagnostics"] = {
            "per_symbol": {symbols[0]: "SUCCESS"},
            "per_symbol_records": {symbols[0]: {"acquisition_status": "SUCCESS", "retryable": False}},
        }
        return result

    monkeypatch.setattr(scan, "_download_price_batch_network", network)
    assert not scan.download_price_batch(["TEST"]).empty
    assert not scan.download_price_batch(["TEST"]).empty
    assert calls == [260, 10]


def test_investable_coverage_is_distinct_from_raw_coverage():
    scan._GOVERNED_UNIVERSE_RESULT.clear()
    scan._GOVERNED_UNIVERSE_RESULT.update({
        "stock_symbols": ["A", "B"], "etf_symbols": ["SPY"],
        "summary": {"raw_universe_count": 5, "investable_stock_universe_count": 2,
                    "etf_routed_separately": 1, "exclusion_reason_counts": {"INACTIVE_LISTING": 2}},
    })
    scan._GOVERNED_MARKET_COVERAGE["per_symbol"] = {"A": "SUCCESS", "B": "PERMANENT_SYMBOL_NOT_FOUND", "SPY": "SUCCESS"}
    scan._GOVERNED_MARKET_COVERAGE["per_symbol_records"] = {
        symbol: {"acquisition_status": status, "requested_twelve_symbol": symbol}
        for symbol, status in scan._GOVERNED_MARKET_COVERAGE["per_symbol"].items()
    }
    artifact = scan.build_governed_market_acquisition_diagnostics(generated_at="2026-09-08T00:00:00Z")
    assert artifact["summary"]["raw_universe_coverage_pct"] == 40.0
    assert artifact["summary"]["investable_market_history_coverage_pct"] == 50.0


def test_acquisition_failure_remains_data_failure_not_economic_exclusion():
    source = Path(scan.__file__).read_text(encoding="utf-8")
    assert '"DATA_ACQUISITION_FAILURE" if acquisition_status not in' in source
    assert "PRICE_BELOW_MINIMUM_OR_UNAVAILABLE" in source
