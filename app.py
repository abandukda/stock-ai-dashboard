import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# ============================================================
# AI TRADING DASHBOARD
# V26.5 — MODERN FRIENDLY UI + HEADER TOOLTIPS + MULTI-USER VIEWER MODE
# ============================================================

st.set_page_config(
    page_title="AI Trading Dashboard V26.5",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# MODERN UI THEME
# ============================================================

st.markdown("""
<style>
/* App background */
.stApp {
    background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 45%, #f8fafc 100%);
}

/* Main content width and spacing */
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
}

section[data-testid="stSidebar"] * {
    color: #f8fafc !important;
}

section[data-testid="stSidebar"] .stButton button {
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.18);
    color: white !important;
    border-radius: 12px;
}

/* Headings */
h1, h2, h3 {
    letter-spacing: -0.03em;
}

h1 {
    font-size: 2.3rem !important;
    font-weight: 800 !important;
}

h2 {
    font-size: 1.55rem !important;
    font-weight: 750 !important;
}

/* Cards and containers */
.modern-hero {
    padding: 24px;
    border-radius: 24px;
    background: linear-gradient(135deg, #111827 0%, #1e3a8a 55%, #312e81 100%);
    color: white;
    box-shadow: 0 18px 45px rgba(15, 23, 42, 0.22);
    margin-bottom: 20px;
}

.modern-hero h1 {
    color: white !important;
    margin-bottom: 4px;
}

.modern-hero p {
    color: #dbeafe !important;
    font-size: 1.02rem;
    margin-bottom: 0;
}

.modern-card {
    padding: 18px 20px;
    border-radius: 20px;
    background: rgba(255,255,255,0.86);
    border: 1px solid rgba(148, 163, 184, 0.22);
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    margin-bottom: 16px;
}

.modern-section-title {
    padding: 12px 0 6px 0;
    font-size: 1.25rem;
    font-weight: 800;
    color: #0f172a;
}

/* Metrics */
[data-testid="stMetric"] {
    background: rgba(255,255,255,0.92);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 18px;
    padding: 14px 16px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}

[data-testid="stMetricLabel"] {
    color: #475569 !important;
}

[data-testid="stMetricValue"] {
    font-weight: 800 !important;
    color: #0f172a !important;
}

/* Buttons */
.stButton button, .stDownloadButton button, .stLinkButton a {
    border-radius: 14px !important;
    border: 1px solid rgba(59, 130, 246, 0.25) !important;
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
    font-weight: 700 !important;
}

/* Inputs */
.stTextInput input, .stNumberInput input, textarea {
    border-radius: 12px !important;
}

/* Data tables */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
    border: 1px solid rgba(148, 163, 184, 0.24);
}

/* Alerts */
.stAlert {
    border-radius: 16px;
}

/* Expander */
.streamlit-expanderHeader {
    border-radius: 14px !important;
    font-weight: 700 !important;
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
            <div style="font-weight:800;font-size:1.05rem;color:#0f172a;margin-bottom:4px;">{title}</div>
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
WATCHLIST_FILE = "watchlist.json"
PAPER_TRADES_FILE = "paper_trades.json"

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

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
VIEW_USER = os.getenv("VIEW_USER", "viewer")
VIEW_PASSWORD = os.getenv("VIEW_PASSWORD", "viewer123")


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
        if username == ADMIN_USER and password == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.user_role = "admin"
            st.session_state.login_user = username
            st.rerun()
        elif username == VIEW_USER and password == VIEW_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.user_role = "viewer"
            st.session_state.login_user = username
            st.rerun()
        else:
            st.error("Invalid username or password.")

    st.info("Set ADMIN_USER, ADMIN_PASSWORD, VIEW_USER, and VIEW_PASSWORD in Render environment variables.")
    st.stop()


def is_admin():
    return st.session_state.get("user_role") == "admin"


require_login()


# ============================================================
# STORAGE HELPERS
# ============================================================

def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace("$", "")


def load_json_file(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json_file(path: str, data):
    try:
        with open(path, "w") as f:
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
    near_52_low = ((price - low_52) / low_52 * 100) <= 20 if low_52 else False
    far_from_high = delta_to_high_pct and delta_to_high_pct >= 20

    # Entry range logic
    if ai_score >= 75 and risk_score < 35 and above_20 and above_50:
        entry_range = f"${price * 0.97:.2f} - ${price * 1.01:.2f}"
        entry_reason = "entry can be considered near current levels or on a small pullback because trend confirmation is already strong."
    elif rsi < 35 and far_from_high:
        entry_range = f"${price * 0.94:.2f} - ${price * 0.99:.2f}"
        entry_reason = "better entry is on weakness because the stock is oversold and still trying to stabilize."
    elif above_50:
        entry_range = f"${max(sma20 * 0.98, price * 0.96):.2f} - ${price:.2f}"
        entry_reason = "entry is best near short-term support rather than chasing a green day."
    else:
        entry_range = f"Wait for reclaim above ${sma50:.2f} or pullback near ${price * 0.90:.2f} - ${price * 0.95:.2f}"
        entry_reason = "trend is not fully confirmed yet, so waiting for strength or a better pullback is safer."

    # Target/sell zone logic
    if delta_to_high_pct and delta_to_high_pct > 35:
        target_zone = f"${price * 1.12:.2f} - ${min(high_52, price * 1.30):.2f}"
        sell_reason = "first target uses a partial recovery move, not the full 52-week high, because large rebounds often pause before fully recovering."
    elif delta_to_high_pct and delta_to_high_pct > 15:
        target_zone = f"${price * 1.07:.2f} - ${min(high_52, price * 1.16):.2f}"
        sell_reason = "target zone is moderate because upside to the prior high exists but is not extreme."
    else:
        target_zone = f"${price * 1.04:.2f} - ${price * 1.08:.2f}"
        sell_reason = "upside to the prior high is limited, so profit-taking should be tighter."

    # Hold style logic
    if ai_score >= 80 and risk_score < 30 and above_50:
        hold_style = "Short swing / momentum hold"
    elif near_52_low and far_from_high and rsi < 45:
        hold_style = "Recovery swing / staged long-term hold"
    elif above_200 and ai_score >= 60:
        hold_style = "Longer swing / possible long-term hold"
    elif risk_score >= 55:
        hold_style = "Watch only / avoid oversized position"
    else:
        hold_style = "Watchlist candidate"

    # Detailed buy guidance
    if ai_score >= 75 and risk_score < 35:
        opening = f"{ticker} is showing a BUY NOW style setup because the AI Score is strong at {ai_score:.0f} while risk remains controlled at {risk_score:.0f}."
    elif ai_score >= 60 and risk_score < 50:
        opening = f"{ticker} is a constructive watch/buy candidate, but not as clean as a top-tier BUY NOW setup. AI Score is {ai_score:.0f} and risk is {risk_score:.0f}."
    elif rsi < 35 and far_from_high:
        opening = f"{ticker} looks more like an oversold recovery candidate than a clean momentum buy. The setup may work, but it needs patience and staged entries."
    else:
        opening = f"{ticker} is not a clean buy yet. The current setup needs better confirmation before treating it as a high-conviction entry."

    trend_detail = []
    if above_20:
        trend_detail.append("above the 20-day trend")
    else:
        trend_detail.append("below the 20-day trend")
    if above_50:
        trend_detail.append("above the 50-day trend")
    else:
        trend_detail.append("below the 50-day trend")
    if above_200:
        trend_detail.append("above the 200-day long-term trend")
    else:
        trend_detail.append("below the 200-day long-term trend")

    if rsi < 30:
        rsi_detail = f"RSI is {rsi:.1f}, which is oversold. That can create rebound potential, but it can also mean the stock is still weak."
    elif rsi <= 45:
        rsi_detail = f"RSI is {rsi:.1f}, which suggests the stock is still beaten down but not necessarily broken."
    elif rsi <= 70:
        rsi_detail = f"RSI is {rsi:.1f}, which is a healthier momentum zone for swing entries."
    else:
        rsi_detail = f"RSI is {rsi:.1f}, which is overbought. I would avoid chasing unless there is a strong catalyst."

    if delta_to_high_pct and delta_to_high_pct >= 30:
        high_detail = f"The 52-week high is ${high_52:.2f}, which is ${delta_to_high_dollars:.2f} above the current price, or about {delta_to_high_pct:.1f}% away. That gives meaningful recovery room."
    elif delta_to_high_pct and delta_to_high_pct >= 10:
        high_detail = f"The 52-week high is ${high_52:.2f}, which is ${delta_to_high_dollars:.2f} above the current price, or about {delta_to_high_pct:.1f}% away. Upside exists, but it is more moderate."
    else:
        high_detail = f"The 52-week high is ${high_52:.2f}. The stock is already close to that level, so the setup is more about momentum than recovery upside."

    if volume_ratio >= 1.3:
        volume_detail = f"Volume is {volume_ratio:.2f}x normal, which supports stronger market interest."
    elif volume_ratio >= 0.9:
        volume_detail = f"Volume is {volume_ratio:.2f}x normal, so participation looks normal."
    else:
        volume_detail = f"Volume is only {volume_ratio:.2f}x normal, so I would want stronger confirmation before sizing up."

    plan = (
        f"{opening} "
        f"Technically, price is {', '.join(trend_detail)}. "
        f"{rsi_detail} "
        f"{high_detail} "
        f"{volume_detail} "
        f"Suggested entry: {entry_range}; {entry_reason} "
        f"Target/sell zone: {target_zone}; {sell_reason}"
    )

    return {
        "52W High": round(high_52, 2) if high_52 else None,
        "Delta to 52W High $": round(delta_to_high_dollars, 2) if delta_to_high_dollars is not None else None,
        "Delta to 52W High %": round(delta_to_high_pct, 1) if delta_to_high_pct is not None else None,
        "AI Trade Plan": plan,
        "Entry Range": entry_range,
        "Target / Sell Zone": target_zone,
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

    ai_score = max(0, min(100, trend_score - risk_score + 35))

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

    return {
        "Ticker": ticker,
        "Price": safe_round(price),
        "Daily %": safe_round(change_pct),
        "AI Score": safe_round(ai_score, 0),
        "Signal": signal,
        "Risk Score": safe_round(risk_score, 0),
        "RSI": safe_round(rsi, 1),
        "52W High": trade_plan["52W High"],
        "Delta to 52W High $": trade_plan["Delta to 52W High $"],
        "Delta to 52W High %": trade_plan["Delta to 52W High %"],
        "From 52W Low %": safe_round(from_low, 1),
        "From 52W High %": safe_round(from_high, 1),
        "Volume Ratio": safe_round(volume_ratio, 2),
        "Entry Range": trade_plan["Entry Range"],
        "Target / Sell Zone": trade_plan["Target / Sell Zone"],
        "Hold Style": trade_plan["Hold Style"],
        "AI Trade Plan": trade_plan["AI Trade Plan"],
        "SMA20": safe_round(sma20),
        "SMA50": safe_round(sma50),
        "SMA200": safe_round(sma200),
    }


@st.cache_data(ttl=300)
def build_scan(tickers):
    rows = []
    for ticker in tickers:
        result = analyze_ticker(ticker)
        if result:
            rows.append(result)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["AI Score", "Risk Score"], ascending=[False, True])
    return df


@st.cache_data(ttl=3600)
def build_recovery_radar(tickers):
    rows = []

    for ticker in tickers:
        try:
            ticker = normalize_ticker(ticker)
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")

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
                "Target / Sell Zone": f"${price * 1.10:.2f} - ${min(high_52, price * 1.25):.2f}",
                "Hold Style": recovery_hold_style,
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
        df = df.sort_values(by="Recovery Score", ascending=False)

    return df


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
# UI HELPERS
# ============================================================


def prepare_display_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hides internal technical columns from main tables to keep the dashboard clean.
    SMA values are still used by the AI engine and shown in detail view.
    """
    if df is None or df.empty:
        return df
    hidden_cols = ["SMA20", "SMA50", "SMA200"]
    return df.drop(columns=[c for c in hidden_cols if c in df.columns], errors="ignore")


def render_clickable_table(df, symbol_col="Ticker"):
    if df.empty:
        st.info("No data to show.")
        return

    display_df = prepare_display_table(df).copy()

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


def detail_page(ticker):
    ticker = normalize_ticker(ticker)
    st.markdown(f"## 🔎 Deep Detail: {ticker}")

    data = analyze_ticker(ticker)
    hist = get_history(ticker, period="1y")

    if not data or hist.empty:
        st.warning("No data found for this ticker.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"${data['Price']}")
    c2.metric("AI Score", data["AI Score"])
    c3.metric("RSI", data["RSI"])
    c4.metric("Signal", data["Signal"])

    st.line_chart(hist["Close"], use_container_width=True)

    modern_section("Technical Snapshot")
    st.dataframe(pd.DataFrame([data]), use_container_width=True, hide_index=True)

    modern_section("AI Trade Plan")
    st.markdown(f"**Suggested Hold Style:** {data.get('Hold Style', 'N/A')}")
    st.markdown(f"**Good Entry Range:** {data.get('Entry Range', 'N/A')}")
    st.markdown(f"**Target / Sell Zone:** {data.get('Target / Sell Zone', 'N/A')}")
    st.markdown(f"**52-Week High:** ${data.get('52W High', 'N/A')}")
    st.markdown(f"**Gap to 52-Week High:** ${data.get('Delta to 52W High $', 'N/A')} / {data.get('Delta to 52W High %', 'N/A')}%")
    st.info(data.get("AI Trade Plan", "No AI trade plan available."))

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
st.sidebar.caption("V26.5 Modern UI")

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
        "Detail View",
    ],
)

st.sidebar.markdown("### Refresh")
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
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
    "Cleaner AI trade guidance with specific buy rationale, entry zones, sell targets, 52-week high gap, and viewer-safe access."
)

