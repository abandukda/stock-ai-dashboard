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

import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ============================================================
# AI TRADING DASHBOARD
# V28.3 — MODERN FRIENDLY UI + HEADER TOOLTIPS + MULTI-USER VIEWER MODE
# ============================================================

st.set_page_config(
    page_title="AI Trading Dashboard V28.3",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)



# ============================================================
# READABLE PREMIUM UI THEME
# ============================================================

st.markdown("""
<style>
:root {
    --bg-main: #f3f6fb;
    --bg-card: #ffffff;
    --text-main: #111827;
    --text-muted: #475569;
    --border-soft: #d8e0ec;
    --blue-main: #2563eb;
}

.stApp {
    background: #f3f6fb !important;
    color: #111827 !important;
}

html, body, p, div, span, label {
    color: #111827;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1500px;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #0f172a !important;
    border-right: 1px solid rgba(255,255,255,0.08);
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div {
    color: #f8fafc !important;
}

section[data-testid="stSidebar"] input {
    color: #111827 !important;
    background: #ffffff !important;
}

section[data-testid="stSidebar"] .stButton button {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #ffffff !important;
    border-radius: 12px !important;
}

/* Headings */
h1, h2, h3 {
    color: #111827 !important;
    letter-spacing: -0.03em;
}

h1 {
    font-size: 2.25rem !important;
    font-weight: 850 !important;
}

h2 {
    font-size: 1.55rem !important;
    font-weight: 800 !important;
}

/* Hero */
.modern-hero {
    padding: 26px;
    border-radius: 24px;
    background: linear-gradient(135deg, #0f172a 0%, #1e40af 58%, #0f766e 100%);
    color: #ffffff !important;
    box-shadow: 0 18px 42px rgba(15, 23, 42, 0.22);
    margin-bottom: 20px;
    border: 1px solid rgba(255,255,255,0.12);
}

.modern-hero h1,
.modern-hero p,
.modern-hero span,
.modern-hero div {
    color: #ffffff !important;
}

.modern-hero p {
    color: #e0f2fe !important;
    font-size: 1.03rem;
    margin-bottom: 0;
}

/* Cards */
.modern-card {
    padding: 18px 20px;
    border-radius: 20px;
    background: #ffffff !important;
    color: #111827 !important;
    border: 1px solid #d8e0ec;
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
    margin-bottom: 16px;
}

.modern-card * {
    color: #111827 !important;
}

.modern-section-title {
    padding: 14px 0 8px 0;
    font-size: 1.25rem;
    font-weight: 850;
    color: #111827 !important;
}

[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    color: #475569 !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #d8e0ec;
    border-radius: 18px;
    padding: 15px 16px;
    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.07);
}

[data-testid="stMetric"] * {
    color: #111827 !important;
}

[data-testid="stMetricLabel"] {
    color: #475569 !important;
}

[data-testid="stMetricValue"] {
    color: #111827 !important;
    font-weight: 850 !important;
}

/* Buttons */
.stButton button, .stDownloadButton button, .stLinkButton a {
    border-radius: 13px !important;
    border: 1px solid #bfdbfe !important;
    background: #ffffff !important;
    color: #1d4ed8 !important;
    box-shadow: 0 5px 14px rgba(15, 23, 42, 0.08);
    font-weight: 750 !important;
}

.stButton button:hover, .stDownloadButton button:hover, .stLinkButton a:hover {
    background: #eff6ff !important;
    color: #1e40af !important;
    border-color: #93c5fd !important;
}

/* Inputs */
.stTextInput input, .stNumberInput input, textarea {
    border-radius: 12px !important;
    background: #ffffff !important;
    color: #111827 !important;
    border: 1px solid #cbd5e1 !important;
}

/* Alerts */
.stAlert {
    border-radius: 16px !important;
    color: #111827 !important;
}

.stAlert * {
    color: #111827 !important;
}

/* Expanders */
.streamlit-expanderHeader {
    border-radius: 14px !important;
    font-weight: 750 !important;
    color: #111827 !important;
    background: #ffffff !important;
}

/* Tables */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
    border: 1px solid #d8e0ec;
    background: #ffffff !important;
}

[data-testid="stDataFrame"] div,
[data-testid="stDataEditor"] div,
[data-testid="stDataFrame"] span,
[data-testid="stDataEditor"] span,
[data-testid="stDataFrame"] p,
[data-testid="stDataEditor"] p {
    color: #111827 !important;
}

[data-testid="stDataEditor"] [role="columnheader"],
[data-testid="stDataFrame"] [role="columnheader"] {
    background: #e8eef8 !important;
    color: #111827 !important;
    font-weight: 800 !important;
}

a {
    color: #1d4ed8 !important;
    font-weight: 650;
}

/* Mobile */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.8rem;
        padding-right: 0.8rem;
    }

    .modern-hero {
        padding: 18px;
        border-radius: 18px;
    }

    h1 {
        font-size: 1.75rem !important;
    }

    h2 {
        font-size: 1.25rem !important;
    }

    [data-testid="stMetric"] {
        padding: 12px;
    }
}
</style>
""", unsafe_allow_html=True)


