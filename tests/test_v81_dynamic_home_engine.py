import pandas as pd
from engines.dynamic_home_engine import build_home_sections, build_dynamic_home_sections

def _df():
    return pd.DataFrame([
        {"Ticker":"MSFT","Quality":95,"Opportunity":80,"Confidence":85,"Technical Score":75,"Valuation Score":70,"Market Cap":3_000_000_000_000},
        {"Ticker":"XYZ","Quality":82,"Opportunity":88,"Confidence":78,"Technical Score":84,"Valuation Score":76,"Market Cap":5_000_000_000,"Analyst Count":4},
    ])

def test_compat_alias_and_sections():
    a=build_home_sections(_df()); b=build_dynamic_home_sections(_df())
    assert a["today"]
    assert a["mega"]
    assert a["hidden"]
    assert b["today"]

def test_repeated_call_is_stable():
    a=build_home_sections(_df()); b=build_home_sections(_df())
    assert [r["Ticker"] for r in a["today"]] == [r["Ticker"] for r in b["today"]]
