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

auth_cookie = cookie_manager.get(cookie="ai_dashboard_auth_v15")

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
                    cookie="ai_dashboard_auth_v15",
                    val="true",
                    expires_at=datetime.now() + timedelta(days=30),
                    key="set_auth_cookie_v15"
                )

            st.rerun()
        else:
            st.error("Invalid login")

    st.stop()


# =====================
# VERSION / SETTINGS
# =====================
APP_VERSION = "V15 PRO - CHARTS + PERSONAL ALERTS + AI SUMMARY"

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("APP_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

JOURNAL_FILE = "trade_journal.csv"
ALERT_FILE = "alert_history.csv"

AI_TOP_15 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "GOOGL", "TSLA", "AMD", "NFLX", "AVGO",
    "COST", "LLY", "JPM", "V", "UNH"
]


# =====================
# WATCHLIST COOKIE
# =====================
def load_personal_watchlist():
    raw = cookie_manager.get(cookie="personal_watchlist_v15")
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return sorted(list(set([x.strip().upper() for x in items if x.strip()])))
    except Exception:
        return []


def save_personal_watchlist(symbols):
    clean = sorted(list(set([s.strip().upper() for s in symbols if s.strip()])))
    cookie_manager.set(
        cookie="personal_watchlist_v15",
        val=json.dumps(clean),
        expires_at=datetime.now() + timedelta(days=365),
        key="save_personal_watchlist_v15"
    )


# =====================
# HELPERS
# =====================
def load_csv(file, columns):
    if os.path.exists(file):
        return pd.read_csv(file)
    return pd.DataFrame(columns=columns)


def save_csv(df, file):
    df.to_csv(file, index=False)


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