def modern_hero(title, subtitle):
    st.markdown(
        f"""
        <div class="modern-hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True
    )


def modern_card(title, body):
    st.markdown(
        f"""
        <div class="modern-card">
            <div style="font-weight:800;font-size:1.05rem;color:#111827;margin-bottom:4px;">{title}</div>
            <div style="color:#475569;font-size:0.95rem;">{body}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def modern_section(title, subtitle=None):
    st.markdown(f'<div class="modern-section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)



EASTERN = ZoneInfo("America/New_York")

# Render local filesystem can reset on deploy. If you attach a persistent disk,
# set DATA_DIR=/var/data in Render environment variables.
DATA_DIR = Path(os.getenv("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

WATCHLIST_FILE = DATA_DIR / "watchlist.json"
PAPER_TRADES_FILE = DATA_DIR / "paper_trades.json"
ALERT_HISTORY_FILE = DATA_DIR / "alert_history.json"

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "AMZN", "GOOGL", "META",
    "SNOW", "ELF", "PLTR", "SHOP"
]

CORE_SCAN_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "AMZN", "GOOGL", "META",
    "NFLX", "AVGO", "SMCI", "PLTR", "SNOW", "SHOP", "ELF", "COST",
    "LLY", "UNH", "JPM", "V", "MA", "CRM", "ADBE", "NOW", "PANW",
    "CRWD", "QQQ", "SPY", "DIA", "IWM"
]

RECOVERY_TICKERS = [
    "PYPL", "NKE", "DIS", "ADBE", "SNOW", "SBUX", "TGT", "INTC",
    "AMD", "BA", "UPS", "CVS", "WBA", "ELF", "ENPH", "SEDG",
    "TSLA", "SHOP", "SQ", "ROKU", "F", "GM", "PFE", "MRNA"
]

ETF_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "SMH", "ARKK"]



# ============================================================
# LOGIN / ROLE HELPERS
# ============================================================

def clean_secret(value):
    return str(value or "").strip()


ADMIN_USER = clean_secret(os.getenv("ADMIN_USER", ""))
ADMIN_PASSWORD = clean_secret(os.getenv("ADMIN_PASSWORD", ""))
VIEW_USER = clean_secret(os.getenv("VIEW_USER", ""))
VIEW_PASSWORD = clean_secret(os.getenv("VIEW_PASSWORD", ""))


def require_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_role" not in st.session_state:
        st.session_state.user_role = None
    if "login_user" not in st.session_state:
        st.session_state.login_user = ""

    if st.session_state.logged_in:
        return

    st.title("🔐 AI Trading Dashboard Login")
    st.caption("Admin can edit watchlists, paper trades, and send email alerts. Viewer has read-only access.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        entered_user = clean_secret(username).lower()
        entered_password = clean_secret(password)

        admin_user_match = ADMIN_USER and entered_user == ADMIN_USER.lower()
        view_user_match = VIEW_USER and entered_user == VIEW_USER.lower()

        if admin_user_match and ADMIN_PASSWORD and entered_password == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.user_role = "admin"
            st.session_state.login_user = ADMIN_USER
            st.rerun()
        elif view_user_match and VIEW_PASSWORD and entered_password == VIEW_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.user_role = "viewer"
            st.session_state.login_user = VIEW_USER
            st.rerun()
        else:
            st.error("Invalid username or password.")
            st.warning("Check that Render environment variable names and values are saved exactly, then redeploy.")

    with st.expander("🔧 Login Diagnostics"):
        st.write("This does not show your passwords. It only confirms whether Render can read the variables.")
        st.write(f"ADMIN_USER set: {'✅ Yes' if ADMIN_USER else '❌ No'}")
        st.write(f"ADMIN_PASSWORD set: {'✅ Yes' if ADMIN_PASSWORD else '❌ No'}")
        st.write(f"VIEW_USER set: {'✅ Yes' if VIEW_USER else '❌ No'}")
        st.write(f"VIEW_PASSWORD set: {'✅ Yes' if VIEW_PASSWORD else '❌ No'}")
        st.caption("Expected variable names: ADMIN_USER, ADMIN_PASSWORD, VIEW_USER, VIEW_PASSWORD")

    st.info("Set ADMIN_USER, ADMIN_PASSWORD, VIEW_USER, and VIEW_PASSWORD in Render environment variables, then use Manual Deploy → Clear build cache & deploy.")
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
# DATA + INDICATORS
# ============================================================

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


@st.cache_data(ttl=60)
def get_history(ticker, period="1y", interval="1d"):
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.dropna()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_info(ticker):
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}




# ============================================================
# V28.3 FREE RULES-BASED MULTI-AGENT ENGINE
# ============================================================

def technical_agent(price, sma20, sma50, sma200, rsi, volume_ratio):
    score = 0
    reasons = []

    if price > sma20:
        score += 18
        reasons.append("above 20-day trend")
    else:
        reasons.append("below 20-day trend")

    if price > sma50:
        score += 22
        reasons.append("above 50-day trend")
    else:
        reasons.append("below 50-day trend")

    if price > sma200:
        score += 25
        reasons.append("above 200-day trend")
    else:
        reasons.append("below 200-day trend")

    if 45 <= rsi <= 70:
        score += 20
        reasons.append("RSI in healthy swing zone")
    elif 30 <= rsi < 45:
        score += 12
        reasons.append("RSI beaten down but stabilizing")
    elif rsi < 30:
        score += 8
        reasons.append("RSI oversold")
    else:
        score -= 10
        reasons.append("RSI overbought")

    if volume_ratio >= 1.3:
        score += 15
        reasons.append("volume confirms stronger interest")
    elif volume_ratio >= 0.9:
        score += 8
        reasons.append("volume is normal")
    else:
        score -= 5
        reasons.append("volume confirmation is weak")

    return max(0, min(100, score)), "; ".join(reasons)


def risk_agent(price, stop_loss, target_low, risk_score, hist):
    try:
        close = hist["Close"]
        daily_returns = close.pct_change().dropna()
        volatility = daily_returns.tail(30).std() * 100
        drawdown = ((price - close.tail(90).max()) / close.tail(90).max()) * 100
    except Exception:
        volatility = 3
        drawdown = -10

    risk_per_share = max(price - stop_loss, 0.01)
    reward_per_share = max(target_low - price, 0.01)
    rr = reward_per_share / risk_per_share

    score = 100
    reasons = []

    if rr >= 2:
        reasons.append("risk/reward is attractive")
    elif rr >= 1.2:
        score -= 15
        reasons.append("risk/reward is acceptable but not ideal")
    else:
        score -= 30
        reasons.append("risk/reward is weak")

    if risk_score >= 55:
        score -= 25
        reasons.append("dashboard risk score is elevated")
    elif risk_score < 35:
        reasons.append("dashboard risk score is controlled")

    if volatility > 4:
        score -= 15
        reasons.append("short-term volatility is high")
    elif volatility < 2.5:
        reasons.append("volatility is manageable")

    if drawdown < -25:
        score -= 10
        reasons.append("recent drawdown is deep")
    else:
        reasons.append("recent drawdown is not extreme")

    return max(0, min(100, score)), "; ".join(reasons)


def fundamental_agent(info):
    score = 50
    reasons = []

    forward_pe = info.get("forwardPE", None)
    trailing_pe = info.get("trailingPE", None)
    profit_margin = info.get("profitMargins", None)
    revenue_growth = info.get("revenueGrowth", None)
    debt_to_equity = info.get("debtToEquity", None)
    market_cap = info.get("marketCap", None)

    pe = forward_pe or trailing_pe

    if market_cap and market_cap > 10_000_000_000:
        score += 10
        reasons.append("large-cap quality/liquidity")
    elif market_cap:
        reasons.append("smaller/mid-cap profile")

    if pe and 0 < pe < 25:
        score += 15
        reasons.append("valuation is reasonable")
    elif pe and 25 <= pe < 50:
        score += 5
        reasons.append("valuation is elevated but not extreme")
    elif pe and pe >= 50:
        score -= 10
        reasons.append("valuation is expensive")

    if profit_margin and profit_margin > 0.15:
        score += 15
        reasons.append("strong profit margins")
    elif profit_margin and profit_margin > 0:
        score += 5
        reasons.append("positive margins")
    elif profit_margin is not None:
        score -= 10
        reasons.append("weak or negative margins")

    if revenue_growth and revenue_growth > 0.10:
        score += 15
        reasons.append("healthy revenue growth")
    elif revenue_growth and revenue_growth > 0:
        score += 5
        reasons.append("modest revenue growth")
    elif revenue_growth is not None:
        score -= 10
        reasons.append("revenue growth is negative")

    if debt_to_equity and debt_to_equity > 200:
        score -= 10
        reasons.append("debt load appears elevated")
    elif debt_to_equity is not None:
        score += 5
        reasons.append("debt level appears manageable")

    if not reasons:
        reasons.append("limited fundamental data available")

    return max(0, min(100, score)), "; ".join(reasons)


def recovery_agent(price, high_52, low_52, rsi, delta_to_high_pct):
    score = 0
    reasons = []

    from_low_pct = ((price - low_52) / low_52 * 100) if low_52 else 0

    if delta_to_high_pct and delta_to_high_pct >= 40:
        score += 30
        reasons.append("large upside gap to 52-week high")
    elif delta_to_high_pct and delta_to_high_pct >= 20:
        score += 20
        reasons.append("moderate upside gap to 52-week high")
    else:
        score += 8
        reasons.append("limited recovery gap to 52-week high")

    if from_low_pct <= 15:
        score += 25
        reasons.append("near 52-week low")
    elif from_low_pct <= 30:
        score += 15
        reasons.append("still close to lower yearly range")

    if rsi < 35:
        score += 25
        reasons.append("oversold rebound setup")
    elif rsi < 50:
        score += 15
        reasons.append("beaten-down but stabilizing")

    if price > low_52 * 1.05:
        score += 10
        reasons.append("price has bounced off lows")

    return max(0, min(100, score)), "; ".join(reasons)


@st.cache_data(ttl=300)
def macro_agent():
    spy = get_history("SPY", period="6mo")
    qqq = get_history("QQQ", period="6mo")

    score = 50
    reasons = []

    for symbol, hist in [("SPY", spy), ("QQQ", qqq)]:
        try:
            close = hist["Close"]
            price = close.iloc[-1]
            sma20 = close.rolling(20).mean().iloc[-1]
            sma50 = close.rolling(50).mean().iloc[-1]

            if price > sma20 and price > sma50:
                score += 20
                reasons.append(f"{symbol} trend is supportive")
            elif price > sma50:
                score += 8
                reasons.append(f"{symbol} is above 50-day trend but short-term trend is mixed")
            elif price < sma50:
                score -= 15
                reasons.append(f"{symbol} is below 50-day trend")
            else:
                reasons.append(f"{symbol} trend is mixed")
        except Exception:
            reasons.append(f"{symbol} data unavailable")

    return max(0, min(100, score)), "; ".join(reasons)


def synthesis_agent(technical_score, risk_score_agent, fundamental_score, recovery_score, macro_score):
    final = (
        technical_score * 0.30
        + risk_score_agent * 0.25
        + fundamental_score * 0.20
        + recovery_score * 0.15
        + macro_score * 0.10
    )

    if final >= 80:
        verdict = "🟢 High Conviction"
    elif final >= 68:
        verdict = "🟢 Strong Candidate"
    elif final >= 55:
        verdict = "🟡 Watch / Starter Size"
    elif final >= 45:
        verdict = "⚪ Mixed Setup"
    else:
        verdict = "🔴 Avoid / Wait"

    return round(final, 0), verdict



def build_ai_trade_plan(ticker, price, sma20, sma50, sma200, rsi, ai_score, risk_score, high_52, low_52, upside_to_high, volume_ratio):
    """
    Creates detailed rules-based AI trade guidance.
    This is research guidance only, not financial advice.
    """
    delta_to_high_dollars = high_52 - price if high_52 and price else None
    delta_to_high_pct = ((high_52 - price) / price * 100) if high_52 and price else None

    above_20 = price > sma20
    above_50 = price > sma50
    above_200 = price > sma200
    far_from_high = delta_to_high_pct and delta_to_high_pct >= 20

    # Entry range
    if ai_score >= 75 and risk_score < 35 and above_20 and above_50:
        entry_low = price * 0.97
        entry_high = price * 1.01
        entry_range = f"${entry_low:.2f} - ${entry_high:.2f}"
        entry_reason = "trend confirmation is already strong, so a small pullback or near-current entry is reasonable for research."
    elif rsi < 35 and far_from_high:
        entry_low = price * 0.94
        entry_high = price * 0.99
        entry_range = f"${entry_low:.2f} - ${entry_high:.2f}"
        entry_reason = "the setup is more of an oversold rebound, so staged entries on weakness are safer."
    elif above_50:
        entry_low = max(sma20 * 0.98, price * 0.96)
        entry_high = price
        entry_range = f"${entry_low:.2f} - ${entry_high:.2f}"
        entry_reason = "price is holding the medium trend, but the better entry is near short-term support."
    else:
        entry_low = price * 0.90
        entry_high = price * 0.95
        entry_range = f"Wait for reclaim above ${sma50:.2f} or pullback near ${entry_low:.2f} - ${entry_high:.2f}"
        entry_reason = "the trend is not fully confirmed, so patience is better than chasing."

    # Stop loss
    if above_50 and risk_score < 40:
        stop_loss = min(sma50 * 0.98, price * 0.92)
        stop_reason = "stop is placed below the 50-day trend area to control downside if the setup breaks."
    elif rsi < 35:
        stop_loss = price * 0.90
        stop_reason = "oversold rebounds can be volatile, so the stop gives the trade room but protects from a failed bounce."
    else:
        stop_loss = price * 0.88
        stop_reason = "because confirmation is weaker, risk should be controlled with a wider but smaller-sized stop."

    # Target / sell zone
    if delta_to_high_pct and delta_to_high_pct > 35:
        target_low = price * 1.12
        target_high = min(high_52, price * 1.30)
        sell_reason = "target uses a partial recovery move first because big rebounds often pause before reaching the full 52-week high."
    elif delta_to_high_pct and delta_to_high_pct > 15:
        target_low = price * 1.07
        target_high = min(high_52, price * 1.16)
        sell_reason = "target is moderate because upside exists but is not extreme."
    else:
        target_low = price * 1.04
        target_high = price * 1.08
        sell_reason = "target is tighter because upside to the prior high is limited."

    target_zone = f"${target_low:.2f} - ${target_high:.2f}"

    risk_per_share = max(price - stop_loss, 0.01)
    reward_per_share = max(target_low - price, 0.01)
    rr = reward_per_share / risk_per_share
    risk_reward = f"{rr:.2f}:1"

    if rr >= 2 and risk_score < 45:
        position_note = "Normal starter position may be reasonable if it fits your plan."
    elif rr >= 1.2:
        position_note = "Use smaller starter size and add only if confirmation improves."
    else:
        position_note = "Watch-only or very small size because risk/reward is not attractive yet."

    # Hold style
    if ai_score >= 80 and risk_score < 30 and above_50:
        hold_style = "Short swing / momentum hold"
    elif rsi < 40 and far_from_high:
        hold_style = "Recovery swing / staged long-term hold"
    elif above_200 and ai_score >= 60:
        hold_style = "Longer swing / possible long-term hold"
    elif risk_score >= 55:
        hold_style = "Watch only / avoid oversized position"
    else:
        hold_style = "Watchlist candidate"

    # Specific narrative
    if ai_score >= 75 and risk_score < 35:
        opening = f"{ticker} is a stronger BUY NOW style candidate because the AI Score is {ai_score:.0f} and the Risk Score is controlled at {risk_score:.0f}."
    elif ai_score >= 60 and risk_score < 50:
        opening = f"{ticker} is a constructive watch/buy candidate, but not the cleanest setup yet. AI Score is {ai_score:.0f} and Risk Score is {risk_score:.0f}."
    elif rsi < 35 and far_from_high:
        opening = f"{ticker} is more of an oversold recovery candidate than a clean momentum buy."
    else:
        opening = f"{ticker} is not a clean buy yet and needs more confirmation."

    trend_parts = []
    trend_parts.append("above 20-day trend" if above_20 else "below 20-day trend")
    trend_parts.append("above 50-day trend" if above_50 else "below 50-day trend")
    trend_parts.append("above 200-day trend" if above_200 else "below 200-day trend")

    if rsi < 30:
        rsi_detail = f"RSI is {rsi:.1f}, oversold. That may create rebound potential, but it can also mean sellers are still in control."
    elif rsi <= 45:
        rsi_detail = f"RSI is {rsi:.1f}, which suggests the stock is still beaten down but starting to become more interesting."
    elif rsi <= 70:
        rsi_detail = f"RSI is {rsi:.1f}, a healthier range for swing entries."
    else:
        rsi_detail = f"RSI is {rsi:.1f}, overbought. I would avoid chasing strength here."

    if delta_to_high_pct and delta_to_high_pct >= 30:
        high_detail = f"The 52-week high is ${high_52:.2f}, which is ${delta_to_high_dollars:.2f} above current price, or about {delta_to_high_pct:.1f}% away."
    elif delta_to_high_pct and delta_to_high_pct >= 10:
        high_detail = f"The 52-week high is ${high_52:.2f}, leaving about {delta_to_high_pct:.1f}% potential back to that level."
    else:
        high_detail = f"The stock is already close to its 52-week high of ${high_52:.2f}, so this is more of a momentum setup than a recovery setup."

    volume_detail = (
        f"Volume is {volume_ratio:.2f}x normal, showing stronger participation."
        if volume_ratio >= 1.3 else
        f"Volume is {volume_ratio:.2f}x normal, which is acceptable but not a major confirmation."
        if volume_ratio >= 0.9 else
        f"Volume is only {volume_ratio:.2f}x normal, so confirmation is weaker."
    )

    plan = (
        f"{opening} "
        f"Technically, price is {', '.join(trend_parts)}. "
        f"{rsi_detail} {high_detail} {volume_detail} "
        f"Suggested entry: {entry_range}; {entry_reason} "
        f"Stop loss: ${stop_loss:.2f}; {stop_reason} "
        f"Target/sell zone: {target_zone}; {sell_reason} "
        f"Risk/reward is about {risk_reward}. {position_note}"
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
        "Position Size Note": position_note,
        "Hold Style": hold_style,
    }


def analyze_ticker(ticker):
    ticker = normalize_ticker(ticker)
    hist = get_history(ticker, period="1y")

    if hist.empty or len(hist) < 60:
        return None

    close = hist["Close"]
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else price
    change_pct = ((price - prev) / prev) * 100 if prev else 0

    sma20 = close.rolling(20).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.rolling(100).mean().iloc[-1]
    rsi = calc_rsi(close).iloc[-1]

    high_52 = hist["High"].max()
    low_52 = hist["Low"].min()
    from_low = ((price - low_52) / low_52) * 100 if low_52 else 0
    from_high = ((price - high_52) / high_52) * 100 if high_52 else 0
    upside_to_high = ((high_52 - price) / price) * 100 if price else 0

    vol = hist["Volume"].iloc[-1]
    avg_vol = hist["Volume"].rolling(20).mean().iloc[-1]
    volume_ratio = vol / avg_vol if avg_vol else 1

    info = get_info(ticker)

    trend_score = 0
    if price > sma20:
        trend_score += 20
    if price > sma50:
        trend_score += 20
    if price > sma200:
        trend_score += 20
    if sma20 > sma50:
        trend_score += 15
    if rsi >= 45 and rsi <= 70:
        trend_score += 15
    if volume_ratio > 1.1:
        trend_score += 10

    risk_score = 0
    if rsi > 75:
        risk_score += 25
    if price < sma50:
        risk_score += 20
    if price < sma200:
        risk_score += 25
    if from_high < -25:
        risk_score += 15
    if volume_ratio < 0.6:
        risk_score += 10

    raw_score = trend_score - (risk_score * 0.65)
    ai_score = max(0, min(100, raw_score))

    if ai_score >= 75 and risk_score < 35:
        signal = "🟢 BUY NOW"
    elif ai_score >= 60:
        signal = "🟡 Watch"
    elif ai_score >= 45:
        signal = "⚪ Neutral"
    else:
        signal = "🔴 Avoid"

    trade_plan = build_ai_trade_plan(
        ticker=ticker,
        price=price,
        sma20=sma20,
        sma50=sma50,
        sma200=sma200,
        rsi=rsi,
        ai_score=ai_score,
        risk_score=risk_score,
        high_52=high_52,
        low_52=low_52,
        upside_to_high=upside_to_high,
        volume_ratio=volume_ratio,
    )

    # Multi-agent scoring layer
    target_text = trade_plan["Target / Sell Zone"]
    try:
        target_low = float(target_text.replace("$", "").split(" - ")[0])
    except Exception:
        target_low = price * 1.08

    tech_agent_score, tech_reason = technical_agent(price, sma20, sma50, sma200, rsi, volume_ratio)
    risk_agent_score, risk_reason = risk_agent(price, trade_plan["Stop Loss"], target_low, risk_score, hist)
    fundamental_score, fundamental_reason = fundamental_agent(info)
    recovery_agent_score, recovery_reason = recovery_agent(price, high_52, low_52, rsi, trade_plan["Delta to 52W High %"])
    macro_score, macro_reason = macro_agent()
    final_conviction, agent_verdict = synthesis_agent(
        tech_agent_score,
        risk_agent_score,
        fundamental_score,
        recovery_agent_score,
        macro_score,
    )

    agent_summary = (
        f"Technical: {tech_reason}. "
        f"Risk: {risk_reason}. "
        f"Fundamental: {fundamental_reason}. "
        f"Recovery: {recovery_reason}. "
        f"Macro: {macro_reason}."
    )

    return {
        "Ticker": ticker,
        "Price": safe_round(price),
        "Daily %": safe_round(change_pct),
        "AI Score": safe_round(ai_score, 0),
        "Signal": signal,
        "Risk Score": safe_round(risk_score, 0),
        "Technical Agent": safe_round(tech_agent_score, 0),
        "Risk Agent": safe_round(risk_agent_score, 0),
        "Fundamental Agent": safe_round(fundamental_score, 0),
        "Recovery Agent": safe_round(recovery_agent_score, 0),
        "Macro Agent": safe_round(macro_score, 0),
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
def build_scan(tickers):
    unique_tickers = []
    for ticker in tickers:
        t = normalize_ticker(str(ticker))
        if t and t not in unique_tickers:
            unique_tickers.append(t)

    rows = []
    if not unique_tickers:
        return pd.DataFrame()

    max_workers = min(8, max(1, len(unique_tickers)))

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(analyze_ticker, unique_tickers))
        rows = [r for r in results if r]
    except Exception:
        # Safe fallback if threading fails on Render
        rows = []
        for ticker in unique_tickers:
            result = analyze_ticker(ticker)
            if result:
                rows.append(result)

    df = pd.DataFrame(rows)
    if not df.empty:
        sort_col = "Final Conviction" if "Final Conviction" in df.columns else "AI Score"
        df = df.sort_values([sort_col, "Risk Score"], ascending=[False, True])
    return df


@st.cache_data(ttl=3600)
def build_recovery_radar(tickers):
    rows = []

    for ticker in tickers:
        try:
            ticker = normalize_ticker(ticker)
            hist = get_history(ticker, period="1y")

            if hist.empty or len(hist) < 60:
                continue

            info = get_info(ticker)

            price = hist["Close"].iloc[-1]
            low_52 = hist["Low"].min()
            high_52 = hist["High"].max()
            rsi = calc_rsi(hist["Close"]).iloc[-1]

            distance_from_low = ((price - low_52) / low_52) * 100
            upside_to_high = ((high_52 - price) / price) * 100

            change_30d = ((price - hist["Close"].iloc[-22]) / hist["Close"].iloc[-22]) * 100
            change_90d = ((price - hist["Close"].iloc[-63]) / hist["Close"].iloc[-63]) * 100

            market_cap = info.get("marketCap", 0)
            forward_pe = info.get("forwardPE", None)
            target_price = info.get("targetMeanPrice", None)

            analyst_upside = None
            if target_price and price:
                analyst_upside = ((target_price - price) / price) * 100

            score = 0

            if distance_from_low <= 10:
                score += 25
            elif distance_from_low <= 20:
                score += 18
            elif distance_from_low <= 30:
                score += 10

            if rsi < 30:
                score += 25
            elif rsi < 40:
                score += 18
            elif rsi < 50:
                score += 8

            if upside_to_high > 50:
                score += 20
            elif upside_to_high > 30:
                score += 15
            elif upside_to_high > 15:
                score += 8

            if change_30d < -15:
                score += 15
            elif change_30d < -8:
                score += 10
            elif change_30d < 0:
                score += 5

            if analyst_upside and analyst_upside > 25:
                score += 15
            elif analyst_upside and analyst_upside > 10:
                score += 8

            if market_cap and market_cap > 10_000_000_000:
                score += 10

            if score >= 75:
                rating = "🟢 Strong Recovery Candidate"
            elif score >= 55:
                rating = "🟡 Watchlist Bounce Candidate"
            else:
                rating = "🔴 Risky / Possible Value Trap"

            delta_to_high_dollars = high_52 - price
            delta_to_high_pct = ((high_52 - price) / price) * 100 if price else None

            if score >= 75:
                recovery_plan = (
                    f"{ticker} is showing a strong recovery setup because it remains below its prior high, "
                    f"has about {upside_to_high:.1f}% upside back to the 52-week high, and the recovery score is elevated. "
                    f"Consider staged entries instead of buying all at once."
                )
                recovery_hold_style = "Recovery swing / staged long-term hold"
            elif score >= 55:
                recovery_plan = (
                    f"{ticker} is a watchlist recovery candidate. Wait for stabilization, stronger volume, "
                    f"and improvement above key moving averages."
                )
                recovery_hold_style = "Watchlist bounce candidate"
            else:
                recovery_plan = (
                    f"{ticker} may still carry value-trap risk. Wait for better trend confirmation."
                )
                recovery_hold_style = "Watch only"

            rows.append({
                "Ticker": ticker,
                "Price": safe_round(price),
                "Recovery Score": safe_round(score, 0),
                "Rating": rating,
                "RSI": safe_round(rsi, 1),
                "52W High": safe_round(high_52),
                "Delta to 52W High $": safe_round(delta_to_high_dollars),
                "Delta to 52W High %": safe_round(delta_to_high_pct, 1),
                "From 52W Low %": safe_round(distance_from_low, 1),
                        "Entry Range": f"${price * 0.95:.2f} - ${price:.2f}",
                "Stop Loss": safe_round(price * 0.90),
                "Target / Sell Zone": f"${price * 1.10:.2f} - ${min(high_52, price * 1.25):.2f}",
                "Risk / Reward": "1.00:1+",
                "Hold Style": recovery_hold_style,
                "Position Size Note": "Use staged entries; add only after trend confirmation.",
                "AI Trade Plan": recovery_plan,
                "30D Change %": safe_round(change_30d, 1),
                "90D Change %": safe_round(change_90d, 1),
                "Analyst Upside %": safe_round(analyst_upside, 1),
                "Forward PE": safe_round(forward_pe, 1),
            })

        except Exception:
            continue

    df = pd.DataFrame(rows)

    if not df.empty:
        sort_cols = [c for c in ["Final Conviction", "Recovery Score"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))

    return df



def load_alert_history():
    return load_json_file(ALERT_HISTORY_FILE, [])


def save_alert_history(history):
    return save_json_file(ALERT_HISTORY_FILE, history)


def log_alert(alert_type, tickers):
    history = load_alert_history()
    if isinstance(tickers, list):
        ticker_text = ", ".join([str(t) for t in tickers])
    else:
        ticker_text = str(tickers)

    history.append({
        "timestamp": datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M:%S %p ET"),
        "alert_type": alert_type,
        "tickers": ticker_text,
    })
    save_alert_history(history[-100:])



# ============================================================
# EMAIL ALERTS
# ============================================================

def send_email_alert(subject, body):
    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    recipients = os.getenv("EMAIL_RECIPIENTS", "")

    if not sender or not password or not recipients:
        return False, "Missing EMAIL_SENDER, EMAIL_PASSWORD, or EMAIL_RECIPIENTS environment variable."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipients

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, [x.strip() for x in recipients.split(",")], msg.as_string())
        return True, "Email sent successfully."
    except Exception as e:
        return False, str(e)




