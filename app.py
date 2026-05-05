import streamlit as st
import yfinance as yf
import pandas as pd
import os
import json
import smtplib
import plotly.graph_objects as go
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
# LOGIN
# =====================
APP_USERNAME = os.getenv("APP_USERNAME", "admin").strip()
APP_PASSWORD_LOGIN = os.getenv("APP_PASSWORD_LOGIN", "admin123").strip()

auth_cookie = cookie_manager.get(cookie="ai_dashboard_auth_v19")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = auth_cookie == "true"

if not st.session_state.logged_in:
    st.title("🔐 AI Trading Dashboard Login")

    username = st.text_input("Username").strip()
    password = st.text_input("Password", type="password").strip()
    remember_me = st.checkbox("Keep me logged in", value=True)

    if st.button("Login"):
        if username == APP_USERNAME and password == APP_PASSWORD_LOGIN:
            st.session_state.logged_in = True

            if remember_me:
                cookie_manager.set(
                    cookie="ai_dashboard_auth_v19",
                    val="true",
                    expires_at=datetime.now() + timedelta(days=30),
                    key="set_auth_cookie_v19"
                )

            st.rerun()
        else:
            st.error("Invalid login")

    st.stop()


# =====================
# VERSION / ENV
# =====================
APP_VERSION = "V19 PRO - TIMING SIGNALS + TRADE ANALYTICS"

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("APP_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")


# =====================
# EXCLUSION RULES
# =====================
EXCLUDED_TICKERS = {
    "JPM", "BAC", "GS", "MS", "C", "WFC", "AIG", "MET", "PRU",
    "AXP", "V", "MA", "COF", "SCHW", "BLK", "BX", "SPGI", "ICE",
    "PYPL", "SQ", "HOOD", "COIN",
    "BUD", "STZ", "TAP", "DEO", "SAM", "BF-B", "BF-A",
    "DKNG", "LVS", "WYNN", "MGM", "PENN", "CZR", "FLUT"
}


def is_excluded_symbol(symbol):
    return str(symbol).strip().upper() in EXCLUDED_TICKERS


def filter_excluded_symbols(symbols):
    return [s for s in symbols if not is_excluded_symbol(s)]


AI_TOP_15 = filter_excluded_symbols([
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "GOOGL", "TSLA", "AMD", "NFLX", "AVGO",
    "COST", "LLY", "UNH", "CRM", "NOW"
])


# =====================
# COOKIE HELPERS
# =====================
def load_cookie_list(cookie_name, session_key):
    if session_key in st.session_state:
        return st.session_state[session_key]

    raw = cookie_manager.get(cookie=cookie_name)

    if raw:
        try:
            data = json.loads(raw)
            st.session_state[session_key] = data
            return data
        except Exception:
            pass

    st.session_state[session_key] = []
    return []


def save_cookie_list(cookie_name, session_key, data):
    st.session_state[session_key] = data
    cookie_manager.set(
        cookie=cookie_name,
        val=json.dumps(data),
        expires_at=datetime.now() + timedelta(days=365),
        key=f"save_{cookie_name}"
    )


def clean_symbols(symbols):
    cleaned = sorted(list(set([str(s).strip().upper() for s in symbols if str(s).strip()])))
    return filter_excluded_symbols(cleaned)


def load_watchlist():
    raw = load_cookie_list("watchlist_v19", "watchlist_v19")
    cleaned = clean_symbols(raw)
    if cleaned != raw:
        save_watchlist(cleaned)
    return cleaned


def save_watchlist(symbols):
    save_cookie_list("watchlist_v19", "watchlist_v19", clean_symbols(symbols))


def load_portfolio():
    raw = load_cookie_list("portfolio_v19", "portfolio_v19")
    return [p for p in raw if not is_excluded_symbol(p.get("Symbol", ""))]


def save_portfolio(portfolio):
    filtered = [p for p in portfolio if not is_excluded_symbol(p.get("Symbol", ""))]
    save_cookie_list("portfolio_v19", "portfolio_v19", filtered)