def get_stock_data(symbol, period="6mo"):
    try:
        data = yf.download(
            symbol,
            period=period,
            interval="1d",
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


def make_ai_summary(confidence, rr, rsi, dip_pct, volume_ratio, near_entry):
    if confidence >= 70 and rr >= 1.8 and near_entry:
        return "Strong setup: trend, pullback, risk/reward, and entry timing are aligned."
    if confidence >= 60 and rr >= 1.5:
        return "Good watchlist setup: worth monitoring closely, but wait for clean entry confirmation."
    if confidence >= 45:
        return "Mixed setup: some positives, but not enough confirmation yet."
    if rsi > 70:
        return "Avoid for now: RSI appears extended and entry risk may be high."
    if volume_ratio < 0.8:
        return "Avoid for now: weak volume confirmation."
    return "Weak setup: better opportunities may exist."


def analyze_stock(symbol):
    data = get_stock_data(symbol)

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

    confidence = min(score, 100)

    entry = round(price * 0.995, 2)
    stop = round(price * 0.94, 2)
    target = round(price * 1.10, 2)

    risk = entry - stop
    reward = target - entry
    rr = round(reward / risk, 2) if risk > 0 else 0

    near_entry = abs(price - entry) / entry <= 0.015
    actionable = confidence >= 60 and rr >= 1.5 and near_entry

    if confidence >= 70 and rr >= 1.8 and near_entry:
        action = "BUY / STRONG SETUP"
    elif confidence >= 60 and rr >= 1.5:
        action = "WATCH / POSSIBLE ENTRY"
    elif confidence >= 45:
        action = "WAIT"
    else:
        action = "AVOID"

    ai_summary = make_ai_summary(confidence, rr, rsi, dip_pct, volume_ratio, near_entry)

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


def check_alert(row):
    alert_df = load_csv(
        ALERT_FILE,
        ["Time", "Symbol", "Price", "Entry", "Target", "Stop", "Confidence", "R/R", "AI Action", "AI Summary"]
    )

    symbol = row["Symbol"]
    now = datetime.now()

    if not alert_df.empty and symbol in alert_df["Symbol"].values:
        last_time = alert_df[alert_df["Symbol"] == symbol]["Time"].iloc[-1]
        last_time = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")

        if now - last_time < timedelta(hours=1):
            return

    subject = f"🚨 Personal Watchlist Alert: {symbol}"

    body = f"""
AI Trading Dashboard Alert

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

Score Reasons:
{row['Score Reasons']}

Time: {now.strftime('%Y-%m-%d %H:%M:%S')}
"""

    send_email_alert(subject, body)

    new_alert = pd.DataFrame([{
        "Time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "Symbol": symbol,
        "Price": row["Price"],
        "Entry": row["Entry"],
        "Target": row["Target"],
        "Stop": row["Stop"],
        "Confidence": row["Confidence"],
        "R/R": row["R/R"],
        "AI Action": row["AI Action"],
        "AI Summary": row["AI Summary"]
    }])

    alert_df = pd.concat([alert_df, new_alert], ignore_index=True)
    save_csv(alert_df, ALERT_FILE)


def make_chart(symbol, row, period):
    data = get_stock_data(symbol, period=period)

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
    cookie_manager.delete(cookie="ai_dashboard_auth_v15", key="delete_auth_cookie_v15")
    st.rerun()

capital = st.sidebar.number_input("Trading Capital ($)", value=5000, step=500)
max_loss = st.sidebar.number_input("Risk Budget Per Trade ($)", value=500, step=50)

scan_mode = st.sidebar.radio(
    "Scan Mode",
    [
        "Personal Watchlist Only",
        "AI Top 15 Only",
        "Personal Watchlist + AI Top 15"
    ]
)

chart_period = st.sidebar.selectbox("Chart Period", ["1mo", "3mo", "6mo", "1y"], index=2)

enable_email_alerts = st.sidebar.checkbox("Enable Email Alerts", value=True)
personal_alerts_only = st.sidebar.checkbox("Alerts only for Personal Watchlist", value=True)

if st.sidebar.button("🔄 Manual Refresh"):
    st.rerun()


# =====================
# PERSONAL WATCHLIST
# =====================
st.sidebar.divider()
st.sidebar.header("⭐ PERSONAL WATCHLIST")
st.sidebar.caption("Separate from AI Top 15. Add only stocks YOU want to track.")

personal_watchlist = load_personal_watchlist()

new_symbol = st.sidebar.text_input("Add ticker", placeholder="Example: NFLX")

if st.sidebar.button("➕ Add Ticker"):
    symbol_to_add = new_symbol.strip().upper()

    if symbol_to_add:
        personal_watchlist.append(symbol_to_add)
        personal_watchlist = sorted(list(set(personal_watchlist)))
        save_personal_watchlist(personal_watchlist)
        st.sidebar.success(f"Added {symbol_to_add}")
        st.rerun()

if personal_watchlist:
    st.sidebar.write("Saved Personal Watchlist:")
    st.sidebar.success(", ".join(personal_watchlist))

    remove_symbol = st.sidebar.selectbox("Remove ticker", [""] + personal_watchlist)

    if st.sidebar.button("🗑️ Remove Ticker"):
        if remove_symbol:
            personal_watchlist = [s for s in personal_watchlist if s != remove_symbol]
            save_personal_watchlist(personal_watchlist)
            st.sidebar.warning(f"Removed {remove_symbol}")
            st.rerun()

    if st.sidebar.button("🧹 Clear Personal Watchlist"):
        save_personal_watchlist([])
        st.sidebar.warning("Personal watchlist cleared.")
        st.rerun()
else:
    st.sidebar.info("No personal tickers yet. Add one above.")


# =====================
# HEADER
# =====================
st.title("📈 AI Trading Dashboard")
st.success(APP_VERSION)
st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# =====================
# SYMBOL LIST
# =====================
if scan_mode == "Personal Watchlist Only":
    symbols = personal_watchlist
elif scan_mode == "AI Top 15 Only":
    symbols = AI_TOP_15
else:
    symbols = sorted(list(set(personal_watchlist + AI_TOP_15)))

if not symbols:
    st.info("Your Personal Watchlist is empty. Add a ticker from the sidebar.")
    st.stop()


# =====================
# SCAN
# =====================
results = []

with st.spinner("Scanning stocks..."):
    for symbol in symbols:
        result = analyze_stock(symbol)

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
            result["List Type"] = "Personal Watchlist" if symbol in personal_watchlist else "AI Top 15"

            results.append(result)

df = pd.DataFrame(results)

if df.empty:
    st.warning("No stock data found. Check ticker symbols.")
    st.stop()


# =====================
# ALERT ENGINE
# =====================
if enable_email_alerts:
    actionable_df = df[df["Actionable"] == True]

    if personal_alerts_only:
        actionable_df = actionable_df[actionable_df["Symbol"].isin(personal_watchlist)]

    for _, row in actionable_df.iterrows():
        check_alert(row)


# =====================
# TABS
# =====================
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "⭐ Personal Watchlist",
    "🤖 AI Top 15",
    "🔥 Best Setups",
    "📊 Full Scanner",
    "📬 Alerts",
    "📓 Trade Journal",
    "📚 Cheat Sheets"
])


