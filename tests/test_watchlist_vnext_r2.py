import pandas as pd
from pathlib import Path

from ui.watchlist_vnext import _clean_ticker, _money, _security_type, _verified_price, _watchlist_rows


def test_empty_watchlist_never_expands_to_the_full_universe():
    universe = pd.DataFrame([{"Ticker": "NVDA"}, {"Ticker": "MSFT"}])
    assert _watchlist_rows(universe, []) == []


def test_saved_unknown_and_variant_symbols_are_preserved():
    universe = pd.DataFrame([{"Ticker": "NVDA", "Company": "NVIDIA"}])
    rows = _watchlist_rows(universe, ["NVDA", "AAC.WT", "AAC/UN"])
    assert [ticker for ticker, _ in rows] == ["AAC.WT", "AAC/UN", "NVDA"]
    assert _clean_ticker("aac.wt") == "AAC.WT"
    assert _security_type("AAC.WT", {}) == ("Warrant", False)
    assert _security_type("AAC/UN", {"security_type": "UNIT"}) == ("Unit", False)


def test_missing_or_nonpositive_price_is_never_rendered_as_zero():
    assert _money(None) == "Unavailable"
    assert _money(0) == "Unavailable"
    assert _money(-2) == "Unavailable"
    assert _verified_price({"Price": 0}) == (None, None)
    assert _verified_price({"Price": 23.5, "Price Date": "2026-10-08"}) == (23.5, "2026-10-08")


def test_search_filter_positive_negative_and_clear_states_are_exact():
    universe = pd.DataFrame([
        {"Ticker": "NVDA", "Company": "NVIDIA Corporation"},
        {"Ticker": "MSFT", "Company": "Microsoft Corporation"},
    ])
    saved = ["NVDA", "AAAAQ"]
    assert [ticker for ticker, _ in _watchlist_rows(universe, saved, query="NVD")] == ["NVDA"]
    assert _watchlist_rows(universe, saved, query="NO_MATCH_QA") == []
    assert [ticker for ticker, _ in _watchlist_rows(universe, saved, query="")] == ["AAAAQ", "NVDA"]


def test_customer_market_tape_hides_internal_fallback_language():
    source = Path("app.py").read_text(encoding="utf-8")
    start = source.rindex("def render_v72_market_tape(always_show=True):")
    function = source[start:source.index("\ndef v74_market_regime", start)]
    assert "if is_viewer():" in function
    assert function.index("if is_viewer():") < function.index("Live source unavailable")
    assert "latest retained completed-session evidence" in function
