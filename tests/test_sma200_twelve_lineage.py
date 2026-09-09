import pandas as pd
import pytest

from overnight_market_scan import attach_technical_research_evidence


def test_sma200_display_canonical_and_governed_snapshot_are_equal():
    history = pd.DataFrame(
        {"Close": [float(value) for value in range(1, 221)]},
        index=pd.date_range("2026-01-01", periods=220, tz="UTC"),
    )
    canonical = float(history["Close"].rolling(200).mean().iloc[-1])
    row = {}
    attach_technical_research_evidence(row, {"sma200": canonical}, history)
    evidence = row["deep_research_evidence"]
    assert evidence["sma200"] == round(canonical, 2)
    assert evidence["sma200_provider"] == "TWELVE_DATA"
    assert evidence["sma200_source_type"] == "TWELVE_DATA_TIME_SERIES_1DAY"


def test_sma200_mismatch_fails_closed():
    history = pd.DataFrame(
        {"Close": [float(value) for value in range(1, 221)]},
        index=pd.date_range("2026-01-01", periods=220, tz="UTC"),
    )
    with pytest.raises(RuntimeError, match="SMA200_GOVERNED_HISTORY_RECONCILIATION_FAILED"):
        attach_technical_research_evidence({}, {"sma200": 1.0}, history)