with tab1:
    st.subheader("⭐ Personal Watchlist AI Evaluation")

    personal_df = df[df["Symbol"].isin(personal_watchlist)].sort_values(
        ["Confidence", "R/R"],
        ascending=False
    )

    if personal_df.empty:
        st.info("Your personal watchlist is empty. Add a ticker from the sidebar.")
    else:
        st.dataframe(personal_df, use_container_width=True)

        selected = st.selectbox("Choose a personal stock to evaluate", personal_df["Symbol"].tolist())
        selected_row = personal_df[personal_df["Symbol"] == selected].iloc[0]

        st.markdown(f"## {selected} — {selected_row['AI Action']}")
        st.info(selected_row["AI Summary"])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Price", selected_row["Price"])
        c2.metric("Entry", selected_row["Entry"])
        c3.metric("Target", selected_row["Target"])
        c4.metric("Stop", selected_row["Stop"])

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Confidence", selected_row["Confidence"])
        c6.metric("Risk/Reward", selected_row["R/R"])
        c7.metric("RSI", selected_row["RSI"])
        c8.metric("Dip %", selected_row["Dip %"])

        st.markdown("### 📈 Chart")
        make_chart(selected, selected_row, chart_period)

        st.markdown("### Why AI scored it this way")
        for reason in selected_row["Score Reasons"].split(" | "):
            st.write(f"- {reason}")


with tab2:
    st.subheader("🤖 AI Top 15 Recommendations Scanner")

    ai_df = df[df["Symbol"].isin(AI_TOP_15)].sort_values(
        ["Confidence", "R/R"],
        ascending=False
    )

    st.dataframe(ai_df, use_container_width=True)


