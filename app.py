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

auth_cookie = cookie_manager.get(cookie="ai_dashboard_auth_v17")

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
                    cookie="ai_dashboard_auth_v17",
                    val="true",
                    expires_at=datetime.now() + timedelta(days=30),
                    key="set_auth_cookie_v17"
                )

            st.rerun()
        else:
            st.error("Invalid login")

    st.stop()


# =====================
# VERSION / ENV
# =====================
APP_VERSION = "V17 PRO - MARKET REGIME + PORTFOLIO + PRICE ALERTS"

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("APP_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

AI_TOP_15 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "GOOGL", "TSLA", "AMD", "NFLX", "AVGO",
    "COST", "LLY", "JPM", "V", "UNH"
]


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
    return sorted(list(set([str(s).strip().upper() for s in symbols if str(s).strip()])))


# =====================
# WATCHLIST / PORTFOLIO / PRICE ALERTS
# =====================
def load_watchlist():
    return clean_symbols(load_cookie_list("watchlist_v17", "watchlist_v17"))


def save_watchlist(symbols):
    save_cookie_list("watchlist_v17", "watchlist_v17", clean_symbols(symbols))


def load_portfolio():
    return load_cookie_list("portfolio_v17", "portfolio_v17")


def save_portfolio(portfolio):
    save_cookie_list("portfolio_v17", "portfolio_v17", portfolio)


def load_price_alerts():
    return load_cookie_list("price_alerts_v17", "price_alerts_v17")


def save_price_alerts(alerts):
    save_cookie_list("price_alerts_v17", "price_alerts_v17", alerts)


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
# STOCK ANALYSIS
# =====================
def make_ai_summary(confidence, rr, rsi, volume_ratio, near_entry, regime):
    if regime == "Bearish / Risk-Off":
        if confidence >= 70:
            return "Good individual setup, but market regime is risk-off. Use smaller size or wait for confirmation."
        return "Market regime is weak. Be selective and avoid forcing trades."

    if confidence >= 75 and rr >= 1.8 and near_entry:
        return "Strong setup: trend, pullback, risk/reward, and entry timing are aligned."
    if confidence >= 60 and rr >= 1.5:
        return "Good watchlist setup: worth monitoring closely, but wait for clean entry confirmation."
    if confidence >= 45:
        return "Mixed setup: some positives, but not enough confirmation yet."
    if rsi > 70:
        return "Avoid for now: RSI appears extended."
    if volume_ratio < 0.8:
        return "Avoid for now: weak volume confirmation."
    return "Weak setup: better opportunities may exist."


def analyze_stock(symbol, regime="Neutral"):
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

    confidence = max(0, min(score, 100))

    entry = round(price * 0.995, 2)
    stop = round(price * 0.94, 2)
    target = round(price * 1.10, 2)

    risk = entry - stop
    reward = target - entry
    rr = round(reward / risk, 2) if risk > 0 else 0

    near_entry = abs(price - entry) / entry <= 0.015
    actionable = confidence >= 60 and rr >= 1.5 and near_entry

    if confidence >= 75 and rr >= 1.8 and near_entry:
        action = "BUY / STRONG SETUP"
    elif confidence >= 60 and rr >= 1.5:
        action = "WATCH / POSSIBLE ENTRY"
    elif confidence >= 45:
        action = "WAIT"
    else:
        action = "AVOID"

    ai_summary = make_ai_summary(confidence, rr, rsi, volume_ratio, near_entry, regime)

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
    cookie_manager.delete(cookie="ai_dashboard_auth_v17", key="delete_auth_cookie_v17")
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

watchlist = load_watchlist()
new_symbol = st.sidebar.text_input("Add ticker", placeholder="Example: NVDA")

if st.sidebar.button("➕ Add Ticker"):
    symbol_to_add = new_symbol.strip().upper()
    if symbol_to_add:
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

c1, c2 = st.columns([1, 3])
c1.metric("Market Regime", regime)
c2.info(regime_reason)


# =====================
# SYMBOL LIST
# =====================
if scan_mode == "Personal Watchlist Only":
    symbols = watchlist
elif scan_mode == "AI Top 15 Only":
    symbols = AI_TOP_15
else:
    symbols = clean_symbols(watchlist + AI_TOP_15)

if not symbols:
    st.info("Your Personal Watchlist is empty. Add a ticker from the sidebar.")
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
    sent_log = load_cookie_list("sent_ai_alerts_v17", "sent_ai_alerts_v17")
    now = datetime.now()

    symbol = row["Symbol"]

    latest_for_symbol = [
        x for x in sent_log
        if x.get("Symbol") == symbol
    ]

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
        "AI Action": row["AI Action"]
    })

    save_cookie_list("sent_ai_alerts_v17", "sent_ai_alerts_v17", sent_log)


def check_price_alerts(current_df):
    alerts = load_price_alerts()
    updated_alerts = []

    for alert in alerts:
        symbol = alert.get("Symbol")
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
# TABS
# =====================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🏆 Top Picks",
    "⭐ Watchlist",
    "🤖 AI Top 15",
    "🔥 Best Setups",
    "📊 Full Scanner",
    "🎯 Price Alerts",
    "💼 Portfolio",
    "📓 Journal"
])


with tab1:
    st.subheader("🏆 Top 3 AI Picks Today")

    top3 = df.sort_values(["Confidence", "R/R"], ascending=False).head(3)

    st.dataframe(top3, use_container_width=True)

    if not top3.empty:
        best = top3.iloc[0]
        st.markdown(f"### Best Setup: {best['Symbol']} — {best['AI Action']}")
        st.info(best["AI Summary"])