def load_price_alerts():
    raw = load_cookie_list("price_alerts_v19", "price_alerts_v19")
    return [a for a in raw if not is_excluded_symbol(a.get("Symbol", ""))]


def save_price_alerts(alerts):
    filtered = [a for a in alerts if not is_excluded_symbol(a.get("Symbol", ""))]
    save_cookie_list("price_alerts_v19", "price_alerts_v19", filtered)


def load_journal():
    raw = load_cookie_list("journal_v19", "journal_v19")
    return [j for j in raw if not is_excluded_symbol(j.get("Symbol", ""))]


def save_journal(journal):
    filtered = [j for j in journal if not is_excluded_symbol(j.get("Symbol", ""))]
    save_cookie_list("journal_v19", "journal_v19", filtered)


# =====================
# DATA
# =====================
@st.cache_data(ttl=60)
def get_stock_data(symbol, period="6mo", interval="1d"):
    try:
        data = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True
        )

        if data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data.dropna()
    except Exception:
        return None


def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def send_email_alert(subject, body):
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        return False, "Missing EMAIL_SENDER, APP_PASSWORD, or EMAIL_RECEIVER."

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)

        return True, "Email sent."
    except Exception as e:
        return False, str(e)


# =====================
# MARKET REGIME
# =====================
def get_market_regime():
    data = get_stock_data("SPY", period="1y", interval="1d")

    if data is None or len(data) < 200:
        return "Unknown", "Not enough SPY data available."

    close = data["Close"]
    price = float(close.iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1])

    if price > sma50 > sma200:
        return "Bullish", "SPY is above both 50-day and 200-day moving averages."
    if price > sma200 and price < sma50:
        return "Neutral / Pullback", "SPY is above the 200-day average but below the 50-day average."
    if price < sma200:
        return "Bearish / Risk-Off", "SPY is below the 200-day moving average."

    return "Neutral", "Market trend is mixed."


# =====================
# INTRADAY MOMENTUM + TIMING
# =====================
def get_intraday_momentum(symbol):
    data = get_stock_data(symbol, period="1d", interval="5m")

    if data is None or len(data) < 10:
        return "Unknown", 0, "Not enough intraday data."

    close = data["Close"]
    price = float(close.iloc[-1])
    open_price = float(close.iloc[0])
    recent = float(close.iloc[-6]) if len(close) >= 6 else open_price

    day_change = ((price - open_price) / open_price) * 100 if open_price > 0 else 0
    recent_change = ((price - recent) / recent) * 100 if recent > 0 else 0

    if day_change > 1 and recent_change > 0:
        return "Positive", round(day_change, 2), "Intraday trend is positive."
    if day_change < -1 and recent_change < 0:
        return "Negative", round(day_change, 2), "Intraday trend is weak."
    return "Neutral", round(day_change, 2), "Intraday momentum is mixed."


def make_timing_signal(confidence, rr, near_entry, intraday_status, regime):
    if regime == "Bearish / Risk-Off":
        return "WAIT / SMALL SIZE", "Market is risk-off, so avoid aggressive entries."

    if confidence >= 75 and rr >= 1.8 and near_entry and intraday_status == "Positive":
        return "BUY NOW", "Setup is strong and intraday momentum confirms timing."

    if confidence >= 60 and rr >= 1.5 and near_entry:
        return "READY / WATCH CLOSELY", "Setup is near entry, but wait for stronger momentum confirmation."

    if confidence >= 60 and rr >= 1.5 and not near_entry:
        return "WAIT FOR ENTRY", "Setup is good, but price is not close enough to entry."

    if confidence >= 45:
        return "WAIT", "Setup is mixed and needs more confirmation."

    return "AVOID", "Setup is currently weak."