with tab3:
    st.subheader("🔥 Best Setups Today")

    actionable = df[df["Actionable"] == True].sort_values("Confidence", ascending=False)
    watch = df[(df["Actionable"] == False) & (df["Confidence"] >= 55)].sort_values("Confidence", ascending=False)
    avoid = df[df["Confidence"] < 45].sort_values("Confidence", ascending=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Actionable", len(actionable))
    c2.metric("Watch / Wait", len(watch))
    c3.metric("Avoid", len(avoid))

    st.markdown("### ✅ Actionable Now")
    if actionable.empty:
        st.info("No actionable setups right now.")
    else:
        st.dataframe(actionable, use_container_width=True)

    st.markdown("### 👀 Watch / Wait")
    st.dataframe(watch, use_container_width=True)

    st.markdown("### ⚠️ Avoid")
    st.dataframe(avoid, use_container_width=True)


with tab4:
    st.subheader("📊 Full Scanner")

    min_confidence = st.slider("Minimum Confidence", 0, 100, 50)
    min_rr = st.slider("Minimum R/R", 0.0, 5.0, 1.0, 0.1)

    filtered = df[
        (df["Confidence"] >= min_confidence) &
        (df["R/R"] >= min_rr)
    ]

    st.dataframe(filtered, use_container_width=True)


with tab5:
    st.subheader("📬 Alerts")

    st.markdown("### Email Setup Check")
    st.write("EMAIL_SENDER:", "✅ Set" if EMAIL_SENDER else "❌ Missing")
    st.write("APP_PASSWORD:", "✅ Set" if EMAIL_PASSWORD else "❌ Missing")
    st.write("EMAIL_RECEIVER:", "✅ Set" if EMAIL_RECEIVER else "❌ Missing")

    st.write("Alert mode:", "Personal Watchlist only" if personal_alerts_only else "All scanned stocks")

    if st.button("📨 Send Test Email Alert"):
        sent, msg = send_email_alert(
            "Test Alert from AI Trading Dashboard",
            "This is a test email. Your AI Trading Dashboard alert system is working."
        )

        if sent:
            st.success("Test email sent successfully.")
        else:
            st.error(f"Email failed: {msg}")

    st.markdown("### Alert History")

    alert_df = load_csv(
        ALERT_FILE,
        ["Time", "Symbol", "Price", "Entry", "Target", "Stop", "Confidence", "R/R", "AI Action", "AI Summary"]
    )

    if alert_df.empty:
        st.info("No alerts yet.")
    else:
        st.dataframe(alert_df.sort_values("Time", ascending=False), use_container_width=True)


with tab6:
    st.subheader("📓 Trade Journal")

    journal_df = load_csv(
        JOURNAL_FILE,
        ["Date", "Symbol", "Entry", "Exit", "Shares", "Result", "P/L", "Notes"]
    )

    with st.form("trade_form"):
        col1, col2, col3 = st.columns(3)

        symbol = col1.text_input("Symbol").upper()
        entry_price = col2.number_input("Entry Price", value=0.0)
        exit_price = col3.number_input("Exit Price", value=0.0)
        shares = col1.number_input("Shares", value=0, step=1)
        result = col2.selectbox("Result", ["Open", "Win", "Loss", "Breakeven"])
        notes = col3.text_input("Notes")

        submit = st.form_submit_button("Add Trade")

        if submit and symbol:
            pnl = round((exit_price - entry_price) * shares, 2) if exit_price > 0 else 0

            new_trade = pd.DataFrame([{
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Symbol": symbol,
                "Entry": entry_price,
                "Exit": exit_price,
                "Shares": shares,
                "Result": result,
                "P/L": pnl,
                "Notes": notes
            }])

            journal_df = pd.concat([journal_df, new_trade], ignore_index=True)
            save_csv(journal_df, JOURNAL_FILE)
            st.success("Trade added.")
            st.rerun()

    if journal_df.empty:
        st.info("No trades logged yet.")
    else:
        open_trades = journal_df[journal_df["Result"] == "Open"]
        closed_trades = journal_df[journal_df["Result"] != "Open"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Open Trades", len(open_trades))
        c2.metric("Closed Trades", len(closed_trades))
        c3.metric("Total P/L", f"${journal_df['P/L'].sum():,.2f}")

        wins = len(closed_trades[closed_trades["Result"] == "Win"])
        total_closed = len(closed_trades)
        win_rate = round((wins / total_closed) * 100, 2) if total_closed > 0 else 0
        c4.metric("Win Rate", f"{win_rate}%")

        st.markdown("### Open Trades")
        st.dataframe(open_trades, use_container_width=True)

        st.markdown("### Closed Trades")
        st.dataframe(closed_trades, use_container_width=True)


with tab7:
    st.subheader("📚 Cheat Sheets")

    st.markdown("""
### ✅ Actionable Setup
A stock becomes actionable when:
- Confidence is 60 or higher
- Risk/Reward is 1.5 or higher
- Price is near entry

### 🟢 BUY / STRONG SETUP
Usually means:
- Strong trend
- Healthy pullback
- RSI is reasonable
- Volume confirms the move
- Risk/reward is attractive

### 🟡 WATCH / POSSIBLE ENTRY
The setup is forming, but may need a better price, stronger volume, or more confirmation.

### 🔴 AVOID
Usually means:
- Weak trend
- Poor risk/reward
- Extended RSI
- Weak volume
- Setup is not clean

### 📬 Alerts
V15 alerts are designed to focus on your Personal Watchlist by default.
Duplicate alerts are blocked for 1 hour per stock.

### ⭐ Personal Watchlist
Use the sidebar to add only stocks YOU want to track.
This is separate from the AI Top 15 scanner.
""")