import pandas as pd

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