st.caption("AI Trade Plans are rules-based research guidance, not financial advice. SMA20/SMA50/SMA200 are used internally for trend analysis, but hidden from the main tables to keep the dashboard cleaner.")

if page == "Dashboard":
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
    c3.metric("Strong Recovery", int((recovery_df["Recovery Score"] >= 75).sum()) if not recovery_df.empty else 0)
    c4.metric("Paper Trades", len(st.session_state.paper_trades))

    modern_section("🟢 Top BUY NOW Signals")
    if scan_df.empty:
        st.info("No scan data available.")
    else:
        buy_now = scan_df[scan_df["Signal"] == "🟢 BUY NOW"].head(10)
        if buy_now.empty:
            st.info("No BUY NOW signals right now.")
        else:
            render_clickable_table(buy_now, "Ticker")

    modern_section("🔥 Top Recovery Radar")
    if recovery_df.empty:
        st.info("No recovery candidates right now.")
    else:
        render_clickable_table(recovery_df.head(10), "Ticker")

    modern_section("⭐ Your Watchlist Snapshot")
    if watch_df.empty:
        st.info("No watchlist data available.")
    else:
        render_clickable_table(watch_df, "Ticker")


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
        render_clickable_table(df, "Ticker")


elif page == "AI Scanner":
    modern_section("🤖 AI Swing Trade Scanner", "Ranks stocks based on trend, momentum, RSI, moving averages, volume, and risk.")
    df = build_scan(CORE_SCAN_TICKERS)
    render_clickable_table(df, "Ticker")


