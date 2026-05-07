
import streamlit as st
import yfinance as yf
import pandas as pd
import os
import json
import hashlib
import smtplib
import plotly.graph_objects as go
from email.mime.text import MIMEText
from datetime import datetime, timedelta

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


# =====================
# PAGE CONFIG
# =====================
st.set_page_config(page_title="AI Trading Dashboard", page_icon="📈", layout="wide")

if st_autorefresh:
    st_autorefresh(interval=60 * 1000, key="refresh")


# =====================
# FILE STORAGE
# =====================
STORE_FILE = "dashboard_store.json"


def load_store():
    if os.path.exists(STORE_FILE):
        try:
            with open(STORE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "watchlist": [],
        "price_alerts": [],
        "portfolio": [],
        "paper_trades": [],
        "journal": [],
        "sent_alerts": []
    }


def save_store(store):
    with open(STORE_FILE, "w") as f:
        json.dump(store, f, indent=2)


store = load_store()


# =====================
# LOGIN — REFRESH SAFE
# =====================
APP_USERNAME = os.getenv("APP_USERNAME", "admin").strip()
APP_PASSWORD_LOGIN = os.getenv("APP_PASSWORD_LOGIN", "admin123").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "default_secret_key").strip()


def make_auth_token():
    raw = f"{APP_USERNAME}:{APP_PASSWORD_LOGIN}:{SECRET_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()


AUTH_TOKEN = make_auth_token()

query_params = st.query_params
url_token = query_params.get("auth", "")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = url_token == AUTH_TOKEN

if not st.session_state.logged_in:
    st.title("🔐 AI Trading Dashboard Login")

    username = st.text_input("Username").strip()
    password = st.text_input("Password", type="password").strip()
    remember_me = st.checkbox("Keep me logged in on refresh", value=True)

    if st.button("Login"):
        if username == APP_USERNAME and password == APP_PASSWORD_LOGIN:
            st.session_state.logged_in = True

            if remember_me:
                st.query_params["auth"] = AUTH_TOKEN

            st.rerun()
        else:
            st.error("Invalid login")

    st.stop()


# =====================
# ENV / VERSION
# =====================
APP_VERSION = "V22.1 DAILY SWING PLAN + BUY NOW EMAIL ALERTS"

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("APP_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")


# =====================
# EXCLUSIONS
# =====================
EXCLUDED_TICKERS = {
    # Financials / banks / brokers / insurance / payments
    "JPM", "BAC", "GS", "MS", "C", "WFC", "AIG", "MET", "PRU",
    "AXP", "V", "MA", "COF", "SCHW", "BLK", "BX", "SPGI", "ICE",
    "PYPL", "SQ", "HOOD", "COIN",

    # Alcohol
    "BUD", "STZ", "TAP", "DEO", "SAM", "BF-B", "BF-A",

    # Gambling / casinos / betting
    "DKNG", "LVS", "WYNN", "MGM", "PENN", "CZR", "FLUT"
}


def is_excluded_symbol(symbol):
    return str(symbol).strip().upper() in EXCLUDED_TICKERS


def clean_symbols(symbols):
    cleaned = sorted(list(set([str(s).strip().upper() for s in symbols if str(s).strip()])))
    return [s for s in cleaned if not is_excluded_symbol(s)]


AI_TOP_15 = clean_symbols([
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "GOOGL", "TSLA", "AMD", "NFLX", "AVGO",
    "COST", "LLY", "UNH", "CRM", "NOW"
])


# =====================
# DATA HELPERS
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
# MARKET PULSE
# =====================
MARKET_TICKERS = {
    "Nasdaq / QQQ": "QQQ",
    "S&P 500 / SPY": "SPY",
    "Dow / DIA": "DIA",
    "Russell / IWM": "IWM",
    "VIX": "^VIX"
}


def get_market_pulse():
    rows = []

    for name, ticker in MARKET_TICKERS.items():
        data = get_stock_data(ticker, period="5d", interval="1d")

        if data is None or len(data) < 2:
            continue

        last = float(data["Close"].iloc[-1])
        prev = float(data["Close"].iloc[-2])
        change_pct = ((last - prev) / prev) * 100 if prev > 0 else 0

        rows.append({
            "Market": name,
            "Ticker": ticker,
            "Price": round(last, 2),
            "Daily %": round(change_pct, 2)
        })

    return pd.DataFrame(rows)


