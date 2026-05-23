import os
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

APP_VERSION = "V39.0 Stable Clean Dashboard"

st.set_page_config(
    page_title=f"AI Trading Dashboard {APP_VERSION}",
    page_icon="📈",
    layout="wide",
)

# ============================================================
# CONFIG
# ============================================================

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
PRESCREEN_FILE = DATA_DIR / "market_prescreen.json"
SCAN_STATE_FILE = DATA_DIR / "market_scan_state.json"
UNIVERSE_FILE = DATA_DIR / "total_market_universe.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
    "PLTR", "ELF", "SNOW", "COST", "AVGO", "PANW", "CRWD"
]


def first_env(*names, default=""):
    for name in names:
        value = os.getenv(name)
        if value not in [None, ""]:
            return value
    return default


ADMIN_USER = first_env(
    "ADMIN_USER",
    "APP_USERNAME",
    "APP_USER",
    "USERNAME",
    "LOGIN_USER",
    default="admin",
)

ADMIN_PASSWORD = first_env(
    "ADMIN_PASSWORD",
    "APP_PASSWORD",
    "PASSWORD",
    "LOGIN_PASSWORD",
    default="admin",
)


# ============================================================
# BASIC HELPERS
# ============================================================

def read_json_safe(path, default):
    try:
        p = Path(path)
        if p.exists():
            with p.open("r") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def write_json_safe(path, data):
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        st.error(f"Could not save file: {e}")
        return False


def safe_number(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, str) and value.strip() in ["", "N/A", "None", "nan", "NaN", "$N/A", "$None"]:
            return default
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def money_display(value):
    try:
        if value is None or pd.isna(value):
            return "N/A"
        return f"${float(value):,.2f}"
    except Exception:
        s = str(value)
        return "N/A" if s in ["None", "nan", "$None"] else s


def normalize_ticker(ticker):
    return str(ticker or "").strip().upper().replace("$", "")


def company_display(row):
    ticker = row.get("Ticker", "")
    name = row.get("Company Name", "")
    if not name or str(name).strip() in ["", "None", "nan", ticker]:
        return ticker
    return name


# ============================================================
# LOGIN
# ============================================================

def login_gate():
    if st.session_state.get("authenticated"):
        return True

    st.title("🔐 AI Trading Dashboard Login")
    st.caption(APP_VERSION)

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        if username == ADMIN_USER and password == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.session_state.is_admin = True
            st.rerun()
        else:
            st.error("Invalid login. Check your Render environment variables.")

    with st.expander("Login help"):
        st.write("This app checks these environment variables:")
        st.code("ADMIN_USER / ADMIN_PASSWORD\nor APP_USERNAME / APP_PASSWORD\nor APP_USER / APP_PASSWORD")
        st.write("For local testing, defaults are admin/admin if no variables are set.")

    return False


# ============================================================
# DATA LOADING
# ============================================================

def normalize_scan_df(df):
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()

    if "Ticker" not in work.columns:
        return pd.DataFrame()

    work["Ticker"] = work["Ticker"].apply(normalize_ticker)
    work = work[work["Ticker"] != ""]

    if "Company Name" not in work.columns:
        work["Company Name"] = work["Ticker"]

    if "Price" in work.columns:
        work["Price"] = pd.to_numeric(work["Price"], errors="coerce")
    else:
        work["Price"] = None

    if "Final Conviction" not in work.columns:
        if "Quick Score" in work.columns:
            work["Final Conviction"] = pd.to_numeric(work["Quick Score"], errors="coerce").fillna(0)
        else:
            work["Final Conviction"] = 0
    else:
        work["Final Conviction"] = pd.to_numeric(work["Final Conviction"], errors="coerce").fillna(0)

    defaults = {
        "Execution Quality": "Research Candidate",
        "Financial Safety": "Needs Review",
        "Agent Greenlight": "Research Only",
        "Signal": "Research",
        "Investment Style": "Overnight Scan",
        "RSI": "N/A",
        "From 52W High %": "N/A",
        "Entry Range": "Use Detail View",
        "Stop Loss": "N/A",
        "Target / Sell Zone": "N/A",
        "Why Ranked Highly": "Passed overnight scan filters.",
        "Financial Safety Detail": "",
        "Research Summary": "",
        "AI Trade Plan": "",
    }

    for col, val in defaults.items():
        if col not in work.columns:
            work[col] = val

    # Sort high conviction first, then lower price first.
    work = work.sort_values(["Final Conviction", "Price"], ascending=[False, True], na_position="last")

    return work.drop_duplicates(subset=["Ticker"], keep="first")