# ============================================================
# MODERN HEADER TOOLTIP MODE
# ============================================================

COLUMN_HELP = {
    "Ticker": "Stock symbol. Click to open Yahoo Finance.",
    "ETF": "ETF ticker symbol. Click to open Yahoo Finance.",
    "Price": "Latest available stock price from Yahoo Finance.",
    "Daily %": "How much the stock moved today compared with the prior close.",
    "AI Score": "Overall bullish setup score from 0 to 100. Higher means the trend, RSI, moving averages, and volume look stronger.",
    "Signal": "Simple dashboard label based on the AI Score and risk engine.",
    "Risk Score": "Risk estimate from 0 to 100. Higher means more caution due to weak trend, overbought RSI, or other warning signs.",
    "RSI": "Relative Strength Index. Below 30 can mean oversold. Above 70 can mean overbought.",
    "From 52W Low %": "How far the current price is above its 52-week low.",
    "From 52W High %": "How far the current price is below its 52-week high. Negative means it is under the high.",
    "Volume Ratio": "Current volume compared with average volume. Above 1.0 means higher than normal trading activity.",
    "SMA20": "20-day moving average used internally for trend analysis. Hidden from main table but shown in detail view.",
    "SMA50": "50-day moving average used internally for trend confirmation. Hidden from main table but shown in detail view.",
    "SMA200": "200-day moving average used internally for long-term trend health. Hidden from main table but shown in detail view.",
    "Recovery Score": "Score from 0 to 100 for beaten-down stocks that may have rebound potential.",
    "Rating": "Recovery Radar label. Helps separate strong recovery candidates from riskier value traps.",
    "30D Change %": "Stock performance over roughly the last 30 trading days.",
    "90D Change %": "Stock performance over roughly the last 90 trading days.",
    "Analyst Upside %": "Estimated upside based on analyst target price data when available.",
    "Forward PE": "Forward price-to-earnings ratio. Lower can mean cheaper, but it depends on growth and business quality.",
    "Entry Price": "Your paper-trade entry price.",
    "Current Price": "Latest available price for the paper-trade ticker.",
    "Shares": "Number of paper-trade shares entered.",
    "P/L $": "Estimated dollar profit or loss for the paper trade.",
    "P/L %": "Estimated percentage profit or loss for the paper trade.",
    "Date": "Date and time the paper trade was added.",
    "52W High": "The highest price reached over the last 52 weeks.",
    "Delta to 52W High $": "Dollar amount between the current price and the 52-week high.",
    "Delta to 52W High %": "Percentage gain needed to return to the 52-week high.",
    "AI Trade Plan": "Plain-English explanation of why the setup may or may not be attractive.",
    "Entry Range": "Suggested research entry zone based on current price, trend, RSI, and moving averages.",
    "Target / Sell Zone": "Potential profit-taking area based on 52-week high, moving averages, and risk.",
    "Hold Style": "Suggested style: short swing, longer swing, long-term hold, or avoid/watch.",
    "Stop Loss": "Suggested risk-control level where the setup may be invalidated.",
    "Risk / Reward": "Estimated reward versus risk based on target and stop-loss levels.",
    "Position Size Note": "Simple guidance on whether to use normal, smaller, or watch-only sizing.",
    "Technical Agent": "Technical score from trend, RSI, moving averages, and volume.",
    "Risk Agent": "Risk-control score based on stop distance, volatility, drawdown, and risk/reward.",
    "Fundamental Agent": "Fundamental quality score based on valuation, profitability, debt, and growth data where available.",
    "Recovery Agent": "Recovery score based on distance from highs/lows and oversold rebound setup.",
    "Macro Agent": "Market backdrop score using broad ETF trend and risk-on/risk-off conditions.",
    "Final Conviction": "Combined multi-agent investment opportunity score.",
    "Agent Verdict": "Final label from the multi-agent engine.",
    "Agent Summary": "Plain-English summary of what the agents agree or disagree on.",
}