def get_market_news():
    news_items = []
    tickers = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "TSLA"]

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            news = getattr(stock, "news", [])

            for item in news[:3]:
                content = item.get("content", item) if isinstance(item, dict) else {}

                title = content.get("title") or item.get("title", "")
                publisher = "Market News"
                link = ""

                provider = content.get("provider", {})
                if isinstance(provider, dict):
                    publisher = provider.get("displayName", "Market News")
                else:
                    publisher = item.get("publisher", "Market News")

                canonical = content.get("canonicalUrl", {})
                if isinstance(canonical, dict):
                    link = canonical.get("url", "")
                else:
                    link = item.get("link", "")

                if title:
                    news_items.append({
                        "Source": publisher,
                        "Ticker": ticker,
                        "Headline": title,
                        "Link": link
                    })
        except Exception:
            pass

    seen = set()
    clean = []

    for item in news_items:
        if item["Headline"] not in seen:
            clean.append(item)
            seen.add(item["Headline"])

    return clean[:8]


def get_macro_events():
    return pd.DataFrame([
        {
            "Event": "Federal Reserve / Interest Rate Decision",
            "Why It Matters": "Can move the entire market, especially growth and tech stocks.",
            "What To Watch": "Rate cuts, rate hikes, Fed tone, inflation language"
        },
        {
            "Event": "CPI Inflation Report",
            "Why It Matters": "Higher inflation can hurt growth stocks and delay rate cuts.",
            "What To Watch": "Headline CPI, core CPI, month-over-month trend"
        },
        {
            "Event": "Jobs Report",
            "Why It Matters": "Strong jobs can delay rate cuts; weak jobs can raise recession fears.",
            "What To Watch": "Payrolls, unemployment, wage growth"
        },
        {
            "Event": "PCE Inflation",
            "Why It Matters": "The Fed watches PCE closely for inflation decisions.",
            "What To Watch": "Core PCE trend"
        },
        {
            "Event": "Major Tech Earnings",
            "Why It Matters": "NVDA, MSFT, AAPL, AMZN, META can move Nasdaq heavily.",
            "What To Watch": "Guidance, AI demand, margins, cloud growth"
        }
    ])


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
# ANALYSIS
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

    if confidence >= 65 and rr >= 1.5 and near_entry:
        return "BEST SWING CANDIDATE", "Best candidate, but wait for cleaner intraday confirmation before forcing entry."

    if confidence >= 60 and rr >= 1.5 and not near_entry:
        return "WAIT FOR ENTRY", "Setup is good, but price is not close enough to ideal entry."

    if confidence >= 45:
        return "WATCHLIST ONLY", "Setup is mixed and needs more confirmation."

    return "AVOID", "Setup is currently weak."


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

    intraday_status, intraday_change, _ = get_intraday_momentum(symbol)

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
    elif timing_signal == "BEST SWING CANDIDATE":
        action = "BEST CANDIDATE / WATCH ENTRY"
    elif confidence >= 60 and rr >= 1.5:
        action = "WATCH / POSSIBLE ENTRY"
    elif confidence >= 45:
        action = "WAIT"
    else:
        action = "AVOID"

    if timing_signal == "BUY NOW":
        ai_summary = "Strong setup with supportive timing. Use position sizing carefully."
    elif timing_signal == "BEST SWING CANDIDATE":
        ai_summary = "Best swing trade candidate today. Context is supportive, but do not chase if price moves away from entry."
    elif confidence >= 60:
        ai_summary = "Good setup. Monitor for clean confirmation."
    elif confidence >= 45:
        ai_summary = "Mixed setup. Wait for better confirmation."
    else:
        ai_summary = "Weak setup. Better opportunities may exist."

    setup_score = confidence + (rr * 5)
    if timing_signal == "BUY NOW":
        setup_score += 20
    elif timing_signal == "BEST SWING CANDIDATE":
        setup_score += 10
    if regime == "Bearish / Risk-Off":
        setup_score -= 15

    return {
        "Symbol": symbol,
        "Price": round(price, 2),
        "Entry": entry,
        "Target": target,
        "Stop": stop,
        "R/R": rr,
        "Confidence": confidence,
        "Setup Score": round(setup_score, 2),
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

    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"chart_{symbol}_{period}_{datetime.now().timestamp()}"
    )