def load_full_scan():
    data = read_json_safe(FULL_SCAN_FILE, [])
    if not data:
        return pd.DataFrame()
    return normalize_scan_df(pd.DataFrame(data))


def load_prescreen():
    data = read_json_safe(PRESCREEN_FILE, [])
    if not data:
        return pd.DataFrame()
    return normalize_scan_df(pd.DataFrame(data))


def load_best_scan():
    full = load_full_scan()
    pre = load_prescreen()

    # If full scan is very small or mostly unusable, use prescreen.
    if len(full) >= 25:
        return full, "Full AI Scan"

    if len(pre) > len(full):
        return pre, "Broad Prescreen"

    if not full.empty:
        return full, "Full AI Scan"

    return pre, "Broad Prescreen"


def load_watchlist():
    wl = read_json_safe(WATCHLIST_FILE, DEFAULT_WATCHLIST)
    if not isinstance(wl, list):
        wl = DEFAULT_WATCHLIST
    return sorted(set([normalize_ticker(x) for x in wl if normalize_ticker(x)]))


def save_watchlist(watchlist):
    return write_json_safe(WATCHLIST_FILE, sorted(set(watchlist)))


# ============================================================
# UI SECTIONS
# ============================================================

def render_scan_status():
    state = read_json_safe(SCAN_STATE_FILE, {})
    universe = read_json_safe(UNIVERSE_FILE, {})
    full = load_full_scan()
    pre = load_prescreen()

    with st.expander("Scan status", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Universe", universe.get("count", state.get("universe_count", "N/A")) if isinstance(universe, dict) else "N/A")
        c2.metric("Prescreen Rows", len(pre))
        c3.metric("Full Scan Rows", len(full))
        c4.metric("GitHub Persisted", str(state.get("github_persisted", "N/A")))

        st.json(state)


def render_main_table(df, title="📋 All Stock Ideas"):
    st.subheader(title)

    if df is None or df.empty:
        st.warning("No stock ideas found yet. Check the overnight Cron job.")
        return

    left, mid, right = st.columns(3)

    with left:
        min_score = st.slider("Minimum score", 0, 100, 0)

    with mid:
        max_price = st.number_input("Max price", min_value=0.0, value=0.0, step=5.0, help="Use 0 for no max price.")

    with right:
        search = st.text_input("Search ticker/company").strip().upper()

    filtered = df.copy()
    filtered = filtered[filtered["Final Conviction"].fillna(0) >= min_score]

    if max_price:
        filtered = filtered[filtered["Price"].fillna(999999) <= max_price]

    if search:
        mask = filtered["Ticker"].astype(str).str.upper().str.contains(search, na=False)
        mask = mask | filtered["Company Name"].astype(str).str.upper().str.contains(search, na=False)
        filtered = filtered[mask]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Shown", len(filtered))
    c2.metric("Total Loaded", len(df))
    c3.metric("Top Score", int(filtered["Final Conviction"].max()) if not filtered.empty else 0)
    c4.metric("Under $75", len(filtered[filtered["Price"].fillna(999999) < 75]) if "Price" in filtered.columns else 0)

    show_cols = [
        "Ticker",
        "Company Name",
        "Price",
        "Final Conviction",
        "Signal",
        "Execution Quality",
        "Financial Safety",
        "Agent Greenlight",
        "Investment Style",
        "RSI",
        "From 52W High %",
        "Entry Range",
        "Stop Loss",
        "Target / Sell Zone",
        "Why Ranked Highly",
    ]
    show_cols = [c for c in show_cols if c in filtered.columns]

    display_df = filtered[show_cols].copy()
    if "Price" in display_df.columns:
        display_df["Price"] = display_df["Price"].apply(money_display)

    st.dataframe(display_df, use_container_width=True, hide_index=True, height=650)

    with st.expander("Actions for visible stocks", expanded=False):
        for _, row in filtered.head(75).iterrows():
            ticker = row["Ticker"]
            name = company_display(row)
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.write(f"**{ticker}** — {name}")
            with c2:
                if st.button("Details", key=f"detail_{ticker}"):
                    st.session_state.selected_ticker = ticker
                    st.session_state.page = "Detail View"
                    st.rerun()
            with c3:
                if st.button("Add Watch", key=f"watch_{ticker}"):
                    wl = load_watchlist()
                    wl.append(ticker)
                    save_watchlist(wl)
                    st.success(f"Added {ticker}")


def render_watchlist(df):
    st.subheader("⭐ Watchlist")

    wl = load_watchlist()

    c1, c2 = st.columns([3, 1])
    with c1:
        new_ticker = st.text_input("Add ticker").strip().upper()
    with c2:
        if st.button("Add", use_container_width=True):
            if new_ticker:
                wl.append(new_ticker)
                save_watchlist(wl)
                st.rerun()

    if not wl:
        st.info("Watchlist is empty.")
        return

    if df is None or df.empty:
        st.write(", ".join(wl))
        return

    watch_df = df[df["Ticker"].isin(wl)].copy()

    if watch_df.empty:
        st.write(", ".join(wl))
    else:
        render_main_table(watch_df, title="Watchlist Analysis")

    with st.expander("Remove tickers"):
        for ticker in wl:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(ticker)
            with c2:
                if st.button("Remove", key=f"remove_{ticker}"):
                    wl = [x for x in wl if x != ticker]
                    save_watchlist(wl)
                    st.rerun()


def render_detail(df):
    ticker = st.session_state.get("selected_ticker", "")

    typed = st.text_input("Ticker", value=ticker).strip().upper()
    if typed:
        ticker = typed
        st.session_state.selected_ticker = ticker

    if not ticker:
        st.info("Select a ticker from the table.")
        return

    row_df = df[df["Ticker"] == ticker] if df is not None and not df.empty else pd.DataFrame()

    st.subheader(f"🔎 Detail View: {ticker}")

    if row_df.empty:
        st.warning("Ticker not found in latest scan results.")
        return

    row = row_df.iloc[0].to_dict()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company", company_display(row))
    c2.metric("Price", money_display(row.get("Price")))
    c3.metric("Conviction", int(safe_number(row.get("Final Conviction"), 0)))
    c4.metric("Signal", row.get("Signal", "N/A"))

    st.write("### Summary")
    st.write(row.get("Research Summary") or row.get("Why Ranked Highly") or "No summary available.")

    st.write("### Trade Plan")
    st.write(row.get("AI Trade Plan") or "Use your own risk management before acting.")

    st.write("### Financial Safety")
    st.write(row.get("Financial Safety", "N/A"))
    st.write(row.get("Financial Safety Detail", ""))

    st.write("### Raw Scan Row")
    st.json(row)


# ============================================================
# APP
# ============================================================

if not login_gate():
    st.stop()

st.sidebar.title("📈 AI Dashboard")
st.sidebar.caption(APP_VERSION)

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Watchlist", "Detail View", "Scan Status"],
    index=["Dashboard", "Watchlist", "Detail View", "Scan Status"].index(st.session_state.get("page", "Dashboard")) if st.session_state.get("page", "Dashboard") in ["Dashboard", "Watchlist", "Detail View", "Scan Status"] else 0,
)

st.session_state.page = page

scan_df, source = load_best_scan()

st.title(f"📈 AI Trading Dashboard {APP_VERSION}")
st.caption("Stable clean dashboard. Overnight scan results are loaded from JSON files. Not financial advice.")

if page == "Dashboard":
    c1, c2, c3 = st.columns(3)
    c1.metric("Data Source", source)
    c2.metric("Rows Loaded", len(scan_df))
    c3.metric("Last Scan", read_json_safe(SCAN_STATE_FILE, {}).get("finished_at", "N/A"))

    render_scan_status()
    render_main_table(scan_df, title="📋 All Overnight Stock Ideas")

elif page == "Watchlist":
    render_watchlist(scan_df)

elif page == "Detail View":
    render_detail(scan_df)

elif page == "Scan Status":
    render_scan_status()
    st.write("### Files")
    st.write({
        "DATA_DIR": str(DATA_DIR),
        "FULL_SCAN_FILE": str(FULL_SCAN_FILE),
        "PRESCREEN_FILE": str(PRESCREEN_FILE),
        "SCAN_STATE_FILE": str(SCAN_STATE_FILE),
        "UNIVERSE_FILE": str(UNIVERSE_FILE),
    })
