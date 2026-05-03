import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go


st.set_page_config(page_title="AI Trading Dashboard", layout="wide")


# =========================
# LOGIN PROTECTION
# =========================
APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "password")


def login():
    st.title("AI Trading Dashboard Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username == APP_USERNAME and password == APP_PASSWORD:
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("Invalid login")


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
    st.stop()


# =========================
# SETTINGS
# =========================
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVERS = os.getenv("EMAIL_RECEIVERS", "")

DEFAULT_WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META",
    "GOOGL", "TSLA", "AMD", "PLTR", "SNOW",
    "ELF", "COST", "TSM", "AVGO", "QQQ"
]

PORTFOLIO = {
    "NVDA": 100,
    "ELF": 100,
    "GLDY": 1500,
}


# =========================
# DATA FUNCTIONS
# =========================
@st.cache_data(ttl=300)
def get_stock_data(ticker, period="6mo"):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)

        if hist.empty:
            return None

        return hist
    except Exception:
        return None


def calculate_rsi(data, window=14):
    delta = data["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_dip_status(data):
    if data is None or data.empty or len(data) < 50:
        return "Not enough data", "Neutral"

    latest_close = data["Close"].iloc[-1]
    high_20 = data["Close"].tail(20).max()
    high_50 = data["Close"].tail(50).max()

    drop_from_20 = ((latest_close - high_20) / high_20) * 100
    drop_from_50 = ((latest_close - high_50) / high_50) * 100

    rsi = calculate_rsi(data).iloc[-1]

    if drop_from_50 <= -20 and rsi < 35:
        return "Deep Dip", "Strong Opportunity"
    elif drop_from_20 <= -10 and rsi < 40:
        return "Dip", "Possible Opportunity"
    elif drop_from_20 <= -5:
        return "Small Dip", "Watch"
    elif rsi > 70:
        return "Overbought", "Avoid Chasing"
    else:
        return "No Dip", "Neutral"


def get_signal(data):
    if data is None or data.empty or len(data) < 50:
        return "Hold"

    latest = data["Close"].iloc[-1]
    ma20 = data["Close"].rolling(20).mean().iloc[-1]
    ma50 = data["Close"].rolling(50).mean().iloc[-1]
    rsi = calculate_rsi(data).iloc[-1]

    if latest > ma20 > ma50 and rsi < 70:
        return "Buy"
    elif latest < ma20 and rsi > 60:
        return "Sell"
    else:
        return "Hold"


def send_email_alert(subject, body):
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVERS:
        return False

    receivers = [email.strip() for email in EMAIL_RECEIVERS.split(",") if email.strip()]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(receivers)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, receivers, msg.as_string())
        return True
    except Exception:
        return False


