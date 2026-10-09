"""Customer Watchlist change surface backed by existing certified rows."""
from __future__ import annotations

from typing import Any, Callable, Mapping

import streamlit as st

from services.session_stability import emit_page_interactive
from services.customer_authority import customer_authority
from ui.atlas_design_system import action_badge


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
    authority = customer_authority(row)
    return (
        str(authority.get("action") or "RATING_NOT_PUBLISHED"),
        authority.get("fair_value") if authority.get("status") == "AVAILABLE" else None,
    )


def render_watchlist_vnext(full_df: Any, tickers: list[str], *, open_research: Callable[[str], Any]) -> None:
    st.markdown('<span data-atlas-qa="watchlist-vnext" data-atlas-non-scoring="true" '
                'style="display:none">watchlist-vnext</span>', unsafe_allow_html=True)
    st.markdown('<div class="atlas-kicker">Certified monitoring</div>', unsafe_allow_html=True)
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
        st.markdown(
            '<div class="atlas-empty-state"><strong>Your certified watchlist is ready.</strong>'
            '<span>Add a ticker to monitor its ATLAS decision and meaningful changes.</span></div>',
            unsafe_allow_html=True,
        )
        return
    for ticker, row in rows:
        with st.container(border=True):
            st.markdown('<span class="atlas-watchlist-card-anchor" aria-hidden="true"></span>', unsafe_allow_html=True)
            company = str(_value(row, "Company", "company", "Name") or ticker)
            authority = customer_authority(row)
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
            st.markdown(action_badge(action), unsafe_allow_html=True)
            st.markdown(
                f'<span data-atlas-qa="watchlist-certified-authority" data-atlas-ticker="{ticker}" '
                f'data-atlas-publication-allowed="{str(authority.get("publication_allowed") is True).lower()}" '
                f'data-atlas-evaluation-snapshot="{authority.get("evaluation_snapshot") or ""}" '
                f'aria-hidden="true" style="display:none">certified-authority</span>',
                unsafe_allow_html=True,
            )
            decision_cols = st.columns(3)
            decision_cols[0].metric("Certified Action", action)
            decision_cols[1].metric("ATLAS Fair Value", _money(fair_value))
            decision_cols[2].metric("Opportunity", f'{float(authority["opportunity"]):.2f}' if authority.get("opportunity") is not None else "Unavailable")
            context_cols = st.columns(3)
            context_cols[0].metric("Decision Confidence", f'{float(authority["confidence"]):.2f}' if authority.get("confidence") is not None else "Unavailable")
            context_cols[1].metric("Current / reference", _money(price))
            context_cols[2].metric("Distance to Fair Value", _pct(distance))
            st.write("**What changed:** " + str(_value(row, "What Changed", "change_since_last_scan", "material_change") or "No governed material change is attached."))
            st.caption("Earnings: " + str(_value(row, "Next Earnings", "next_earnings_date", "earnings_date") or "Unavailable") + " · Transcript/context: " + ("Available" if _value(row, "transcript_url", "earnings_transcript_url", "earnings_summary") else "Unavailable"))
            if st.button(f"Open Research — {ticker}", key=f"watchlist-vnext-{ticker}", use_container_width=True):
                open_research(ticker)


__all__ = ["render_watchlist_vnext"]
