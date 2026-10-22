"""Customer Watchlist change surface backed by existing certified rows."""
from __future__ import annotations

import html
from typing import Any, Callable, Mapping
import re

import streamlit as st

from services.session_stability import emit_page_interactive
from services.customer_authority import customer_authority
from services.customer_research_view import Availability, build_customer_research_view, customer_date
from services.customer_metric_format import customer_confidence, customer_money, customer_percent, customer_score
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
        number = float(value)
        return f"${number:,.2f}" if number > 0 else "Unavailable"
    except (TypeError, ValueError):
        return "Unavailable"


def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "Unavailable"


def _certified_fields(row: Mapping[str, Any]) -> tuple[str, Any]:
    # Retained for the legacy helper contract. The live renderer below uses
    # CustomerResearchView so all complete customer records share one route
    # projection; this helper accepts older minimal certified fixtures too.
    authority = customer_authority(row)
    return (
        str(authority.get("action") or "RATING_NOT_PUBLISHED"),
        authority.get("fair_value") if authority.get("status") == "AVAILABLE" else None,
    )


def _security_type(ticker: str, row: Mapping[str, Any]) -> tuple[str, bool]:
    raw = str(_value(row, "Security Type", "security_type", "quote_type") or "").strip().upper()
    if raw in {"COMMON_STOCK", "COMMON STOCK", "EQUITY", "CS"}:
        return "Common stock", True
    if raw in {"ETF", "EXCHANGE_TRADED_FUND"}:
        return "ETF", True
    if raw in {"WARRANT", "WT"} or ticker.endswith(".WT"):
        return "Warrant", False
    if raw in {"UNIT", "UN"} or ticker.endswith(".UN") or ticker.endswith("U"):
        return "Unit", False
    if raw in {"PREFERRED", "PREFERRED_STOCK"}:
        return "Preferred security", False
    return (raw.replace("_", " ").title() if raw else "Security type unavailable"), False


def _verified_price(row: Mapping[str, Any]) -> tuple[float | None, str | None]:
    value = _value(row, "Price", "Current Price", "current_price", "certified_close")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, None
    if number <= 0:
        return None, None
    as_of = _value(row, "Price Date", "price_date", "price_timestamp", "as_of", "certified_at")
    return number, str(as_of).strip() if as_of not in (None, "") else None


def _clean_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    return ticker if re.fullmatch(r"[A-Z0-9][A-Z0-9.\-/]{0,11}", ticker) else ""


def _watchlist_rows(full_df: Any, tickers: list[str], *, query: str = "", sort_by: str = "Ticker") -> list[tuple[str, dict[str, Any]]]:
    """Return only customer-owned symbols; never expand an empty watchlist."""
    wanted = {_clean_ticker(item) for item in tickers if _clean_ticker(item)}
    needle = str(query or "").strip().upper()
    rows: list[tuple[str, dict[str, Any]]] = []
    if full_df is not None and not getattr(full_df, "empty", True):
        for _, item in full_df.iterrows():
            row = dict(item)
            ticker = str(_value(row, "Ticker", "ticker") or "").upper()
            company = str(_value(row, "Company", "company", "Name") or "").upper()
            if ticker in wanted and (not needle or needle in ticker or needle in company):
                rows.append((ticker, row))
    found = {ticker for ticker, _ in rows}
    for ticker in sorted(wanted - found):
        if not needle or needle in ticker:
            rows.append((ticker, {"ticker": ticker}))
    if sort_by in {"Opportunity", "Confidence"}:
        key_name = "opportunity" if sort_by == "Opportunity" else "confidence"
        rows.sort(key=lambda pair: float(build_customer_research_view(pair[1]).surface.get(key_name) or -1), reverse=True)
    else:
        rows.sort(key=lambda pair: pair[0])
    return rows