def build_daily_trade_plan(df, regime):
    ranked = df.sort_values(["Setup Score", "Confidence", "R/R"], ascending=False)

    if ranked.empty:
        return None

    best = ranked.iloc[0]

    if regime == "Bearish / Risk-Off":
        decision = "NO CLEAN BUY / RISK-OFF"
        context = "Market regime is risk-off. The best candidate may still be worth watching, but avoid aggressive entries."
    elif best["Timing Signal"] == "BUY NOW":
        decision = "BUY NOW CANDIDATE"
        context = "This is the cleanest immediate setup because timing, risk/reward, trend, and momentum are aligned."
    elif best["Timing Signal"] == "BEST SWING CANDIDATE":
        decision = "BEST SWING CANDIDATE"
        context = "This is the best candidate today, but entry discipline still matters. Consider using a price alert near entry."
    elif best["Confidence"] >= 60:
        decision = "WAIT FOR ENTRY"
        context = "Good setup, but not an ideal buy-now situation. Use alerts and wait for price to come into the entry zone."
    else:
        decision = "NO CLEAN TRADE TODAY"
        context = "No stock has enough confirmation. This is a day to watch, not force trades."

    return {
        "symbol": best["Symbol"],
        "decision": decision,
        "context": context,
        "row": best,
        "ranked": ranked
    }


# =====================
# SIDEBAR
# =====================
st.sidebar.title("⚙️ Dashboard Settings")

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.query_params.clear()
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

watchlist = clean_symbols(store.get("watchlist", []))
new_symbol = st.sidebar.text_input("Add ticker", placeholder="Example: NVDA")

if st.sidebar.button("➕ Add Ticker"):
    symbol_to_add = new_symbol.strip().upper()

    if not symbol_to_add:
        st.sidebar.warning("Enter a ticker.")
    elif is_excluded_symbol(symbol_to_add):
        st.sidebar.error(f"{symbol_to_add} is blocked by your exclusion rules.")
    else:
        store["watchlist"] = clean_symbols(watchlist + [symbol_to_add])
        save_store(store)
        st.sidebar.success(f"Added {symbol_to_add}")
        st.rerun()

if watchlist:
    st.sidebar.success(", ".join(watchlist))

    remove_symbol = st.sidebar.selectbox("Remove ticker", [""] + watchlist)

    if st.sidebar.button("🗑️ Remove Ticker"):
        if remove_symbol:
            store["watchlist"] = [s for s in watchlist if s != remove_symbol]
            save_store(store)
            st.rerun()

    if st.sidebar.button("🧹 Clear Watchlist"):
        store["watchlist"] = []
        save_store(store)
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
# MARKET PULSE
# =====================
st.subheader("📊 Market Pulse")

market_df = get_market_pulse()

if not market_df.empty:
    cols = st.columns(len(market_df))

    for i, row in market_df.iterrows():
        cols[i].metric(row["Market"], row["Price"], f"{row['Daily %']}%")

    with st.expander("View Market Pulse Table", expanded=False):
        st.dataframe(market_df, use_container_width=True)
else:
    st.warning("Market pulse data unavailable.")

st.divider()


# =====================
# MARKET NEWS
# =====================
st.subheader("📰 Market News & Macro Risk")

news_items = get_market_news()

if news_items:
    for item in news_items[:6]:
        if item["Link"]:
            st.markdown(f"**[{item['Headline']}]({item['Link']})**  \n{item['Source']} | Related: `{item['Ticker']}`")
        else:
            st.markdown(f"**{item['Headline']}**  \n{item['Source']} | Related: `{item['Ticker']}`")
else:
    st.info("No market news available right now.")

with st.expander("Upcoming Market-Moving Events to Watch", expanded=False):
    st.dataframe(get_macro_events(), use_container_width=True)

