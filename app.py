
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
from zoneinfo import ZoneInfo

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


# =====================
# PAGE CONFIG
# =====================
st.set_page_config(page_title="AI Trading Dashboard", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 1500px;
    }
    div[data-testid="stMetric"] {
        background: #fafafa;
        border: 1px solid #eeeeee;
        padding: 10px;
        border-radius: 12px;
    }
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        div[data-testid="stMetric"] {
            padding: 7px;
        }
        h1 {
            font-size: 1.55rem !important;
        }
        h2, h3 {
            font-size: 1.15rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

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
APP_VERSION = "V25.1 MOBILE-FRIENDLY TABLES + DEEP DETAIL VIEW"

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
# V23 RISK / SECTOR / EXIT HELPERS
# =====================
SECTOR_ETFS = {
    "Technology": "XLK",
    "Semiconductors": "SMH",
    "Software": "IGV",
    "AI / Robotics": "BOTZ",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU"
}


def get_sector_strength():
    rows = []

    for sector, ticker in SECTOR_ETFS.items():
        data = get_stock_data(ticker, period="3mo", interval="1d")

        if data is None or len(data) < 22:
            continue

        close = data["Close"]
        price = float(close.iloc[-1])
        five_day = ((price - float(close.iloc[-6])) / float(close.iloc[-6])) * 100 if len(close) >= 6 else 0
        one_month = ((price - float(close.iloc[-22])) / float(close.iloc[-22])) * 100 if len(close) >= 22 else 0

        rows.append({
            "Sector": sector,
            "ETF": ticker,
            "5D %": round(five_day, 2),
            "1M %": round(one_month, 2),
            "Strength Score": round((five_day * 0.4) + (one_month * 0.6), 2)
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Strength Score", ascending=False)


def get_relative_strength(symbol):
    stock = get_stock_data(symbol, period="3mo", interval="1d")
    qqq = get_stock_data("QQQ", period="3mo", interval="1d")

    if stock is None or qqq is None or len(stock) < 22 or len(qqq) < 22:
        return 0.0, "Unknown"

    stock_ret = ((float(stock["Close"].iloc[-1]) - float(stock["Close"].iloc[-22])) / float(stock["Close"].iloc[-22])) * 100
    qqq_ret = ((float(qqq["Close"].iloc[-1]) - float(qqq["Close"].iloc[-22])) / float(qqq["Close"].iloc[-22])) * 100
    rs = round(stock_ret - qqq_ret, 2)

    if rs >= 5:
        label = "Strong Outperformance"
    elif rs >= 1:
        label = "Outperforming"
    elif rs > -1:
        label = "In Line"
    elif rs > -5:
        label = "Underperforming"
    else:
        label = "Weak Relative Strength"

    return rs, label


def get_earnings_warning(symbol):
    """
    Best-effort earnings risk check using yfinance calendar.
    If data is unavailable, it returns no hard penalty.
    """
    try:
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar

        if cal is None:
            return "Unknown", 0, "Earnings date unavailable."

        earnings_date = None

        if isinstance(cal, dict):
            possible = cal.get("Earnings Date") or cal.get("EarningsDate")
            if isinstance(possible, list) and possible:
                earnings_date = possible[0]
            elif possible is not None:
                earnings_date = possible

        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if "Earnings Date" in cal.index:
                possible = cal.loc["Earnings Date"].dropna().tolist()
                if possible:
                    earnings_date = possible[0]

        if earnings_date is None:
            return "Unknown", 0, "Earnings date unavailable."

        earnings_ts = pd.to_datetime(earnings_date, errors="coerce")

        if pd.isna(earnings_ts):
            return "Unknown", 0, "Earnings date unavailable."

        today = pd.Timestamp(datetime.now().date())
        days = (earnings_ts.normalize() - today).days

        if 0 <= days <= 3:
            return "High Earnings Risk", -20, f"Earnings appear to be within {days} day(s). Avoid forcing swing entries."
        if 4 <= days <= 7:
            return "Moderate Earnings Risk", -10, f"Earnings appear to be within {days} days. Size smaller or wait."
        if days < 0:
            return "No Near-Term Earnings Risk", 0, "Earnings appear to have passed."
        return "No Near-Term Earnings Risk", 0, f"Earnings appear more than 7 days away."

    except Exception:
        return "Unknown", 0, "Earnings date unavailable."


def build_risk_factors(row):
    risks = []

    if row.get("Volume Ratio", 1) < 1.0:
        risks.append("Volume is below average, so confirmation is weaker.")

    if row.get("RSI", 50) >= 68:
        risks.append("RSI is elevated, which increases chase risk.")

    if row.get("Dip %", 0) < 1:
        risks.append("Very small dip from recent highs; entry may be less favorable.")

    if row.get("Intraday %", 0) > 4:
        risks.append("Intraday move is already large; avoid chasing a spike.")

    if row.get("Earnings Risk", "") in ["High Earnings Risk", "Moderate Earnings Risk"]:
        risks.append(row.get("Earnings Note", "Upcoming earnings may increase gap risk."))

    if row.get("Relative Strength %", 0) < 0:
        risks.append("Stock is underperforming QQQ over the last month.")

    if not risks:
        risks.append("No major risk flags from the current rule set.")

    return risks


def trade_grade(row):
    score = float(row.get("Setup Score", 0))

    if row.get("Earnings Risk") == "High Earnings Risk":
        score -= 20
    elif row.get("Earnings Risk") == "Moderate Earnings Risk":
        score -= 10

    if row.get("Volume Ratio", 1) < 1:
        score -= 5

    if row.get("Relative Strength %", 0) < 0:
        score -= 5

    if score >= 130:
        return "A+"
    if score >= 115:
        return "A"
    if score >= 100:
        return "B+"
    if score >= 85:
        return "B"
    if score >= 70:
        return "C"
    return "D"


def exit_strategy(row):
    entry = float(row["Entry"])
    target = float(row["Target"])
    stop = float(row["Stop"])

    first_trim = round(entry + ((target - entry) * 0.5), 2)

    if row.get("Timing Signal") == "BUY NOW":
        return (
            f"Consider scaling: take partial profit near ${first_trim}, "
            f"target near ${target}, and use stop near ${stop}. "
            f"If price moves halfway to target, consider moving stop toward breakeven."
        )

    if row.get("Timing Signal") in ["BEST SWING CANDIDATE", "WAIT FOR ENTRY"]:
        return (
            f"Do not chase. Consider entry near ${entry}; stop near ${stop}; "
            f"first trim near ${first_trim}; full target near ${target}."
        )

    return "No active exit plan because setup is not strong enough yet."


# =====================
# V24 ETF ENTRY TIMING
# =====================
ETF_UNIVERSE = {
    "QQQ": "Nasdaq 100 / Growth",
    "SPY": "S&P 500 Broad Market",
    "VOO": "S&P 500 Broad Market",
    "VTI": "Total US Market",
    "IWM": "Russell 2000 Small Caps",
    "XLK": "Technology",
    "SMH": "Semiconductors",
    "SOXX": "Semiconductors",
    "IGV": "Software",
    "BOTZ": "AI / Robotics",
    "ARKQ": "Autonomous Tech / Robotics",
    "XLV": "Healthcare",
    "IBB": "Biotech",
    "XBI": "Biotech",
    "XLY": "Consumer Discretionary",
    "XLI": "Industrials",
    "XLE": "Energy",
    "ICLN": "Clean Energy",
    "TAN": "Solar",
    "XLU": "Utilities",
    "VNQ": "Real Estate"
}

# Broadly avoid financial-sector ETFs, alcohol/gambling/media-entertainment-focused ETFs.
BLOCKED_ETFS = {
    "XLF", "VFH", "KBE", "KRE", "IYF", "IAI", "KIE",
    "PEJ", "PBS", "XLC", "VOX", "IYZ", "BJK", "BETZ"
}


def is_blocked_etf(symbol):
    return str(symbol).strip().upper() in BLOCKED_ETFS


def analyze_etf_entry(symbol, label, regime):
    if is_blocked_etf(symbol):
        return None

    data = get_stock_data(symbol, period="6mo", interval="1d")

    if data is None or len(data) < 60:
        return None

    close = data["Close"]
    high = data["High"]
    volume = data["Volume"]

    price = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else sma50
    rsi = float(calculate_rsi(close).iloc[-1])

    recent_high = float(high.tail(30).max())
    dip_pct = ((recent_high - price) / recent_high) * 100 if recent_high > 0 else 0

    avg_volume = float(volume.tail(20).mean())
    current_volume = float(volume.iloc[-1])
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

    one_month_return = ((price - float(close.iloc[-22])) / float(close.iloc[-22])) * 100 if len(close) >= 22 else 0
    five_day_return = ((price - float(close.iloc[-6])) / float(close.iloc[-6])) * 100 if len(close) >= 6 else 0

    score = 0
    reasons = []
    risks = []

    if price > sma20:
        score += 15
        reasons.append("ETF is above the 20-day moving average.")
    else:
        reasons.append("ETF is below the 20-day moving average.")

    if price > sma50:
        score += 15
        reasons.append("ETF is above the 50-day moving average.")
    else:
        risks.append("ETF is below the 50-day moving average.")

    if sma20 > sma50:
        score += 15
        reasons.append("Short-term trend is stronger than medium-term trend.")
    else:
        risks.append("20-day average is not above 50-day average.")

    if price > sma200:
        score += 10
        reasons.append("ETF is above the long-term trend line.")
    else:
        risks.append("ETF is below the long-term trend line.")

    if 2 <= dip_pct <= 8:
        score += 20
        reasons.append("Healthy pullback range for ETF entry.")
    elif 8 < dip_pct <= 15:
        score += 10
        reasons.append("Deeper pullback; possible entry but needs confirmation.")
    elif dip_pct < 2:
        risks.append("Very small pullback; avoid chasing if extended.")
    else:
        risks.append("Pullback is deep; trend may be weakening.")

    if 40 <= rsi <= 58:
        score += 20
        reasons.append("RSI is in a reasonable ETF entry zone.")
    elif 58 < rsi <= 68:
        score += 8
        reasons.append("RSI is strong but getting extended.")
    elif rsi < 40:
        score += 8
        risks.append("RSI is weak; may need more confirmation.")
    else:
        risks.append("RSI is elevated; entry may be late.")

    if volume_ratio >= 1.1:
        score += 10
        reasons.append("Volume is above average.")
    elif volume_ratio < 0.8:
        risks.append("Volume is below average.")

    if price > prev:
        score += 8
        reasons.append("Price momentum is positive today.")
    else:
        risks.append("Short-term price momentum is weak today.")

    if regime == "Bullish":
        score += 7
        reasons.append("Broad market regime is supportive.")
    elif regime == "Bearish / Risk-Off":
        score -= 15
        risks.append("Market regime is risk-off.")

    score = max(0, min(score, 100))

    if score >= 80 and 40 <= rsi <= 65 and regime != "Bearish / Risk-Off":
        decision = "GOOD ETF ENTRY ZONE"
    elif score >= 65:
        decision = "WATCH / SCALE IN SLOWLY"
    elif score >= 50:
        decision = "WAIT FOR BETTER ENTRY"
    else:
        decision = "AVOID FOR NOW"

    if score >= 85:
        grade = "A"
    elif score >= 75:
        grade = "B+"
    elif score >= 65:
        grade = "B"
    elif score >= 50:
        grade = "C"
    else:
        grade = "D"

    entry_zone = round(price * 0.995, 2)
    add_zone = round(price * 0.97, 2)
    risk_level = "Low / Moderate" if score >= 75 else "Moderate" if score >= 60 else "Elevated"

    if not risks:
        risks.append("No major ETF-specific risk flags from the current rule set.")

    return {
        "ETF": symbol,
        "Category": label,
        "Price": round(price, 2),
        "Decision": decision,
        "Grade": grade,
        "Score": score,
        "Entry Zone": entry_zone,
        "Add-on Pullback Zone": add_zone,
        "RSI": round(rsi, 1),
        "Dip %": round(dip_pct, 2),
        "5D %": round(five_day_return, 2),
        "1M %": round(one_month_return, 2),
        "Volume Ratio": round(volume_ratio, 2),
        "Risk Level": risk_level,
        "Reasons": " | ".join(reasons),
        "Risk Factors": " | ".join(risks)
    }


def build_etf_entry_table(regime):
    rows = []

    for symbol, label in ETF_UNIVERSE.items():
        result = analyze_etf_entry(symbol, label, regime)
        if result:
            rows.append(result)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(["Score", "1M %"], ascending=False)




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

    relative_strength_pct, relative_strength_label = get_relative_strength(symbol)

    if relative_strength_pct >= 5:
        score += 8
        reasons.append("Strong relative strength versus QQQ")
    elif relative_strength_pct >= 1:
        score += 4
        reasons.append("Positive relative strength versus QQQ")
    elif relative_strength_pct < -5:
        score -= 8
        reasons.append("Weak relative strength versus QQQ")
    elif relative_strength_pct < 0:
        score -= 4
        reasons.append("Slight underperformance versus QQQ")

    earnings_risk, earnings_penalty, earnings_note = get_earnings_warning(symbol)
    score += earnings_penalty

    if earnings_penalty < 0:
        reasons.append(earnings_note)

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

    if earnings_risk == "High Earnings Risk" and timing_signal == "BUY NOW":
        timing_signal = "WAIT / EARNINGS RISK"
        timing_reason = earnings_note
    elif earnings_risk == "Moderate Earnings Risk" and timing_signal == "BUY NOW":
        timing_signal = "BEST SWING CANDIDATE"
        timing_reason = f"{timing_reason} However, earnings risk is moderate."

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
        "Trade Grade": None,
        "Relative Strength %": relative_strength_pct,
        "Relative Strength": relative_strength_label,
        "Earnings Risk": earnings_risk,
        "Earnings Note": earnings_note,
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
        "Last Updated": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
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


# =====================
# V25 DEEP DETAIL VIEW HELPERS
# =====================
def make_detail_link(symbol, label=None):
    symbol = str(symbol).strip().upper()
    label = label or symbol
    return f'<a href="?detail={symbol}" target="_blank">{label}</a>'


def make_etf_detail_link(symbol, label=None):
    symbol = str(symbol).strip().upper()
    label = label or symbol
    return f'<a href="?etf_detail={symbol}" target="_blank">{label}</a>'


def compact_stock_table(df, max_rows=None):
    """
    Main dashboard stock table: short, mobile-friendly.
    Full explanations stay in Deep Detail View.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    keep_cols = [
        "Symbol", "Timing Signal", "Trade Grade", "Price", "Entry", "Target", "Stop",
        "Confidence", "Setup Score", "R/R", "RSI", "Volume Ratio",
        "Relative Strength %", "Earnings Risk", "List Type"
    ]

    available = [c for c in keep_cols if c in df.columns]
    out = df[available].copy()

    if max_rows:
        out = out.head(max_rows)

    return out


def compact_etf_table(df, max_rows=None):
    """
    Main dashboard ETF table: short, mobile-friendly.
    Full reasons stay in ETF Deep Detail View.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    keep_cols = [
        "ETF", "Category", "Decision", "Grade", "Score", "Price",
        "Entry Zone", "Add-on Pullback Zone", "RSI", "Dip %",
        "5D %", "1M %", "Volume Ratio", "Risk Level"
    ]

    available = [c for c in keep_cols if c in df.columns]
    out = df[available].copy()

    if max_rows:
        out = out.head(max_rows)

    return out


def render_clickable_table(df, symbol_col="Symbol", etf=False, max_rows=None, compact=True):
    if df is None or df.empty:
        st.info("No data available.")
        return

    if compact:
        if etf:
            display_df = compact_etf_table(df, max_rows=max_rows)
        else:
            display_df = compact_stock_table(df, max_rows=max_rows)
    else:
        display_df = df.copy()
        if max_rows:
            display_df = display_df.head(max_rows)

    if symbol_col in display_df.columns:
        if etf:
            display_df[symbol_col] = display_df[symbol_col].apply(make_etf_detail_link)
        else:
            display_df[symbol_col] = display_df[symbol_col].apply(make_detail_link)

    html = display_df.to_html(escape=False, index=False)

    st.markdown(
        """
        <style>
        .mobile-table-wrapper {
            overflow-x: auto;
            width: 100%;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 4px;
            margin-bottom: 1rem;
        }
        .mobile-table-wrapper table {
            border-collapse: collapse;
            width: 100%;
            min-width: 900px;
            font-size: 0.86rem;
        }
        .mobile-table-wrapper th {
            position: sticky;
            top: 0;
            background: #f8fafc;
            z-index: 1;
            white-space: nowrap;
            padding: 7px;
            border-bottom: 1px solid #e5e7eb;
        }
        .mobile-table-wrapper td {
            white-space: nowrap;
            padding: 7px;
            border-bottom: 1px solid #f1f5f9;
        }
        .mobile-table-wrapper a {
            font-weight: 700;
            text-decoration: none;
        }
        @media (max-width: 768px) {
            .mobile-table-wrapper table {
                font-size: 0.78rem;
                min-width: 780px;
            }
            .mobile-table-wrapper th,
            .mobile-table-wrapper td {
                padding: 5px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f'<div class="mobile-table-wrapper">{html}</div>',
        unsafe_allow_html=True
    )


def render_stock_detail_page(symbol, regime, capital, max_loss, chart_period):
    symbol = str(symbol).strip().upper()

    if is_excluded_symbol(symbol):
        st.error(f"{symbol} is blocked by your exclusion rules.")
        st.stop()

    result = analyze_stock(symbol, regime=regime)

    if not result:
        st.error(f"No data available for {symbol}.")
        st.stop()

    shares, capital_needed, actual_loss = position_size(
        capital,
        max_loss,
        result["Entry"],
        result["Stop"]
    )

    result["Shares"] = shares
    result["Capital Needed"] = capital_needed
    result["Max Loss"] = actual_loss
    result["Trade Grade"] = trade_grade(result)

    st.title(f"🔎 Deep AI Detail View: {symbol}")
    st.success(APP_VERSION)

    eastern_now = datetime.now(ZoneInfo("America/New_York"))
    st.caption(
        f"Opened: {eastern_now.strftime('%Y-%m-%d %I:%M:%S %p ET')}"
    )

    st.markdown(f"## Decision: {result['Timing Signal']}")
    st.info(result["Timing Reason"])
    st.write(result["AI Summary"])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Price", result["Price"])
    c2.metric("Trade Grade", result["Trade Grade"])
    c3.metric("Confidence", result["Confidence"])
    c4.metric("R/R", result["R/R"])
    c5.metric("Setup Score", result["Setup Score"])

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Entry", result["Entry"])
    c7.metric("Target", result["Target"])
    c8.metric("Stop", result["Stop"])
    c9.metric("Max Loss", f"${result['Max Loss']:,.2f}")

    c10, c11, c12, c13 = st.columns(4)
    c10.metric("RSI", result["RSI"])
    c11.metric("Volume Ratio", result["Volume Ratio"])
    c12.metric("Relative Strength", f"{result['Relative Strength %']}%")
    c13.metric("Earnings Risk", result["Earnings Risk"])

    st.markdown("### 📈 Chart")
    make_chart(symbol, result, chart_period)

    st.markdown("### 🧠 Full AI Context")
    context_points = [
        f"Market regime: **{regime}**",
        f"Timing signal: **{result['Timing Signal']}** — {result['Timing Reason']}",
        f"Intraday momentum: **{result['Intraday']}** ({result['Intraday %']}%)",
        f"Trade grade: **{result['Trade Grade']}**",
        f"Confidence score: **{result['Confidence']}**",
        f"Risk/reward: **{result['R/R']}**",
        f"Near entry: **{result['Near Entry']}**",
        f"RSI: **{result['RSI']}**",
        f"Volume ratio: **{result['Volume Ratio']}**",
        f"Relative strength vs QQQ: **{result['Relative Strength %']}%** ({result['Relative Strength']})",
        f"Earnings risk: **{result['Earnings Risk']}** — {result['Earnings Note']}",
    ]

    for point in context_points:
        st.write(f"- {point}")

    st.markdown("### ⚠️ Why NOT to buy / Risk factors")
    for risk in build_risk_factors(result):
        st.write(f"- {risk}")

    st.markdown("### ✅ Why AI likes it")
    for reason in result["Score Reasons"].split(" | "):
        st.write(f"- {reason}")

    st.markdown("### 🧭 Suggested Exit Strategy")
    st.write(exit_strategy(result))

    st.markdown("### 🧪 Paper Trade Guidance")
    st.write(
        f"Suggested paper trade: {shares} shares near ${result['Entry']} "
        f"with stop near ${result['Stop']} and target near ${result['Target']}."
    )

    if st.button("🧪 Add This to Paper Trades"):
        paper_trades = store.get("paper_trades", [])
        paper_trades.append({
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Symbol": symbol,
            "Entry": float(result["Entry"]),
            "Exit": 0.0,
            "Shares": float(shares),
            "Status": "Open",
            "P/L": 0.0,
            "Notes": f"Auto-added from V25 Deep Detail View. Signal: {result['Timing Signal']}"
        })
        store["paper_trades"] = paper_trades
        save_store(store)
        st.success(f"Added {symbol} to Paper Trading Simulator.")

    st.stop()


def render_etf_detail_page(symbol, regime, chart_period):
    symbol = str(symbol).strip().upper()

    if is_blocked_etf(symbol):
        st.error(f"{symbol} is blocked by your ETF exclusion rules.")
        st.stop()

    label = ETF_UNIVERSE.get(symbol, "ETF")
    result = analyze_etf_entry(symbol, label, regime)

    if not result:
        st.error(f"No ETF data available for {symbol}.")
        st.stop()

    st.title(f"🔎 ETF Deep Detail View: {symbol}")
    st.success(APP_VERSION)

    eastern_now = datetime.now(ZoneInfo("America/New_York"))
    st.caption(
        f"Opened: {eastern_now.strftime('%Y-%m-%d %I:%M:%S %p ET')}"
    )

    st.markdown(f"## Decision: {result['Decision']}")
    st.info(
        f"{symbol} ({result['Category']}) is rated {result['Grade']} "
        f"with score {result['Score']}."
    )

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Price", result["Price"])
    e2.metric("Grade", result["Grade"])
    e3.metric("Score", result["Score"])
    e4.metric("Risk Level", result["Risk Level"])

    e5, e6, e7, e8 = st.columns(4)
    e5.metric("Entry Zone", result["Entry Zone"])
    e6.metric("Add-on Pullback", result["Add-on Pullback Zone"])
    e7.metric("RSI", result["RSI"])
    e8.metric("Volume Ratio", result["Volume Ratio"])

    data = get_stock_data(symbol, period=chart_period, interval="5m" if chart_period in ["1d", "5d"] else "1d")

    if data is not None and not data.empty:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=data.index,
            open=data["Open"],
            high=data["High"],
            low=data["Low"],
            close=data["Close"],
            name=symbol
        ))
        fig.add_hline(y=result["Entry Zone"], line_dash="dot", annotation_text="Entry Zone")
        fig.add_hline(y=result["Add-on Pullback Zone"], line_dash="dot", annotation_text="Add-on Pullback")
        fig.update_layout(
            height=520,
            xaxis_rangeslider_visible=False,
            title=f"{symbol} ETF Chart"
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            key=f"etf_chart_{symbol}_{chart_period}_{datetime.now().timestamp()}"
        )

    st.markdown("### Why AI likes this ETF")
    for reason in str(result["Reasons"]).split(" | "):
        st.write(f"- {reason}")

    st.markdown("### ETF Risk Factors")
    for risk in str(result["Risk Factors"]).split(" | "):
        st.write(f"- {risk}")

    st.markdown("### Suggested ETF Entry Plan")
    st.write(
        f"Consider staged ETF entry near ${result['Entry Zone']}. "
        f"If the ETF pulls back further, the add-on zone is near ${result['Add-on Pullback Zone']}. "
        f"This is designed for scaling, not an all-in trade."
    )

    st.stop()


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
eastern_now = datetime.now(ZoneInfo("America/New_York"))

market_status = (
    "🟢 Market Open"
    if (
        eastern_now.weekday() < 5
        and (
            eastern_now.hour > 9
            or (
                eastern_now.hour == 9
                and eastern_now.minute >= 30
            )
        )
        and eastern_now.hour < 16
    )
    else "🔴 Market Closed"
)

st.caption(
    f"Last refresh: "
    f"{eastern_now.strftime('%Y-%m-%d %I:%M:%S %p ET')} | "
    f"{market_status} | "
    f"Auto-refresh every 60 seconds"
)

regime, regime_reason = get_market_regime()

# =====================
# V25 DETAIL VIEW ROUTING
# =====================
detail_symbol = st.query_params.get("detail", "")
etf_detail_symbol = st.query_params.get("etf_detail", "")

if detail_symbol:
    render_stock_detail_page(detail_symbol, regime, capital, max_loss, chart_period)

if etf_detail_symbol:
    render_etf_detail_page(etf_detail_symbol, regime, chart_period)


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

df["Trade Grade"] = df.apply(trade_grade, axis=1)


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
                "Time": now.strftime("%Y-%m-%d %I:%M:%S %p"),
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

sector_df_for_summary = get_sector_strength()
best_sector_label = "Unavailable"
if not sector_df_for_summary.empty:
    best_sector_label = f"{sector_df_for_summary.iloc[0]['Sector']} ({sector_df_for_summary.iloc[0]['ETF']})"

daily_risk_level = (
    "High" if regime == "Bearish / Risk-Off"
    else "Moderate" if buy_now_count == 0
    else "Moderate / Opportunity"
)

st.markdown("### 🧠 Daily AI Market Summary")
s1, s2, s3 = st.columns(3)
s1.metric("Best Sector", best_sector_label)
s2.metric("Risk Level", daily_risk_level)
s3.metric("Primary Focus", top_pick["Symbol"])

st.write(
    f"Market trend is **{regime}**. Best current candidate is **{top_pick['Symbol']}** "
    f"with a **{top_pick['Timing Signal']}** signal and trade grade **{top_pick['Trade Grade']}**."
)

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

    st.markdown("### ⚠️ Why NOT to buy / Risk factors")
    for risk in build_risk_factors(best):
        st.write(f"- {risk}")

    st.markdown("### 🧭 Suggested exit strategy")
    st.write(exit_strategy(best))

    with st.expander("Full AI scoring reasons", expanded=False):
        for reason in best["Score Reasons"].split(" | "):
            st.write(f"- {reason}")

    st.markdown("### Candidate chart")
    make_chart(best["Symbol"], best, chart_period)

    if daily_plan["decision"] != "BUY NOW CANDIDATE":
        st.warning("This is not a forced buy signal. Use price alerts and paper trading first if the entry is not clean.")

    if st.button("🧪 Paper Trade This Candidate"):
        paper_trades = store.get("paper_trades", [])
        paper_trades.append({
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Symbol": best["Symbol"],
            "Entry": float(best["Entry"]),
            "Exit": 0.0,
            "Shares": float(best["Shares"]),
            "Status": "Open",
            "P/L": 0.0,
            "Notes": f"Auto-added from Daily AI Swing Trade Plan. Decision: {daily_plan['decision']}"
        })
        store["paper_trades"] = paper_trades
        save_store(store)
        st.success(f"Added {best['Symbol']} to Paper Trading Simulator.")
        st.rerun()

st.divider()


# =====================
# TOP PICKS
# =====================
st.subheader("🏆 Ranked Swing Trade Candidates")
st.caption("Compact view: click any ticker to open the full AI Detail View in a new tab. Long explanations are hidden from this table for easier navigation.")

ranked = df.sort_values(["Setup Score", "Confidence", "R/R"], ascending=False)
render_clickable_table(ranked.head(10), symbol_col="Symbol")

st.divider()

# =====================
# SECTOR ROTATION
# =====================
st.subheader("🧭 Sector Rotation Heatmap")

sector_df = get_sector_strength()
if not sector_df.empty:
    st.dataframe(sector_df, use_container_width=True)
    strongest = sector_df.iloc[0]
    weakest = sector_df.iloc[-1]
    c1, c2 = st.columns(2)
    c1.metric("Strongest Sector", f"{strongest['Sector']} ({strongest['ETF']})", f"{strongest['Strength Score']} score")
    c2.metric("Weakest Sector", f"{weakest['Sector']} ({weakest['ETF']})", f"{weakest['Strength Score']} score")
else:
    st.info("Sector strength data unavailable right now.")

st.divider()

# =====================
# ETF ENTRY TIMING
# =====================
st.subheader("📦 ETF Fund Entry Timing")

st.caption(
    "This section scans approved ETFs only. It avoids financial-sector, gambling, alcohol, "
    "and entertainment/media-focused ETFs based on your rules."
)

etf_df = build_etf_entry_table(regime)

if etf_df.empty:
    st.info("ETF entry data is unavailable right now.")
else:
    best_etf = etf_df.iloc[0]

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Best ETF Candidate", best_etf["ETF"])
    e2.metric("Decision", best_etf["Decision"])
    e3.metric("Grade", best_etf["Grade"])
    e4.metric("Score", best_etf["Score"])

    st.info(
        f"{best_etf['ETF']} ({best_etf['Category']}) is currently ranked highest. "
        f"Entry zone: ${best_etf['Entry Zone']}. Add-on pullback zone: ${best_etf['Add-on Pullback Zone']}."
    )

    st.markdown("### Why this ETF is ranked highest")
    for reason in str(best_etf["Reasons"]).split(" | "):
        st.write(f"- {reason}")

    st.markdown("### ETF risk factors")
    for risk in str(best_etf["Risk Factors"]).split(" | "):
        st.write(f"- {risk}")

    st.markdown("### Approved ETF Ranking")
st.caption("Compact view: click any ETF ticker to open the full ETF Detail View in a new tab.")
    render_clickable_table(etf_df, symbol_col="ETF", etf=True)

    with st.expander("ETF Universe Used", expanded=False):
        st.write("Approved ETFs scanned:")
        st.write(", ".join([f"{k} ({v})" for k, v in ETF_UNIVERSE.items()]))
        st.write("Blocked ETF examples:")
        st.write(", ".join(sorted(BLOCKED_ETFS)))

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
    render_clickable_table(watch_df, symbol_col="Symbol")

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

    with st.expander("⚠️ Why NOT to buy / Risk factors", expanded=True):
        for risk in build_risk_factors(row):
            st.write(f"- {risk}")

    with st.expander("🧭 Suggested Exit Strategy", expanded=False):
        st.write(exit_strategy(row))

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
    render_clickable_table(buy_now, symbol_col="Symbol")

with st.expander("🎯 Best Swing Candidates", expanded=True):
    render_clickable_table(best_candidate, symbol_col="Symbol")

with st.expander("⏳ Wait For Entry", expanded=True):
    render_clickable_table(wait_entry, symbol_col="Symbol")

with st.expander("👀 Watchlist Only", expanded=False):
    render_clickable_table(watch_only, symbol_col="Symbol")

with st.expander("⚠️ Avoid", expanded=False):
    render_clickable_table(avoid, symbol_col="Symbol")

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
                "Created": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
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
                "Created": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
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

### V23 Risk Engine
- Earnings within 3 days downgrades risky BUY NOW setups.
- Weak volume, high RSI, overextended intraday moves, and weak relative strength are shown as risk factors.
- Trade Grade gives a simplified A+ to D quality rating.
- Sector Rotation shows where market strength is concentrated.

### V24 ETF Entry Timing
- Scans approved ETFs only.
- Blocks financial-sector, gambling, alcohol, and entertainment/media-focused ETF examples.
- Gives ETF entry decisions such as GOOD ETF ENTRY ZONE, WATCH / SCALE IN SLOWLY, WAIT, or AVOID.
- ETF signals are for staged entries, not all-in trades.

### V25 Deep Detail View
- Click a stock ticker to open a full AI detail page in a new tab.
- Click an ETF ticker to open a full ETF entry timing page in a new tab.
- Deep views include chart, risk factors, context, entry/target/stop, and paper trade guidance.

### Difference between Portfolio and Paper Trading
- **Portfolio Tracker** = real or actual holdings you want to monitor
- **Paper Trading Simulator** = fake practice trades to test the AI system

### Persistence Fix
This version saves watchlist, paper trades, alerts, portfolio, and journal to:
`dashboard_store.json`

It also keeps login active through the URL auth token after refresh.
""")