def render_watchlist_vnext(
    full_df: Any,
    tickers: list[str],
    *,
    open_research: Callable[[str], Any],
    add_symbol: Callable[[str], bool] | None = None,
    remove_symbol: Callable[[str], bool] | None = None,
) -> None:
    st.markdown('<span data-atlas-qa="watchlist-vnext" data-atlas-non-scoring="true" '
                'style="display:none">watchlist-vnext</span>', unsafe_allow_html=True)
    st.markdown(
        '<section class="atlas-page-hero atlas-page-hero-watchlist atlas-ai-insight-panel">'
        '<div class="atlas-kicker">Certified monitoring</div><h1>Watchlist</h1>'
        '<p>Track material changes without losing the certified investment view.</p>'
        '<span>Market-state context cannot change the certified Action.</span></section>',
        unsafe_allow_html=True,
    )
    emit_page_interactive(st, "Watchlist Intelligence")
    from services.watchlist_access import workspace_watchlist_allowed
    if not workspace_watchlist_allowed(st.session_state):
        st.markdown('<span data-atlas-qa="watchlist-access-pending" '
                    'data-atlas-watchlist-access="denied" style="display:none">'
                    'watchlist-access-pending</span>', unsafe_allow_html=True)
        st.info("Personal watchlists are awaiting individual account access. Shared-password sessions cannot read or edit a saved watchlist.")
        return
    st.caption("Administrator workspace watchlist — this shared list is not a personal beta-user account.")
    controls = st.columns([3, 2, 2])
    query = controls[0].text_input("Search your watchlist", key="watchlist-vnext-search").strip().upper()
    sort_by = controls[1].selectbox("Sort", ("Ticker", "Opportunity", "Confidence"), key="watchlist-vnext-sort")
    with controls[2]:
        new_ticker = st.text_input("Add ticker", key="watchlist-vnext-add").strip().upper()
        if st.button("Add", key="watchlist-vnext-add-button", use_container_width=True):
            clean = _clean_ticker(new_ticker)
            if not clean:
                st.error("Enter a valid ticker.")
            elif add_symbol is None:
                st.info("Watchlist editing is unavailable in this session.")
            elif add_symbol(clean):
                st.success(f"Added {clean}.")
                st.rerun()
    rows = _watchlist_rows(full_df, tickers, query=query, sort_by=sort_by)
    visible_tickers = ",".join(ticker for ticker, _ in rows)
    st.markdown(
        f'<span data-atlas-qa="watchlist-filter-state" '
        f'data-atlas-query="{html.escape(query, quote=True)}" '
        f'data-atlas-visible-count="{len(rows)}" '
        f'data-atlas-visible-tickers="{html.escape(visible_tickers, quote=True)}" '
        f'data-atlas-sort="{html.escape(sort_by, quote=True)}" '
        'aria-hidden="true" style="display:none">watchlist-filter-state</span>',
        unsafe_allow_html=True,
    )
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
            customer_view = build_customer_research_view(row)
            authority = customer_view.surface
            action, certified_fair_value = _certified_fields(row)
            action = action.replace("_", " ")
            price = authority.get("certified_close")
            price_as_of = authority.get("certified_close_at")
            security_type, supported = _security_type(ticker, row)
            fair_value = certified_fair_value
            distance = None
            try:
                distance = (float(fair_value) / float(price) - 1.0) * 100.0
            except (TypeError, ValueError, ZeroDivisionError):
                pass
            st.markdown(f"### {ticker} · {company}")
            st.caption(security_type + (" · Research supported" if supported else " · Saved for identification; certified Research may be unavailable"))
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
            decision_cols[1].metric("ATLAS Fair Value", customer_money(fair_value))
            decision_cols[2].metric("Opportunity", customer_score(authority.get("opportunity")))
            context_cols = st.columns(3)
            context_cols[0].metric("Confidence", customer_confidence(authority.get("confidence")))
            price_label = "Last Certified Close"
            if authority.get("certified_close_availability") == Availability.CERTIFIED_DATED.value:
                price_label += " · Dated"
            context_cols[1].metric(
                price_label,
                customer_money(price),
                help=(f"Certified as of {customer_date(price_as_of)}; this is not a live quote." if price_as_of else "Certified close unavailable"),
            )
            context_cols[2].metric("Distance to Fair Value", customer_percent(distance, signed=True) if distance is not None else "Unavailable")
            st.write("**What changed:** " + str(_value(row, "What Changed", "change_since_last_scan", "material_change") or "No governed material change is attached."))
            from services.customer_narrative_projection import customer_narrative_projection
            narrative = customer_narrative_projection(row)
            st.markdown(
                f'<span data-atlas-qa="shared-customer-narrative" data-atlas-ticker="{ticker}" '
                f'data-atlas-source="{html.escape(str(narrative.get("source") or "UNAVAILABLE"))}" '
                'style="display:none">shared-customer-narrative</span>', unsafe_allow_html=True,
            )
            st.caption("Earnings: " + str(_value(row, "Next Earnings", "next_earnings_date", "earnings_date") or "Unavailable") + " · Transcript/context: " + ("Available" if _value(row, "transcript_url", "earnings_transcript_url", "earnings_summary") else "Unavailable"))
            if st.button(f"Open Research — {ticker}", key=f"watchlist-vnext-{ticker}", use_container_width=True):
                open_research(ticker)
            if remove_symbol is not None and st.button(f"Remove {ticker}", key=f"watchlist-vnext-remove-{ticker}"):
                if remove_symbol(ticker):
                    st.rerun()


__all__ = ["_clean_ticker", "_security_type", "_verified_price", "_watchlist_rows", "render_watchlist_vnext"]