with tab2:
    st.subheader("⭐ Personal Watchlist Ranking")

    watch_df = df[df["Symbol"].isin(watchlist)].sort_values(["Confidence", "R/R"], ascending=False)

    if watch_df.empty:
        st.info("Add stocks to your personal watchlist from the sidebar.")
    else:
        st.dataframe(watch_df, use_container_width=True)

        selected = st.selectbox("Select stock", watch_df["Symbol"].tolist())
        row = watch_df[watch_df["Symbol"] == selected].iloc[0]

        st.markdown(f"## {selected} — {row['AI Action']}")
        st.info(row["AI Summary"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Price", row["Price"])
        m2.metric("Confidence", row["Confidence"])
        m3.metric("R/R", row["R/R"])
        m4.metric("RSI", row["RSI"])

        st.markdown("### 📈 Chart")
        make_chart(selected, row, chart_period)

        st.markdown("### Why AI scored it this way")
        for reason in row["Score Reasons"].split(" | "):
            st.write(f"- {reason}")


with tab3:
    st.subheader("🤖 AI Top 15 Scanner")

    ai_df = df[df["Symbol"].isin(AI_TOP_15)].sort_values(["Confidence", "R/R"], ascending=False)
    st.dataframe(ai_df, use_container_width=True)


with tab4:
    st.subheader("🔥 Best Setups")

    actionable = df[df["Actionable"] == True].sort_values("Confidence", ascending=False)
    watch = df[(df["Actionable"] == False) & (df["Confidence"] >= 55)].sort_values("Confidence", ascending=False)
    avoid = df[df["Confidence"] < 45].sort_values("Confidence", ascending=True)

    a, b, c = st.columns(3)
    a.metric("Actionable", len(actionable))
    b.metric("Watch / Wait", len(watch))
    c.metric("Avoid", len(avoid))

    st.markdown("### ✅ Actionable")
    st.dataframe(actionable, use_container_width=True)

    st.markdown("### 👀 Watch / Wait")
    st.dataframe(watch, use_container_width=True)

    st.markdown("### ⚠️ Avoid")
    st.dataframe(avoid, use_container_width=True)


with tab5:
    st.subheader("📊 Full Scanner")

    min_confidence = st.slider("Minimum Confidence", 0, 100, 50)
    min_rr = st.slider("Minimum R/R", 0.0, 5.0, 1.0, 0.1)

    filtered = df[(df["Confidence"] >= min_confidence) & (df["R/R"] >= min_rr)]
    st.dataframe(filtered, use_container_width=True)


with tab6:
    st.subheader("🎯 Persistent Price Alerts")

    alerts = load_price_alerts()

    with st.form("price_alert_form"):
        alert_symbol = st.text_input("Ticker").upper()
        alert_price = st.number_input("Target Price", value=0.0)
        direction = st.selectbox("Direction", ["Above", "Below"])
        submit_alert = st.form_submit_button("Add Price Alert")

        if submit_alert and alert_symbol and alert_price > 0:
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
        alert_df = pd.DataFrame(alerts)
        st.dataframe(alert_df, use_container_width=True)

        if st.button("Clear All Price Alerts"):
            save_price_alerts([])
            st.rerun()
    else:
        st.info("No price alerts yet.")


with tab7:
    st.subheader("💼 Portfolio Tracker")

    portfolio = load_portfolio()

    with st.form("portfolio_form"):
        p_symbol = st.text_input("Symbol").upper()
        p_buy = st.number_input("Buy Price", value=0.0)
        p_qty = st.number_input("Shares", value=0.0)
        p_submit = st.form_submit_button("Add Position")

        if p_submit and p_symbol and p_buy > 0 and p_qty > 0:
            portfolio.append({
                "Symbol": p_symbol,
                "Buy Price": p_buy,
                "Shares": p_qty,
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            save_portfolio(portfolio)
            st.success("Position added.")
            st.rerun()

    rows = []
    total_value = 0
    total_cost = 0
    total_pnl = 0

    for pos in portfolio:
        symbol = pos["Symbol"]
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

    if rows:
        port_df = pd.DataFrame(rows)

        p1, p2, p3 = st.columns(3)
        p1.metric("Portfolio Value", f"${total_value:,.2f}")
        p2.metric("Total Cost", f"${total_cost:,.2f}")
        p3.metric("Total P/L", f"${total_pnl:,.2f}")

        st.dataframe(port_df, use_container_width=True)

        if st.button("Clear Portfolio"):
            save_portfolio([])
            st.rerun()
    else:
        st.info("No portfolio positions yet.")


with tab8:
    st.subheader("📓 Trade Journal")

    if "journal_v17" not in st.session_state:
        st.session_state.journal_v17 = []

    with st.form("journal_form"):
        j_symbol = st.text_input("Trade Symbol").upper()
        j_entry = st.number_input("Entry", value=0.0)
        j_exit = st.number_input("Exit", value=0.0)
        j_shares = st.number_input("Shares", value=0.0)
        j_result = st.selectbox("Result", ["Open", "Win", "Loss", "Breakeven"])
        j_notes = st.text_input("Notes")
        j_submit = st.form_submit_button("Add Trade")

        if j_submit and j_symbol:
            pnl = round((j_exit - j_entry) * j_shares, 2) if j_exit > 0 else 0
            st.session_state.journal_v17.append({
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Symbol": j_symbol,
                "Entry": j_entry,
                "Exit": j_exit,
                "Shares": j_shares,
                "Result": j_result,
                "P/L": pnl,
                "Notes": j_notes
            })
            st.rerun()

    if st.session_state.journal_v17:
        journal_df = pd.DataFrame(st.session_state.journal_v17)
        st.dataframe(journal_df, use_container_width=True)
    else:
        st.info("No trades logged yet.")