import pandas as pd
import pytest

from overnight_market_scan import attach_technical_research_evidence, compute_indicators
from services.governed_market_cache import append_history, normalize_history_frame


def test_sma200_display_canonical_and_governed_snapshot_are_equal():
    history = pd.DataFrame(
        {"Close": [float(value) for value in range(1, 221)]},
        index=pd.date_range("2026-01-01", periods=220, tz="UTC"),
    )
    history.iloc[-1, 0] = 220.123
    canonical = float(history["Close"].rolling(200).mean().iloc[-1])
    indicators = compute_indicators(history)
    row = {}
    attach_technical_research_evidence(row, indicators, history)
    evidence = row["deep_research_evidence"]
    assert evidence["sma200"] == round(canonical, 2)
    assert evidence["sma200_provider"] == "TWELVE_DATA"
    assert evidence["sma200_source_type"] == "TWELVE_DATA_TIME_SERIES_1DAY"
    assert evidence["sma200_unrounded"] == canonical


def test_sma200_mismatch_fails_closed():
    history = pd.DataFrame(
        {"Close": [float(value) for value in range(1, 221)]},
        index=pd.date_range("2026-01-01", periods=220, tz="UTC"),
    )
    with pytest.raises(RuntimeError, match="SMA200_GOVERNED_HISTORY_RECONCILIATION_FAILED"):
        attach_technical_research_evidence({}, {"sma200": 1.0, "sma200_unrounded": 1.0}, history)


def test_unsorted_timezone_and_duplicate_representation_is_deterministic():
    index = list(pd.date_range("2025-01-01", periods=220, tz="America/New_York"))
    history = pd.DataFrame({"Close": [float(value) for value in range(220)]}, index=index)
    duplicate = pd.DataFrame({"Close": [219.0]}, index=[index[-1].tz_convert("UTC")])
    scrambled = pd.concat([history.iloc[::-1], duplicate])
    normalized = normalize_history_frame(scrambled)
    indicators = compute_indicators(scrambled)
    expected = float(normalized["Close"].tail(200).mean())
    assert indicators["sma200_unrounded"] == expected
    row = {}
    attach_technical_research_evidence(row, indicators, scrambled)
    assert row["deep_research_evidence"]["sma200"] == round(expected, 2)


def test_cache_append_and_recompute_is_deterministic(tmp_path):
    namespace = "sma"
    index = pd.date_range("2025-01-01", periods=220, tz="UTC")
    first = pd.DataFrame({"Close": range(210)}, index=index[:210])
    fresh = pd.DataFrame({"Close": range(205, 220)}, index=index[205:])
    append_history(tmp_path, "TEST", first, namespace=namespace)
    combined = append_history(tmp_path, "TEST", fresh.iloc[::-1], namespace=namespace)
    indicators = compute_indicators(combined)
    assert indicators["sma200_unrounded"] == float(combined["Close"].tail(200).mean())
    row = {}
    attach_technical_research_evidence(row, indicators, combined)
    assert row["deep_research_evidence"]["sma200_status"] == "AVAILABLE"


def test_insufficient_history_fails_closed_without_publishing_sma200():
    history = pd.DataFrame({"Close": range(199)}, index=pd.date_range("2025-01-01", periods=199, tz="UTC"))
    row = {}
    attach_technical_research_evidence(row, compute_indicators(history), history)
    assert row["deep_research_evidence"] == {"sma200_status": "DATA_UNAVAILABLE_INSUFFICIENT_HISTORY"}