elif page == "BUY NOW":
    modern_section("🟢 BUY NOW Signals", "Highest-conviction setups from the current scan.")
    df = build_scan(CORE_SCAN_TICKERS + st.session_state.watchlist)
    if df.empty:
        st.info("No scan data available.")
    else:
        buy_df = df[df["Signal"] == "🟢 BUY NOW"]
        if buy_df.empty:
            st.info("No BUY NOW signals right now.")
        else:
            render_clickable_table(buy_df, "Ticker")

            with st.expander("📧 BUY NOW Email Alert Preview"):
                body = "AI Trading Dashboard BUY NOW signals:\n\n"
                for _, row in buy_df.iterrows():
                    body += f"{row['Ticker']} | Price: {row['Price']} | AI Score: {row['AI Score']} | RSI: {row['RSI']}\n"
                st.text(body)

                if is_admin():
                    if st.button("Send BUY NOW Email Alert"):
                        ok, msg = send_email_alert("AI Dashboard BUY NOW Alert", body)
                        if ok:
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
        render_clickable_table(recovery_df.head(20), "Ticker")

        strong_recovery = recovery_df[recovery_df["Recovery Score"] >= 75]

        if not strong_recovery.empty:
            st.success(f"🟢 {len(strong_recovery)} strong recovery candidates found.")

            with st.expander("📧 Email Alert Preview - Recovery Radar"):
                alert_text = "AI Recovery Radar found strong rebound candidates:\n\n"
                for _, row in strong_recovery.iterrows():
                    alert_text += (
                        f"{row['Ticker']} | Score: {row['Recovery Score']} | "
                        f"RSI: {row['RSI']} | "
                        f"Upside to 52W High: {row['Upside to 52W High %']}%\n"
                    )
                st.text(alert_text)

                if is_admin():
                    if st.button("Send Recovery Radar Email Alert"):
                        ok, msg = send_email_alert("AI Recovery Radar Alert", alert_text)
                        if ok:
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
        render_clickable_table(etf_df, "ETF")


