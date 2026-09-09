from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import overnight_market_scan as scan
from services.governed_discovery_data import (
    assert_governed_stock_universe, canonical_security_ticker, load_governed_universe,
    normalize_listing_exchange, twelve_symbol_route,
)
from services.governed_market_cache import (
    append_history, cache_namespace, load_history, load_negative_cache, write_negative_cache,
)


class Response:
    def __init__(self, payload):
        self.status_code = 200
        self.payload = payload

    def json(self):
        return self.payload


class Client:
    def __init__(self, stock, etf):
        self.stock, self.etf = stock, etf
        self.calls = []

    def __call__(self, url, params, timeout):
        self.calls.append((url, dict(params), timeout))
        if url.endswith("/etfs/list"):
            return Response({"result": {"count": len(self.etf), "list": self.etf}, "status": "ok"})
        return Response({"data": self.stock})


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
    result = load_governed_universe(api_key="x", get=Client(stock, [
        {"symbol": "SPY", "exchangeShortName": "ARCA", "isEtf": True},
    ]))
    assert result["stock_symbols"] == ["ADR", "LIVE"]
    assert result["etf_symbols"] == ["SPY"]
    reasons = {row["ticker"]: row["reason"] for row in result["exclusions"]}
    assert reasons == {
        "OLD": "INACTIVE_LISTING", "DEL": "DELISTED_LISTING", "W": "WARRANT_SECURITY",
        "U": "UNIT_SECURITY", "P": "PREFERRED_SECURITY", "OTC": "OTC_OUTSIDE_STOCK_POLICY",
    }


def test_twelve_stock_reference_is_country_scoped_and_routes_are_separate():
    client = Client([], [])
    load_governed_universe(api_key="x", get=client)
    assert len(client.calls) == 2
    url, params, _timeout = client.calls[0]
    assert url.endswith("/stocks")
    assert params["country"] == "United States"
    etf_url, etf_params, _timeout = client.calls[1]
    assert etf_url.endswith("/etfs/list")
    assert etf_params["country"] == "United States"


def test_twelve_etf_directory_routes_major_us_funds_and_excludes_foreign():
    etfs = [
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "mic_code": "ARCX", "country": "United States"},
        {"symbol": "QQQ", "name": "Invesco QQQ", "mic_code": "XNAS", "country": "United States"},
        {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "mic_code": "ARCX", "country": "United States"},
        {"symbol": "DIA", "name": "SPDR Dow ETF", "mic_code": "ARCX", "country": "United States"},
        {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "mic_code": "ARCX", "country": "United States"},
        {"symbol": "2800.HK", "name": "Tracker Fund", "mic_code": "XHKG", "country": "Hong Kong"},
    ]
    result = load_governed_universe(api_key="x", get=Client([], etfs))
    assert result["etf_symbols"] == ["DIA", "IWM", "QQQ", "SPY", "VOO"]
    assert "2800.HK" not in result["symbols"]
    excluded = {item["ticker"]: item["reason"] for item in result["exclusions"]}
    assert excluded["2800.HK"] == "NON_US_EXCHANGE_OUTSIDE_STOCK_POLICY"


def test_exchange_resolution_fails_closed_before_stock_or_etf_routing():
    stock = [
        {"symbol": "0001.HK", "name": "Foreign blank", "exchangeShortName": "", "country": "HK"},
        {"symbol": "0001.KL", "exchange": "KLS", "type": "Common Stock"},
        {"symbol": "VOD.L", "exchangeFullName": "London Stock Exchange", "country": "US"},
        {"symbol": "TSM", "exchangeShortName": "NYSE", "country": "TW", "type": "ADR"},
        {"symbol": "BEKE", "exchangeShortName": "NYSE", "country": "CN", "type": "ADS"},
        {"symbol": "BP", "exchangeShortName": "NYSE", "country": "GB", "type": "ADR"},
        {"symbol": "SHEL", "exchangeShortName": "NYSE", "country": "GB", "type": "ADR"},
        {"symbol": "DRD", "exchangeShortName": "NYSE", "country": "ZA", "type": "ADR"},
        {"symbol": "UMC", "exchangeShortName": "NYSE", "country": "TW", "type": "ADS"},
        {"symbol": "PKX", "exchangeShortName": "NYSE", "country": "KR", "type": "ADR"},
        {"symbol": "AAPL", "exchangeFullName": "NASDAQ Global Select", "country": "US", "type": "Common Stock", "isActivelyTrading": True},
        {"symbol": "MSFT", "exchangeShortName": "NASDAQ", "country": "US", "type": "Common Stock"},
        {"symbol": "JNJ", "exchangeShortName": "NYSE", "country": "US", "type": "Common Stock"},
    ]
    etfs = [
        {"symbol": "2800.HK", "exchange": "HKSE", "isEtf": True},
        {"symbol": "SPY", "exchange": "NYSE Arca", "isEtf": True},
    ]
    result = load_governed_universe(api_key="x", get=Client(stock, etfs))
    assert set(result["stock_symbols"]) == {
        "AAPL", "BEKE", "BP", "DRD", "JNJ", "MSFT", "PKX", "SHEL", "TSM", "UMC",
    }
    assert result["etf_symbols"] == ["SPY"]
    assert not ({"0001.HK", "0001.KL", "VOD.L", "2800.HK"} & set(result["symbols"]))
    reasons = {row["ticker"]: row["reason"] for row in result["exclusions"]}
    assert reasons["0001.HK"] == "UNRESOLVED_LISTING_IDENTITY"
    assert reasons["0001.KL"] == reasons["VOD.L"] == reasons["2800.HK"] == "NON_US_EXCHANGE_OUTSIDE_STOCK_POLICY"
    assert result["summary"]["raw_global_master_count"] == 15
    assert result["summary"]["resolved_us_listing_count"] == 11
    assert result["summary"]["unresolved_listing_identity_count"] == 1
    assert result["summary"]["foreign_listing_removed_count"] == 3
    assert result["summary"]["us_stock_universe_count"] == 10
    assert result["summary"]["us_etf_universe_count"] == 1
    assert result["summary"]["stock_exchange_distribution"] == {"NASDAQ": 2, "NYSE": 8}
    assert result["summary"]["etf_exchange_distribution"] == {"ARCA": 1}
    assert {"symbol", "exchangeShortName", "isActivelyTrading"} <= set(
        result["diagnostics"]["observed_response_fields"]
    )
    assert result["summary"]["representative_unresolved_symbols"][0]["ticker"] == "0001.HK"
    assert {row["ticker"] for row in result["summary"]["representative_foreign_symbols"]} == {
        "0001.KL", "VOD.L", "2800.HK",
    }