# =====================
# STOCK ANALYSIS
# =====================
def make_ai_summary(confidence, rr, rsi, volume_ratio, near_entry, regime, timing_signal):
    if timing_signal == "BUY NOW":
        return "Strong setup with supportive timing. Consider position sizing carefully."
    if regime == "Bearish / Risk-Off":
        if confidence >= 70:
            return "Good individual setup, but market is risk-off. Use smaller size or wait."
        return "Market is weak. Be selective and avoid forcing trades."
    if confidence >= 75 and rr >= 1.8 and near_entry:
        return "Strong setup: trend, pullback, risk/reward, and entry timing are close."
    if confidence >= 60 and rr >= 1.5:
        return "Good setup: worth monitoring closely for clean entry confirmation."
    if confidence >= 45:
        return "Mixed setup: some positives, but not enough confirmation yet."
    if rsi > 70:
        return "Avoid for now: RSI appears extended."
    if volume_ratio < 0.8:
        return "Avoid for now: weak volume confirmation."
    return "Weak setup: better opportunities may exist."


def analyze_stock(symbol, regime="Neutral"):
    if is_excluded_symbol(symbol):
        return None

    data = get_stock_data(symbol, period="6mo", interval="1d")

    if data is None or len(data) < 60:
        return None

    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume = data["Volume"]

    price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])

    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    rsi = float(calculate_rsi(close).iloc[-1])

    recent_high = float(high.tail(30).max())
    recent_low = float(low.tail(30).min())

    avg_volume = float(volume.tail(20).mean())
    current_volume = float(volume.iloc[-1])
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

    dip_pct = ((recent_high - price) / recent_high) * 100
    recovery_pct = ((price - recent_low) / recent_low) * 100

    score = 0
    reasons = []

    if price > sma20:
        score += 15
        reasons.append("Price is above 20-day moving average")
    else:
        reasons.append("Price is below 20-day moving average")

    if price > sma50:
        score += 15
        reasons.append("Price is above 50-day moving average")
    else:
        reasons.append("Price is below 50-day moving average")

    if sma20 > sma50:
        score += 10
        reasons.append("20-day moving average is above 50-day moving average")
    else:
        reasons.append("20-day moving average is not above 50-day moving average")

    if 3 <= dip_pct <= 12:
        score += 20
        reasons.append("Healthy pullback from recent high")
    elif 12 < dip_pct <= 25:
        score += 10
        reasons.append("Large dip, possible rebound setup")
    else:
        reasons.append("Dip is either too small or too deep")

    if 35 <= rsi <= 55:
        score += 20
        reasons.append("RSI is in attractive entry range")
    elif 55 < rsi <= 65:
        score += 10
        reasons.append("RSI is acceptable but getting stronger")
    elif rsi < 35:
        score += 15
        reasons.append("RSI is oversold")
    else:
        reasons.append("RSI may be extended")

    if volume_ratio >= 1.2:
        score += 15
        reasons.append("Volume confirmation is strong")
    elif volume_ratio >= 0.9:
        score += 8
        reasons.append("Volume is normal")
    else:
        reasons.append("Volume confirmation is weak")

    if price > prev_price:
        score += 10
        reasons.append("Positive price momentum")
    else:
        reasons.append("Price momentum is weak")

    if regime == "Bullish":
        score += 5
        reasons.append("Market regime is supportive")
    elif regime == "Bearish / Risk-Off":
        score -= 10
        reasons.append("Market regime is risk-off")

    intraday_status, intraday_change, intraday_reason = get_intraday_momentum(symbol)

    if intraday_status == "Positive":
        score += 5
        reasons.append("Intraday momentum is positive")
    elif intraday_status == "Negative":
        score -= 5
        reasons.append("Intraday momentum is weak")

    confidence = max(0, min(score, 100))

    entry = round(price * 0.995, 2)
    stop = round(price * 0.94, 2)
    target = round(price * 1.10, 2)

    risk = entry - stop
    reward = target - entry
    rr = round(reward / risk, 2) if risk > 0 else 0

    near_entry = abs(price - entry) / entry <= 0.015
    actionable = confidence >= 60 and rr >= 1.5 and near_entry

    timing_signal, timing_reason = make_timing_signal(
        confidence,
        rr,
        near_entry,
        intraday_status,
        regime
    )

    if timing_signal == "BUY NOW":
        action = "BUY / STRONG SETUP"
    elif confidence >= 60 and rr >= 1.5:
        action = "WATCH / POSSIBLE ENTRY"
    elif confidence >= 45:
        action = "WAIT"
    else:
        action = "AVOID"

    ai_summary = make_ai_summary(
        confidence,
        rr,
        rsi,
        volume_ratio,
        near_entry,
        regime,
        timing_signal
    )

    return {
        "Symbol": symbol,
        "Price": round(price, 2),
        "Entry": entry,
        "Target": target,
        "Stop": stop,
        "R/R": rr,
        "Confidence": confidence,
        "RSI": round(rsi, 1),
        "Dip %": round(dip_pct, 2),
        "Recovery %": round(recovery_pct, 2),
        "Volume Ratio": round(volume_ratio, 2),
        "Intraday": intraday_status,
        "Intraday %": intraday_change,
        "Timing Signal": timing_signal,
        "Timing Reason": timing_reason,
        "Near Entry": near_entry,
        "Actionable": actionable,
        "AI Action": action,
        "AI Summary": ai_summary,
        "Score Reasons": " | ".join(reasons),
        "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def position_size(capital, max_loss, entry, stop):
    risk_per_share = entry - stop

    if risk_per_share <= 0:
        return 0, 0, 0

    shares = int(max_loss / risk_per_share)
    capital_needed = shares * entry

    if capital_needed > capital:
        shares = int(capital / entry)
        capital_needed = shares * entry

    actual_loss = shares * risk_per_share
    return shares, round(capital_needed, 2), round(actual_loss, 2)


def make_chart(symbol, row, period):
    interval = "5m" if period in ["1d", "5d"] else "1d"
    data = get_stock_data(symbol, period=period, interval=interval)

    if data is None or data.empty:
        st.warning("Chart data unavailable.")
        return

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data["Open"],
        high=data["High"],
        low=data["Low"],
        close=data["Close"],
        name=symbol
    ))

    fig.add_hline(y=row["Entry"], line_dash="dot", annotation_text="Entry")
    fig.add_hline(y=row["Target"], line_dash="dot", annotation_text="Target")
    fig.add_hline(y=row["Stop"], line_dash="dot", annotation_text="Stop")

    fig.update_layout(
        height=520,
        xaxis_rangeslider_visible=False,
        title=f"{symbol} Chart"
    )

    st.plotly_chart(fig, use_container_width=True)