elif page == "Paper Trading":
    modern_section("🧾 Paper Trading", "Track practice trades before risking real capital.")

    if is_admin():
        c1, c2, c3 = st.columns(3)
        pt_ticker = c1.text_input("Ticker", placeholder="NVDA")
        pt_price = c2.number_input("Entry Price", min_value=0.0, step=0.01)
        pt_qty = c3.number_input("Shares", min_value=0.0, step=1.0)

        if st.button("Add Paper Trade"):
            t = normalize_ticker(pt_ticker)
            if not t or pt_price <= 0 or pt_qty <= 0:
                st.warning("Enter ticker, entry price, and shares.")
            else:
                st.session_state.paper_trades.append({
                    "Ticker": t,
                    "Entry Price": pt_price,
                    "Shares": pt_qty,
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

            rows.append({
                "ID": i,
                "Ticker": ticker,
                "Entry Price": entry,
                "Current Price": current,
                "Shares": shares,
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

    test_body = f"Test email from AI Trading Dashboard V25.5 at {datetime.now(EASTERN).strftime('%Y-%m-%d %I:%M:%S %p ET')}"

    if st.button("Send Test Email"):
        ok, msg = send_email_alert("AI Trading Dashboard Test Email", test_body)
        if ok:
            st.success(msg)
        else:
            st.error(msg)


elif page == "Detail View":
    modern_section("🔎 Mobile Detail View", "Single-stock deep view optimized for quick mobile checks.")
    selected = st.text_input("Enter ticker for detail view", value=st.session_state.watchlist[0] if st.session_state.watchlist else "NVDA")
    if selected:
        detail_page(selected)


st.markdown("---")
st.caption("Not financial advice. Use for research and paper-trading support only.")