def test_exchange_field_priority_and_trace_are_deterministic():
    resolved = normalize_listing_exchange({
        "exchangeShortName": "NYSE", "exchange": "LSE", "exchangeFullName": "London Stock Exchange"
    })
    assert resolved == {
        "source_exchange_value": "NYSE", "normalized_exchange": "NYSE",
        "exchange_resolution_status": "RESOLVED_US",
    }
    assert normalize_listing_exchange({"country": "US"})["exchange_resolution_status"] == "UNRESOLVED"
    assert normalize_listing_exchange({
        "exchangeShortName": "   ", "exchange": "NYSE",
    }) == {
        "source_exchange_value": "NYSE", "normalized_exchange": "NYSE",
        "exchange_resolution_status": "RESOLVED_US",
    }


def test_pre_twelve_assertion_rejects_unresolved_or_foreign_stock_identity():
    for exchange, status in ((None, "UNRESOLVED"), ("HKSE", "RESOLVED_FOREIGN")):
        result = {
            "stock_symbols": ["BAD"],
            "symbol_mappings": {"BAD": {
                "exchange": exchange, "normalized_exchange": exchange,
                "exchange_resolution_status": status,
            }},
        }
        try:
            assert_governed_stock_universe(result)
        except RuntimeError as exc:
            assert "GOVERNED_STOCK_EXCHANGE_ASSERTION_FAILED" in str(exc)
        else:
            raise AssertionError("invalid stock identity reached the Twelve acquisition boundary")


def test_pre_twelve_stock_universe_contains_only_approved_resolved_us_exchanges():
    result = load_governed_universe(api_key="x", get=Client([
        {"symbol": "AAPL", "exchangeShortName": "NASDAQ", "isActivelyTrading": True},
        {"symbol": "JNJ", "exchangeShortName": "NYSE", "isActivelyTrading": True},
        {"symbol": "TSM", "exchangeShortName": "NYSE", "country": "TW", "type": "ADR"},
        {"symbol": "0001.HK", "exchangeShortName": "HKSE", "isActivelyTrading": True},
    ], []))
    assert result["stock_symbols"] == ["AAPL", "JNJ", "TSM"]
    assert all(
        result["symbol_mappings"][symbol]["exchange_resolution_status"] == "RESOLVED_US"
        and result["symbol_mappings"][symbol]["normalized_exchange"] in {"NASDAQ", "NYSE"}
        for symbol in result["stock_symbols"]
    )


def test_class_share_mapping_is_traceable_and_canonical_without_duplicates():
    aliases = ["BRK-A", "BRK.B", "BF-A", "BF-B", "BH-A", "CALY"]
    canonical = [canonical_security_ticker(value) for value in aliases]
    assert canonical == ["BRK.A", "BRK.B", "BF.A", "BF.B", "BH.A", "CALY"]
    assert twelve_symbol_route("BRK-B", exchange="NYSE")["provider_ticker"] == "BRK.B"
    assert len({canonical_security_ticker(value) for value in ["BRK-B", "BRK.B"]}) == 1


def test_real_class_share_aliases_are_retained_once_after_us_exchange_resolution():
    stock = [
        {"symbol": symbol, "exchangeShortName": "NYSE", "type": "Common Stock"}
        for symbol in ("BRK-B", "BRK.B", "BF-B", "BF.B")
    ]
    result = load_governed_universe(api_key="x", get=Client(stock, []))
    assert result["stock_symbols"] == ["BF.B", "BRK.B"]
    assert result["symbol_mappings"]["BRK.B"]["provider_ticker"] == "BRK.B"
    assert result["symbol_mappings"]["BF.B"]["provider_ticker"] == "BF.B"


def test_master_ordering_cannot_admit_foreign_and_cap_is_applied_after_policy(monkeypatch):
    rows = [
        {"symbol": "0001.HK", "exchange": "HKSE", "type": "Common Stock"},
        {"symbol": "MSFT", "exchange": "NASDAQ", "type": "Common Stock"},
        {"symbol": "AAPL", "exchange": "NASDAQ", "type": "Common Stock"},
    ]
    first = load_governed_universe(api_key="x", get=Client(rows, []))
    second = load_governed_universe(api_key="x", get=Client(list(reversed(rows)), []))
    assert first["stock_symbols"] == second["stock_symbols"] == ["AAPL", "MSFT"]
    monkeypatch.setattr(scan, "load_governed_universe", lambda **_kwargs: first)
    monkeypatch.setattr(scan, "MAX_UNIVERSE", 1)
    assert scan.build_universe() == ["AAPL"]
    assert "0001.HK" not in scan._GOVERNED_UNIVERSE_RESULT["stock_symbols"]


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