def build_scanner(tickers):
    rows = []

    for ticker in tickers:
        data = get_stock_data(ticker)

        if data is None or data.empty or len(data) < 2:
            continue

        latest_price = data["Close"].iloc[-1]
        previous_price = data["Close"].iloc[-2]
        daily_change = ((latest_price - previous_price) / previous_price) * 100

        rsi_series = calculate_rsi(data)
        rsi = rsi_series.iloc[-1] if not rsi_series.empty else None

        signal = get_signal(data)
        dip_status, dip_note = calculate_dip_status(data)

        high_20 = data["Close"].tail(20).max()
        high_50 = data["Close"].tail(50).max()

        drop_from_20 = ((latest_price - high_20) / high_20) * 100
        drop_from_50 = ((latest_price - high_50) / high_50) * 100

        rows.append({
            "Ticker": ticker,
            "Price": round(latest_price, 2),
            "Daily Change %": round(daily_change, 2),
            "RSI": round(rsi, 2) if pd.notna(rsi) else None,
            "Signal": signal,
            "DIP STATUS": dip_status,
            "Dip Note": dip_note,
            "Drop From 20D High %": round(drop_from_20, 2),
            "Drop From 50D High %": round(drop_from_50, 2),
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    signal_rank = {
        "Buy": 1,
        "Hold": 2,
        "Sell": 3,
    }

    dip_rank = {
        "Deep Dip": 1,
        "Dip": 2,
        "Small Dip": 3,
        "No Dip": 4,
        "Overbought": 5,
        "Not enough data": 6,
    }

    df["Signal Rank"] = df["Signal"].map(signal_rank).fillna(9)
    df["Dip Rank"] = df["DIP STATUS"].map(dip_rank).fillna(9)

    df = df.sort_values(
        by=["Dip Rank", "Signal Rank", "Drop From 20D High %"],
        ascending=[True, True, True]
    )

    df = df.drop(columns=["Signal Rank", "Dip Rank"])

    return df.head(15)


# =========================
# UI
# =========================
st.title("AI Trading Dashboard")

with st.sidebar:
    st.header("Controls")

    tickers_input = st.text_area(
        "Watchlist",
        value=", ".join(DEFAULT_WATCHLIST)
    )

    watchlist = [
        ticker.strip().upper()
        for ticker in tickers_input.split(",")
        if ticker.strip()
    ]

    selected_ticker = st.selectbox("Chart Ticker", watchlist)

    chart_period = st.selectbox(
        "Chart Period",
        ["1mo", "3mo", "6mo", "1y", "2y"],
        index=2
    )

    st.divider()

    if st.button("Logout"):
        st.session_state["logged_in"] = False
        st.rerun()


# =========================
# TOP DIP OPPORTUNITIES + SCANNER
# =========================
st.subheader("🔥 Top Dip Opportunities")

scanner_df = build_scanner(watchlist)

if scanner_df.empty:
    st.warning("No scanner data available.")
else:
    best_dips = scanner_df[
        scanner_df["DIP STATUS"].isin(["Deep Dip", "Dip"])
    ].head(5)

    if not best_dips.empty:
        for _, row in best_dips.iterrows():
            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Ticker", row["Ticker"])
            col2.metric("Price", f"${row['Price']}")
            col3.metric("DIP STATUS", row["DIP STATUS"])
            col4.metric("Signal", row["Signal"])

        st.divider()
    else:
        st.info("No strong dip opportunities right now.")

    st.subheader("Top 15 Scanner")

    def highlight_dip(row):
        status = row["DIP STATUS"]

        if status == "Deep Dip":
            return ["background-color: #14532d; color: white"] * len(row)
        elif status == "Dip":
            return ["background-color: #166534; color: white"] * len(row)
        elif status == "Small Dip":
            return ["background-color: #facc15; color: black"] * len(row)
        elif status == "Overbought":
            return ["background-color: #7f1d1d; color: white"] * len(row)
        else:
            return [""] * len(row)

    st.dataframe(
        scanner_df.style.apply(highlight_dip, axis=1),
        use_container_width=True,
        hide_index=True
    )


# =========================
# CHARTS
# =========================
st.subheader(f"{selected_ticker} Chart")

chart_data = get_stock_data(selected_ticker, chart_period)

if chart_data is not None and not chart_data.empty:
    chart_data["MA20"] = chart_data["Close"].rolling(20).mean()
    chart_data["MA50"] = chart_data["Close"].rolling(50).mean()

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=chart_data.index,
        open=chart_data["Open"],
        high=chart_data["High"],
        low=chart_data["Low"],
        close=chart_data["Close"],
        name="Price"
    ))

    fig.add_trace(go.Scatter(
        x=chart_data.index,
        y=chart_data["MA20"],
        mode="lines",
        name="20D MA"
    ))

    fig.add_trace(go.Scatter(
        x=chart_data.index,
        y=chart_data["MA50"],
        mode="lines",
        name="50D MA"
    ))

    fig.update_layout(
        height=550,
        xaxis_rangeslider_visible=False
    )

    st.plotly_chart(fig, use_container_width=True)

    dip_status, dip_note = calculate_dip_status(chart_data)

    col1, col2, col3 = st.columns(3)

    col1.metric("Current Price", f"${chart_data['Close'].iloc[-1]:.2f}")
    col2.metric("DIP STATUS", dip_status)
    col3.metric("Dip Note", dip_note)
else:
    st.warning("No chart data available.")


# =========================
# PORTFOLIO
# =========================
st.subheader("Portfolio")

portfolio_rows = []

for ticker, shares in PORTFOLIO.items():
    data = get_stock_data(ticker)

    if data is None or data.empty:
        continue

    price = data["Close"].iloc[-1]
    value = price * shares
    dip_status, dip_note = calculate_dip_status(data)

    portfolio_rows.append({
        "Ticker": ticker,
        "Shares": shares,
        "Price": round(price, 2),
        "Value": round(value, 2),
        "DIP STATUS": dip_status,
        "Dip Note": dip_note,
    })

portfolio_df = pd.DataFrame(portfolio_rows)

if not portfolio_df.empty:
    total_value = portfolio_df["Value"].sum()

    st.metric("Total Portfolio Value", f"${total_value:,.2f}")
    st.dataframe(portfolio_df, use_container_width=True, hide_index=True)
else:
    st.warning("No portfolio data available.")


# =========================
# SMART ALERTS
# =========================
st.subheader("Smart Alerts - New Dip Opportunities Only")

if "last_dip_states" not in st.session_state:
    st.session_state["last_dip_states"] = {}

alert_rows = []

for ticker in watchlist:
    data = get_stock_data(ticker)

    if data is None or data.empty:
        continue

    signal = get_signal(data)
    dip_status, dip_note = calculate_dip_status(data)

    previous_status = st.session_state["last_dip_states"].get(ticker)

    is_new_dip = (
        dip_status in ["Deep Dip", "Dip"]
        and previous_status not in ["Deep Dip", "Dip"]
    )

    if is_new_dip:
        alert_rows.append({
            "Ticker": ticker,
            "Signal": signal,
            "DIP STATUS": dip_status,
            "Note": dip_note,
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    st.session_state["last_dip_states"][ticker] = dip_status

alert_df = pd.DataFrame(alert_rows)

if not alert_df.empty:
    st.success("🚨 New dip opportunities detected")
    st.dataframe(alert_df, use_container_width=True, hide_index=True)

    if st.button("Send Email Alerts"):
        body = alert_df.to_string(index=False)
        sent = send_email_alert("New Dip Opportunities", body)

        if sent:
            st.success("Alert email sent.")
        else:
            st.warning("Email not sent. Check EMAIL_SENDER, EMAIL_PASSWORD, and EMAIL_RECEIVERS.")
else:
    st.info("No new dip alerts right now.")