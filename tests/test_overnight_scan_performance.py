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
    calls = []
    monkeypatch.setattr(scan, "FAST_CRON_MODE", True)
    monkeypatch.setattr(scan, "FAST_CRON_SKIP_PRE_RANK_DEEP_APIS", True)
    monkeypatch.setattr(scan, "v421_should_run_full_research", lambda symbol, row: True)
    monkeypatch.setattr(scan, "get_fmp_data", lambda symbol: calls.append(symbol) or {
        "sector": "Technology", "country": "US", "source_fmp_profile": True,
    })
    monkeypatch.setattr(scan, "v42_build_committee_safe", lambda symbol, row, meta, ind, hist: row)
    monkeypatch.setattr(scan, "v42_apply_investor_translations_safe", lambda row: row)

    row = scan.v421_apply_tiered_committee(
        "NVDA", {"ticker": "NVDA", "sector": "Unknown"}, {}, {}, pd.DataFrame()
    )

    assert calls == ["NVDA"]
    assert row["sector"] == "Technology"
    assert row["country"] == "US"
    assert row["source_fmp_profile"] is True
    assert row["v42_tier"] == "full"


def test_successful_yahoo_batch_has_no_unconditional_sleep(monkeypatch):
    sleeps = []
    frame = pd.DataFrame({"Close": [100.0]})
    monkeypatch.setattr(scan.yf, "download", lambda **kwargs: frame)
    monkeypatch.setattr(scan.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = scan.download_price_batch(["NVDA", "AVGO"])

    assert result is frame
    assert sleeps == []


def test_yahoo_failure_keeps_exponential_retry_backoff(monkeypatch):
    sleeps = []
    attempts = []
    frame = pd.DataFrame({"Close": [100.0]})

    def download(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise RuntimeError("429 rate limited")
        return frame

    monkeypatch.setattr(scan.yf, "download", download)
    monkeypatch.setattr(scan.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = scan.download_price_batch(["NVDA"])

    assert result is frame
    assert len(attempts) == 2
    assert sleeps == [1]