# =====================
# SIDEBAR
# =====================
st.sidebar.title("⚙️ Dashboard Settings")

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    cookie_manager.delete(cookie="ai_dashboard_auth_v19", key="delete_auth_cookie_v19")
    st.rerun()

capital = st.sidebar.number_input("Trading Capital ($)", value=5000, step=500)
max_loss = st.sidebar.number_input("Risk Budget Per Trade ($)", value=500, step=50)

scan_mode = st.sidebar.radio(
    "Scan Mode",
    ["Personal Watchlist Only", "AI Top 15 Only", "Personal Watchlist + AI Top 15"]
)

chart_period = st.sidebar.selectbox("Chart Period", ["1d", "5d", "1mo", "3mo", "6mo", "1y"], index=4)

enable_email_alerts = st.sidebar.checkbox("Enable Email Alerts", value=True)
personal_alerts_only = st.sidebar.checkbox("Alerts only for Personal Watchlist", value=True)

if st.sidebar.button("🔄 Manual Refresh"):
    st.cache_data.clear()
    st.rerun()


# =====================
# WATCHLIST
# =====================
st.sidebar.divider()
st.sidebar.header("⭐ PERSONAL WATCHLIST")
st.sidebar.caption("Financial, alcohol, and gambling tickers are blocked.")

watchlist = load_watchlist()
new_symbol = st.sidebar.text_input("Add ticker", placeholder="Example: NVDA")

if st.sidebar.button("➕ Add Ticker"):
    symbol_to_add = new_symbol.strip().upper()

    if not symbol_to_add:
        st.sidebar.warning("Enter a ticker.")
    elif is_excluded_symbol(symbol_to_add):
        st.sidebar.error(f"{symbol_to_add} is blocked by your exclusion rules.")
    else:
        watchlist = clean_symbols(watchlist + [symbol_to_add])
        save_watchlist(watchlist)
        st.sidebar.success(f"Added {symbol_to_add}")
        st.rerun()