st.divider()


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
def check_price_alerts(current_df):
    alerts = store.get("price_alerts", [])
    updated = []

    for alert in alerts:
        symbol = alert.get("Symbol")

        if is_excluded_symbol(symbol):
            continue

        row_df = current_df[current_df["Symbol"] == symbol]

        if row_df.empty:
            updated.append(alert)
            continue

        current_price = float(row_df.iloc[0]["Price"])
        target_price = float(alert.get("Target Price", 0))
        direction = alert.get("Direction", "Above")
        triggered = alert.get("Triggered", False)

        hit = current_price >= target_price if direction == "Above" else current_price <= target_price

        if hit and not triggered and enable_email_alerts:
            send_email_alert(
                f"🎯 Price Alert Triggered: {symbol}",
                f"{symbol} hit {current_price}. Target was {target_price} {direction}."
            )
            alert["Triggered"] = True

        updated.append(alert)

    store["price_alerts"] = updated
    save_store(store)


def check_ai_buy_now_alerts(current_df, watchlist):
    """
    Sends an email when a Personal Watchlist stock gets a BUY NOW signal.
    Prevents repeat emails for the same ticker for 6 hours.
    """
    sent_alerts = store.get("sent_alerts", [])
    now = datetime.now()

    if current_df.empty or not watchlist:
        return

    buy_now_df = current_df[
        (current_df["Timing Signal"] == "BUY NOW") &
        (current_df["Symbol"].isin(watchlist))
    ]

    for _, row in buy_now_df.iterrows():
        symbol = row["Symbol"]

        recent_alerts = [
            a for a in sent_alerts
            if a.get("Symbol") == symbol and a.get("Type") == "BUY_NOW"
        ]

        if recent_alerts:
            try:
                last_time = datetime.strptime(
                    recent_alerts[-1]["Time"],
                    "%Y-%m-%d %H:%M:%S"
                )
                if now - last_time < timedelta(hours=6):
                    continue
            except Exception:
                pass

        subject = f"🚨 BUY NOW Signal: {symbol}"

        body = f"""
AI Trading Dashboard BUY NOW Alert

Symbol: {symbol}
Price: {row['Price']}
Entry: {row['Entry']}
Target: {row['Target']}
Stop: {row['Stop']}
Confidence: {row['Confidence']}
Risk/Reward: {row['R/R']}
Suggested Shares: {row['Shares']}
Capital Needed: ${row['Capital Needed']}
Max Loss: ${row['Max Loss']}

Timing Signal:
{row['Timing Signal']} — {row['Timing Reason']}

AI Summary:
{row['AI Summary']}

Score Reasons:
{row['Score Reasons']}

Time:
{now.strftime('%Y-%m-%d %H:%M:%S')}
"""

        sent, msg = send_email_alert(subject, body)

        if sent:
            sent_alerts.append({
                "Type": "BUY_NOW",
                "Symbol": symbol,
                "Time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "Price": row["Price"],
                "Confidence": row["Confidence"],
                "R/R": row["R/R"],
                "Timing Signal": row["Timing Signal"]
            })

    store["sent_alerts"] = sent_alerts
    save_store(store)


if enable_email_alerts:
    check_price_alerts(df)
    check_ai_buy_now_alerts(df, watchlist)


# =====================
# PORTFOLIO SUMMARY
# =====================
def portfolio_summary():
    rows = []
    total_value = 0
    total_cost = 0
    total_pnl = 0

    for pos in store.get("portfolio", []):
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


portfolio_rows, total_value, total_cost, total_pnl = portfolio_summary()


# =====================
# TOP STRIP
# =====================
daily_plan = build_daily_trade_plan(df, regime)
actionable_count = len(df[df["Actionable"] == True])
buy_now_count = len(df[df["Timing Signal"] == "BUY NOW"])
top_pick = df.sort_values(["Setup Score", "Confidence", "R/R"], ascending=False).iloc[0]

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Market Regime", regime)
m2.metric("Top Pick", top_pick["Symbol"])
m3.metric("Buy Now Signals", buy_now_count)
m4.metric("Actionable", actionable_count)
m5.metric("Portfolio P/L", f"${total_pnl:,.2f}")

st.info(regime_reason)

st.divider()


# =====================
# DAILY AI SWING TRADE PLAN
# =====================
st.subheader("🎯 Daily AI Swing Trade Plan")

