import json

from services.historical_volume_stability import DISPUTED_SESSIONS, append_stability_observation


def _rows(twelve=100, finnhub=101):
    return [{"ticker": ticker, "session_date": date, "twelve_volume": twelve, "finnhub_volume": finnhub,
             "absolute_difference": abs(twelve-finnhub), "percentage_difference": 1.0,
             "root_cause_evidence": "TEST"}
            for ticker, dates in DISPUTED_SESSIONS.items() for date in dates]


def _records():
    return {ticker: {"historical_ohlcv": {"provenance": {
        "market_coverage_class": "FULL_CONSOLIDATED", "adapter_version": "FINNHUB_TEST",
        "raw_evidence_id": f"FINNHUB:{ticker}",
    }}} for ticker in DISPUTED_SESSIONS}


def test_first_observation_is_append_only_and_insufficient(tmp_path):
    path = tmp_path / "ledger.json"
    report = append_stability_observation(path, forensic_rows=_rows(), provider_records=_records(),
                                          observed_at="2026-09-20T12:00:00Z")
    assert len(report["observations"]) == 11
    assert all(item["classification"] == "INSUFFICIENT_OBSERVATIONS" for item in report["per_session_history"])
    assert json.loads(path.read_text())["append_only"] is True


def test_same_day_rerun_does_not_count_as_independent_day(tmp_path):
    path = tmp_path / "ledger.json"
    append_stability_observation(path, forensic_rows=_rows(), provider_records=_records(), observed_at="2026-09-20T12:00:00Z")
    report = append_stability_observation(path, forensic_rows=_rows(), provider_records=_records(), observed_at="2026-09-20T18:00:00Z")
    assert len(report["observations"]) == 22
    assert all(item["independent_calendar_day_count"] == 1 for item in report["per_session_history"])
    assert all(item["classification"] == "INSUFFICIENT_OBSERVATIONS" for item in report["per_session_history"])


def test_three_stable_calendar_days_classify_stable_provider_divergence(tmp_path):
    path = tmp_path / "ledger.json"
    for day in (20, 21, 22):
        report = append_stability_observation(path, forensic_rows=_rows(), provider_records=_records(),
                                              observed_at=f"2026-09-{day}T12:00:00Z")
    assert all(item["classification"] == "STABLE_PROVIDER_DIVERGENCE" for item in report["per_session_history"])
    assert all(item["identical_to_prior"] is True for item in report["per_session_history"])


def test_changed_provider_remains_insufficient_before_three_days(tmp_path):
    path = tmp_path / "ledger.json"
    append_stability_observation(path, forensic_rows=_rows(), provider_records=_records(), observed_at="2026-09-20T12:00:00Z")
    report = append_stability_observation(path, forensic_rows=_rows(finnhub=100.5), provider_records=_records(),
                                          observed_at="2026-09-21T12:00:00Z")
    assert all(item["finnhub_changed"] is True for item in report["per_session_history"])
    assert all(item["moved_toward"] is True for item in report["per_session_history"])
    assert all(item["classification"] == "INSUFFICIENT_OBSERVATIONS" for item in report["per_session_history"])
