"""
V39.3 Dashboard AI Sections Helper
Place this file next to app.py.

Minimal app.py usage:
    from dashboard_ai_sections import render_ai_trading_sections
    render_ai_trading_sections()

This adds a cleaner top view without redesigning your whole app:
- Top AI ranked results
- My Watchlist
- Recovery / crashed-stock candidates
- Full ranked scan
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st


DATA_DIR = Path(".")
TOP_IDEAS_FILE = DATA_DIR / "top_ai_ideas.json"
FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
WATCHLIST_SCAN_FILE = DATA_DIR / "watchlist_scan.json"
RECOVERY_SCAN_FILE = DATA_DIR / "recovery_scan.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"


def _load_json(path: Path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def _load_rows(primary: Path, fallback: Path = None) -> List[Dict[str, Any]]:
    rows = _load_json(primary, [])
    if not rows and fallback is not None:
        rows = _load_json(fallback, [])
    return rows if isinstance(rows, list) else []


def _money(value):
    try:
        if value is None or value == "":
            return ""
        return f"${float(value):,.2f}"
    except Exception:
        return value


def _compact_cap(value):
    try:
        value = float(value)
        if value >= 1_000_000_000_000:
            return f"${value/1_000_000_000_000:.1f}T"
        if value >= 1_000_000_000:
            return f"${value/1_000_000_000:.1f}B"
        if value >= 1_000_000:
            return f"${value/1_000_000:.1f}M"
        return f"${value:,.0f}"
    except Exception:
        return ""


def _display_table(rows: List[Dict[str, Any]], limit: int = 25):
    if not rows:
        st.info("No rows available yet. Run the Render Cron Job to refresh scans.")
        return

    df = pd.DataFrame(rows)
    wanted = [
        "symbol", "company_name", "setup_type", "conviction", "price",
        "entry_range", "stop_loss", "target", "risk_reward",
        "sector", "industry", "market_cap", "twenty_day_pct", "sixty_day_pct", "volume_ratio"
    ]
    cols = [c for c in wanted if c in df.columns]
    df = df[cols].head(limit).copy()

    df = df.rename(columns={
        "symbol": "Ticker", "company_name": "Company", "setup_type": "Setup",
        "conviction": "AI Score", "price": "Price", "entry_range": "Entry Range",
        "stop_loss": "Stop", "target": "Target", "risk_reward": "R/R",
        "sector": "Sector", "industry": "Industry", "market_cap": "Mkt Cap",
        "twenty_day_pct": "20D %", "sixty_day_pct": "60D %", "volume_ratio": "Vol x",
    })

    for c in ["Price", "Stop", "Target"]:
        if c in df.columns:
            df[c] = df[c].apply(_money)
    if "Mkt Cap" in df.columns:
        df["Mkt Cap"] = df["Mkt Cap"].apply(_compact_cap)

    st.dataframe(df, use_container_width=True, hide_index=True)


def _idea_cards(rows: List[Dict[str, Any]], limit: int = 5):
    if not rows:
        st.info("No ideas found yet.")
        return

    for row in rows[:limit]:
        symbol = row.get("symbol") or row.get("ticker") or ""
        company = row.get("company_name") or row.get("company") or symbol
        score = row.get("conviction") or row.get("conviction_score") or row.get("score")
        setup = row.get("setup_type") or row.get("bucket") or "AI Setup"
        price = row.get("price") or row.get("current_price")
        entry = row.get("entry_range", "")
        stop = row.get("stop_loss", "")
        target = row.get("target", "")
        rr = row.get("risk_reward", "")
        reasoning = row.get("ai_reasoning") or row.get("guidance") or row.get("summary") or ""
        good = row.get("what_looks_good", "")
        bad = row.get("what_could_go_wrong", "")

        with st.container(border=True):
            left, right = st.columns([0.72, 0.28])
            with left:
                st.subheader(f"{symbol} — {company}")
                st.caption(f"{setup} | AI Score: {score} | Price: {_money(price)}")
                st.write(reasoning)
                if good:
                    st.success(f"Looks good: {good}")
                if bad:
                    st.warning(f"Risk: {bad}")
            with right:
                st.metric("Entry", entry)
                st.metric("Stop", _money(stop))
                st.metric("Target", _money(target))
                st.metric("Risk/Reward", rr)


def _save_watchlist(symbols: List[str]):
    cleaned = []
    for s in symbols:
        sym = str(s).strip().upper()
        if sym and "." not in sym and "/" not in sym:
            cleaned.append(sym)
    cleaned = list(dict.fromkeys(cleaned))
    WATCHLIST_FILE.write_text(json.dumps({"symbols": cleaned}, indent=2), encoding="utf-8")
    return cleaned


def _watchlist_editor():
    raw = _load_json(WATCHLIST_FILE, {"symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "PLTR", "SOFI"]})
    symbols = raw if isinstance(raw, list) else raw.get("symbols", [])
    default_text = ", ".join(symbols)

    with st.expander("Edit Watchlist Tickers", expanded=False):
        text = st.text_area(
            "Tickers to track",
            value=default_text,
            help="Comma-separated ticker list. Example: AAPL, NVDA, SOFI, PLTR",
            key="watchlist_text_area",
        )
        if st.button("Save Watchlist", key="save_watchlist_btn"):
            new_symbols = [x.strip() for x in text.replace("\n", ",").split(",") if x.strip()]
            saved = _save_watchlist(new_symbols)
            st.success(f"Saved {len(saved)} watchlist tickers. Run the Cron Job to refresh watchlist scores.")


def render_ai_trading_sections():
    st.markdown("## AI Trading Command Center")
    st.caption("Top ideas come from the latest overnight scan. Watchlist and recovery setups are separated so different opportunity types are easier to read.")

    top_rows = _load_rows(TOP_IDEAS_FILE, FULL_SCAN_FILE)
    watchlist_rows = _load_rows(WATCHLIST_SCAN_FILE)
    recovery_rows = _load_rows(RECOVERY_SCAN_FILE)
    all_rows = _load_rows(FULL_SCAN_FILE)

    c1, c2, c3 = st.columns(3)
    c1.metric("Top AI Ideas", len(top_rows))
    c2.metric("Watchlist Matches", len(watchlist_rows))
    c3.metric("Recovery Setups", len(recovery_rows))

    tabs = st.tabs(["Top AI Results", "My Watchlist", "Recovery / Crashed Stocks", "All Ranked Scan"])

    with tabs[0]:
        st.markdown("### Highest Ranked AI Setups")
        _idea_cards(top_rows, limit=5)
        st.markdown("### Ranked Table")
        _display_table(top_rows, limit=25)

    with tabs[1]:
        st.markdown("### My Watchlist")
        _watchlist_editor()
        _idea_cards(watchlist_rows, limit=5)
        _display_table(watchlist_rows, limit=50)

    with tabs[2]:
        st.markdown("### Recovery / Reversal Candidates")
        st.caption("These are stocks that may have crashed or pulled back but are showing early signs of stabilization or reversal.")
        _idea_cards(recovery_rows, limit=5)
        _display_table(recovery_rows, limit=50)

    with tabs[3]:
        st.markdown("### Full Ranked Scan")
        _display_table(all_rows, limit=150)
