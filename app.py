import os
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

APP_VERSION = "V39.3 AI Reasoning + Watchlist Dashboard"

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
TOP_IDEAS_FILE = DATA_DIR / "top_ai_ideas.json"
WATCHLIST_SCAN_FILE = DATA_DIR / "watchlist_scan.json"
RECOVERY_SCAN_FILE = DATA_DIR / "recovery_scan.json"

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

    # V39.3 scanner outputs lowercase fields. Older V39 used display-case fields.
    rename_map = {
        "symbol": "Ticker",
        "ticker": "Ticker",
        "company": "Company Name",
        "company_name": "Company Name",
        "name": "Company Name",
        "price": "Price",
        "current_price": "Price",
        "last_price": "Price",
        "conviction": "Final Conviction",
        "conviction_score": "Final Conviction",
        "score": "Final Conviction",
        "ai_score": "Final Conviction",
        "setup_type": "Investment Style",
        "bucket": "Investment Style",
        "rsi": "RSI",
        "entry_range": "Entry Range",
        "stop_loss": "Stop Loss",
        "target": "Target / Sell Zone",
        "why_ranked_high": "Why Ranked Highly",
        "ai_reasoning": "Research Summary",
        "guidance": "AI Trade Plan",
        "what_looks_good": "Execution Quality",
        "what_could_go_wrong": "Financial Safety Detail",
        "sector": "Sector",
        "industry": "Industry",
        "market_cap": "Market Cap",
        "risk_reward": "Risk/Reward",
        "twenty_day_pct": "20D %",
        "sixty_day_pct": "60D %",
        "volume_ratio": "Volume Ratio",
        "dollar_volume": "Dollar Volume",
    }

    for old, new in rename_map.items():
        if old in work.columns and new not in work.columns:
            work[new] = work[old]

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
        "Sector": "Unknown",
        "Industry": "Unknown",
        "Market Cap": "N/A",
        "Risk/Reward": "N/A",
        "20D %": "N/A",
        "60D %": "N/A",
        "Volume Ratio": "N/A",
    }

    for col, val in defaults.items():
        if col not in work.columns:
            work[col] = val

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


def load_top_ai_ideas():
    data = read_json_safe(TOP_IDEAS_FILE, [])
    if not data:
        return pd.DataFrame()
    return normalize_scan_df(pd.DataFrame(data))


def load_watchlist_scan():
    data = read_json_safe(WATCHLIST_SCAN_FILE, [])
    if not data:
        return pd.DataFrame()
    return normalize_scan_df(pd.DataFrame(data))


def load_recovery_scan():
    data = read_json_safe(RECOVERY_SCAN_FILE, [])
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
    wl = read_json_safe(WATCHLIST_FILE, {"symbols": DEFAULT_WATCHLIST})
    if isinstance(wl, dict):
        wl = wl.get("symbols", DEFAULT_WATCHLIST)
    if not isinstance(wl, list):
        wl = DEFAULT_WATCHLIST
    return sorted(set([normalize_ticker(x) for x in wl if normalize_ticker(x)]))


def save_watchlist(watchlist):
    cleaned = sorted(set([normalize_ticker(x) for x in watchlist if normalize_ticker(x)]))
    return write_json_safe(WATCHLIST_FILE, {"symbols": cleaned})

# ============================================================
# UI SECTIONS
# ============================================================

def render_ai_idea_cards(df, title="Top AI Results", limit=5):
    st.subheader(title)

    if df is None or df.empty:
        st.info("No AI ideas available yet. Run the Render Cron Job to generate V39.3 files.")
        return

    for _, row in df.head(limit).iterrows():
        ticker = row.get("Ticker", "")
        company = company_display(row)
        score = int(safe_number(row.get("Final Conviction"), 0))
        setup = row.get("Investment Style", "AI Setup")
        price = money_display(row.get("Price"))
        entry = row.get("Entry Range", "N/A")
        stop = row.get("Stop Loss", "N/A")
        target = row.get("Target / Sell Zone", "N/A")
        rr = row.get("Risk/Reward", "N/A")

        with st.container(border=True):
            left, right = st.columns([0.72, 0.28])

            with left:
                st.markdown(f"### {ticker} — {company}")
                st.caption(f"{setup} | AI Score: {score} | Price: {price}")
                st.write(row.get("Research Summary") or row.get("AI Trade Plan") or row.get("Why Ranked Highly") or "No AI reasoning available.")

                good = row.get("Execution Quality", "")
                risk = row.get("Financial Safety Detail", "")
                if good:
                    st.success(f"Looks good: {good}")
                if risk:
                    st.warning(f"What could go wrong: {risk}")

            with right:
                st.metric("Entry", entry)
                st.metric("Stop", money_display(stop) if isinstance(stop, (int, float)) else stop)
                st.metric("Target", money_display(target) if isinstance(target, (int, float)) else target)
                st.metric("Risk/Reward", rr)


def render_clean_ai_command_center(scan_df):
    top_df = load_top_ai_ideas()
    if top_df.empty:
        top_df = scan_df.head(25).copy() if scan_df is not None and not scan_df.empty else pd.DataFrame()

    watch_scan_df = load_watchlist_scan()
    recovery_df = load_recovery_scan()

    st.subheader("🤖 AI Trading Command Center")
    st.caption("Top results are sorted by AI conviction. Watchlist and recovery setups are separated so the dashboard is easier to read.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Top AI Ideas", len(top_df))
    c2.metric("Watchlist Matches", len(watch_scan_df))
    c3.metric("Recovery Setups", len(recovery_df))
    c4.metric("Full Scan Rows", len(scan_df) if scan_df is not None else 0)

    tabs = st.tabs(["Top AI Results", "My Watchlist", "Recovery / Crashed Stocks", "All Ranked Scan"])

    with tabs[0]:
        render_ai_idea_cards(top_df, "Highest Ranked AI Setups", limit=5)
        render_main_table(top_df, title="Top AI Ranked Table")

    with tabs[1]:
        render_watchlist(scan_df)
        if not watch_scan_df.empty:
            st.divider()
            render_ai_idea_cards(watch_scan_df, "Watchlist AI Reasoning", limit=5)

    with tabs[2]:
        st.caption("These are stocks that may have crashed or pulled back but are showing early signs of stabilization or reversal.")
        render_ai_idea_cards(recovery_df, "Recovery / Reversal Candidates", limit=5)
        render_main_table(recovery_df, title="Recovery Ranked Table")

    with tabs[3]:
        render_main_table(scan_df, title="All Ranked Overnight Stock Ideas")


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

        c5, c6, c7 = st.columns(3)
        c5.metric("Top AI Ideas", state.get("top_ai_ideas_count", "N/A"))
        c6.metric("Watchlist Matches", state.get("watchlist_count", "N/A"))
        c7.metric("Recovery Setups", state.get("recovery_count", "N/A"))

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
    state = read_json_safe(SCAN_STATE_FILE, {})
    c3.metric("Last Scan", state.get("finished_at") or state.get("generated_at", "N/A"))

    render_scan_status()
    render_clean_ai_command_center(scan_df)

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