if daily_plan:
    best = daily_plan["row"]

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Best Candidate", daily_plan["symbol"])
    p2.metric("Decision", daily_plan["decision"])
    p3.metric("Confidence", best["Confidence"])
    p4.metric("R/R", best["R/R"])

    st.info(daily_plan["context"])
    st.write(best["AI Summary"])

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Entry Zone", best["Entry"])
    e2.metric("Target", best["Target"])
    e3.metric("Stop", best["Stop"])
    e4.metric("Suggested Shares", best["Shares"])

    st.markdown("### Context backing the decision")
    context_points = [
        f"Market regime: **{regime}** — {regime_reason}",
        f"Timing signal: **{best['Timing Signal']}** — {best['Timing Reason']}",
        f"Intraday momentum: **{best['Intraday']}** ({best['Intraday %']}%)",
        f"Confidence score: **{best['Confidence']}**",
        f"Risk/reward: **{best['R/R']}**",
        f"Near entry: **{best['Near Entry']}**",
        f"RSI: **{best['RSI']}**",
        f"Volume ratio: **{best['Volume Ratio']}**"
    ]

    for point in context_points:
        st.write(f"- {point}")

    with st.expander("Full AI scoring reasons", expanded=False):
        for reason in best["Score Reasons"].split(" | "):
            st.write(f"- {reason}")

    st.markdown("### Candidate chart")
    make_chart(best["Symbol"], best, chart_period)

    if daily_plan["decision"] != "BUY NOW CANDIDATE":
        st.warning("This is not a forced buy signal. Use price alerts and paper trading first if the entry is not clean.")

st.divider()


# =====================
# TOP PICKS
# =====================
st.subheader("🏆 Ranked Swing Trade Candidates")

ranked = df.sort_values(["Setup Score", "Confidence", "R/R"], ascending=False)
st.dataframe(ranked.head(10), use_container_width=True)

st.divider()


# =====================
# PERSONAL WATCHLIST
# =====================
st.subheader("⭐ Personal Watchlist Decision Center")

