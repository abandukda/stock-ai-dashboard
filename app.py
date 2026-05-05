import streamlit as st
import yfinance as yf
import pandas as pd
import os
import json
import plotly.graph_objects as go
import extra_streamlit_components as stx
from datetime import datetime, timedelta

from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="AI Trading Dashboard", layout="wide")

st_autorefresh(interval=60 * 1000, key="refresh")

cookie_manager = stx.CookieManager()

# =====================
# LOGIN
# =====================
APP_USERNAME = os.getenv("APP_USERNAME", "admin").strip()
APP_PASSWORD_LOGIN = os.getenv("APP_PASSWORD_LOGIN", "admin123").strip()

auth_cookie = cookie_manager.get(cookie="auth_v14")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = auth_cookie == "true"

if not st.session_state.logged_in:
    st.title("🔐 Login")

    u = st.text_input("Username").strip()
    p = st.text_input("Password", type="password").strip()

    if st.button("Login"):
        if u == APP_USERNAME and p == APP_PASSWORD_LOGIN:
            st.session_state.logged_in = True
            cookie_manager.set("auth_v14", "true",
                expires_at=datetime.now() + timedelta(days=30))
            st.rerun()
        else:
            st.error("Invalid login")

    st.stop()

# =====================
# VERSION
# =====================
st.success("V14 PRO DASHBOARD LIVE")

# =====================
# WATCHLIST COOKIE
# =====================
def load_watchlist():
    raw = cookie_manager.get("watchlist_v14")
    if not raw:
        return []
    return json.loads(raw)

def save_watchlist(w):
    cookie_manager.set("watchlist_v14", json.dumps(w),
        expires_at=datetime.now() + timedelta(days=365))

watchlist = load_watchlist()

# =====================
# SIDEBAR
# =====================
st.sidebar.title("⚙️ Controls")

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    cookie_manager.delete("auth_v14")
    st.rerun()

capital = st.sidebar.number_input("Capital", 5000)
risk = st.sidebar.number_input("Risk per trade", 100)

mode = st.sidebar.radio("Scan Mode",
    ["Watchlist", "AI Top 15", "Combined"])

AI_TOP_15 = [
"AAPL","MSFT","NVDA","AMZN","META",
"GOOGL","TSLA","AMD","NFLX","AVGO",
"COST","LLY","JPM","V","UNH"
]

# =====================
# WATCHLIST UI
# =====================
st.sidebar.divider()
st.sidebar.header("⭐ Personal Watchlist")

new = st.sidebar.text_input("Add ticker")

if st.sidebar.button("Add"):
    if new:
        watchlist.append(new.upper())
        watchlist = list(set(watchlist))
        save_watchlist(watchlist)
        st.rerun()

if watchlist:
    st.sidebar.success(", ".join(watchlist))

    rem = st.sidebar.selectbox("Remove", [""] + watchlist)
    if st.sidebar.button("Remove"):
        if rem:
            watchlist = [x for x in watchlist if x != rem]
            save_watchlist(watchlist)
            st.rerun()

else:
    st.sidebar.info("Add stocks")

# =====================
# ANALYSIS
# =====================
def analyze(symbol):
    df = yf.download(symbol, period="6mo", progress=False)

    if df.empty:
        return None

    price = df["Close"].iloc[-1]
    sma20 = df["Close"].rolling(20).mean().iloc[-1]
    sma50 = df["Close"].rolling(50).mean().iloc[-1]

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
    stop = round(price * 0.94, 2)
    target = round(price * 1.1, 2)

    rr = round((target - entry) / (entry - stop), 2)

    # AI summary
    if confidence >= 60 and rr >= 1.5:
        summary = "Strong trend + good risk/reward"
    elif confidence >= 40:
        summary = "Setup forming, wait"
    else:
        summary = "Weak setup, avoid"

    return {
        "Symbol": symbol,
        "Price": round(price,2),
        "Confidence": confidence,
        "R/R": rr,
        "Entry": entry,
        "Target": target,
        "Stop": stop,
        "Summary": summary
    }

# =====================
# SYMBOLS
# =====================
if mode == "Watchlist":
    symbols = watchlist
elif mode == "AI Top 15":
    symbols = AI_TOP_15
else:
    symbols = list(set(watchlist + AI_TOP_15))

if not symbols:
    st.warning("No symbols")
    st.stop()

results = []
for s in symbols:
    r = analyze(s)
    if r:
        results.append(r)

df = pd.DataFrame(results)

# =====================
# TABS
# =====================
t1, t2, t3 = st.tabs(["⭐ Watchlist","🤖 AI","📓 Journal"])

# =====================
# WATCHLIST TAB
# =====================
with t1:
    st.subheader("Your Watchlist")

    wdf = df[df["Symbol"].isin(watchlist)]

    if wdf.empty:
        st.info("Add stocks")
    else:
        st.dataframe(wdf)

        pick = st.selectbox("Select stock", wdf["Symbol"])
        row = wdf[wdf["Symbol"]==pick].iloc[0]

        st.metric("Confidence", row["Confidence"])
        st.metric("R/R", row["R/R"])

        st.write("🧠", row["Summary"])

        # CHART
        data = yf.download(pick, period="6mo")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=data.index, y=data["Close"],
            name="Price"))

        fig.add_hline(y=row["Entry"], line_dash="dot")
        fig.add_hline(y=row["Target"], line_dash="dot")
        fig.add_hline(y=row["Stop"], line_dash="dot")

        st.plotly_chart(fig, use_container_width=True)

# =====================
# AI TAB
# =====================
with t2:
    st.subheader("AI Scanner")
    st.dataframe(df)

# =====================
# JOURNAL
# =====================
with t3:
    st.subheader("Trade Journal")

    if "journal" not in st.session_state:
        st.session_state.journal = []

    with st.form("trade"):
        sym = st.text_input("Symbol")
        entry = st.number_input("Entry")
        exit = st.number_input("Exit")
        shares = st.number_input("Shares")

        sub = st.form_submit_button("Add")

        if sub:
            pnl = (exit-entry)*shares
            st.session_state.journal.append(
                {"Symbol":sym,"P/L":pnl}
            )

    if st.session_state.journal:
        jdf = pd.DataFrame(st.session_state.journal)

        st.dataframe(jdf)

        st.metric("Total P/L", jdf["P/L"].sum())