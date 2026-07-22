
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd
import streamlit as st

_DATE_KEYS = ("next_earnings_date","Next Earnings","Next Earnings Date","earnings_date","Earnings Date","latest_earnings_date","reportDate","date")

def _first(row: Mapping[str, Any], keys):
    sources=[row]
    for nested in ("raw","Raw"):
        value=row.get(nested)
        if isinstance(value,Mapping): sources.append(value)
    for source in sources:
        for key in keys:
            value=source.get(key)
            if value not in (None,"","N/A","Unavailable","Under review"):
                return value
    return None

def render_v104_earnings_briefing(pipeline: Mapping[str, Any]) -> None:
    rows=pipeline.get("ranked_candidates") or pipeline.get("all_rows") or []
    earnings=[]
    for row in rows:
        date=_first(row,_DATE_KEYS)
        if not date: continue
        earnings.append({
            "Ticker":row.get("ticker"),
            "Company":row.get("company"),
            "Next Earnings":date,
            "Committee Verdict":str(row.get("committee_verdict") or "MONITOR").replace("_"," ").title(),
            "Opportunity":row.get("opportunity_score"),
            "Confidence":row.get("confidence_pct"),
        })

    st.markdown("## Earnings Calendar")
    st.caption("Upcoming earnings dates found in the current scan, including nested raw scanner fields.")
    show=st.toggle("Show upcoming earnings",value=False,key="v1046_earnings_toggle")
    if show:
        if earnings:
            st.dataframe(pd.DataFrame(earnings[:25]),hide_index=True,use_container_width=True)
        else:
            st.info("No upcoming earnings dates were found in the current scan. The legacy Earnings Intelligence page remains available for live lookup.")

__all__=["render_v104_earnings_briefing"]
