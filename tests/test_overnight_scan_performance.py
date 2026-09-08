import pandas as pd
import json

import overnight_market_scan as scan


def test_fast_cron_skips_fmp_profile_in_broad_pre_rank_loop(monkeypatch):
    calls = []
    monkeypatch.setattr(scan, "FAST_CRON_MODE", True)
    monkeypatch.setattr(scan, "FAST_CRON_SKIP_PRE_RANK_DEEP_APIS", True)
    monkeypatch.setattr(scan, "get_fmp_data", lambda symbol: calls.append(symbol) or {"sector": "Technology"})

    assert scan.get_pre_rank_fmp_data("NVDA") == {}
    assert calls == []


def test_fmp_profile_still_enriches_bounded_full_research_tier(monkeypatch):
    scan._FINALIST_ENRICHMENT_CACHE.clear()
    calls = []
    monkeypatch.setattr(scan, "FAST_CRON_MODE", True)
    monkeypatch.setattr(scan, "FAST_CRON_SKIP_PRE_RANK_DEEP_APIS", True)
    monkeypatch.setattr(scan, "v421_should_run_full_research", lambda symbol, row: True)
    monkeypatch.setattr(scan, "get_finalist_enrichment", lambda symbol, _company: (
        calls.append(symbol) or {"sector": "Technology", "country": "US", "source_fmp_profile": True},
        {"profile": "FETCHED"},
    ))
    monkeypatch.setattr(scan, "v42_build_committee_safe", lambda symbol, row, meta, ind, hist: row)
    monkeypatch.setattr(scan, "v42_apply_investor_translations_safe", lambda row: row)

    row = scan.v421_apply_tiered_committee(
        "ATLSZZ", {"ticker": "ATLSZZ", "sector": "Unknown"}, {}, {}, pd.DataFrame()
    )

    assert calls == ["ATLSZZ"]
    assert row["sector"] == "Technology"
    assert row["country"] == "US"
    assert row["source_fmp_profile"] is True
    assert row["v42_tier"] == "full"


def test_successful_governed_batch_has_no_unconditional_sleep(monkeypatch):
    sleeps = []
    frame = pd.DataFrame({"Close": [100.0]})
    monkeypatch.setattr(scan, "fetch_twelve_daily_batch", lambda _symbols: frame)
    monkeypatch.setattr(scan.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = scan.download_price_batch(["NVDA", "AVGO"])

    assert result is frame
    assert sleeps == []


def test_governed_provider_failure_keeps_exponential_retry_backoff(monkeypatch):
    sleeps = []
    attempts = []
    frame = pd.DataFrame({"Close": [100.0]})

    def download(symbols):
        attempts.append(symbols)
        if len(attempts) == 1:
            raise RuntimeError("429 rate limited")
        return frame

    monkeypatch.setattr(scan, "fetch_twelve_daily_batch", download)
    monkeypatch.setattr(scan.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = scan.download_price_batch(["NVDA"])

    assert result is frame
    assert len(attempts) == 2
    assert sleeps == [1]


def test_partial_batch_retries_only_missing_symbol_and_preserves_successes(monkeypatch):
    calls = []
    index = pd.to_datetime(["2026-09-04"], utc=True)

    def download(symbols):
        calls.append(list(symbols))
        available = symbols[:-1] if len(calls) == 1 else symbols
        frames = {symbol: pd.DataFrame({"Close": [100.0]}, index=index) for symbol in available}
        result = pd.concat(frames, axis=1) if frames else pd.DataFrame()
        result.attrs["governed_market_diagnostics"] = {"per_symbol": {
            symbol: "SUCCESS" for symbol in available}}
        return result

    monkeypatch.setattr(scan, "fetch_twelve_daily_batch", download)
    monkeypatch.setattr(scan.time, "sleep", lambda _seconds: None)
    result = scan.download_price_batch(["A", "B", "C"])
    assert calls == [["A", "B", "C"], ["C"]]
    assert set(result.columns.get_level_values(0)) == {"A", "B", "C"}
    diagnostics = result.attrs["governed_market_diagnostics"]
    assert diagnostics["market_history_success"] == 3
    assert diagnostics["market_history_retry_success"] == 1
    assert diagnostics["market_history_final_failure"] == 0
    assert diagnostics["per_symbol_records"]["A"]["retry_count"] == 0
    assert diagnostics["per_symbol_records"]["C"]["retry_count"] == 1


def test_failure_safe_diagnostics_retain_exact_symbols_metadata_and_exclusions(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_CANDIDATE_OUTPUT_DIR", str(tmp_path))
    scan._GOVERNED_MARKET_COVERAGE["per_symbol"] = {"GOOD": "SUCCESS", "MISS": "HTTP_FAILURE"}
    scan._GOVERNED_MARKET_COVERAGE["per_symbol_records"] = {
        "GOOD": {"requested_twelve_symbol": "GOOD", "acquisition_status": "SUCCESS", "retry_count": 0, "http_status": 200},
        "MISS": {"requested_twelve_symbol": "MISS", "acquisition_status": "HTTP_FAILURE", "retry_count": 2,
                 "http_status": 400, "provider_error_message": "symbol unsupported", "failure_stage": "HTTP_RESPONSE"},
    }
    scan._GOVERNED_MARKET_METADATA.clear()
    scan._GOVERNED_MARKET_METADATA.update({
        "MISS": {"company_name": "Missing Corp", "exchange": "NYSE", "country": "US",
                 "security_type": "EQUITY", "market_cap": 100_000_000, "price": 10,
                 "average_volume": 500_000, "is_actively_trading": True, "is_delisted": False},
    })
    scan._GOVERNED_MARKET_EXCLUSION_REASONS.clear()
    scan._GOVERNED_MARKET_EXCLUSION_REASONS["MISS"] = "DATA_ACQUISITION_FAILURE"
    scan._GOVERNED_MARKET_OBSERVATIONS.clear()

    path = scan.persist_failure_safe_market_diagnostics(generated_at="2026-09-08T00:00:00+00:00")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["market_history_success_symbols"] == ["GOOD"]
    assert artifact["market_history_failure_symbols"] == ["MISS"]
    miss = next(row for row in artifact["records"] if row["ticker"] == "MISS")
    assert miss["final_classification"] == "DATA_ACQUISITION_FAILURE"
    assert miss["company_name"] == "Missing Corp"
    assert miss["dollar_volume"] == 5_000_000
    assert miss["retry_count"] == 2
    assert artifact["customer_publication_allowed"] is False


def test_stale_yahoo_batch_metric_names_are_not_emitted():
    source = open("overnight_market_scan.py", encoding="utf-8").read()
    assert "yahoo_batch_seconds=" not in source
    assert '"yahoo_broad_scan_seconds"' not in source
    assert "governed_market_batch_seconds=" in source


def test_zero_validation_control_cannot_be_reported_complete():
    source = open("overnight_market_scan.py", encoding="utf-8").read()
    assert '"COMPLETE" if discovery_recall.get("discovery_gate") == "PASS" else "FAILED_VALIDATION"' in source
    assert 'discovery_recall["status"] = "COMPLETE"\n' not in source