if watchlist:
    st.sidebar.success(", ".join(watchlist))

    remove_symbol = st.sidebar.selectbox("Remove ticker", [""] + watchlist)

    if st.sidebar.button("🗑️ Remove Ticker"):
        if remove_symbol:
            watchlist = [s for s in watchlist if s != remove_symbol]
            save_watchlist(watchlist)
            st.rerun()

    if st.sidebar.button("🧹 Clear Watchlist"):
        save_watchlist([])
        st.rerun()
else:
    st.sidebar.info("No personal tickers yet.")


# =====================
# HEADER
# =====================
st.title("📈 AI Trading Dashboard")
st.success(APP_VERSION)
st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

regime, regime_reason = get_market_regime()


# =====================
# SYMBOL LIST
# =====================
if scan_mode == "Personal Watchlist Only":
    symbols = watchlist
elif scan_mode == "AI Top 15 Only":
    symbols = AI_TOP_15
else:
    symbols = clean_symbols(watchlist + AI_TOP_15)

symbols = filter_excluded_symbols(symbols)

if not symbols:
    st.info("Your Personal Watchlist is empty. Add a non-excluded ticker from the sidebar.")
    st.stop()


# =====================
# SCAN
# =====================
results = []

with st.spinner("Scanning stocks..."):
    for symbol in symbols:
        result = analyze_stock(symbol, regime=regime)

        if result:
            shares, capital_needed, actual_loss = position_size(
                capital,
                max_loss,
                result["Entry"],
                result["Stop"]
            )

            result["Shares"] = shares
            result["Capital Needed"] = capital_needed
            result["Max Loss"] = actual_loss
            result["List Type"] = "Personal Watchlist" if symbol in watchlist else "AI Top 15"

            results.append(result)

df = pd.DataFrame(results)

if df.empty:
    st.warning("No stock data found. Check ticker symbols.")
    st.stop()


# =====================
# ALERTS
# =====================
def check_ai_alert(row):
    sent_log = load_cookie_list("sent_ai_alerts_v19", "sent_ai_alerts_v19")
    now = datetime.now()
    symbol = row["Symbol"]

    latest_for_symbol = [x for x in sent_log if x.get("Symbol") == symbol]

    if latest_for_symbol:
        last_time = datetime.strptime(latest_for_symbol[-1]["Time"], "%Y-%m-%d %H:%M:%S")
        if now - last_time < timedelta(hours=1):
            return

    subject = f"🚨 AI Trading Alert: {symbol}"

    body = f"""
Symbol: {symbol}
Price: {row['Price']}
Entry: {row['Entry']}
Target: {row['Target']}
Stop: {row['Stop']}
Confidence: {row['Confidence']}
Risk/Reward: {row['R/R']}
Timing Signal: {row['Timing Signal']}
AI Action: {row['AI Action']}

AI Summary:
{row['AI Summary']}

Time:
{now.strftime('%Y-%m-%d %H:%M:%S')}
"""

    send_email_alert(subject, body)

    sent_log.append({
        "Time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "Symbol": symbol,
        "Price": row["Price"],
        "Confidence": row["Confidence"],
        "Timing Signal": row["Timing Signal"],
        "AI Action": row["AI Action"]
    })

    save_cookie_list("sent_ai_alerts_v19", "sent_ai_alerts_v19", sent_log)


