import os
from pathlib import Path
import json
import smtplib
import time
from email.mime.text import MIMEText
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ============================================================
# ALPACA — optional, graceful fallback to yfinance if not configured
# pip install alpaca-py
# ============================================================
try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False

# ============================================================
# AI TRADING DASHBOARD
# V32.4 — CLEAN DIVERSIFICATION ENGINE
# ============================================================

st.set_page_config(
    page_title="AI Trading Dashboard V32.4.4.1",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# UI THEME
# ============================================================

st.markdown("""
<style>
:root {
    --bg-main: #f3f6fb; --bg-card: #ffffff;
    --text-main: #111827; --text-muted: #475569;
    --border-soft: #d8e0ec; --blue-main: #2563eb;
}
.stApp { background: #f3f6fb !important; color: #111827 !important; }
html, body, p, div, span, label { color: #111827; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1500px; }
section[data-testid="stSidebar"] { background: #0f172a !important; border-right: 1px solid rgba(255,255,255,0.08); }
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div { color: #f8fafc !important; }
section[data-testid="stSidebar"] input { color: #111827 !important; background: #ffffff !important; }
section[data-testid="stSidebar"] .stButton button {
    background: #1e293b !important; border: 1px solid #334155 !important;
    color: #ffffff !important; border-radius: 12px !important;
}
h1, h2, h3 { color: #111827 !important; letter-spacing: -0.03em; }
h1 { font-size: 2.25rem !important; font-weight: 850 !important; }
h2 { font-size: 1.55rem !important; font-weight: 800 !important; }
.modern-hero {
    padding: 26px; border-radius: 24px;
    background: linear-gradient(135deg, #0f172a 0%, #1e40af 58%, #0f766e 100%);
    color: #ffffff !important; box-shadow: 0 18px 42px rgba(15,23,42,0.22);
    margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.12);
}
.modern-hero h1, .modern-hero p, .modern-hero span, .modern-hero div { color: #ffffff !important; }
.modern-hero p { color: #e0f2fe !important; font-size: 1.03rem; margin-bottom: 0; }
.modern-card {
    padding: 18px 20px; border-radius: 20px; background: #ffffff !important;
    color: #111827 !important; border: 1px solid #d8e0ec;
    box-shadow: 0 8px 22px rgba(15,23,42,0.08); margin-bottom: 16px;
}
.modern-card * { color: #111827 !important; }
.modern-section-title { padding: 14px 0 8px 0; font-size: 1.25rem; font-weight: 850; color: #111827 !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #475569 !important; }
[data-testid="stMetric"] {
    background: #ffffff !important; border: 1px solid #d8e0ec;
    border-radius: 18px; padding: 15px 16px; box-shadow: 0 8px 20px rgba(15,23,42,0.07);
}
[data-testid="stMetric"] * { color: #111827 !important; }
[data-testid="stMetricLabel"] { color: #475569 !important; }
[data-testid="stMetricValue"] { color: #111827 !important; font-weight: 850 !important; }
.stButton button, .stDownloadButton button, .stLinkButton a {
    border-radius: 13px !important; border: 1px solid #bfdbfe !important;
    background: #ffffff !important; color: #1d4ed8 !important;
    box-shadow: 0 5px 14px rgba(15,23,42,0.08); font-weight: 750 !important;
}
.stButton button:hover, .stDownloadButton button:hover, .stLinkButton a:hover {
    background: #eff6ff !important; color: #1e40af !important; border-color: #93c5fd !important;
}
.stTextInput input, .stNumberInput input, textarea {
    border-radius: 12px !important; background: #ffffff !important;
    color: #111827 !important; border: 1px solid #cbd5e1 !important;
}
.stAlert { border-radius: 16px !important; color: #111827 !important; }
.stAlert * { color: #111827 !important; }
.streamlit-expanderHeader { border-radius: 14px !important; font-weight: 750 !important; color: #111827 !important; background: #ffffff !important; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: 18px; overflow: hidden;
    box-shadow: 0 10px 24px rgba(15,23,42,0.08);
    border: 1px solid #d8e0ec; background: #ffffff !important;
}
[data-testid="stDataFrame"] div, [data-testid="stDataEditor"] div,
[data-testid="stDataFrame"] span, [data-testid="stDataEditor"] span,
[data-testid="stDataFrame"] p, [data-testid="stDataEditor"] p { color: #111827 !important; }
[data-testid="stDataEditor"] [role="columnheader"],
[data-testid="stDataFrame"] [role="columnheader"] {
    background: #e8eef8 !important; color: #111827 !important; font-weight: 800 !important;
}
a { color: #1d4ed8 !important; font-weight: 650; }
@media (max-width: 768px) {
    .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
    .modern-hero { padding: 18px; border-radius: 18px; }
    h1 { font-size: 1.75rem !important; }
    h2 { font-size: 1.25rem !important; }
    [data-testid="stMetric"] { padding: 12px; }
}
</style>
""", unsafe_allow_html=True)


def modern_hero(title, subtitle):
    st.markdown(f'<div class="modern-hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)

def modern_section(title, subtitle=None):
    st.markdown(f'<div class="modern-section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def conviction_bar_html(score):
    try:
        score = float(score or 0)
    except Exception:
        score = 0

    pct = max(0, min(100, int(score)))
    if pct >= 75:
        color = "#16a34a"
    elif pct >= 60:
        color = "#f59e0b"
    else:
        color = "#ef4444"

    return f"""
    <div style="background:#e5e7eb;border-radius:999px;height:9px;width:100%;overflow:hidden;">
        <div style="background:{color};width:{pct}%;height:9px;border-radius:999px;"></div>
    </div>
    <div style="font-size:0.78rem;color:#475569;margin-top:3px;">{pct}/100 conviction</div>
    """


def render_signal_card(row, card_key=None):
    ticker = row.get("Ticker", "N/A")
    price = row.get("Price", "N/A")
    verdict = row.get("Agent Verdict", row.get("Signal", ""))
    signal = row.get("Signal", "")
    conviction = row.get("Final Conviction", row.get("AI Score", 0))
    entry = row.get("Entry Range", "N/A")
    stop = row.get("Stop Loss", "N/A")
    target = row.get("Target / Sell Zone", "N/A")
    rr = row.get("Risk / Reward", "N/A")
    rs = row.get("Relative Strength vs SPY %", "N/A")
    earnings = row.get("Earnings", "")
    plan = str(row.get("AI Trade Plan", ""))
    plan_short = plan[:260] + ("..." if len(plan) > 260 else "")

    if "High" in str(verdict) or "BUY" in str(signal):
        border_color = "#16a34a"
        pill_bg = "#dcfce7"
        pill_color = "#166534"
    elif "Watch" in str(verdict) or "Watch" in str(signal):
        border_color = "#f59e0b"
        pill_bg = "#fef3c7"
        pill_color = "#92400e"
    else:
        border_color = "#64748b"
        pill_bg = "#f1f5f9"
        pill_color = "#334155"

    st.markdown(
        f"""
        <div style="
            background:#ffffff;
            border:1px solid #d8e0ec;
            border-left:6px solid {border_color};
            border-radius:18px;
            padding:18px 18px;
            margin-bottom:14px;
            box-shadow:0 8px 22px rgba(15,23,42,0.08);
        ">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
                <div>
                    <div style="font-size:1.35rem;font-weight:850;color:#111827;">{ticker}
                        <span style="font-size:1rem;color:#475569;margin-left:8px;">${price}</span>
                    </div>
                    <div style="margin-top:4px;color:#64748b;font-size:0.9rem;">{signal}</div>
                </div>
                <div style="background:{pill_bg};color:{pill_color};padding:6px 12px;border-radius:999px;font-weight:800;font-size:0.85rem;white-space:nowrap;">
                    {verdict}
                </div>
            </div>

            <div style="margin-top:12px;">
                {conviction_bar_html(conviction)}
            </div>

            <div style="
                display:grid;
                grid-template-columns:repeat(4,minmax(0,1fr));
                gap:10px;
                margin-top:14px;
            ">
                <div><div style="font-size:0.75rem;color:#64748b;">Entry</div><div style="font-weight:800;color:#111827;">{entry}</div></div>
                <div><div style="font-size:0.75rem;color:#64748b;">Stop</div><div style="font-weight:800;color:#111827;">${stop}</div></div>
                <div><div style="font-size:0.75rem;color:#64748b;">Target</div><div style="font-weight:800;color:#111827;">{target}</div></div>
                <div><div style="font-size:0.75rem;color:#64748b;">R/R</div><div style="font-weight:800;color:#111827;">{rr}</div></div>
            </div>

            <div style="margin-top:12px;color:#475569;font-size:0.88rem;">
                <b>RS vs SPY:</b> {rs}% &nbsp; | &nbsp; <b>Earnings:</b> {earnings}
            </div>

            <div style="margin-top:10px;color:#334155;font-size:0.9rem;line-height:1.45;">
                {plan_short}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    c1, c2 = st.columns([1, 4])
    with c1:
        st.link_button("Open chart", f"https://finance.yahoo.com/quote/{ticker}", use_container_width=True)
    with c2:
        st.caption("Use Detail View for full chart, agent breakdown, and position sizing.")


def render_signal_cards(df, limit=12):
    if df is None or df.empty:
        st.info("No signals to show.")
        return

    for i, (_, row) in enumerate(df.head(limit).iterrows()):
        render_signal_card(row, card_key=f"signal_card_{i}")


def render_mobile_signal_summary(df):
    if df is None or df.empty:
        st.info("No mobile summary available.")
        return

    cols = ["Ticker", "Price", "Entry Range", "Stop Loss", "Target / Sell Zone", "Risk / Reward"]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(df[cols].head(15), use_container_width=True, hide_index=True)


# ============================================================
# CONSTANTS
# ============================================================

EASTERN = ZoneInfo("America/New_York")

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

WATCHLIST_FILE    = DATA_DIR / "watchlist.json"
PAPER_TRADES_FILE = DATA_DIR / "paper_trades.json"
ALERT_HISTORY_FILE= DATA_DIR / "alert_history.json"
SIGNAL_LOG_FILE   = DATA_DIR / "signal_log.json"

DEFAULT_WATCHLIST = [
    "AAPL","MSFT","NVDA","AMD","TSLA","AMZN","GOOGL","META",
    "SNOW","ELF","PLTR","SHOP"
]
CORE_SCAN_TICKERS = [
    # Premium / mega-cap quality
    "AAPL","MSFT","NVDA","AMD","TSLA","AMZN","GOOGL","META",
    "AVGO","COST","LLY","UNH","CRM","ADBE","NOW","PANW","CRWD",

    # $75-$150 quality growth / recovery
    "SHOP","SNOW","NET","DDOG","TEAM","MDB","ZS","CELH","DECK",
    "NKE","SBUX","TGT","UBER","ABNB","TTD",

    # $30-$75 growth / recovery / swing names
    "PYPL","SQ","PLTR","HIMS","ONON","CHWY","TOST",
    "U","PATH","GTLB","AFRM","CAVA","WOLF","ENPH","SEDG",

    # $10-$30 affordable but more liquid / investable growth
    "SOFI","IONQ","RKLB","JOBY","ACHR","F","GM","RIVN",
    "NIO","BROS","NU","RIOT","MARA",

    # Under $10 limited, higher-risk but still monitored
    "SOUN","BBAI","AI"
]
RECOVERY_TICKERS = [
    # Affordable recovery / rebound candidates
    "SOFI","PLTR","HIMS","CHWY","TOST","U","PATH",
    "IONQ","RKLB","JOBY","ACHR","RIVN","F","GM",

    # Mid-price recovery names
    "PYPL","NKE","SBUX","TGT","SHOP","SNOW","NET","CELH","ENPH","SEDG",
    "SQ","BROS","ONON","AFRM","CAVA",

    # Premium quality recovery names
    "ADBE","AMD","TSLA","CRM","PANW","CRWD","DECK"
]
ETF_TICKERS = ["SPY","QQQ","IWM","DIA","XLK","XLF","XLV","XLE","XLY","XLP","SMH","ARKK"]


# ============================================================
# LOGIN
# ============================================================

def clean_secret(value):
    return str(value or "").strip()


# V32.4 SAFE LOGIN
# Built-in fallback credentials so Render env issues do not block access.
# Render environment variables can still override these later if needed.
ADMIN_USER     = clean_secret(os.getenv("ADMIN_USER", ""))
ADMIN_PASSWORD = clean_secret(os.getenv("ADMIN_PASSWORD", ""))
VIEW_USER      = clean_secret(os.getenv("VIEW_USER", ""))
VIEW_PASSWORD  = clean_secret(os.getenv("VIEW_PASSWORD", ""))


def require_login():
    for key, default in [("logged_in", False), ("user_role", None), ("login_user", "")]:
        if key not in st.session_state:
            st.session_state[key] = default

    if st.session_state.logged_in:
        return

    st.title("🔐 AI Trading Dashboard Login — V32.4 SECURE LOGIN")
    st.caption("Admin can edit watchlists, paper trades, and send email alerts. Viewer has read-only access.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        entered_user = clean_secret(username).lower()
        entered_password = clean_secret(password)

        if ADMIN_USER and ADMIN_PASSWORD and entered_user == ADMIN_USER.lower() and entered_password == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.user_role = "admin"
            st.session_state.login_user = ADMIN_USER
            st.rerun()
        elif VIEW_USER and VIEW_PASSWORD and entered_user == VIEW_USER.lower() and entered_password == VIEW_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.user_role = "viewer"
            st.session_state.login_user = VIEW_USER
            st.rerun()
        else:
            st.error("Invalid username or password.")
    with st.expander("🔧 Login Diagnostics"):
        st.write("This only confirms whether Render can read the variables. Password values are not shown.")
        st.write(f"ADMIN_USER set: {'✅ Yes' if ADMIN_USER else '❌ No'}")
        st.write(f"ADMIN_PASSWORD set: {'✅ Yes' if ADMIN_PASSWORD else '❌ No'}")
        st.write(f"VIEW_USER set: {'✅ Yes' if VIEW_USER else '❌ No'}")
        st.write(f"VIEW_PASSWORD set: {'✅ Yes' if VIEW_PASSWORD else '❌ No'}")
        st.caption("Required Render variables: ADMIN_USER, ADMIN_PASSWORD, VIEW_USER, VIEW_PASSWORD")

    st.stop()


def is_admin():
    return st.session_state.get("user_role") == "admin"


require_login()


# ============================================================
# STORAGE HELPERS
# ============================================================

def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace("$", "")


def load_json_file(path, default):
    try:
        path = Path(path)
        if path.exists():
            with path.open("r") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json_file(path, data):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        st.error(f"Could not save {path}: {e}")
        return False


def load_watchlist():
    saved = load_json_file(WATCHLIST_FILE, DEFAULT_WATCHLIST)
    clean = []
    for ticker in saved:
        t = normalize_ticker(str(ticker))
        if t and t not in clean:
            clean.append(t)
    return clean or DEFAULT_WATCHLIST

def save_watchlist():
    return save_json_file(WATCHLIST_FILE, st.session_state.watchlist)

def load_paper_trades():
    return load_json_file(PAPER_TRADES_FILE, [])

def save_paper_trades():
    return save_json_file(PAPER_TRADES_FILE, st.session_state.paper_trades)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if "paper_trades" not in st.session_state:
    st.session_state.paper_trades = load_paper_trades()


# ============================================================
# ALPACA DATA LAYER
# ============================================================

ALPACA_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "")

alpaca_client = None
if ALPACA_AVAILABLE and ALPACA_KEY and ALPACA_SECRET:
    try:
        alpaca_client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
    except Exception:
        alpaca_client = None

ALPACA_STATUS = "🟢 Alpaca Connected" if alpaca_client else "🟡 Yahoo Finance (Alpaca not configured)"


def _alpaca_bars_to_df(bars, ticker):
    """Convert Alpaca bars response to a yfinance-compatible DataFrame."""
    try:
        df = bars.df
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(ticker, level="symbol")
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
            "vwap": "VWAP", "trade_count": "Trade Count",
        })
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        return df.dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def get_history(ticker, period="1y", interval="1d"):
    """Primary data function. Tries Alpaca first, falls back to yfinance."""
    ticker = normalize_ticker(ticker)

    if alpaca_client and ALPACA_AVAILABLE:
        try:
            period_days = {
                "1y": 365, "6mo": 182, "3mo": 91,
                "1mo": 31, "5d": 7, "1d": 2,
            }.get(period, 365)

            if interval == "1d":
                tf = TimeFrame.Day
            elif interval == "1h":
                tf = TimeFrame.Hour
            elif interval == "15m":
                tf = TimeFrame(15, TimeFrameUnit.Minute)
            elif interval == "5m":
                tf = TimeFrame(5, TimeFrameUnit.Minute)
            else:
                tf = TimeFrame.Day

            start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=period_days + 5)
            req = StockBarsRequest(symbol_or_symbols=ticker, timeframe=tf, start=start)
            bars = alpaca_client.get_stock_bars(req)
            df = _alpaca_bars_to_df(bars, ticker)
            if not df.empty and len(df) >= 10:
                return df
        except Exception:
            pass

    # yfinance fallback
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        if df is not None and not df.empty:
            return df.dropna()
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=30)
def get_live_quote(ticker):
    """
    Returns latest bid/ask/mid from Alpaca during market hours.
    Falls back to last daily close from yfinance.
    """
    ticker = normalize_ticker(ticker)
    if alpaca_client and ALPACA_AVAILABLE:
        try:
            req = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            result = alpaca_client.get_stock_latest_quote(req)
            q = result[ticker]
            bid = float(q.bid_price or 0)
            ask = float(q.ask_price or 0)
            if bid > 0 and ask > 0:
                mid = (bid + ask) / 2
                return {
                    "price": round(mid, 2),
                    "bid": round(bid, 2),
                    "ask": round(ask, 2),
                    "spread": round(ask - bid, 3),
                    "source": "🟢 Alpaca Live",
                }
        except Exception:
            pass

    hist = get_history(ticker, period="5d")
    if not hist.empty:
        return {
            "price": round(float(hist["Close"].iloc[-1]), 2),
            "bid": None, "ask": None, "spread": None,
            "source": "🟡 Yahoo (delayed close)",
        }
    return None


@st.cache_data(ttl=3600)
def get_info(ticker):
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def get_earnings_flag(ticker):
    """Returns (label, days_away) for upcoming earnings."""
    try:
        info = get_info(ticker)
        ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        if ts:
            earnings_dt = pd.Timestamp(ts, unit="s")
            days = (earnings_dt - pd.Timestamp.now()).days
            if 0 <= days <= 7:
                return f"🔴 Earnings in {days}d — binary risk, reduce size", days
            elif 0 <= days <= 14:
                return f"🟡 Earnings in {days}d — elevated event risk", days
            elif days < 0:
                return "🟢 Earnings recently passed", days
            else:
                return f"🟢 Earnings in {days}d", days
    except Exception:
        pass
    return "⚪ Earnings date unknown", None


# ============================================================
# SIGNAL LOG + ACCURACY ENGINE
# ============================================================

def load_signal_log():
    return load_json_file(SIGNAL_LOG_FILE, [])

def save_signal_log(log):
    return save_json_file(SIGNAL_LOG_FILE, log)


def auto_log_signals(df):
    """
    Automatically logs BUY NOW and High Conviction signals once per ticker per day.
    Called when the BUY NOW page loads.
    """
    if df is None or df.empty:
        return

    log = load_signal_log()
    existing_ids = {entry["id"] for entry in log}
    today = datetime.now(EASTERN).strftime("%Y%m%d")
    added = 0

    signals_to_log = df[
        (df.get("Signal", pd.Series(dtype=str)) == "🟢 BUY NOW") |
        (df.get("Final Conviction", pd.Series(dtype=float)).fillna(0) >= 68)
    ] if "Signal" in df.columns else pd.DataFrame()

    for _, row in signals_to_log.iterrows():
        ticker = row.get("Ticker", "")
        if not ticker:
            continue
        signal_id = f"{ticker}_{today}"
        if signal_id in existing_ids:
            continue

        # Parse target low from "Target / Sell Zone" string
        target_low = None
        try:
            tz_str = str(row.get("Target / Sell Zone", ""))
            target_low = float(tz_str.replace("$", "").split(" - ")[0])
        except Exception:
            pass

        log.append({
            "id": signal_id,
            "ticker": ticker,
            "date": datetime.now(EASTERN).strftime("%Y-%m-%d"),
            "timestamp": datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M %p ET"),
            "signal": str(row.get("Signal", "")),
            "conviction": row.get("Final Conviction", None),
            "agent_verdict": str(row.get("Agent Verdict", "")),
            "entry_price": row.get("Price", None),
            "stop_loss": row.get("Stop Loss", None),
            "target": target_low,
            "risk_reward": str(row.get("Risk / Reward", "")),
            "outcome_1d": None,
            "outcome_5d": None,
            "outcome_10d": None,
            "pct_1d": None,
            "pct_5d": None,
            "pct_10d": None,
        })
        existing_ids.add(signal_id)
        added += 1

    if added > 0:
        save_signal_log(log[-500:])
    return added


def check_signal_outcomes():
    """
    For each logged signal, fetch historical prices and mark outcomes at 1d, 5d, 10d.
    Returns updated log.
    """
    log = load_signal_log()
    updated = False

    for entry in log:
        signal_date = entry.get("date")
        entry_price = entry.get("entry_price")
        ticker = entry.get("ticker")

        if not all([signal_date, entry_price, ticker]):
            continue
        if entry.get("outcome_10d") is not None:
            continue  # fully resolved

        try:
            hist = get_history(ticker, period="3mo")
            if hist.empty:
                continue

            signal_dt = pd.Timestamp(signal_date)
            # Normalize index to date only for comparison
            hist_idx = hist.index.normalize() if hasattr(hist.index, "normalize") else hist.index
            hist_after = hist[hist_idx > signal_dt]

            for days, key_pct, key_out in [
                (1, "pct_1d", "outcome_1d"),
                (5, "pct_5d", "outcome_5d"),
                (10, "pct_10d", "outcome_10d"),
            ]:
                if entry.get(key_out) is None and len(hist_after) >= days:
                    future_price = float(hist_after["Close"].iloc[days - 1])
                    pct = ((future_price - entry_price) / entry_price) * 100
                    entry[key_pct] = round(pct, 2)
                    entry[key_out] = "✅ Win" if pct > 0 else "❌ Loss"
                    updated = True
        except Exception:
            continue

    if updated:
        save_signal_log(log)

    return log


def get_weak_signal_patterns(log):
    weak = []
    if not log:
        return weak

    low_conviction = [
        e for e in log
        if e.get("conviction") is not None
        and float(e.get("conviction") or 0) < 70
        and e.get("outcome_5d")
    ]

    if len(low_conviction) >= 5:
        wins = sum(1 for e in low_conviction if "Win" in str(e.get("outcome_5d")))
        win_rate = wins / len(low_conviction)
        if win_rate < 0.45:
            weak.append(f"Low conviction signals under 70 have only {win_rate*100:.0f}% 5D win rate. Consider raising BUY NOW threshold.")

    high_conviction = [
        e for e in log
        if e.get("conviction") is not None
        and float(e.get("conviction") or 0) >= 75
        and e.get("outcome_5d")
    ]

    if len(high_conviction) >= 5:
        wins = sum(1 for e in high_conviction if "Win" in str(e.get("outcome_5d")))
        win_rate = wins / len(high_conviction)
        if win_rate >= 0.60:
            weak.append(f"High conviction signals 75+ are performing well with {win_rate*100:.0f}% 5D win rate.")

    return weak


def get_accuracy_stats(log):
    """Compute win rate and average return at 1D, 5D, 10D."""
    stats = {}
    for period, key_out, key_pct in [
        ("1D", "outcome_1d", "pct_1d"),
        ("5D", "outcome_5d", "pct_5d"),
        ("10D", "outcome_10d", "pct_10d"),
    ]:
        outcomes = [e[key_out] for e in log if e.get(key_out)]
        pcts = [e[key_pct] for e in log if e.get(key_pct) is not None]
        if outcomes:
            wins = sum(1 for o in outcomes if "Win" in o)
            stats[period] = {
                "win_rate": round(wins / len(outcomes) * 100, 1),
                "total": len(outcomes),
                "wins": wins,
                "avg_return": round(sum(pcts) / len(pcts), 2) if pcts else 0,
            }
    return stats


# ============================================================
# POSITION SIZE CALCULATOR
# ============================================================

def calc_position_size(account_size, risk_pct, entry_price, stop_price):
    """Returns position sizing details given account and risk parameters."""
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return None
    risk_dollars = account_size * (risk_pct / 100)
    risk_per_share = entry_price - stop_price
    shares = int(risk_dollars / risk_per_share)
    if shares <= 0:
        return None
    position_value = shares * entry_price
    return {
        "Shares": shares,
        "Position $": round(position_value, 2),
        "Risk $": round(risk_dollars, 2),
        "Risk per Share": round(risk_per_share, 2),
        "% of Account": round(position_value / account_size * 100, 1),
    }


def render_position_calculator(entry_price=None, stop_price=None):
    """Inline position size calculator widget."""
    modern_section("📐 Position Size Calculator")
    st.caption("Based on fixed-dollar risk per trade. 1-2% of account per trade is standard.")

    c1, c2, c3, c4 = st.columns(4)
    account = c1.number_input("Account Size ($)", min_value=1000, value=25000, step=1000, key="ps_account")
    risk_pct = c2.number_input("Risk per Trade (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="ps_risk")
    entry = c3.number_input("Entry Price ($)", min_value=0.01, value=float(entry_price) if entry_price else 100.0, step=0.01, key="ps_entry")
    stop = c4.number_input("Stop Loss ($)", min_value=0.01, value=float(stop_price) if stop_price else 90.0, step=0.01, key="ps_stop")

    result = calc_position_size(account, risk_pct, entry, stop)
    if result:
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Shares to Buy", result["Shares"])
        m2.metric("Position Value", f"${result['Position $']:,.2f}")
        m3.metric("Max Risk $", f"${result['Risk $']:,.2f}")
        m4.metric("Risk/Share", f"${result['Risk per Share']:.2f}")
        m5.metric("% of Account", f"{result['% of Account']}%")

        if result["% of Account"] > 20:
            st.warning("Position is over 20% of account — consider reducing size or widening the stop.")
    else:
        st.info("Enter a valid entry price higher than stop price to calculate position size.")


# ============================================================
# OPPORTUNITY DIVERSIFICATION ENGINE
# ============================================================

EXCLUDED_SECTOR_KEYWORDS = [
    "financial", "bank", "banks", "insurance", "capital markets",
    "asset management", "mortgage", "reit", "real estate",
    "entertainment", "media", "broadcast", "streaming", "gaming",
    "casino", "resort"
]

EXCLUDED_TICKERS = {
    "JPM","BAC","WFC","C","GS","MS","SCHW","COF","AXP","USB","PNC",
    "TFC","BK","BLK","BX","KKR","AIG","MET","PRU","ALL","TRV",
    "DIS","NFLX","WBD","PARA","CMCSA","ROKU","LYV","DKNG","PENN","MGM","WYNN","LVS",
    # Highly speculative / value-trap prone names removed from default scans
    "SPCE","GOEV","QS","FCEL","PLUG","BLNK","WKHS","MVST","LCID","OPEN","LAZR","CHPT","DNA"
}


def get_price_bucket(price):
    try:
        price = float(price)
    except Exception:
        return "Unknown"
    if price < 10:
        return "Under $10"
    if price < 30:
        return "$10-$30"
    if price < 75:
        return "$30-$75"
    if price < 150:
        return "$75-$150"
    return "$150+"


def is_excluded_company(ticker, info=None):
    ticker = normalize_ticker(str(ticker))
    if ticker in EXCLUDED_TICKERS:
        return True

    info = info or get_info(ticker)
    combined = " ".join([
        str(info.get("sector", "")),
        str(info.get("industry", "")),
        str(info.get("longName", "")),
    ]).lower()

    return any(keyword in combined for keyword in EXCLUDED_SECTOR_KEYWORDS)


def filter_excluded_companies(tickers):
    clean = []
    for ticker in tickers:
        t = normalize_ticker(str(ticker))
        if not t:
            continue
        try:
            if not is_excluded_company(t):
                clean.append(t)
        except Exception:
            clean.append(t)
    return clean


def diversify_by_price_bucket(df, per_bucket=6, min_conviction=55):
    if df is None or df.empty or "Price" not in df.columns:
        return df

    work = df.copy()
    work["Price Bucket"] = work["Price"].apply(get_price_bucket)

    if "Final Conviction" in work.columns:
        sort_col = "Final Conviction"
    elif "AI Score" in work.columns:
        sort_col = "AI Score"
    elif "Recovery Score" in work.columns:
        sort_col = "Recovery Score"
    else:
        sort_col = None

    pieces = []
    for bucket in ["Under $10", "$10-$30", "$30-$75", "$75-$150", "$150+"]:
        sub = work[work["Price Bucket"] == bucket]
        if sort_col:
            sub = sub[sub[sort_col].fillna(0) >= min_conviction]
            sub = sub.sort_values(sort_col, ascending=False)
        pieces.append(sub.head(per_bucket))

    out = pd.concat(pieces, ignore_index=True) if pieces else work
    if not out.empty and sort_col:
        out = out.sort_values([sort_col, "Price"], ascending=[False, True])
    return out


# ============================================================
# INDICATORS
# ============================================================


def calc_atr(hist, period=14):
    """
    Average True Range. Used for volatility-adjusted stops.
    """
    try:
        high = hist["High"]
        low = hist["Low"]
        close = hist["Close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not pd.isna(atr) else None
    except Exception:
        return None


def get_relative_strength_from_hist(ticker_hist, spy_hist, lookback=63):
    """
    Relative strength vs SPY over roughly 3 months.
    Positive means the stock outperformed SPY.
    """
    try:
        if ticker_hist is None or spy_hist is None or ticker_hist.empty or spy_hist.empty:
            return None
        if len(ticker_hist) < lookback + 1 or len(spy_hist) < lookback + 1:
            return None

        t_ret = (ticker_hist["Close"].iloc[-1] / ticker_hist["Close"].iloc[-lookback]) - 1
        s_ret = (spy_hist["Close"].iloc[-1] / spy_hist["Close"].iloc[-lookback]) - 1
        rs = (t_ret - s_ret) * 100
        return round(float(rs), 1)
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_market_regime():
    """
    Market regime gate using SPY vs 200-day moving average.
    """
    spy = get_history("SPY", period="1y")
    if spy.empty or len(spy) < 200:
        return "unknown", "⚪ Market Regime Unknown", "SPY data unavailable."

    close = spy["Close"]
    price = close.iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]

    if price > sma200 * 1.02:
        return "bull", "🟢 Bull Market", "Momentum signals are more reliable. Standard thresholds are allowed."
    elif price < sma200 * 0.98:
        return "bear", "🔴 Bear Market", "Momentum signals are less reliable. BUY NOW threshold is raised and position sizes should be reduced."
    else:
        return "neutral", "🟡 Neutral Market", "Market is near long-term trend. Use starter size and require stronger confirmation."


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def safe_round(value, digits=2):
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), digits)
    except Exception:
        return None


# ============================================================
# MULTI-AGENT ENGINE
# ============================================================

def technical_agent(price, sma20, sma50, sma200, rsi, volume_ratio, relative_strength=None):
    score, reasons = 0, []
    if price > sma20: score += 18; reasons.append("above 20-day trend")
    else: reasons.append("below 20-day trend")
    if price > sma50: score += 22; reasons.append("above 50-day trend")
    else: reasons.append("below 50-day trend")
    if price > sma200: score += 25; reasons.append("above 200-day trend")
    else: reasons.append("below 200-day trend")
    if 45 <= rsi <= 70: score += 20; reasons.append("RSI in healthy swing zone")
    elif 30 <= rsi < 45: score += 12; reasons.append("RSI beaten down but stabilizing")
    elif rsi < 30: score += 8; reasons.append("RSI oversold")
    else: score -= 10; reasons.append("RSI overbought")
    if volume_ratio >= 1.3: score += 15; reasons.append("volume confirms stronger interest")
    elif volume_ratio >= 0.9: score += 8; reasons.append("volume is normal")
    else: score -= 5; reasons.append("volume confirmation is weak")
    if relative_strength is not None:
        if relative_strength > 10:
            score += 15
            reasons.append(f"strong relative strength vs SPY (+{relative_strength:.1f}%)")
        elif relative_strength > 0:
            score += 8
            reasons.append(f"outperforming SPY (+{relative_strength:.1f}%)")
        elif relative_strength < -10:
            score -= 15
            reasons.append(f"lagging SPY badly ({relative_strength:.1f}%)")
        else:
            score -= 5
            reasons.append(f"slightly lagging SPY ({relative_strength:.1f}%)")

    return max(0, min(100, score)), "; ".join(reasons)


def risk_agent(price, stop_loss, target_low, risk_score, hist):
    try:
        close = hist["Close"]
        volatility = close.pct_change().dropna().tail(30).std() * 100
        drawdown = ((price - close.tail(90).max()) / close.tail(90).max()) * 100
    except Exception:
        volatility, drawdown = 3, -10

    rr = max(target_low - price, 0.01) / max(price - stop_loss, 0.01)
    score, reasons = 100, []

    if rr >= 2: reasons.append("risk/reward is attractive")
    elif rr >= 1.2: score -= 15; reasons.append("risk/reward is acceptable but not ideal")
    else: score -= 30; reasons.append("risk/reward is weak")

    if risk_score >= 55: score -= 25; reasons.append("dashboard risk score is elevated")
    elif risk_score < 35: reasons.append("dashboard risk score is controlled")

    if volatility > 4: score -= 15; reasons.append("short-term volatility is high")
    elif volatility < 2.5: reasons.append("volatility is manageable")

    if drawdown < -25: score -= 10; reasons.append("recent drawdown is deep")
    else: reasons.append("recent drawdown is not extreme")

    return max(0, min(100, score)), "; ".join(reasons)


def fundamental_agent(info):
    score, reasons = 50, []
    pe = info.get("forwardPE") or info.get("trailingPE")
    profit_margin = info.get("profitMargins")
    revenue_growth = info.get("revenueGrowth")
    debt_to_equity = info.get("debtToEquity")
    market_cap = info.get("marketCap")

    if market_cap and market_cap > 10_000_000_000: score += 10; reasons.append("large-cap quality/liquidity")
    elif market_cap: reasons.append("smaller/mid-cap profile")
    if pe and 0 < pe < 25: score += 15; reasons.append("valuation is reasonable")
    elif pe and 25 <= pe < 50: score += 5; reasons.append("valuation is elevated but not extreme")
    elif pe and pe >= 50: score -= 10; reasons.append("valuation is expensive")
    if profit_margin and profit_margin > 0.15: score += 15; reasons.append("strong profit margins")
    elif profit_margin and profit_margin > 0: score += 5; reasons.append("positive margins")
    elif profit_margin is not None: score -= 10; reasons.append("weak or negative margins")
    if revenue_growth and revenue_growth > 0.10: score += 15; reasons.append("healthy revenue growth")
    elif revenue_growth and revenue_growth > 0: score += 5; reasons.append("modest revenue growth")
    elif revenue_growth is not None: score -= 10; reasons.append("revenue growth is negative")
    if debt_to_equity and debt_to_equity > 200: score -= 10; reasons.append("debt load appears elevated")
    elif debt_to_equity is not None: score += 5; reasons.append("debt level appears manageable")
    if not reasons: reasons.append("limited fundamental data available")
    return max(0, min(100, score)), "; ".join(reasons)


def recovery_agent(price, high_52, low_52, rsi, delta_to_high_pct):
    score, reasons = 0, []
    from_low_pct = ((price - low_52) / low_52 * 100) if low_52 else 0
    if delta_to_high_pct and delta_to_high_pct >= 40: score += 30; reasons.append("large upside gap to 52-week high")
    elif delta_to_high_pct and delta_to_high_pct >= 20: score += 20; reasons.append("moderate upside gap to 52-week high")
    else: score += 8; reasons.append("limited recovery gap to 52-week high")
    if from_low_pct <= 15: score += 25; reasons.append("near 52-week low")
    elif from_low_pct <= 30: score += 15; reasons.append("still close to lower yearly range")
    if rsi < 35: score += 25; reasons.append("oversold rebound setup")
    elif rsi < 50: score += 15; reasons.append("beaten-down but stabilizing")
    if price > low_52 * 1.05: score += 10; reasons.append("price has bounced off lows")
    return max(0, min(100, score)), "; ".join(reasons)


@st.cache_data(ttl=300)
def macro_agent():
    spy = get_history("SPY", period="6mo")
    qqq = get_history("QQQ", period="6mo")
    score, reasons = 50, []
    for symbol, hist in [("SPY", spy), ("QQQ", qqq)]:
        try:
            close = hist["Close"]
            price = close.iloc[-1]
            sma20 = close.rolling(20).mean().iloc[-1]
            sma50 = close.rolling(50).mean().iloc[-1]
            if price > sma20 and price > sma50: score += 20; reasons.append(f"{symbol} trend is supportive")
            elif price > sma50: score += 8; reasons.append(f"{symbol} above 50-day but short-term mixed")
            elif price < sma50: score -= 15; reasons.append(f"{symbol} below 50-day trend")
            else: reasons.append(f"{symbol} trend is mixed")
        except Exception:
            reasons.append(f"{symbol} data unavailable")
    return max(0, min(100, score)), "; ".join(reasons)


def synthesis_agent(tech, risk, fund, rec, macro):
    final = tech*0.30 + risk*0.25 + fund*0.20 + rec*0.15 + macro*0.10
    if final >= 80: verdict = "🟢 High Conviction"
    elif final >= 68: verdict = "🟢 Strong Candidate"
    elif final >= 55: verdict = "🟡 Watch / Starter Size"
    elif final >= 45: verdict = "⚪ Mixed Setup"
    else: verdict = "🔴 Avoid / Wait"
    return round(final, 0), verdict


# ============================================================
# TRADE PLAN
# ============================================================

def build_ai_trade_plan(ticker, price, sma20, sma50, sma200, rsi, ai_score, risk_score, high_52, low_52, upside_to_high, volume_ratio, atr=None, relative_strength=None, market_regime='neutral'):
    delta_to_high_dollars = high_52 - price if high_52 and price else None
    delta_to_high_pct = ((high_52 - price) / price * 100) if high_52 and price else None
    above_20 = price > sma20
    above_50 = price > sma50
    above_200 = price > sma200
    far_from_high = delta_to_high_pct and delta_to_high_pct >= 20

    if ai_score >= 75 and risk_score < 35 and above_20 and above_50:
        entry_range = f"${price*0.97:.2f} - ${price*1.01:.2f}"
        entry_reason = "trend confirmation is strong; near-current entry is reasonable."
    elif rsi < 35 and far_from_high:
        entry_range = f"${price*0.94:.2f} - ${price*0.99:.2f}"
        entry_reason = "oversold rebound — staged entries on weakness are safer."
    elif above_50:
        entry_range = f"${max(sma20*0.98, price*0.96):.2f} - ${price:.2f}"
        entry_reason = "holding medium trend — better entry near short-term support."
    else:
        entry_range = f"Wait for reclaim above ${sma50:.2f} or pullback near ${price*0.90:.2f} - ${price*0.95:.2f}"
        entry_reason = "trend not confirmed — patience is better than chasing."

    # ATR-based stop-loss. This adapts to each stock's actual volatility.
    if atr and atr > 0:
        atr_mult = 2.0
        if market_regime == "bear":
            atr_mult = 1.6  # tighter risk in weak markets
        elif rsi < 35:
            atr_mult = 2.2  # give oversold rebounds slightly more room

        atr_stop = price - (atr * atr_mult)
        technical_stop = sma50 * 0.98 if above_50 else price * 0.90
        stop_loss = max(atr_stop, price * 0.82)  # avoid extreme stops
        if above_50:
            stop_loss = min(stop_loss, technical_stop) if technical_stop < price else stop_loss
        stop_reason = f"ATR-based stop using about {atr_mult:.1f}x ATR; adapts to this stock's volatility."
    elif above_50 and risk_score < 40:
        stop_loss = min(sma50 * 0.98, price * 0.92)
        stop_reason = "fallback stop below the 50-day trend area."
    elif rsi < 35:
        stop_loss = price * 0.90
        stop_reason = "fallback oversold rebound stop."
    else:
        stop_loss = price * 0.88
        stop_reason = "fallback wider stop because confirmation is weaker."

    if delta_to_high_pct and delta_to_high_pct > 35:
        target_low = price * 1.12
        target_high = min(high_52, price * 1.30)
        sell_reason = "partial recovery target first."
    elif delta_to_high_pct and delta_to_high_pct > 15:
        target_low = price * 1.07
        target_high = min(high_52, price * 1.16)
        sell_reason = "moderate target — upside exists but not extreme."
    else:
        target_low = price * 1.04
        target_high = price * 1.08
        sell_reason = "tighter target — upside to prior high is limited."

    target_zone = f"${target_low:.2f} - ${target_high:.2f}"
    rr = max(target_low - price, 0.01) / max(price - stop_loss, 0.01)
    risk_reward = f"{rr:.2f}:1"

    if rr >= 2 and risk_score < 45: position_note = "Normal starter position may be reasonable."
    elif rr >= 1.2: position_note = "Smaller starter size — add only if confirmation improves."
    else: position_note = "Watch-only or very small size — R:R not attractive yet."

    if ai_score >= 80 and risk_score < 30 and above_50: hold_style = "Short swing / momentum hold"
    elif rsi < 40 and far_from_high: hold_style = "Recovery swing / staged long-term hold"
    elif above_200 and ai_score >= 60: hold_style = "Longer swing / possible long-term hold"
    elif risk_score >= 55: hold_style = "Watch only / avoid oversized position"
    else: hold_style = "Watchlist candidate"

    trend_parts = [
        "above 20-day" if above_20 else "below 20-day",
        "above 50-day" if above_50 else "below 50-day",
        "above 200-day" if above_200 else "below 200-day",
    ]

    if rsi < 30: rsi_d = f"RSI {rsi:.1f} — oversold."
    elif rsi <= 45: rsi_d = f"RSI {rsi:.1f} — beaten down but stabilizing."
    elif rsi <= 70: rsi_d = f"RSI {rsi:.1f} — healthy swing zone."
    else: rsi_d = f"RSI {rsi:.1f} — overbought, avoid chasing."

    rs_text = ""
    if relative_strength is not None:
        if relative_strength > 0:
            rs_text = f" Relative strength vs SPY is positive at +{relative_strength:.1f}%, which supports the setup."
        else:
            rs_text = f" Relative strength vs SPY is {relative_strength:.1f}%, so this stock is lagging the market."

    regime_text = ""
    if market_regime == "bear":
        regime_text = " Market regime is bearish, so require smaller size and stronger confirmation."
    elif market_regime == "bull":
        regime_text = " Market regime is bullish, so momentum signals have better backdrop."

    plan = (
        f"Price is {', '.join(trend_parts)}. {rsi_d} "
        f"52W high ${high_52:.2f} ({delta_to_high_pct:.1f}% away)."
        f"{rs_text}{regime_text} "
        f"Entry: {entry_range} — {entry_reason} "
        f"Stop: ${stop_loss:.2f} — {stop_reason} "
        f"Target: {target_zone} — {sell_reason} "
        f"R/R: {risk_reward}. {position_note}"
    )

    return {
        "52W High": round(high_52, 2) if high_52 else None,
        "Delta to 52W High $": round(delta_to_high_dollars, 2) if delta_to_high_dollars is not None else None,
        "Delta to 52W High %": round(delta_to_high_pct, 1) if delta_to_high_pct is not None else None,
        "AI Trade Plan": plan,
        "Entry Range": entry_range,
        "Stop Loss": round(stop_loss, 2),
        "Target / Sell Zone": target_zone,
        "Risk / Reward": risk_reward,
        "ATR": round(atr, 2) if atr else None,
        "Relative Strength vs SPY %": relative_strength,
        "Position Size Note": position_note,
        "Hold Style": hold_style,
    }


# ============================================================
# ANALYZE TICKER — uses live price when Alpaca is connected + market open
# ============================================================

def analyze_ticker(ticker):
    ticker = normalize_ticker(ticker)
    hist = get_history(ticker, period="1y")
    if hist.empty or len(hist) < 60:
        return None

    close = hist["Close"]

    # Use live price during market hours if Alpaca is available
    market_status, _ = get_market_status()
    live_quote = None
    if "Open" in market_status and alpaca_client:
        live_quote = get_live_quote(ticker)

    price = float(live_quote["price"]) if live_quote else float(close.iloc[-1])
    price_source = live_quote["source"] if live_quote else "Yahoo close"

    prev = float(close.iloc[-2]) if len(close) > 1 else price
    change_pct = ((price - prev) / prev) * 100 if prev else 0

    sma20  = close.rolling(20).mean().iloc[-1]
    sma50  = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.rolling(100).mean().iloc[-1]
    rsi    = calc_rsi(close).iloc[-1]

    high_52 = hist["High"].max()
    low_52  = hist["Low"].min()
    from_low  = ((price - low_52) / low_52) * 100 if low_52 else 0
    from_high = ((price - high_52) / high_52) * 100 if high_52 else 0
    upside_to_high = ((high_52 - price) / price) * 100 if price else 0

    vol = hist["Volume"].iloc[-1]
    avg_vol = hist["Volume"].rolling(20).mean().iloc[-1]
    volume_ratio = vol / avg_vol if avg_vol else 1

    atr = calc_atr(hist)
    spy_hist = get_history("SPY", period="1y")
    relative_strength = get_relative_strength_from_hist(hist, spy_hist)
    market_regime, market_regime_label, market_regime_note = get_market_regime()

    info = get_info(ticker)

    trend_score = 0
    if price > sma20: trend_score += 20
    if price > sma50: trend_score += 20
    if price > sma200: trend_score += 20
    if sma20 > sma50: trend_score += 15
    if 45 <= rsi <= 70: trend_score += 15
    if volume_ratio > 1.1: trend_score += 10

    risk_score = 0
    if rsi > 75: risk_score += 25
    if price < sma50: risk_score += 20
    if price < sma200: risk_score += 25
    if from_high < -25: risk_score += 15
    if volume_ratio < 0.6: risk_score += 10

    ai_score = max(0, min(100, trend_score - (risk_score * 0.65)))

    if ai_score >= 75 and risk_score < 35: signal = "🟢 BUY NOW"
    elif ai_score >= 60: signal = "🟡 Watch"
    elif ai_score >= 45: signal = "⚪ Neutral"
    else: signal = "🔴 Avoid"

    trade_plan = build_ai_trade_plan(
        ticker=ticker, price=price, sma20=sma20, sma50=sma50, sma200=sma200,
        rsi=rsi, ai_score=ai_score, risk_score=risk_score,
        high_52=high_52, low_52=low_52, upside_to_high=upside_to_high,
        volume_ratio=volume_ratio,
        atr=atr,
        relative_strength=relative_strength,
        market_regime=market_regime,
    )

    try:
        target_low = float(trade_plan["Target / Sell Zone"].replace("$", "").split(" - ")[0])
    except Exception:
        target_low = price * 1.08

    tech_score, tech_reason   = technical_agent(price, sma20, sma50, sma200, rsi, volume_ratio, relative_strength)
    risk_a_score, risk_reason = risk_agent(price, trade_plan["Stop Loss"], target_low, risk_score, hist)
    fund_score, fund_reason   = fundamental_agent(info)
    rec_score, rec_reason     = recovery_agent(price, high_52, low_52, rsi, trade_plan["Delta to 52W High %"])
    mac_score, mac_reason     = macro_agent()
    final_conviction, agent_verdict = synthesis_agent(tech_score, risk_a_score, fund_score, rec_score, mac_score)

    # Market regime gate: in bear markets, require stronger conviction and downgrade weaker buy signals.
    if market_regime == "bear" and final_conviction < 75:
        if signal == "🟢 BUY NOW":
            signal = "🟡 Watch (Bear Market)"
        if agent_verdict in ("🟢 High Conviction", "🟢 Strong Candidate"):
            agent_verdict = "🟡 Bear Market Caution"

    # Earnings suppression: downgrade High Conviction to Watch if earnings within 7 days
    earnings_label, days_to_earnings = get_earnings_flag(ticker)
    if days_to_earnings is not None and 0 <= days_to_earnings <= 7:
        if signal == "🟢 BUY NOW":
            signal = "🟡 Watch (⚠️ Earnings)"
        if agent_verdict in ("🟢 High Conviction", "🟢 Strong Candidate"):
            agent_verdict = "🟡 Earnings Risk"

    agent_summary = (
        f"Technical: {tech_reason}. Risk: {risk_reason}. "
        f"Fundamental: {fund_reason}. Recovery: {rec_reason}. Macro: {mac_reason}."
    )

    return {
        "Ticker": ticker,
        "Price": safe_round(price),
        "Price Bucket": get_price_bucket(price),
        "Price Source": price_source,
        "Daily %": safe_round(change_pct),
        "AI Score": safe_round(ai_score, 0),
        "Signal": signal,
        "Earnings": earnings_label,
        "Market Regime": market_regime_label,
        "Relative Strength vs SPY %": relative_strength,
        "ATR": safe_round(atr),
        "Risk Score": safe_round(risk_score, 0),
        "Technical Agent": safe_round(tech_score, 0),
        "Risk Agent": safe_round(risk_a_score, 0),
        "Fundamental Agent": safe_round(fund_score, 0),
        "Recovery Agent": safe_round(rec_score, 0),
        "Macro Agent": safe_round(mac_score, 0),
        "Final Conviction": safe_round(final_conviction, 0),
        "Agent Verdict": agent_verdict,
        "RSI": safe_round(rsi, 1),
        "52W High": trade_plan["52W High"],
        "Delta to 52W High $": trade_plan["Delta to 52W High $"],
        "Delta to 52W High %": trade_plan["Delta to 52W High %"],
        "From 52W Low %": safe_round(from_low, 1),
        "From 52W High %": safe_round(from_high, 1),
        "Volume Ratio": safe_round(volume_ratio, 2),
        "Entry Range": trade_plan["Entry Range"],
        "Stop Loss": trade_plan["Stop Loss"],
        "Target / Sell Zone": trade_plan["Target / Sell Zone"],
        "Risk / Reward": trade_plan["Risk / Reward"],
        "Hold Style": trade_plan["Hold Style"],
        "Position Size Note": trade_plan["Position Size Note"],
        "Agent Summary": agent_summary,
        "AI Trade Plan": trade_plan["AI Trade Plan"],
        "SMA20": safe_round(sma20),
        "SMA50": safe_round(sma50),
        "SMA200": safe_round(sma200),
    }


@st.cache_data(ttl=300)
def build_scan(tickers, diversified=True, per_bucket=6):
    unique = []
    for t in tickers:
        n = normalize_ticker(str(t))
        if n and n not in unique:
            unique.append(n)

    unique = filter_excluded_companies(unique)

    if not unique:
        return pd.DataFrame()

    try:
        with ThreadPoolExecutor(max_workers=min(8, len(unique))) as ex:
            results = list(ex.map(analyze_ticker, unique))
        rows = [r for r in results if r]
    except Exception:
        rows = [r for r in (analyze_ticker(t) for t in unique) if r]

    df = pd.DataFrame(rows)
    if not df.empty:
        if "Ticker" in df.columns:
            df = df[~df["Ticker"].apply(lambda t: is_excluded_company(t))]
        sort_col = "Final Conviction" if "Final Conviction" in df.columns else "AI Score"
        df = df.sort_values([sort_col, "Risk Score"], ascending=[False, True])
        if diversified:
            df = diversify_by_price_bucket(df, per_bucket=per_bucket, min_conviction=55)
    return df


@st.cache_data(ttl=3600)
def build_recovery_radar(tickers):
    rows = []
    for ticker in tickers:
        try:
            ticker = normalize_ticker(ticker)
            if is_excluded_company(ticker):
                continue
            hist = get_history(ticker, period="1y")
            if hist.empty or len(hist) < 60:
                continue
            info = get_info(ticker)
            price = float(hist["Close"].iloc[-1])
            low_52 = hist["Low"].min()
            high_52 = hist["High"].max()
            rsi = float(calc_rsi(hist["Close"]).iloc[-1])
            atr = calc_atr(hist)
            spy_hist = get_history("SPY", period="1y")
            relative_strength = get_relative_strength_from_hist(hist, spy_hist)
            distance_from_low = ((price - low_52) / low_52) * 100
            upside_to_high = ((high_52 - price) / price) * 100
            change_30d = ((price - hist["Close"].iloc[-22]) / hist["Close"].iloc[-22]) * 100
            change_90d = ((price - hist["Close"].iloc[-63]) / hist["Close"].iloc[-63]) * 100
            market_cap = info.get("marketCap", 0)
            forward_pe = info.get("forwardPE")
            target_price = info.get("targetMeanPrice")
            analyst_upside = ((target_price - price) / price * 100) if target_price and price else None

            score = 0
            if distance_from_low <= 10: score += 25
            elif distance_from_low <= 20: score += 18
            elif distance_from_low <= 30: score += 10
            if rsi < 30: score += 25
            elif rsi < 40: score += 18
            elif rsi < 50: score += 8
            if upside_to_high > 50: score += 20
            elif upside_to_high > 30: score += 15
            elif upside_to_high > 15: score += 8
            if change_30d < -15: score += 15
            elif change_30d < -8: score += 10
            elif change_30d < 0: score += 5
            if analyst_upside and analyst_upside > 25: score += 15
            elif analyst_upside and analyst_upside > 10: score += 8
            if market_cap and market_cap > 10_000_000_000: score += 10

            if score >= 75: rating = "🟢 Strong Recovery Candidate"; hold = "Recovery swing / staged long-term hold"
            elif score >= 55: rating = "🟡 Watchlist Bounce Candidate"; hold = "Watchlist bounce candidate"
            else: rating = "🔴 Risky / Possible Value Trap"; hold = "Watch only"

            recovery_plan = (
                f"{ticker} has {upside_to_high:.1f}% upside to its 52-week high. "
                f"{'Strong recovery setup.' if score >= 75 else 'Watchlist candidate.' if score >= 55 else 'Value-trap risk — wait for confirmation.'}"
            )

            rows.append({
                "Ticker": ticker, "Price": safe_round(price), "Price Bucket": get_price_bucket(price),
                "Recovery Score": safe_round(score, 0), "Rating": rating,
                "RSI": safe_round(rsi, 1), "ATR": safe_round(atr), "Relative Strength vs SPY %": relative_strength, "52W High": safe_round(high_52),
                "Delta to 52W High $": safe_round(high_52 - price),
                "Delta to 52W High %": safe_round(((high_52 - price) / price * 100), 1),
                "From 52W Low %": safe_round(distance_from_low, 1),
                "Entry Range": f"${price*0.95:.2f} - ${price:.2f}",
                "Stop Loss": safe_round(price * 0.90),
                "Target / Sell Zone": f"${price*1.10:.2f} - ${min(high_52, price*1.25):.2f}",
                "Risk / Reward": "~1.5:1 est.", "Hold Style": hold,
                "Position Size Note": "Use staged entries; add only after trend confirmation.",
                "AI Trade Plan": recovery_plan,
                "30D Change %": safe_round(change_30d, 1), "90D Change %": safe_round(change_90d, 1),
                "Analyst Upside %": safe_round(analyst_upside, 1), "Forward PE": safe_round(forward_pe, 1),
            })
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by="Recovery Score", ascending=False)
        df = diversify_by_price_bucket(df, per_bucket=5, min_conviction=55)
    return df


def check_sector_concentration(df):
    if df is None or df.empty or "Ticker" not in df.columns:
        return {}

    sectors = {}
    for ticker in df["Ticker"].dropna().tolist():
        try:
            info = get_info(ticker)
            sector = info.get("sector", "Unknown") or "Unknown"
            sectors[sector] = sectors.get(sector, 0) + 1
        except Exception:
            sectors["Unknown"] = sectors.get("Unknown", 0) + 1
    return sectors


def show_sector_concentration_warning(df):
    sectors = check_sector_concentration(df)
    total = sum(sectors.values())
    if not sectors or total == 0:
        return

    top_sector, top_count = max(sectors.items(), key=lambda x: x[1])
    if total >= 3 and (top_count / total) > 0.50:
        st.warning(f"⚠️ Sector concentration: {top_count} of {total} signals are in {top_sector}. Consider diversifying before committing capital.")


# ============================================================
# ALERT LOG + EMAIL
# ============================================================

def load_alert_history(): return load_json_file(ALERT_HISTORY_FILE, [])
def save_alert_history(h): return save_json_file(ALERT_HISTORY_FILE, h)

def log_alert(alert_type, tickers):
    history = load_alert_history()
    ticker_text = ", ".join(str(t) for t in tickers) if isinstance(tickers, list) else str(tickers)
    history.append({
        "timestamp": datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M:%S %p ET"),
        "alert_type": alert_type,
        "tickers": ticker_text,
    })
    save_alert_history(history[-100:])


def send_email_alert(subject, body):
    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    recipients = os.getenv("EMAIL_RECIPIENTS", "")
    if not sender or not password or not recipients:
        return False, "Missing EMAIL_SENDER, EMAIL_PASSWORD, or EMAIL_RECIPIENTS env var."
    msg = MIMEText(body)
    msg["Subject"] = subject; msg["From"] = sender; msg["To"] = recipients
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, [x.strip() for x in recipients.split(",")], msg.as_string())
        return True, "Email sent successfully."
    except Exception as e:
        return False, str(e)


# ============================================================
# COLUMN CONFIG + TABLE HELPERS
# ============================================================

COLUMN_HELP = {
    "Ticker": "Stock symbol. Click to open Yahoo Finance.",
    "ETF": "ETF ticker. Click to open Yahoo Finance.",
    "Price": "Latest price. Live from Alpaca during market hours if configured; otherwise Yahoo daily close.",
    "Price Bucket": "Price range category used to improve opportunity variety.",
    "Relative Strength vs SPY %": "3-month performance versus SPY. Positive means the stock is outperforming the market.",
    "ATR": "Average True Range. Used to create volatility-adjusted stop losses.",
    "Market Regime": "Broad market condition using SPY versus its 200-day moving average.",
    "Price Source": "Where the current price came from — Alpaca live or Yahoo delayed.",
    "Daily %": "Price change vs prior close.",
    "AI Score": "Rules-based technical score 0-100.",
    "Signal": "Dashboard label. Earnings within 7 days automatically downgrades BUY NOW to Watch.",
    "Earnings": "Upcoming earnings date proximity and risk level.",
    "Risk Score": "Risk estimate 0-100. Higher = more caution.",
    "RSI": "Relative Strength Index. Below 30 oversold, above 70 overbought.",
    "From 52W Low %": "Distance above the 52-week low.",
    "From 52W High %": "Distance below the 52-week high.",
    "Volume Ratio": "Current volume vs 20-day average.",
    "Recovery Score": "Rebound potential score 0-100 for beaten-down stocks.",
    "Rating": "Recovery Radar label.",
    "30D Change %": "Last 30 trading day performance.",
    "90D Change %": "Last 90 trading day performance.",
    "Analyst Upside %": "Analyst target price upside.",
    "Forward PE": "Forward price-to-earnings ratio.",
    "Technical Agent": "Trend, RSI, volume score.",
    "Risk Agent": "Stop distance, volatility, R:R score.",
    "Fundamental Agent": "Valuation, margins, growth score.",
    "Recovery Agent": "Distance from highs/lows score.",
    "Macro Agent": "SPY/QQQ backdrop score.",
    "Final Conviction": "Weighted synthesis of all 5 agents.",
    "Agent Verdict": "Final multi-agent label.",
    "Agent Summary": "Plain-English agent reasoning.",
    "Entry Range": "Suggested entry zone.",
    "Stop Loss": "Risk-control level — setup invalidated below this.",
    "Target / Sell Zone": "Profit-taking area.",
    "Risk / Reward": "Reward vs risk ratio.",
    "Hold Style": "Suggested hold style.",
    "Position Size Note": "Sizing guidance.",
    "AI Trade Plan": "Full plain-English trade narrative.",
    "52W High": "52-week high price.",
    "Delta to 52W High $": "Dollar gap to 52-week high.",
    "Delta to 52W High %": "% gain needed to reach 52-week high.",
    "P/L $": "Paper trade dollar P/L.",
    "P/L %": "Paper trade % P/L.",
    "Stop Status": "Whether current price is above or below paper trade stop.",
}


def build_column_config(df, symbol_col=None):
    config = {}
    if df is None or df.empty:
        return config
    for col in df.columns:
        help_text = COLUMN_HELP.get(str(col), "")
        if symbol_col and col == symbol_col:
            config[col] = st.column_config.LinkColumn(
                label=col, help=help_text,
                display_text=r"https://finance\.yahoo\.com/quote/(.*)"
            )
        elif pd.api.types.is_numeric_dtype(df[col]):
            config[col] = st.column_config.NumberColumn(label=col, help=help_text)
        else:
            config[col] = st.column_config.TextColumn(label=col, help=help_text)
    return config


COMPACT_COLUMNS = [
    "Ticker", "ETF", "Price", "Price Bucket", "Final Conviction", "Agent Verdict", "Signal",
    "Earnings", "Market Regime", "RSI", "Relative Strength vs SPY %", "ATR", "Entry Range", "Stop Loss", "Target / Sell Zone",
    "Risk / Reward", "Hold Style", "52W High", "Delta to 52W High %"
]

def compact_table(df):
    if df is None or df.empty:
        return df
    cols = [c for c in COMPACT_COLUMNS if c in df.columns]
    return df[cols] if cols else df

def prepare_display_table(df):
    if df is None or df.empty:
        return df
    hidden = ["SMA20", "SMA50", "SMA200", "Price Source"]
    return df.drop(columns=[c for c in hidden if c in df.columns], errors="ignore")

def render_clickable_table(df, symbol_col="Ticker", default_compact=True, table_id="default"):
    if df.empty:
        st.info("No data to show.")
        return
    use_compact = st.toggle("Compact view", value=default_compact, key=f"compact_view_{table_id}")
    display_df = prepare_display_table(compact_table(df) if use_compact else df).copy()
    if symbol_col in display_df.columns:
        display_df[symbol_col] = display_df[symbol_col].apply(
            lambda x: f"https://finance.yahoo.com/quote/{x}"
        )
    st.data_editor(
        display_df,
        column_config=build_column_config(display_df, symbol_col if symbol_col in display_df.columns else None),
        hide_index=True, use_container_width=True, disabled=True,
    )


def show_last_refresh():
    st.caption(f"Last refreshed: {datetime.now(EASTERN).strftime('%Y-%m-%d %I:%M:%S %p ET')}")


# ============================================================
# MARKET STATUS
# ============================================================

def get_market_status():
    now = datetime.now(EASTERN)
    if now.weekday() >= 5:
        return "🔴 Market Closed", "Weekend — prices are the last trading day close."
    open_t  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    pre_t   = now.replace(hour=4,  minute=0,  second=0, microsecond=0)
    after_t = now.replace(hour=20, minute=0,  second=0, microsecond=0)
    if pre_t <= now < open_t:
        return "🟡 Pre-Market", "Market opens at 9:30 AM ET."
    elif open_t <= now <= close_t:
        return "🟢 Market Open", "Live prices active. Intraday detail view useful for timing entries."
    elif close_t < now <= after_t:
        return "🟡 After Hours", "Regular session closed."
    return "🔴 Market Closed", "Market is closed — signals based on latest available data."


def show_market_regime_banner():
    regime, label, note = get_market_regime()
    if regime == "bull":
        st.success(f"{label} — {note}")
    elif regime == "bear":
        st.error(f"{label} — {note}")
    elif regime == "neutral":
        st.warning(f"{label} — {note}")
    else:
        st.info(f"{label} — {note}")


def show_market_status_banner():
    status, note = get_market_status()
    if "Open" in status: st.success(f"{status} — {note}")
    elif "Pre" in status or "After" in status: st.info(f"{status} — {note}")
    else: st.warning(f"{status} — {note}")


# ============================================================
# CHART
# ============================================================

def plot_candlestick_chart(ticker, hist):
    if hist is None or hist.empty:
        st.info("No chart data.")
        return
    chart_df = hist.copy()
    n = len(chart_df)
    if n >= 180: periods, labels = [20, 50, 200], ["SMA20", "SMA50", "SMA200"]
    elif n >= 60: periods, labels = [5, 10, 20], ["MA5", "MA10", "MA20"]
    else: periods, labels = [3, 5, 10], ["MA3", "MA5", "MA10"]
    for p, l in zip(periods, labels):
        if n >= p:
            chart_df[l] = chart_df["Close"].rolling(p).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        row_heights=[0.72, 0.28], subplot_titles=(f"{ticker} Price Action", "Volume"))
    fig.add_trace(go.Candlestick(x=chart_df.index, open=chart_df["Open"], high=chart_df["High"],
                                  low=chart_df["Low"], close=chart_df["Close"], name="Candles"), row=1, col=1)
    for l in labels:
        if l in chart_df.columns and chart_df[l].notna().sum() > 0:
            fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df[l], mode="lines", name=l), row=1, col=1)
    fig.add_trace(go.Bar(x=chart_df.index, y=chart_df["Volume"], name="Volume"), row=2, col=1)
    fig.update_layout(height=720, margin=dict(l=10, r=10, t=55, b=10),
                      xaxis_rangeslider_visible=False, template="plotly_white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# DETAIL PAGE
# ============================================================

def detail_page(ticker):
    ticker = normalize_ticker(ticker)
    st.markdown(f"## 🔎 Deep Detail: {ticker}")

    data = analyze_ticker(ticker)

    chart_mode = st.radio("Chart timeframe", ["1Y Daily", "5D 15-Min", "1D 5-Min"],
                          horizontal=True, key=f"chart_mode_{ticker}")

    if chart_mode == "1D 5-Min": hist = get_history(ticker, period="1d", interval="5m")
    elif chart_mode == "5D 15-Min": hist = get_history(ticker, period="5d", interval="15m")
    else: hist = get_history(ticker, period="1y", interval="1d")

    if not data or hist.empty:
        st.warning("No data found for this ticker.")
        return

    # Live quote banner
    live = get_live_quote(ticker)
    if live:
        lc1, lc2, lc3, lc4 = st.columns(4)
        lc1.metric("Live Price", f"${live['price']}")
        if live["bid"]: lc2.metric("Bid / Ask", f"${live['bid']} / ${live['ask']}")
        if live["spread"]: lc3.metric("Spread", f"${live['spread']}")
        lc4.caption(live["source"])

    # Earnings flag
    earnings_label, days_to_earnings = get_earnings_flag(ticker)
    if days_to_earnings is not None and 0 <= days_to_earnings <= 14:
        st.warning(f"⚠️ {earnings_label}")
    else:
        st.caption(earnings_label)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AI Score", data["AI Score"])
    c2.metric("Final Conviction", data.get("Final Conviction", "N/A"))
    c3.metric("RSI", data["RSI"])
    c4.metric("Signal", data["Signal"])

    plot_candlestick_chart(ticker, hist)

    modern_section("AI Trade Plan")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Hold Style:** {data.get('Hold Style','N/A')}")
        st.markdown(f"**Entry Range:** {data.get('Entry Range','N/A')}")
        st.markdown(f"**Stop Loss:** ${data.get('Stop Loss','N/A')}")
    with col2:
        st.markdown(f"**Target / Sell Zone:** {data.get('Target / Sell Zone','N/A')}")
        st.markdown(f"**Risk / Reward:** {data.get('Risk / Reward','N/A')}")
        st.markdown(f"**Gap to 52W High:** {data.get('Delta to 52W High %','N/A')}%")
        st.markdown(f"**Relative Strength vs SPY:** {data.get('Relative Strength vs SPY %','N/A')}%")
        st.markdown(f"**ATR:** ${data.get('ATR','N/A')}")
    st.info(data.get("AI Trade Plan", ""))

    modern_section("Multi-Agent Breakdown")
    agent_cols = ["Technical Agent","Risk Agent","Fundamental Agent","Recovery Agent","Macro Agent","Final Conviction","Agent Verdict"]
    st.dataframe(pd.DataFrame([{k: data.get(k,"N/A") for k in agent_cols}]), use_container_width=True, hide_index=True)
    st.write(data.get("Agent Summary",""))

    # Position size calculator pre-filled with this signal's values
    render_position_calculator(
        entry_price=data.get("Price"),
        stop_price=data.get("Stop Loss"),
    )

    modern_section("Full Technical Snapshot")
    st.dataframe(pd.DataFrame([data]), use_container_width=True, hide_index=True)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("📈 AI Trading Dashboard")
st.sidebar.caption("V32.4 — Signal Cards UI Router Fix + Safe Login")

role_label = "Admin" if is_admin() else "View Only"
st.sidebar.success(f"Logged in as: {role_label}")

# Data source indicator
if alpaca_client:
    st.sidebar.success("🟢 Alpaca: Connected")
else:
    st.sidebar.info("🟡 Data: Yahoo Finance (set ALPACA_API_KEY + ALPACA_SECRET_KEY for live data)")

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.rerun()

show_last_refresh()

st.sidebar.markdown("### Navigation")
nav_page = st.sidebar.radio("Go to", [
    "Home",
    "Scanner",
    "Watchlist",
    "Paper Trades",
    "Settings & Logs",
    "Detail View",
])

# V32.4 simplified navigation mapping.
page = nav_page
if nav_page == "Home":
    page = "Dashboard"
elif nav_page == "Scanner":
    page = "Scanner Hub"
elif nav_page == "Paper Trades":
    page = "Paper Trading"
elif nav_page == "Settings & Logs":
    page = "Settings & Logs"

st.sidebar.markdown("### Refresh")
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

auto_refresh = st.sidebar.toggle("🔄 Auto Refresh (60s)", value=False)
if auto_refresh:
    st.sidebar.caption("🔄 Auto-refresh enabled. Refreshes every 60 seconds.")
    if st_autorefresh:
        st_autorefresh(interval=60_000, key="v301_autorefresh")
    else:
        st.sidebar.warning("streamlit-autorefresh is missing. Add it to requirements.txt for auto-refresh.")

st.sidebar.markdown("### Watchlist Quick Add")
if is_admin():
    quick_ticker = st.sidebar.text_input("Ticker", placeholder="NVDA", key="sidebar_add_ticker")
    if st.sidebar.button("Add to Watchlist"):
        t = normalize_ticker(quick_ticker)
        if not t:
            st.sidebar.warning("Enter a ticker.")
        elif t in st.session_state.watchlist:
            st.sidebar.info(f"{t} already in watchlist.")
        else:
            st.session_state.watchlist.append(t)
            save_watchlist()
            st.sidebar.success(f"Added {t}")
            st.rerun()
else:
    st.sidebar.info("View-only: watchlist editing disabled.")


# ============================================================
# MAIN APP
# ============================================================

modern_hero(
    "📈 AI Trading Dashboard V32.4.4",
    "Alpaca live data · Signal cards · Simplified navigation · ATR stops · Relative strength vs SPY"
)
st.caption(
    "V32.4 — Prices sourced from Alpaca during market hours when configured; falls back to Yahoo Finance. "
    "BUY NOW signals auto-logged for accuracy tracking. Earnings within 7 days auto-downgrades signals. "
    "Not financial advice — use for research only."
)

# ============================================================
# PAGES
# ============================================================

if page == "Dashboard":
    show_market_status_banner()
    show_market_regime_banner()
    modern_section("🏠 Home Dashboard")
    st.caption("V32.4 balances results across price buckets while applying a minimum conviction floor. Financial, entertainment/media, and highly speculative value-trap names are excluded.")
    if is_admin(): st.success("Admin mode active.")
    else: st.info("View-only mode.")

    scan_df     = build_scan(CORE_SCAN_TICKERS)
    watch_df    = build_scan(st.session_state.watchlist)
    recovery_df = build_recovery_radar(RECOVERY_TICKERS)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Watchlist Stocks", len(st.session_state.watchlist))
    c2.metric("BUY NOW Signals", int((scan_df["Signal"].str.contains("BUY NOW")).sum()) if not scan_df.empty else 0)
    c3.metric("High Conviction", int((scan_df.get("Final Conviction", pd.Series()) >= 80).sum()) if not scan_df.empty else 0)
    c4.metric("Paper Trades", len(st.session_state.paper_trades))

    modern_section("🟢 Top BUY NOW Signals")
    if not scan_df.empty:
        buy_now = scan_df[scan_df["Signal"].str.contains("BUY NOW", na=False)].head(10)
        if buy_now.empty: st.info("No BUY NOW signals right now.")
        else: render_clickable_table(buy_now, "Ticker", table_id="dash_buynow")
    else: st.info("No scan data.")

    modern_section("🔥 Top Recovery Radar")
    if not recovery_df.empty: render_clickable_table(recovery_df.head(10), "Ticker", table_id="dash_recovery")
    else: st.info("No recovery candidates.")

    modern_section("⭐ Watchlist Snapshot")
    if not watch_df.empty: render_clickable_table(watch_df, "Ticker", table_id="dash_watchlist")
    else: st.info("No watchlist data.")


elif page == "Scanner Hub":
    show_market_status_banner()
    show_market_regime_banner()
    modern_section("🔎 Scanner Hub", "Use tabs to review all opportunities, BUY NOW signal cards, recovery rebounds, and ETF timing.")

    scan_df = build_scan(CORE_SCAN_TICKERS)
    recovery_df = build_recovery_radar(RECOVERY_TICKERS)
    etf_df = build_scan(ETF_TICKERS, diversified=False) if "build_scan" in globals() else pd.DataFrame()

    tab1, tab2, tab3, tab4 = st.tabs(["Signal Cards", "All Scanner", "Recovery Radar", "ETF Timing"])

    with tab1:
        modern_section("🟢 BUY NOW / High Conviction Cards")
        if not scan_df.empty:
            if "Final Conviction" in scan_df.columns:
                buy_df = scan_df[(scan_df["Signal"].astype(str).str.contains("BUY NOW", na=False)) | (scan_df["Final Conviction"].fillna(0) >= 68)]
            else:
                buy_df = scan_df[scan_df["Signal"].astype(str).str.contains("BUY NOW", na=False)]

            mobile_summary = st.toggle("📱 Mobile Summary View", value=False, key="scanner_cards_mobile")
            if buy_df.empty:
                st.info("No BUY NOW or high-conviction signals right now.")
            elif mobile_summary:
                render_mobile_signal_summary(buy_df)
            else:
                show_sector_concentration_warning(buy_df)
                render_signal_cards(buy_df, limit=12)
        else:
            st.info("No scanner data.")

    with tab2:
        modern_section("🤖 All Scanner Results")
        if not scan_df.empty:
            render_clickable_table(scan_df, "Ticker", table_id="scanner_hub_all")
        else:
            st.info("No scanner data.")

    with tab3:
        modern_section("🔥 Recovery Radar")
        if not recovery_df.empty:
            render_clickable_table(recovery_df, "Ticker", table_id="scanner_hub_recovery")
        else:
            st.info("No recovery candidates.")

    with tab4:
        modern_section("📊 ETF Timing")
        if not etf_df.empty:
            render_clickable_table(etf_df, "Ticker", table_id="scanner_hub_etf")
        else:
            st.info("No ETF data.")


elif page == "Watchlist":
    modern_section("⭐ Persistent Watchlist")
    if is_admin():
        st.success(f"Watchlist saved to: {WATCHLIST_FILE}")
        add_col, reset_col = st.columns([3, 1])
        with add_col:
            new_ticker = st.text_input("Add ticker", placeholder="AAPL, NVDA, ELF", key="watchlist_add")
        with reset_col:
            st.write(""); st.write("")
            if st.button("Reset Default"):
                st.session_state.watchlist = DEFAULT_WATCHLIST.copy()
                save_watchlist(); st.rerun()
        if st.button("➕ Add Ticker"):
            t = normalize_ticker(new_ticker)
            if not t: st.warning("Enter a ticker.")
            elif t in st.session_state.watchlist: st.info(f"{t} already in watchlist.")
            else:
                st.session_state.watchlist.append(t); save_watchlist()
                st.success(f"Added {t}"); st.rerun()
    else:
        st.info("View-only: editing disabled.")

    modern_section("Current Watchlist")
    if not st.session_state.watchlist:
        st.info("Watchlist is empty.")
    else:
        for ticker in list(st.session_state.watchlist):
            if is_admin():
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"**{ticker}**")
                c2.link_button("Open Yahoo", f"https://finance.yahoo.com/quote/{ticker}")
                if c3.button("Remove", key=f"remove_{ticker}"):
                    st.session_state.watchlist.remove(ticker); save_watchlist(); st.rerun()
            else:
                c1, c2 = st.columns([2, 2])
                c1.write(f"**{ticker}**")
                c2.link_button("Open Yahoo", f"https://finance.yahoo.com/quote/{ticker}")

        modern_section("Watchlist Analysis")
        render_clickable_table(build_scan(st.session_state.watchlist), "Ticker", table_id="watchlist_analysis")


elif page == "Paper Trading":
    modern_section("🧾 Paper Trading", "Track practice trades before real capital.")
    if is_admin():
        c1, c2, c3, c4 = st.columns(4)
        pt_ticker = c1.text_input("Ticker", placeholder="NVDA")
        pt_price  = c2.number_input("Entry Price", min_value=0.0, step=0.01)
        pt_qty    = c3.number_input("Shares", min_value=0.0, step=1.0)
        pt_stop   = c4.number_input("Stop Loss", min_value=0.0, step=0.01)
        if st.button("Add Paper Trade"):
            t = normalize_ticker(pt_ticker)
            if not t or pt_price <= 0 or pt_qty <= 0: st.warning("Enter ticker, price, and shares.")
            else:
                st.session_state.paper_trades.append({
                    "Ticker": t, "Entry Price": pt_price, "Shares": pt_qty,
                    "Stop Loss": pt_stop if pt_stop > 0 else None,
                    "Date": datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M %p ET"),
                })
                save_paper_trades(); st.success(f"Added {t}"); st.rerun()
    else:
        st.info("View-only: editing disabled.")

    trades = st.session_state.paper_trades
    if not trades:
        st.info("No paper trades yet.")
    else:
        rows = []
        for i, trade in enumerate(trades):
            ticker = trade["Ticker"]
            data = analyze_ticker(ticker)
            current = data["Price"] if data else None
            entry = trade["Entry Price"]; shares = trade["Shares"]
            pnl = ((current - entry) * shares) if current else None
            pnl_pct = ((current - entry) / entry * 100) if current and entry else None
            stop = trade.get("Stop Loss")
            stop_status = "⚪ No stop" if not stop or not current else ("🔴 Stop breached" if current < stop else "🟢 Above stop")
            rows.append({
                "ID": i, "Ticker": ticker, "Entry Price": entry,
                "Current Price": current, "Shares": shares,
                "Stop Loss": stop, "Stop Status": stop_status,
                "P/L $": safe_round(pnl), "P/L %": safe_round(pnl_pct),
                "Date": trade["Date"],
            })

        trade_df = pd.DataFrame(rows)
        st.dataframe(trade_df, column_config=build_column_config(trade_df), use_container_width=True, hide_index=True)

        # Portfolio total
        total_pnl = sum(r["P/L $"] for r in rows if r["P/L $"] is not None)
        st.metric("Total Portfolio P/L", f"${total_pnl:,.2f}")

        if is_admin():
            remove_id = st.number_input("Remove trade ID", min_value=0, max_value=max(0, len(trades)-1), step=1)
            if st.button("Remove Paper Trade"):
                try:
                    st.session_state.paper_trades.pop(int(remove_id))
                    save_paper_trades(); st.rerun()
                except Exception:
                    st.error("Could not remove trade.")


elif page == "Settings & Logs":
    modern_section("⚙️ Settings & Logs", "Signal accuracy, alert history, and email diagnostics in one place.")

    tab1, tab2, tab3 = st.tabs(["Signal Accuracy", "Alert History", "Email Test"])

    with tab1:
        modern_section("📈 Signal Accuracy")
        if st.button("Update Signal Outcomes", key="settings_update_signal_outcomes"):
            log = check_signal_outcomes()
            st.success("Signal outcomes updated.")
        else:
            log = load_signal_log()

        stats = get_accuracy_stats(log)

        patterns = get_weak_signal_patterns(log)
        if patterns:
            modern_section("📋 Pattern Insights")
            for p in patterns:
                st.info(p)

        if stats:
            cols = st.columns(len(stats))
            for i, (period, s) in enumerate(stats.items()):
                cols[i].metric(f"{period} Win Rate", f"{s['win_rate']}%", f"Avg {s['avg_return']}%")
        else:
            st.info("No completed signal outcomes yet. This will populate after enough trading days pass.")

        if log:
            st.dataframe(pd.DataFrame(log), use_container_width=True, hide_index=True)

    with tab2:
        modern_section("📜 Alert History")
        history = load_alert_history()
        if not history:
            st.info("No alerts logged yet.")
        else:
            st.dataframe(pd.DataFrame(history).sort_index(ascending=False), use_container_width=True, hide_index=True)

    with tab3:
        modern_section("📧 Email Diagnostics")
        if not is_admin():
            st.warning("View-only users cannot access email diagnostics.")
        else:
            st.write("This checks whether your email alert environment variables are set.")
            env_df = pd.DataFrame([
                {"Variable": "EMAIL_SENDER", "Set": bool(os.getenv("EMAIL_SENDER", ""))},
                {"Variable": "EMAIL_PASSWORD", "Set": bool(os.getenv("EMAIL_PASSWORD", ""))},
                {"Variable": "EMAIL_RECIPIENTS", "Set": bool(os.getenv("EMAIL_RECIPIENTS", ""))},
            ])
            st.dataframe(env_df, use_container_width=True, hide_index=True)

            if st.button("Send Test Email"):
                ok, msg = send_email_alert(
                    "AI Dashboard V32.4 Test",
                    f"Test email from AI Trading Dashboard V32.4.4 at {datetime.now(EASTERN)}"
                )
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)


elif page == "Detail View":
    modern_section("🔎 Detail View", "Full single-stock analysis with live price, chart, agents, and position sizing.")
    selected = st.text_input(
        "Enter ticker",
        value=st.session_state.watchlist[0] if st.session_state.watchlist else "NVDA"
    )
    if selected:
        detail_page(selected)


st.markdown("---")
st.caption("Not financial advice. Use for research and paper-trading only. | AI Trading Dashboard V32.4.4")