watch_df = df[df["Symbol"].isin(watchlist)].sort_values(
    ["Setup Score", "Confidence", "R/R"],
    ascending=[False, False, False]
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
# PAPER TRADING SIMULATOR
# =====================
st.subheader("🧪 Paper Trading Simulator")

st.info("Use this section to simulate trades without using real money.")

paper_trades = store.get("paper_trades", [])

with st.form("paper_trade_form"):
    p1, p2, p3, p4 = st.columns(4)

    paper_symbol = p1.text_input("Paper Symbol").upper()
    paper_entry = p2.number_input("Paper Entry Price", value=0.0)
    paper_shares = p3.number_input("Paper Shares", value=0.0)
    paper_status = p4.selectbox("Status", ["Open", "Closed"])

    p5, p6 = st.columns(2)
    paper_exit = p5.number_input("Paper Exit Price", value=0.0)
    paper_notes = p6.text_input("Notes")

    submit_paper = st.form_submit_button("Add Paper Trade")

    if submit_paper:
        if not paper_symbol:
            st.warning("Enter a ticker.")
        elif is_excluded_symbol(paper_symbol):
            st.error(f"{paper_symbol} is blocked by your exclusion rules.")
        elif paper_entry <= 0 or paper_shares <= 0:
            st.warning("Enter valid entry price and shares.")
        else:
            pnl = round((paper_exit - paper_entry) * paper_shares, 2) if paper_exit > 0 else 0

            paper_trades.append({
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Symbol": paper_symbol,
                "Entry": paper_entry,
                "Exit": paper_exit,
                "Shares": paper_shares,
                "Status": paper_status,
                "P/L": pnl,
                "Notes": paper_notes
            })

            store["paper_trades"] = paper_trades
            save_store(store)
            st.success("Paper trade added.")
            st.rerun()

if paper_trades:
    paper_df = pd.DataFrame(paper_trades)
    st.dataframe(paper_df, use_container_width=True)

    open_paper = paper_df[paper_df["Status"] == "Open"]
    closed_paper = paper_df[paper_df["Status"] == "Closed"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Open Paper Trades", len(open_paper))
    c2.metric("Closed Paper Trades", len(closed_paper))
    c3.metric("Paper P/L", f"${paper_df['P/L'].sum():,.2f}")

    if st.button("Clear Paper Trades"):
        store["paper_trades"] = []
        save_store(store)
        st.rerun()
else:
    st.info("No paper trades yet. Add simulated trades here.")

st.divider()


# =====================
# SCANNER OUTPUT
# =====================
st.subheader("🔥 Scanner Output")

buy_now = df[df["Timing Signal"] == "BUY NOW"].sort_values("Setup Score", ascending=False)
best_candidate = df[df["Timing Signal"] == "BEST SWING CANDIDATE"].sort_values("Setup Score", ascending=False)
wait_entry = df[df["Timing Signal"] == "WAIT FOR ENTRY"].sort_values("Setup Score", ascending=False)
watch_only = df[df["Timing Signal"] == "WATCHLIST ONLY"].sort_values("Setup Score", ascending=False)
avoid = df[df["Timing Signal"] == "AVOID"].sort_values("Setup Score", ascending=True)

with st.expander("🚀 Buy Now", expanded=True):
    st.dataframe(buy_now, use_container_width=True)

with st.expander("🎯 Best Swing Candidates", expanded=True):
    st.dataframe(best_candidate, use_container_width=True)

with st.expander("⏳ Wait For Entry", expanded=True):
    st.dataframe(wait_entry, use_container_width=True)

with st.expander("👀 Watchlist Only", expanded=False):
    st.dataframe(watch_only, use_container_width=True)

with st.expander("⚠️ Avoid", expanded=False):
    st.dataframe(avoid, use_container_width=True)

st.divider()


# =====================
# PRICE ALERTS
# =====================
st.subheader("🎯 Price Alerts")

alerts = store.get("price_alerts", [])

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

            store["price_alerts"] = alerts
            save_store(store)
            st.success("Price alert added.")
            st.rerun()

if alerts:
    st.dataframe(pd.DataFrame(alerts), use_container_width=True)

    if st.button("Clear All Price Alerts"):
        store["price_alerts"] = []
        save_store(store)
        st.rerun()
else:
    st.info("No price alerts yet.")

st.divider()


# =====================
# PORTFOLIO
# =====================
st.subheader("💼 Portfolio Tracker")

portfolio = store.get("portfolio", [])

with st.form("portfolio_form"):
    p1, p2, p3 = st.columns(3)

    pf_symbol = p1.text_input("Symbol").upper()
    pf_buy = p2.number_input("Buy Price", value=0.0)
    pf_qty = p3.number_input("Shares", value=0.0)

    pf_submit = st.form_submit_button("Add Position")

    if pf_submit:
        if not pf_symbol:
            st.warning("Enter a ticker.")
        elif is_excluded_symbol(pf_symbol):
            st.error(f"{pf_symbol} is blocked by your exclusion rules.")
        elif pf_buy <= 0 or pf_qty <= 0:
            st.warning("Enter valid buy price and shares.")
        else:
            portfolio.append({
                "Symbol": pf_symbol,
                "Buy Price": pf_buy,
                "Shares": pf_qty,
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

            store["portfolio"] = portfolio
            save_store(store)
            st.success("Position added.")
            st.rerun()

if portfolio_rows:
    p1, p2, p3 = st.columns(3)
    p1.metric("Portfolio Value", f"${total_value:,.2f}")
    p2.metric("Total Cost", f"${total_cost:,.2f}")
    p3.metric("Total P/L", f"${total_pnl:,.2f}")

    st.dataframe(pd.DataFrame(portfolio_rows), use_container_width=True)

    if st.button("Clear Portfolio"):
        store["portfolio"] = []
        save_store(store)
        st.rerun()
else:
    st.info("No portfolio positions yet.")


# =====================
# CHEAT SHEET
# =====================
with st.expander("📚 Notes / Where to Enter Paper Trades", expanded=True):
    st.markdown("""
### Where to input paper transactions
Use the **🧪 Paper Trading Simulator** section.

Enter:
- Symbol
- Entry price
- Shares
- Status: Open or Closed
- Exit price only when closing the paper trade
- Notes

### How to read Daily AI Swing Trade Plan
- **BUY NOW CANDIDATE** = strongest immediate setup
- **BEST SWING CANDIDATE** = best overall candidate, but entry timing may need confirmation
- **WAIT FOR ENTRY** = good stock, but price is not ideal
- **NO CLEAN TRADE TODAY** = do not force a trade

### Difference between Portfolio and Paper Trading
- **Portfolio Tracker** = real or actual holdings you want to monitor
- **Paper Trading Simulator** = fake practice trades to test the AI system

### Persistence Fix
This version saves watchlist, paper trades, alerts, portfolio, and journal to:
`dashboard_store.json`

It also keeps login active through the URL auth token after refresh.
""")
