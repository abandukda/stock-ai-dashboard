
"""
Atlas Professional Dashboard Components — Sprint 3.1
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.components import (
    atlas_dashboard_hero,
    atlas_metric_tile,
    atlas_shell_header,
    opportunity_card,
    section_header,
)
from engines.report_sections.formatting import fmt_pct, safe_text


def _first_value(df: pd.DataFrame | None, column: str, default: str = "") -> str:
    try:
        if df is not None and not df.empty and column in df.columns:
            return safe_text(df.iloc[0].get(column), default)
    except Exception:
        pass
    return default


def _best_ticker(df: pd.DataFrame | None) -> str:
    return _first_value(df, "Ticker", "PODD")


def _best_company(df: pd.DataFrame | None) -> str:
    return _first_value(df, "Company", "Top opportunity from latest scan")


def _score(df: pd.DataFrame | None) -> str:
    for col in ["Opportunity", "Final Conviction", "Score"]:
        val = _first_value(df, col, "")
        if val:
            return str(val)
    return "—"


def _upside(df: pd.DataFrame | None) -> str:
    for col in ["Target Upside %", "Upside", "Upside %"]:
        val = _first_value(df, col, "")
        if val:
            try:
                return fmt_pct(val)
            except Exception:
                return str(val)
    return "—"


def render_professional_home_header(
    full_df: pd.DataFrame | None = None,
    top_df: pd.DataFrame | None = None,
    scanner_version: str = "Latest",
    full_scan_count: int | str = "—",
    prescreen_count: int | str = "—",
    last_scan: str = "Latest completed scan",
    market_tone: str = "Constructive",
) -> None:
    source = top_df if top_df is not None and not top_df.empty else full_df
    top_ticker = _best_ticker(source)
    top_company = _best_company(source)

    atlas_shell_header()

    atlas_dashboard_hero(
        greeting="Good Evening",
        user_name="Asif",
        market_tone=market_tone,
        top_idea=top_ticker,
        scan_count=str(full_scan_count),
        prescreen_count=str(prescreen_count),
        last_scan=last_scan,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        atlas_metric_tile("Market Tone", market_tone, "Current scan environment", "🟢", "success")
    with c2:
        atlas_metric_tile("Top Opportunity", top_ticker, top_company, "⭐", "ai")
    with c3:
        atlas_metric_tile("Full Scan", str(full_scan_count), f"Scanner {scanner_version}", "📡", "info")
    with c4:
        atlas_metric_tile("Prescreen", str(prescreen_count), "Candidates reviewed", "🧠", "ai")

    section_header("🔥", "Today's Best AI Opportunity", "The highest-priority idea surfaced by Atlas from the latest completed scan.")

    opportunity_card(
        ticker=top_ticker,
        company=top_company,
        recommendation=_first_value(source, "Recommendation", "BUY NOW"),
        conviction=_score(source),
        upside=_upside(source),
        entry=_first_value(source, "Entry", _first_value(source, "Entry Range", "")),
        target=_first_value(source, "Target", ""),
    )