def build_column_config(df: pd.DataFrame, symbol_col=None):
    config = {}

    if df is None or df.empty:
        return config

    for col in df.columns:
        help_text = COLUMN_HELP.get(str(col), "")

        if symbol_col and col == symbol_col:
            config[col] = st.column_config.LinkColumn(
                label=col,
                help=help_text,
                display_text=r"https://finance\.yahoo\.com/quote/(.*)"
            )
        elif pd.api.types.is_numeric_dtype(df[col]):
            config[col] = st.column_config.NumberColumn(
                label=col,
                help=help_text
            )
        else:
            config[col] = st.column_config.TextColumn(
                label=col,
                help=help_text
            )

    return config




# ============================================================
# MARKET STATUS + DISPLAY HELPERS
# ============================================================

def get_market_status():
    now = datetime.now(EASTERN)
    is_weekday = now.weekday() < 5

    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    premarket_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
    afterhours_time = now.replace(hour=20, minute=0, second=0, microsecond=0)

    if not is_weekday:
        return "🔴 Market Closed", "Weekend. Daily prices may be stale until the next trading session."

    if premarket_time <= now < open_time:
        return "🟡 Pre-Market", "Market opens at 9:30 AM ET. Some prices may be delayed."
    elif open_time <= now <= close_time:
        return "🟢 Market Open", "Market is open. Intraday detail view is useful for timing entries."
    elif close_time < now <= afterhours_time:
        return "🟡 After Hours", "Regular market is closed. Some after-hours pricing may be limited."
    else:
        return "🔴 Market Closed", "Market is closed. Signals are based on latest available data."