def check_price_alerts(current_df):
    alerts = load_price_alerts()
    updated_alerts = []

    for alert in alerts:
        symbol = alert.get("Symbol")

        if is_excluded_symbol(symbol):
            continue

        target_price = float(alert.get("Target Price", 0))
        direction = alert.get("Direction", "Above")
        triggered = alert.get("Triggered", False)

        row_df = current_df[current_df["Symbol"] == symbol]

        if row_df.empty:
            updated_alerts.append(alert)
            continue

        current_price = float(row_df.iloc[0]["Price"])

        is_triggered = (
            current_price >= target_price if direction == "Above"
            else current_price <= target_price
        )

        if is_triggered and not triggered and enable_email_alerts:
            subject = f"🎯 Price Alert Triggered: {symbol}"
            body = f"""
Price alert triggered.

Symbol: {symbol}
Current Price: {current_price}
Target Price: {target_price}
Direction: {direction}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            send_email_alert(subject, body)
            alert["Triggered"] = True

        updated_alerts.append(alert)

    save_price_alerts(updated_alerts)


if enable_email_alerts:
    actionable_df = df[df["Actionable"] == True]

    if personal_alerts_only:
        actionable_df = actionable_df[actionable_df["Symbol"].isin(watchlist)]

    for _, row in actionable_df.iterrows():
        check_ai_alert(row)

    check_price_alerts(df)


# =====================
# PORTFOLIO SUMMARY
# =====================
def portfolio_summary():
    portfolio = load_portfolio()
    rows = []
    total_value = 0
    total_cost = 0
    total_pnl = 0

    for pos in portfolio:
        symbol = pos["Symbol"]

        if is_excluded_symbol(symbol):
            continue

        buy_price = float(pos["Buy Price"])
        shares = float(pos["Shares"])

        data = get_stock_data(symbol, period="5d", interval="1d")

        if data is None or data.empty:
            continue

        current_price = float(data["Close"].iloc[-1])
        cost = buy_price * shares
        value = current_price * shares
        pnl = value - cost
        pnl_pct = (pnl / cost) * 100 if cost > 0 else 0

        total_cost += cost
        total_value += value
        total_pnl += pnl

        rows.append({
            "Symbol": symbol,
            "Buy Price": round(buy_price, 2),
            "Current Price": round(current_price, 2),
            "Shares": shares,
            "Cost": round(cost, 2),
            "Value": round(value, 2),
            "P/L": round(pnl, 2),
            "P/L %": round(pnl_pct, 2)
        })

    return rows, total_value, total_cost, total_pnl


def trade_analytics():
    journal = load_journal()
    if not journal:
        return 0, 0, 0, 0, pd.DataFrame()

    jdf = pd.DataFrame(journal)
    closed = jdf[jdf["Result"] != "Open"] if "Result" in jdf.columns else pd.DataFrame()
    total_pnl = jdf["P/L"].sum() if "P/L" in jdf.columns else 0

    wins = len(closed[closed["Result"] == "Win"]) if not closed.empty else 0
    losses = len(closed[closed["Result"] == "Loss"]) if not closed.empty else 0
    total_closed = len(closed)
    win_rate = round((wins / total_closed) * 100, 2) if total_closed > 0 else 0

    return total_pnl, wins, losses, win_rate, jdf


portfolio_rows, total_value, total_cost, total_pnl = portfolio_summary()
journal_pnl, journal_wins, journal_losses, journal_win_rate, journal_df = trade_analytics()


# =====================
# TOP STRIP
# =====================
actionable_count = len(df[df["Actionable"] == True])
buy_now_count = len(df[df["Timing Signal"] == "BUY NOW"])
top_pick = df.sort_values(["Confidence", "R/R"], ascending=False).iloc[0]

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Market Regime", regime)
m2.metric("Top Pick", top_pick["Symbol"])
m3.metric("Buy Now Signals", buy_now_count)
m4.metric("Actionable", actionable_count)
m5.metric("Portfolio P/L", f"${total_pnl:,.2f}")

st.info(regime_reason)

st.divider()


# =====================
# TOP PICKS
# =====================
st.subheader("🏆 Top 3 AI Picks Today")

top3 = df.sort_values(["Confidence", "R/R"], ascending=False).head(3)
st.dataframe(top3, use_container_width=True)

best = top3.iloc[0]
st.markdown(f"### Best Setup: {best['Symbol']} — {best['Timing Signal']}")
st.info(best["AI Summary"])

st.divider()


# =====================
# PERSONAL WATCHLIST
# =====================
st.subheader("⭐ Personal Watchlist Decision Center")

watch_df = df[df["Symbol"].isin(watchlist)].sort_values(
    ["Timing Signal", "Confidence", "R/R"],
    ascending=[True, False, False]
)

if watch_df.empty:
    st.info("Add non-excluded stocks to your personal watchlist from the sidebar.")
else:
    st.dataframe(watch_df, use_container_width=True)

    selected = st.selectbox("Select stock to analyze", watch_df["Symbol"].tolist())
    row = watch_df[watch_df["Symbol"] == selected].iloc[0]

    st.markdown(f"## {selected} — {row['Timing Signal']}")
    st.info(row["Timing Reason"])
    st.write(row["AI Summary"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", row["Price"])
    c2.metric("Confidence", row["Confidence"])
    c3.metric("R/R", row["R/R"])
    c4.metric("Intraday", row["Intraday"], f"{row['Intraday %']}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Entry", row["Entry"])
    c6.metric("Target", row["Target"])
    c7.metric("Stop", row["Stop"])
    c8.metric("Max Loss", f"${row['Max Loss']:,.2f}")

    st.markdown("### Auto Position Sizing")
    st.write(
        f"Suggested shares: **{row['Shares']}** | "
        f"Capital needed: **${row['Capital Needed']:,.2f}** | "
        f"Max loss: **${row['Max Loss']:,.2f}**"
    )

    st.markdown("### 📈 Chart")
    make_chart(selected, row, chart_period)

    with st.expander("Why AI scored it this way"):
        for reason in row["Score Reasons"].split(" | "):
            st.write(f"- {reason}")

st.divider()


# =====================
# SCANNER OUTPUT
# =====================
st.subheader("🔥 Scanner Output")

actionable = df[df["Actionable"] == True].sort_values("Confidence", ascending=False)
buy_now = df[df["Timing Signal"] == "BUY NOW"].sort_values("Confidence", ascending=False)
watch = df[(df["Timing Signal"].str.contains("WAIT|READY", regex=True))].sort_values("Confidence", ascending=False)
avoid = df[df["Timing Signal"] == "AVOID"].sort_values("Confidence", ascending=True)

with st.expander("🚀 Buy Now", expanded=True):
    st.dataframe(buy_now, use_container_width=True)

with st.expander("✅ Actionable", expanded=True):
    st.dataframe(actionable, use_container_width=True)

with st.expander("👀 Ready / Wait", expanded=True):
    st.dataframe(watch, use_container_width=True)

with st.expander("⚠️ Avoid", expanded=False):
    st.dataframe(avoid, use_container_width=True)

st.divider()


# =====================
# PRICE ALERTS
# =====================
st.subheader("🎯 Price Alerts")

alerts = load_price_alerts()

with st.form("price_alert_form"):
    a1, a2, a3 = st.columns(3)
    alert_symbol = a1.text_input("Ticker").upper()
    alert_price = a2.number_input("Target Price", value=0.0)
    direction = a3.selectbox("Direction", ["Above", "Below"])
    submit_alert = st.form_submit_button("Add Price Alert")

    if submit_alert:
        if not alert_symbol:
            st.warning("Enter a ticker.")
        elif is_excluded_symbol(alert_symbol):
            st.error(f"{alert_symbol} is blocked by your exclusion rules.")
        elif alert_price <= 0:
            st.warning("Enter a valid target price.")
        else:
            alerts.append({
                "Symbol": alert_symbol,
                "Target Price": alert_price,
                "Direction": direction,
                "Triggered": False,
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            save_price_alerts(alerts)
            st.success("Price alert added.")
            st.rerun()

if alerts:
    st.dataframe(pd.DataFrame(alerts), use_container_width=True)

    if st.button("Clear All Price Alerts"):
        save_price_alerts([])
        st.rerun()
else:
    st.info("No price alerts yet.")

st.divider()


# =====================
# PORTFOLIO
# =====================
st.subheader("💼 Portfolio Tracker")

portfolio = load_portfolio()

with st.form("portfolio_form"):
    p1, p2, p3 = st.columns(3)
    p_symbol = p1.text_input("Symbol").upper()
    p_buy = p2.number_input("Buy Price", value=0.0)
    p_qty = p3.number_input("Shares", value=0.0)
    p_submit = st.form_submit_button("Add Position")

    if p_submit:
        if not p_symbol:
            st.warning("Enter a ticker.")
        elif is_excluded_symbol(p_symbol):
            st.error(f"{p_symbol} is blocked by your exclusion rules.")
        elif p_buy <= 0 or p_qty <= 0:
            st.warning("Enter valid buy price and shares.")
        else:
            portfolio.append({
                "Symbol": p_symbol,
                "Buy Price": p_buy,
                "Shares": p_qty,
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            save_portfolio(portfolio)
            st.success("Position added.")
            st.rerun()

if portfolio_rows:
    p1, p2, p3 = st.columns(3)
    p1.metric("Portfolio Value", f"${total_value:,.2f}")
    p2.metric("Total Cost", f"${total_cost:,.2f}")
    p3.metric("Total P/L", f"${total_pnl:,.2f}")

    st.dataframe(pd.DataFrame(portfolio_rows), use_container_width=True)

    if st.button("Clear Portfolio"):
        save_portfolio([])
        st.rerun()
else:
    st.info("No portfolio positions yet.")

st.divider()


# =====================
# TRADE ANALYTICS + JOURNAL
# =====================
with st.expander("📈 Trade Performance Analytics", expanded=True):
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Journal P/L", f"${journal_pnl:,.2f}")
    a2.metric("Wins", journal_wins)
    a3.metric("Losses", journal_losses)
    a4.metric("Win Rate", f"{journal_win_rate}%")

with st.expander("📓 Trade Journal", expanded=False):
    journal = load_journal()

    with st.form("journal_form"):
        j1, j2, j3 = st.columns(3)
        j_symbol = j1.text_input("Trade Symbol").upper()
        j_entry = j2.number_input("Entry", value=0.0)
        j_exit = j3.number_input("Exit", value=0.0)
        j_shares = j1.number_input("Trade Shares", value=0.0)
        j_result = j2.selectbox("Result", ["Open", "Win", "Loss", "Breakeven"])
        j_notes = j3.text_input("Notes")
        j_submit = st.form_submit_button("Add Trade")

        if j_submit:
            if not j_symbol:
                st.warning("Enter a ticker.")
            elif is_excluded_symbol(j_symbol):
                st.error(f"{j_symbol} is blocked by your exclusion rules.")
            else:
                pnl = round((j_exit - j_entry) * j_shares, 2) if j_exit > 0 else 0
                journal.append({
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Symbol": j_symbol,
                    "Entry": j_entry,
                    "Exit": j_exit,
                    "Shares": j_shares,
                    "Result": j_result,
                    "P/L": pnl,
                    "Notes": j_notes
                })
                save_journal(journal)
                st.rerun()

    if journal:
        st.dataframe(pd.DataFrame(journal), use_container_width=True)

        if st.button("Clear Trade Journal"):
            save_journal([])
            st.rerun()
    else:
        st.info("No trades logged yet.")


# =====================
# AI TOP 15 / FULL SCANNER / CHEAT SHEET
# =====================
with st.expander("🤖 AI Top 15 Scanner", expanded=False):
    ai_df = df[df["Symbol"].isin(AI_TOP_15)].sort_values(["Confidence", "R/R"], ascending=False)
    st.dataframe(ai_df, use_container_width=True)

with st.expander("📊 Full Scanner Filters", expanded=False):
    min_confidence = st.slider("Minimum Confidence", 0, 100, 50)
    min_rr = st.slider("Minimum R/R", 0.0, 5.0, 1.0, 0.1)

    filtered = df[(df["Confidence"] >= min_confidence) & (df["R/R"] >= min_rr)]
    st.dataframe(filtered, use_container_width=True)

with st.expander("📚 Cheat Sheet", expanded=False):
    st.markdown("""
### V19 Timing Signal
- **BUY NOW**: setup + risk/reward + entry + intraday momentum align
- **READY / WATCH CLOSELY**: setup is near entry but needs confirmation
- **WAIT FOR ENTRY**: setup is good but price is not near ideal entry
- **WAIT**: mixed setup
- **AVOID**: weak setup

### Exclusions
Financial, alcohol, and gambling tickers are blocked everywhere.

### Position Sizing
The dashboard estimates shares, capital needed, and max loss using your sidebar risk budget.
""")