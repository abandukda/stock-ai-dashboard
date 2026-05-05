import streamlit as st
import yfinance as yf
import pandas as pd
import os
import json
import plotly.graph_objects as go
import extra_streamlit_components as stx
from datetime import datetime, timedelta

try:
    from streamlit_autorefresh import st_autorefresh
except:
    st_autorefresh = None

st.set_page_config(page_title="AI Trading Dashboard", layout="wide")

if st_autorefresh:
    st_autorefresh(interval=60 * 1000, key="refresh")

cookie_manager = stx.CookieManager()

# =====================
# LOGIN
# =====================
APP_USERNAME = os.getenv("APP_USERNAME", "admin").strip()
APP_PASSWORD_LOGIN = os.getenv("APP_PASSWORD_LOGIN", "admin123").strip()

auth_cookie = cookie_manager.get("auth_v16")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = auth_cookie == "true"

if not st.session_state.logged_in:
    st.title("🔐 Login")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        if u == APP_USERNAME and p == APP_PASSWORD_LOGIN:
            st.session_state.logged_in = True
            cookie_manager.set("auth_v16","true",
                expires_at=datetime.now()+timedelta(days=30))
            st.rerun()
        else:
            st.error("Invalid login")

    st.stop()

st.success("V16 PRO LIVE 🚀")

# =====================
# WATCHLIST (FIXED)
# =====================
def load_watchlist():
    if "wl" in st.session_state:
        return st.session_state.wl

    raw = cookie_manager.get("wl_v16")

    if raw:
        wl = json.loads(raw)
        st.session_state.wl = wl
        return wl

    st.session_state.wl = []
    return []

def save_watchlist(w):
    w = sorted(list(set(w)))
    st.session_state.wl = w

    cookie_manager.set("wl_v16", json.dumps(w),
        expires_at=datetime.now()+timedelta(days=365))

watchlist = load_watchlist()

# =====================
# SIDEBAR
# =====================
st.sidebar.title("⚙️ Controls")

mode = st.sidebar.radio("Mode",
    ["Watchlist","AI Top 15","Combined"])

chart_tf = st.sidebar.selectbox("Chart Timeframe",
    ["1d","5d","1mo","6mo"], index=2)

# =====================
# WATCHLIST UI
# =====================
st.sidebar.header("⭐ Watchlist")

new = st.sidebar.text_input("Add ticker")

if st.sidebar.button("Add"):
    if new:
        watchlist.append(new.upper())
        save_watchlist(watchlist)
        st.rerun()

if watchlist:
    st.sidebar.success(", ".join(watchlist))

# =====================
# AI LIST
# =====================
AI = ["AAPL","MSFT","NVDA","AMZN","META",
"GOOGL","TSLA","AMD","NFLX","AVGO"]

# =====================
# ANALYSIS
# =====================
def analyze(s):
    df = yf.download(s, period="6mo", progress=False)

    if df.empty:
        return None

    price = df["Close"].iloc[-1]
    sma20 = df["Close"].rolling(20).mean().iloc[-1]

    score = 0
    if price > sma20:
        score += 50

    entry = round(price*0.995,2)
    stop = round(price*0.94,2)
    target = round(price*1.1,2)

    rr = round((target-entry)/(entry-stop),2)

    return {
        "Symbol":s,
        "Price":round(price,2),
        "Confidence":score,
        "R/R":rr,
        "Entry":entry,
        "Target":target,
        "Stop":stop
    }

# =====================
# SYMBOLS
# =====================
if mode=="Watchlist":
    syms = watchlist
elif mode=="AI Top 15":
    syms = AI
else:
    syms = list(set(watchlist+AI))

results = []
for s in syms:
    r = analyze(s)
    if r:
        results.append(r)

df = pd.DataFrame(results)

# =====================
# TOP 3 PICKS
# =====================
top3 = df.sort_values("Confidence", ascending=False).head(3)

st.subheader("🏆 Top 3 AI Picks")
st.dataframe(top3)

# =====================
# WATCHLIST TAB
# =====================
st.subheader("⭐ Watchlist")

wdf = df[df["Symbol"].isin(watchlist)]

if not wdf.empty:
    wdf = wdf.sort_values("Confidence", ascending=False)
    st.dataframe(wdf)

    pick = st.selectbox("Select", wdf["Symbol"])
    row = wdf[wdf["Symbol"]==pick].iloc[0]

    st.metric("Confidence", row["Confidence"])
    st.metric("R/R", row["R/R"])

    # CHART
    data = yf.download(pick, period=chart_tf)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data.index, y=data["Close"]))

    fig.add_hline(y=row["Entry"])
    fig.add_hline(y=row["Target"])
    fig.add_hline(y=row["Stop"])

    st.plotly_chart(fig, use_container_width=True)

# =====================
# PRICE ALERT
# =====================
st.subheader("🎯 Price Alerts")

if "alerts" not in st.session_state:
    st.session_state.alerts = []

sym = st.text_input("Ticker for alert")
price = st.number_input("Alert price")

if st.button("Add Alert"):
    st.session_state.alerts.append((sym.upper(),price))

for a in st.session_state.alerts:
    st.write(a)

# =====================
# PORTFOLIO
# =====================
st.subheader("💼 Portfolio")

if "pf" not in st.session_state:
    st.session_state.pf = []

with st.form("pf"):
    s = st.text_input("Symbol")
    buy = st.number_input("Buy Price")
    qty = st.number_input("Shares")

    if st.form_submit_button("Add"):
        st.session_state.pf.append((s.upper(),buy,qty))

total = 0

for s,b,q in st.session_state.pf:
    try:
        price = yf.download(s, period="1d")["Close"].iloc[-1]
        pnl = (price-b)*q
        total += pnl
        st.write(s, round(pnl,2))
    except:
        pass

st.metric("Total P&L", round(total,2))