def show_market_status_banner():
    status, note = get_market_status()
    if "Open" in status:
        st.success(f"{status} — {note}")
    elif "Pre" in status or "After" in status:
        st.info(f"{status} — {note}")
    else:
        st.warning(f"{status} — {note}")



# ============================================================
# UI HELPERS
# ============================================================



COMPACT_COLUMNS = [
    "Ticker", "ETF", "Price", "Final Conviction", "Agent Verdict", "Signal",
    "RSI", "Entry Range", "Stop Loss", "Target / Sell Zone", "Risk / Reward",
    "Hold Style", "52W High", "Delta to 52W High %"
]


def compact_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    compact_cols = [c for c in COMPACT_COLUMNS if c in df.columns]
    if compact_cols:
        return df[compact_cols]
    return df



def prepare_display_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hides internal technical columns from main tables to keep the dashboard clean.
    SMA values are still used by the AI engine and shown in detail view.
    """
    if df is None or df.empty:
        return df
    hidden_cols = ["SMA20", "SMA50", "SMA200"]
    return df.drop(columns=[c for c in hidden_cols if c in df.columns], errors="ignore")


def render_clickable_table(df, symbol_col="Ticker", default_compact=True, table_id="default"):
    if df.empty:
        st.info("No data to show.")
        return

    compact_key = f"compact_view_{table_id}"
    use_compact = st.toggle("Compact table view", value=default_compact, key=compact_key)

    base_df = compact_table(df) if use_compact else df
    display_df = prepare_display_table(base_df).copy()

    if symbol_col in display_df.columns:
        display_df[symbol_col] = display_df[symbol_col].apply(
            lambda x: f"https://finance.yahoo.com/quote/{x}"
        )

    st.data_editor(
        display_df,
        column_config=build_column_config(display_df, symbol_col=symbol_col if symbol_col in display_df.columns else None),
        hide_index=True,
        use_container_width=True,
        disabled=True,
    )



def show_last_refresh():
    now = datetime.now(EASTERN)
    st.caption(f"Last refreshed: {now.strftime('%Y-%m-%d %I:%M:%S %p ET')}")



def plot_candlestick_chart(ticker, hist):
    if hist is None or hist.empty:
        st.info("No chart data available.")
        return

    chart_df = hist.copy()
    candle_count = len(chart_df)

    # Daily charts use classic SMA20/50/200.
    # Intraday charts use shorter moving averages so overlays are not empty.
    if candle_count >= 180:
        ma_periods = [20, 50, 200]
        ma_labels = ["SMA20", "SMA50", "SMA200"]
    elif candle_count >= 60:
        ma_periods = [5, 10, 20]
        ma_labels = ["MA5", "MA10", "MA20"]
    else:
        ma_periods = [3, 5, 10]
        ma_labels = ["MA3", "MA5", "MA10"]

    for period, label in zip(ma_periods, ma_labels):
        if candle_count >= period:
            chart_df[label] = chart_df["Close"].rolling(period).mean()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
        subplot_titles=(f"{ticker} Price Action", "Volume"),
    )

    fig.add_trace(
        go.Candlestick(
            x=chart_df.index,
            open=chart_df["Open"],
            high=chart_df["High"],
            low=chart_df["Low"],
            close=chart_df["Close"],
            name="Candles",
        ),
        row=1,
        col=1,
    )

    for label in ma_labels:
        if label in chart_df.columns and chart_df[label].notna().sum() > 0:
            fig.add_trace(
                go.Scatter(x=chart_df.index, y=chart_df[label], mode="lines", name=label),
                row=1,
                col=1,
            )

    fig.add_trace(
        go.Bar(x=chart_df.index, y=chart_df["Volume"], name="Volume"),
        row=2,
        col=1,
    )

    fig.update_layout(
        height=720,
        margin=dict(l=10, r=10, t=55, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )

    st.plotly_chart(fig, use_container_width=True)



def detail_page(ticker):
    ticker = normalize_ticker(ticker)
    st.markdown(f"## 🔎 Deep Detail: {ticker}")

    data = analyze_ticker(ticker)

    chart_mode = st.radio(
        "Chart timeframe",
        ["1Y Daily", "5D 15-Min", "1D 5-Min"],
        horizontal=True,
        key=f"chart_mode_{ticker}"
    )

    if chart_mode == "1D 5-Min":
        hist = get_history(ticker, period="1d", interval="5m")
    elif chart_mode == "5D 15-Min":
        hist = get_history(ticker, period="5d", interval="15m")
    else:
        hist = get_history(ticker, period="1y", interval="1d")

    if not data or hist.empty:
        st.warning("No data found for this ticker.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"${data['Price']}")
    c2.metric("AI Score", data["AI Score"])
    c3.metric("RSI", data["RSI"])
    c4.metric("Signal", data["Signal"])

    plot_candlestick_chart(ticker, hist)

    modern_section("Technical Snapshot")
    st.dataframe(pd.DataFrame([data]), use_container_width=True, hide_index=True)

    modern_section("AI Trade Plan")
    st.markdown(f"**Suggested Hold Style:** {data.get('Hold Style', 'N/A')}")
    st.markdown(f"**Good Entry Range:** {data.get('Entry Range', 'N/A')}")
    st.markdown(f"**Stop Loss:** ${data.get('Stop Loss', 'N/A')}")
    st.markdown(f"**Target / Sell Zone:** {data.get('Target / Sell Zone', 'N/A')}")
    st.markdown(f"**Risk / Reward:** {data.get('Risk / Reward', 'N/A')}")
    st.markdown(f"**Position Size Note:** {data.get('Position Size Note', 'N/A')}")
    st.markdown(f"**52-Week High:** ${data.get('52W High', 'N/A')}")
    st.markdown(f"**Gap to 52-Week High:** ${data.get('Delta to 52W High $', 'N/A')} / {data.get('Delta to 52W High %', 'N/A')}%")
    st.info(data.get("AI Trade Plan", "No AI trade plan available."))

    modern_section("Multi-Agent Breakdown")
    agent_cols = [
        "Technical Agent", "Risk Agent", "Fundamental Agent",
        "Recovery Agent", "Macro Agent", "Final Conviction", "Agent Verdict"
    ]
    agent_data = {k: data.get(k, "N/A") for k in agent_cols}
    st.dataframe(pd.DataFrame([agent_data]), use_container_width=True, hide_index=True)
    st.markdown("**Agent Summary:**")
    st.write(data.get("Agent Summary", "No multi-agent summary available."))

    modern_section("AI Notes")
    notes = []
    if data["Signal"] == "🟢 BUY NOW":
        notes.append("Strong setup with supportive trend conditions. Use position sizing carefully.")
    if data["RSI"] and data["RSI"] < 35:
        notes.append("RSI is oversold, which may indicate rebound potential but can also signal weakness.")
    if data["From 52W High %"] and data["From 52W High %"] < -20:
        notes.append("Stock is meaningfully below its 52-week high. Check whether this is temporary weakness or a value trap.")
    if data["Risk Score"] and data["Risk Score"] > 50:
        notes.append("Risk score is elevated. Avoid oversized positions.")
    if not notes:
        notes.append("No major warning flags found, but confirm with your own research.")

    for n in notes:
        st.write(f"- {n}")


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("📈 AI Trading Dashboard")
st.sidebar.caption("V28.3 Modern UI")

role_label = "Admin" if is_admin() else "View Only"
st.sidebar.success(f"Logged in as: {role_label}")

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.login_user = ""
    st.rerun()

show_last_refresh()

st.sidebar.markdown("### Navigation")
page = st.sidebar.radio(
    "Go to",
    [
        "Dashboard",
        "Watchlist",
        "AI Scanner",
        "BUY NOW",
        "Recovery Radar",
        "ETF Timing",
        "Paper Trading",
        "Email Test",
        "Alert History",
        "Detail View",
    ],
)

st.sidebar.markdown("### Refresh")
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

auto_refresh = st.sidebar.toggle("Auto-refresh every 60 seconds", value=False)
if auto_refresh:
    if "last_auto_refresh" not in st.session_state:
        st.session_state.last_auto_refresh = time.time()

    elapsed = time.time() - st.session_state.last_auto_refresh

    if elapsed >= 60:
        st.session_state.last_auto_refresh = time.time()
        st.cache_data.clear()
        st.rerun()
    else:
        st.sidebar.caption(f"⏱ Next refresh in {max(0, 60 - int(elapsed))}s")
        time.sleep(1)
        st.rerun()

st.sidebar.markdown("### Watchlist Quick Add")
if is_admin():
    quick_ticker = st.sidebar.text_input("Ticker", placeholder="Example: NVDA", key="sidebar_add_ticker")
    if st.sidebar.button("Add to Watchlist"):
        t = normalize_ticker(quick_ticker)
        if not t:
            st.sidebar.warning("Enter a ticker.")
        elif t in st.session_state.watchlist:
            st.sidebar.info(f"{t} is already in your watchlist.")
        else:
            st.session_state.watchlist.append(t)
            save_watchlist()
            st.sidebar.success(f"Added {t}")
            st.rerun()
else:
    st.sidebar.info("View-only users cannot edit the watchlist.")


# ============================================================
# MAIN APP
# ============================================================

modern_hero(
    "📈 AI Trading Dashboard",
    "Login diagnostics fix with whitespace-safe environment variables and clearer Render variable checks."
)

st.caption("AI Trade Plans are rules-based research guidance, not financial advice. V28.3 merges the free multi-agent engine with persistent DATA_DIR storage, non-blocking auto-refresh, Recovery Radar bug fixes, and updated email diagnostics.")

if page == "Dashboard":
    show_market_status_banner()
    modern_section("🏠 Home Dashboard", "Quick overview of signals, watchlist strength, recovery candidates, and paper trades.")
    if is_admin():
        st.success("Admin mode: edit controls and email alerts are enabled.")
    else:
        st.info("View-only mode: friends can view scans and detail pages, but cannot edit or send alerts.")

    watch_df = build_scan(st.session_state.watchlist)
    scan_df = build_scan(CORE_SCAN_TICKERS)
    recovery_df = build_recovery_radar(RECOVERY_TICKERS)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Watchlist Stocks", len(st.session_state.watchlist))
    c2.metric("BUY NOW Signals", int((scan_df["Signal"] == "🟢 BUY NOW").sum()) if not scan_df.empty else 0)
    c3.metric("High Conviction", int((scan_df["Final Conviction"] >= 80).sum()) if not scan_df.empty and "Final Conviction" in scan_df.columns else 0)
    c4.metric("Paper Trades", len(st.session_state.paper_trades))

    modern_section("🟢 Top BUY NOW Signals")
    if scan_df.empty:
        st.info("No scan data available.")
    else:
        buy_now = scan_df[scan_df["Signal"] == "🟢 BUY NOW"].head(10)
        if buy_now.empty:
            st.info("No BUY NOW or high-conviction signals right now.")
        else:
            render_clickable_table(buy_now, "Ticker", table_id="dash_buynow")

    modern_section("🔥 Top Recovery Radar")
    if recovery_df.empty:
        st.info("No recovery candidates right now.")
    else:
        render_clickable_table(recovery_df.head(10), "Ticker", table_id="dash_recovery")

    modern_section("⭐ Your Watchlist Snapshot")
    if watch_df.empty:
        st.info("No watchlist data available.")
    else:
        render_clickable_table(watch_df, "Ticker", table_id="dash_watchlist")


elif page == "Watchlist":
    modern_section("⭐ Persistent Watchlist", "Saved watchlist with refresh-safe storage and viewer-safe access.")

    if is_admin():
        st.success("Admin mode: your watchlist is saved to watchlist.json and reloads automatically after refresh.")

        add_col, reset_col = st.columns([3, 1])

        with add_col:
            new_ticker = st.text_input("Add ticker", placeholder="Example: AAPL, NVDA, ELF", key="watchlist_add")
        with reset_col:
            st.write("")
            st.write("")
            if st.button("Reset Default"):
                st.session_state.watchlist = DEFAULT_WATCHLIST.copy()
                save_watchlist()
                st.rerun()

        if st.button("➕ Add Ticker"):
            t = normalize_ticker(new_ticker)
            if not t:
                st.warning("Enter a ticker.")
            elif t in st.session_state.watchlist:
                st.info(f"{t} is already in your watchlist.")
            else:
                st.session_state.watchlist.append(t)
                save_watchlist()
                st.success(f"Added {t}")
                st.rerun()
    else:
        st.info("View-only mode: watchlist editing is disabled.")

    modern_section("Current Watchlist")

    if not st.session_state.watchlist:
        st.info("Your watchlist is empty.")
    else:
        for ticker in list(st.session_state.watchlist):
            if is_admin():
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"**{ticker}**")
                c2.link_button("Open Yahoo", f"https://finance.yahoo.com/quote/{ticker}")
                if c3.button("Remove", key=f"remove_{ticker}"):
                    st.session_state.watchlist.remove(ticker)
                    save_watchlist()
                    st.rerun()
            else:
                c1, c2 = st.columns([2, 2])
                c1.write(f"**{ticker}**")
                c2.link_button("Open Yahoo", f"https://finance.yahoo.com/quote/{ticker}")

        modern_section("Watchlist Analysis")
        df = build_scan(st.session_state.watchlist)
        render_clickable_table(df, "Ticker", table_id="watchlist_analysis")


elif page == "AI Scanner":
    show_market_status_banner()
    modern_section("🤖 AI Swing Trade Scanner", "Ranks stocks based on trend, momentum, RSI, moving averages, volume, and risk.")
    df = build_scan(CORE_SCAN_TICKERS)
    render_clickable_table(df, "Ticker", table_id="scanner")


elif page == "BUY NOW":
    show_market_status_banner()
    modern_section("🟢 BUY NOW Signals", "Highest-conviction setups from the current scan.")
    df = build_scan(CORE_SCAN_TICKERS + st.session_state.watchlist)
    if df.empty:
        st.info("No scan data available.")
    else:
        if "Final Conviction" in df.columns:
            buy_df = df[(df["Signal"] == "🟢 BUY NOW") | (df["Final Conviction"] >= 68)]
        else:
            buy_df = df[df["Signal"] == "🟢 BUY NOW"]
        if buy_df.empty:
            st.info("No BUY NOW or high-conviction signals right now.")
        else:
            render_clickable_table(buy_df, "Ticker", table_id="buynow_page")

            with st.expander("📧 BUY NOW Email Alert Preview"):
                body = "AI Trading Dashboard BUY NOW signals:\n\n"
                for _, row in buy_df.iterrows():
                    body += f"{row['Ticker']} | Price: {row['Price']} | AI Score: {row['AI Score']} | RSI: {row['RSI']}\n"
                st.text(body)

                if is_admin():
                    if st.button("Send BUY NOW Email Alert"):
                        ok, msg = send_email_alert("AI Dashboard BUY NOW Alert", body)
                        if ok:
                            log_alert("BUY NOW", list(buy_df["Ticker"]) if "Ticker" in buy_df.columns else [])
                            st.success(msg)
                        else:
                            st.error(msg)
                else:
                    st.info("View-only users cannot send email alerts.")


elif page == "Recovery Radar":
    modern_section("🔥 AI Recovery Radar", "Finds beaten-down quality names with potential rebound upside.")
    st.caption("Finds well-known stocks near lows, beaten down after weakness, but still showing rebound potential.")

    recovery_df = build_recovery_radar(RECOVERY_TICKERS)

    if recovery_df.empty:
        st.warning("No recovery candidates found right now. Try refreshing later.")
    else:
        render_clickable_table(recovery_df.head(20), "Ticker", table_id="recovery_page")

        strong_recovery = recovery_df[recovery_df["Recovery Score"] >= 75]

        if not strong_recovery.empty:
            st.success(f"🟢 {len(strong_recovery)} strong recovery candidates found.")

            with st.expander("📧 Email Alert Preview - Recovery Radar"):
                alert_text = "AI Recovery Radar found strong rebound candidates:\n\n"
                for _, row in strong_recovery.iterrows():
                    alert_text += (
                        f"{row['Ticker']} | Score: {row['Recovery Score']} | "
                        f"RSI: {row['RSI']} | "
                        f"Delta to 52W High: {row['Delta to 52W High %']}%\n"
                    )
                st.text(alert_text)

                if is_admin():
                    if st.button("Send Recovery Radar Email Alert"):
                        ok, msg = send_email_alert("AI Recovery Radar Alert", alert_text)
                        if ok:
                            log_alert("Recovery Radar", list(strong_recovery["Ticker"]) if "Ticker" in strong_recovery.columns else [])
                            st.success(msg)
                        else:
                            st.error(msg)
                else:
                    st.info("View-only users cannot send email alerts.")
        else:
            st.info("No strong recovery candidates today, but watchlist candidates may still be useful.")


elif page == "ETF Timing":
    modern_section("📊 ETF Entry Timing", "Tracks ETF strength, risk, and entry timing across major sectors.")
    etf_df = build_scan(ETF_TICKERS)
    if etf_df.empty:
        st.info("No ETF data available.")
    else:
        etf_df = etf_df.rename(columns={"Ticker": "ETF"})
        render_clickable_table(etf_df, "ETF", table_id="etf_page")


elif page == "Paper Trading":
    modern_section("🧾 Paper Trading", "Track practice trades before risking real capital.")

    if is_admin():
        c1, c2, c3, c4 = st.columns(4)
        pt_ticker = c1.text_input("Ticker", placeholder="NVDA")
        pt_price = c2.number_input("Entry Price", min_value=0.0, step=0.01)
        pt_qty = c3.number_input("Shares", min_value=0.0, step=1.0)
        pt_stop = c4.number_input("Stop Loss", min_value=0.0, step=0.01)

        if st.button("Add Paper Trade"):
            t = normalize_ticker(pt_ticker)
            if not t or pt_price <= 0 or pt_qty <= 0:
                st.warning("Enter ticker, entry price, and shares.")
            else:
                st.session_state.paper_trades.append({
                    "Ticker": t,
                    "Entry Price": pt_price,
                    "Shares": pt_qty,
                    "Stop Loss": pt_stop if pt_stop > 0 else None,
                    "Date": datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M %p ET"),
                })
                save_paper_trades()
                st.success(f"Added paper trade for {t}")
                st.rerun()
    else:
        st.info("View-only mode: paper trade editing is disabled.")

    trades = st.session_state.paper_trades

    if not trades:
        st.info("No paper trades yet.")
    else:
        rows = []
        for i, trade in enumerate(trades):
            ticker = trade["Ticker"]
            data = analyze_ticker(ticker)
            current = data["Price"] if data else None
            entry = trade["Entry Price"]
            shares = trade["Shares"]
            pnl = ((current - entry) * shares) if current else None
            pnl_pct = ((current - entry) / entry * 100) if current and entry else None

            stop = trade.get("Stop Loss", None)
            stop_status = "⚪ No stop set"
            if stop and current:
                stop_status = "🔴 Stop breached" if current < stop else "🟢 Above stop"

            rows.append({
                "ID": i,
                "Ticker": ticker,
                "Entry Price": entry,
                "Current Price": current,
                "Shares": shares,
                "Stop Loss": stop,
                "Stop Status": stop_status,
                "P/L $": safe_round(pnl),
                "P/L %": safe_round(pnl_pct),
                "Date": trade["Date"],
            })

        trade_df = pd.DataFrame(rows)
        st.dataframe(
            trade_df,
            column_config=build_column_config(trade_df),
            use_container_width=True,
            hide_index=True
        )

        if is_admin():
            remove_id = st.number_input("Remove trade ID", min_value=0, max_value=max(0, len(trades)-1), step=1)
            if st.button("Remove Paper Trade"):
                try:
                    st.session_state.paper_trades.pop(int(remove_id))
                    save_paper_trades()
                    st.rerun()
                except Exception:
                    st.error("Could not remove trade.")


elif page == "Email Test":
    modern_section("📧 Gmail / Email Diagnostics", "Admin-only email alert setup and test area.")

    if not is_admin():
        st.warning("View-only users cannot access email diagnostics.")
        st.stop()

    st.write("This checks whether your Render environment variables are set.")

    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    recipients = os.getenv("EMAIL_RECIPIENTS", "")

    st.write(f"EMAIL_SENDER set: {'✅ Yes' if sender else '❌ No'}")
    st.write(f"EMAIL_PASSWORD set: {'✅ Yes' if password else '❌ No'}")
    st.write(f"EMAIL_RECIPIENTS set: {'✅ Yes' if recipients else '❌ No'}")

    test_body = f"Test email from AI Trading Dashboard V28.3 at {datetime.now(EASTERN).strftime('%Y-%m-%d %I:%M:%S %p ET')}"

    if st.button("Send Test Email"):
        ok, msg = send_email_alert("AI Trading Dashboard Test Email", test_body)
        if ok:
            st.success(msg)
        else:
            st.error(msg)



elif page == "Alert History":
    modern_section("📜 Alert History", "Recent email alerts sent by the dashboard.")

    history = load_alert_history()
    if not history:
        st.info("No alerts logged yet.")
    else:
        hist_df = pd.DataFrame(history)
        st.dataframe(hist_df.sort_index(ascending=False), use_container_width=True, hide_index=True)


elif page == "Detail View":
    modern_section("🔎 Mobile Detail View", "Single-stock deep view optimized for quick mobile checks.")
    selected = st.text_input("Enter ticker for detail view", value=st.session_state.watchlist[0] if st.session_state.watchlist else "NVDA")
    if selected:
        detail_page(selected)


st.markdown("---")
st.caption("Not financial advice. Use for research and paper-trading support only.")
