import streamlit as st
import yfinance as yf
import pandas as pd
import os
import json
import smtplib
import extra_streamlit_components as stx
from email.mime.text import MIMEText
from datetime import datetime, timedelta

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

st.set_page_config(page_title="AI Trading Dashboard", page_icon="📈", layout="wide")

if st_autorefresh:
    st_autorefresh(interval=60 * 1000, key="refresh")

cookie_manager = stx.CookieManager()

# =====================
# LOGIN (FIXED + DEBUG)
# =====================
APP_USERNAME = os.getenv("APP_USERNAME", "admin").strip()
APP_PASSWORD_LOGIN = os.getenv("APP_PASSWORD_LOGIN", "admin123").strip()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 AI Trading Dashboard Login")

    # DEBUG INFO
    st.warning("DEBUG LOGIN CHECK")
    st.write("Env Username:", APP_USERNAME)
    st.write("Env Password Length:", len(APP_PASSWORD_LOGIN))

    username = st.text_input("Username").strip()
    password = st.text_input("Password", type="password").strip()

    if st.button("Login"):
        if username == APP_USERNAME and password == APP_PASSWORD_LOGIN:
            st.session_state.logged_in = True

            cookie_manager.set(
                cookie="auth",
                val="true",
                expires_at=datetime.now() + timedelta(days=30),
                key="auth_cookie"
            )

            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid login")
            st.write("Typed username:", username)
            st.write("Typed password length:", len(password))

    st.stop()

# =====================
# APP VERSION
# =====================
st.success("V12 LOGIN FIX + PERSONAL WATCHLIST WORKING")

# =====================
# SETTINGS
# =====================
AI_TOP_15 = [
    "AAPL","MSFT","NVDA","AMZN","META",
    "GOOGL","TSLA","AMD","NFLX","AVGO",
    "COST","LLY","JPM","V","UNH"
]

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("APP_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# =====================
# WATCHLIST COOKIE
# =====================
def load_watchlist():
    raw = cookie_manager.get(cookie="watchlist_v12")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except:
        return []

def save_watchlist(lst):
    cookie_manager.set(
        cookie="watchlist_v12",
        val=json.dumps(lst),
        expires_at=datetime.now() + timedelta(days=365),
        key="watchlist_save"
    )

watchlist = load_watchlist()

# =====================
# SIDEBAR
# =====================
st.sidebar.title("⚙️ Controls")

capital = st.sidebar.number_input("Capital", value=5000)
risk = st.sidebar.number_input("Risk per trade", value=100)

scan_mode = st.sidebar.radio("Scan Mode", [
    "Personal Watchlist",
    "AI Top 15",
    "Combined"
])

# WATCHLIST UI
st.sidebar.divider()
st.sidebar.header("⭐ Personal Watchlist")

new_symbol = st.sidebar.text_input("Add ticker")

if st.sidebar.button("Add"):
    if new_symbol:
        watchlist.append(new_symbol.upper())
        watchlist = list(set(watchlist))
        save_watchlist(watchlist)
        st.sidebar.success("Added")
        st.rerun()

if watchlist:
    st.sidebar.write(", ".join(watchlist))

    remove = st.sidebar.selectbox("Remove", [""] + watchlist)

    if st.sidebar.button("Remove"):
        if remove:
            watchlist = [x for x in watchlist if x != remove]
            save_watchlist(watchlist)
            st.sidebar.warning("Removed")
            st.rerun()

else:
    st.sidebar.info("No personal watchlist yet")

# =====================
# STOCK ANALYSIS
# =====================
def analyze(symbol):
    data = yf.download(symbol, period="6mo", progress=False)

    if data.empty:
        return None

    price = data["Close"].iloc[-1]
    sma20 = data["Close"].rolling(20).mean().iloc[-1]
    sma50 = data["Close"].rolling(50).mean().iloc[-1]

    score = 0
    reasons = []

    if price > sma20:
        score += 20
        reasons.append("Above SMA20")

    if price > sma50:
        score += 20
        reasons.append("Above SMA50")

    confidence = min(score, 100)

    entry = round(price * 0.995, 2)
    stop = round(price * 0.95, 2)
    target = round(price * 1.1, 2)

    rr = round((target - entry) / (entry - stop), 2)

    return {
        "Symbol": symbol,
        "Price": round(price, 2),
        "Confidence": confidence,
        "R/R": rr,
        "Entry": entry,
        "Target": target,
        "Stop": stop,
        "Reasons": ", ".join(reasons)
    }

# =====================
# SYMBOL LIST
# =====================
if scan_mode == "Personal Watchlist":
    symbols = watchlist
elif scan_mode == "AI Top 15":
    symbols = AI_TOP_15
else:
    symbols = list(set(watchlist + AI_TOP_15))

if not symbols:
    st.warning("No symbols to scan")
    st.stop()

# =====================
# RUN SCAN
# =====================
results = []

for s in symbols:
    r = analyze(s)
    if r:
        results.append(r)

df = pd.DataFrame(results)

# =====================
# DISPLAY
# =====================
tab1, tab2 = st.tabs(["⭐ Watchlist", "🤖 AI Scanner"])

with tab1:
    st.subheader("Your Personal Watchlist")

    personal_df = df[df["Symbol"].isin(watchlist)]

    if personal_df.empty:
        st.info("Add stocks to watchlist")
    else:
        st.dataframe(personal_df)

with tab2:
    st.subheader("AI Top 15")

    ai_df = df[df["Symbol"].isin(AI_TOP_15)]
    st.dataframe(ai_df)