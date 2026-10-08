"""Customer Watchlist change surface backed by existing certified rows."""
from __future__ import annotations

from typing import Any, Callable, Mapping

import streamlit as st

from services.session_stability import emit_page_interactive


def _value(row: Mapping[str, Any], *keys: str) -> Any:
    raw = row.get("Raw") if isinstance(row.get("Raw"), Mapping) else {}
    for key in keys:
        value = row.get(key, raw.get(key))
        if value not in (None, ""):
            return value
    return None


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "Unavailable"


def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "Unavailable"


def _certified_fields(row: Mapping[str, Any]) -> tuple[str, Any]:
    raw = row.get("Raw") if isinstance(row.get("Raw"), Mapping) else row
    evaluation = raw.get("certified_customer_evaluation") if isinstance(raw, Mapping) else {}
    evaluation = evaluation if isinstance(evaluation, Mapping) else {}
    decision = evaluation.get("decision") if isinstance(evaluation.get("decision"), Mapping) else {}
    allowed = evaluation.get("customer_publication_allowed") is True
    action = str(decision.get("action") or "").strip() if allowed else ""
    fields = evaluation.get("certified_fields") if isinstance(evaluation.get("certified_fields"), Mapping) else {}
    fair_value = fields.get("atlas_fair_value")
    if isinstance(fair_value, Mapping):
        fair_value = fair_value.get("value")
    return (action or "RATING_NOT_PUBLISHED", fair_value if allowed else None)


def render_watchlist_vnext(full_df: Any, tickers: list[str], *, open_research: Callable[[str], Any]) -> None:
    st.markdown('<span data-atlas-qa="watchlist-vnext" data-atlas-non-scoring="true" '
                'style="display:none">watchlist-vnext</span>', unsafe_allow_html=True)
    st.title("Watchlist")
    st.caption("What changed since the last certified review. Market-state context cannot change the certified Action.")
    emit_page_interactive(st, "Watchlist Intelligence")
    wanted = {str(item).upper() for item in tickers}
    rows = []
    if full_df is not None and not getattr(full_df, "empty", True):
        for _, item in full_df.iterrows():
            row = dict(item)
            ticker = str(_value(row, "Ticker", "ticker") or "").upper()
            if ticker and (not wanted or ticker in wanted):
                rows.append((ticker, row))
    if not rows:
        st.info("Add a ticker to your Watchlist to see certified decisions and what changed.")
        return
    for ticker, row in rows:
        with st.container(border=True):
            company = str(_value(row, "Company", "company", "Name") or ticker)
            action, certified_fair_value = _certified_fields(row)
            action = action.replace("_", " ")
            price = _value(row, "Price", "Current Price", "current_price")
            fair_value = certified_fair_value
            distance = None
            try:
                distance = (float(fair_value) / float(price) - 1.0) * 100.0
            except (TypeError, ValueError, ZeroDivisionError):
                pass
            st.markdown(f"### {ticker} · {company}")
            cols = st.columns(4)
            cols[0].metric("Certified Action", action)
            cols[1].metric("Current / reference", _money(price))
            cols[2].metric("ATLAS Fair Value", _money(fair_value))
            cols[3].metric("Distance to Fair Value", _pct(distance))
            st.write("**What changed:** " + str(_value(row, "What Changed", "change_since_last_scan", "material_change") or "No governed material change is attached."))
            st.caption("Earnings: " + str(_value(row, "Next Earnings", "next_earnings_date", "earnings_date") or "Unavailable") + " · Transcript/context: " + ("Available" if _value(row, "transcript_url", "earnings_transcript_url", "earnings_summary") else "Unavailable"))
            if st.button(f"Open Research — {ticker}", key=f"watchlist-vnext-{ticker}", use_container_width=True):
                open_research(ticker)


__all__ = ["render_watchlist_vnext"]
