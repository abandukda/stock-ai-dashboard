from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
import streamlit as st

QuoteFetcher=Callable[[Sequence[str]],Mapping[str,Mapping[str,Any]]]

def normalize_quote(ticker: str, raw: Mapping[str, Any], source="") -> dict[str, Any]:
    price=raw.get("price") or raw.get("last") or raw.get("last_price") or raw.get("c")
    timestamp=raw.get("price_as_of") or raw.get("timestamp") or raw.get("t")
    return {"ticker":ticker,"price":price,"price_as_of":str(timestamp or datetime.now(timezone.utc).isoformat()),"quote_source":source or str(raw.get("source") or "Atlas quote provider"),"market_status":str(raw.get("market_status") or "UNKNOWN")}

@st.cache_data(ttl=1800,show_spinner=False)
def cached_batch_quotes(tickers: tuple[str,...],provider_key: str,_fetcher: QuoteFetcher) -> dict[str,dict[str,Any]]:
    raw=_fetcher(list(tickers)); out={}
    for ticker in tickers:
        item=raw.get(ticker) or {}
        if item: out[ticker]=normalize_quote(ticker,item,provider_key)
    return out

def get_quotes_with_fallback(tickers: Sequence[str],fetcher: QuoteFetcher,provider_key: str,last_good=None) -> dict[str,Any]:
    ordered=tuple(sorted({str(t).upper() for t in tickers if str(t).strip()}))
    try:
        quotes=cached_batch_quotes(ordered,provider_key,fetcher)
        if not quotes: raise RuntimeError("Provider returned no quotes.")
        return {"status":"LIVE","quotes":quotes,"error":""}
    except Exception as exc:
        return {"status":"FALLBACK","quotes":dict(last_good or {}),"error":str(exc)}

__all__=["QuoteFetcher","cached_batch_quotes","get_quotes_with_fallback","normalize_quote"]
