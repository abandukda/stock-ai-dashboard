import pandas as pd

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
