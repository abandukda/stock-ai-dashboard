import os
import re
import xml.etree.ElementTree as ET
import math
import datetime as dt
import json
import csv
from pathlib import Path
from urllib.parse import quote_plus
from io import StringIO

import pandas as pd
import streamlit as st
import requests
import yfinance as yf
import plotly.graph_objects as go


APP_VERSION = "V49.3 Performance Stability Fix"


# =========================
# V43.2.1 STRICT ENVIRONMENT VARIABLE NAMES
# =========================
# Exact Render variable names supported. No legacy aliases.
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
GUEST_PASSWORD = os.getenv("GUEST_PASSWORD", "").strip()

FMP_API_KEY = os.getenv("FMP_API_KEY", "").strip()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "").strip()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL", "").strip()
DATA_DIR = os.getenv("DATA_DIR", ".").strip() or "."

def strict_env(name, default=""):
    """Read one exact environment variable name only."""
    return os.getenv(name, default).strip()

def strict_env_len(name):
    return len(strict_env(name, ""))

def strict_env_detected(name):
    return bool(strict_env(name, ""))


st.set_page_config(
    page_title="AI Trading Dashboard",
    page_icon="📈",
    layout="wide",
)

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
FMP_API_KEY = os.getenv("FMP_API_KEY", "").strip()
FINNHUB_API_KEY = (os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_TOKEN") or "").strip()
NEWSAPI_KEY = (os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY") or "").strip()
ALPHA_VANTAGE_API_KEY = (os.getenv("ALPHA_VANTAGE_API_KEY") or os.getenv("ALPHAVANTAGE_API_KEY") or "").strip()

# =========================
# V49.3 SECRET / ENV RECONCILIATION
# =========================
# Lets Streamlit secrets override environment variables when present,
# while keeping Render env vars working normally.
try:
    if hasattr(st, "secrets"):
        for _k in ["FMP_API_KEY", "FINNHUB_API_KEY", "NEWSAPI_KEY", "ALPHA_VANTAGE_API_KEY", "SEC_USER_AGENT"]:
            if _k in st.secrets and str(st.secrets[_k]).strip():
                globals()[_k] = str(st.secrets[_k]).strip()
except Exception:
    pass

FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
PRESCREEN_FILE = DATA_DIR / "market_prescreen.json"
STATE_FILE = DATA_DIR / "market_scan_state.json"
UNIVERSE_FILE = DATA_DIR / "total_market_universe.json"

TOP_IDEAS_FILE = DATA_DIR / "top_ai_ideas.json"
RECOVERY_SCAN_FILE = DATA_DIR / "recovery_scan.json"
WATCHLIST_SCAN_FILE = DATA_DIR / "watchlist_scan.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
ETF_SCAN_FILE = DATA_DIR / "etf_scan.json"

MIN_UPSIDE_PCT = float(os.getenv("MIN_UPSIDE_PCT", "0"))

VIEWER_PASSWORD = (os.getenv("VIEWER_PASSWORD") or os.getenv("VIEW_PASSWORD") or os.getenv("GUEST_PASSWORD") or "").strip()
VIEWER_USERNAME = (os.getenv("VIEWER_USERNAME") or os.getenv("GUEST_USERNAME") or "guest").strip()
ADMIN_PASSWORD = (os.getenv("APP_PASSWORD") or os.getenv("ADMIN_PASSWORD") or "").strip()


def get_user_role():
    if "user_role" not in st.session_state:
        st.session_state["user_role"] = "admin" if not VIEWER_PASSWORD and not ADMIN_PASSWORD else None
    return st.session_state.get("user_role")



def is_viewer():
    return get_user_role() == "viewer"



# =========================
# SAFE HELPERS
# =========================

def safe_number(value, default=0.0):
    try:
        if value is None:
            return default
        if value == "":
            return default
        value = float(value)
        if pd.isna(value):
            return default
        return value
    except Exception:
        return default


def safe_text(value, default=""):
    if value is None:
        return default
    text = str(value)
    if text.lower() in {"nan", "none", "null"}:
        return default
    return text


def fmt_money(value):
    value = safe_number(value, None)
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.2f}"


def fmt_pct(value):
    value = safe_number(value, None)
    if value is None:
        return "N/A"
    return f"{value:.1f}%"



def setup_label(score):
    score = safe_number(score, 0)
    if score >= 95:
        return "🟢 Elite Setup"
    if score >= 90:
        return "🟢 Strong Buy Candidate"
    if score >= 85:
        return "🟡 Attractive Setup"
    if score >= 75:
        return "🔵 Watchlist Setup"
    if score >= 65:
        return "⚪ Neutral Setup"
    return "🔴 Speculative Setup"


def analyst_support_label(value):
    value = safe_number(value, None)
    if value is None:
        return "Coverage-based"
    if value >= 70:
        return f"Bullish ({value:.0f}/100)"
    if value >= 45:
        return f"Constructive ({value:.0f}/100)"
    if value >= 25:
        return f"Mixed ({value:.0f}/100)"
    return f"Weak ({value:.0f}/100)"


def sentiment_badge(value):
    text = safe_text(value, "N/A")
    if text.lower() == "positive":
        return "🟢 Positive"
    if text.lower() == "negative":
        return "🔴 Negative"
    if text.lower() == "neutral":
        return "⚪ Neutral"
    return text


def compact_reason_list(text, max_items=5):
    text = safe_text(text, "")
    if not text:
        return []
    parts = []
    for chunk in text.replace(".", ";").split(";"):
        clean = chunk.strip()
        if clean:
            parts.append(clean)
    return parts[:max_items]



def format_agent_score(score):
    value = safe_number(score, None)
    if value is None:
        return "N/A"
    value = int(round(value))
    if value >= 80:
        return f"🟢 {value}/100"
    if value >= 60:
        return f"🟡 {value}/100"
    if value >= 45:
        return f"⚪ {value}/100"
    return f"🔴 {value}/100"


def safe_list(value):
    if isinstance(value, list):
        return value
    return []


def render_agent_card(agent):
    if not isinstance(agent, dict):
        return
    name = safe_text(agent.get("agent"), "Agent")
    score = agent.get("score")
    status = safe_text(agent.get("status"), "N/A")
    summary = safe_text(agent.get("summary"), "No summary available.")
    impact = safe_text(agent.get("impact"), "Neutral")
    data_used = safe_text(agent.get("data_used"), "")
    findings = safe_list(agent.get("findings"))

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        c1.markdown(f"#### {name}")
        c2.markdown(f"**{format_agent_score(score)}**")
        c3.markdown(f"**Impact:** {impact}")
        st.caption(f"Status: {status}" + (f" · Data used: {data_used}" if data_used else ""))
        st.write(summary)
        if findings:
            st.markdown("**What AI found:**")
            for item in findings[:6]:
                st.markdown(f"• {safe_text(item)}")



def metric_label(kind, value):
    value = safe_number(value, None)
    if value is None:
        return "N/A"
    if kind == "revenue":
        if value < 0: return "🔴 Declining"
        if value < 10: return "🟡 Slow"
        if value < 20: return "🟢 Healthy"
        if value < 40: return "🟢 Strong"
        return "🟢 Exceptional"
    if kind == "earnings":
        if value < 0: return "🔴 Concern"
        if value < 10: return "🟡 Stable"
        if value < 20: return "🟢 Good"
        return "🟢 Strong"
    if kind == "pe":
        if value <= 0: return "N/A"
        if value < 15: return "🟢 Cheap"
        if value <= 25: return "🟢 Reasonable"
        if value <= 40: return "🟡 Expensive"
        return "🔴 Very expensive"
    if kind == "peg":
        if value <= 0: return "N/A"
        if value < 1: return "🟢 Excellent / undervalued"
        if value <= 2: return "🟡 Fair"
        return "🔴 Expensive"
    if kind == "rsi":
        if value < 30: return "🟡 Oversold"
        if value < 50: return "🟡 Weak / recovering"
        if value <= 70: return "🟢 Healthy"
        return "🔴 Overbought"
    if kind == "volume":
        if value < 0.75: return "🔴 Light"
        if value < 1.25: return "🟡 Normal"
        if value < 2: return "🟢 Above average"
        return "🟢 Strong"
    if kind == "atr":
        if value < 2: return "🟢 Low volatility"
        if value <= 5: return "🟢 Tradable"
        if value <= 8: return "🟡 Elevated"
        return "🔴 High risk"
    if kind == "upside":
        if value < 0: return "🔴 Downside"
        if value < 10: return "🟡 Limited"
        if value < 25: return "🟢 Moderate"
        if value < 50: return "🟢 Strong"
        return "🟡 Very high / higher uncertainty"
    return "N/A"


def metric_card(title, value, label, meaning, ranges, take):
    st.markdown(f"**{title}: {value} — {label}**")
    st.caption(f"**What it means:** {meaning}")
    st.caption(f"**Good/bad range:** {ranges}")
    st.caption(f"**AI take:** {take}")
    st.write("")


def render_metric_education(row):
    raw = row.get("Raw", {})
    raw = raw if isinstance(raw, dict) else {}

    st.markdown("### 📚 Metric Education")
    st.caption("Plain-English definitions, good/bad ranges, and how to interpret this stock's readings.")

    rev = pick(raw, "revenue_growth", "Revenue Growth", default=None)
    rev = safe_number(rev, None)
    if rev is not None:
        if abs(rev) <= 2:
            rev = rev * 100
        metric_card(
            "Revenue growth",
            f"{rev:.1f}%",
            metric_label("revenue", rev),
            "How fast the company's sales are growing.",
            "<0% declining · 0-10% slow · 10-20% healthy · 20-40% strong · 40%+ exceptional",
            "Strong revenue growth supports the long-term thesis if profitability and cash flow are not weakening."
        )

    earn = pick(raw, "earnings_growth", "Earnings Growth", default=None)
    earn = safe_number(earn, None)
    if earn is not None:
        if abs(earn) <= 2:
            earn = earn * 100
        metric_card(
            "Earnings growth",
            f"{earn:.1f}%",
            metric_label("earnings", earn),
            "How fast profits are growing.",
            "Negative = concern · 0-10% stable · 10-20% good · 20%+ strong",
            "Positive earnings growth confirms the business is converting sales into profit."
        )

    pe = safe_number(pick(raw, "forward_pe", "Forward PE", default=None), None)
    if pe is not None and pe > 0:
        metric_card(
            "Forward PE",
            f"{pe:.1f}",
            metric_label("pe", pe),
            "How much investors pay today for $1 of expected earnings next year.",
            "<15 cheap · 15-25 reasonable · 25-40 expensive · 40+ very expensive",
            "Lower is generally better, but high-growth companies can justify higher PE ratios."
        )

    peg = safe_number(pick(raw, "peg_ratio", "PEG Ratio", default=None), None)
    if peg is not None and peg > 0:
        metric_card(
            "PEG ratio",
            f"{peg:.2f}",
            metric_label("peg", peg),
            "PEG compares valuation to growth.",
            "<1 undervalued · 1-2 fair · 2+ expensive",
            "A PEG below 1 can suggest the stock is inexpensive relative to its growth."
        )

    rsi = safe_number(row.get("RSI"), None)
    if rsi is not None and rsi > 0:
        metric_card(
            "RSI",
            f"{rsi:.1f}",
            metric_label("rsi", rsi),
            "RSI measures price momentum on a 0-100 scale.",
            "<30 oversold · 30-50 weak/recovering · 50-70 healthy · 70+ overbought",
            "Healthy RSI suggests positive momentum without excessive overheating."
        )

    vol = safe_number(row.get("Volume Ratio"), None)
    if vol is not None and vol > 0:
        metric_card(
            "Volume ratio",
            f"{vol:.2f}x",
            metric_label("volume", vol),
            "Compares current/recent volume to average volume.",
            "<0.75 light · 0.75-1.25 normal · 1.25-2 above average · 2+ strong",
            "Above-average volume suggests broader participation behind the move."
        )

    atr = safe_number(row.get("ATR %"), None)
    if atr is not None and atr > 0:
        metric_card(
            "ATR %",
            f"{atr:.1f}%",
            metric_label("atr", atr),
            "ATR estimates normal price volatility.",
            "<2% low · 2-5% tradable · 5-8% elevated · 8%+ high risk",
            "Higher ATR means bigger swings, so position sizing should be smaller."
        )

    upside = safe_number(row.get("Target Upside %"), None)
    if upside is not None:
        metric_card(
            "Target upside",
            fmt_pct(upside),
            metric_label("upside", upside),
            "Potential upside from current price to AI fair value.",
            "<10% limited · 10-25% moderate · 25-50% strong · 50%+ high upside but higher uncertainty",
            "Very high upside is attractive but should be confirmed by fundamentals, analysts, and risk signals."
        )

    st.markdown("### 🧮 AI vs Analyst Target")
    price = safe_number(row.get("Price"), 0)
    analyst = safe_number(row.get("Analyst Target"), 0)
    ai_value = safe_number(row.get("AI Fair Value"), 0)
    st.markdown(f"**Current Price:** {fmt_money(price)}")
    st.markdown(f"**Analyst Target:** {fmt_money(analyst) if analyst else 'N/A'}")
    st.markdown(f"**AI Fair Value:** {fmt_money(ai_value) if ai_value else 'N/A'}")
    if analyst and ai_value:
        gap = ((ai_value - analyst) / analyst) * 100
        st.markdown(f"**AI vs Analyst Gap:** {gap:.1f}%")
        if gap > 60:
            st.warning("AI is much more optimistic than Wall Street. Treat this as higher upside but higher uncertainty.")
        elif gap > 20:
            st.info("AI is more optimistic than analysts, likely due to growth, valuation, or trend factors.")
        elif gap < -20:
            st.warning("AI is more conservative than analysts, likely due to technical or risk concerns.")
        else:
            st.success("AI fair value broadly agrees with analyst expectations.")


def educational_bottom_line(row):
    score = safe_number(row.get("Final Conviction"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    support = safe_text(row.get("Analyst Support"), "N/A")
    news = safe_text(row.get("News Sentiment"), "N/A")

    positives = []
    cautions = []
    if score >= 90:
        positives.append("high AI conviction")
    if upside >= 25:
        positives.append("strong upside to AI fair value")
    elif upside < 10:
        cautions.append("limited upside")
    if "Bullish" in support or "Constructive" in support:
        positives.append("supportive analyst view")
    if "Positive" in news:
        positives.append("positive news flow")
    if "Negative" in news:
        cautions.append("negative news flow")
    if not positives:
        positives.append("some supportive signals")
    if not cautions:
        cautions.append("normal market and execution risk")
    return f"Bottom line: This setup is supported by {', '.join(positives)}. Watch for {', '.join(cautions)}."


def tooltip_md():
    return """
**Column Guide**

- **Final Conviction:** AI score using trend, momentum, liquidity, valuation/growth context, analyst support, news, and risk.
- **Setup Rating:** Plain-English label for the conviction score.
- **Analyst Target:** Average Wall Street/Finnhub target when available.
- **AI Fair Value:** Internal AI estimate using analyst targets, growth, valuation, technicals, volume, and risk.
- **Target Upside %:** Difference between AI Fair Value and current price.
- **Analyst Support:** Finnhub analyst recommendation strength.
- **News Sentiment:** Recent headline tone from NewsAPI.
"""


def pick(raw, *keys, default=None):
    if not isinstance(raw, dict):
        return default
    for key in keys:
        if key in raw and raw.get(key) not in (None, "", "Unknown", "N/A"):
            return raw.get(key)
    return default


def read_json_file(path: Path):
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def read_state():
    data = read_json_file(STATE_FILE)
    return data if isinstance(data, dict) else {}


def normalize_rows(data):
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            return data["rows"]
        if isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data.get("symbols"), list):
            return [{"symbol": s} for s in data["symbols"]]
        return []
    if isinstance(data, list):
        return data
    return []


# =========================
# DATA NORMALIZATION
# =========================

def price_bucket(price):
    price = safe_number(price, 0)
    if price <= 0:
        return "Unknown"
    if price < 25:
        return "Lower"
    if price < 100:
        return "Mid"
    if price < 300:
        return "Higher"
    return "Premium"


def opportunity_bucket(row):
    price = safe_number(row.get("Price"), 0)
    rsi = safe_number(row.get("RSI"), 50)
    twenty = safe_number(row.get("20D %"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    score = safe_number(row.get("Final Conviction"), 0)

    if score >= 85 and upside >= 10:
        return "Top AI Opportunity"
    if rsi < 45 and twenty < 0 and upside >= 8:
        return "Recovery / Reversal"
    if price <= 25:
        return "Lower Price"
    if price <= 100:
        return "Mid Price"
    return "Higher Price"


def normalize_scan_row(raw):
    ticker = safe_text(pick(raw, "Ticker", "ticker", "symbol", default="")).upper()
    company = safe_text(pick(raw, "Company", "company", "company_name", "name", default=ticker), ticker)

    price = safe_number(pick(raw, "Price", "price", "current_price", "last_price", default=0), 0)
    target = safe_number(pick(raw, "AI Fair Value", "ai_base_target", "target", "Target", default=0), 0)
    bull = safe_number(pick(raw, "AI Bull Case", "ai_bull_target", "target_2", default=0), 0)
    bear = safe_number(pick(raw, "AI Bear Case", "ai_bear_target", default=0), 0)

    expected_upside = pick(raw, "Target Upside %", "expected_upside_pct", "upside", "analyst_upside_pct", default=None)
    expected_upside = safe_number(expected_upside, None)
    if expected_upside is None and price and target:
        expected_upside = ((target - price) / price) * 100

    # Critical V40.2 fix:
    # Respect scanner conviction first. Do NOT recalculate synthetic 99 scores inside app.py.
    score = safe_number(
        pick(
            raw,
            "Final Conviction",
            "conviction",
            "conviction_score",
            "ai_confidence",
            "confidence",
            "ai_score",
            "score",
            default=0,
        ),
        0,
    )
    score = int(round(score)) if score else 0

    market_cap = safe_number(pick(raw, "Market Cap", "market_cap", default=0), 0)
    dollar_volume = safe_number(pick(raw, "Dollar Volume", "dollar_volume", default=0), 0)

    row = {
        "Ticker": ticker,
        "Company": company,
        "Sector": safe_text(pick(raw, "Sector", "sector", default="Unknown"), "Unknown"),
        "Industry": safe_text(pick(raw, "Industry", "industry", default="Unknown"), "Unknown"),
        "Price": price,
        "Final Conviction": score,
        "Setup Rating": setup_label(score),
        "AI Confidence": score,
        "AI Fair Value": target,
        "AI Bull Case": bull,
        "AI Bear Case": bear,
        "Target Upside %": expected_upside if expected_upside is not None else 0,
        "Analyst Target": safe_number(pick(raw, "Analyst Target", "analyst_target_mean", default=0), 0),
        "Analyst High": safe_number(pick(raw, "Analyst High", "analyst_target_high", default=0), 0),
        "Analyst Low": safe_number(pick(raw, "Analyst Low", "analyst_target_low", default=0), 0),
        "Analyst Count": int(safe_number(pick(raw, "Analyst Count", "analyst_count", default=0), 0)),
        "Recommendation": safe_text(pick(raw, "Recommendation", "recommendation_key", default="N/A"), "N/A"),
        "Analyst Support": safe_text(pick(raw, "analyst_support_label", default=""), "") or analyst_support_label(pick(raw, "analyst_support_score", "Analyst Support", default=None)),
        "Analyst Support Source": safe_text(pick(raw, "analyst_support_source", default=""), ""),
        "News Sentiment": sentiment_badge(pick(raw, "news_sentiment_label", "News Sentiment", default="Neutral")),
        "News Sentiment Source": safe_text(pick(raw, "news_sentiment_source", default=""), ""),
        "Top News": safe_text(pick(raw, "top_news_headline", "Top News", default=""), ""),
        "AI Fair Value Adjustment %": safe_number(pick(raw, "AI Fair Value Adjustment %", "ai_fair_value_adjustment_pct", default=0), 0),
        "Entry Range": safe_text(pick(raw, "Entry Range", "entry_range", default="N/A"), "N/A"),
        "Stop Loss": safe_number(pick(raw, "Stop Loss", "stop_loss", default=0), 0),
        "Target": target,
        "Risk/Reward": safe_number(pick(raw, "Risk/Reward", "risk_reward", default=0), 0),
        "RSI": safe_number(pick(raw, "RSI", "rsi", default=0), 0),
        "ATR %": safe_number(pick(raw, "ATR %", "atr_pct", default=0), 0),
        "Volume Ratio": safe_number(pick(raw, "Volume Ratio", "volume_ratio", default=0), 0),
        "20D %": safe_number(pick(raw, "20D %", "twenty_day_pct", default=0), 0),
        "60D %": safe_number(pick(raw, "60D %", "sixty_day_pct", default=0), 0),
        "Dollar Volume": dollar_volume,
        "Market Cap": market_cap,
        "Price Bucket": price_bucket(price),
        "Investment Thesis": safe_text(
            pick(raw, "Investment Thesis", "investment_thesis", "table_reason", "opportunity_reason", "summary", "guidance", default=""),
            "",
        ),
        "Primary Risk": safe_text(pick(raw, "Primary Risk", "what_could_go_wrong", default=""), ""),
        "Research Summary": safe_text(
            pick(raw, "Why Ranked High", "why_ranked_high", "table_reason", "summary", default=""),
            ""
        ),
        "What Looks Good": safe_text(pick(raw, "What Looks Good", "what_looks_good", default=""), ""),
        "Why Ranked High": safe_text(pick(raw, "Why Ranked High", "why_ranked_high", default=""), ""),
        "Guidance": safe_text(pick(raw, "Guidance", "guidance", "ai_guidance", default=""), ""),
        "Action Note": safe_text(pick(raw, "Action Note", "action_note", default=""), ""),
        "Recovery Score": safe_number(pick(raw, "recovery_score", "Recovery Score", default=0), 0),
        "Recovery Label": safe_text(pick(raw, "recovery_label", "Recovery Label", default=""), ""),
        "Recovery Thesis": safe_text(pick(raw, "recovery_thesis", "Recovery Thesis", default=""), ""),
        "Recovery Drop Reason": safe_text(pick(raw, "recovery_drop_reason", default=""), ""),
        "Recovery Rebound Reason": safe_text(pick(raw, "recovery_rebound_reason", default=""), ""),
        "Recovery Risk": safe_text(pick(raw, "recovery_risk", default=""), ""),
        "AI Committee": pick(raw, "ai_committee", "AI Committee", default={}),
        "Finance Agent Score": safe_number(pick(raw, "finance_agent_score", default=0), 0),
        "Finance Agent Status": safe_text(pick(raw, "finance_agent_status", default=""), ""),
        "Finance Agent Bottom Line": safe_text(pick(raw, "finance_agent_bottom_line", default=""), ""),
        "Finance Agent Findings": pick(raw, "finance_agent_findings", default=[]),
        "Finance Agent Risks": pick(raw, "finance_agent_risks", default=[]),
        "Thesis Strength": safe_text(pick(raw, "thesis_strength", default=""), ""),
        "Latest EPS": safe_number(pick(raw, "latest_eps", default=0), 0),
        "Revenue QoQ %": safe_number(pick(raw, "revenue_qoq_pct", default=0), 0),
        "EPS Beats Last 4": int(safe_number(pick(raw, "eps_beats_last4", default=0), 0)),
        "EPS Misses Last 4": int(safe_number(pick(raw, "eps_misses_last4", default=0), 0)),
        "Debt to Equity": safe_number(pick(raw, "debt_to_equity", default=0), 0),
        "Debt to Assets": safe_number(pick(raw, "debt_to_assets", default=0), 0),
        "Current Ratio": safe_number(pick(raw, "current_ratio", default=0), 0),
        "Gross Margin": safe_number(pick(raw, "gross_profit_margin", default=0), 0),
        "Operating Margin": safe_number(pick(raw, "operating_profit_margin", default=0), 0),
        "Net Margin": safe_number(pick(raw, "net_profit_margin", default=0), 0),
        "Free Cash Flow": safe_number(pick(raw, "free_cash_flow", default=0), 0),
        "Operating Cash Flow": safe_number(pick(raw, "operating_cash_flow", default=0), 0),
        "ROIC": safe_number(pick(raw, "roic", default=0), 0),
        "EV/Sales": safe_number(pick(raw, "ev_to_sales", default=0), 0),
        "Peers": pick(raw, "peer_symbols", default=[]),
        "52W High": safe_number(pick(raw, "high_52w", "52W High", default=0), 0),
        "52W Low": safe_number(pick(raw, "low_52w", "52W Low", default=0), 0),
        "Range Position %": safe_number(pick(raw, "range_position_pct", default=0), 0),
        "Range Position Label": safe_text(pick(raw, "range_position_label", default=""), ""),
        "Distance From 52W High %": safe_number(pick(raw, "distance_from_52w_high_pct", default=0), 0),
        "Distance From 52W Low %": safe_number(pick(raw, "distance_from_52w_low_pct", default=0), 0),
        "Drawdown From High %": safe_number(pick(raw, "drawdown_from_period_high_pct", default=0), 0),
        "Drawdown Label": safe_text(pick(raw, "drawdown_label", default=""), ""),
        "Return 1M %": safe_number(pick(raw, "return_1m_pct", default=0), 0),
        "Return 3M %": safe_number(pick(raw, "return_3m_pct", default=0), 0),
        "Return 6M %": safe_number(pick(raw, "return_6m_pct", default=0), 0),
        "Return 1Y %": safe_number(pick(raw, "return_1y_pct", default=0), 0),
        "Return 3Y %": safe_number(pick(raw, "return_3y_pct", default=0), 0),
        "Return 5Y %": safe_number(pick(raw, "return_5y_pct", default=0), 0),
        "History Days Available": int(safe_number(pick(raw, "history_days_available", default=0), 0)),
        "Price History Note": safe_text(pick(raw, "price_history_note", default=""), ""),
        "Target Source": safe_text(pick(raw, "Target Source", "target_source", default="N/A"), "N/A"),
        "Target Confidence Note": safe_text(pick(raw, "Target Confidence Note", "target_confidence_note", default=""), ""),
        "ETF Screen": safe_text(pick(raw, "etf_preference_screen", "ETF Screen", default=""), ""),
        "Source FMP": bool(pick(raw, "source_fmp_profile", "Source FMP", default=False)),
        "Website": safe_text(pick(raw, "website", "Website", default=""), ""),
        "AI Committee": pick(raw, "ai_committee", default=[]),
        "Thesis Strength": safe_text(pick(raw, "thesis_strength", default=""), ""),
        "Evidence Confidence": safe_text(pick(raw, "evidence_confidence", default="Medium"), "Medium"),
        "Committee Conclusion": safe_text(pick(raw, "committee_conclusion", default=""), ""),
        "Valuation Reconciliation": safe_text(pick(raw, "valuation_reconciliation", default=""), ""),
        "Insider Score": safe_number(pick(raw, "insider_score", default=0), 0),
        "Insider Activity": safe_text(pick(raw, "insider_activity_label", default="N/A"), "N/A"),

        "V42 News Score": pick(raw, "v42_news_score", default=None),
        "V42 News Available": pick(raw, "v42_news_available", default=False),
        "V42 News Summary": safe_text(pick(raw, "v42_news_summary", default=""), ""),
        "V42 News Catalysts": pick(raw, "v42_news_catalysts", default=[]),
        "V42 News Risks": pick(raw, "v42_news_risks", default=[]),
        "V42 News Sources": pick(raw, "v42_news_sources", default=[]),
        "V42 News Direct Headlines": pick(raw, "v42_news_direct_headlines", default=[]),
        "V42 News Indirect Headlines": pick(raw, "v42_news_indirect_headlines", default=[]),
        "V42 SEC Available": pick(raw, "v42_sec_available", default=False),
        "V42 SEC CIK": safe_text(pick(raw, "v42_sec_cik", default=""), ""),
        "Support 1": safe_number(pick(raw, "v42_support_1", default=0), 0),
        "Support 2": safe_number(pick(raw, "v42_support_2", default=0), 0),
        "Resistance 1": safe_number(pick(raw, "v42_resistance_1", default=0), 0),
        "Resistance 2": safe_number(pick(raw, "v42_resistance_2", default=0), 0),
        "Breakout Level": safe_number(pick(raw, "v42_breakout_level", default=0), 0),
        "Pullback Zone": safe_text(pick(raw, "v42_pullback_zone", default=""), ""),
        "Chart Guidance": safe_text(pick(raw, "v42_chart_guidance", default=""), ""),
        "Committee Positive Agents": int(safe_number(pick(raw, "v42_committee_positive_agents", default=0), 0)),
        "Committee Total Agents": int(safe_number(pick(raw, "v42_committee_total_agents", default=0), 0)),
        "V42 Committee Warning": safe_text(pick(raw, "v42_committee_warning", default=""), ""),
        "V42 Translation Warning": safe_text(pick(raw, "v42_translation_warning", default=""), ""),
        "V42 Tier": safe_text(pick(raw, "v42_tier", default=""), ""),
        "V42 Tier Warning": safe_text(pick(raw, "v42_tier_warning", default=""), ""),
        "Raw": raw,
    }

    row["Opportunity Bucket"] = safe_text(pick(raw, "Opportunity Bucket", default=""), "")
    if not row["Opportunity Bucket"]:
        row["Opportunity Bucket"] = opportunity_bucket(row)

    return row


def load_file(path: Path):
    rows = normalize_rows(read_json_file(path))
    normalized = [normalize_scan_row(r) for r in rows if isinstance(r, dict)]
    df = pd.DataFrame(normalized)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "Ticker",
                "Company",
                "Sector",
                "Industry",
                "Price",
                "Final Conviction",
                "AI Fair Value",
                "Target Upside %",
                "Investment Thesis",
            ]
        )

    numeric_cols = [
        "Final Conviction",
        "Target Upside %",
        "Price",
        "Dollar Volume",
        "AI Fair Value",
        "AI Bull Case",
        "AI Bear Case",
        "Analyst Target",
        "Stop Loss",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["Final Conviction"] = df["Final Conviction"].astype(int)

    return df.sort_values(
        ["Final Conviction", "Target Upside %", "Dollar Volume"],
        ascending=[False, False, False],
    )


def load_full_scan():
    return load_file(FULL_SCAN_FILE)


def actionable(df, min_score=35, require_upside=True):
    if df.empty:
        return df

    work = df.copy()
    work = work[work["Final Conviction"] >= min_score]

    if require_upside:
        work = work[work["Target Upside %"].fillna(-999) >= MIN_UPSIDE_PCT * 100]

    return work.sort_values(
        ["Final Conviction", "Target Upside %", "Dollar Volume"],
        ascending=[False, False, False],
    )


def latest_top_ideas():
    """
    V40.4: use fresh market_full_scan.json as source of truth.
    Avoid stale top_ai_ideas.json showing old scores/upside.
    """
    full = actionable(load_full_scan(), min_score=45, require_upside=True)
    return full.head(25)


def latest_recovery():
    recovery = actionable(load_file(RECOVERY_SCAN_FILE), min_score=35, require_upside=True)
    if not recovery.empty:
        return recovery

    full = load_full_scan()
    if full.empty:
        return full

    mask = full["Opportunity Bucket"].eq("Recovery / Reversal")
    return actionable(full[mask].copy(), min_score=35, require_upside=True)


def latest_watchlist_scan():
    watch = load_file(WATCHLIST_SCAN_FILE)
    if not watch.empty:
        return watch

    full = load_full_scan()
    if full.empty or not WATCHLIST_FILE.exists():
        return pd.DataFrame()

    try:
        watchlist_data = read_json_file(WATCHLIST_FILE)
        if isinstance(watchlist_data, dict):
            symbols = watchlist_data.get("symbols", [])
        elif isinstance(watchlist_data, list):
            symbols = watchlist_data
        else:
            symbols = []

        symbols = {str(s).upper() for s in symbols}
        return full[full["Ticker"].isin(symbols)].copy()
    except Exception:
        return pd.DataFrame()


def render_inline_metric_summary(row):
    """
    V41.4.1: Always-visible educational summary.
    Keeps the full explainer expander, but surfaces the most important meanings/ranges directly.
    """
    raw = row.get("Raw", {})
    raw = raw if isinstance(raw, dict) else {}

    rev = pick(raw, "revenue_growth", "Revenue Growth", default=None)
    rev = safe_number(rev, None)
    if rev is not None and abs(rev) <= 2:
        rev *= 100

    earn = pick(raw, "earnings_growth", "Earnings Growth", default=None)
    earn = safe_number(earn, None)
    if earn is not None and abs(earn) <= 2:
        earn *= 100

    pe = safe_number(pick(raw, "forward_pe", "Forward PE", default=None), None)
    peg = safe_number(pick(raw, "peg_ratio", "PEG Ratio", default=None), None)
    rsi = safe_number(row.get("RSI"), None)
    atr = safe_number(row.get("ATR %"), None)
    vol = safe_number(row.get("Volume Ratio"), None)
    upside = safe_number(row.get("Target Upside %"), None)

    with st.container(border=True):
        st.markdown("### 📘 Quick Metric Guide")
        st.caption("These are the key readings from the AI agents with plain-English meaning and good/bad ranges.")

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### 🏢 Fundamentals")
            if rev is not None:
                st.markdown(f"**Revenue Growth:** {rev:.1f}% — {metric_label('revenue', rev)}")
                st.caption("Sales growth. Range: <0 declining · 0-10 slow · 10-20 healthy · 20-40 strong · 40+ exceptional.")
            if earn is not None:
                st.markdown(f"**Earnings Growth:** {earn:.1f}% — {metric_label('earnings', earn)}")
                st.caption("Profit growth. Range: negative concern · 0-10 stable · 10-20 good · 20+ strong.")
            if pe is not None and pe > 0:
                st.markdown(f"**Forward PE:** {pe:.1f} — {metric_label('pe', pe)}")
                st.caption("Price paid for $1 of next year's expected earnings. Range: <15 cheap · 15-25 reasonable · 25-40 expensive · 40+ very expensive.")
            if peg is not None and peg > 0:
                st.markdown(f"**PEG Ratio:** {peg:.2f} — {metric_label('peg', peg)}")
                st.caption("Valuation compared to growth. Range: <1 undervalued · 1-2 fair · 2+ expensive.")

        with c2:
            st.markdown("#### 📈 Technical / Risk")
            if rsi is not None and rsi > 0:
                st.markdown(f"**RSI:** {rsi:.1f} — {metric_label('rsi', rsi)}")
                st.caption("Momentum score. Range: <30 oversold · 30-50 weak/recovering · 50-70 healthy · 70+ overbought.")
            if vol is not None and vol > 0:
                st.markdown(f"**Volume Ratio:** {vol:.2f}x — {metric_label('volume', vol)}")
                st.caption("Volume vs average. Range: <0.75 light · 0.75-1.25 normal · 1.25-2 above average · 2+ strong.")
            if atr is not None and atr > 0:
                st.markdown(f"**ATR %:** {atr:.1f}% — {metric_label('atr', atr)}")
                st.caption("Volatility. Range: <2 low · 2-5 tradable · 5-8 elevated · 8+ high risk.")
            if upside is not None:
                st.markdown(f"**Target Upside:** {fmt_pct(upside)} — {metric_label('upside', upside)}")
                st.caption("Upside to AI fair value. Range: <10 limited · 10-25 moderate · 25-50 strong · 50+ high upside but higher uncertainty.")

        st.markdown("**Plain-English takeaway:**")
        st.info(educational_bottom_line(row))


def fmt_ratio(value):
    value = safe_number(value, None)
    return "N/A" if value is None or value == 0 else f"{value:.2f}"


def fmt_margin(value):
    value = safe_number(value, None)
    if value is None or value == 0:
        return "N/A"
    if abs(value) <= 2:
        value *= 100
    return f"{value:.1f}%"


def render_bullets(items, empty="No detail available."):
    if isinstance(items, str):
        items = compact_reason_list(items, max_items=8)
    if not isinstance(items, list) or not items:
        st.caption(empty)
        return
    for item in items[:10]:
        st.markdown(f"• {safe_text(item)}")


def render_deep_finance_agent(row):
    with st.container(border=True):
        st.markdown("### 💰 Finance Agent — Deep Financial Execution")
        score = int(safe_number(row.get("Finance Agent Score"), 0))
        status = safe_text(row.get("Finance Agent Status"), "N/A")
        thesis = safe_text(row.get("Thesis Strength"), "")
        st.markdown(f"**Score:** {score}/100 · **Status:** {status}" + (f" · **Thesis Strength:** {thesis}" if thesis else ""))
        st.caption("Cross-checks EPS, revenue execution, debt, liquidity, margins, cash flow, valuation, and peer context.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Latest EPS", f"{safe_number(row.get('Latest EPS'), 0):.2f}" if safe_number(row.get("Latest EPS"), 0) else "N/A")
        c2.metric("Revenue QoQ", fmt_pct(row.get("Revenue QoQ %")) if safe_number(row.get("Revenue QoQ %"), 0) else "N/A")
        c3.metric("Debt/Equity", fmt_ratio(row.get("Debt to Equity")))
        c4.metric("Current Ratio", fmt_ratio(row.get("Current Ratio")))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Gross Margin", fmt_margin(row.get("Gross Margin")))
        c6.metric("Operating Margin", fmt_margin(row.get("Operating Margin")))
        c7.metric("Net Margin", fmt_margin(row.get("Net Margin")))
        c8.metric("ROIC", fmt_margin(row.get("ROIC")))

        c9, c10, c11, c12 = st.columns(4)
        c9.metric("EPS Beats/Misses", f"{row.get('EPS Beats Last 4', 0)}/{row.get('EPS Misses Last 4', 0)}")
        c10.metric("FCF", fmt_money(row.get("Free Cash Flow")) if safe_number(row.get("Free Cash Flow"), 0) else "N/A")
        c11.metric("Op. Cash Flow", fmt_money(row.get("Operating Cash Flow")) if safe_number(row.get("Operating Cash Flow"), 0) else "N/A")
        c12.metric("EV/Sales", fmt_ratio(row.get("EV/Sales")))

        st.markdown("**What AI cross-checked:**")
        render_bullets(row.get("Finance Agent Findings"), empty="Finance findings not available yet.")

        st.markdown("**Watch-outs:**")
        render_bullets(row.get("Finance Agent Risks"), empty="No major finance-specific red flags detected.")

        peers = row.get("Peers")
        if isinstance(peers, list) and peers:
            st.markdown(f"**Peer set for comparison:** {', '.join([safe_text(x) for x in peers[:8]])}")
            st.caption("Peer set is used as the foundation for future peer valuation and growth comparison.")

        bottom = safe_text(row.get("Finance Agent Bottom Line"), "")
        if bottom:
            st.info(f"**Finance Agent Bottom Line:** {bottom}")

        with st.expander("📘 What these finance metrics mean", expanded=False):
            st.markdown("""
**EPS:** Earnings per share. Positive and improving EPS usually means profitability is improving.

**Revenue QoQ:** Sequential revenue growth from the prior quarter. Positive is better; repeated declines can signal weakening demand.

**Debt/Equity:** Debt compared to shareholder equity. Under 0.5 is conservative, 0.5-1.5 is manageable, above 1.5 can be risky.

**Current Ratio:** Short-term assets divided by short-term liabilities. Above 1.5 is usually healthy; below 1 can signal liquidity risk.

**Margins:** Gross, operating, and net margins show profitability quality. Higher and stable/improving margins are better.

**Free Cash Flow:** Cash left after operating needs and capital spending. Positive FCF gives the company flexibility.

**ROIC:** Return on invested capital. Higher ROIC means the business is using capital efficiently.

**EV/Sales:** Enterprise value compared to revenue. Lower can be cheaper, but growth and margins matter.
""")


def render_ai_committee_details(row):
    committee = row.get("AI Committee")
    if not isinstance(committee, dict) or not committee:
        return

    with st.expander("🧠 Full AI Committee Agent Details", expanded=False):
        for name, agent in committee.items():
            if not isinstance(agent, dict):
                continue
            st.markdown(f"### {name}")
            st.markdown(
                f"**Score:** {(str(agent.get('score')) + '/100') if agent.get('score') is not None else 'Not scored'} · "
                f"**Status:** {agent.get('status', 'N/A')} · "
                f"**Impact:** {agent.get('impact', 'N/A')}"
            )
            st.caption(f"**Data used:** {agent.get('data_used', 'N/A')}")
            st.write(agent.get("summary", ""))
            render_v425_agent_standard_box(name, agent, row)

            render_v4244_agent_plain_english_box(name, agent, row)
            findings = agent.get("findings") or []
            risks = agent.get("risks") or []
            if findings:
                st.markdown("**Findings:**")
                render_bullets(findings)
            if risks:
                st.markdown("**Risks / limits:**")
                render_bullets(risks)
            bottom = agent.get("bottom_line")
            if bottom:
                st.info(f"**Bottom line:** {bottom}")
            st.markdown("---")


def render_price_history_intelligence(row):
    with st.container(border=True):
        st.markdown("### 📉 Price History Intelligence")

        price = safe_number(row.get("Price"), 0)
        high_52 = safe_number(row.get("52W High"), 0)
        low_52 = safe_number(row.get("52W Low"), 0)
        range_pos = safe_number(row.get("Range Position %"), 0)
        range_label = safe_text(row.get("Range Position Label"), "")
        dist_high = safe_number(row.get("Distance From 52W High %"), 0)
        dist_low = safe_number(row.get("Distance From 52W Low %"), 0)
        drawdown = safe_number(row.get("Drawdown From High %"), 0)
        drawdown_label = safe_text(row.get("Drawdown Label"), "")
        note = safe_text(row.get("Price History Note"), "")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current Price", fmt_money(price))
        c2.metric("52W Low", fmt_money(low_52) if low_52 else "N/A")
        c3.metric("52W High", fmt_money(high_52) if high_52 else "N/A")
        c4.metric("52W Range Position", f"{range_pos:.1f}%" if range_pos else "N/A")

        c5, c6, c7 = st.columns(3)
        c5.metric("From 52W Low", fmt_pct(dist_low) if dist_low else "N/A")
        c6.metric("From 52W High", fmt_pct(dist_high) if dist_high else "N/A")
        c7.metric("Drawdown", fmt_pct(drawdown) if drawdown else "N/A")

        if high_52 and low_52 and price:
            st.progress(min(max(range_pos / 100, 0), 1))
            st.caption(f"Position in 52-week range: {range_label or 'N/A'}. 0% means near low, 100% means near high.")

        returns = {
            "1M": safe_number(row.get("Return 1M %"), 0),
            "3M": safe_number(row.get("Return 3M %"), 0),
            "6M": safe_number(row.get("Return 6M %"), 0),
            "1Y": safe_number(row.get("Return 1Y %"), 0),
            "3Y": safe_number(row.get("Return 3Y %"), 0),
            "5Y": safe_number(row.get("Return 5Y %"), 0),
        }
        return_rows = [{"Period": k, "Return %": v} for k, v in returns.items() if v]
        if return_rows:
            st.markdown("**Multi-period return snapshot**")
            st.dataframe(pd.DataFrame(return_rows), use_container_width=True, hide_index=True)

        if note:
            st.caption(note)

        if range_pos >= 75:
            st.info("AI interpretation: Price is near the upper part of its 52-week range. Upside depends more on earnings growth, news, and valuation support.")
        elif 0 < range_pos <= 35:
            st.info("AI interpretation: Price is closer to the lower part of its 52-week range. This may support a recovery thesis if fundamentals and analyst support remain healthy.")
        elif range_pos:
            st.info("AI interpretation: Price is in the middle of its 52-week range, so confirmation from trend, earnings, and analyst support matters.")

        if drawdown <= -30:
            st.warning("Large drawdown detected. This can create opportunity, but only if the business outlook remains intact.")
        elif drawdown <= -10:
            st.caption("Moderate pullback from recent highs.")


@st.cache_data(ttl=900)
def fetch_chart_history(ticker, period="5y"):
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return pd.DataFrame()
    try:
        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.dropna(subset=["Close"]).copy()
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
        return df
    except Exception:
        return pd.DataFrame()


def render_interactive_price_chart_fixed(row):
    ticker = safe_text(row.get("Ticker"), "").upper()
    if not ticker:
        return

    st.markdown("### 📊 Interactive Price Chart")
    st.caption("Shows price trend, 20/50/200-day averages, true 52-week high/low, analyst target, and AI fair value.")

    period = st.selectbox(
        "Chart range",
        ["6mo", "1y", "3y", "5y"],
        index=3,
        key=chart_instance_key(row, "detail_chart_range"),
    )

    hist = fetch_chart_history(ticker, period=period)
    if hist.empty:
        st.warning("Chart data unavailable for this ticker.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Price"))
    fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA20"], mode="lines", name="SMA 20"))
    fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA50"], mode="lines", name="SMA 50"))
    if hist["SMA200"].notna().any():
        fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA200"], mode="lines", name="SMA 200"))

    close = hist["Close"].dropna()
    high = hist["High"].dropna() if "High" in hist.columns else close
    low = hist["Low"].dropna() if "Low" in hist.columns else close

    high_52 = float(high.tail(min(252, len(high))).max()) if not high.empty else None
    low_52 = float(low.tail(min(252, len(low))).min()) if not low.empty else None
    current = float(close.iloc[-1]) if not close.empty else None

    analyst_target = safe_number(row.get("Analyst Target"), 0)
    ai_target = safe_number(row.get("AI Fair Value"), 0)

    if high_52:
        fig.add_hline(y=high_52, line_dash="dash", annotation_text="52W High", annotation_position="top left")
    if low_52:
        fig.add_hline(y=low_52, line_dash="dash", annotation_text="52W Low", annotation_position="bottom left")
    if analyst_target:
        fig.add_hline(y=analyst_target, line_dash="dot", annotation_text="Analyst Target", annotation_position="top right")
    if ai_target:
        fig.add_hline(y=ai_target, line_dash="dot", annotation_text="AI Fair Value", annotation_position="top right")

    fig.update_layout(
        height=520,
        margin=dict(l=20, r=20, t=40, b=20),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis_title="Date",
        yaxis_title="Price",
    )

    st.plotly_chart(fig, use_container_width=True, key=chart_instance_key(row, "plotly_detail_chart"))

    if current and high_52 and low_52 and high_52 > low_52:
        range_pos = ((current - low_52) / (high_52 - low_52)) * 100
        d_high = ((current - high_52) / high_52) * 100
        d_low = ((current - low_52) / low_52) * 100

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current Price", fmt_money(current))
        c2.metric("True 52W Low", fmt_money(low_52))
        c3.metric("True 52W High", fmt_money(high_52))
        c4.metric("Position in 52W Range", f"{range_pos:.1f}%")

        st.progress(min(max(range_pos / 100, 0), 1))
        st.caption(f"From 52W low: {d_low:.1f}% · From 52W high: {d_high:.1f}%")

        if range_pos >= 75:
            st.info("Chart interpretation: The stock is near the upper part of its 52-week range. Upside depends more on earnings growth, valuation, and analyst support.")
        elif range_pos <= 35:
            st.info("Chart interpretation: The stock is closer to the lower part of its 52-week range. This can support a recovery setup if fundamentals remain intact.")
        else:
            st.info("Chart interpretation: The stock is in the middle of its 52-week range. Confirmation from trend, analysts, and financial execution matters.")


@st.cache_data(ttl=900)
def fetch_chart_history_fixed(ticker, period="5y"):
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return pd.DataFrame()
    try:
        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # yfinance can return multi-index columns sometimes.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        df = df.dropna(subset=["Close"]).copy()
        if df.empty:
            return pd.DataFrame()

        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
        return df
    except Exception:
        return pd.DataFrame()


def render_interactive_price_chart_fixed(row):
    ticker = safe_text(row.get("Ticker"), "").upper()
    if not ticker:
        return

    with st.container(border=True):
        st.markdown("### 📊 Interactive Price Chart")
        st.caption("Price trend with 20/50/200-day averages, 52-week high/low, analyst target, and AI fair value.")

        period = st.selectbox(
            "Chart range",
            ["6mo", "1y", "3y", "5y"],
            index=3,
            key=chart_instance_key(row, "detail_chart_range"),
        )

        hist = fetch_chart_history_fixed(ticker, period=period)
        if hist.empty:
            st.warning("Chart data unavailable. Check that yfinance is installed in requirements.txt and that the ticker is valid.")
            st.code("Add to requirements.txt if missing: yfinance, plotly")
            return

        close = hist["Close"].dropna()
        if close.empty:
            st.warning("No close-price history returned for this ticker.")
            return

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Price"))

        if "SMA20" in hist.columns and hist["SMA20"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA20"], mode="lines", name="SMA 20"))
        if "SMA50" in hist.columns and hist["SMA50"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA50"], mode="lines", name="SMA 50"))
        if "SMA200" in hist.columns and hist["SMA200"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA200"], mode="lines", name="SMA 200"))

        high = hist["High"].dropna() if "High" in hist.columns else close
        low = hist["Low"].dropna() if "Low" in hist.columns else close

        high_52 = float(high.tail(min(252, len(high))).max()) if not high.empty else None
        low_52 = float(low.tail(min(252, len(low))).min()) if not low.empty else None
        current = float(close.iloc[-1])

        analyst_target = safe_number(row.get("Analyst Target"), 0)
        ai_target = safe_number(row.get("AI Fair Value"), 0)

        if high_52:
            fig.add_hline(y=high_52, line_dash="dash", annotation_text="52W High", annotation_position="top left")
        if low_52:
            fig.add_hline(y=low_52, line_dash="dash", annotation_text="52W Low", annotation_position="bottom left")
        if analyst_target:
            fig.add_hline(y=analyst_target, line_dash="dot", annotation_text="Analyst Target", annotation_position="top right")
        if ai_target:
            fig.add_hline(y=ai_target, line_dash="dot", annotation_text="AI Fair Value", annotation_position="top right")
        support_1 = safe_number(row.get("Support 1"), 0)
        resistance_1 = safe_number(row.get("Resistance 1"), 0)
        breakout = safe_number(row.get("Breakout Level"), 0)
        if support_1:
            fig.add_hline(y=support_1, line_dash="dash", annotation_text="Support 1", annotation_position="bottom right")
        if resistance_1:
            fig.add_hline(y=resistance_1, line_dash="dash", annotation_text="Resistance 1", annotation_position="top right")
        if breakout:
            fig.add_hline(y=breakout, line_dash="dot", annotation_text="Breakout", annotation_position="top right")

        fig.update_layout(
            height=520,
            margin=dict(l=20, r=20, t=35, b=20),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            xaxis_title="Date",
            yaxis_title="Price",
        )
        st.plotly_chart(fig, use_container_width=True, key=chart_instance_key(row, "plotly_detail_chart"))

        if high_52 and low_52 and high_52 > low_52:
            range_pos = ((current - low_52) / (high_52 - low_52)) * 100
            from_low = ((current - low_52) / low_52) * 100 if low_52 else 0
            from_high = ((current - high_52) / high_52) * 100 if high_52 else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current Price", fmt_money(current))
            c2.metric("True 52W Low", fmt_money(low_52))
            c3.metric("True 52W High", fmt_money(high_52))
            c4.metric("52W Range Position", f"{range_pos:.1f}%")

            st.progress(min(max(range_pos / 100, 0), 1))
            st.caption(f"From 52W low: {from_low:.1f}% · From 52W high: {from_high:.1f}%")


@st.cache_data(ttl=900)
def fetch_chart_history_force_chart(ticker, period="5y"):
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return pd.DataFrame()
    try:
        df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.dropna(subset=["Close"]).copy()
        if df.empty:
            return pd.DataFrame()
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
        return df
    except Exception:
        return pd.DataFrame()


def render_force_chart_section(row):
    ticker = safe_text(row.get("Ticker"), "").upper()
    if not ticker:
        return

    with st.container(border=True):
        st.markdown("### 📊 Interactive Price Chart")
        st.caption("Loads on demand. Shows price, SMA 20/50/200, 52-week high/low, analyst target, and AI fair value.")

        period = st.selectbox(
            "Chart range",
            ["6mo", "1y", "3y", "5y"],
            index=3,
            key=chart_instance_key(row, "detail_chart_range"),
        )

        hist = fetch_chart_history_force_chart(ticker, period)
        if hist.empty:
            st.warning("Chart data unavailable. Make sure `yfinance` and `plotly` are in requirements.txt, then redeploy.")
            st.code("yfinance\nplotly\nrequests")
            return

        close = hist["Close"].dropna()
        high = hist["High"].dropna() if "High" in hist.columns else close
        low = hist["Low"].dropna() if "Low" in hist.columns else close

        current = float(close.iloc[-1])
        high_52 = float(high.tail(min(252, len(high))).max())
        low_52 = float(low.tail(min(252, len(low))).min())
        range_pos = ((current - low_52) / (high_52 - low_52)) * 100 if high_52 > low_52 else 0

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Price"))
        if hist["SMA20"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA20"], mode="lines", name="SMA 20"))
        if hist["SMA50"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA50"], mode="lines", name="SMA 50"))
        if hist["SMA200"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA200"], mode="lines", name="SMA 200"))

        fig.add_hline(y=high_52, line_dash="dash", annotation_text="52W High", annotation_position="top left")
        fig.add_hline(y=low_52, line_dash="dash", annotation_text="52W Low", annotation_position="bottom left")

        analyst_target = safe_number(row.get("Analyst Target"), 0)
        ai_target = safe_number(row.get("AI Fair Value"), 0)
        if analyst_target:
            fig.add_hline(y=analyst_target, line_dash="dot", annotation_text="Analyst Target", annotation_position="top right")
        if ai_target:
            fig.add_hline(y=ai_target, line_dash="dot", annotation_text="AI Fair Value", annotation_position="top right")

        fig.update_layout(
            height=540,
            margin=dict(l=20, r=20, t=35, b=20),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            xaxis_title="Date",
            yaxis_title="Price",
        )
        st.plotly_chart(fig, use_container_width=True, key=chart_instance_key(row, "plotly_detail_chart"))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current Price", fmt_money(current))
        c2.metric("True 52W Low", fmt_money(low_52))
        c3.metric("True 52W High", fmt_money(high_52))
        c4.metric("52W Range Position", f"{range_pos:.1f}%")
        st.progress(min(max(range_pos / 100, 0), 1))


def render_legacy_agent_details_force(row):
    committee = row.get("AI Committee")
    if isinstance(committee, dict) and committee:
        return

    with st.container(border=True):
        st.markdown("### 🧠 AI Agent Details")
        st.caption("Fallback agent breakdown from available scan fields because this row does not have full committee JSON yet.")

        conviction = safe_number(row.get("Final Conviction"), 0)
        upside = safe_number(row.get("Target Upside %"), 0)
        rsi = safe_number(row.get("RSI"), 0)
        atr = safe_number(row.get("ATR %"), 0)

        st.markdown("#### 📈 Technical Agent")
        st.markdown(f"• Final conviction context: {conviction:.0f}/100")
        st.markdown(f"• RSI: {rsi:.1f}")
        st.markdown(f"• ATR volatility: {atr:.1f}%")
        if rsi >= 70:
            st.warning("RSI is overbought, so avoid chasing.")
        else:
            st.info("Momentum is not excessively overheated.")

        st.markdown("#### 💰 Valuation Agent")
        st.markdown(f"• AI upside: {upside:.1f}%")
        st.markdown(f"• Analyst target: {fmt_money(row.get('Analyst Target'))}")
        st.markdown(f"• AI fair value: {fmt_money(row.get('AI Fair Value'))}")
        if upside >= 50:
            st.warning("AI upside is very high; treat this as higher uncertainty unless finance/news/analyst data confirms it.")

        st.markdown("#### 👨‍💼 Analyst Agent")
        st.markdown(f"• Analyst support: {safe_text(row.get('Analyst Support'), 'N/A')}")
        st.markdown(f"• Analyst count: {row.get('Analyst Count', 'N/A')}")
        source = safe_text(row.get("Analyst Support Source"), "")
        if source:
            st.caption(source)

        st.markdown("#### 📰 News Agent")
        st.markdown(f"• News sentiment: {safe_text(row.get('News Sentiment'), 'N/A')}")
        news_source = safe_text(row.get("News Sentiment Source"), "")
        if news_source:
            st.caption(news_source)

        st.markdown("#### 🏢 Finance Agent")
        st.markdown("• Finance Agent details require V41.5+ row data or live AI research.")
        st.markdown("• Use ⚡ Run Live AI or run the latest cron scan to populate deeper financial details.")


def chart_instance_key(row, prefix="chart"):
    ticker = safe_text(row.get("Ticker"), "UNKNOWN").upper()
    st.session_state["_chart_key_counter"] = st.session_state.get("_chart_key_counter", 0) + 1
    return f"{prefix}_{ticker}_{st.session_state['_chart_key_counter']}"


@st.cache_data(ttl=900)
def fetch_detail_chart_history_v4184(ticker, period="5y"):
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return pd.DataFrame()
    try:
        df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.dropna(subset=["Close"]).copy()
        if df.empty:
            return pd.DataFrame()
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
        return df
    except Exception:
        return pd.DataFrame()


def render_detail_chart_v4184(row):
    ticker = safe_text(row.get("Ticker"), "").upper().strip()
    if not ticker:
        return

    with st.container(border=True):
        st.markdown("### 📊 Interactive Price Chart")
        st.caption("This appears directly above the Quick Metric Guide. It loads live chart data on demand.")

        period = st.selectbox(
            "Chart range",
            ["6mo", "1y", "3y", "5y"],
            index=3,
            key=chart_instance_key(row, "detail_chart_range"),
        )

        hist = fetch_detail_chart_history_v4184(ticker, period)
        if hist.empty:
            st.warning("Chart data unavailable from both Yahoo and FMP. Confirm `yfinance`, `plotly`, and `requests` are in requirements.txt and FMP_API_KEY is set in Render.")
            st.code("yfinance\nplotly\nrequests")
            return

        close = hist["Close"].dropna()
        high = hist["High"].dropna() if "High" in hist.columns else close
        low = hist["Low"].dropna() if "Low" in hist.columns else close
        current = float(close.iloc[-1])
        high_52 = float(high.tail(min(252, len(high))).max())
        low_52 = float(low.tail(min(252, len(low))).min())
        range_pos = ((current - low_52) / (high_52 - low_52)) * 100 if high_52 > low_52 else 0

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Price"))
        if hist["SMA20"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA20"], mode="lines", name="SMA 20"))
        if hist["SMA50"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA50"], mode="lines", name="SMA 50"))
        if hist["SMA200"].notna().any():
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA200"], mode="lines", name="SMA 200"))

        fig.add_hline(y=high_52, line_dash="dash", annotation_text="52W High", annotation_position="top left")
        fig.add_hline(y=low_52, line_dash="dash", annotation_text="52W Low", annotation_position="bottom left")

        analyst_target = safe_number(row.get("Analyst Target"), 0)
        ai_target = safe_number(row.get("AI Fair Value"), 0)
        if analyst_target:
            fig.add_hline(y=analyst_target, line_dash="dot", annotation_text="Analyst Target", annotation_position="top right")
        if ai_target:
            fig.add_hline(y=ai_target, line_dash="dot", annotation_text="AI Fair Value", annotation_position="top right")

        fig.update_layout(
            height=540,
            margin=dict(l=20, r=20, t=35, b=20),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            xaxis_title="Date",
            yaxis_title="Price",
        )
        st.plotly_chart(fig, use_container_width=True, key=chart_instance_key(row, "plotly_detail_chart"))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current Price", fmt_money(current))
        c2.metric("True 52W Low", fmt_money(low_52))
        c3.metric("True 52W High", fmt_money(high_52))
        c4.metric("52W Range Position", f"{range_pos:.1f}%")
        st.progress(min(max(range_pos / 100, 0), 1))


def render_legacy_agent_details_v4184(row):
    committee = row.get("AI Committee")
    if isinstance(committee, dict) and committee:
        return

    with st.container(border=True):
        st.markdown("### 🧠 AI Agent Details")
        st.caption("Fallback agent breakdown from available scan fields because this row does not have full committee JSON yet.")

        conviction = safe_number(row.get("Final Conviction"), 0)
        upside = safe_number(row.get("Target Upside %"), 0)
        rsi = safe_number(row.get("RSI"), 0)
        atr = safe_number(row.get("ATR %"), 0)

        st.markdown("#### 📈 Technical Agent")
        st.markdown(f"• Final conviction context: {conviction:.0f}/100")
        st.markdown(f"• RSI: {rsi:.1f}")
        st.markdown(f"• ATR volatility: {atr:.1f}%")
        if rsi >= 70:
            st.warning("RSI is overbought, so avoid chasing.")

        st.markdown("#### 💰 Valuation Agent")
        st.markdown(f"• AI upside: {upside:.1f}%")
        st.markdown(f"• Analyst target: {fmt_money(row.get('Analyst Target'))}")
        st.markdown(f"• AI fair value: {fmt_money(row.get('AI Fair Value'))}")

        st.markdown("#### 👨‍💼 Analyst Agent")
        st.markdown(f"• Analyst support: {safe_text(row.get('Analyst Support'), 'N/A')}")
        st.markdown(f"• Analyst count: {row.get('Analyst Count', 'N/A')}")

        st.markdown("#### 📰 News Agent")
        st.markdown(f"• News sentiment: {safe_text(row.get('News Sentiment'), 'N/A')}")

        st.markdown("#### 🏢 Finance Agent")
        st.markdown("• Finance Agent details require V41.5+ row data or live AI research.")


def fetch_fmp_chart_history_v4185(ticker, period="5y"):
    """
    FMP fallback for chart data when yfinance is unavailable or rate-limited.
    Uses /api/v3/historical-price-full/{ticker}.
    """
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker or not FMP_API_KEY:
        return pd.DataFrame()

    try:
        import datetime as _dt
        end = _dt.date.today()
        years = 5
        if period == "6mo":
            start = end - _dt.timedelta(days=190)
        elif period == "1y":
            start = end - _dt.timedelta(days=370)
        elif period == "3y":
            start = end - _dt.timedelta(days=365 * 3 + 10)
        else:
            start = end - _dt.timedelta(days=365 * years + 20)

        url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}"
        params = {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "apikey": FMP_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return pd.DataFrame()

        data = resp.json()
        historical = data.get("historical", [])
        if not historical:
            return pd.DataFrame()

        df = pd.DataFrame(historical)
        if df.empty or "date" not in df or "close" not in df:
            return pd.DataFrame()

        df["Date"] = pd.to_datetime(df["date"])
        df = df.sort_values("Date").set_index("Date")

        rename = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        df = df.rename(columns=rename)
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                if col == "Volume":
                    df[col] = 0
                else:
                    df[col] = df["Close"]
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["Close"]).copy()
        if df.empty:
            return pd.DataFrame()

        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
        return df
    except Exception:
        return pd.DataFrame()


# Override the V41.8.4 chart fetcher with a Yahoo -> FMP fallback.
@st.cache_data(ttl=900)
def fetch_detail_chart_history_v4184(ticker, period="5y"):
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return pd.DataFrame()

    # 1) Try Yahoo/yfinance first.
    try:
        df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.dropna(subset=["Close"]).copy()
            if not df.empty:
                df["SMA20"] = df["Close"].rolling(20).mean()
                df["SMA50"] = df["Close"].rolling(50).mean()
                df["SMA200"] = df["Close"].rolling(200).mean()
                return df
    except Exception:
        pass

    # 2) Fallback to FMP historical prices.
    return fetch_fmp_chart_history_v4185(ticker, period)


def render_v42_news_block(row):
    score=safe_number(row.get("V42 News Score"),0); catalysts=row.get("V42 News Catalysts"); risks=row.get("V42 News Risks"); sources=row.get("V42 News Sources"); summary=safe_text(row.get("V42 News Summary"),"")
    if not score and not catalysts and not summary: return
    with st.container(border=True):
        st.markdown("### 📰 News Agent Summary")
        news_available = bool(row.get("V42 News Available"))
        if news_available and score:
            st.metric("News Agent Score", f"{safe_number(score, 0):.0f}/100")
        else:
            st.metric("News Agent Status", "No recent news found", "Not scored")
            st.warning("No recent company-specific news was retrieved from the connected sources. This is not bearish or neutral — it means there was no news summary available from the scan.")
        if sources: st.caption("Sources used: "+", ".join([safe_text(x) for x in sources[:5]]) if isinstance(sources,list) else safe_text(sources))
        if catalysts:
            st.markdown("**Key catalysts:**")
            for item in (catalysts if isinstance(catalysts,list) else compact_reason_list(catalysts))[:6]: st.markdown(f"• {safe_text(item)}")
        if risks:
            st.markdown("**News risks / limits:**")
            for item in (risks if isinstance(risks,list) else compact_reason_list(risks))[:5]: st.markdown(f"• {safe_text(item)}")
        if summary: st.info(summary)

def render_v42_support_resistance(row):
    vals=[row.get("Support 1"),row.get("Support 2"),row.get("Resistance 1"),row.get("Resistance 2"),row.get("Breakout Level")]
    if not any(safe_number(v,0) for v in vals) and not row.get("Chart Guidance"): return
    with st.container(border=True):
        st.markdown("### 🧭 Support / Resistance Guidance")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Support 1",fmt_money(row.get("Support 1")) if safe_number(row.get("Support 1"),0) else "N/A")
        c2.metric("Support 2",fmt_money(row.get("Support 2")) if safe_number(row.get("Support 2"),0) else "N/A")
        c3.metric("Resistance 1",fmt_money(row.get("Resistance 1")) if safe_number(row.get("Resistance 1"),0) else "N/A")
        c4.metric("Resistance 2",fmt_money(row.get("Resistance 2")) if safe_number(row.get("Resistance 2"),0) else "N/A")
        c5,c6=st.columns(2); c5.metric("Breakout Level",fmt_money(row.get("Breakout Level")) if safe_number(row.get("Breakout Level"),0) else "N/A"); c6.metric("Pullback Zone",safe_text(row.get("Pullback Zone"),"N/A"))
        if row.get("Chart Guidance"): st.info(row.get("Chart Guidance"))

def render_v42_committee_dashboard(row):
    committee=row.get("AI Committee")
    if not isinstance(committee,dict) or not committee: return
    st.markdown("### 🧠 V42 AI Investment Committee")
    total=int(safe_number(row.get("Committee Total Agents"),0)); positive=int(safe_number(row.get("Committee Positive Agents"),0))
    if total: st.caption(f"{positive} of {total} agents are supportive.")
    names=["News Agent","Finance Agent","Analyst Agent","Technical Agent","Insider Agent","Institutional Agent","Competitor Agent","Political Agent","Recovery Agent","ETF / Ownership Agent"]
    cols=st.columns(5)
    for i,n in enumerate(names):
        a=committee.get(n,{})
        if isinstance(a,dict):
            with cols[i%5]: st.metric(n.replace(" Agent","").replace(" / Ownership","").replace("ETF", "ETF"), f"{safe_number(a.get('score'),0):.0f}/100", safe_text(a.get('status'),""))
    with st.expander("Open full V42 agent findings, risks, and bottom lines", expanded=True):
        for n in names:
            a=committee.get(n)
            if not isinstance(a,dict): continue
            st.markdown(f"#### {n}"); st.markdown(f"**Score:** {a.get('score','N/A')}/100 · **Status:** {a.get('status','N/A')} · **Impact:** {a.get('impact','N/A')}"); st.caption(f"**Data used:** {a.get('data_used','N/A')}")
            if a.get('summary'): st.write(a.get('summary'))
            if a.get('findings'):
                st.markdown("**Findings:**")
                for item in a.get('findings',[])[:8]: st.markdown(f"• {safe_text(item)}")
            if a.get('risks'):
                st.markdown("**Risks / limits:**")
                for item in a.get('risks',[])[:6]: st.markdown(f"• {safe_text(item)}")
            if a.get('bottom_line'): st.info(f"**Bottom line:** {a.get('bottom_line')}")
            st.markdown("---")


def render_agent_education_summary(row):
    with st.container(border=True):
        st.markdown("### 📘 How to Read This Report Card")
        st.markdown("""
**Score** tells you how supportive that agent is.

**Status** tells you whether the signal is positive, mixed, limited, unavailable, or not connected.

**Impact** tells you whether the signal should influence the decision.

**Findings** are the facts the agent found.

**Risks / limits** explain what is missing, weak, or dangerous.

**Investor translation** explains what it means, why it matters, and what action to consider.

A high score does **not** automatically mean buy. The best setups happen when news, finance, analyst, technical, and valuation evidence all agree.
""")


def render_agent_translation_box(agent):
    if not isinstance(agent, dict):
        return
    if not (agent.get("what_it_means") or agent.get("why_it_matters") or agent.get("investor_action")):
        return

    with st.container(border=True):
        st.markdown("**Investor translation**")
        if agent.get("what_it_means"):
            st.markdown(f"• **What it means:** {safe_text(agent.get('what_it_means'))}")
        if agent.get("why_it_matters"):
            st.markdown(f"• **Why it matters:** {safe_text(agent.get('why_it_matters'))}")
        if agent.get("investor_action"):
            st.markdown(f"• **What to do:** {safe_text(agent.get('investor_action'))}")

        cgreen, cred = st.columns(2)
        with cgreen:
            st.success(f"Green flag: {safe_text(agent.get('green_flag', 'Supportive evidence.'))}")
        with cred:
            st.warning(f"Red flag: {safe_text(agent.get('red_flag', 'Watch for weak evidence.'))}")


def render_v42_diagnostics(row):
    warnings = []
    for key in ["V42 Committee Warning", "V42 Translation Warning"]:
        value = safe_text(row.get(key), "")
        if value:
            warnings.append(value)
    if warnings:
        with st.container(border=True):
            st.markdown("### ⚙️ V42 Diagnostics")
            for w in warnings:
                st.warning(w)


def render_v42_tier_status(row):
    tier = safe_text(row.get("V42 Tier"), "")
    warn = safe_text(row.get("V42 Tier Warning"), "")
    if not tier and not warn:
        return
    with st.container(border=True):
        if tier == "full":
            st.success("V42 Research Tier: Full AI Committee completed in scheduled scan.")
        elif tier == "light":
            st.info("V42 Research Tier: Lightweight scheduled scan. Use ⚡ Run Live AI / Research Any Ticker for full live committee, latest news, SEC, and competitor data.")
        elif tier:
            st.caption(f"V42 Research Tier: {tier}")
        if warn:
            st.warning(warn)


# =========================
# V42.2 AGENT V2 DISPLAY INTELLIGENCE
# =========================

def v422_display_num(value, default=None):
    try:
        if value in (None, "", "N/A"):
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return default


def v422_display_money(value):
    value = v422_display_num(value, None)
    return "N/A" if value is None else f"${value:,.2f}"


def v422_display_pct(value):
    value = v422_display_num(value, None)
    return "N/A" if value is None else f"{value:.1f}%"


def v422_row_num(row, *keys, default=None):
    for key in keys:
        try:
            value = row.get(key)
            if value not in (None, "", "N/A"):
                return v422_display_num(value, default)
        except Exception:
            pass
    return default


def v422_agent_v2_commentary(agent_name, agent, row):
    """
    Dashboard-side intelligence layer.
    Converts raw agent findings into deeper investment judgment without requiring another heavy cron.
    """
    name = safe_text(agent_name, "").lower()
    score = v422_display_num(agent.get("score"), None) if isinstance(agent, dict) else None

    if "finance" in name:
        revenue_growth = None
        earnings_growth = None
        forward_pe = None
        debt_equity = None
        current_ratio = None
        free_cash_flow = None

        # Try to parse from existing findings.
        for item in agent.get("findings", []) if isinstance(agent, dict) else []:
            txt = safe_text(item)
            m = re.search(r"Revenue growth[^0-9\-]*(-?\d+\.?\d*)", txt, re.I)
            if m: revenue_growth = float(m.group(1))
            m = re.search(r"Earnings growth[^0-9\-]*(-?\d+\.?\d*)", txt, re.I)
            if m: earnings_growth = float(m.group(1))
            m = re.search(r"Forward PE[^0-9\-]*(-?\d+\.?\d*)", txt, re.I)
            if m: forward_pe = float(m.group(1))
            m = re.search(r"Debt/equity[^0-9\-]*(-?\d+\.?\d*)", txt, re.I)
            if m: debt_equity = float(m.group(1))
            m = re.search(r"Current ratio[^0-9\-]*(-?\d+\.?\d*)", txt, re.I)
            if m: current_ratio = float(m.group(1))

        judgments = []
        concerns = []
        if revenue_growth is not None:
            if revenue_growth >= 30:
                judgments.append("Revenue growth is exceptional and indicates strong demand.")
            elif revenue_growth >= 15:
                judgments.append("Revenue growth is strong.")
            elif revenue_growth < 0:
                concerns.append("Revenue growth is negative.")
        if revenue_growth is not None and earnings_growth is not None:
            if revenue_growth >= 20 and earnings_growth < revenue_growth * 0.35:
                concerns.append("Revenue is growing much faster than earnings, which may signal reinvestment, margin pressure, or weaker profit conversion.")
            elif earnings_growth >= 15:
                judgments.append("Earnings growth supports the revenue story.")
        if forward_pe is not None and revenue_growth is not None:
            if forward_pe < max(revenue_growth, 1):
                judgments.append("Valuation appears reasonable relative to growth.")
            elif forward_pe > 50:
                concerns.append("Valuation is elevated and depends on continued execution.")
        if debt_equity is not None:
            if debt_equity < 0.5:
                judgments.append("Balance sheet leverage appears low.")
            elif debt_equity > 2:
                concerns.append("Leverage is elevated.")

        return {
            "title": "Finance Agent V2 Judgment",
            "what_it_means": "This checks whether sales growth is converting into earnings, margins, cash flow, and balance-sheet strength.",
            "why_it_matters": "High revenue growth alone is not enough. The best setups show quality growth with profit conversion and manageable debt.",
            "judgment": judgments or ["Financial profile is constructive, but deeper margin/cash-flow comparison would improve confidence."],
            "watchouts": concerns or ["No major finance-specific red flag detected from the available fields."],
            "action": "Prefer entries when revenue growth, earnings growth, margins, and cash flow agree. If revenue growth is much faster than earnings growth, use smaller sizing and require confirmation.",
        }

    if "analyst" in name:
        price = v422_row_num(row, "Price")
        analyst_target = v422_row_num(row, "Analyst Target")
        analyst_count = v422_row_num(row, "Analyst Count")
        ai_fair = v422_row_num(row, "AI Fair Value")
        judgments = []
        concerns = []
        if analyst_count is not None:
            if analyst_count >= 25:
                judgments.append(f"Coverage is broad with {int(analyst_count)} analysts, so consensus is more meaningful.")
            elif analyst_count < 5:
                concerns.append("Analyst coverage is thin, so consensus is less reliable.")
        if price and analyst_target:
            upside = (analyst_target - price) / price * 100
            judgments.append(f"Analyst consensus implies {upside:.1f}% upside.")
            if upside < 5:
                concerns.append("Analyst target shows limited upside.")
        if ai_fair and analyst_target:
            gap = (ai_fair - analyst_target) / analyst_target * 100
            if gap > 50:
                concerns.append(f"AI fair value is {gap:.1f}% above analyst consensus; treat model upside as higher uncertainty.")
            elif abs(gap) <= 20:
                judgments.append("AI fair value is reasonably aligned with analyst consensus.")

        return {
            "title": "Analyst Agent V2 Judgment",
            "what_it_means": "This checks whether Wall Street consensus supports or conflicts with the AI thesis.",
            "why_it_matters": "If AI upside is far above analyst consensus, the idea may still work but requires stronger confirmation.",
            "judgment": judgments or ["Analyst data is supportive but should be combined with finance, news, and technical signals."],
            "watchouts": concerns or ["Analyst data can lag fast-moving news."],
            "action": "Use analyst support as confirmation. When AI fair value is far above consensus, require stronger evidence from other agents.",
        }

    if "technical" in name:
        price = v422_row_num(row, "Price")
        support = v422_row_num(row, "Support 1")
        resistance = v422_row_num(row, "Resistance 1")
        breakout = v422_row_num(row, "Breakout Level")
        rsi = None
        for item in agent.get("findings", []) if isinstance(agent, dict) else []:
            txt = safe_text(item)
            m = re.search(r"RSI[^0-9]*(\d+\.?\d*)", txt, re.I)
            if m: rsi = float(m.group(1))
        judgments = []
        concerns = []
        if price and support:
            judgments.append(f"Price is {(price-support)/price*100:.1f}% above support at {v422_display_money(support)}.")
        if price and resistance:
            judgments.append(f"Price is {(resistance-price)/price*100:.1f}% below resistance at {v422_display_money(resistance)}.")
        if price and support and resistance:
            rr = max(resistance-price, 0) / max(price-support, 0.01)
            judgments.append(f"Near-term chart risk/reward to first resistance is about {rr:.2f}:1.")
            if rr < 1:
                concerns.append("Price is closer to resistance than support; entry is less attractive.")
        if rsi is not None:
            if rsi >= 70:
                concerns.append("RSI is overbought; avoid chasing.")
            elif 45 <= rsi <= 65:
                judgments.append("RSI is in a healthier momentum zone.")
        return {
            "title": "Technical Agent V2 Judgment",
            "what_it_means": "This checks whether the current price is a good entry, not just whether the trend is strong.",
            "why_it_matters": "A strong stock can still be a poor entry if it is too close to resistance or overbought.",
            "judgment": judgments or ["Technical setup is being evaluated using trend, RSI, support, and resistance."],
            "watchouts": concerns or ["No major technical risk detected from available chart fields."],
            "action": f"Prefer pullback near {v422_display_money(support)} or breakout above {v422_display_money(breakout or resistance)} with volume.",
        }

    if "insider" in name:
        form4_count = None
        for item in agent.get("findings", []) if isinstance(agent, dict) else []:
            m = re.search(r"Form 4 filings found:\s*(\d+)", safe_text(item), re.I)
            if m: form4_count = int(m.group(1))
        return {
            "title": "Insider Agent V2 Judgment",
            "what_it_means": "The system detected SEC insider filing activity, but it may not yet classify whether insiders bought or sold.",
            "why_it_matters": "Insider buying can be powerful, but Form 4 count alone is not bullish because it can include sales, option exercises, and routine compensation.",
            "judgment": [f"Recent Form 4 count: {form4_count}." if form4_count is not None else "Transaction-level insider detail is not available yet."],
            "watchouts": ["Do not treat filing count alone as bullish."],
            "action": "Wait for buy/sell classification before using this as a major decision factor.",
        }

    if "institutional" in name:
        return {
            "title": "Institutional Agent V2 Judgment",
            "what_it_means": "This checks whether institutional filing context exists, but 13F data is delayed.",
            "why_it_matters": "Institutional accumulation can confirm a thesis, but delayed filings are not real-time trade signals.",
            "judgment": ["Institutional signal is directional until holder-level net flow is shown."],
            "watchouts": ["Do not buy solely because 13F context exists; confirm actual holders added shares."],
            "action": "Use institutional data as confirmation only. Strong signal requires funds added vs funds reduced over multiple quarters.",
        }

    if "competitor" in name:
        return {
            "title": "Competitor Agent V2 Judgment",
            "what_it_means": "This should tell whether the company is growing faster, trading cheaper, or operating better than peers.",
            "why_it_matters": "A stock can look good alone but be less attractive if peers are cheaper or growing faster.",
            "judgment": ["Peer context is useful only when actual peer averages are available."],
            "watchouts": ["If peer list or peer averages are unavailable, do not over-weight this score."],
            "action": "Use full/live research for peer average revenue growth, margins, PE, and debt comparison.",
        }

    if "recovery" in name:
        price = v422_row_num(row, "Price")
        high52 = v422_row_num(row, "52W High")
        judgments = []
        if price and high52:
            dd = (price-high52)/high52*100
            judgments.append(f"Current price is {dd:.1f}% from the 52-week high.")
        return {
            "title": "Recovery Agent V2 Judgment",
            "what_it_means": "This checks whether weakness is a temporary dislocation or a broken-business decline.",
            "why_it_matters": "A lower price is only attractive if the reason for the drop is temporary or already priced in.",
            "judgment": judgments or ["Recovery case depends on whether fundamentals remain intact after the drawdown."],
            "watchouts": ["Avoid recovery setups caused by deteriorating fundamentals, debt stress, or repeated guidance cuts."],
            "action": "Prefer recovery names with stabilizing fundamentals, improving news, analyst support, and clear support levels.",
        }

    return None


def render_v422_agent_v2_box(agent_name, agent, row):
    info = v422_agent_v2_commentary(agent_name, agent, row)
    if not info:
        return
    with st.container(border=True):
        st.markdown(f"**{info['title']}**")
        st.markdown(f"• **What it means:** {info['what_it_means']}")
        st.markdown(f"• **Why it matters:** {info['why_it_matters']}")
        if info.get("judgment"):
            st.markdown("**Judgment:**")
            for item in info["judgment"][:5]:
                st.markdown(f"✓ {safe_text(item)}")
        if info.get("watchouts"):
            st.markdown("**Watchouts:**")
            for item in info["watchouts"][:5]:
                st.markdown(f"⚠️ {safe_text(item)}")
        st.info(f"**Action:** {info['action']}")


def render_v422_status(row):
    st.success("V42.2 Agent V2 Intelligence: report cards now add investment judgment on top of raw agent metrics.")


# =========================
# V42.3 PROFESSIONAL MARKET COMMAND CENTER
# =========================

def v423_safe_float(value, default=None):
    try:
        if value in (None, "", "N/A"):
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return default


def v423_fmt_money(value):
    value = v423_safe_float(value, None)
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


@st.cache_data(ttl=300)
def v423_fetch_quote(symbol):
    symbol = str(symbol).upper().strip()
    if not symbol:
        return {}
    try:
        if FMP_API_KEY:
            url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
            r = requests.get(url, params={"apikey": FMP_API_KEY}, timeout=8)
            if r.status_code == 200:
                data = r.json() or []
                if data:
                    q = data[0]
                    return {
                        "symbol": symbol,
                        "price": q.get("price"),
                        "change_pct": q.get("changesPercentage"),
                        "change": q.get("change"),
                        "name": q.get("name"),
                    }
    except Exception:
        pass
    return {}


@st.cache_data(ttl=900)
def v423_fetch_market_snapshot():
    symbols = ["SPY", "QQQ", "DIA", "IWM"]
    out = []
    for s in symbols:
        q = v423_fetch_quote(s)
        if q:
            out.append(q)
    vix = v423_fetch_quote("^VIX") or v423_fetch_quote("VIX")
    return {"indexes": out, "vix": vix}


@st.cache_data(ttl=1800)
def v423_fetch_economic_calendar():
    events = []
    try:
        if FMP_API_KEY:
            today = dt.datetime.now().date()
            end = today + dt.timedelta(days=7)
            url = "https://financialmodelingprep.com/api/v3/economic_calendar"
            r = requests.get(url, params={"from": today.isoformat(), "to": end.isoformat(), "apikey": FMP_API_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json() or []
                important_terms = ["CPI", "PPI", "Payroll", "Nonfarm", "FOMC", "Fed", "Jobless", "GDP", "Retail Sales", "Inflation", "Unemployment", "ISM", "PMI"]
                for item in data:
                    name = safe_text(item.get("event") or item.get("name") or "")
                    if name and any(term.lower() in name.lower() for term in important_terms):
                        events.append({
                            "date": safe_text(item.get("date") or item.get("datetime") or ""),
                            "event": name,
                            "actual": item.get("actual"),
                            "estimate": item.get("estimate"),
                            "previous": item.get("previous"),
                        })
                    if len(events) >= 8:
                        break
    except Exception:
        pass
    return events


@st.cache_data(ttl=900)
def v423_fetch_earnings_calendar():
    """
    V42.3.2: Today's broad earnings calendar.
    Not watchlist-only. Shows major earnings due today from FMP.
    """
    events = []
    try:
        if FMP_API_KEY:
            today = dt.datetime.now().date()
            url = "https://financialmodelingprep.com/api/v3/earning_calendar"
            r = requests.get(
                url,
                params={
                    "from": today.isoformat(),
                    "to": today.isoformat(),
                    "apikey": FMP_API_KEY,
                },
                timeout=12,
            )
            if r.status_code == 200:
                data = r.json() or []
                priority_symbols = {
                    "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","AMD","AVGO","NFLX",
                    "CRM","ADBE","ORCL","COST","WMT","HD","LOW","JPM","BAC","WFC","GS","MS",
                    "UNH","LLY","NVO","MRK","PFE","ABBV","JNJ","XOM","CVX","CAT","DE",
                    "PLTR","SOFI","TEAM","SNOW","CRWD","NOW","PANW","SHOP","UBER","DIS"
                }

                def rank_item(item):
                    sym = safe_text(item.get("symbol") or "").upper()
                    pri = 0 if sym in priority_symbols else 1
                    rev_est = item.get("revenueEstimated")
                    eps_est = item.get("epsEstimated")
                    has_rev = 0 if rev_est not in (None, "", 0) else 1
                    has_eps = 0 if eps_est not in (None, "", 0) else 1
                    return (pri, has_rev, has_eps, sym)

                for item in sorted(data, key=rank_item):
                    sym = safe_text(item.get("symbol") or "").upper()
                    if not sym:
                        continue
                    events.append({
                        "symbol": sym,
                        "date": safe_text(item.get("date") or ""),
                        "eps": item.get("eps"),
                        "epsEstimated": item.get("epsEstimated"),
                        "time": safe_text(item.get("time") or ""),
                        "revenueEstimated": item.get("revenueEstimated"),
                    })
                    if len(events) >= 18:
                        break
    except Exception:
        pass
    return events


@st.cache_data(ttl=900)
def v423_fetch_market_news_headlines():
    """
    V42.3.2: lightweight broad market/news headlines for top ribbon.
    """
    headlines = []
    try:
        if NEWSAPI_KEY:
            url = "https://newsapi.org/v2/everything"
            r = requests.get(
                url,
                params={
                    "q": '(stock market OR S&P 500 OR Nasdaq OR Federal Reserve OR CPI OR inflation OR earnings)',
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 5,
                    "apiKey": NEWSAPI_KEY,
                },
                timeout=10,
            )
            if r.status_code == 200:
                for article in (r.json().get("articles") or [])[:5]:
                    title = safe_text(article.get("title") or "")
                    if title:
                        headlines.append(title)
    except Exception:
        pass
    return headlines[:5]


def render_v423_market_ribbon():
    snap = v423_fetch_market_snapshot()
    parts = []

    for q in snap.get("indexes", []):
        sym = q.get("symbol")
        pct = v423_safe_float(q.get("change_pct"), None)
        if sym and pct is not None:
            icon = "🟢" if pct >= 0 else "🔴"
            parts.append(f"{icon} {sym} {pct:+.2f}%")

    vix = snap.get("vix") or {}
    if vix.get("price") is not None:
        parts.append(f"⚠️ VIX {v423_safe_float(vix.get('price'), 0):.2f}")

    earnings = v423_fetch_earnings_calendar()
    earnings_symbols = [safe_text(e.get("symbol")).upper() for e in earnings[:8] if e.get("symbol")]
    if earnings_symbols:
        parts.append("💼 Earnings Today: " + ", ".join(earnings_symbols))

    econ = v423_fetch_economic_calendar()
    econ_items = [safe_text(e.get("event")) for e in econ[:2] if e.get("event")]
    if econ_items:
        parts.append("🗓️ Macro: " + " | ".join(econ_items))

    headlines = v423_fetch_market_news_headlines()
    if headlines:
        parts.append("📰 " + " | ".join(headlines[:2]))

    if not parts:
        parts = ["Market data loading from connected sources"]

    ribbon_text = "  •  ".join(parts)

    st.markdown(f"""
<style>
.v423-ribbon {{
    width: 100%; overflow: hidden; white-space: nowrap;
    background: linear-gradient(90deg, #0E1117, #172033);
    color: #E8EEF7; border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px; padding: 10px 0; margin-bottom: 12px;
}}
.v423-ribbon span {{
    display: inline-block; padding-left: 100%;
    animation: v423-marquee 36s linear infinite;
    font-weight: 650; letter-spacing: 0.2px;
}}
@keyframes v423-marquee {{
    0% {{ transform: translate(0, 0); }}
    100% {{ transform: translate(-100%, 0); }}
}}
.v423-meter-bg {{
    width: 100%; height: 14px; background: rgba(255,255,255,0.12);
    border-radius: 999px; overflow: hidden;
}}
.v423-meter-fill {{
    height: 14px; background: linear-gradient(90deg, #1E88E5, #00C853);
    border-radius: 999px;
}}
</style>
<div class="v423-ribbon"><span>{ribbon_text} &nbsp;&nbsp;&nbsp; {ribbon_text}</span></div>
""", unsafe_allow_html=True)


def render_v423_command_center():
    st.markdown("## 🧭 Market Command Center")
    render_v423_market_ribbon()
    econ = v423_fetch_economic_calendar()
    earnings = v423_fetch_earnings_calendar()
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            if econ:
                for e in econ[:6]:
                    st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
                    details = []
                    if e.get("estimate") not in (None, ""):
                        details.append(f"Est: {e.get('estimate')}")
                    if e.get("previous") not in (None, ""):
                        details.append(f"Prev: {e.get('previous')}")
                    if details:
                        st.caption(" | ".join(details))
            else:
                st.caption("No high-priority economic events returned from connected source.")
    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            if earnings:
                for e in earnings[:12]:
                    time_txt = f" · {safe_text(e.get('time'))}" if e.get("time") else ""
                    st.markdown(f"• **{safe_text(e.get('symbol'))}** — {safe_text(e.get('date'))}{time_txt}")
                    if e.get("epsEstimated") not in (None, ""):
                        st.caption(f"EPS Est: {e.get('epsEstimated')}")
            else:
                st.caption(
                    f"No earnings returned for today. FMP_API_KEY configured={'Yes' if bool(FMP_API_KEY) else 'No'}. "
                    "If key is configured, there may simply be no major earnings today or the endpoint is plan-limited."
                )


def render_v423_conviction_meter(row):
    score = v423_safe_float(row.get("Final Conviction") or row.get("Score") or row.get("AI Score"), None)
    if score is None:
        return
    score = max(0, min(100, score))
    st.markdown("### 🎯 Conviction Meter")
    st.markdown(f"**{score:.0f}/100**")
    st.markdown(f"""<div class="v423-meter-bg"><div class="v423-meter-fill" style="width: {score:.0f}%"></div></div>""", unsafe_allow_html=True)
    if score >= 90:
        st.success("Elite conviction — multiple signals appear aligned.")
    elif score >= 75:
        st.info("Strong conviction — attractive, but confirm risks and entry.")
    elif score >= 55:
        st.warning("Moderate conviction — needs stronger confirmation.")
    else:
        st.error("Low conviction — not a priority idea.")


def render_v423_why_ranked(row):
    positives, risks = [], []
    score = v423_safe_float(row.get("Final Conviction") or row.get("Score") or row.get("AI Score"), None)
    upside = v423_safe_float(row.get("Target Upside %") or row.get("AI Upside"), None)
    rsi = v423_safe_float(row.get("RSI"), None)
    price = v423_safe_float(row.get("Price"), None)
    resistance = v423_safe_float(row.get("Resistance 1"), None)
    committee = row.get("AI Committee")
    if isinstance(committee, dict):
        for agent_name, agent in committee.items():
            if not isinstance(agent, dict):
                continue
            a_score = v423_safe_float(agent.get("score"), None)
            if a_score is not None and a_score >= 75:
                positives.append(f"{agent_name}: supportive ({a_score:.0f}/100)")
            for r in (agent.get("risks") or [])[:1]:
                if r and len(risks) < 5:
                    risks.append(f"{agent_name}: {safe_text(r)}")
    if score is not None and score >= 85:
        positives.insert(0, f"High AI conviction score: {score:.0f}/100")
    if upside is not None and upside >= 20:
        positives.append(f"Attractive modeled upside: {upside:.1f}%")
    if rsi is not None:
        if rsi >= 70:
            risks.append(f"RSI is overbought at {rsi:.1f}; avoid chasing.")
        elif 45 <= rsi <= 65:
            positives.append(f"RSI is healthy at {rsi:.1f}.")
    if price and resistance:
        dist = (resistance - price) / price * 100
        if dist > 5:
            positives.append(f"Room to resistance: {dist:.1f}%")
        elif dist < 3:
            risks.append("Price is close to resistance; entry may be less attractive.")
    positives = positives[:7] or ["Ranking is based on combined AI score, trend, valuation, analyst, and risk signals."]
    risks = risks[:5] or ["No major red flag detected from available report-card fields."]
    with st.container(border=True):
        st.markdown("### 🏆 Why This Ranked")
        st.markdown("**Key reasons:**")
        for p in positives:
            st.markdown(f"✓ {safe_text(p)}")
        st.markdown("**Biggest risks / watchouts:**")
        for r in risks:
            st.markdown(f"⚠️ {safe_text(r)}")


def render_v423_professional_trading_levels(row):
    price = v423_safe_float(row.get("Price"), None)
    support1 = v423_safe_float(row.get("Support 1"), None)
    support2 = v423_safe_float(row.get("Support 2"), None)
    resistance1 = v423_safe_float(row.get("Resistance 1"), None)
    resistance2 = v423_safe_float(row.get("Resistance 2"), None)
    breakout = v423_safe_float(row.get("Breakout Level"), None)
    pullback = safe_text(row.get("Pullback Zone"), "")
    guidance = safe_text(row.get("Chart Guidance"), "")
    if not any([price, support1, support2, resistance1, resistance2, breakout, pullback, guidance]):
        return
    with st.container(border=True):
        st.markdown("### 📈 Professional Trading Levels")
        c1, c2, c3 = st.columns(3)
        c1.metric("Current", v423_fmt_money(price))
        c2.metric("Support 1", v423_fmt_money(support1))
        c3.metric("Resistance 1", v423_fmt_money(resistance1))
        c4, c5, c6 = st.columns(3)
        c4.metric("Support 2", v423_fmt_money(support2))
        c5.metric("Resistance 2", v423_fmt_money(resistance2))
        c6.metric("Breakout", v423_fmt_money(breakout))
        if pullback:
            st.caption(f"Pullback Zone: {pullback}")
        if guidance:
            st.info(guidance)


def render_v423_ai_news_summary(row):
    catalysts = row.get("V42 News Catalysts")
    risks = row.get("V42 News Risks")
    sources = row.get("V42 News Sources")
    score = v423_safe_float(row.get("V42 News Score"), None)
    if not catalysts and not risks:
        return
    with st.container(border=True):
        st.markdown("### 📰 AI News Summary")
        if score is not None:
            st.metric("News Score", f"{score:.0f}/100")
        else:
            st.metric("News Status", "No scored news", "Check live research")
        if sources:
            if isinstance(sources, list):
                st.caption("Sources checked: " + ", ".join([safe_text(x) for x in sources[:5]]))
            else:
                st.caption(f"Sources checked: {safe_text(sources)}")
        if catalysts:
            st.markdown("**Catalysts / headlines:**")
            items = catalysts if isinstance(catalysts, list) else compact_reason_list(catalysts)
            for item in items[:5]:
                st.markdown(f"• {safe_text(item)}")
        if risks:
            st.markdown("**News risks / limits:**")
            items = risks if isinstance(risks, list) else compact_reason_list(risks)
            for item in items[:4]:
                st.markdown(f"⚠️ {safe_text(item)}")



# =========================
# V42.4 COMMAND CENTER + ANALYST RATINGS AGENT
# =========================

def v424_float(value, default=None):
    try:
        if value in (None, "", "N/A"):
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return default


def v424_money(value):
    x = v424_float(value, None)
    return "N/A" if x is None else f"${x:,.2f}"


def v424_pct(value):
    x = v424_float(value, None)
    return "N/A" if x is None else f"{x:.1f}%"


def v424_today():
    return dt.datetime.now().date()


@st.cache_data(ttl=300)
def v424_fmp_get(endpoint, params=None):
    if not FMP_API_KEY:
        return None
    try:
        url = f"https://financialmodelingprep.com/api/v3/{endpoint.lstrip('/')}"
        merged = dict(params or {})
        merged["apikey"] = FMP_API_KEY
        r = requests.get(url, params=merged, timeout=12)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


@st.cache_data(ttl=300)
def v424_quote(symbol):
    symbol = safe_text(symbol, "").upper().strip()
    if not symbol:
        return {}
    data = v424_fmp_get(f"quote/{symbol}")
    if isinstance(data, list) and data:
        q = data[0]
        return {
            "symbol": symbol,
            "price": q.get("price"),
            "change_pct": q.get("changesPercentage"),
            "change": q.get("change"),
            "name": q.get("name"),
        }
    return {}


@st.cache_data(ttl=900)
def v424_market_quotes():
    symbols = ["SPY", "QQQ", "DIA", "IWM", "VIX"]
    return [v424_quote(s) for s in symbols if v424_quote(s)]


@st.cache_data(ttl=1800)
def v424_economic_calendar():
    """
    Shows today's high-impact events if available.
    If none today, shows next high-impact macro reports in the next 45 days.
    """
    important = ["CPI", "PPI", "Payroll", "Nonfarm", "FOMC", "Fed", "Jobless", "GDP", "Retail Sales", "Inflation", "Unemployment", "ISM", "PMI"]
    today = v424_today()
    end = today + dt.timedelta(days=45)
    data = v424_fmp_get("economic_calendar", {"from": today.isoformat(), "to": end.isoformat()})
    events = []
    if isinstance(data, list):
        for item in data:
            name = safe_text(item.get("event") or item.get("name") or "")
            if not name:
                continue
            if any(term.lower() in name.lower() for term in important):
                events.append({
                    "date": safe_text(item.get("date") or item.get("datetime") or ""),
                    "event": name,
                    "actual": item.get("actual"),
                    "estimate": item.get("estimate"),
                    "previous": item.get("previous"),
                })
    # Sort by date text; FMP usually returns ISO-style strings
    events = sorted(events, key=lambda x: safe_text(x.get("date")))
    today_str = today.isoformat()
    todays = [e for e in events if safe_text(e.get("date")).startswith(today_str)]
    return {
        "today": todays[:8],
        "next": events[:12],
        "source": "FMP economic calendar" if events else "No source data returned",
    }


@st.cache_data(ttl=900)
def v424_earnings_today():
    """
    Broad earnings calendar for today; not watchlist-limited.
    """
    today = v424_today()
    data = v424_fmp_get("earning_calendar", {"from": today.isoformat(), "to": today.isoformat()})
    rows = []
    if isinstance(data, list):
        priority = {
            "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","AMD","AVGO","NFLX","CRM","ADBE","ORCL",
            "COST","WMT","HD","LOW","JPM","BAC","WFC","GS","MS","UNH","LLY","MRK","PFE","ABBV","JNJ",
            "XOM","CVX","CAT","DE","PLTR","SOFI","TEAM","SNOW","CRWD","NOW","PANW","SHOP","UBER","DIS"
        }
        def rank_item(item):
            sym = safe_text(item.get("symbol") or "").upper()
            return (0 if sym in priority else 1, sym)
        for item in sorted(data, key=rank_item):
            sym = safe_text(item.get("symbol") or "").upper()
            if not sym:
                continue
            rows.append({
                "Symbol": sym,
                "Date": safe_text(item.get("date") or ""),
                "Time": safe_text(item.get("time") or ""),
                "EPS Est": item.get("epsEstimated"),
                "Revenue Est": item.get("revenueEstimated"),
            })
            if len(rows) >= 30:
                break
    return rows


@st.cache_data(ttl=900)
def v424_market_news():
    """
    Broad market news fallback for command center.
    """
    headlines = []
    try:
        key = globals().get("NEWSAPI_KEY") or globals().get("NEWS_API_KEY") or os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY")
        key = (key or "").strip()
        if key:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": '(stock market OR S&P 500 OR Nasdaq OR Federal Reserve OR CPI OR inflation OR earnings)',
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 5,
                    "apiKey": key,
                },
                timeout=10,
            )
            if r.status_code == 200:
                for a in (r.json().get("articles") or [])[:5]:
                    title = safe_text(a.get("title") or "")
                    source = safe_text((a.get("source") or {}).get("name") or "")
                    if title:
                        headlines.append(f"{title}" + (f" — {source}" if source else ""))
    except Exception:
        pass
    return headlines


@st.cache_data(ttl=900)
def v424_analyst_ratings_agent(ticker, current_price=None, ai_fair_value=None):
    """
    Analyst Ratings Agent:
    Pulls top target/recommendation style data from FMP when available.
    Falls back to quote/target consensus fields already available in report cards.
    """
    ticker = safe_text(ticker, "").upper().strip()
    result = {
        "ticker": ticker,
        "available": False,
        "source": "FMP / scan fallback",
        "top_ratings": [],
        "consensus_target": None,
        "analyst_count": None,
        "consensus_rating": "N/A",
        "upside_pct": None,
        "ai_gap_pct": None,
        "summary": "",
        "risks": [],
    }
    if not ticker:
        return result

    current_price = v424_float(current_price, None)
    ai_fair_value = v424_float(ai_fair_value, None)

    # FMP target consensus endpoint availability varies by plan; try multiple endpoints safely.
    targets = None
    for endpoint in [
        f"price-target-consensus/{ticker}",
        f"price-target/{ticker}",
        f"analyst-stock-recommendations/{ticker}",
    ]:
        data = v424_fmp_get(endpoint)
        if data:
            targets = data
            break

    # Parse price target consensus if available.
    if isinstance(targets, list) and targets:
        result["available"] = True
        for item in targets[:20]:
            if not isinstance(item, dict):
                continue
            target = item.get("priceTarget") or item.get("target") or item.get("targetPrice") or item.get("publishedPriceTarget")
            firm = item.get("analystCompany") or item.get("firm") or item.get("analyst") or item.get("company") or item.get("brokerage") or "Analyst"
            rating = item.get("rating") or item.get("newGrade") or item.get("recommendation") or item.get("grade") or ""
            date = item.get("publishedDate") or item.get("date") or item.get("updatedDate") or ""
            target_num = v424_float(target, None)
            if target_num:
                result["top_ratings"].append({
                    "Firm": safe_text(firm, "Analyst"),
                    "Rating": safe_text(rating, "N/A"),
                    "Target": target_num,
                    "Date": safe_text(date, ""),
                })

    # FMP consensus may return one row with target fields.
    if isinstance(targets, list) and targets:
        first = targets[0] if isinstance(targets[0], dict) else {}
        consensus = (
            first.get("targetConsensus") or first.get("targetMedian") or first.get("targetMean") or
            first.get("priceTargetAverage") or first.get("target")
        )
        count = first.get("numberOfAnalyst") or first.get("analystCount") or first.get("analysts")
        rating = first.get("rating") or first.get("consensus") or first.get("recommendation")
        result["consensus_target"] = v424_float(consensus, result["consensus_target"])
        result["analyst_count"] = v424_float(count, result["analyst_count"])
        if rating:
            result["consensus_rating"] = safe_text(rating, "N/A")

    # If top ratings are available, use top 5 highest target rows as the "top analyst targets".
    if result["top_ratings"]:
        result["top_ratings"] = sorted(result["top_ratings"], key=lambda x: v424_float(x.get("Target"), 0), reverse=True)[:5]
        if not result["consensus_target"]:
            vals = [v424_float(x.get("Target"), None) for x in result["top_ratings"]]
            vals = [x for x in vals if x]
            if vals:
                result["consensus_target"] = sum(vals) / len(vals)
        if not result["analyst_count"]:
            result["analyst_count"] = len(result["top_ratings"])

    if current_price and result["consensus_target"]:
        result["upside_pct"] = ((result["consensus_target"] - current_price) / current_price) * 100
    if ai_fair_value and result["consensus_target"]:
        result["ai_gap_pct"] = ((ai_fair_value - result["consensus_target"]) / result["consensus_target"]) * 100

    # Summary
    upside = result["upside_pct"]
    ai_gap = result["ai_gap_pct"]
    if result["top_ratings"]:
        result["summary"] = "Recent/high target analyst data is available. Use this to validate whether Wall Street supports the AI thesis."
    elif result["consensus_target"]:
        result["summary"] = "Consensus analyst target is available, but individual top 5 analyst rows were not returned by the data source."
    else:
        result["summary"] = "Analyst target detail was not returned by connected sources. Use scan-level analyst target/count as fallback."

    if ai_gap is not None and ai_gap > 50:
        result["risks"].append("AI fair value is far above analyst consensus; treat modeled upside as higher uncertainty.")
    if upside is not None and upside < 5:
        result["risks"].append("Analyst consensus implies limited upside.")
    if not result["top_ratings"]:
        result["risks"].append("Top 5 individual analyst firm targets may require a higher-tier analyst data source if FMP does not return firm-level rows.")

    return result


def render_v424_market_command_center():
    st.markdown("## 🧭 Market Command Center")

    quotes = v424_market_quotes()
    if quotes:
        cols = st.columns(min(5, len(quotes)))
        for i, q in enumerate(quotes[:5]):
            pct = v424_float(q.get("change_pct"), None)
            delta = f"{pct:+.2f}%" if pct is not None else None
            cols[i].metric(q.get("symbol", ""), v424_money(q.get("price")), delta)
    else:
        st.info(
            "Market quote data did not return. Diagnostics: "
            f"FMP_API_KEY configured={'Yes' if bool(FMP_API_KEY) else 'No'}; "
            "check FMP plan/access for quote endpoint."
        )

    econ = v424_economic_calendar()
    earnings = v424_earnings_today()
    news = v424_market_news()

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            today_events = econ.get("today") or []
            next_events = econ.get("next") or []
            if today_events:
                st.markdown("**Today:**")
                for e in today_events[:6]:
                    st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
            elif next_events:
                st.caption("No major event found for today. Showing next market-moving reports.")
                for e in next_events[:8]:
                    st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
            else:
                st.caption(
                    f"No economic calendar data returned. FMP_API_KEY configured={'Yes' if bool(FMP_API_KEY) else 'No'}. "
                    "This may require FMP calendar endpoint access on your plan."
                )

    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            if earnings:
                edf = pd.DataFrame(earnings)
                st.dataframe(edf, use_container_width=True, hide_index=True)
            else:
                st.caption(
                    f"No earnings returned for today. FMP_API_KEY configured={'Yes' if bool(FMP_API_KEY) else 'No'}. "
                    "If key is configured, there may simply be no major earnings today or the endpoint is plan-limited."
                )

    with st.container(border=True):
        st.markdown("### 📰 Market News Ribbon / Table")
        if news:
            for h in news[:5]:
                st.markdown(f"• {safe_text(h)}")
        else:
            st.caption(
            "No broad market headlines returned. "
            f"NEWSAPI_KEY configured={'Yes' if bool((globals().get('NEWSAPI_KEY') or globals().get('NEWS_API_KEY') or os.getenv('NEWSAPI_KEY') or os.getenv('NEWS_API_KEY') or '').strip()) else 'No'}."
        )


def render_v424_analyst_ratings_box(row):
    ticker = safe_text(row.get("Ticker"), "").upper().strip()
    if not ticker:
        return
    data = v424_analyst_ratings_agent(
        ticker,
        current_price=row.get("Price"),
        ai_fair_value=row.get("AI Fair Value"),
    )
    with st.container(border=True):
        st.markdown("### 🏦 Analyst Ratings Agent")
        st.caption("Shows top analyst target data where available, plus consensus vs AI valuation.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Consensus Target", v424_money(data.get("consensus_target")))
        c2.metric("Analyst Count", "N/A" if data.get("analyst_count") is None else f"{int(v424_float(data.get('analyst_count'), 0))}")
        c3.metric("Consensus Upside", v424_pct(data.get("upside_pct")))
        c4.metric("AI vs Consensus", v424_pct(data.get("ai_gap_pct")))
        st.info(data.get("summary") or "Analyst ratings data processed.")

        rows = data.get("top_ratings") or []
        if rows:
            display = []
            for r in rows[:5]:
                display.append({
                    "Firm / Analyst": r.get("Firm"),
                    "Rating": r.get("Rating") or "N/A",
                    "Price Target": v424_money(r.get("Target")),
                    "Date": r.get("Date") or "",
                })
            st.markdown("**Top 5 analyst targets returned by source:**")
            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
        else:
            st.warning("Top 5 firm-level analyst targets were not returned by current data source. Consensus target is shown when available.")

        risks = data.get("risks") or []
        if risks:
            st.markdown("**Limits / watchouts:**")
            for r in risks[:4]:
                st.markdown(f"⚠️ {safe_text(r)}")


def render_v424_support_resistance_box(row):
    price = v424_float(row.get("Price"), None)
    s1 = v424_float(row.get("Support 1"), None)
    s2 = v424_float(row.get("Support 2"), None)
    r1 = v424_float(row.get("Resistance 1"), None)
    r2 = v424_float(row.get("Resistance 2"), None)
    breakout = v424_float(row.get("Breakout Level"), None)
    guidance = safe_text(row.get("Chart Guidance"), "")
    if not any([s1, s2, r1, r2, breakout, guidance]):
        return
    with st.container(border=True):
        st.markdown("### 📍 Support / Resistance Agent")
        c1, c2, c3 = st.columns(3)
        c1.metric("Current", v424_money(price))
        c2.metric("Support 1", v424_money(s1))
        c3.metric("Resistance 1", v424_money(r1))
        c4, c5, c6 = st.columns(3)
        c4.metric("Support 2", v424_money(s2))
        c5.metric("Resistance 2", v424_money(r2))
        c6.metric("Breakout", v424_money(breakout))
        if guidance:
            st.info(guidance)



# =========================
# UI
# =========================

def render_status_banner():
    state = read_state()

    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Includes live any-ticker research, visible 52-week fields, and interactive charts inside each research card.")

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.metric("Status", state.get("status", "unknown"))
    with c2:
        st.metric("Scanner Version", state.get("version", "N/A"))
    with c3:
        st.metric("Full Scan", state.get("full_scan_count", "N/A"))
    with c4:
        st.metric("Prescreen", state.get("prescreen_count", "N/A"))
    with c5:
        persisted = state.get("github_persisted", False)
        st.metric("GitHub Persisted", "✅" if persisted else "❌")

    if is_viewer():
        st.info("Viewer mode: view scans, search tickers, and open research cards. Admin controls remain hidden.")

    if state:
        generated = state.get("generated_at", "N/A")
        duration = state.get("duration_seconds", "N/A")
        st.caption(
            f"Last scan: {generated} | Duration: {duration}s | DATA_DIR={state.get('data_dir', '.')}"
        )


def render_score_help():
    st.markdown("### 📘 Quick Guide")

    with st.expander("Open dashboard guide: what each column means", expanded=True):
        st.markdown(
            """
            | Column | Plain-English Meaning | How to Use It |
            |---|---|---|
            | **Final Conviction** | Overall AI confidence score based on trend, momentum, liquidity, valuation/growth, analyst support, news, and risk. | Higher score = stronger overall setup, but still check upside and risk. |
            | **Setup Rating** | Plain-English label for the conviction score. | Elite/Strong means high-priority research candidate. |
            | **AI Fair Value** | The model's estimated value using analyst targets, growth, valuation, technical strength, volume, and risk. | Compare this to current price. |
            | **Target Upside %** | Potential upside from current price to AI Fair Value. | Higher upside is attractive, but very high upside usually means higher risk. |
            | **Analyst Target** | Wall Street/Finnhub consensus price target when available. | Helps compare AI estimate against analyst expectations. |
            | **Analyst Support** | Strength of analyst recommendations on a 0-100 scale. | Bullish/Constructive is better than Mixed/Weak. |
            | **News Sentiment** | Recent news tone from headlines. | Positive news can support momentum; negative news can increase risk. |
            | **Thesis Strength** | How many AI agents support the stock thesis. | Strong/Exceptional means multiple agents agree. |
            | **Evidence Confidence** | How much support exists behind the AI Fair Value and thesis. | High confidence means more data sources agree. |
            | **Insider Activity** | Recent insider buying/selling signal from Finnhub when available. | Positive insider buying can strengthen conviction; heavy selling adds caution. |
            | **Entry Range** | Preferred buy zone from the model. | Avoid chasing far above this range. |
            | **Stop Loss** | Suggested risk-control level. | Helps define downside before entering. |
            """
        )

        st.info(
            "Use the research card above each table to see the full thesis, why AI likes the stock, valuation, risks, and action plan."
        )


def render_table(df, title, key_prefix, min_score_default=35):
    st.subheader(title)

    if df.empty:
        st.info("No rows available yet.")
        return

    controls = st.columns([1, 1, 1, 2])

    with controls[0]:
        min_score = st.slider(
            "Minimum score",
            0,
            100,
            min_score_default,
            key=f"{key_prefix}_score",
            help="Filters out lower-confidence ideas. Final Conviction is the model's overall score."
        )
    with controls[1]:
        max_price = st.number_input(
            "Max price",
            min_value=0.0,
            value=0.0,
            step=5.0,
            key=f"{key_prefix}_max_price",
            help="Optional filter. Leave 0 to show all prices."
        )
    with controls[2]:
        min_upside = st.number_input(
            "Min upside %",
            value=float(MIN_UPSIDE_PCT * 100),
            step=1.0,
            key=f"{key_prefix}_min_upside",
            help="Filters by potential upside from current price to AI Fair Value."
        )
    with controls[3]:
        search = st.text_input(
            "Search ticker/company",
            key=f"{key_prefix}_search",
            help="Search by ticker or company name."
        )

    filtered = df.copy()
    filtered = filtered[filtered["Final Conviction"] >= min_score]
    filtered = filtered[filtered["Target Upside %"].fillna(-999) >= min_upside]

    if max_price > 0:
        filtered = filtered[filtered["Price"].fillna(999999) <= max_price]

    if search:
        s = search.strip().lower()
        filtered = filtered[
            filtered["Ticker"].str.lower().str.contains(s, na=False)
            | filtered["Company"].str.lower().str.contains(s, na=False)
        ]

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Rows", len(filtered), help="Number of stocks matching the current filters.")
    with m2:
        st.metric("Top Score", int(filtered["Final Conviction"].max()) if not filtered.empty else 0, help="Highest AI conviction score in the filtered table.")
    with m3:
        st.metric("Top Upside", fmt_pct(filtered["Target Upside %"].max()) if not filtered.empty else "N/A", help="Highest upside to AI Fair Value in the filtered table.")
    with m4:
        st.metric("Median Score", int(filtered["Final Conviction"].median()) if not filtered.empty else 0, help="Middle conviction score across the filtered results.")

    if filtered.empty:
        st.warning("No rows match filters.")
        return

    st.markdown("### 🔎 Full Research Card")
    tickers = filtered["Ticker"].dropna().unique().tolist()
    selected = st.selectbox(
        "Choose a ticker to view the full guidance",
        tickers,
        key=f"{key_prefix}_select",
        help="This opens the detailed thesis, valuation, risks, and action plan for the selected stock."
    )

    if selected:
        row = filtered[filtered["Ticker"].eq(selected)].iloc[0]
        render_detail(row)

    st.markdown("### 📋 Ranked Table")
    st.caption("This table is intentionally concise. Use the research card above for full guidance and decision context.")

    display_cols = [
        "Ticker",
        "Company",
        "Sector",
        "Price",
        "Final Conviction",
        "Setup Rating",
        "AI Fair Value",
        "Target Upside %",
        "52W Low",
        "52W High",
        "Range Position %",
        "Analyst Target",
        "Analyst Count",
        "Analyst Support",
        "News Sentiment",
        "Thesis Strength",
        "Evidence Confidence",
        "Insider Activity",
        "Entry Range",
        "Stop Loss",
    ]

    existing_cols = [c for c in display_cols if c in filtered.columns]
    display_df = filtered[existing_cols].head(100).copy()

    for col in ["Price", "AI Fair Value", "AI Bull Case", "AI Bear Case", "Analyst Target", "Stop Loss", "52W Low", "52W High"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: f"${safe_number(x, 0):,.2f}" if safe_number(x, 0) else "N/A"
            )

    if "Target Upside %" in display_df.columns:
        display_df["Target Upside %"] = display_df["Target Upside %"].apply(fmt_pct)
    if "Range Position %" in display_df.columns:
        display_df["Range Position %"] = display_df["Range Position %"].apply(fmt_pct)

    st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_detail(row):
    ticker = row.get("Ticker", "")
    company = row.get("Company", ticker)
    score = int(safe_number(row.get("Final Conviction"), 0))
    rating = safe_text(row.get("Setup Rating"), setup_label(score))

    st.markdown(f"## {ticker} — {company}")
    st.caption("This research card explains why the stock ranked highly, what the upside is, what could go wrong, and how to approach an entry.")
    st.markdown(f"### {rating} · {score}/100")

    research_summary = safe_text(row.get("Research Summary"), "")
    if research_summary:
        st.info(research_summary)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Price", fmt_money(row.get("Price")))
    c2.metric("AI Fair Value", fmt_money(row.get("AI Fair Value")))
    c3.metric("AI Upside", fmt_pct(row.get("Target Upside %")))
    c4.metric("Analyst Target", fmt_money(row.get("Analyst Target")))
    c5.metric("Analyst Count", int(safe_number(row.get("Analyst Count"), 0)))

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Bull Case", fmt_money(row.get("AI Bull Case")))
    c7.metric("Bear Case", fmt_money(row.get("AI Bear Case")))
    c8.metric("Stop Loss", fmt_money(row.get("Stop Loss")))
    c9.metric("Risk/Reward", safe_text(row.get("Risk/Reward"), "N/A"))

    render_v42_support_resistance(row)
    render_v423_ai_news_summary(row)
    render_v42_news_block(row)
    render_v423_conviction_meter(row)
    render_v423_why_ranked(row)
    render_v43_professional_research_card(row)
    render_v424_analyst_ratings_box(row)
    render_v424_support_resistance_box(row)
    render_v4243_technical_translation_box(row)
    render_detail_chart_v4184(row)
    render_v423_professional_trading_levels(row)
    render_inline_metric_summary(row)

    with st.expander("📚 Full metric education and AI vs analyst explanation", expanded=False):
        render_metric_education(row)

    render_v422_status(row)
    render_v42_tier_status(row)
    render_v42_diagnostics(row)
    render_agent_education_summary(row)
    v427_hide_duplicate_notice()
    render_v4251_standardized_committee(row)
    render_v42_committee_dashboard(row)

    st.markdown("---")

    st.markdown("### 🧠 AI Committee Summary")
    thesis_strength = safe_text(row.get("Thesis Strength"), "N/A")
    evidence_confidence = safe_text(row.get("Evidence Confidence"), "N/A")
    committee_conclusion = safe_text(row.get("Committee Conclusion"), "")
    valuation_reconciliation = safe_text(row.get("Valuation Reconciliation"), "")

    s1, s2, s3 = st.columns(3)
    s1.metric("Thesis Strength", thesis_strength)
    s2.metric("Evidence Confidence", evidence_confidence)
    s3.metric("Insider Activity", safe_text(row.get("Insider Activity"), "N/A"))

    if committee_conclusion:
        st.info(committee_conclusion)
    if valuation_reconciliation:
        st.caption(f"Valuation reconciliation: {valuation_reconciliation}")

    agents = safe_list(row.get("AI Committee"))
    if agents:
        with st.expander("Open AI agent-by-agent breakdown", expanded=True):
            for agent in agents:
                render_agent_card(agent)
    else:
        st.warning("AI Committee details are not available in this scan yet. Run the latest V41 scanner to populate agent summaries.")

    st.markdown("---")

    recovery_score = safe_number(row.get("Recovery Score"), 0)
    recovery_label = safe_text(row.get("Recovery Label"), "")
    if recovery_score:
        with st.container(border=True):
            st.markdown("### 🔄 Recovery Intelligence")
            st.markdown(f"**Recovery Score:** {int(recovery_score)}/100")
            if recovery_label:
                st.markdown(f"**Recovery Label:** {recovery_label}")
            thesis = safe_text(row.get("Recovery Thesis"), "")
            if thesis:
                st.write(thesis)
            drop_reason = safe_text(row.get("Recovery Drop Reason"), "")
            rebound_reason = safe_text(row.get("Recovery Rebound Reason"), "")
            recovery_risk = safe_text(row.get("Recovery Risk"), "")
            if drop_reason:
                st.markdown(f"**Why it dropped:** {drop_reason}")
            if rebound_reason:
                st.markdown(f"**Why it may recover:** {rebound_reason}")
            if recovery_risk:
                st.markdown(f"**Recovery risk:** {recovery_risk}")

    left, right = st.columns(2)

    with left:
        with st.container(border=True):
            st.markdown("### 🟢 Why We Like It")
            reasons = compact_reason_list(row.get("What Looks Good"), max_items=6)
            if not reasons:
                thesis = safe_text(row.get("Investment Thesis"), "")
                reasons = compact_reason_list(thesis, max_items=5)

            if reasons:
                for item in reasons:
                    st.markdown(f"✓ {item}")
            else:
                st.write("No positive factor summary available yet.")

            analyst_support = safe_text(row.get("Analyst Support"), "N/A")
            news_sentiment = safe_text(row.get("News Sentiment"), "N/A")
            st.markdown(f"**Analyst Support:** {analyst_support}")
            analyst_source = safe_text(row.get("Analyst Support Source"), "")
            if analyst_source:
                st.caption(f"Analyst support source: {analyst_source}")
            st.markdown(f"**News Sentiment:** {news_sentiment}")
            news_source = safe_text(row.get("News Sentiment Source"), "")
            if news_source:
                st.caption(f"News sentiment source: {news_source}")
            st.markdown(f"**Insider Activity:** {safe_text(row.get('Insider Activity'), 'N/A')}")

        with st.container(border=True):
            st.markdown("### 🎯 AI Valuation")
            st.markdown(f"**Current Price:** {fmt_money(row.get('Price'))}")
            st.markdown(f"**Analyst Target:** {fmt_money(row.get('Analyst Target'))}")
            st.markdown(f"**AI Fair Value:** {fmt_money(row.get('AI Fair Value'))}")
            st.markdown(f"**AI Upside:** {fmt_pct(row.get('Target Upside %'))}")
            st.markdown(f"**Bull Case:** {fmt_money(row.get('AI Bull Case'))}")
            st.markdown(f"**Bear Case:** {fmt_money(row.get('AI Bear Case'))}")

    with right:
        with st.container(border=True):
            st.markdown("### ⚠️ Key Risks")
            risk = safe_text(row.get("Primary Risk"), "")
            risk_items = compact_reason_list(risk, max_items=5)
            if risk_items:
                for item in risk_items:
                    st.markdown(f"• {item}")
            else:
                st.write("No specific risk summary available yet.")

        with st.container(border=True):
            st.markdown("### 📈 Action Plan")
            st.markdown(f"**Entry Zone:** {safe_text(row.get('Entry Range'), 'N/A')}")
            st.markdown(f"**Stop Loss:** {fmt_money(row.get('Stop Loss'))}")
            st.markdown(f"**First Target / Fair Value:** {fmt_money(row.get('AI Fair Value'))}")
            st.markdown(f"**Bull Case:** {fmt_money(row.get('AI Bull Case'))}")
            st.markdown(f"**Risk/Reward:** {safe_text(row.get('Risk/Reward'), 'N/A')}")

            action_note = safe_text(row.get("Action Note"), "")
            if action_note:
                st.caption(action_note)

    with st.expander("Full AI Thesis", expanded=False):
        thesis = safe_text(row.get("Investment Thesis"), "")
        if thesis:
            st.write(thesis)
        guidance = safe_text(row.get("Guidance"), "")
        if guidance:
            st.write(guidance)

    with st.expander("Target Logic", expanded=False):
        st.write(safe_text(row.get("Target Source"), "N/A"))
        note = safe_text(row.get("Target Confidence Note"), "")
        if note:
            st.caption(note)
        top_news = safe_text(row.get("Top News"), "")
        if top_news:
            st.markdown(f"**Top News:** {top_news}")

    render_v4251_final_ai_thesis(row)

    with st.expander("Raw row data", expanded=False):
        raw = row.get("Raw", {})
        st.json(raw if isinstance(raw, dict) else {})


def render_market_summary(full_df):
    st.subheader("Market Scan Summary")

    if full_df.empty:
        st.info("No scan data available.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Ideas", len(full_df))
    c2.metric("Avg Score", int(full_df["Final Conviction"].mean()))
    c3.metric("Median Upside", fmt_pct(full_df["Target Upside %"].median()))
    c4.metric("FMP Enriched", int(full_df["Source FMP"].sum()) if "Source FMP" in full_df else 0)
    c5.metric("Manual Watchlist Count", len(read_watchlist_symbols()))

    if "Sector" in full_df.columns:
        sector_counts = full_df["Sector"].fillna("Unknown").value_counts().head(10)
        st.bar_chart(sector_counts)



def read_watchlist_symbols():
    try:
        data = read_json_file(WATCHLIST_FILE)
        if isinstance(data, dict):
            symbols = data.get("symbols", [])
        elif isinstance(data, list):
            symbols = data
        else:
            symbols = []

        cleaned = []
        for item in symbols:
            sym = safe_text(item, "").upper().strip()
            if sym:
                cleaned.append(sym)
        return list(dict.fromkeys(cleaned))
    except Exception:
        return []


def write_watchlist_symbols(symbols):
    cleaned = []
    for item in symbols:
        sym = safe_text(item, "").upper().strip()
        if sym and "." not in sym and "/" not in sym and len(sym) <= 7:
            cleaned.append(sym)

    payload = {"symbols": list(dict.fromkeys(cleaned))}

    try:
        with WATCHLIST_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return True
    except Exception as exc:
        st.error(f"Could not update watchlist: {exc}")
        return False


def add_symbol_to_watchlist(symbol):
    symbol = safe_text(symbol, "").upper().strip()
    if not symbol:
        return False

    symbols = read_watchlist_symbols()
    if symbol not in symbols:
        symbols.append(symbol)
        return write_watchlist_symbols(symbols)

    return True


def find_ticker_row(ticker, *dfs):
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return None
    for df in dfs:
        if df is not None and not df.empty and "Ticker" in df.columns:
            matched = df[df["Ticker"].astype(str).str.upper().eq(ticker)]
            if not matched.empty:
                return matched.iloc[0]
    return None


def _safe_float_live(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


@st.cache_data(ttl=900)
def build_live_research_row(ticker):
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return None

    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        hist = yf.download(ticker, period="5y", interval="1d", auto_adjust=True, progress=False, threads=False)
        if hist is None or hist.empty:
            return None

        hist = hist.dropna(subset=["Close"]).copy()
        if hist.empty:
            return None

        close = hist["Close"].astype(float)
        high = hist["High"].astype(float) if "High" in hist else close
        low = hist["Low"].astype(float) if "Low" in hist else close
        volume = hist["Volume"].astype(float) if "Volume" in hist else pd.Series(index=hist.index, data=0)

        price = float(close.iloc[-1])
        sma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else price
        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else price

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1]) if rsi_series.notna().any() else 50.0

        avg_vol_20 = float(volume.tail(20).mean()) if len(volume) >= 20 else float(volume.mean())
        latest_vol = float(volume.iloc[-1]) if len(volume) else 0
        volume_ratio = latest_vol / avg_vol_20 if avg_vol_20 else 1

        tr = (high - low).abs()
        atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(tr.mean())
        atr_pct = (atr / price) * 100 if price else 0

        high_52 = float(high.tail(min(252, len(high))).max())
        low_52 = float(low.tail(min(252, len(low))).min())
        range_pos = ((price - low_52) / (high_52 - low_52)) * 100 if high_52 > low_52 else 0
        dist_high = ((price - high_52) / high_52) * 100 if high_52 else 0
        dist_low = ((price - low_52) / low_52) * 100 if low_52 else 0

        def ret(days):
            if len(close) > days:
                base = float(close.iloc[-days-1])
                return ((price - base) / base) * 100 if base else 0
            return 0

        analyst_target = _safe_float_live(info.get("targetMeanPrice"), 0) or 0
        analyst_count = int(_safe_float_live(info.get("numberOfAnalystOpinions"), 0) or 0)
        recommendation = safe_text(info.get("recommendationKey"), "").replace("_", " ").title()

        revenue_growth = _safe_float_live(info.get("revenueGrowth"), None)
        earnings_growth = _safe_float_live(info.get("earningsGrowth"), None)
        forward_pe = _safe_float_live(info.get("forwardPE"), None)
        peg_ratio = _safe_float_live(info.get("pegRatio"), None)
        debt_to_equity = _safe_float_live(info.get("debtToEquity"), None)
        current_ratio = _safe_float_live(info.get("currentRatio"), None)
        gross_margin = _safe_float_live(info.get("grossMargins"), None)
        op_margin = _safe_float_live(info.get("operatingMargins"), None)
        profit_margin = _safe_float_live(info.get("profitMargins"), None)
        free_cash_flow = _safe_float_live(info.get("freeCashflow"), 0) or 0
        operating_cash_flow = _safe_float_live(info.get("operatingCashflow"), 0) or 0
        latest_eps = _safe_float_live(info.get("trailingEps"), 0) or 0

        ai_fair = analyst_target if analyst_target > 0 else price * (1.10 if price > sma50 else 1.04)
        if revenue_growth is not None and revenue_growth >= 0.15:
            ai_fair *= 1.08
        if earnings_growth is not None and earnings_growth >= 0.15:
            ai_fair *= 1.05
        if atr_pct > 8:
            ai_fair *= 0.96

        upside = ((ai_fair - price) / price) * 100 if price else 0

        technical_score = 50
        if price > sma20: technical_score += 10
        if price > sma50: technical_score += 12
        if price > sma200: technical_score += 10
        if 45 <= rsi <= 70: technical_score += 8
        elif rsi > 75: technical_score -= 5
        if volume_ratio >= 1.2: technical_score += 5
        if atr_pct > 8: technical_score -= 6
        technical_score = int(min(max(technical_score, 20), 95))

        finance_score = 50
        finance_findings = []
        finance_risks = []

        if revenue_growth is not None:
            if revenue_growth >= 0.15:
                finance_score += 12
                finance_findings.append(f"Revenue growth is strong at {revenue_growth*100:.1f}%")
            elif revenue_growth >= 0.05:
                finance_score += 6
                finance_findings.append(f"Revenue growth is positive at {revenue_growth*100:.1f}%")
            else:
                finance_risks.append(f"Revenue growth is weak at {revenue_growth*100:.1f}%")

        if earnings_growth is not None:
            if earnings_growth >= 0.15:
                finance_score += 10
                finance_findings.append(f"Earnings growth is strong at {earnings_growth*100:.1f}%")
            elif earnings_growth >= 0:
                finance_score += 4
                finance_findings.append(f"Earnings growth is positive at {earnings_growth*100:.1f}%")
            else:
                finance_score -= 8
                finance_risks.append("Earnings growth is negative")

        if debt_to_equity is not None:
            de = debt_to_equity / 100 if debt_to_equity > 10 else debt_to_equity
            if de < 0.5:
                finance_score += 6
                finance_findings.append(f"Debt-to-equity is low at {de:.2f}")
            elif de <= 1.5:
                finance_score += 2
                finance_findings.append(f"Debt-to-equity is manageable at {de:.2f}")
            else:
                finance_score -= 6
                finance_risks.append(f"Debt-to-equity is elevated at {de:.2f}")
            debt_to_equity = de

        if current_ratio is not None:
            if current_ratio >= 1.5:
                finance_score += 4
                finance_findings.append(f"Current ratio is healthy at {current_ratio:.2f}")
            elif current_ratio < 1:
                finance_score -= 4
                finance_risks.append(f"Current ratio is below 1.0 at {current_ratio:.2f}")

        if free_cash_flow > 0:
            finance_score += 6
            finance_findings.append("Free cash flow is positive")
        elif free_cash_flow < 0:
            finance_score -= 5
            finance_risks.append("Free cash flow is negative")

        finance_score = int(min(max(finance_score, 15), 98))

        analyst_support = 50
        if analyst_target:
            analyst_support += min(max(upside, -20), 50) * 0.45
        if analyst_count >= 20:
            analyst_support += 8
        elif analyst_count >= 5:
            analyst_support += 5
        if recommendation in {"Buy", "Strong Buy"}:
            analyst_support += 10
        elif recommendation in {"Sell", "Underperform"}:
            analyst_support -= 15
        analyst_support = int(min(max(analyst_support, 0), 100))

        upside_score = 90 if upside >= 40 else 82 if upside >= 25 else 68 if upside >= 10 else 55 if upside >= 0 else 35
        conviction = int(round((technical_score * 0.35) + (finance_score * 0.30) + (upside_score * 0.20) + (analyst_support * 0.15)))
        conviction = int(min(max(conviction, 20), 97))

        thesis_strength = "Exceptional Thesis" if conviction >= 90 and finance_score >= 80 else "Strong Thesis" if conviction >= 80 else "Moderate Thesis" if conviction >= 65 else "Developing Thesis"
        evidence_confidence = "High" if analyst_count >= 10 and finance_score >= 75 else "Medium-High" if analyst_count >= 5 else "Medium"

        entry_low = price * 0.97
        entry_high = price * 1.01
        stop_loss = price * (1 - max(0.06, min(0.14, atr_pct / 100 * 2)))
        bull_case = ai_fair * 1.15

        finance_findings = finance_findings or ["Live finance data is limited; review latest company filings before acting"]
        finance_risks = finance_risks or ["No major live financial red flag detected from available Yahoo data"]

        raw = {
            "revenue_growth": revenue_growth,
            "earnings_growth": earnings_growth,
            "forward_pe": forward_pe,
            "peg_ratio": peg_ratio,
            "latest_eps": latest_eps,
            "debt_to_equity": debt_to_equity,
            "current_ratio": current_ratio,
            "gross_profit_margin": gross_margin,
            "operating_profit_margin": op_margin,
            "net_profit_margin": profit_margin,
            "free_cash_flow": free_cash_flow,
            "operating_cash_flow": operating_cash_flow,
            "source_live_research": True,
        }

        committee = {
            "Technical Agent": {
                "score": technical_score, "status": "Positive" if technical_score >= 75 else "Mixed", "impact": "Positive" if technical_score >= 75 else "Neutral",
                "data_used": "Live Yahoo price history, SMA20/50/200, RSI, volume, ATR",
                "summary": "Live technical check from on-demand history.",
                "findings": [f"Price vs SMA20: {'above' if price > sma20 else 'below'}", f"Price vs SMA50: {'above' if price > sma50 else 'below'}", f"Price vs SMA200: {'above' if price > sma200 else 'below'}", f"RSI is {rsi:.1f}", f"Volume ratio is {volume_ratio:.2f}x"],
                "risks": [f"ATR volatility is {atr_pct:.1f}%"], "bottom_line": "Technical setup is constructive." if technical_score >= 75 else "Technical setup needs confirmation."
            },
            "Finance Agent": {
                "score": finance_score, "status": "Positive" if finance_score >= 75 else "Mixed", "impact": "Positive" if finance_score >= 75 else "Neutral",
                "data_used": "Live Yahoo fundamentals, margins, debt, liquidity, cash flow",
                "summary": "Live financial execution check.",
                "findings": finance_findings, "risks": finance_risks,
                "bottom_line": "Financial profile supports the thesis." if finance_score >= 75 else "Financial profile is mixed or limited."
            },
            "Analyst Agent": {
                "score": analyst_support, "status": "Positive" if analyst_support >= 60 else "Mixed", "impact": "Positive" if analyst_support >= 60 else "Neutral",
                "data_used": "Yahoo analyst target, analyst count, recommendation key",
                "summary": "Live analyst support check.",
                "findings": [f"Analyst target: {fmt_money(analyst_target) if analyst_target else 'N/A'}", f"Analyst count: {analyst_count}", f"Recommendation: {recommendation or 'N/A'}"],
                "risks": ["Analyst data may lag real-time revisions."],
                "bottom_line": "Analyst data supports the thesis." if analyst_support >= 60 else "Analyst data is mixed or limited."
            },
        }

        return {
            "Ticker": ticker, "Company": safe_text(info.get("longName") or info.get("shortName"), ticker),
            "Sector": safe_text(info.get("sector"), "N/A"), "Industry": safe_text(info.get("industry"), "N/A"),
            "Price": round(price, 2), "Final Conviction": conviction,
            "Setup Rating": "🟢 Elite Setup" if conviction >= 90 else "🟡 Strong Setup" if conviction >= 80 else "🔵 Watchlist",
            "AI Fair Value": round(ai_fair, 2), "Target Upside %": round(upside, 1),
            "Analyst Target": round(analyst_target, 2) if analyst_target else 0, "Analyst Count": analyst_count,
            "Analyst Support": analyst_support_label(analyst_support), "Analyst Support Source": "Live Yahoo analyst fallback",
            "News Sentiment": "⚪ Neutral", "News Sentiment Source": "Live on-demand mode defaults news to neutral unless scan data exists",
            "Entry Range": f"${entry_low:.2f} - ${entry_high:.2f}", "Stop Loss": round(stop_loss, 2), "Risk/Reward": "Live",
            "AI Bull Case": round(bull_case, 2), "AI Bear Case": round(stop_loss, 2),
            "52W High": round(high_52, 2), "52W Low": round(low_52, 2), "Range Position %": round(range_pos, 1),
            "Distance From 52W High %": round(dist_high, 1), "Distance From 52W Low %": round(dist_low, 1),
            "Drawdown From High %": round(dist_high, 1), "Range Position Label": "Near 52-week highs" if range_pos >= 75 else "Lower range" if range_pos <= 35 else "Middle range",
            "Drawdown Label": "Moderate drawdown" if dist_high <= -10 else "Shallow drawdown",
            "Return 1M %": round(ret(21), 1), "Return 3M %": round(ret(63), 1), "Return 6M %": round(ret(126), 1),
            "Return 1Y %": round(ret(252), 1), "Return 3Y %": round(ret(252*3), 1), "Return 5Y %": round(ret(252*5), 1),
            "History Days Available": len(close), "Price History Note": "Live 5-year chart and 52-week range fetched on demand.",
            "RSI": round(rsi, 1), "ATR %": round(atr_pct, 1), "Volume Ratio": round(volume_ratio, 2), "20D %": round(ret(21), 1), "60D %": round(ret(63), 1),
            "Finance Agent Score": finance_score, "Finance Agent Status": "Positive" if finance_score >= 75 else "Mixed",
            "Finance Agent Bottom Line": "Financial profile supports the thesis." if finance_score >= 75 else "Financial profile is mixed or limited.",
            "Finance Agent Findings": finance_findings, "Finance Agent Risks": finance_risks,
            "Latest EPS": latest_eps, "Debt to Equity": debt_to_equity or 0, "Current Ratio": current_ratio or 0,
            "Gross Margin": gross_margin or 0, "Operating Margin": op_margin or 0, "Net Margin": profit_margin or 0,
            "Free Cash Flow": free_cash_flow or 0, "Operating Cash Flow": operating_cash_flow or 0,
            "Thesis Strength": thesis_strength, "Evidence Confidence": evidence_confidence,
            "Investment Thesis": f"{ticker} live research card generated on demand. The setup is {thesis_strength.lower()} with {conviction}/100 conviction.",
            "Primary Risk": "Live on-demand research may not include all FMP/Finnhub/NewsAPI fields until the next full scan.",
            "Guidance": f"Live AI view: conviction {conviction}/100, AI fair value {fmt_money(ai_fair)}, upside {upside:.1f}%.",
            "Action Note": "Use this live card for immediate review; full cron scan may add deeper FMP/Finnhub/NewsAPI details later.",
            "AI Committee": committee, "Raw": raw, "Live Research": True,
        }
    except Exception as exc:
        return {"error": str(exc), "Ticker": ticker}


@st.cache_data(ttl=900)
def build_price_only_live_row(ticker, reason="Live fundamentals unavailable"):
    """
    V41.8.2 fallback card.
    Used when Yahoo quoteSummary/info is rate-limited.
    Still produces a usable research card from price history, 52W range, RSI, SMA, ATR, and chart data.
    """
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return None

    hist = yf.download(
        ticker,
        period="5y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if hist is None or hist.empty:
        return None

    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = [c[0] if isinstance(c, tuple) else c for c in hist.columns]

    hist = hist.dropna(subset=["Close"]).copy()
    if hist.empty:
        return None

    close = hist["Close"].astype(float)
    high = hist["High"].astype(float) if "High" in hist else close
    low = hist["Low"].astype(float) if "Low" in hist else close
    volume = hist["Volume"].astype(float) if "Volume" in hist else pd.Series(index=hist.index, data=0)

    price = float(close.iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else price
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else price

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = float(rsi_series.iloc[-1]) if rsi_series.notna().any() else 50.0

    avg_vol_20 = float(volume.tail(20).mean()) if len(volume) >= 20 else float(volume.mean())
    latest_vol = float(volume.iloc[-1]) if len(volume) else 0
    volume_ratio = latest_vol / avg_vol_20 if avg_vol_20 else 1

    tr = (high - low).abs()
    atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(tr.mean())
    atr_pct = (atr / price) * 100 if price else 0

    high_52 = float(high.tail(min(252, len(high))).max())
    low_52 = float(low.tail(min(252, len(low))).min())
    range_pos = ((price - low_52) / (high_52 - low_52)) * 100 if high_52 > low_52 else 0
    dist_high = ((price - high_52) / high_52) * 100 if high_52 else 0
    dist_low = ((price - low_52) / low_52) * 100 if low_52 else 0

    def ret(days):
        if len(close) > days:
            base = float(close.iloc[-days-1])
            return ((price - base) / base) * 100 if base else 0
        return 0

    technical_score = 50
    if price > sma20: technical_score += 10
    if price > sma50: technical_score += 12
    if price > sma200: technical_score += 10
    if 45 <= rsi <= 70: technical_score += 8
    elif rsi > 75: technical_score -= 5
    if volume_ratio >= 1.2: technical_score += 5
    if atr_pct > 8: technical_score -= 6
    technical_score = int(min(max(technical_score, 20), 95))

    ai_fair = price * (1.08 if price > sma50 else 1.03)
    upside = ((ai_fair - price) / price) * 100 if price else 0
    upside_score = 82 if upside >= 25 else 68 if upside >= 10 else 55 if upside >= 0 else 35
    conviction = int(round((technical_score * 0.70) + (upside_score * 0.30)))
    conviction = int(min(max(conviction, 20), 92))

    stop_loss = price * (1 - max(0.06, min(0.14, atr_pct / 100 * 2)))
    entry_low = price * 0.97
    entry_high = price * 1.01

    finance_risks = [
        "Live fundamentals were rate-limited or unavailable.",
        "Finance Agent is limited until the next full cron scan pulls FMP/Finnhub/NewsAPI data.",
        safe_text(reason, "Live data rate-limited")[:180],
    ]

    committee = {
        "Technical Agent": {
            "score": technical_score,
            "status": "Positive" if technical_score >= 75 else "Mixed",
            "impact": "Positive" if technical_score >= 75 else "Neutral",
            "data_used": "Live Yahoo price history, SMA20/50/200, RSI, volume, ATR",
            "summary": "Rate-limit-safe live technical card from price history.",
            "findings": [
                f"Price vs SMA20: {'above' if price > sma20 else 'below'}",
                f"Price vs SMA50: {'above' if price > sma50 else 'below'}",
                f"Price vs SMA200: {'above' if price > sma200 else 'below'}",
                f"RSI is {rsi:.1f}",
                f"Volume ratio is {volume_ratio:.2f}x",
                f"52W range position is {range_pos:.1f}%",
            ],
            "risks": [f"ATR volatility is {atr_pct:.1f}%"],
            "bottom_line": "Technical setup is constructive." if technical_score >= 75 else "Technical setup needs confirmation.",
        },
        "Finance Agent": {
            "score": 50,
            "status": "Limited",
            "impact": "Neutral",
            "data_used": "Fundamentals unavailable in live mode due to rate limit; full scan uses deeper API data.",
            "summary": "Finance data is limited for this immediate card.",
            "findings": ["Price/technical live research completed successfully."],
            "risks": finance_risks,
            "bottom_line": "Financial fields are limited right now. Use the next full scan for deeper Finance Agent analysis.",
        },
        "Analyst Agent": {
            "score": 50,
            "status": "Limited",
            "impact": "Neutral",
            "data_used": "Analyst target unavailable in rate-limit-safe fallback mode.",
            "summary": "Analyst data is limited until next full scan or Yahoo rate limit clears.",
            "findings": ["No live analyst target returned."],
            "risks": ["Analyst/Finnhub details may populate on full cron scan."],
            "bottom_line": "Analyst data is limited for this immediate card.",
        },
    }

    return {
        "Ticker": ticker,
        "Company": ticker,
        "Sector": "N/A",
        "Industry": "N/A",
        "Price": round(price, 2),
        "Final Conviction": conviction,
        "Setup Rating": "🟡 Strong Setup" if conviction >= 80 else "🔵 Watchlist",
        "AI Fair Value": round(ai_fair, 2),
        "Target Upside %": round(upside, 1),
        "Analyst Target": 0,
        "Analyst Count": 0,
        "Analyst Support": "Coverage-based",
        "Analyst Support Source": "Rate-limit-safe fallback",
        "News Sentiment": "⚪ Neutral",
        "News Sentiment Source": "Live fallback defaults news to neutral until full scan",
        "Entry Range": f"${entry_low:.2f} - ${entry_high:.2f}",
        "Stop Loss": round(stop_loss, 2),
        "Risk/Reward": "Live fallback",
        "AI Bull Case": round(ai_fair * 1.12, 2),
        "AI Bear Case": round(stop_loss, 2),
        "52W High": round(high_52, 2),
        "52W Low": round(low_52, 2),
        "Range Position %": round(range_pos, 1),
        "Distance From 52W High %": round(dist_high, 1),
        "Distance From 52W Low %": round(dist_low, 1),
        "Drawdown From High %": round(dist_high, 1),
        "Range Position Label": "Near 52-week highs" if range_pos >= 75 else "Lower range" if range_pos <= 35 else "Middle range",
        "Drawdown Label": "Moderate drawdown" if dist_high <= -10 else "Shallow drawdown",
        "Return 1M %": round(ret(21), 1),
        "Return 3M %": round(ret(63), 1),
        "Return 6M %": round(ret(126), 1),
        "Return 1Y %": round(ret(252), 1),
        "Return 3Y %": round(ret(252*3), 1),
        "Return 5Y %": round(ret(252*5), 1),
        "History Days Available": len(close),
        "Price History Note": "Rate-limit-safe live chart and 52-week range fetched on demand.",
        "RSI": round(rsi, 1),
        "ATR %": round(atr_pct, 1),
        "Volume Ratio": round(volume_ratio, 2),
        "20D %": round(ret(21), 1),
        "60D %": round(ret(63), 1),
        "Finance Agent Score": 50,
        "Finance Agent Status": "Limited",
        "Finance Agent Bottom Line": "Financial fields are limited due to rate limit; price/technical card is available.",
        "Finance Agent Findings": ["Price/technical live research completed successfully."],
        "Finance Agent Risks": finance_risks,
        "Latest EPS": 0,
        "Debt to Equity": 0,
        "Current Ratio": 0,
        "Gross Margin": 0,
        "Operating Margin": 0,
        "Net Margin": 0,
        "Free Cash Flow": 0,
        "Operating Cash Flow": 0,
        "Thesis Strength": "Moderate Thesis" if conviction >= 65 else "Developing Thesis",
        "Evidence Confidence": "Medium-Low",
        "Investment Thesis": f"{ticker} live fallback card generated from price history due to rate limits.",
        "Primary Risk": "Finance/analyst/news data is limited until full scan or rate limit clears.",
        "Guidance": f"Live fallback view: conviction {conviction}/100, technical fair value {fmt_money(ai_fair)}, upside {upside:.1f}%.",
        "Action Note": "Use this for immediate chart/technical review; run full cron scan for deeper API-backed research.",
        "AI Committee": committee,
        "Raw": {"source_live_fallback": True, "fundamentals_limited": True},
        "Live Research": True,
    }


def render_research_any_ticker(full_df, recovery_df, watch_df, prescreen_df, etf_df=None):
    st.subheader("🔍 Research Any Ticker")
    st.caption("Search existing scan files first. If not found, run live AI research immediately without waiting for cron.")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        ticker = st.text_input("Enter ticker", placeholder="NVDA, MSFT, PLTR, ELF, ZS", key="research_any_ticker").upper().strip()
    with c2:
        st.write("")
        st.write("")
        open_card = st.button("Open Research Card", key="research_any_ticker_btn")
    with c3:
        st.write("")
        st.write("")
        force_live = st.button("⚡ Run Live AI", key="force_live_research_btn")
    with c4:
        st.write("")
        st.write("")
        add_watch = st.button("➕ Add to Watchlist", key="add_any_ticker_watchlist_btn")

    if ticker:
        current_watchlist = read_watchlist_symbols()
        if ticker in current_watchlist:
            st.success(f"{ticker} is already in your watchlist.")

        if add_watch:
            if add_symbol_to_watchlist(ticker):
                st.success(f"{ticker} added to watchlist.")

    if ticker and (open_card or force_live or ticker):
        row = None if force_live else find_ticker_row(ticker, full_df, recovery_df, watch_df, prescreen_df, etf_df)

        if row is not None:
            render_detail(row)
        else:
            with st.spinner(f"Running live AI research for {ticker}..."):
                live_row = build_live_research_row(ticker)

            if not live_row:
                st.error(f"Could not fetch live data for {ticker}. Please verify the ticker symbol.")
            elif isinstance(live_row, dict) and live_row.get("error"):
                st.warning(f"Full live research was limited for {ticker}: {live_row.get('error')}")
                with st.spinner(f"Building rate-limit-safe price/technical card for {ticker}..."):
                    fallback_row = build_price_only_live_row(ticker, reason=live_row.get("error"))
                if fallback_row:
                    st.info("Showing rate-limit-safe live card now. The next full cron scan may add deeper FMP/Finnhub/NewsAPI details.")
                    render_detail(pd.Series(fallback_row))
                else:
                    st.error(f"Could not fetch even price-history data for {ticker}. Try again later.")
            else:
                st.info("Live card generated now. The next full cron scan may add deeper FMP/Finnhub/NewsAPI details.")
                render_detail(pd.Series(live_row))


def render_chat_helper(full_df):
    st.subheader("Ask About the Scan")

    question = st.text_input("Ask about a ticker or ranking", placeholder="Why did NVDA score high?")

    if not question:
        return

    q = question.lower().strip()
    if full_df.empty:
        st.info("No scan data loaded.")
        return

    matched = None
    for ticker in full_df["Ticker"].dropna().unique():
        if ticker.lower() in q:
            rows = full_df[full_df["Ticker"].eq(ticker)]
            if not rows.empty:
                matched = rows.iloc[0]
                break

    if matched is None:
        st.info("Type a ticker from the table, such as MSFT, NVDA, META, or PLTR.")
        return

    ticker = matched.get("Ticker")
    st.markdown(f"### {ticker} Quick Explanation")
    st.write(
        f"{ticker} has an AI score of {int(safe_number(matched.get('Final Conviction'), 0))}, "
        f"AI fair value of {fmt_money(matched.get('AI Fair Value'))}, and estimated upside of "
        f"{fmt_pct(matched.get('Target Upside %'))}."
    )

    thesis = safe_text(matched.get("Investment Thesis"), "")
    if thesis:
        st.write(thesis)

    committee = safe_text(matched.get("Committee Conclusion"), "")
    if committee:
        st.info(committee)

    risk = safe_text(matched.get("Primary Risk"), "")
    if risk:
        st.warning(risk)


# =========================
# MAIN APP
# =========================





def get_configured_viewer_passwords():
    candidates = {
        "VIEWER_PASSWORD": (os.getenv("VIEWER_PASSWORD") or "").strip(),
        "GUEST_PASSWORD": (os.getenv("GUEST_PASSWORD") or "").strip(),
        "VIEW_PASSWORD": (os.getenv("VIEW_PASSWORD") or "").strip(),
    }
    return {k: v for k, v in candidates.items() if v}


def viewer_password_matches(password):
    password = (password or "").strip()
    return bool(password) and any(password == v for v in get_configured_viewer_passwords().values())


# Backward-compatible aliases so any old code path still uses the hard-fixed login gate.







def dashboard_login_gate():
    if st.session_state.get("authenticated"):
        return True

    viewer_passwords = get_configured_viewer_passwords()

    if not ADMIN_PASSWORD and not viewer_passwords:
        st.session_state["authenticated"] = True
        st.session_state["role"] = "admin"
        return True

    st.title("🔐 AI Stock Dashboard Login")
    st.caption(f"Running: {APP_VERSION}")
    st.info("Admin password opens admin mode. Any configured viewer password opens guest/viewer mode.")

    with st.expander("Login diagnostics"):
        st.caption(f"APP_VERSION: {APP_VERSION}")
        st.caption(f"Admin password configured: {'Yes' if bool(ADMIN_PASSWORD) else 'No'}")
        st.caption(f"VIEWER_PASSWORD configured: {'Yes' if bool((os.getenv('VIEWER_PASSWORD') or '').strip()) else 'No'} | length: {len((os.getenv('VIEWER_PASSWORD') or '').strip())}")
        st.caption(f"GUEST_PASSWORD configured: {'Yes' if bool((os.getenv('GUEST_PASSWORD') or '').strip()) else 'No'} | length: {len((os.getenv('GUEST_PASSWORD') or '').strip())}")
        st.caption(f"VIEW_PASSWORD configured: {'Yes' if bool((os.getenv('VIEW_PASSWORD') or '').strip()) else 'No'} | length: {len((os.getenv('VIEW_PASSWORD') or '').strip())}")
        st.caption("V42.3.4: Viewer login no longer requires username.")

    password = st.text_input("Password", type="password").strip()

    if st.button("Login"):
        st.session_state["last_login_typed_length"] = len(password)

        if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
            st.session_state["authenticated"] = True
            st.session_state["role"] = "admin"
            st.rerun()

        if viewer_password_matches(password):
            st.session_state["authenticated"] = True
            st.session_state["role"] = "viewer"
            st.rerun()

        st.error(f"Invalid password. Typed password length: {len(password)}. Match it to one of the configured viewer password lengths above.")

    return False


def check_login():
    return dashboard_login_gate()


def require_login():
    return dashboard_login_gate()



# =========================
# V42.4.2 COMMAND CENTER FALLBACK SOURCES
# =========================

def v4242_source_label(label, ok=True):
    return {"source": label, "ok": bool(ok)}


@st.cache_data(ttl=300)
def v4242_yahoo_quote(symbol):
    """
    Fallback quote via yfinance when FMP quote endpoint is unavailable/plan-limited.
    """
    symbol = safe_text(symbol, "").upper().strip()
    if not symbol:
        return {}
    yf_symbol = {"VIX": "^VIX"}.get(symbol, symbol)
    try:
        t = yf.Ticker(yf_symbol)
        price = None
        prev = None

        # fast_info is quicker and usually works.
        try:
            fi = t.fast_info
            price = fi.get("last_price") or fi.get("lastPrice")
            prev = fi.get("previous_close") or fi.get("previousClose")
        except Exception:
            pass

        # Fallback to short history.
        if price is None:
            hist = t.history(period="5d", interval="1d", auto_adjust=False)
            if hist is not None and not hist.empty:
                price = float(hist["Close"].dropna().iloc[-1])
                if len(hist["Close"].dropna()) >= 2:
                    prev = float(hist["Close"].dropna().iloc[-2])

        pct = None
        if price is not None and prev:
            pct = ((float(price) - float(prev)) / float(prev)) * 100

        if price is not None:
            return {
                "symbol": symbol,
                "price": float(price),
                "change_pct": pct,
                "source": "Yahoo/yfinance fallback",
            }
    except Exception:
        return {}
    return {}


@st.cache_data(ttl=300)
def v424_quote(symbol):
    """
    V42.4.2 override:
    Quote source priority:
      1) FMP quote endpoint
      2) Yahoo/yfinance fallback
    """
    symbol = safe_text(symbol, "").upper().strip()
    if not symbol:
        return {}

    # Try original/FMP path directly
    try:
        if FMP_API_KEY:
            data = v424_fmp_get(f"quote/{symbol}") if "v424_fmp_get" in globals() else None
            if isinstance(data, list) and data:
                q = data[0]
                if q.get("price") not in (None, ""):
                    return {
                        "symbol": symbol,
                        "price": q.get("price"),
                        "change_pct": q.get("changesPercentage"),
                        "change": q.get("change"),
                        "name": q.get("name"),
                        "source": "FMP",
                    }
    except Exception:
        pass

    return v4242_yahoo_quote(symbol)


@st.cache_data(ttl=900)
def v424_market_quotes():
    """
    V42.4.2 override with Yahoo fallback.
    """
    symbols = ["SPY", "QQQ", "DIA", "IWM", "VIX"]
    rows = []
    for s in symbols:
        q = v424_quote(s)
        if q:
            rows.append(q)
    return rows


@st.cache_data(ttl=900)
def v4242_nasdaq_earnings_today():
    """
    No-key public Nasdaq earnings-calendar fallback.
    This endpoint can occasionally block cloud hosts; if so, we fail safely.
    """
    rows = []
    try:
        today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()
        url = "https://api.nasdaq.com/api/calendar/earnings"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/market-activity/earnings",
        }
        r = requests.get(url, params={"date": today.isoformat()}, headers=headers, timeout=12)
        if r.status_code == 200:
            data = r.json() or {}
            table = (((data.get("data") or {}).get("rows")) or [])
            for item in table:
                sym = safe_text(item.get("symbol") or "").upper()
                if not sym:
                    continue
                rows.append({
                    "Symbol": sym,
                    "Date": today.isoformat(),
                    "Time": safe_text(item.get("time") or item.get("timeOfDay") or ""),
                    "EPS Est": item.get("epsForecast") or item.get("eps_estimate"),
                    "Revenue Est": item.get("revenueForecast") or item.get("revenue_estimate"),
                    "Source": "Nasdaq public fallback",
                })
                if len(rows) >= 30:
                    break
    except Exception:
        pass
    return rows


@st.cache_data(ttl=1800)
def v4242_alpha_vantage_earnings_today():
    """
    Optional Alpha Vantage fallback if ALPHA_VANTAGE_API_KEY is configured.
    """
    rows = []
    try:
        key = (globals().get("ALPHA_VANTAGE_API_KEY") or os.getenv("ALPHA_VANTAGE_API_KEY") or "").strip()
        if not key:
            return rows
        url = "https://www.alphavantage.co/query"
        r = requests.get(url, params={"function": "EARNINGS_CALENDAR", "horizon": "3month", "apikey": key}, timeout=15)
        if r.status_code == 200 and r.text:
            today = (v424_today() if "v424_today" in globals() else dt.datetime.now().date()).isoformat()
            reader = csv.DictReader(StringIO(r.text))
            for item in reader:
                if safe_text(item.get("reportDate")) != today:
                    continue
                sym = safe_text(item.get("symbol")).upper()
                if not sym:
                    continue
                rows.append({
                    "Symbol": sym,
                    "Date": today,
                    "Time": "",
                    "EPS Est": item.get("estimate"),
                    "Revenue Est": "",
                    "Source": "Alpha Vantage fallback",
                })
                if len(rows) >= 30:
                    break
    except Exception:
        pass
    return rows


@st.cache_data(ttl=900)
def v424_earnings_today():
    """
    V42.4.2 override:
    Earnings source priority:
      1) FMP earning_calendar
      2) Nasdaq public earnings calendar
      3) Alpha Vantage optional fallback
    """
    rows = []
    today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()

    # 1) FMP
    try:
        data = v424_fmp_get("earning_calendar", {"from": today.isoformat(), "to": today.isoformat()}) if "v424_fmp_get" in globals() else None
        if isinstance(data, list):
            for item in data:
                sym = safe_text(item.get("symbol") or "").upper()
                if not sym:
                    continue
                rows.append({
                    "Symbol": sym,
                    "Date": safe_text(item.get("date") or today.isoformat()),
                    "Time": safe_text(item.get("time") or ""),
                    "EPS Est": item.get("epsEstimated"),
                    "Revenue Est": item.get("revenueEstimated"),
                    "Source": "FMP",
                })
                if len(rows) >= 30:
                    break
    except Exception:
        pass

    if rows:
        return rows

    # 2) Nasdaq no-key fallback
    rows = v4242_nasdaq_earnings_today()
    if rows:
        return rows

    # 3) Alpha Vantage optional
    rows = v4242_alpha_vantage_earnings_today()
    if rows:
        return rows

    return []


@st.cache_data(ttl=1800)
def v4242_tradingeconomics_calendar():
    """
    No-key TradingEconomics guest fallback.
    Guest access can be rate-limited, but often returns broad macro calendar.
    """
    events = []
    try:
        today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()
        end = today + dt.timedelta(days=45)
        url = "https://api.tradingeconomics.com/calendar"
        r = requests.get(
            url,
            params={"c": "guest:guest", "f": "json", "d1": today.isoformat(), "d2": end.isoformat()},
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json() or []
            important = ["CPI", "PPI", "Payroll", "Non Farm", "Nonfarm", "FOMC", "Fed", "Jobless", "GDP", "Retail Sales", "Inflation", "Unemployment", "ISM", "PMI"]
            for item in data:
                name = safe_text(item.get("Event") or item.get("event") or item.get("Category") or "")
                country = safe_text(item.get("Country") or item.get("country") or "")
                if country and country.lower() not in {"united states", "united states of america", "us", "usa"}:
                    continue
                if not any(term.lower() in name.lower() for term in important):
                    continue
                date_val = safe_text(item.get("Date") or item.get("date") or "")
                events.append({
                    "date": date_val,
                    "event": name,
                    "actual": item.get("Actual"),
                    "estimate": item.get("Forecast"),
                    "previous": item.get("Previous"),
                    "source": "TradingEconomics guest fallback",
                })
                if len(events) >= 12:
                    break
    except Exception:
        pass
    return events


@st.cache_data(ttl=1800)
def v424_economic_calendar():
    """
    V42.4.2 override:
    Economic calendar source priority:
      1) FMP economic_calendar
      2) TradingEconomics guest fallback
      3) Static upcoming macro checklist fallback
    """
    important = ["CPI", "PPI", "Payroll", "Nonfarm", "FOMC", "Fed", "Jobless", "GDP", "Retail Sales", "Inflation", "Unemployment", "ISM", "PMI"]
    today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()
    end = today + dt.timedelta(days=45)
    events = []

    # 1) FMP
    try:
        data = v424_fmp_get("economic_calendar", {"from": today.isoformat(), "to": end.isoformat()}) if "v424_fmp_get" in globals() else None
        if isinstance(data, list):
            for item in data:
                name = safe_text(item.get("event") or item.get("name") or "")
                if not name:
                    continue
                if any(term.lower() in name.lower() for term in important):
                    events.append({
                        "date": safe_text(item.get("date") or item.get("datetime") or ""),
                        "event": name,
                        "actual": item.get("actual"),
                        "estimate": item.get("estimate"),
                        "previous": item.get("previous"),
                        "source": "FMP",
                    })
    except Exception:
        pass

    # 2) Trading Economics fallback
    if not events:
        events = v4242_tradingeconomics_calendar()

    # 3) Static fallback so card is not blank.
    if not events:
        events = [
            {"date": "Check official calendar", "event": "CPI / Inflation report", "source": "Static fallback"},
            {"date": "Check official calendar", "event": "PPI report", "source": "Static fallback"},
            {"date": "Check official calendar", "event": "FOMC / Fed decision or minutes", "source": "Static fallback"},
            {"date": "Check official calendar", "event": "Nonfarm Payrolls / Jobs report", "source": "Static fallback"},
            {"date": "Check official calendar", "event": "Jobless Claims", "source": "Static fallback"},
        ]

    events = sorted(events, key=lambda x: safe_text(x.get("date")))
    today_str = today.isoformat()
    todays = [e for e in events if safe_text(e.get("date")).startswith(today_str)]
    return {
        "today": todays[:8],
        "next": events[:12],
        "source": safe_text(events[0].get("source"), "Fallback") if events else "No source",
    }


@st.cache_data(ttl=900)
def v424_market_news():
    """
    V42.4.2 override:
    Market news source priority:
      1) NewsAPI
      2) Finnhub general news
      3) No-data message
    """
    headlines = []

    # 1) NewsAPI
    try:
        key = (globals().get("NEWSAPI_KEY") or globals().get("NEWS_API_KEY") or os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY") or "").strip()
        if key:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": '(stock market OR S&P 500 OR Nasdaq OR Federal Reserve OR CPI OR inflation OR earnings)',
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 5,
                    "apiKey": key,
                },
                timeout=10,
            )
            if r.status_code == 200:
                for a in (r.json().get("articles") or [])[:5]:
                    title = safe_text(a.get("title") or "")
                    source = safe_text((a.get("source") or {}).get("name") or "")
                    if title:
                        headlines.append(f"{title}" + (f" — {source}" if source else ""))
    except Exception:
        pass

    if headlines:
        return headlines

    # 2) Finnhub
    try:
        token = (globals().get("FINNHUB_API_KEY") or os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_TOKEN") or "").strip()
        if token:
            r = requests.get("https://finnhub.io/api/v1/news", params={"category": "general", "token": token}, timeout=10)
            if r.status_code == 200:
                for a in (r.json() or [])[:5]:
                    headline = safe_text(a.get("headline") or "")
                    source = safe_text(a.get("source") or "")
                    if headline:
                        headlines.append(f"{headline}" + (f" — {source}" if source else ""))
    except Exception:
        pass

    return headlines


def render_v424_market_command_center():
    """
    V42.4.2 override: one Command Center with source fallbacks and visible source diagnostics.
    """
    st.markdown("## 🧭 Market Command Center")

    quotes = v424_market_quotes()
    if quotes:
        cols = st.columns(min(5, len(quotes)))
        for i, q in enumerate(quotes[:5]):
            pct = v424_float(q.get("change_pct"), None) if "v424_float" in globals() else safe_number(q.get("change_pct"), None)
            delta = f"{pct:+.2f}%" if pct is not None else None
            label = q.get("display_label") or q.get("symbol", "")
            source = safe_text(q.get("source"), "")
            cols[i].metric(label, v424_money(q.get("price")) if "v424_money" in globals() else fmt_money(q.get("price")), delta)
            if source:
                cols[i].caption(source)
    else:
        st.info(
            "Market quote data did not return from FMP or Yahoo fallback. "
            f"FMP_API_KEY configured={'Yes' if bool(FMP_API_KEY) else 'No'}."
        )

    econ = v424_economic_calendar()
    earnings = v424_earnings_today()
    news = v424_market_news()

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            st.caption(f"Source: {safe_text(econ.get('source'), 'Unknown')}")
            today_events = econ.get("today") or []
            next_events = econ.get("next") or []
            if today_events:
                st.markdown("**Today:**")
                for e in today_events[:6]:
                    st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
            elif next_events:
                st.caption("No major event found for today. Showing next market-moving reports.")
                for e in next_events[:8]:
                    st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
            else:
                st.caption("No economic calendar source returned data.")

    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            if earnings:
                edf = pd.DataFrame(earnings)
                st.caption("Source priority: FMP → Nasdaq public fallback → Alpha Vantage optional fallback")
                st.dataframe(edf, use_container_width=True, hide_index=True)
            else:
                st.caption(
                    "No earnings returned from FMP, Nasdaq fallback, or Alpha Vantage. "
                    f"FMP_API_KEY configured={'Yes' if bool(FMP_API_KEY) else 'No'}; "
                    f"ALPHA_VANTAGE_API_KEY configured={'Yes' if bool((globals().get('ALPHA_VANTAGE_API_KEY') or '').strip()) else 'No'}."
                )

    with st.container(border=True):
        st.markdown("### 📰 Market News")
        if news:
            st.caption("Source priority: NewsAPI → Finnhub general news")
            for h in news[:5]:
                st.markdown(f"• {safe_text(h)}")
        else:
            st.caption(
                "No broad market headlines returned. "
                f"NEWSAPI_KEY configured={'Yes' if bool((globals().get('NEWSAPI_KEY') or globals().get('NEWS_API_KEY') or os.getenv('NEWSAPI_KEY') or os.getenv('NEWS_API_KEY') or '').strip()) else 'No'}; "
                f"FINNHUB_API_KEY configured={'Yes' if bool((globals().get('FINNHUB_API_KEY') or os.getenv('FINNHUB_API_KEY') or os.getenv('FINNHUB_TOKEN') or '').strip()) else 'No'}."
            )



# =========================
# V42.4.3 COMMAND CENTER LABELS + EARNINGS NAMES
# =========================

INDEX_DISPLAY_LABELS = {
    "SPY": "S&P 500 ETF",
    "QQQ": "Nasdaq 100 ETF",
    "DIA": "Dow Jones ETF",
    "IWM": "Russell 2000 ETF",
    "VIX": "VIX Fear Gauge",
}


@st.cache_data(ttl=300)
def v424_market_quotes():
    """
    V42.4.3 override:
    Show recognizable market labels instead of only ETF tickers.
    Uses FMP first, Yahoo/yfinance fallback.
    """
    symbols = ["SPY", "QQQ", "DIA", "IWM", "VIX"]
    rows = []
    for s in symbols:
        q = v424_quote(s)
        if q:
            q["display_label"] = INDEX_DISPLAY_LABELS.get(s, s)
            rows.append(q)
    return rows


@st.cache_data(ttl=900)
def v4242_nasdaq_earnings_today():
    """
    V42.4.3: Nasdaq public fallback with company names when returned.
    """
    rows = []
    try:
        today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()
        url = "https://api.nasdaq.com/api/calendar/earnings"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/market-activity/earnings",
        }
        r = requests.get(url, params={"date": today.isoformat()}, headers=headers, timeout=12)
        if r.status_code == 200:
            data = r.json() or {}
            table = (((data.get("data") or {}).get("rows")) or [])
            for item in table:
                sym = safe_text(item.get("symbol") or "").upper()
                if not sym:
                    continue
                company = (
                    item.get("name") or item.get("companyName") or item.get("company") or
                    item.get("securityName") or ""
                )
                rows.append({
                    "Company": safe_text(company, ""),
                    "Ticker": sym,
                    "Date": today.isoformat(),
                    "Time": safe_text(item.get("time") or item.get("timeOfDay") or ""),
                    "EPS Est": item.get("epsForecast") or item.get("eps_estimate"),
                    "Revenue Est": item.get("revenueForecast") or item.get("revenue_estimate"),
                    "Source": "Nasdaq public fallback",
                })
                if len(rows) >= 30:
                    break
    except Exception:
        pass
    return rows


@st.cache_data(ttl=1800)
def v4242_alpha_vantage_earnings_today():
    """
    V42.4.3: Alpha Vantage fallback with company/name field when available.
    """
    rows = []
    try:
        key = (globals().get("ALPHA_VANTAGE_API_KEY") or os.getenv("ALPHA_VANTAGE_API_KEY") or "").strip()
        if not key:
            return rows
        url = "https://www.alphavantage.co/query"
        r = requests.get(url, params={"function": "EARNINGS_CALENDAR", "horizon": "3month", "apikey": key}, timeout=15)
        if r.status_code == 200 and r.text:
            today = (v424_today() if "v424_today" in globals() else dt.datetime.now().date()).isoformat()
            reader = csv.DictReader(StringIO(r.text))
            for item in reader:
                if safe_text(item.get("reportDate")) != today:
                    continue
                sym = safe_text(item.get("symbol")).upper()
                if not sym:
                    continue
                rows.append({
                    "Company": safe_text(item.get("name") or item.get("companyName") or "", ""),
                    "Ticker": sym,
                    "Date": today,
                    "Time": "",
                    "EPS Est": item.get("estimate"),
                    "Revenue Est": "",
                    "Source": "Alpha Vantage fallback",
                })
                if len(rows) >= 30:
                    break
    except Exception:
        pass
    return rows


@st.cache_data(ttl=900)
def v424_earnings_today():
    """
    V42.4.3 override:
    Earnings source priority:
      1) FMP earning_calendar with company name lookup where possible
      2) Nasdaq public earnings calendar
      3) Alpha Vantage optional fallback
    """
    rows = []
    today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()

    # 1) FMP
    try:
        data = v424_fmp_get("earning_calendar", {"from": today.isoformat(), "to": today.isoformat()}) if "v424_fmp_get" in globals() else None
        if isinstance(data, list):
            for item in data:
                sym = safe_text(item.get("symbol") or "").upper()
                if not sym:
                    continue
                company = safe_text(item.get("name") or item.get("companyName") or item.get("company") or "", "")
                if not company:
                    try:
                        q = v424_quote(sym)
                        company = safe_text(q.get("name") or "", "")
                    except Exception:
                        company = ""
                rows.append({
                    "Company": company,
                    "Ticker": sym,
                    "Date": safe_text(item.get("date") or today.isoformat()),
                    "Time": safe_text(item.get("time") or ""),
                    "EPS Est": item.get("epsEstimated"),
                    "Revenue Est": item.get("revenueEstimated"),
                    "Source": "FMP",
                })
                if len(rows) >= 30:
                    break
    except Exception:
        pass

    if rows:
        return rows

    rows = v4242_nasdaq_earnings_today()
    if rows:
        return rows

    rows = v4242_alpha_vantage_earnings_today()
    if rows:
        return rows

    return []


def v4243_technical_translation(row):
    """
    Investor-friendly interpretation for technical agent signals.
    """
    rsi = safe_number(row.get("RSI"), None)
    vol = safe_number(row.get("Volume Ratio"), None)
    atr = safe_number(row.get("ATR %"), None)
    support = safe_number(row.get("Support 1"), 0)
    resistance = safe_number(row.get("Resistance 1"), 0)

    positives = []
    watchouts = []
    action = []

    if rsi is not None and rsi > 0:
        if rsi >= 70:
            watchouts.append(f"RSI is {rsi:.1f}, which is overbought. Avoid chasing a gap-up move.")
            action.append("Prefer a pullback or a confirmed breakout with volume.")
        elif 50 <= rsi < 70:
            positives.append(f"RSI is {rsi:.1f}, which shows healthy momentum without extreme overheating.")
        elif rsi < 40:
            watchouts.append(f"RSI is {rsi:.1f}, which suggests weak momentum or an oversold setup.")

    if vol is not None and vol > 0:
        if vol < 0.75:
            watchouts.append(f"Volume ratio is {vol:.2f}x, meaning the move is not strongly confirmed by trading volume.")
        elif vol >= 1.25:
            positives.append(f"Volume ratio is {vol:.2f}x, showing stronger-than-normal participation.")

    if atr is not None and atr > 0:
        if atr >= 8:
            watchouts.append(f"ATR volatility is high at {atr:.2f}%; position size should be smaller.")
        elif atr >= 5:
            watchouts.append(f"ATR volatility is elevated at {atr:.2f}%; expect wider swings and avoid oversized positions.")
        else:
            positives.append(f"ATR volatility is manageable at {atr:.2f}%.")

    if support:
        action.append(f"Preferred pullback area is near support around {fmt_money(support)}.")
    if resistance:
        action.append(f"Breakout confirmation is stronger above resistance around {fmt_money(resistance)}.")

    if not positives:
        positives.append("Trend signals are being evaluated from price, moving averages, RSI, volume, and volatility.")
    if not watchouts:
        watchouts.append("No major technical warning from available fields.")
    if not action:
        action.append("Use pullback or breakout confirmation rather than chasing.")

    return positives, watchouts, action


def render_v4243_technical_translation_box(row):
    positives, watchouts, action = v4243_technical_translation(row)
    with st.container(border=True):
        st.markdown("### 📈 Technical Agent — Investor Translation")
        st.markdown("**Bullish / constructive signals:**")
        for p in positives[:5]:
            st.markdown(f"✓ {safe_text(p)}")
        st.markdown("**Watchouts:**")
        for w in watchouts[:5]:
            st.markdown(f"⚠️ {safe_text(w)}")
        st.info(" ".join([safe_text(a) for a in action[:3]]))




# =========================
# V42.4.4 PLAIN ENGLISH AGENTS + SMART LEVELS
# =========================

def v4244_is_valid_level(x):
    x = safe_number(x, 0)
    return x is not None and x > 0.01


@st.cache_data(ttl=900)
def v4244_chart_levels_from_history(ticker):
    """
    Fallback support/resistance from Yahoo price history when scanner values are missing.
    """
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return {}
    try:
        hist = yf.download(ticker, period="6mo", interval="1d", auto_adjust=True, progress=False, threads=False)
        if hist is None or hist.empty:
            return {}
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = [c[0] if isinstance(c, tuple) else c for c in hist.columns]
        if "Close" not in hist.columns:
            return {}
        high = hist["High"].dropna() if "High" in hist.columns else hist["Close"].dropna()
        low = hist["Low"].dropna() if "Low" in hist.columns else hist["Close"].dropna()
        close = hist["Close"].dropna()
        if close.empty or high.empty or low.empty:
            return {}
        support1 = float(low.tail(min(20, len(low))).min())
        support2 = float(low.tail(min(60, len(low))).min())
        resistance1 = float(high.tail(min(20, len(high))).max())
        resistance2 = float(high.tail(min(60, len(high))).max())
        return {
            "support1": support1,
            "support2": support2,
            "resistance1": resistance1,
            "resistance2": resistance2,
            "breakout": resistance1,
            "source": "Yahoo 20/60-day price history fallback",
        }
    except Exception:
        return {}


def v4244_get_smart_levels(row):
    price = safe_number(row.get("Price"), 0)
    levels = {
        "price": price,
        "support1": safe_number(row.get("Support 1"), 0),
        "support2": safe_number(row.get("Support 2"), 0),
        "resistance1": safe_number(row.get("Resistance 1"), 0),
        "resistance2": safe_number(row.get("Resistance 2"), 0),
        "breakout": safe_number(row.get("Breakout Level"), 0),
        "source": "Scanner support/resistance",
    }
    if any(v4244_is_valid_level(levels[k]) for k in ["support1", "support2", "resistance1", "resistance2", "breakout"]):
        return levels

    fallback = v4244_chart_levels_from_history(row.get("Ticker"))
    if fallback:
        levels.update(fallback)
    return levels


def render_v423_professional_trading_levels(row):
    """
    V42.4.4 override:
    Hide $0.00 levels and calculate fallback support/resistance from recent chart history.
    """
    levels = v4244_get_smart_levels(row)
    price = levels.get("price")
    s1 = levels.get("support1")
    s2 = levels.get("support2")
    r1 = levels.get("resistance1")
    r2 = levels.get("resistance2")
    breakout = levels.get("breakout")
    guidance = safe_text(row.get("Chart Guidance"), "")
    has_levels = any(v4244_is_valid_level(x) for x in [s1, s2, r1, r2, breakout])

    with st.container(border=True):
        st.markdown("### 📈 Professional Trading Levels")
        if not has_levels:
            st.warning("Trading levels are unavailable for this ticker. Run live research or latest scan to calculate support/resistance.")
            return

        c1, c2, c3 = st.columns(3)
        c1.metric("Current", fmt_money(price))
        c2.metric("Support 1", fmt_money(s1) if v4244_is_valid_level(s1) else "N/A")
        c3.metric("Resistance 1", fmt_money(r1) if v4244_is_valid_level(r1) else "N/A")
        c4, c5, c6 = st.columns(3)
        c4.metric("Support 2", fmt_money(s2) if v4244_is_valid_level(s2) else "N/A")
        c5.metric("Resistance 2", fmt_money(r2) if v4244_is_valid_level(r2) else "N/A")
        c6.metric("Breakout", fmt_money(breakout) if v4244_is_valid_level(breakout) else "N/A")
        st.caption(f"Level source: {safe_text(levels.get('source'), 'N/A')}")

        if price and s1 and r1 and s1 > 0 and r1 > 0:
            downside = ((price - s1) / price) * 100
            upside = ((r1 - price) / price) * 100
            st.info(
                f"Plain English: nearest support is about {downside:.1f}% below current price and nearest resistance is about {upside:.1f}% above. "
                "A better entry is usually near support, or after a breakout above resistance with stronger volume."
            )
        elif guidance:
            st.info(guidance)


def render_v424_support_resistance_box(row):
    """
    V42.4.4 override: same smart levels for the Support / Resistance Agent.
    """
    levels = v4244_get_smart_levels(row)
    price = levels.get("price")
    s1 = levels.get("support1")
    s2 = levels.get("support2")
    r1 = levels.get("resistance1")
    r2 = levels.get("resistance2")
    breakout = levels.get("breakout")
    has_levels = any(v4244_is_valid_level(x) for x in [s1, s2, r1, r2, breakout])

    with st.container(border=True):
        st.markdown("### 📍 Support / Resistance Agent")
        if not has_levels:
            st.warning("Support/resistance was not calculated yet. This is not bearish — it just means the agent needs live chart history or a fresh scan.")
            return

        c1, c2, c3 = st.columns(3)
        c1.metric("Current", fmt_money(price))
        c2.metric("Support 1", fmt_money(s1) if v4244_is_valid_level(s1) else "N/A")
        c3.metric("Resistance 1", fmt_money(r1) if v4244_is_valid_level(r1) else "N/A")
        c4, c5, c6 = st.columns(3)
        c4.metric("Support 2", fmt_money(s2) if v4244_is_valid_level(s2) else "N/A")
        c5.metric("Resistance 2", fmt_money(r2) if v4244_is_valid_level(r2) else "N/A")
        c6.metric("Breakout", fmt_money(breakout) if v4244_is_valid_level(breakout) else "N/A")

        st.caption(f"Source: {safe_text(levels.get('source'), 'N/A')}")
        if price and s1 and r1 and s1 > 0 and r1 > 0:
            risk = max(price - s1, 0)
            reward = max(r1 - price, 0)
            rr = reward / risk if risk > 0 else 0
            st.info(
                f"Plain English: support is the area buyers may defend; resistance is where sellers may appear. "
                f"The short-term reward/risk to first resistance is about {rr:.2f}:1."
            )


def v4244_agent_plain_english(agent_name, agent, row):
    name = safe_text(agent_name, "").lower()
    score = safe_number(agent.get("score") if isinstance(agent, dict) else None, None)

    if "technical" in name:
        rsi = safe_number(row.get("RSI"), None)
        vol = safe_number(row.get("Volume Ratio"), None)
        atr = safe_number(row.get("ATR %"), None)
        explanation = []
        action = []
        if rsi is not None and rsi > 0:
            if rsi >= 70:
                explanation.append(f"RSI is {rsi:.1f}, which means the stock may be hot/extended short term.")
                action.append("Avoid chasing; wait for a pullback or a clean breakout with volume.")
            elif rsi >= 50:
                explanation.append(f"RSI is {rsi:.1f}, showing healthy momentum.")
            else:
                explanation.append(f"RSI is {rsi:.1f}, showing weaker or recovering momentum.")
        if vol is not None and vol > 0:
            if vol < 0.75:
                explanation.append(f"Volume is light at {vol:.2f}x average, so the move has weaker confirmation.")
            elif vol >= 1.25:
                explanation.append(f"Volume is strong at {vol:.2f}x average, which confirms participation.")
        if atr is not None and atr > 0:
            if atr >= 5:
                explanation.append(f"ATR is {atr:.2f}%, meaning daily swings are elevated; use smaller position sizing.")
        if not action:
            action.append("Best setup is a pullback near support or breakout above resistance with volume.")
        return explanation, action

    if "finance" in name:
        return [
            "This checks whether the business growth is backed by profits, margins, cash flow, and a healthy balance sheet.",
            "Strong revenue is good, but it is better when earnings and cash flow also improve."
        ], [
            "Prefer stocks where revenue growth, earnings growth, margins, and cash flow point in the same direction."
        ]

    if "analyst" in name:
        return [
            "This checks whether Wall Street target prices and ratings support the AI thesis.",
            "If AI fair value is much higher than analyst consensus, the idea may still work but has higher uncertainty."
        ], [
            "Use analyst support as confirmation, not as the only reason to buy."
        ]

    if "news" in name:
        return [
            "This checks whether recent headlines are creating positive catalysts, negative risk, or no clear signal.",
            "No news is not automatically bad — it means the stock may be moving on technicals, earnings, or sector trends."
        ], [
            "Prefer stocks where news flow supports the technical and financial setup."
        ]

    if "insider" in name:
        return [
            "This checks whether executives/directors are buying or selling shares.",
            "Form 4 count alone is not enough; actual buy/sell classification matters."
        ], [
            "Treat insider activity as supporting evidence only until transaction-level buy/sell details are shown."
        ]

    if "institutional" in name:
        return [
            "This checks whether large funds appear to be accumulating or reducing exposure.",
            "13F data can be delayed, so it is useful for confirmation, not real-time timing."
        ], [
            "Best signal is multiple large institutions adding over more than one quarter."
        ]

    if "competitor" in name:
        return [
            "This compares the company against peers on growth, valuation, margins, and risk.",
            "A stock can look good alone but less attractive if peers are cheaper or growing faster."
        ], [
            "Use peer comparison to decide whether this is the best stock in its group."
        ]

    if "recovery" in name:
        return [
            "This checks whether the stock is temporarily beaten down or suffering from a broken business trend.",
            "A lower price is only attractive when fundamentals remain intact."
        ], [
            "Prefer recovery names with improving fundamentals, analyst support, and clear catalysts."
        ]

    return [], []


def render_v4244_agent_plain_english_box(agent_name, agent, row):
    explanation, action = v4244_agent_plain_english(agent_name, agent, row)
    if not explanation and not action:
        return
    with st.container(border=True):
        st.markdown("**Plain-English Agent Explanation**")
        for e in explanation[:5]:
            st.markdown(f"• {safe_text(e)}")
        if action:
            st.info(" ".join([safe_text(a) for a in action[:3]]))





# =========================
# V42.5 STANDARDIZED INVESTOR AGENT EXPLANATIONS
# =========================

def v425_score_label(score):
    score = safe_number(score, None)
    if score is None:
        return "Not scored"
    if score >= 85:
        return f"{int(score)}/100 · Strong"
    if score >= 70:
        return f"{int(score)}/100 · Constructive"
    if score >= 50:
        return f"{int(score)}/100 · Mixed"
    return f"{int(score)}/100 · Weak"


def v425_extract_agent_findings(agent):
    if not isinstance(agent, dict):
        return []
    findings = agent.get("findings") or []
    if isinstance(findings, str):
        findings = compact_reason_list(findings, max_items=8)
    if not isinstance(findings, list):
        findings = []
    cleaned = []
    for x in findings:
        txt = safe_text(x, "").strip()
        if txt:
            cleaned.append(txt)
    return cleaned[:8]


def v425_agent_template(agent_name, agent, row):
    name = safe_text(agent_name, "Agent")
    lname = name.lower()
    score = agent.get("score") if isinstance(agent, dict) else None
    findings = v425_extract_agent_findings(agent)

    what_found = findings[:5] if findings else []
    what_means = []
    why_matters = []
    how_use = []

    price = safe_number(row.get("Price"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    rsi = safe_number(row.get("RSI"), 0)
    vol = safe_number(row.get("Volume Ratio"), 0)
    atr = safe_number(row.get("ATR %"), 0)
    analyst_target = safe_number(row.get("Analyst Target"), 0)
    analyst_count = safe_number(row.get("Analyst Count"), 0)
    ai_value = safe_number(row.get("AI Fair Value"), 0)

    if "technical" in lname:
        if not what_found:
            if rsi:
                what_found.append(f"RSI: {rsi:.1f}")
            if vol:
                what_found.append(f"Volume ratio: {vol:.2f}x average")
            if atr:
                what_found.append(f"ATR volatility: {atr:.2f}%")
        if rsi >= 70:
            what_means.append("Momentum is strong but may be stretched in the short term.")
        elif rsi >= 50:
            what_means.append("Momentum is positive and generally healthy.")
        elif rsi > 0:
            what_means.append("Momentum is weaker or still recovering.")
        if vol and vol < 0.75:
            what_means.append("The move is not strongly confirmed by volume yet.")
        elif vol >= 1.25:
            what_means.append("Volume confirms stronger buyer/seller participation.")
        if atr >= 5:
            what_means.append("Volatility is elevated, so daily swings may be larger than normal.")
        why_matters.append("A good stock can still be a poor entry if it is overbought, near resistance, or moving on weak volume.")
        how_use.append("Prefer buying near support or after a confirmed breakout with stronger volume. Use smaller size when ATR is elevated.")

    elif "finance" in lname:
        what_means.append("This checks whether the company is converting growth into profits, margins, cash flow, and balance-sheet strength.")
        why_matters.append("Revenue growth alone is not enough. Higher-quality companies also show earnings and cash-flow conversion.")
        how_use.append("Give more weight to ideas where revenue, EPS, margins, and free cash flow are all improving.")

    elif "analyst" in lname:
        if analyst_target:
            what_found.append(f"Analyst target: {fmt_money(analyst_target)}")
        if analyst_count:
            what_found.append(f"Analyst count: {int(analyst_count)}")
        if price and analyst_target:
            a_up = ((analyst_target - price) / price) * 100
            what_found.append(f"Analyst upside: {a_up:.1f}%")
        what_means.append("This checks whether Wall Street targets and recommendations support or challenge the AI thesis.")
        if ai_value and analyst_target and analyst_target > 0:
            gap = ((ai_value - analyst_target) / analyst_target) * 100
            if gap > 50:
                what_means.append("AI fair value is much higher than analyst consensus, which means the modeled upside is higher uncertainty.")
            elif abs(gap) <= 20:
                what_means.append("AI fair value is reasonably aligned with analyst consensus.")
        why_matters.append("Analyst support can validate a thesis, but analysts can lag fast-moving news and market reactions.")
        how_use.append("Use analyst support as confirmation, not as the only reason to buy.")

    elif "news" in lname:
        what_means.append("This checks whether recent headlines are creating positive catalysts, negative risks, or no clear signal.")
        why_matters.append("News can change analyst revisions, sentiment, and short-term demand quickly.")
        how_use.append("Positive news is strongest when it aligns with strong technicals and financial execution. If no news is found, do not treat that as bullish or bearish.")

    elif "insider" in lname:
        what_means.append("This checks whether executives or directors are filing transactions in the stock.")
        why_matters.append("Open-market insider buying can be bullish, while selling can be routine or cautionary depending on the pattern.")
        how_use.append("Treat Form 4 count as neutral until the agent classifies actual buys, sells, option exercises, and net dollars.")

    elif "institutional" in lname:
        what_means.append("This checks whether large funds appear to be involved in the stock.")
        why_matters.append("Institutional demand can support longer-term moves, but 13F data is delayed.")
        how_use.append("Use institutional ownership as confirmation only. Stronger signal comes from multiple funds adding over multiple quarters.")

    elif "competitor" in lname or "peer" in lname:
        what_means.append("This compares the company against peers on growth, valuation, margins, and risk.")
        why_matters.append("A stock can look attractive alone but less attractive if peers are cheaper, growing faster, or more profitable.")
        how_use.append("Use peer comparison to decide whether this is the best stock in its group, not just a good stock by itself.")

    elif "recovery" in lname:
        what_means.append("This checks whether the stock is temporarily beaten down or suffering from a broken business trend.")
        why_matters.append("A lower price is only attractive if fundamentals remain intact and catalysts can support recovery.")
        how_use.append("Prefer recovery setups with improving fundamentals, analyst support, positive catalysts, and clear support levels.")

    elif "political" in lname or "congress" in lname:
        what_means.append("This checks whether congressional trading activity may add a sentiment signal.")
        why_matters.append("Political trading data can be interesting but is delayed and should not be treated as a primary buy signal.")
        how_use.append("Use it as a minor supporting signal only after technical, financial, and valuation checks pass.")

    else:
        what_means.append("This agent contributes one piece of the overall AI thesis.")
        why_matters.append("No single agent should drive the decision alone; the best setups have multiple agents aligned.")
        how_use.append("Use this together with valuation, technicals, news, and risk management.")

    risks = []
    if isinstance(agent, dict):
        raw_risks = agent.get("risks") or []
        if isinstance(raw_risks, str):
            raw_risks = compact_reason_list(raw_risks, max_items=5)
        if isinstance(raw_risks, list):
            risks = [safe_text(r) for r in raw_risks if safe_text(r)][:5]

    if not what_found:
        what_found = ["No detailed metric returned yet for this agent. Run live research or latest scan for deeper data."]
    if not risks:
        risks = ["No major agent-specific red flag returned from available data."]

    return {
        "name": name,
        "score_label": v425_score_label(score),
        "what_found": what_found[:6],
        "what_means": what_means[:5],
        "why_matters": why_matters[:4],
        "how_use": how_use[:4],
        "risks": risks[:5],
    }


def render_v425_agent_standard_box(agent_name, agent, row):
    t = v425_agent_template(agent_name, agent, row)
    with st.container(border=True):
        st.markdown(f"#### {t['name']} — Investor Explanation")
        st.caption(f"Score interpretation: {t['score_label']}")

        st.markdown("**What We Found**")
        for x in t["what_found"]:
            st.markdown(f"• {safe_text(x)}")

        st.markdown("**What This Means**")
        for x in t["what_means"]:
            st.markdown(f"• {safe_text(x)}")

        st.markdown("**Why It Matters**")
        for x in t["why_matters"]:
            st.markdown(f"• {safe_text(x)}")

        st.markdown("**How To Use This**")
        for x in t["how_use"]:
            st.markdown(f"• {safe_text(x)}")

        if t["risks"]:
            st.markdown("**Risks / Limits**")
            for x in t["risks"]:
                st.markdown(f"⚠️ {safe_text(x)}")


def v425_build_final_thesis(row):
    ticker = safe_text(row.get("Ticker"), "This stock")
    score = safe_number(row.get("Final Conviction"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    analyst = safe_text(row.get("Analyst Support"), "")
    news = safe_text(row.get("News Sentiment"), "")
    rsi = safe_number(row.get("RSI"), 0)
    atr = safe_number(row.get("ATR %"), 0)
    entry = safe_text(row.get("Entry Range"), "")
    support = safe_number(row.get("Support 1"), 0)
    resistance = safe_number(row.get("Resistance 1"), 0)

    positives = []
    risks = []
    strategy = []

    if score >= 90:
        positives.append(f"High AI conviction at {score:.0f}/100.")
    elif score >= 75:
        positives.append(f"Constructive AI conviction at {score:.0f}/100.")
    if upside >= 25:
        positives.append(f"Strong modeled upside of {upside:.1f}%.")
    elif upside >= 10:
        positives.append(f"Moderate modeled upside of {upside:.1f}%.")
    if "Bullish" in analyst or "Constructive" in analyst:
        positives.append(f"Analyst support is {analyst}.")
    if "Positive" in news:
        positives.append("Recent news flow appears supportive.")
    if rsi and rsi >= 70:
        risks.append("RSI is overbought, so entry timing matters.")
    if atr and atr >= 5:
        risks.append("Volatility is elevated, so position size should be controlled.")
    if upside < 10:
        risks.append("Modeled upside is limited unless new catalysts appear.")

    if entry and entry != "N/A":
        strategy.append(f"Preferred entry zone: {entry}.")
    elif support:
        strategy.append(f"Preferred entry is closer to support around {fmt_money(support)}.")
    else:
        strategy.append("Preferred entry is a controlled pullback or confirmed breakout, not a chase.")
    if resistance:
        strategy.append(f"Watch resistance near {fmt_money(resistance)} for breakout confirmation.")
    strategy.append("Use stop loss and position sizing because AI conviction does not eliminate market risk.")

    if not positives:
        positives.append("Some supportive signals are present, but the thesis needs stronger confirmation.")
    if not risks:
        risks.append("No major red flag returned, but normal market, earnings, and execution risks still apply.")

    return {
        "ticker": ticker,
        "confidence": score,
        "positives": positives[:6],
        "risks": risks[:5],
        "strategy": strategy[:5],
    }


def render_v425_final_ai_thesis(row):
    t = v425_build_final_thesis(row)
    with st.container(border=True):
        st.markdown("### 🎯 Final AI Investment Thesis")
        st.caption("This section translates all agents into a simple action-oriented summary.")

        c1, c2 = st.columns(2)
        c1.metric("AI Confidence", f"{t['confidence']:.0f}/100" if t["confidence"] else "N/A")
        c2.metric("Ticker", t["ticker"])

        st.markdown("**Why This Stock Is Attractive**")
        for x in t["positives"]:
            st.markdown(f"✓ {safe_text(x)}")

        st.markdown("**Biggest Risks**")
        for x in t["risks"]:
            st.markdown(f"⚠️ {safe_text(x)}")

        st.markdown("**Preferred Strategy**")
        for x in t["strategy"]:
            st.markdown(f"• {safe_text(x)}")





# =========================
# V42.5.1 AGENT EXPLANATION WIRING FIX
# =========================

def v42_safe_float(value, default=0.0):
    """
    Compatibility helper for older V42 scanner/app functions.
    Prevents fallback errors like: name 'v42_safe_float' is not defined.
    """
    try:
        if value in (None, "", "N/A", "Unknown"):
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return default


def v4251_agent_display_name(name):
    text = safe_text(name, "Agent")
    if not text.lower().endswith("agent"):
        return f"{text} Agent"
    return text


def v4251_build_agent_explanation(agent_name, agent, row):
    """
    Forces every visible committee card into the same investor-friendly format.
    """
    name = safe_text(agent_name, "Agent")
    lname = name.lower()
    score = None
    status = "N/A"
    impact = "Neutral"
    data_used = ""

    if isinstance(agent, dict):
        score = agent.get("score")
        status = safe_text(agent.get("status"), "N/A")
        impact = safe_text(agent.get("impact"), "Neutral")
        data_used = safe_text(agent.get("data_used"), "")

    findings = []
    if isinstance(agent, dict):
        raw_findings = agent.get("findings") or []
        if isinstance(raw_findings, str):
            raw_findings = compact_reason_list(raw_findings, max_items=8)
        if isinstance(raw_findings, list):
            findings = [safe_text(x) for x in raw_findings if safe_text(x)]

    risks = []
    if isinstance(agent, dict):
        raw_risks = agent.get("risks") or []
        if isinstance(raw_risks, str):
            raw_risks = compact_reason_list(raw_risks, max_items=8)
        if isinstance(raw_risks, list):
            risks = [safe_text(x) for x in raw_risks if safe_text(x)]

    price = safe_number(row.get("Price"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    rsi = safe_number(row.get("RSI"), 0)
    vol = safe_number(row.get("Volume Ratio"), 0)
    atr = safe_number(row.get("ATR %"), 0)
    support = safe_number(row.get("Support 1"), 0)
    resistance = safe_number(row.get("Resistance 1"), 0)
    analyst_target = safe_number(row.get("Analyst Target"), 0)
    analyst_count = safe_number(row.get("Analyst Count"), 0)
    ai_value = safe_number(row.get("AI Fair Value"), 0)
    news = safe_text(row.get("News Sentiment"), "")

    what_found = findings[:6]
    what_means = []
    why_matters = []
    how_use = []

    if "technical" in lname:
        if not what_found:
            if rsi:
                what_found.append(f"RSI: {rsi:.1f}")
            if vol:
                what_found.append(f"Volume ratio: {vol:.2f}x average")
            if atr:
                what_found.append(f"ATR volatility: {atr:.2f}%")
            if support:
                what_found.append(f"Nearest support: {fmt_money(support)}")
            if resistance:
                what_found.append(f"Nearest resistance: {fmt_money(resistance)}")

        if rsi >= 70:
            what_means.append("Momentum is strong, but the stock may be short-term overbought.")
        elif rsi >= 50:
            what_means.append("Momentum is positive and not extremely overheated.")
        elif rsi > 0:
            what_means.append("Momentum is weak or still recovering.")

        if vol and vol < 0.75:
            what_means.append("Volume is below normal, so the move has weaker confirmation.")
        elif vol >= 1.25:
            what_means.append("Volume is above average, which gives the move stronger confirmation.")

        if atr >= 8:
            what_means.append("Volatility is high; the stock can move sharply day-to-day.")
        elif atr >= 5:
            what_means.append("Volatility is elevated; expect wider swings than normal.")

        why_matters.append("Technical strength helps with timing, but a strong stock can still be a bad entry if it is near resistance or moving on weak volume.")
        how_use.append("Prefer a pullback near support or a confirmed breakout above resistance with strong volume.")
        if atr >= 5:
            how_use.append("Use smaller position sizing because volatility is elevated.")

    elif "finance" in lname:
        what_means.append("This checks whether the company is growing in a healthy way: revenue, earnings, margins, cash flow, and balance sheet.")
        why_matters.append("Revenue growth is more valuable when it converts into profit and cash flow.")
        how_use.append("Give more weight to this stock if growth, earnings, margins, and cash flow all point in the same direction.")

    elif "analyst" in lname:
        if analyst_target:
            what_found.append(f"Analyst target: {fmt_money(analyst_target)}")
        if analyst_count:
            what_found.append(f"Analyst coverage count: {int(analyst_count)}")
        if price and analyst_target:
            a_upside = ((analyst_target - price) / price) * 100
            what_found.append(f"Analyst-implied upside: {a_upside:.1f}%")
        what_means.append("This checks whether Wall Street target prices and ratings support the AI thesis.")
        if ai_value and analyst_target:
            gap = ((ai_value - analyst_target) / analyst_target) * 100
            if gap > 50:
                what_means.append("AI fair value is far above analyst consensus, so the upside is higher uncertainty.")
            elif abs(gap) <= 20:
                what_means.append("AI fair value is reasonably close to analyst consensus.")
        why_matters.append("Analyst support helps validate the thesis, but analysts can lag fast-moving news.")
        how_use.append("Use analyst support as confirmation, not as the only reason to buy.")

    elif "news" in lname:
        if news:
            what_found.append(f"Current news sentiment: {news}")
        what_means.append("This checks whether recent headlines are creating catalysts, risk, or no clear signal.")
        why_matters.append("News can quickly change sentiment, analyst revisions, and short-term demand.")
        how_use.append("Positive news is strongest when it agrees with technical, financial, and analyst signals.")
        if not findings:
            what_found.append("No high-confidence recent headline was returned.")
            what_means.append("No recent news is not automatically bearish; it means the stock may be moving on other signals.")

    elif "valuation" in lname:
        if ai_value:
            what_found.append(f"AI fair value: {fmt_money(ai_value)}")
        if upside:
            what_found.append(f"Modeled upside: {upside:.1f}%")
        what_means.append("This checks whether the current price looks attractive compared with AI fair value and analyst targets.")
        why_matters.append("Upside is useful only if supported by fundamentals, analysts, and risk controls.")
        how_use.append("Very high upside should be treated as opportunity plus uncertainty, not as a guarantee.")

    elif "insider" in lname:
        what_means.append("This checks whether executives or directors are buying or selling shares.")
        why_matters.append("Open-market insider buying can be supportive; routine selling or option exercises are less useful.")
        how_use.append("Treat insider activity as neutral until the agent classifies actual buy/sell transactions.")

    elif "institutional" in lname:
        what_means.append("This checks whether large funds appear involved or accumulating shares.")
        why_matters.append("Institutional ownership can support longer-term price moves, but 13F data is delayed.")
        how_use.append("Use institutional data as confirmation only, especially when multiple funds add over multiple quarters.")

    elif "competitor" in lname or "peer" in lname:
        what_means.append("This compares the company against peers on growth, valuation, margins, and risk.")
        why_matters.append("A company can look attractive alone but less attractive if peers are cheaper or growing faster.")
        how_use.append("Use peer context to decide whether this is the best opportunity in its group.")

    elif "recovery" in lname:
        what_means.append("This checks whether the stock is temporarily beaten down or facing a broken-business decline.")
        why_matters.append("A lower price is only attractive if the business outlook remains intact.")
        how_use.append("Prefer recovery setups with improving fundamentals, positive catalysts, and support levels holding.")

    elif "political" in lname or "congress" in lname:
        what_means.append("This checks whether congressional trading may add a sentiment signal.")
        why_matters.append("Political trade data is delayed and should not be used as a primary buy signal.")
        how_use.append("Use political trading as a minor supporting signal only after stronger agents agree.")

    else:
        what_means.append("This agent contributes one part of the overall investment thesis.")
        why_matters.append("The best setups happen when several agents point in the same direction.")
        how_use.append("Do not rely on one agent alone; combine it with valuation, technicals, news, and risk control.")

    if not what_found:
        what_found = ["No detailed metric returned yet for this agent. Run latest scan or live research for deeper data."]
    if not risks:
        risks = ["No major agent-specific red flag returned from available data."]

    return {
        "name": v4251_agent_display_name(name),
        "score": score,
        "status": status,
        "impact": impact,
        "data_used": data_used,
        "what_found": what_found[:7],
        "what_means": what_means[:5],
        "why_matters": why_matters[:4],
        "how_use": how_use[:4],
        "risks": risks[:5],
    }


def render_v4251_standardized_committee(row):
    """
    Replacement committee renderer.
    Always shows the audience-friendly interpretation format.
    """
    committee = row.get("AI Committee")
    if not isinstance(committee, dict) or not committee:
        return

    st.markdown("### 🧠 AI Agent Explanations")
    st.caption("Each agent translates raw metrics into plain-English meaning and action guidance.")

    for name, agent in committee.items():
        if not isinstance(agent, dict):
            continue
        e = v4251_build_agent_explanation(name, agent, row)
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.markdown(f"#### {e['name']}")
            c2.markdown(f"**Score:** {format_agent_score(e['score'])}")
            c3.markdown(f"**Impact:** {e['impact']}")
            st.caption(f"Status: {e['status']}" + (f" · Data used: {e['data_used']}" if e["data_used"] else ""))

            st.markdown("**What We Found**")
            for x in e["what_found"]:
                st.markdown(f"• {safe_text(x)}")

            st.markdown("**What This Means**")
            for x in e["what_means"]:
                st.markdown(f"• {safe_text(x)}")

            st.markdown("**Why It Matters**")
            for x in e["why_matters"]:
                st.markdown(f"• {safe_text(x)}")

            st.markdown("**How To Use This**")
            for x in e["how_use"]:
                st.markdown(f"• {safe_text(x)}")

            st.markdown("**Risks / Limits**")
            for x in e["risks"]:
                st.markdown(f"⚠️ {safe_text(x)}")


def v4251_level_interpretation(row):
    levels = v4244_get_smart_levels(row) if "v4244_get_smart_levels" in globals() else {}
    price = safe_number(levels.get("price") or row.get("Price"), 0)
    s1 = safe_number(levels.get("support1") or row.get("Support 1"), 0)
    r1 = safe_number(levels.get("resistance1") or row.get("Resistance 1"), 0)

    if not price or not s1 or not r1:
        return "Trading levels are not fully available. Treat this as missing data, not a bullish or bearish signal."

    down = ((price - s1) / price) * 100 if price else 0
    up = ((r1 - price) / price) * 100 if price else 0
    risk = max(price - s1, 0)
    reward = max(r1 - price, 0)
    rr = reward / risk if risk > 0 else 0

    if up < 2 and down > 5:
        return (
            f"The stock is very close to resistance with only about {up:.1f}% room before the next likely selling zone, "
            f"while support is about {down:.1f}% below. This is not an ideal fresh entry unless it breaks above resistance with volume."
        )
    if rr < 1:
        return (
            f"The short-term reward/risk is weak at about {rr:.2f}:1. "
            "A better setup is a pullback closer to support or a confirmed breakout."
        )
    if rr >= 2:
        return (
            f"The short-term reward/risk is attractive at about {rr:.2f}:1, assuming support holds."
        )
    return (
        f"The stock has about {up:.1f}% room to resistance and about {down:.1f}% downside to support. "
        "This is a balanced setup; entry discipline still matters."
    )


def render_v4251_final_ai_thesis(row):
    """
    Stronger final thesis that includes entry-quality interpretation.
    """
    ticker = safe_text(row.get("Ticker"), "Ticker")
    score = safe_number(row.get("Final Conviction"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    analyst = safe_text(row.get("Analyst Support"), "")
    news = safe_text(row.get("News Sentiment"), "")
    entry = safe_text(row.get("Entry Range"), "")
    stop = safe_number(row.get("Stop Loss"), 0)

    positives = []
    risks = []
    strategy = []

    if score >= 90:
        positives.append(f"High AI conviction at {score:.0f}/100.")
    elif score >= 75:
        positives.append(f"Constructive AI conviction at {score:.0f}/100.")
    if upside >= 50:
        positives.append(f"Very high modeled upside of {upside:.1f}%, but this needs confirmation.")
        risks.append("Very high upside also means higher uncertainty; validate with news, finance, and analyst support.")
    elif upside >= 20:
        positives.append(f"Strong modeled upside of {upside:.1f}%.")
    if "Bullish" in analyst or "Constructive" in analyst:
        positives.append(f"Analyst support is {analyst}.")
    if "Positive" in news:
        positives.append("Recent news flow appears positive.")
    elif "Neutral" in news or "N/A" in news:
        risks.append("News flow is neutral or limited, so the thesis depends more on financials, analysts, and technicals.")

    level_text = v4251_level_interpretation(row)
    strategy.append(level_text)
    if entry and entry != "N/A":
        strategy.append(f"Suggested entry zone: {entry}.")
    if stop:
        strategy.append(f"Risk control: consider stop loss near {fmt_money(stop)}.")
    strategy.append("Do not treat AI score as a guarantee. Use position sizing and confirm the setup before entering.")

    if not positives:
        positives.append("Some supportive signals exist, but the thesis needs stronger confirmation.")
    if not risks:
        risks.append("Normal market, earnings, liquidity, and execution risks still apply.")

    with st.container(border=True):
        st.markdown("### 🎯 Final AI Investment Thesis")
        st.caption("Plain-English summary of all agents, entry quality, and risk controls.")
        c1, c2 = st.columns(2)
        c1.metric("AI Confidence", f"{score:.0f}/100" if score else "N/A")
        c2.metric("Ticker", ticker)

        st.markdown("**Why This Stock Is Attractive**")
        for x in positives[:6]:
            st.markdown(f"✓ {safe_text(x)}")

        st.markdown("**Biggest Risks**")
        for x in risks[:6]:
            st.markdown(f"⚠️ {safe_text(x)}")

        st.markdown("**How To Use This Setup**")
        for x in strategy[:6]:
            st.markdown(f"• {safe_text(x)}")


def render_v4251_scanner_version_notice():
    """
    Shows a clear note when the UI code is newer than last scan output.
    """
    try:
        state = read_state()
        scanner_version = safe_text(state.get("version") or state.get("scanner_version") or "")
        if scanner_version and scanner_version not in APP_VERSION:
            st.warning(
                f"App version is {APP_VERSION}, but latest scan data was generated by scanner {scanner_version}. "
                "Run the latest cron/manual scan after deploying overnight_market_scan.py so all agent fields populate correctly."
            )
    except Exception:
        pass



# =========================
# V42.5.2 ANALYST DETAILS FALLBACK FIX
# =========================

def v4252_analyst_signal_from_row(row):
    """
    Guaranteed analyst fallback from existing scan row.
    Prevents Analyst Ratings Agent from showing all N/A when firm-level targets are unavailable.
    """
    price = safe_number(row.get("Price"), 0)
    analyst_target = safe_number(row.get("Analyst Target"), 0)
    analyst_high = safe_number(row.get("Analyst High"), 0)
    analyst_low = safe_number(row.get("Analyst Low"), 0)
    analyst_count = int(safe_number(row.get("Analyst Count"), 0))
    analyst_support = safe_text(row.get("Analyst Support"), "N/A")
    analyst_source = safe_text(row.get("Analyst Support Source"), "")
    recommendation = safe_text(row.get("Recommendation"), "N/A")
    ai_value = safe_number(row.get("AI Fair Value"), 0)

    analyst_upside = None
    if price and analyst_target:
        analyst_upside = ((analyst_target - price) / price) * 100

    ai_gap = None
    if analyst_target and ai_value:
        ai_gap = ((ai_value - analyst_target) / analyst_target) * 100

    if "Bullish" in analyst_support:
        consensus = "Bullish"
    elif "Constructive" in analyst_support:
        consensus = "Constructive"
    elif "Mixed" in analyst_support:
        consensus = "Mixed"
    elif "Weak" in analyst_support:
        consensus = "Weak"
    elif analyst_upside is not None and analyst_upside >= 20:
        consensus = "Bullish / upside-supported"
    elif analyst_upside is not None and analyst_upside >= 5:
        consensus = "Constructive"
    elif analyst_upside is not None:
        consensus = "Limited upside"
    else:
        consensus = "N/A"

    return {
        "price": price,
        "analyst_target": analyst_target,
        "analyst_high": analyst_high,
        "analyst_low": analyst_low,
        "analyst_count": analyst_count,
        "analyst_support": analyst_support,
        "analyst_source": analyst_source,
        "recommendation": recommendation,
        "analyst_upside": analyst_upside,
        "ai_gap": ai_gap,
        "consensus": consensus,
    }


@st.cache_data(ttl=900)
def v4252_fetch_fmp_analyst_detail_rows(ticker):
    """
    Best-effort firm-level analyst detail retrieval.
    FMP access varies by plan. This function safely tries several endpoints.
    """
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker or not FMP_API_KEY:
        return []

    endpoints = [
        f"price-target/{ticker}",
        f"price-target-consensus/{ticker}",
        f"upgrades-downgrades/{ticker}",
        f"analyst-stock-recommendations/{ticker}",
    ]

    rows = []
    for endpoint in endpoints:
        try:
            data = v424_fmp_get(endpoint) if "v424_fmp_get" in globals() else None
            if not isinstance(data, list):
                continue
            for item in data[:20]:
                if not isinstance(item, dict):
                    continue
                firm = (
                    item.get("analystCompany") or item.get("firm") or item.get("analyst") or
                    item.get("brokerage") or item.get("company") or item.get("publishedBy") or ""
                )
                rating = (
                    item.get("rating") or item.get("newGrade") or item.get("previousGrade") or
                    item.get("recommendation") or item.get("grade") or item.get("action") or ""
                )
                target = (
                    item.get("priceTarget") or item.get("target") or item.get("targetPrice") or
                    item.get("publishedPriceTarget") or item.get("targetConsensus") or
                    item.get("targetMean") or item.get("targetMedian")
                )
                date = item.get("publishedDate") or item.get("date") or item.get("updatedDate") or ""
                target_num = safe_number(target, 0)

                # Keep rows if they contain useful firm/rating/target detail.
                if firm or rating or target_num:
                    rows.append({
                        "Firm": safe_text(firm, "Analyst"),
                        "Rating": safe_text(rating, "N/A"),
                        "Target": target_num,
                        "Date": safe_text(date, ""),
                        "Source": f"FMP {endpoint}",
                    })
            if rows:
                break
        except Exception:
            continue

    # Deduplicate and sort target-bearing rows first.
    seen = set()
    clean = []
    for r in rows:
        key = (r.get("Firm"), r.get("Rating"), r.get("Target"), r.get("Date"))
        if key in seen:
            continue
        seen.add(key)
        clean.append(r)

    clean = sorted(clean, key=lambda x: safe_number(x.get("Target"), 0), reverse=True)
    return clean[:5]


def render_v424_analyst_ratings_box(row):
    """
    V42.5.2 override:
    Always shows useful analyst data using scan fallback even when top firm-level rows are unavailable.
    """
    ticker = safe_text(row.get("Ticker"), "").upper().strip()
    if not ticker:
        return

    base = v4252_analyst_signal_from_row(row)
    firm_rows = v4252_fetch_fmp_analyst_detail_rows(ticker)

    with st.container(border=True):
        st.markdown("### 🏦 Analyst Ratings Agent")
        st.caption("Uses firm-level analyst targets when available. Falls back to scan-level analyst target/count/support so this section does not show all N/A.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Consensus Target", fmt_money(base["analyst_target"]) if base["analyst_target"] else "N/A")
        c2.metric("Analyst Count", str(base["analyst_count"]) if base["analyst_count"] else "N/A")
        c3.metric("Analyst Upside", f"{base['analyst_upside']:.1f}%" if base["analyst_upside"] is not None else "N/A")
        c4.metric("AI vs Analysts", f"{base['ai_gap']:.1f}%" if base["ai_gap"] is not None else "N/A")

        st.markdown("**What We Found**")
        found = []
        if base["analyst_target"]:
            found.append(f"Average analyst target is {fmt_money(base['analyst_target'])}.")
        if base["analyst_count"]:
            found.append(f"{base['analyst_count']} analysts are included in the available coverage count.")
        if base["analyst_upside"] is not None:
            found.append(f"Analyst consensus implies {base['analyst_upside']:.1f}% upside from the current price.")
        if base["analyst_support"] and base["analyst_support"] != "N/A":
            found.append(f"Analyst support reads: {base['analyst_support']}.")
        if base["analyst_high"]:
            found.append(f"High target is {fmt_money(base['analyst_high'])}.")
        if base["analyst_low"]:
            found.append(f"Low target is {fmt_money(base['analyst_low'])}.")
        if not found:
            found.append("No analyst target or coverage data was returned for this ticker.")
        for x in found:
            st.markdown(f"• {safe_text(x)}")

        st.markdown("**What This Means**")
        if base["consensus"] != "N/A":
            st.markdown(f"• Overall analyst read is **{base['consensus']}** based on available target/support data.")
        if base["ai_gap"] is not None:
            if base["ai_gap"] > 50:
                st.markdown("• AI fair value is far above analyst consensus, so the AI upside should be treated as higher uncertainty.")
            elif base["ai_gap"] < -20:
                st.markdown("• AI fair value is below analyst consensus, meaning the AI model is more conservative than Wall Street.")
            else:
                st.markdown("• AI fair value is reasonably close to analyst consensus.")
        else:
            st.markdown("• AI vs analyst comparison is limited because one of the target fields is unavailable.")

        st.markdown("**Why It Matters**")
        st.markdown("• Analyst targets help validate whether Wall Street broadly supports the investment thesis.")
        st.markdown("• Analyst support is useful confirmation, but it can lag fast-moving earnings, news, and market moves.")

        st.markdown("**How To Use This**")
        st.markdown("• Use analyst support as confirmation, not as the only reason to buy.")
        st.markdown("• If AI upside is much higher than analyst upside, require stronger confirmation from financials, news, and technicals.")

        if firm_rows:
            display = []
            for r in firm_rows[:5]:
                display.append({
                    "Firm / Analyst": r.get("Firm") or "Analyst",
                    "Rating / Action": r.get("Rating") or "N/A",
                    "Price Target": fmt_money(r.get("Target")) if safe_number(r.get("Target"), 0) else "N/A",
                    "Date": r.get("Date") or "",
                    "Source": r.get("Source") or "",
                })
            st.markdown("**Top analyst / firm-level rows returned by source:**")
            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
        else:
            st.warning(
                "Firm-level top 5 analyst rows were not returned by the available API plan/source. "
                "The section above is using scan-level analyst target, count, and support as the fallback."
            )

        if base["analyst_source"]:
            st.caption(f"Analyst support source: {base['analyst_source']}")





# =========================
# V42.5.3 OFFICIAL ECONOMIC CALENDAR FALLBACK
# =========================

def v4253_extract_dates_from_text(text):
    text = safe_text(text, "")
    text = re.sub(r"\s+", " ", text)
    patterns = [
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+20\d{2}",
        r"20\d{2}-\d{2}-\d{2}",
        r"\d{1,2}/\d{1,2}/20\d{2}",
    ]
    out = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            val = m.group(0)
            if val not in out:
                out.append(val)
            if len(out) >= 5:
                return out
    return out


@st.cache_data(ttl=21600)
def v4253_official_bls_calendar():
    events = []
    try:
        url = "https://www.bls.gov/schedule/news_release/"
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return events
        text = r.text
        checks = [
            ("CPI / Inflation report", ["Consumer Price Index", "CPI"]),
            ("PPI report", ["Producer Price Index", "PPI"]),
            ("Jobs report / Employment Situation", ["Employment Situation"]),
            ("Job Openings / JOLTS", ["Job Openings and Labor Turnover", "JOLTS"]),
        ]
        for label, terms in checks:
            loc = -1
            for term in terms:
                loc = text.lower().find(term.lower())
                if loc >= 0:
                    break
            if loc >= 0:
                snippet = text[max(0, loc-500): loc+900]
                dates = v4253_extract_dates_from_text(snippet)
                events.append({
                    "date": dates[0] if dates else "Open official BLS schedule",
                    "event": label,
                    "source": "Official BLS schedule",
                    "link": url,
                })
    except Exception:
        pass
    return events


@st.cache_data(ttl=21600)
def v4253_official_fed_calendar():
    events = []
    try:
        url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return events
        text = r.text
        idx = text.lower().find("fomc")
        snippet = text[idx:idx+5000] if idx >= 0 else text[:5000]
        dates = v4253_extract_dates_from_text(snippet)
        events.append({
            "date": dates[0] if dates else "Open official Federal Reserve calendar",
            "event": "FOMC / Fed decision or minutes",
            "source": "Official Federal Reserve calendar",
            "link": url,
        })
    except Exception:
        pass
    return events


@st.cache_data(ttl=21600)
def v4253_official_bea_calendar():
    events = []
    try:
        url = "https://www.bea.gov/news/schedule"
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return events
        text = r.text
        checks = [
            ("GDP report", ["Gross Domestic Product", "GDP"]),
            ("PCE / Personal Income and Outlays", ["Personal Income and Outlays", "PCE"]),
        ]
        for label, terms in checks:
            loc = -1
            for term in terms:
                loc = text.lower().find(term.lower())
                if loc >= 0:
                    break
            if loc >= 0:
                snippet = text[max(0, loc-600): loc+1000]
                dates = v4253_extract_dates_from_text(snippet)
                events.append({
                    "date": dates[0] if dates else "Open official BEA schedule",
                    "event": label,
                    "source": "Official BEA schedule",
                    "link": url,
                })
    except Exception:
        pass
    return events


@st.cache_data(ttl=21600)
def v4253_official_econ_fallback():
    events = []
    events.extend(v4253_official_bls_calendar())
    events.extend(v4253_official_fed_calendar())
    events.extend(v4253_official_bea_calendar())

    clean = []
    seen = set()
    for e in events:
        key = (safe_text(e.get("event")), safe_text(e.get("source")))
        if key in seen:
            continue
        seen.add(key)
        clean.append(e)

    if clean:
        return clean[:12]

    return [
        {
            "date": "Open official BLS schedule",
            "event": "CPI, PPI, Jobs Report, JOLTS",
            "source": "Official BLS link fallback",
            "link": "https://www.bls.gov/schedule/news_release/",
        },
        {
            "date": "Open official Federal Reserve calendar",
            "event": "FOMC / Fed decision or minutes",
            "source": "Official Fed link fallback",
            "link": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        },
        {
            "date": "Open official BEA schedule",
            "event": "GDP, PCE, Personal Income and Outlays",
            "source": "Official BEA link fallback",
            "link": "https://www.bea.gov/news/schedule",
        },
    ]


@st.cache_data(ttl=1800)
def v424_economic_calendar():
    important = ["CPI", "PPI", "Payroll", "Nonfarm", "FOMC", "Fed", "Jobless", "GDP", "Retail Sales", "Inflation", "Unemployment", "ISM", "PMI", "PCE"]
    today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()
    end = today + dt.timedelta(days=45)
    events = []

    try:
        data = v424_fmp_get("economic_calendar", {"from": today.isoformat(), "to": end.isoformat()}) if "v424_fmp_get" in globals() else None
        if isinstance(data, list):
            for item in data:
                name = safe_text(item.get("event") or item.get("name") or "")
                if not name:
                    continue
                if any(term.lower() in name.lower() for term in important):
                    events.append({
                        "date": safe_text(item.get("date") or item.get("datetime") or ""),
                        "event": name,
                        "actual": item.get("actual"),
                        "estimate": item.get("estimate"),
                        "previous": item.get("previous"),
                        "source": "FMP",
                    })
    except Exception:
        pass

    if not events and "v4242_tradingeconomics_calendar" in globals():
        events = v4242_tradingeconomics_calendar()

    if not events:
        events = v4253_official_econ_fallback()

    events = sorted(events, key=lambda x: safe_text(x.get("date")))
    today_str = today.isoformat()
    todays = [e for e in events if safe_text(e.get("date")).startswith(today_str)]

    return {
        "today": todays[:8],
        "next": events[:12],
        "source": safe_text(events[0].get("source"), "Official fallback") if events else "No source",
    }


def v4253_render_event_line(e):
    event = safe_text(e.get("event"), "Economic event")
    date = safe_text(e.get("date"), "Date unavailable")
    link = safe_text(e.get("link"), "")
    source = safe_text(e.get("source"), "")
    label = f"**{event}** — {date}"
    if link:
        label += f" ([official source]({link}))"
    if source:
        label += f" · _{source}_"
    return label


def render_v424_market_command_center():
    st.markdown("## 🧭 Market Command Center")

    quotes = v424_market_quotes()
    if quotes:
        cols = st.columns(min(5, len(quotes)))
        for i, q in enumerate(quotes[:5]):
            pct = v424_float(q.get("change_pct"), None) if "v424_float" in globals() else safe_number(q.get("change_pct"), None)
            delta = f"{pct:+.2f}%" if pct is not None else None
            label = q.get("display_label") or q.get("symbol", "")
            source = safe_text(q.get("source"), "")
            cols[i].metric(label, v424_money(q.get("price")) if "v424_money" in globals() else fmt_money(q.get("price")), delta)
            if source:
                cols[i].caption(source)
    else:
        st.info(
            "Market quote data did not return from FMP or Yahoo fallback. "
            f"FMP_API_KEY configured={'Yes' if bool(FMP_API_KEY) else 'No'}."
        )

    econ = v424_economic_calendar()
    earnings = v424_earnings_today()
    news = v424_market_news()

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            st.caption(f"Source: {safe_text(econ.get('source'), 'Unknown')}")
            today_events = econ.get("today") or []
            next_events = econ.get("next") or []
            if today_events:
                st.markdown("**Today:**")
                for e in today_events[:6]:
                    st.markdown(f"• {v4253_render_event_line(e)}")
            elif next_events:
                st.caption("No major event found for today. Showing next market-moving reports.")
                for e in next_events[:8]:
                    st.markdown(f"• {v4253_render_event_line(e)}")
            else:
                st.caption("No economic calendar source returned data.")

    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            if earnings:
                edf = pd.DataFrame(earnings)
                st.caption("Source priority: FMP → Nasdaq public fallback → Alpha Vantage optional fallback")
                st.dataframe(edf, use_container_width=True, hide_index=True)
            else:
                st.caption(
                    "No earnings returned from FMP, Nasdaq fallback, or Alpha Vantage. "
                    f"FMP_API_KEY configured={'Yes' if bool(FMP_API_KEY) else 'No'}; "
                    f"ALPHA_VANTAGE_API_KEY configured={'Yes' if bool((globals().get('ALPHA_VANTAGE_API_KEY') or '').strip()) else 'No'}."
                )

    with st.container(border=True):
        st.markdown("### 📰 Market News")
        if news:
            st.caption("Source priority: NewsAPI → Finnhub general news")
            for h in news[:5]:
                st.markdown(f"• {safe_text(h)}")
        else:
            st.caption(
                "No broad market headlines returned. "
                f"NEWSAPI_KEY configured={'Yes' if bool((globals().get('NEWSAPI_KEY') or globals().get('NEWS_API_KEY') or os.getenv('NEWSAPI_KEY') or os.getenv('NEWS_API_KEY') or '').strip()) else 'No'}; "
                f"FINNHUB_API_KEY configured={'Yes' if bool((globals().get('FINNHUB_API_KEY') or os.getenv('FINNHUB_API_KEY') or os.getenv('FINNHUB_TOKEN') or '').strip()) else 'No'}."
            )



# =========================
# V42.6 PAID CLIENT INTELLIGENCE + ROBUST FALLBACKS
# =========================

def v426_key_status():
    return {
        "FMP": bool((globals().get("FMP_API_KEY") or os.getenv("FMP_API_KEY") or "").strip()),
        "Finnhub": bool((globals().get("FINNHUB_API_KEY") or os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_TOKEN") or "").strip()),
        "NewsAPI": bool((globals().get("NEWSAPI_KEY") or globals().get("NEWS_API_KEY") or os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY") or "").strip()),
        "AlphaVantage": bool((globals().get("ALPHA_VANTAGE_API_KEY") or os.getenv("ALPHA_VANTAGE_API_KEY") or os.getenv("ALPHAVANTAGE_API_KEY") or "").strip()),
    }


def v426_safe_get(url, params=None, headers=None, timeout=12):
    try:
        r = requests.get(url, params=params or {}, headers=headers or {"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if r.status_code == 200:
            ctype = safe_text(r.headers.get("content-type"), "")
            if "json" in ctype.lower():
                return r.json()
            return r.text
    except Exception:
        return None
    return None


@st.cache_data(ttl=900)
def v426_finnhub_earnings_today():
    rows = []
    try:
        token = (globals().get("FINNHUB_API_KEY") or os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_TOKEN") or "").strip()
        if not token:
            return rows
        today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()
        data = v426_safe_get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={"from": today.isoformat(), "to": today.isoformat(), "token": token},
        )
        earnings = []
        if isinstance(data, dict):
            earnings = data.get("earningsCalendar") or data.get("earnings") or []
        if isinstance(earnings, list):
            for item in earnings:
                sym = safe_text(item.get("symbol") or "").upper()
                if not sym:
                    continue
                rows.append({
                    "Company": safe_text(item.get("name") or item.get("company") or ""),
                    "Ticker": sym,
                    "Date": safe_text(item.get("date") or today.isoformat()),
                    "Time": safe_text(item.get("hour") or item.get("time") or ""),
                    "EPS Est": item.get("epsEstimate"),
                    "Revenue Est": item.get("revenueEstimate"),
                    "Source": "Finnhub earnings calendar",
                })
                if len(rows) >= 40:
                    break
    except Exception:
        pass
    return rows


@st.cache_data(ttl=900)
def v426_yahoo_calendar_earnings():
    rows = []
    try:
        today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()
        html = v426_safe_get("https://finance.yahoo.com/calendar/earnings", params={"day": today.isoformat()}, headers={"User-Agent": "Mozilla/5.0"})
        if not isinstance(html, str):
            return rows
        # Best-effort no-key fallback; Yahoo markup is unstable, so this is intentionally conservative.
        symbols = re.findall(r'>([A-Z][A-Z0-9.\-]{0,8})</a>', html)
        seen = set()
        for sym in symbols:
            if sym in seen or len(sym) > 8:
                continue
            seen.add(sym)
            rows.append({
                "Company": "",
                "Ticker": sym,
                "Date": today.isoformat(),
                "Time": "",
                "EPS Est": "",
                "Revenue Est": "",
                "Source": "Yahoo earnings calendar fallback",
            })
            if len(rows) >= 40:
                break
    except Exception:
        pass
    return rows


@st.cache_data(ttl=900)
def v424_earnings_today():
    """
    V42.6 override:
    Earnings source priority:
    FMP -> Finnhub -> Nasdaq public -> Alpha Vantage -> Yahoo.
    This is broader than only Nasdaq and shows the source used.
    """
    today = v424_today() if "v424_today" in globals() else dt.datetime.now().date()
    rows = []

    try:
        data = v424_fmp_get("earning_calendar", {"from": today.isoformat(), "to": today.isoformat()}) if "v424_fmp_get" in globals() else None
        if isinstance(data, list):
            for item in data:
                sym = safe_text(item.get("symbol") or "").upper()
                if not sym:
                    continue
                company = safe_text(item.get("name") or item.get("companyName") or item.get("company") or "")
                rows.append({
                    "Company": company,
                    "Ticker": sym,
                    "Date": safe_text(item.get("date") or today.isoformat()),
                    "Time": safe_text(item.get("time") or ""),
                    "EPS Est": item.get("epsEstimated"),
                    "Revenue Est": item.get("revenueEstimated"),
                    "Source": "FMP",
                })
                if len(rows) >= 40:
                    break
    except Exception:
        pass
    if rows:
        return rows

    for fn_name in ["v426_finnhub_earnings_today", "v4242_nasdaq_earnings_today", "v4242_alpha_vantage_earnings_today", "v426_yahoo_calendar_earnings"]:
        try:
            fn = globals().get(fn_name)
            if not fn:
                continue
            rows = fn()
            if rows:
                for r in rows:
                    if "Ticker" not in r and "Symbol" in r:
                        r["Ticker"] = r.get("Symbol")
                    if "Company" not in r:
                        r["Company"] = ""
                return rows
        except Exception:
            continue
    return []


def v426_source_health_card():
    keys = v426_key_status()
    with st.expander("🔌 Data Source Health", expanded=False):
        st.markdown("**Configured:** " + ", ".join([k for k, v in keys.items() if v]) if any(keys.values()) else "**Configured:** None detected")
        st.markdown("**Missing optional:** " + ", ".join([k for k, v in keys.items() if not v]) if any(not v for v in keys.values()) else "**Missing optional:** None")
        st.caption("For paid-client quality, configure FMP + Finnhub + NewsAPI + Alpha Vantage. Public fallbacks are best-effort and can be incomplete or blocked.")


def v426_truthful_agent_quality(row):
    committee = row.get("AI Committee")
    if not isinstance(committee, dict):
        return {"ready": [], "limited": []}
    ready, limited = [], []
    for name, agent in committee.items():
        if not isinstance(agent, dict):
            continue
        status = safe_text(agent.get("status"), "").lower()
        findings = agent.get("findings") or []
        if not isinstance(findings, list):
            findings = []
        if "not connected" in status or "framework" in status or (not findings and "technical" not in safe_text(name).lower()):
            limited.append(safe_text(name))
        else:
            ready.append(safe_text(name))
    return {"ready": ready, "limited": limited}


def v426_verdict(row):
    score = safe_number(row.get("Final Conviction"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    price = safe_number(row.get("Price"), 0)
    s1 = safe_number(row.get("Support 1"), 0)
    r1 = safe_number(row.get("Resistance 1"), 0)
    rsi = safe_number(row.get("RSI"), 0)
    vol = safe_number(row.get("Volume Ratio"), 0)
    atr = safe_number(row.get("ATR %"), 0)
    ai_value = safe_number(row.get("AI Fair Value"), 0)
    analyst = safe_number(row.get("Analyst Target"), 0)
    analyst_support = safe_text(row.get("Analyst Support"), "")

    reasons, risks = [], []
    action, action_detail = "Watchlist", "Monitor for a cleaner entry."

    if score >= 90:
        reasons.append(f"High AI conviction ({score:.0f}/100).")
    if analyst and price:
        aup = ((analyst - price) / price) * 100
        if aup > 20:
            reasons.append(f"Analysts imply {aup:.1f}% upside.")
        elif aup < 5:
            risks.append("Analyst consensus shows limited upside.")
    if upside >= 50:
        reasons.append(f"AI model shows very high upside ({upside:.1f}%).")
        risks.append("Very high AI upside needs confirmation from fundamentals, news, and analysts.")
    if ai_value and analyst:
        gap = ((ai_value - analyst) / analyst) * 100
        if gap > 60:
            risks.append(f"AI fair value is {gap:.1f}% above analyst consensus, so uncertainty is elevated.")
    if rsi >= 70:
        risks.append("RSI is overbought.")
    elif 50 <= rsi < 70:
        reasons.append("Momentum is positive without being extremely overheated.")
    if vol and vol < 0.75:
        risks.append("Volume is light; recent move has weaker confirmation.")
    if atr >= 5:
        risks.append("Volatility is elevated; use smaller position sizing.")
    if price and s1 and r1 and price > s1:
        rr = (r1 - price) / (price - s1) if (price - s1) > 0 else 0
        if rr < 1:
            risks.append(f"Short-term reward/risk is weak ({rr:.2f}:1).")
            action = "Wait"
            action_detail = f"Wait for pullback near {fmt_money(s1)} or breakout above {fmt_money(r1)} with volume."
        elif rr >= 1.5 and score >= 75:
            action = "Actionable Watch"
            action_detail = f"Entry is more attractive if support near {fmt_money(s1)} holds."
    if "Bullish" in analyst_support:
        reasons.append(f"Analyst support is {analyst_support}.")
    if not reasons:
        reasons.append("Some supportive signals exist, but more confirmation is needed.")
    if not risks:
        risks.append("Normal market, earnings, liquidity, and execution risks still apply.")
    return {"action": action, "action_detail": action_detail, "reasons": reasons[:4], "risks": risks[:4]}


def render_v426_paid_client_summary(row):
    ticker = safe_text(row.get("Ticker"), "")
    company = safe_text(row.get("Company"), ticker)
    v = v426_verdict(row)
    quality = v426_truthful_agent_quality(row)
    with st.container(border=True):
        st.markdown(f"### 🧠 AI Verdict — {ticker}{(' · ' + company) if company and company != ticker else ''}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Decision Lens", v["action"])
        c2.metric("AI Score", f"{safe_number(row.get('Final Conviction'), 0):.0f}/100")
        c3.metric("Analyst Target", fmt_money(row.get("Analyst Target")) if safe_number(row.get("Analyst Target"), 0) else "N/A")
        st.info(v["action_detail"])
        left, right = st.columns(2)
        with left:
            st.markdown("**Top Reasons**")
            for r in v["reasons"]:
                st.markdown(f"✓ {safe_text(r)}")
        with right:
            st.markdown("**Key Risks**")
            for r in v["risks"]:
                st.markdown(f"⚠️ {safe_text(r)}")
        if quality["limited"]:
            st.caption(f"Agent readiness: {len(quality['ready'])} data-backed agents, {len(quality['limited'])} limited/framework agents. Framework-only agents are not primary buy signals.")


def render_v426_agent_scorecard(row):
    committee = row.get("AI Committee")
    if not isinstance(committee, dict) or not committee:
        return
    rows = []
    for name, agent in committee.items():
        if not isinstance(agent, dict):
            continue
        score = agent.get("score")
        status = safe_text(agent.get("status"), "N/A")
        impact = safe_text(agent.get("impact"), "Neutral")
        findings = agent.get("findings") or []
        risks = agent.get("risks") or []
        if not isinstance(findings, list):
            findings = []
        if not isinstance(risks, list):
            risks = []
        readiness = "Data-backed" if findings and "not connected" not in status.lower() and "framework" not in status.lower() else "Limited"
        rows.append({
            "Agent": safe_text(name),
            "Score": "N/A" if score is None else f"{int(safe_number(score, 0))}",
            "Status": status,
            "Readiness": readiness,
            "Main Finding": safe_text(findings[0]) if findings else "No detailed finding returned",
            "Main Risk": safe_text(risks[0]) if risks else "No major risk returned",
        })
    with st.container(border=True):
        st.markdown("### 🤖 Agent Scorecard")
        st.caption("Condensed view for quick decision-making. Full agent explanations remain below.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_v426_compact_research_card(row):
    render_v426_paid_client_summary(row)
    render_v426_agent_scorecard(row)


def render_v424_market_command_center():
    st.markdown("## 🧭 Market Command Center")
    quotes = v424_market_quotes()
    if quotes:
        cols = st.columns(min(5, len(quotes)))
        for i, q in enumerate(quotes[:5]):
            pct = v424_float(q.get("change_pct"), None) if "v424_float" in globals() else safe_number(q.get("change_pct"), None)
            delta = f"{pct:+.2f}%" if pct is not None else None
            label = q.get("display_label") or q.get("symbol", "")
            cols[i].metric(label, v424_money(q.get("price")) if "v424_money" in globals() else fmt_money(q.get("price")), delta)
            cols[i].caption(safe_text(q.get("source"), ""))
    else:
        st.info("Market quotes unavailable from FMP/Yahoo fallback.")

    econ = v424_economic_calendar()
    earnings = v424_earnings_today()
    news = v424_market_news()

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            st.caption(f"Source: {safe_text(econ.get('source'), 'Unknown')}")
            events = (econ.get("today") or []) or (econ.get("next") or [])
            if events:
                if not econ.get("today"):
                    st.caption("No major event found for today. Showing upcoming market-moving events.")
                for e in events[:6]:
                    if "v4253_render_event_line" in globals():
                        st.markdown(f"• {v4253_render_event_line(e)}")
                    else:
                        st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
            else:
                st.caption("No economic calendar data returned from connected or official fallback sources.")

    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            if earnings:
                edf = pd.DataFrame(earnings)
                preferred = [c for c in ["Company", "Ticker", "Symbol", "Date", "Time", "EPS Est", "Revenue Est", "Source"] if c in edf.columns]
                edf = edf[preferred] if preferred else edf
                st.caption("Source priority: FMP → Finnhub → Nasdaq → Alpha Vantage → Yahoo")
                st.dataframe(edf, use_container_width=True, hide_index=True)
            else:
                st.caption("No earnings returned today from FMP, Finnhub, Nasdaq, Alpha Vantage, or Yahoo fallback.")

    with st.container(border=True):
        st.markdown("### 📰 Market News")
        if news:
            for h in news[:5]:
                st.markdown(f"• {safe_text(h)}")
        else:
            st.caption("No broad market headlines returned. Add NEWSAPI_KEY or FINNHUB_API_KEY for better market news.")
    v426_source_health_card()




def render_v4261_cron_performance_note():
    with st.expander("⚡ Cron Performance Mode", expanded=False):
        st.markdown("V42.6.1 is designed to cut scheduled scan time by skipping expensive deep APIs during the pre-rank pass and hard-capping full committee work.")
        st.markdown("Target: Top candidates get deeper agents; the rest stay lightweight until searched/opened live.")
        st.caption("Recommended Render Cron env vars: FAST_CRON_MODE=true, FAST_CRON_SKIP_PRE_RANK_DEEP_APIS=true, FULL_COMMITTEE_LIMIT=15, ETF_FULL_COMMITTEE_LIMIT=10, HTTP_TIMEOUT_FAST=6")


# =========================
# V42.7 PAID CLIENT LAYOUT + INTELLIGENCE UPGRADE
# =========================

def v427_metric_money(value):
    try:
        return fmt_money(value)
    except Exception:
        x = safe_number(value, 0)
        return "N/A" if not x else f"${x:,.2f}"


def v427_agent_readiness(agent_name, agent):
    if not isinstance(agent, dict):
        return "Limited"
    status = safe_text(agent.get("status"), "").lower()
    findings = agent.get("findings") or []
    data_used = safe_text(agent.get("data_used"), "").lower()
    if "not connected" in status or "framework" in status or "planned" in data_used:
        return "Beta / framework"
    if isinstance(findings, list) and len(findings) >= 1:
        return "Data-backed"
    return "Limited"


def v427_decision_color_label(action):
    action = safe_text(action, "")
    if "Wait" in action:
        return "🟡 WAIT"
    if "Actionable" in action or "Strong" in action:
        return "🟢 WATCH / ACTIONABLE"
    if "Avoid" in action:
        return "🔴 AVOID"
    return "⚪ WATCHLIST"


def v427_build_client_verdict(row):
    # Reuse V42.6 logic when available, then sharpen wording.
    base = v426_verdict(row) if "v426_verdict" in globals() else {
        "action": "Watchlist",
        "action_detail": "Monitor for a cleaner entry.",
        "reasons": [],
        "risks": [],
    }

    score = safe_number(row.get("Final Conviction"), 0)
    price = safe_number(row.get("Price"), 0)
    ai_value = safe_number(row.get("AI Fair Value"), 0)
    analyst_target = safe_number(row.get("Analyst Target"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    support = safe_number(row.get("Support 1"), 0)
    resistance = safe_number(row.get("Resistance 1"), 0)
    volume = safe_number(row.get("Volume Ratio"), 0)
    atr = safe_number(row.get("ATR %"), 0)

    decision = base.get("action", "Watchlist")
    headline = base.get("action_detail", "Monitor for a cleaner entry.")

    # Paid-customer rule: if AI value is extremely above analyst target, don't call it a straight buy.
    if ai_value and analyst_target:
        gap = ((ai_value - analyst_target) / analyst_target) * 100
        if gap > 75:
            decision = "Wait / Validate"
            headline = "AI upside is much higher than Wall Street consensus. Treat this as a high-upside watchlist idea, not an automatic buy."

    if volume and volume < 0.75 and atr >= 5:
        decision = "Wait"
        headline = "Trend is constructive, but light volume plus elevated volatility makes this a poor chase entry."

    if price and resistance and support and price > support:
        rr = (resistance - price) / (price - support) if (price - support) > 0 else 0
        if rr < 1:
            decision = "Wait"
            headline = f"Reward/risk is weak at current price. Prefer pullback near {v427_metric_money(support)} or breakout above {v427_metric_money(resistance)} with volume."

    reasons = list(dict.fromkeys([safe_text(x) for x in base.get("reasons", []) if safe_text(x)]))
    risks = list(dict.fromkeys([safe_text(x) for x in base.get("risks", []) if safe_text(x)]))

    if score >= 90 and "High AI conviction" not in " ".join(reasons):
        reasons.insert(0, f"High AI conviction at {score:.0f}/100.")
    if analyst_target and price:
        aup = ((analyst_target - price) / price) * 100
        reasons.append(f"Wall Street target implies {aup:.1f}% upside.")
    if upside >= 50:
        risks.append("Modeled AI upside is very high, so confidence depends on source quality and confirmation.")
    if volume and volume < 0.75:
        risks.append("Trading volume is light, which weakens breakout confirmation.")
    if atr >= 5:
        risks.append("Volatility is elevated; position size should be smaller.")

    reasons = list(dict.fromkeys(reasons))[:4]
    risks = list(dict.fromkeys(risks))[:4]

    return {
        "decision": v427_decision_color_label(decision),
        "headline": headline,
        "reasons": reasons or ["Some supportive signals exist, but the setup needs more confirmation."],
        "risks": risks or ["Normal market, earnings, and execution risks still apply."],
    }


def render_v427_paid_customer_header(row):
    ticker = safe_text(row.get("Ticker"), "")
    company = safe_text(row.get("Company"), "")
    verdict = v427_build_client_verdict(row)

    with st.container(border=True):
        st.markdown(f"## {ticker} {('— ' + company) if company else ''}")
        st.markdown(f"### {verdict['decision']}")
        st.info(verdict["headline"])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("AI Score", f"{safe_number(row.get('Final Conviction'), 0):.0f}/100")
        c2.metric("Price", v427_metric_money(row.get("Price")))
        c3.metric("Analyst Target", v427_metric_money(row.get("Analyst Target")))
        c4.metric("AI Fair Value", v427_metric_money(row.get("AI Fair Value")))

        left, right = st.columns(2)
        with left:
            st.markdown("**Why it’s interesting**")
            for x in verdict["reasons"]:
                st.markdown(f"✓ {safe_text(x)}")
        with right:
            st.markdown("**What could go wrong**")
            for x in verdict["risks"]:
                st.markdown(f"⚠️ {safe_text(x)}")


def render_v427_entry_plan(row):
    price = safe_number(row.get("Price"), 0)
    support = safe_number(row.get("Support 1"), 0)
    resistance = safe_number(row.get("Resistance 1"), 0)
    breakout = safe_number(row.get("Breakout Level"), 0)
    entry = safe_text(row.get("Entry Range"), "")
    stop = safe_number(row.get("Stop Loss"), 0)
    atr = safe_number(row.get("ATR %"), 0)
    volume = safe_number(row.get("Volume Ratio"), 0)

    with st.container(border=True):
        st.markdown("### 🎯 Entry & Risk Plan")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preferred Entry", entry if entry and entry != "N/A" else (v427_metric_money(support) if support else "Wait"))
        c2.metric("Support", v427_metric_money(support) if support else "N/A")
        c3.metric("Breakout", v427_metric_money(breakout or resistance) if (breakout or resistance) else "N/A")
        c4.metric("Stop", v427_metric_money(stop) if stop else "N/A")

        bullets = []
        if price and support and resistance and price > support:
            rr = (resistance - price) / (price - support) if (price - support) > 0 else 0
            if rr < 1:
                bullets.append(f"Current reward/risk is weak ({rr:.2f}:1). Waiting improves the setup.")
            else:
                bullets.append(f"Current reward/risk is acceptable ({rr:.2f}:1) if support holds.")
        if volume and volume < 0.75:
            bullets.append("Volume is light. A breakout should be confirmed by stronger trading volume.")
        if atr >= 5:
            bullets.append("ATR volatility is elevated. Use smaller position size and avoid oversized entries.")
        if not bullets:
            bullets.append("Entry quality is acceptable, but still use a stop and avoid chasing gap-ups.")

        for b in bullets:
            st.markdown(f"• {safe_text(b)}")


def render_v427_agent_score_strip(row):
    committee = row.get("AI Committee")
    if not isinstance(committee, dict) or not committee:
        return

    rows = []
    for name, agent in committee.items():
        if not isinstance(agent, dict):
            continue
        findings = agent.get("findings") or []
        risks = agent.get("risks") or []
        if not isinstance(findings, list):
            findings = []
        if not isinstance(risks, list):
            risks = []
        rows.append({
            "Agent": safe_text(name),
            "Score": "N/A" if agent.get("score") is None else f"{int(safe_number(agent.get('score'), 0))}",
            "Status": safe_text(agent.get("status"), "N/A"),
            "Readiness": v427_agent_readiness(name, agent),
            "Takeaway": safe_text(agent.get("bottom_line") or (findings[0] if findings else "No detail returned"))[:140],
        })

    with st.container(border=True):
        st.markdown("### 🤖 AI Agent Scorecard")
        st.caption("Fast paid-client view. Open detailed agent explanations only when needed.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_v427_clean_research_card(row):
    render_v427_paid_customer_header(row)
    render_v427_entry_plan(row)
    render_v427_agent_score_strip(row)


def v427_hide_duplicate_notice():
    st.caption("Detailed education, raw data, and legacy committee details are intentionally kept lower on the page for advanced review.")


# Stronger market command center language.
def render_v424_market_command_center():
    st.markdown("## 🧭 Market Command Center")

    quotes = v424_market_quotes()
    if quotes:
        cols = st.columns(min(5, len(quotes)))
        for i, q in enumerate(quotes[:5]):
            pct = v424_float(q.get("change_pct"), None) if "v424_float" in globals() else safe_number(q.get("change_pct"), None)
            delta = f"{pct:+.2f}%" if pct is not None else None
            label = q.get("display_label") or q.get("symbol", "")
            cols[i].metric(label, v424_money(q.get("price")) if "v424_money" in globals() else fmt_money(q.get("price")), delta)
            cols[i].caption(safe_text(q.get("source"), ""))
    else:
        st.warning("Market quotes unavailable from connected and fallback sources.")

    econ = v424_economic_calendar()
    earnings = v424_earnings_today()
    news = v424_market_news()

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            st.caption(f"Source: {safe_text(econ.get('source'), 'Unknown')}")
            events = (econ.get("today") or []) or (econ.get("next") or [])
            if events:
                for e in events[:5]:
                    if "v4253_render_event_line" in globals():
                        st.markdown(f"• {v4253_render_event_line(e)}")
                    else:
                        st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
            else:
                st.warning("No economic calendar data returned. Configure FMP or rely on official BLS/Fed/BEA fallback.")

    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            st.caption("Source priority: FMP → Finnhub → Nasdaq → Alpha Vantage → Yahoo")
            if earnings:
                edf = pd.DataFrame(earnings)
                preferred = [c for c in ["Company", "Ticker", "Symbol", "Date", "Time", "EPS Est", "Revenue Est", "Source"] if c in edf.columns]
                st.dataframe(edf[preferred] if preferred else edf, use_container_width=True, hide_index=True)
            else:
                st.warning("No earnings returned from any connected/fallback source today.")

    with st.container(border=True):
        st.markdown("### 📰 Market News")
        if news:
            for h in news[:5]:
                st.markdown(f"• {safe_text(h)}")
        else:
            st.warning("No broad market headlines returned. Add NEWSAPI_KEY and FINNHUB_API_KEY for paid-client quality news.")
    if "v426_source_health_card" in globals():
        v426_source_health_card()




# =========================
# V43 PROFESSIONAL INTELLIGENCE PLATFORM
# =========================

def v43_num(value, default=0.0):
    try:
        if value in (None, "", "N/A", "None"):
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return default


def v43_money(value):
    try:
        return fmt_money(value)
    except Exception:
        x = v43_num(value, 0)
        return "N/A" if not x else f"${x:,.2f}"


def v43_pct(value):
    x = v43_num(value, None)
    return "N/A" if x is None else f"{x:.1f}%"


def v43_business_quality(row):
    """
    Business Quality Agent for paid-client credibility.
    Uses available row fields first; falls back conservatively when missing.
    """
    sector = safe_text(row.get("Sector"), "")
    ticker = safe_text(row.get("Ticker"), "")
    pe = v43_num(row.get("PE Ratio") or row.get("P/E") or row.get("Trailing PE") or row.get("Forward PE"), None)
    fpe = v43_num(row.get("Forward PE"), None)
    rev_growth = v43_num(row.get("Revenue Growth") or row.get("Revenue Growth %"), None)
    eps_growth = v43_num(row.get("EPS Growth") or row.get("Earnings Growth %"), None)
    fcf = v43_num(row.get("Free Cash Flow") or row.get("FCF"), None)
    net_income = v43_num(row.get("Net Income"), None)
    debt_equity = v43_num(row.get("Debt/Equity") or row.get("Debt To Equity"), None)
    margin = v43_num(row.get("Operating Margin") or row.get("Profit Margin") or row.get("Net Margin"), None)
    price = v43_num(row.get("Price"), 0)
    analyst_count = int(v43_num(row.get("Analyst Count"), 0))
    market_cap = v43_num(row.get("Market Cap"), 0)

    score = 70
    flags = []
    positives = []

    # Profitability / valuation
    if pe is not None:
        if pe < 0:
            score -= 25
            flags.append(f"Negative P/E ({pe:.1f}) suggests the company is currently unprofitable.")
        elif pe > 80:
            score -= 8
            flags.append(f"Very high P/E ({pe:.1f}) raises valuation risk.")
        elif 0 < pe <= 35:
            score += 8
            positives.append(f"P/E of {pe:.1f} is within a more reasonable range.")
    elif fpe is not None:
        if fpe < 0:
            score -= 18
            flags.append(f"Negative forward P/E ({fpe:.1f}) suggests expected losses.")
        elif fpe <= 35:
            score += 5
            positives.append(f"Forward P/E of {fpe:.1f} is reasonable.")
    else:
        flags.append("Profitability valuation metric was not available.")

    if net_income is not None:
        if net_income < 0:
            score -= 15
            flags.append("Net income is negative.")
        else:
            score += 8
            positives.append("Net income is positive.")

    if fcf is not None:
        if fcf < 0:
            score -= 15
            flags.append("Free cash flow is negative.")
        else:
            score += 10
            positives.append("Free cash flow is positive.")

    if eps_growth is not None:
        if eps_growth < 0:
            score -= 8
            flags.append("EPS growth is negative.")
        elif eps_growth > 10:
            score += 6
            positives.append(f"EPS growth is positive ({eps_growth:.1f}%).")

    if rev_growth is not None:
        if rev_growth > 20:
            score += 8
            positives.append(f"Revenue growth is strong ({rev_growth:.1f}%).")
        elif rev_growth < 0:
            score -= 8
            flags.append("Revenue growth is negative.")

    if margin is not None:
        if margin < 0:
            score -= 10
            flags.append("Margins are negative.")
        elif margin > 15:
            score += 6
            positives.append("Margins appear healthy.")

    if debt_equity is not None:
        if debt_equity > 2:
            score -= 8
            flags.append("Debt load appears elevated.")
        elif 0 <= debt_equity < 1:
            score += 4
            positives.append("Debt load appears manageable.")

    # Coverage and size confidence
    if analyst_count >= 20:
        score += 4
        positives.append(f"Strong analyst coverage ({analyst_count} analysts).")
    elif analyst_count and analyst_count < 5:
        score -= 4
        flags.append("Limited analyst coverage.")

    # Sector-specific speculative treatment
    speculative_keywords = ["biotech", "biotechnology", "therapeutics", "pharma", "pharmaceutical"]
    if any(k in (sector + " " + ticker).lower() for k in speculative_keywords):
        if pe is not None and pe < 0:
            score -= 10
            flags.append("Biotech/therapeutics with losses should be treated as speculative.")
        elif price < 10:
            score -= 8
            flags.append("Low-priced healthcare/biotech name carries speculative risk.")

    score = max(0, min(100, round(score)))

    if score >= 85:
        quality = "🏆 Quality Compounder"
    elif score >= 70:
        quality = "📈 Growth Leader"
    elif score >= 55:
        quality = "🔄 Recovery / Mixed Quality"
    else:
        quality = "⚠️ Speculative"

    if not positives:
        positives = ["Some business-quality data was unavailable or mixed."]
    if not flags:
        flags = ["No major business-quality red flag from available fields."]

    return {
        "score": score,
        "tier": quality,
        "positives": positives[:4],
        "flags": flags[:5],
        "pe": pe,
        "fcf": fcf,
        "net_income": net_income,
    }


def v43_valuation_confidence(row):
    price = v43_num(row.get("Price"), 0)
    analyst = v43_num(row.get("Analyst Target"), 0)
    ai = v43_num(row.get("AI Fair Value"), 0)
    bull = v43_num(row.get("Bull Case"), 0)
    bear = v43_num(row.get("Bear Case"), 0)

    if not price:
        return {
            "confidence": "Low",
            "gap": None,
            "conservative": analyst or ai,
            "base": analyst or ai,
            "aggressive": ai or bull,
            "note": "Price data unavailable."
        }

    conservative = analyst if analyst else (price * 1.15)
    base = conservative
    aggressive = ai if ai else (bull if bull else conservative)

    gap = None
    confidence = "Medium"
    note = "AI fair value is reasonably aligned with available target data."

    if analyst and ai:
        gap = ((ai - analyst) / analyst) * 100
        if gap > 75:
            confidence = "Low"
            # Bring base case down to avoid showing unrealistic value as the primary target.
            base = analyst * 1.25
            note = "AI fair value is far above analyst consensus; treat AI value as aggressive scenario, not base case."
        elif gap > 50:
            confidence = "Low-Medium"
            base = analyst * 1.15
            note = "AI fair value is materially above analyst consensus; confidence is reduced."
        elif gap > 20:
            confidence = "Medium"
            base = (analyst + ai) / 2
            note = "AI fair value is above analyst consensus but not extreme."
        else:
            confidence = "High"
            base = (analyst + ai) / 2
            note = "AI fair value is close to analyst consensus."

    if bear and bear < conservative:
        conservative = max(bear, price * 0.9)

    return {
        "confidence": confidence,
        "gap": gap,
        "conservative": conservative,
        "base": base,
        "aggressive": aggressive,
        "note": note,
    }


def v43_rebalanced_score(row):
    """
    Rebalanced paid-client score to reduce compression.
    Combines existing conviction with quality, valuation confidence, technical risk, news, and analyst support.
    """
    existing = v43_num(row.get("Final Conviction"), 0)
    quality = v43_business_quality(row)
    valuation = v43_valuation_confidence(row)
    analyst_support = safe_text(row.get("Analyst Support"), "")
    news = safe_text(row.get("News Sentiment"), "")
    rsi = v43_num(row.get("RSI"), 0)
    vol = v43_num(row.get("Volume Ratio"), 0)
    atr = v43_num(row.get("ATR %"), 0)
    upside = v43_num(row.get("Target Upside %"), 0)

    # Normalize components
    tech = 75
    if 50 <= rsi < 70:
        tech += 8
    elif rsi >= 70:
        tech -= 8
    elif rsi and rsi < 40:
        tech -= 10
    if vol and vol < 0.75:
        tech -= 8
    elif vol >= 1.25:
        tech += 5
    if atr >= 8:
        tech -= 10
    elif atr >= 5:
        tech -= 5
    tech = max(0, min(100, tech))

    analyst = 60
    if "Bullish" in analyst_support:
        analyst = 82
    elif "Constructive" in analyst_support:
        analyst = 68
    elif "Weak" in analyst_support:
        analyst = 45

    news_score = 55
    if "Positive" in news:
        news_score = 75
    elif "Negative" in news:
        news_score = 35
    elif "Neutral" in news:
        news_score = 50

    valuation_score = 75
    if valuation["confidence"] == "High":
        valuation_score = 85
    elif valuation["confidence"] == "Medium":
        valuation_score = 72
    elif valuation["confidence"] == "Low-Medium":
        valuation_score = 62
    elif valuation["confidence"] == "Low":
        valuation_score = 50

    if upside > 150:
        valuation_score -= 8  # giant upside is attractive but less reliable
    elif 20 <= upside <= 80:
        valuation_score += 5

    # Weighted
    raw = (
        quality["score"] * 0.25 +
        tech * 0.20 +
        analyst * 0.15 +
        valuation_score * 0.20 +
        news_score * 0.10 +
        existing * 0.10
    )

    # Spread out scores so everything is not 96/97.
    adjusted = 50 + (raw - 50) * 0.88

    # Additional credibility penalties
    if "Speculative" in quality["tier"]:
        adjusted -= 8
    if valuation["confidence"] == "Low":
        adjusted -= 5
    if vol and vol < 0.75:
        adjusted -= 2

    adjusted = max(0, min(99, round(adjusted, 1)))
    return adjusted


def v43_setup_label(score, tier):
    if "Speculative" in tier:
        if score >= 80:
            return "⚠️ Speculative High-Upside"
        return "⚠️ Speculative"
    if score >= 92:
        return "🟢 Elite Quality Setup"
    if score >= 86:
        return "🟢 Strong Setup"
    if score >= 78:
        return "🟡 Actionable Watch"
    if score >= 70:
        return "🟡 Watchlist"
    return "⚪ Low Priority"


def v43_decision(row):
    quality = v43_business_quality(row)
    valuation = v43_valuation_confidence(row)
    score = v43_rebalanced_score(row)
    label = v43_setup_label(score, quality["tier"])

    price = v43_num(row.get("Price"), 0)
    support = v43_num(row.get("Support 1"), 0)
    resistance = v43_num(row.get("Resistance 1"), 0)
    vol = v43_num(row.get("Volume Ratio"), 0)
    atr = v43_num(row.get("ATR %"), 0)

    decision = "WATCH"
    rationale = "Monitor for a cleaner entry."
    if "Speculative" in quality["tier"]:
        decision = "SPECULATIVE"
        rationale = "Higher-risk idea. Use smaller size and require stronger confirmation."
    elif score >= 90 and valuation["confidence"] in {"High", "Medium"}:
        decision = "ACTIONABLE WATCH"
        rationale = "High-quality setup, but entry timing still matters."
    elif score >= 82:
        decision = "WATCH"
        rationale = "Good setup, but confirm entry and risk."
    elif score < 70:
        decision = "LOW PRIORITY"
        rationale = "Not enough quality-adjusted confirmation."

    if price and support and resistance and price > support:
        rr = (resistance - price) / (price - support) if (price - support) > 0 else 0
        if rr < 1:
            decision = "WAIT"
            rationale = f"Reward/risk is weak. Prefer pullback near {v43_money(support)} or breakout above {v43_money(resistance)} with volume."

    if vol and vol < 0.75:
        rationale += " Volume is light."
    if atr >= 5:
        rationale += " Volatility is elevated."

    return {
        "score": score,
        "label": label,
        "decision": decision,
        "rationale": rationale,
        "quality": quality,
        "valuation": valuation,
    }


def render_v43_decision_card(row):
    d = v43_decision(row)
    q = d["quality"]
    v = d["valuation"]
    ticker = safe_text(row.get("Ticker"), "")
    company = safe_text(row.get("Company"), "")
    sector = safe_text(row.get("Sector"), "")

    with st.container(border=True):
        st.markdown(f"## {ticker}{(' — ' + company) if company else ''}")
        st.markdown(f"### {d['label']} · {d['decision']}")
        st.info(d["rationale"])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("V43 Score", f"{d['score']:.1f}/100")
        c2.metric("Tier", q["tier"])
        c3.metric("Valuation Confidence", v["confidence"])
        c4.metric("Sector", sector if sector else "N/A")

        st.markdown("**Why it can work**")
        cols = st.columns(2)
        with cols[0]:
            for p in q["positives"][:4]:
                st.markdown(f"✓ {safe_text(p)}")
        with cols[1]:
            analyst = v43_num(row.get("Analyst Target"), 0)
            price = v43_num(row.get("Price"), 0)
            if analyst and price:
                st.markdown(f"✓ Analyst target implies {((analyst-price)/price)*100:.1f}% upside.")
            st.markdown(f"✓ Existing AI conviction: {v43_num(row.get('Final Conviction'), 0):.0f}/100.")

        st.markdown("**What could go wrong**")
        for flag in q["flags"][:5]:
            st.markdown(f"⚠️ {safe_text(flag)}")
        if v["gap"] is not None and v["gap"] > 50:
            st.markdown(f"⚠️ AI fair value is {v['gap']:.1f}% above analyst consensus, so aggressive target confidence is lower.")


def render_v43_targets_card(row):
    v = v43_valuation_confidence(row)
    price = v43_num(row.get("Price"), 0)
    stop = v43_num(row.get("Stop Loss"), 0)
    support = v43_num(row.get("Support 1"), 0)
    resistance = v43_num(row.get("Resistance 1"), 0)
    entry = safe_text(row.get("Entry Range"), "")

    with st.container(border=True):
        st.markdown("### 🎯 Targets & Entry Plan")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Conservative", v43_money(v["conservative"]))
        c2.metric("Base", v43_money(v["base"]))
        c3.metric("Aggressive", v43_money(v["aggressive"]))
        c4.metric("Stop", v43_money(stop) if stop else "N/A")
        st.caption(v["note"])

        c5, c6, c7 = st.columns(3)
        c5.metric("Entry Zone", entry if entry and entry != "N/A" else "Wait")
        c6.metric("Support", v43_money(support) if support else "N/A")
        c7.metric("Resistance", v43_money(resistance) if resistance else "N/A")

        if price and support and resistance and price > support:
            rr = (resistance - price) / (price - support) if (price - support) > 0 else 0
            if rr < 1:
                st.warning(f"Entry quality is weak at current price: reward/risk is only {rr:.2f}:1.")
            else:
                st.success(f"Entry quality is acceptable if support holds: reward/risk is {rr:.2f}:1.")


def render_v43_business_quality_agent(row):
    q = v43_business_quality(row)
    with st.container(border=True):
        st.markdown("### 🧱 Business Quality Agent")
        c1, c2, c3 = st.columns(3)
        c1.metric("Business Quality", f"{q['score']}/100")
        c2.metric("Tier", q["tier"])
        c3.metric("P/E", "N/A" if q["pe"] is None else f"{q['pe']:.1f}")

        st.markdown("**Strengths**")
        for p in q["positives"]:
            st.markdown(f"✓ {safe_text(p)}")
        st.markdown("**Quality risks**")
        for f in q["flags"]:
            st.markdown(f"⚠️ {safe_text(f)}")


def render_v43_agent_summary(row):
    committee = row.get("AI Committee")
    if not isinstance(committee, dict) or not committee:
        return

    rows = []
    for name, agent in committee.items():
        if not isinstance(agent, dict):
            continue
        status = safe_text(agent.get("status"), "N/A")
        findings = agent.get("findings") or []
        risks = agent.get("risks") or []
        if not isinstance(findings, list):
            findings = []
        if not isinstance(risks, list):
            risks = []
        readiness = "Data-backed"
        if "not connected" in status.lower() or "framework" in status.lower() or not findings:
            readiness = "Beta / Limited"
        rows.append({
            "Agent": safe_text(name),
            "Score": "N/A" if agent.get("score") is None else f"{int(v43_num(agent.get('score'), 0))}",
            "Status": status,
            "Readiness": readiness,
            "Main Takeaway": safe_text(agent.get("bottom_line") or (findings[0] if findings else "No detailed data yet"))[:150],
        })

    with st.container(border=True):
        st.markdown("### 🤖 Agent Summary")
        st.caption("Paid-client view: real data first; beta/framework agents are labeled clearly.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_v43_professional_research_card(row):
    render_v43_decision_card(row)
    render_v43_targets_card(row)
    render_v43_business_quality_agent(row)
    render_v43_agent_summary(row)


def v43_market_regime():
    quotes = v424_market_quotes() if "v424_market_quotes" in globals() else []
    qmap = {safe_text(q.get("symbol")): q for q in quotes if isinstance(q, dict)}
    spy = v43_num(qmap.get("SPY", {}).get("change_pct"), 0)
    qqq = v43_num(qmap.get("QQQ", {}).get("change_pct"), 0)
    iwm = v43_num(qmap.get("IWM", {}).get("change_pct"), 0)
    vix = v43_num(qmap.get("VIX", {}).get("price"), 0)
    score = 50
    if spy > 0: score += 12
    if qqq > 0: score += 12
    if iwm > 0: score += 8
    if vix and vix < 18: score += 12
    if vix and vix > 22: score -= 15
    if score >= 70:
        return "🟢 Risk On", score
    if score >= 45:
        return "🟡 Neutral", score
    return "🔴 Risk Off", score


def render_v424_market_command_center():
    st.markdown("## 🧭 Market Command Center")
    regime, regime_score = v43_market_regime()
    st.metric("Market Regime", regime, f"{regime_score:.0f}/100")

    quotes = v424_market_quotes()
    if quotes:
        cols = st.columns(min(5, len(quotes)))
        for i, q in enumerate(quotes[:5]):
            pct = v424_float(q.get("change_pct"), None) if "v424_float" in globals() else v43_num(q.get("change_pct"), None)
            delta = f"{pct:+.2f}%" if pct is not None else None
            label = q.get("display_label") or q.get("symbol", "")
            cols[i].metric(label, v43_money(q.get("price")), delta)
            cols[i].caption(safe_text(q.get("source"), ""))
    else:
        st.warning("Market quotes unavailable from connected and fallback sources.")

    econ = v424_economic_calendar()
    earnings = v424_earnings_today()
    news = v424_market_news()

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            st.caption(f"Source: {safe_text(econ.get('source'), 'Unknown')}")
            events = (econ.get("today") or []) or (econ.get("next") or [])
            if events:
                for e in events[:5]:
                    if "v4253_render_event_line" in globals():
                        st.markdown(f"• {v4253_render_event_line(e)}")
                    else:
                        st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
            else:
                st.warning("No economic calendar data returned.")

    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            st.caption("Source priority: FMP → Finnhub → Nasdaq → Alpha Vantage → Yahoo")
            if earnings:
                edf = pd.DataFrame(earnings)
                preferred = [c for c in ["Company", "Ticker", "Symbol", "Date", "Time", "EPS Est", "Revenue Est", "Source"] if c in edf.columns]
                st.dataframe(edf[preferred] if preferred else edf, use_container_width=True, hide_index=True)
            else:
                st.warning("No earnings returned from any connected/fallback source today.")

    with st.container(border=True):
        st.markdown("### 📰 Market News")
        if news:
            for h in news[:5]:
                st.markdown(f"• {safe_text(h)}")
        else:
            st.warning("No broad market headlines returned. Add NEWSAPI_KEY and FINNHUB_API_KEY for paid-client quality news.")

    if "v426_source_health_card" in globals():
        v426_source_health_card()




# =========================
# V43.1 CLEAN WIRING + PAID LAYOUT FIX
# =========================

def v431_get_score(row):
    """
    Use V43 score everywhere when present; otherwise compute live from row.
    """
    existing = v43_num(row.get("V43 Score"), None) if "v43_num" in globals() else safe_number(row.get("V43 Score"), None)
    if existing is not None and existing > 0:
        return existing
    if "v43_rebalanced_score" in globals():
        return v43_rebalanced_score(row)
    return safe_number(row.get("Final Conviction"), 0)


def v431_get_quality(row):
    if "v43_business_quality" in globals():
        return v43_business_quality(row)
    return {"score": 0, "tier": "N/A", "positives": [], "flags": []}


def v431_smart_levels(row):
    """
    One single support/resistance source for all V43.1 paid sections.
    Uses scanner fields, then V42.4.4 Yahoo fallback if available.
    """
    if "v4244_get_smart_levels" in globals():
        try:
            return v4244_get_smart_levels(row)
        except Exception:
            pass
    return {
        "price": safe_number(row.get("Price"), 0),
        "support1": safe_number(row.get("Support 1"), 0),
        "support2": safe_number(row.get("Support 2"), 0),
        "resistance1": safe_number(row.get("Resistance 1"), 0),
        "resistance2": safe_number(row.get("Resistance 2"), 0),
        "breakout": safe_number(row.get("Breakout Level"), 0),
        "source": "Scanner support/resistance",
    }


def v431_setup_label(row):
    score = v431_get_score(row)
    q = v431_get_quality(row)
    tier = q.get("tier", "")
    if "Speculative" in tier:
        return "⚠️ Speculative High-Upside" if score >= 78 else "⚠️ Speculative"
    if score >= 90:
        return "🟢 Elite Quality Setup"
    if score >= 84:
        return "🟢 Strong Setup"
    if score >= 76:
        return "🟡 Actionable Watch"
    if score >= 68:
        return "🟡 Watchlist"
    return "⚪ Low Priority"


def v431_decision(row):
    q = v431_get_quality(row)
    val = v43_valuation_confidence(row) if "v43_valuation_confidence" in globals() else {"confidence": "Medium", "gap": None, "note": ""}
    levels = v431_smart_levels(row)
    score = v431_get_score(row)
    price = safe_number(levels.get("price") or row.get("Price"), 0)
    support = safe_number(levels.get("support1"), 0)
    resistance = safe_number(levels.get("resistance1"), 0)
    vol = safe_number(row.get("Volume Ratio"), 0)
    atr = safe_number(row.get("ATR %"), 0)

    decision = "WATCH"
    why = "Setup is worth monitoring, but entry quality and data confidence still matter."

    if "Speculative" in q.get("tier", ""):
        decision = "SPECULATIVE"
        why = "Higher-risk idea. Use smaller position sizing and require stronger confirmation."
    elif score >= 88 and val.get("confidence") in {"High", "Medium"}:
        decision = "ACTIONABLE WATCH"
        why = "Quality-adjusted score is strong, but still confirm entry and risk."
    elif score < 68:
        decision = "LOW PRIORITY"
        why = "Not enough quality-adjusted confirmation for a premium recommendation."

    if price and support and resistance and price > support:
        rr = (resistance - price) / (price - support) if (price - support) > 0 else 0
        if rr < 1:
            decision = "WAIT"
            why = f"Reward/risk is weak. Prefer pullback near {v43_money(support)} or breakout above {v43_money(resistance)} with volume."
    elif not support or not resistance:
        why += " Support/resistance needs live/fallback confirmation."

    if vol and vol < 0.75:
        why += " Volume is light."
    if atr >= 5:
        why += " Volatility is elevated."

    return {"decision": decision, "why": why, "score": score, "quality": q, "valuation": val, "levels": levels}


def render_v431_decision_card(row):
    d = v431_decision(row)
    q = d["quality"]
    v = d["valuation"]
    levels = d["levels"]
    ticker = safe_text(row.get("Ticker"), "")
    company = safe_text(row.get("Company"), "")
    sector = safe_text(row.get("Sector"), "")

    with st.container(border=True):
        st.markdown(f"## {ticker}{(' — ' + company) if company else ''}")
        st.markdown(f"### {v431_setup_label(row)} · {d['decision']}")
        st.info(d["why"])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("V43 Score", f"{d['score']:.1f}/100")
        c2.metric("Tier", q.get("tier", "N/A"))
        c3.metric("Valuation Confidence", v.get("confidence", "N/A"))
        c4.metric("Sector", sector if sector else "N/A")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Price", v43_money(levels.get("price") or row.get("Price")))
        c6.metric("Support", v43_money(levels.get("support1")) if safe_number(levels.get("support1"), 0) else "N/A")
        c7.metric("Resistance", v43_money(levels.get("resistance1")) if safe_number(levels.get("resistance1"), 0) else "N/A")
        c8.metric("Level Source", safe_text(levels.get("source"), "N/A")[:18])

        left, right = st.columns(2)
        with left:
            st.markdown("**Why it can work**")
            for p in q.get("positives", [])[:4]:
                st.markdown(f"✓ {safe_text(p)}")
            analyst = safe_number(row.get("Analyst Target"), 0)
            price = safe_number(row.get("Price"), 0)
            if analyst and price:
                st.markdown(f"✓ Analyst target implies {((analyst-price)/price)*100:.1f}% upside.")
        with right:
            st.markdown("**What could go wrong**")
            flags = q.get("flags", [])[:4] if q else []
            if v.get("gap") is not None and v.get("gap") > 50:
                flags.append(f"AI fair value is {v['gap']:.1f}% above analyst consensus; aggressive target confidence is lower.")
            if not flags:
                flags = ["Normal market, earnings, liquidity, and execution risk still applies."]
            for f in flags[:5]:
                st.markdown(f"⚠️ {safe_text(f)}")


def render_v431_targets_card(row):
    val = v43_valuation_confidence(row) if "v43_valuation_confidence" in globals() else {}
    levels = v431_smart_levels(row)
    stop = safe_number(row.get("Stop Loss"), 0)
    entry = safe_text(row.get("Entry Range"), "")

    with st.container(border=True):
        st.markdown("### 🎯 Targets & Entry Plan")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Conservative", v43_money(val.get("conservative")) if val else "N/A")
        c2.metric("Base", v43_money(val.get("base")) if val else "N/A")
        c3.metric("Aggressive", v43_money(val.get("aggressive")) if val else "N/A")
        c4.metric("Stop", v43_money(stop) if stop else "N/A")
        if val.get("note"):
            st.caption(val.get("note"))

        c5, c6, c7 = st.columns(3)
        c5.metric("Entry Zone", entry if entry and entry != "N/A" else "Wait")
        c6.metric("Support", v43_money(levels.get("support1")) if safe_number(levels.get("support1"), 0) else "N/A")
        c7.metric("Breakout", v43_money(levels.get("breakout") or levels.get("resistance1")) if safe_number(levels.get("breakout") or levels.get("resistance1"), 0) else "N/A")

        price = safe_number(levels.get("price"), 0)
        support = safe_number(levels.get("support1"), 0)
        resistance = safe_number(levels.get("resistance1"), 0)
        if price and support and resistance and price > support:
            rr = (resistance - price) / (price - support) if (price - support) > 0 else 0
            if rr < 1:
                st.warning(f"Entry quality is weak at current price: reward/risk is only {rr:.2f}:1.")
            else:
                st.success(f"Entry quality is acceptable if support holds: reward/risk is {rr:.2f}:1.")
        else:
            st.warning("Support/resistance could not be confirmed for the entry-quality calculation.")


def render_v431_business_quality_agent(row):
    q = v431_get_quality(row)
    with st.container(border=True):
        st.markdown("### 🧱 Business Quality Agent")
        c1, c2, c3 = st.columns(3)
        c1.metric("Business Quality", f"{q.get('score', 0)}/100")
        c2.metric("Tier", q.get("tier", "N/A"))
        pe = q.get("pe")
        c3.metric("P/E", "N/A" if pe is None else f"{pe:.1f}")
        st.markdown("**Strengths**")
        for p in q.get("positives", ["No quality strengths returned."])[:4]:
            st.markdown(f"✓ {safe_text(p)}")
        st.markdown("**Quality risks / limits**")
        for f in q.get("flags", ["No major quality red flag returned."])[:5]:
            st.markdown(f"⚠️ {safe_text(f)}")


def render_v431_agent_summary(row):
    committee = row.get("AI Committee")
    if not isinstance(committee, dict) or not committee:
        return
    rows = []
    for name, agent in committee.items():
        if not isinstance(agent, dict):
            continue
        status = safe_text(agent.get("status"), "N/A")
        findings = agent.get("findings") or []
        risks = agent.get("risks") or []
        if not isinstance(findings, list):
            findings = []
        if not isinstance(risks, list):
            risks = []
        readiness = "Data-backed"
        if "not connected" in status.lower() or "framework" in status.lower() or "deferred" in status.lower() or not findings:
            readiness = "Deferred / Beta"
        rows.append({
            "Agent": safe_text(name),
            "Score": "N/A" if agent.get("score") is None else f"{int(safe_number(agent.get('score'), 0))}",
            "Readiness": readiness,
            "Status": status,
            "Main Takeaway": safe_text(agent.get("bottom_line") or (findings[0] if findings else "Deferred to live research"))[:150],
        })
    with st.container(border=True):
        st.markdown("### 🤖 Agent Summary")
        st.caption("Deferred/Beta agents are not treated as primary buy signals.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_v431_professional_research_card(row):
    render_v431_decision_card(row)
    render_v431_targets_card(row)
    render_v431_business_quality_agent(row)
    render_v431_agent_summary(row)


def render_v431_advanced_legacy_sections(row):
    """
    Keeps legacy details available without confusing paid users.
    """
    with st.expander("Advanced details / legacy V42 sections", expanded=False):
        st.caption("These sections are retained for audit/debug context and will be simplified in future releases.")
        try:
            if "render_v424_analyst_ratings_box" in globals():
                render_v424_analyst_ratings_box(row)
            if "render_v424_support_resistance_box" in globals():
                render_v424_support_resistance_box(row)
            if "render_v4243_technical_translation_box" in globals():
                render_v4243_technical_translation_box(row)
            if "render_inline_metric_summary" in globals():
                render_inline_metric_summary(row)
            if "render_v4251_standardized_committee" in globals():
                render_v4251_standardized_committee(row)
        except Exception as e:
            st.caption(f"Advanced detail rendering skipped: {e}")


def render_detail(row):
    """
    V43.1 full override: one paid-client research card first, legacy content collapsed.
    This prevents old Elite 97 card and V42/V41 text from appearing above the V43 verdict.
    """
    render_v431_professional_research_card(row)

    if "render_detail_chart_v4184" in globals():
        try:
            render_detail_chart_v4184(row)
        except Exception:
            pass

    render_v431_advanced_legacy_sections(row)

    with st.expander("Raw row data", expanded=False):
        try:
            st.json(row if isinstance(row, dict) else dict(row))
        except Exception:
            st.write(row)


def v431_prepare_display_df(df):
    """
    For ranked tables: show V43 score/rating first and prevent old Final Conviction from dominating.
    """
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    try:
        # Compute columns if missing
        if "V43 Score" not in out.columns:
            out["V43 Score"] = out.apply(lambda r: v431_get_score(r), axis=1)
        if "Quality Tier" not in out.columns:
            out["Quality Tier"] = out.apply(lambda r: v431_get_quality(r).get("tier", "N/A"), axis=1)
        out["V43 Rating"] = out.apply(lambda r: v431_setup_label(r), axis=1)
        if "Final Conviction" in out.columns:
            out["Legacy Score"] = out["Final Conviction"]
        out = out.sort_values("V43 Score", ascending=False)
    except Exception:
        pass
    return out




# =========================
# V43.2 DATA INTELLIGENCE + PAID CLIENT UX
# =========================

def v432_env_value(*names):
    for n in names:
        val = (globals().get(n) or os.getenv(n) or "").strip()
        if val:
            return val
    return ""


def v432_env_status():
    keys = {
        "APP_PASSWORD": v432_env_value("APP_PASSWORD"),
        "GUEST_PASSWORD": v432_env_value("GUEST_PASSWORD"),
        "FMP_API_KEY": v432_env_value("FMP_API_KEY"),
        "FINNHUB_API_KEY": v432_env_value("FINNHUB_API_KEY", "FINNHUB_TOKEN"),
        "NEWSAPI_KEY": v432_env_value("NEWSAPI_KEY", "NEWS_API_KEY"),
        "ALPHA_VANTAGE_API_KEY": v432_env_value("ALPHA_VANTAGE_API_KEY", "ALPHAVANTAGE_API_KEY"),
        "SEC_USER_AGENT": v432_env_value("SEC_USER_AGENT"),
        "GITHUB_TOKEN": v432_env_value("GITHUB_TOKEN"),
        "GITHUB_REPO_URL": v432_env_value("GITHUB_REPO_URL"),
    }
    return {k: {"configured": bool(v), "length": len(v)} for k, v in keys.items()}


def v432_http_json(url, params=None, headers=None, timeout=8):
    try:
        r = requests.get(url, params=params or {}, headers=headers or {"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if r.status_code == 200:
            return r.json(), r.status_code
        return None, r.status_code
    except Exception:
        return None, None


def v432_http_text(url, params=None, headers=None, timeout=8):
    try:
        r = requests.get(url, params=params or {}, headers=headers or {"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if r.status_code == 200:
            return r.text, r.status_code
        return None, r.status_code
    except Exception:
        return None, None


@st.cache_data(ttl=900)
def v432_market_news_items():
    rows = []
    diagnostics = []

    news_key = v432_env_value("NEWSAPI_KEY", "NEWS_API_KEY")
    if news_key:
        data, status = v432_http_json(
            "https://newsapi.org/v2/top-headlines",
            params={"category": "business", "language": "en", "pageSize": 8, "apiKey": news_key},
        )
        diagnostics.append(f"NewsAPI status={status}")
        if isinstance(data, dict):
            for a in data.get("articles", [])[:8]:
                title = safe_text(a.get("title"), "")
                if title:
                    rows.append({
                        "headline": title,
                        "source": safe_text((a.get("source") or {}).get("name"), "NewsAPI"),
                        "url": safe_text(a.get("url"), ""),
                        "published": safe_text(a.get("publishedAt"), ""),
                        "provider": "NewsAPI",
                    })
    else:
        diagnostics.append("NewsAPI missing")

    finnhub_key = v432_env_value("FINNHUB_API_KEY", "FINNHUB_TOKEN")
    if not rows and finnhub_key:
        data, status = v432_http_json(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": finnhub_key},
        )
        diagnostics.append(f"Finnhub news status={status}")
        if isinstance(data, list):
            for a in data[:8]:
                title = safe_text(a.get("headline"), "")
                if title:
                    rows.append({
                        "headline": title,
                        "source": safe_text(a.get("source"), "Finnhub"),
                        "url": safe_text(a.get("url"), ""),
                        "published": safe_text(a.get("datetime"), ""),
                        "provider": "Finnhub",
                    })
    elif not finnhub_key:
        diagnostics.append("Finnhub missing")

    rss_sources = [
        ("Yahoo Finance RSS", "https://finance.yahoo.com/news/rssindex"),
        ("CNBC Business RSS", "https://www.cnbc.com/id/10001147/device/rss/rss.html"),
        ("MarketWatch RSS", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ]
    if not rows:
        for provider, url in rss_sources:
            text, status = v432_http_text(url, timeout=8)
            diagnostics.append(f"{provider} status={status}")
            if not text:
                continue
            try:
                root = ET.fromstring(text.encode("utf-8"))
                for item in root.findall(".//item")[:8]:
                    title_node = item.find("title")
                    link_node = item.find("link")
                    pub_node = item.find("pubDate")
                    title = safe_text(title_node.text if title_node is not None else "", "")
                    if title:
                        rows.append({
                            "headline": title,
                            "source": provider,
                            "url": safe_text(link_node.text if link_node is not None else "", ""),
                            "published": safe_text(pub_node.text if pub_node is not None else "", ""),
                            "provider": provider,
                        })
                if rows:
                    break
            except Exception:
                continue

    return {"rows": rows[:8], "diagnostics": diagnostics}


def v432_market_news_summary():
    data = v432_market_news_items()
    rows = data.get("rows", [])
    diagnostics = data.get("diagnostics", [])
    if not rows:
        return {
            "status": "No headlines returned",
            "sentiment": "Unknown",
            "top": "No market headline source returned a usable headline.",
            "rows": [],
            "diagnostics": diagnostics,
        }

    joined = " ".join([r["headline"].lower() for r in rows])
    bullish_terms = ["rally", "surge", "gain", "beat", "optimism", "growth", "record", "upgrade", "strong"]
    bearish_terms = ["fall", "drop", "selloff", "recession", "inflation", "war", "tariff", "downgrade", "weak", "risk"]
    bull_count = sum(t in joined for t in bullish_terms)
    bear_count = sum(t in joined for t in bearish_terms)
    sentiment = "Mixed / Neutral"
    if bull_count > bear_count:
        sentiment = "Constructive"
    elif bear_count > bull_count:
        sentiment = "Cautious"
    return {"status": "Headlines available", "sentiment": sentiment, "top": rows[0]["headline"], "rows": rows, "diagnostics": diagnostics}


@st.cache_data(ttl=900)
def v432_company_news_items(ticker):
    ticker = safe_text(ticker, "").upper().strip()
    rows, diagnostics = [], []
    if not ticker:
        return {"rows": [], "diagnostics": ["ticker missing"]}

    finnhub_key = v432_env_value("FINNHUB_API_KEY", "FINNHUB_TOKEN")
    if finnhub_key:
        end = dt.datetime.utcnow().date()
        start = end - dt.timedelta(days=21)
        data, status = v432_http_json(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": ticker, "from": start.isoformat(), "to": end.isoformat(), "token": finnhub_key},
        )
        diagnostics.append(f"Finnhub company-news status={status}")
        if isinstance(data, list):
            for a in data[:8]:
                h = safe_text(a.get("headline"), "")
                if h:
                    rows.append({"headline": h, "source": safe_text(a.get("source"), "Finnhub"), "url": safe_text(a.get("url"), ""), "provider": "Finnhub company news"})

    news_key = v432_env_value("NEWSAPI_KEY", "NEWS_API_KEY")
    if not rows and news_key:
        data, status = v432_http_json(
            "https://newsapi.org/v2/everything",
            params={"q": ticker, "language": "en", "sortBy": "publishedAt", "pageSize": 8, "apiKey": news_key},
        )
        diagnostics.append(f"NewsAPI company status={status}")
        if isinstance(data, dict):
            for a in data.get("articles", [])[:8]:
                h = safe_text(a.get("title"), "")
                if h:
                    rows.append({"headline": h, "source": safe_text((a.get("source") or {}).get("name"), "NewsAPI"), "url": safe_text(a.get("url"), ""), "provider": "NewsAPI company search"})

    if not rows:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(ticker)}&region=US&lang=en-US"
        text, status = v432_http_text(url, timeout=8)
        diagnostics.append(f"Yahoo company RSS status={status}")
        if text:
            try:
                root = ET.fromstring(text.encode("utf-8"))
                for item in root.findall(".//item")[:8]:
                    title_node = item.find("title")
                    link_node = item.find("link")
                    h = safe_text(title_node.text if title_node is not None else "", "")
                    if h:
                        rows.append({"headline": h, "source": "Yahoo Finance RSS", "url": safe_text(link_node.text if link_node is not None else "", ""), "provider": "Yahoo Finance RSS"})
            except Exception:
                pass

    return {"rows": rows[:8], "diagnostics": diagnostics}


def v432_news_intelligence(ticker):
    data = v432_company_news_items(ticker)
    rows = data.get("rows", [])
    diagnostics = data.get("diagnostics", [])
    if not rows:
        return {"score": 45, "status": "Insufficient data", "summary": "No recent company headlines returned from connected/fallback sources.", "bullish": [], "bearish": ["News confidence is low because no source returned usable company headlines."], "rows": [], "diagnostics": diagnostics}
    bullish_terms = ["beat", "raise", "upgrade", "growth", "record", "profit", "partnership", "contract", "launch", "approval"]
    bearish_terms = ["miss", "cut", "downgrade", "lawsuit", "probe", "decline", "loss", "warning", "recall", "delay"]
    bull = [r["headline"] for r in rows if any(t in r["headline"].lower() for t in bullish_terms)]
    bear = [r["headline"] for r in rows if any(t in r["headline"].lower() for t in bearish_terms)]
    score = max(0, min(100, 55 + min(20, len(bull) * 5) - min(20, len(bear) * 5)))
    status = "Positive" if score >= 70 else ("Cautious" if score <= 45 else "Mixed")
    return {"score": score, "status": status, "summary": f"{len(rows)} recent company headlines reviewed from available sources.", "bullish": bull[:3] or ["No clear bullish catalyst isolated from headlines."], "bearish": bear[:3] or ["No clear bearish headline risk isolated."], "rows": rows, "diagnostics": diagnostics}


@st.cache_data(ttl=1800)
def v432_analyst_intelligence(ticker, price=0, analyst_target=0, analyst_count=0):
    ticker = safe_text(ticker, "").upper().strip()
    out = {"consensus": analyst_target, "high": 0, "low": 0, "count": int(safe_number(analyst_count, 0)), "upgrades": [], "downgrades": [], "firm_rows": [], "source_notes": [], "rating_trend": "Unknown"}
    if not ticker:
        return out

    if v432_env_value("FMP_API_KEY") and "v424_fmp_get" in globals():
        try:
            data = v424_fmp_get(f"price-target-consensus/{ticker}")
            out["source_notes"].append("FMP price-target-consensus tried")
            if isinstance(data, list) and data:
                d = data[0]
                out["consensus"] = safe_number(d.get("targetConsensus") or d.get("targetMean") or out["consensus"], out["consensus"])
                out["high"] = safe_number(d.get("targetHigh") or d.get("targetHighPrice"), out["high"])
                out["low"] = safe_number(d.get("targetLow") or d.get("targetLowPrice"), out["low"])
                out["count"] = int(safe_number(d.get("numberOfAnalysts") or d.get("analystCount"), out["count"]))
        except Exception as e:
            out["source_notes"].append(f"FMP consensus failed: {e}")

        try:
            data = v424_fmp_get(f"upgrades-downgrades/{ticker}")
            out["source_notes"].append("FMP upgrades-downgrades tried")
            if isinstance(data, list):
                for d in data[:12]:
                    firm = safe_text(d.get("gradingCompany") or d.get("firm") or d.get("analystCompany"), "Analyst firm")
                    new_grade = safe_text(d.get("newGrade") or d.get("rating") or "")
                    old_grade = safe_text(d.get("previousGrade") or "")
                    action = safe_text(d.get("action") or "")
                    row = {"firm": firm, "action": action or new_grade, "rating": new_grade, "previous": old_grade, "date": safe_text(d.get("publishedDate") or d.get("date"), ""), "source": "FMP upgrades/downgrades"}
                    txt = f"{action} {new_grade}".lower()
                    if "upgrade" in txt or "buy" in txt or "overweight" in txt:
                        out["upgrades"].append(row)
                    elif "downgrade" in txt or "sell" in txt or "underweight" in txt:
                        out["downgrades"].append(row)
                    out["firm_rows"].append(row)
        except Exception as e:
            out["source_notes"].append(f"FMP upgrades failed: {e}")

    finnhub_key = v432_env_value("FINNHUB_API_KEY", "FINNHUB_TOKEN")
    if finnhub_key:
        data, status = v432_http_json("https://finnhub.io/api/v1/stock/recommendation", params={"symbol": ticker, "token": finnhub_key})
        out["source_notes"].append(f"Finnhub recommendation status={status}")
        if isinstance(data, list) and data:
            d = data[0]
            strong_buy = int(safe_number(d.get("strongBuy"), 0))
            buy = int(safe_number(d.get("buy"), 0))
            hold = int(safe_number(d.get("hold"), 0))
            sell = int(safe_number(d.get("sell"), 0)) + int(safe_number(d.get("strongSell"), 0))
            out["rating_trend"] = "Bullish / positive recommendation mix" if strong_buy + buy > hold + sell else ("Bearish / negative recommendation mix" if sell > strong_buy + buy else "Mixed / hold-heavy recommendation mix")
            if not out["count"]:
                out["count"] = strong_buy + buy + hold + sell

    if not out["high"] and analyst_target:
        out["high"] = analyst_target * 1.15
    if not out["low"] and analyst_target:
        out["low"] = analyst_target * 0.85
    out["upside"] = ((out["consensus"] - price) / price) * 100 if price and out["consensus"] else None
    return out


def v432_business_quality(row):
    sector = safe_text(row.get("Sector"), "")
    pe = safe_number(row.get("PE Ratio") or row.get("P/E") or row.get("Trailing PE"), None)
    fpe = safe_number(row.get("Forward PE"), None)
    peg = safe_number(row.get("PEG Ratio") or row.get("PEG"), None)
    rev_growth = safe_number(row.get("Revenue Growth") or row.get("Revenue Growth %"), None)
    eps_growth = safe_number(row.get("EPS Growth") or row.get("Earnings Growth %"), None)
    analyst_count = int(safe_number(row.get("Analyst Count"), 0))

    score = 68
    confidence = "Medium"
    positives, risks = [], []

    if pe is not None:
        if pe < 0:
            score -= 18
            risks.append(f"Negative P/E ({pe:.1f}) means current earnings are negative.")
        elif pe <= 35:
            score += 8
            positives.append(f"P/E looks reasonable at {pe:.1f}.")
        elif pe > 80:
            score -= 8
            risks.append(f"P/E is high at {pe:.1f}.")
    elif fpe is not None:
        if fpe > 0 and fpe <= 35:
            score += 7
            positives.append(f"Forward P/E is reasonable at {fpe:.1f}.")
        elif fpe < 0:
            score -= 12
            risks.append(f"Forward P/E is negative ({fpe:.1f}).")
        else:
            risks.append("Trailing P/E unavailable; using forward valuation only.")
    else:
        confidence = "Low-Medium"
        risks.append("Profitability valuation metric is unavailable; quality confidence is lower, not automatically negative.")

    if peg is not None:
        if 0 < peg <= 1.5:
            score += 7
            positives.append(f"PEG ratio appears attractive at {peg:.2f}.")
        elif peg > 3:
            score -= 5
            risks.append(f"PEG ratio is elevated at {peg:.2f}.")

    if rev_growth is not None:
        if rev_growth >= 20:
            score += 8
            positives.append(f"Revenue growth is strong at {rev_growth:.1f}%.")
        elif rev_growth < 0:
            score -= 8
            risks.append("Revenue growth is negative.")

    if eps_growth is not None:
        if eps_growth >= 10:
            score += 6
            positives.append(f"EPS growth is positive at {eps_growth:.1f}%.")
        elif eps_growth < 0:
            score -= 8
            risks.append("EPS growth is negative.")

    if analyst_count >= 20:
        score += 4
        positives.append(f"Strong analyst coverage ({analyst_count} analysts).")
    elif analyst_count and analyst_count < 5:
        score -= 3
        risks.append("Limited analyst coverage.")

    if "biotech" in sector.lower() or "therapeutic" in safe_text(row.get("Company"), "").lower():
        if pe is not None and pe < 0:
            score -= 10
            risks.append("Unprofitable biotech/therapeutics name should be treated as speculative.")

    score = max(0, min(100, round(score)))
    tier = "🏆 Quality Compounder" if score >= 85 else ("📈 Growth Leader" if score >= 70 else ("🔄 Recovery / Mixed Quality" if score >= 55 else "⚠️ Speculative"))
    if not positives:
        positives = ["Some quality inputs are constructive, but more data would improve confidence."]
    if not risks:
        risks = ["No major business-quality red flag from available fields."]
    return {"score": score, "tier": tier, "confidence": confidence, "positives": positives[:5], "flags": risks[:5], "pe": pe, "fpe": fpe, "peg": peg}


def v432_agent_data_grade(row):
    committee = row.get("AI Committee")
    if not isinstance(committee, dict):
        return {"full": 0, "partial": 0, "deferred": 0, "grade": "Limited"}
    full = partial = deferred = 0
    for _, agent in committee.items():
        if not isinstance(agent, dict):
            continue
        status = safe_text(agent.get("status"), "").lower()
        if "deferred" in status or "not connected" in status:
            deferred += 1
        elif "limited" in status or "mixed" in status:
            partial += 1
        else:
            full += 1
    grade = "Strong" if full >= 5 else ("Moderate" if full >= 3 else "Lightweight")
    return {"full": full, "partial": partial, "deferred": deferred, "grade": grade}


def render_v432_news_panel(row):
    n = v432_news_intelligence(safe_text(row.get("Ticker"), ""))
    with st.container(border=True):
        st.markdown("### 📰 News Intelligence")
        c1, c2 = st.columns(2)
        c1.metric("News Score", f"{n['score']}/100")
        c2.metric("Status", n["status"])
        st.caption(n["summary"])
        left, right = st.columns(2)
        with left:
            st.markdown("**Bullish / supportive headlines**")
            for x in n["bullish"][:3]:
                st.markdown(f"✓ {safe_text(x)}")
        with right:
            st.markdown("**Bearish / risk headlines**")
            for x in n["bearish"][:3]:
                st.markdown(f"⚠️ {safe_text(x)}")
        with st.expander("News source diagnostics", expanded=False):
            for d in n["diagnostics"]:
                st.caption(d)


def render_v432_analyst_panel(row):
    ticker = safe_text(row.get("Ticker"), "")
    price = safe_number(row.get("Price"), 0)
    a = v432_analyst_intelligence(ticker, price=price, analyst_target=safe_number(row.get("Analyst Target"), 0), analyst_count=safe_number(row.get("Analyst Count"), 0))
    with st.container(border=True):
        st.markdown("### 🏦 Analyst Intelligence V2")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Consensus", v43_money(a.get("consensus")) if a.get("consensus") else "N/A")
        c2.metric("Upside", f"{a.get('upside'):.1f}%" if a.get("upside") is not None else "N/A")
        c3.metric("High / Low", f"{v43_money(a.get('high'))} / {v43_money(a.get('low'))}" if a.get("high") or a.get("low") else "N/A")
        c4.metric("Coverage", str(a.get("count") or "N/A"))
        st.caption(f"Rating trend: {a.get('rating_trend', 'Unknown')}")
        if a.get("firm_rows"):
            st.markdown("**Recent firm-level actions returned by source**")
            st.dataframe(pd.DataFrame(a["firm_rows"][:6]), use_container_width=True, hide_index=True)
        else:
            st.warning("Firm-level top analyst rows were not returned by the available source/API plan. Using consensus target, high/low, coverage, and recommendation trend.")
        with st.expander("Analyst source diagnostics", expanded=False):
            for d in a.get("source_notes", []):
                st.caption(d)


def render_v432_data_confidence_panel(row):
    grade = v432_agent_data_grade(row)
    q = v432_business_quality(row)
    with st.container(border=True):
        st.markdown("### 🧪 Data Confidence")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Overall Data Grade", grade["grade"])
        c2.metric("Full Agents", grade["full"])
        c3.metric("Partial Agents", grade["partial"])
        c4.metric("Deferred", grade["deferred"])
        st.caption(f"Business quality confidence: {q.get('confidence', 'N/A')}. Deferred agents are not treated as primary buy signals.")


def render_v432_source_diagnostics():
    with st.expander("🔌 Source Diagnostics", expanded=False):
        rows = [{"Variable": k, "Detected": "Yes" if v["configured"] else "No", "Length": v["length"]} for k, v in v432_env_status().items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        mn = v432_market_news_items()
        st.markdown("**Market news test:**")
        for d in mn.get("diagnostics", []):
            st.caption(d)


def render_v424_market_command_center():
    st.markdown("## 🧭 Market Command Center")
    if "v43_market_regime" in globals():
        regime, regime_score = v43_market_regime()
        st.metric("Market Regime", regime, f"{regime_score:.0f}/100")

    quotes = v424_market_quotes()
    if quotes:
        cols = st.columns(min(5, len(quotes)))
        for i, q in enumerate(quotes[:5]):
            pct = v424_float(q.get("change_pct"), None) if "v424_float" in globals() else safe_number(q.get("change_pct"), None)
            delta = f"{pct:+.2f}%" if pct is not None else None
            label = q.get("display_label") or q.get("symbol", "")
            cols[i].metric(label, v43_money(q.get("price")) if "v43_money" in globals() else fmt_money(q.get("price")), delta)
            cols[i].caption(safe_text(q.get("source"), ""))
    else:
        st.warning("Market quotes unavailable from connected and fallback sources.")

    econ = v424_economic_calendar()
    earnings = v424_earnings_today()
    news = v432_market_news_summary()

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            st.caption(f"Source: {safe_text(econ.get('source'), 'Unknown')}")
            events = (econ.get("today") or []) or (econ.get("next") or [])
            if events:
                for e in events[:5]:
                    if "v4253_render_event_line" in globals():
                        st.markdown(f"• {v4253_render_event_line(e)}")
                    else:
                        st.markdown(f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
            else:
                st.warning("No economic calendar data returned.")

    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            st.caption("Source priority: FMP → Finnhub → Nasdaq → Alpha Vantage → Yahoo")
            if earnings:
                edf = pd.DataFrame(earnings)
                preferred = [c for c in ["Company", "Ticker", "Symbol", "Date", "Time", "EPS Est", "Revenue Est", "Source"] if c in edf.columns]
                st.dataframe(edf[preferred] if preferred else edf, use_container_width=True, hide_index=True)
            else:
                st.warning("No earnings returned from any connected/fallback source today.")

    with st.container(border=True):
        st.markdown("### 📰 Market News Intelligence")
        c1, c2 = st.columns(2)
        c1.metric("Status", news["status"])
        c2.metric("Sentiment", news["sentiment"])
        st.markdown(f"**Top headline:** {safe_text(news['top'])}")
        for r in news.get("rows", [])[:5]:
            h, src, url = safe_text(r.get("headline"), ""), safe_text(r.get("source"), ""), safe_text(r.get("url"), "")
            st.markdown(f"• [{h}]({url}) · _{src}_" if url else f"• {h} · _{src}_")
        with st.expander("Market news diagnostics", expanded=False):
            for d in news.get("diagnostics", []):
                st.caption(d)

    render_v432_source_diagnostics()


def v431_get_quality(row):
    return v432_business_quality(row)


def render_v431_professional_research_card(row):
    render_v431_decision_card(row)
    render_v431_targets_card(row)
    render_v432_data_confidence_panel(row)
    render_v431_business_quality_agent(row)
    render_v432_analyst_panel(row)
    render_v432_news_panel(row)
    render_v431_agent_summary(row)




# =========================
# V44.0 PAID CLIENT INTELLIGENCE UPGRADE
# =========================

def v44_secret(name, default=""):
    """Read Streamlit Secrets first, then environment variables."""
    try:
        if hasattr(st, "secrets") and name in st.secrets:
            return str(st.secrets.get(name, default)).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


def v44_float(x, default=0.0):
    try:
        if x in (None, "", "N/A", "None"):
            return default
        if isinstance(x, str):
            x = x.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(x)
    except Exception:
        return default


def v44_money(x):
    x = v44_float(x, None)
    return "N/A" if x is None else f"${x:,.2f}"


@st.cache_data(ttl=900)
def v44_market_news_items():
    rows, diag = [], []
    news_key = v44_secret("NEWSAPI_KEY")
    if news_key:
        q = '(stock market OR "S&P 500" OR Nasdaq OR Federal Reserve OR earnings OR inflation OR treasury OR semiconductor)'
        data, status = v432_http_json(
            "https://newsapi.org/v2/everything",
            params={"q": q, "language": "en", "sortBy": "publishedAt", "pageSize": 10, "apiKey": news_key},
        )
        diag.append(f"NEWSAPI_KEY detected length={len(news_key)}; NewsAPI market-query status={status}")
        if isinstance(data, dict):
            for a in data.get("articles", [])[:10]:
                h = safe_text(a.get("title"), "")
                if h:
                    rows.append({
                        "headline": h,
                        "source": safe_text((a.get("source") or {}).get("name"), "NewsAPI"),
                        "url": safe_text(a.get("url"), ""),
                        "provider": "NewsAPI market query",
                    })
    else:
        diag.append("NEWSAPI_KEY missing or blank")

    finnhub_key = v44_secret("FINNHUB_API_KEY")
    if not rows and finnhub_key:
        data, status = v432_http_json("https://finnhub.io/api/v1/news", params={"category": "general", "token": finnhub_key})
        diag.append(f"FINNHUB_API_KEY detected length={len(finnhub_key)}; Finnhub status={status}")
        if isinstance(data, list):
            for a in data[:10]:
                h = safe_text(a.get("headline"), "")
                if h:
                    rows.append({"headline": h, "source": safe_text(a.get("source"), "Finnhub"), "url": safe_text(a.get("url"), ""), "provider": "Finnhub"})

    if not rows:
        for provider, url in [
            ("Yahoo Finance RSS", "https://finance.yahoo.com/news/rssindex"),
            ("CNBC Business RSS", "https://www.cnbc.com/id/10001147/device/rss/rss.html"),
            ("MarketWatch RSS", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ]:
            text, status = v432_http_text(url, timeout=8)
            diag.append(f"{provider} status={status}")
            if not text:
                continue
            try:
                root = ET.fromstring(text.encode("utf-8"))
                for item in root.findall(".//item")[:10]:
                    title = safe_text(item.findtext("title"), "")
                    link = safe_text(item.findtext("link"), "")
                    if title:
                        rows.append({"headline": title, "source": provider, "url": link, "provider": provider})
                if rows:
                    break
            except Exception as e:
                diag.append(f"{provider} parse failed: {e}")

    return {"rows": rows[:10], "diagnostics": diag}


def v44_news_sentiment(rows):
    bullish = ["rally", "surge", "gain", "jumps", "record", "beat", "raises", "upgrade", "strong", "breakout", "growth"]
    bearish = ["sell-off", "selloff", "slump", "drops", "falls", "miss", "cuts", "downgrade", "inflation", "tariff", "recession", "layoff", "probe", "weak", "warning", "risk"]
    bulls, bears = [], []
    for r in rows:
        h = safe_text(r.get("headline"), "")
        low = h.lower()
        if any(t in low for t in bullish):
            bulls.append(h)
        if any(t in low for t in bearish):
            bears.append(h)
    score = max(0, min(100, 50 + min(25, len(bulls)*6) - min(25, len(bears)*6)))
    sentiment = "Constructive" if score >= 62 else ("Cautious" if score <= 42 else "Mixed / Neutral")
    return {"score": score, "sentiment": sentiment, "bullish": bulls[:3], "bearish": bears[:3]}


def v44_market_news_summary():
    data = v44_market_news_items()
    rows = data.get("rows", [])
    s = v44_news_sentiment(rows)
    return {
        "status": "Headlines available" if rows else "No headlines returned",
        "sentiment": s["sentiment"],
        "score": s["score"],
        "top": rows[0]["headline"] if rows else "No market headline source returned a usable headline.",
        "rows": rows,
        "bullish": s["bullish"],
        "bearish": s["bearish"],
        "diagnostics": data.get("diagnostics", []),
    }


@st.cache_data(ttl=1800)
def v44_fmp_extra(ticker):
    out = {"profile": {}, "metrics": {}, "income": {}, "cashflow": {}, "diagnostics": []}
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker or not v44_secret("FMP_API_KEY") or "v424_fmp_get" not in globals():
        out["diagnostics"].append("FMP unavailable or ticker missing")
        return out
    for key, endpoint, params in [
        ("profile", f"profile/{ticker}", None),
        ("metrics", f"key-metrics-ttm/{ticker}", None),
        ("income", f"income-statement/{ticker}", {"limit": 1}),
        ("cashflow", f"cash-flow-statement/{ticker}", {"limit": 1}),
    ]:
        try:
            data = v424_fmp_get(endpoint, params)
            out["diagnostics"].append(f"FMP {endpoint} tried")
            if isinstance(data, list) and data:
                out[key] = data[0]
            elif isinstance(data, dict):
                out[key] = data
        except Exception as e:
            out["diagnostics"].append(f"FMP {endpoint} failed: {e}")
    return out


def v44_business_quality(row):
    ticker = safe_text(row.get("Ticker"), "")
    extra = v44_fmp_extra(ticker)
    metrics = extra.get("metrics", {}) or {}
    profile = extra.get("profile", {}) or {}
    income = extra.get("income", {}) or {}
    cashflow = extra.get("cashflow", {}) or {}

    pe = v44_float(row.get("PE Ratio") or row.get("P/E") or metrics.get("peRatioTTM") or profile.get("pe"), None)
    fpe = v44_float(row.get("Forward PE"), None)
    peg = v44_float(row.get("PEG Ratio") or row.get("PEG") or metrics.get("pegRatioTTM"), None)
    net_income = v44_float(income.get("netIncome"), None)
    fcf = v44_float(cashflow.get("freeCashFlow"), None)
    gross_margin = v44_float(metrics.get("grossProfitMarginTTM"), None)
    analyst_count = int(v44_float(row.get("Analyst Count"), 0))
    sector = safe_text(row.get("Sector") or profile.get("sector"), "")
    company = safe_text(row.get("Company") or profile.get("companyName"), ticker)

    score, positives, risks, confidence = 68, [], [], "Medium"

    if pe is not None:
        if pe < 0:
            score -= 18; risks.append(f"Negative P/E ({pe:.1f}) means current earnings are negative.")
        elif pe <= 35:
            score += 8; positives.append(f"P/E looks reasonable at {pe:.1f}.")
        elif pe > 80:
            score -= 8; risks.append(f"P/E is high at {pe:.1f}.")
    elif fpe is not None:
        if 0 < fpe <= 35:
            score += 7; positives.append(f"Forward P/E is reasonable at {fpe:.1f}.")
        elif fpe < 0:
            score -= 12; risks.append(f"Forward P/E is negative ({fpe:.1f}).")
    else:
        confidence = "Low-Medium"; risks.append("P/E data is unavailable; quality confidence is lower.")

    if net_income is not None:
        if net_income > 0:
            score += 8; positives.append("Net income is positive.")
        else:
            score -= 12; risks.append("Net income is negative.")
    if fcf is not None:
        if fcf > 0:
            score += 10; positives.append("Free cash flow is positive.")
        else:
            score -= 12; risks.append("Free cash flow is negative.")
    if peg is not None:
        if 0 < peg <= 1.5:
            score += 6; positives.append(f"PEG ratio appears attractive at {peg:.2f}.")
        elif peg > 3:
            score -= 5; risks.append(f"PEG ratio is elevated at {peg:.2f}.")
    if gross_margin is not None:
        gm = gross_margin * 100 if gross_margin < 2 else gross_margin
        if gm >= 40:
            score += 5; positives.append(f"Gross margin is strong at {gm:.1f}%.")
        elif gm < 20:
            score -= 4; risks.append(f"Gross margin is low at {gm:.1f}%.")
    if analyst_count >= 20:
        score += 4; positives.append(f"Strong analyst coverage ({analyst_count} analysts).")
    elif 0 < analyst_count < 5:
        score -= 3; risks.append("Limited analyst coverage.")

    speculative = False
    if "biotech" in sector.lower() or "therapeutic" in company.lower() or "bio" in company.lower():
        if (pe is not None and pe < 0) or (net_income is not None and net_income < 0) or (fcf is not None and fcf < 0):
            speculative = True; score -= 12; risks.append("Unprofitable biotech/therapeutics profile should be treated as speculative.")

    score = max(0, min(100, round(score)))
    tier = "⚠️ Speculative" if speculative or score < 55 else ("🏆 Quality Compounder" if score >= 85 else ("📈 Growth Leader" if score >= 70 else "🔄 Recovery / Mixed Quality"))
    if not positives:
        positives = ["Some quality inputs are constructive, but more data would improve confidence."]
    if not risks:
        risks = ["No major business-quality red flag from available fields."]
    return {"score": score, "tier": tier, "confidence": confidence, "positives": positives[:5], "flags": risks[:6], "pe": pe, "fpe": fpe, "peg": peg, "diagnostics": extra.get("diagnostics", [])}


@st.cache_data(ttl=1800)
def v44_analyst_intelligence(ticker, price=0, analyst_target=0, analyst_count=0):
    out = {"consensus": analyst_target, "high": 0, "low": 0, "count": int(v44_float(analyst_count, 0)), "firm_rows": [], "rating_trend": "Unknown", "source_notes": []}
    ticker = safe_text(ticker, "").upper().strip()
    if not ticker:
        return out

    if v44_secret("FMP_API_KEY") and "v424_fmp_get" in globals():
        for endpoint in [f"price-target-consensus/{ticker}", f"price-target-summary/{ticker}"]:
            try:
                data = v424_fmp_get(endpoint)
                out["source_notes"].append(f"FMP {endpoint} tried")
                if isinstance(data, list) and data:
                    d = data[0]
                    out["consensus"] = v44_float(d.get("targetConsensus") or d.get("targetMean") or d.get("priceTargetAverage") or out["consensus"], out["consensus"])
                    out["high"] = v44_float(d.get("targetHigh") or d.get("targetHighPrice") or d.get("priceTargetHigh"), out["high"])
                    out["low"] = v44_float(d.get("targetLow") or d.get("targetLowPrice") or d.get("priceTargetLow"), out["low"])
                    out["count"] = int(v44_float(d.get("numberOfAnalysts") or d.get("analystCount") or d.get("analystsCount"), out["count"]))
            except Exception as e:
                out["source_notes"].append(f"FMP {endpoint} failed: {e}")
        try:
            data = v424_fmp_get(f"upgrades-downgrades/{ticker}")
            out["source_notes"].append("FMP upgrades-downgrades tried")
            if isinstance(data, list):
                for d in data[:8]:
                    out["firm_rows"].append({
                        "Firm": safe_text(d.get("gradingCompany") or d.get("firm") or d.get("analystCompany"), "Analyst firm"),
                        "Action": safe_text(d.get("action") or d.get("newGrade") or "Update"),
                        "Rating": safe_text(d.get("newGrade") or d.get("rating") or "N/A"),
                        "Previous": safe_text(d.get("previousGrade") or "N/A"),
                        "Date": safe_text(d.get("publishedDate") or d.get("date"), ""),
                    })
        except Exception as e:
            out["source_notes"].append(f"FMP upgrades failed: {e}")

    if v44_secret("FINNHUB_API_KEY"):
        data, status = v432_http_json("https://finnhub.io/api/v1/stock/recommendation", params={"symbol": ticker, "token": v44_secret("FINNHUB_API_KEY")})
        out["source_notes"].append(f"Finnhub recommendation status={status}")
        if isinstance(data, list) and data:
            d = data[0]
            sb, b, h = int(v44_float(d.get("strongBuy"),0)), int(v44_float(d.get("buy"),0)), int(v44_float(d.get("hold"),0))
            s = int(v44_float(d.get("sell"),0)) + int(v44_float(d.get("strongSell"),0))
            out["rating_trend"] = "Bullish / positive recommendation mix" if sb + b > h + s else ("Bearish / negative recommendation mix" if s > sb + b else "Mixed / hold-heavy recommendation mix")
            if not out["count"]:
                out["count"] = sb + b + h + s

    if not out["high"] and out["consensus"]:
        out["high"] = out["consensus"] * 1.15
    if not out["low"] and out["consensus"]:
        out["low"] = out["consensus"] * 0.85
    out["upside"] = ((out["consensus"] - price) / price) * 100 if price and out["consensus"] else None
    return out


def v44_valuation(row):
    price, analyst, ai = v44_float(row.get("Price"),0), v44_float(row.get("Analyst Target"),0), v44_float(row.get("AI Fair Value"),0)
    conservative = analyst if analyst else (price * 1.12 if price else 0)
    base, aggressive, confidence, note = conservative, (ai or conservative), "Medium", "Base case uses analyst consensus when available."
    if analyst and ai:
        gap = ((ai - analyst) / analyst) * 100
        if gap > 75:
            confidence, base, note = "Low", analyst * 1.20, "AI fair value is far above analyst consensus, so AI value is aggressive only."
        elif gap > 50:
            confidence, base, note = "Low-Medium", analyst * 1.15, "AI fair value is materially above consensus, so confidence is reduced."
        elif gap > 20:
            confidence, base, note = "Medium", (analyst + ai) / 2, "AI fair value is above consensus but not extreme."
        else:
            confidence, base, note = "High", (analyst + ai) / 2, "AI fair value is close to analyst consensus."
    return {"conservative": conservative, "base": base, "aggressive": aggressive, "confidence": confidence, "note": note}


def v44_score(row):
    old = v44_float(row.get("Final Conviction"),0)
    q = v44_business_quality(row)
    a = v44_analyst_intelligence(safe_text(row.get("Ticker"),""), price=v44_float(row.get("Price"),0), analyst_target=v44_float(row.get("Analyst Target"),0), analyst_count=v44_float(row.get("Analyst Count"),0))
    val = v44_valuation(row)
    analyst_score = 82 if a.get("rating_trend","").startswith("Bullish") else (62 if a.get("rating_trend","").startswith("Mixed") else 60)
    valuation_score = {"High":85, "Medium":72, "Low-Medium":60, "Low":48}.get(val.get("confidence"),65)
    risk = 75
    if v44_float(row.get("Volume Ratio"),0) < 0.75:
        risk -= 8
    if v44_float(row.get("ATR %"),0) >= 5:
        risk -= 8
    raw = q["score"]*.30 + analyst_score*.18 + valuation_score*.22 + risk*.15 + old*.15
    adjusted = 50 + (raw - 50) * .90
    if "Speculative" in q["tier"]:
        adjusted -= 8
    if val["confidence"] == "Low":
        adjusted -= 5
    return max(0, min(99, round(adjusted,1)))


def v44_verdict(row):
    score, q, val = v44_score(row), v44_business_quality(row), v44_valuation(row)
    levels = v431_smart_levels(row) if "v431_smart_levels" in globals() else {}
    decision, explanation = "WATCH", "Good research candidate, but confirm entry and risk before buying."
    if "Speculative" in q["tier"]:
        decision, explanation = "SPECULATIVE", "Higher-risk idea. Use smaller sizing and require stronger confirmation."
    elif score >= 88 and val["confidence"] in {"High","Medium"}:
        decision, explanation = "ACTIONABLE WATCH", "Quality-adjusted score is strong, but entry discipline still matters."
    elif score < 68:
        decision, explanation = "LOW PRIORITY", "Not enough quality-adjusted confirmation for a paid-client recommendation."
    price, support, resistance = v44_float(levels.get("price") or row.get("Price"),0), v44_float(levels.get("support1"),0), v44_float(levels.get("resistance1"),0)
    if price and support and resistance and price > support:
        rr = (resistance-price)/(price-support) if price-support else 0
        if rr < 1:
            decision, explanation = "WAIT", f"Reward/risk is weak. Prefer pullback near {v44_money(support)} or breakout above {v44_money(resistance)} with volume."
    label = "🟢 Elite Quality Setup" if score >= 90 and "Speculative" not in q["tier"] else ("🟢 Strong Setup" if score >= 84 else ("🟡 Actionable Watch" if score >= 76 else ("⚠️ Speculative High-Upside" if "Speculative" in q["tier"] else "⚪ Low Priority")))
    return {"score": score, "quality": q, "valuation": val, "levels": levels, "decision": decision, "explanation": explanation, "label": label}


def render_v44_executive_card(row):
    v = v44_verdict(row); q = v["quality"]; val = v["valuation"]; levels = v["levels"]
    ticker, company = safe_text(row.get("Ticker"),""), safe_text(row.get("Company"),"")
    with st.container(border=True):
        st.markdown(f"## {ticker}{(' — ' + company) if company else ''}")
        st.markdown(f"### {v['label']} · {v['decision']}")
        st.info(v["explanation"])
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("V44 Score", f"{v['score']:.1f}/100")
        c2.metric("Tier", q["tier"])
        c3.metric("Quality", f"{q['score']}/100")
        c4.metric("Valuation Confidence", val["confidence"])
        c5,c6,c7,c8 = st.columns(4)
        c5.metric("Price", v44_money(levels.get("price") or row.get("Price")))
        c6.metric("Support", v44_money(levels.get("support1")) if v44_float(levels.get("support1"),0) else "N/A")
        c7.metric("Resistance", v44_money(levels.get("resistance1")) if v44_float(levels.get("resistance1"),0) else "N/A")
        c8.metric("Stop", v44_money(row.get("Stop Loss")) if v44_float(row.get("Stop Loss"),0) else "N/A")
        left,right = st.columns(2)
        with left:
            st.markdown("**Top reasons**")
            for p in q["positives"][:4]: st.markdown(f"✓ {safe_text(p)}")
        with right:
            st.markdown("**Top risks**")
            risks = list(q["flags"][:4])
            if val["confidence"] in {"Low","Low-Medium"}: risks.append(val["note"])
            for r in risks[:5]: st.markdown(f"⚠️ {safe_text(r)}")


def render_v44_targets_analyst(row):
    val = v44_valuation(row)
    a = v44_analyst_intelligence(safe_text(row.get("Ticker"),""), price=v44_float(row.get("Price"),0), analyst_target=v44_float(row.get("Analyst Target"),0), analyst_count=v44_float(row.get("Analyst Count"),0))
    with st.container(border=True):
        st.markdown("### 🎯 Targets + Analyst Intelligence")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Conservative", v44_money(val["conservative"]))
        c2.metric("Base", v44_money(val["base"]))
        c3.metric("Aggressive", v44_money(val["aggressive"]))
        c4.metric("Consensus Upside", f"{a['upside']:.1f}%" if a.get("upside") is not None else "N/A")
        st.caption(val["note"])
        c5,c6,c7,c8 = st.columns(4)
        c5.metric("Consensus", v44_money(a.get("consensus")) if a.get("consensus") else "N/A")
        c6.metric("High Target", v44_money(a.get("high")) if a.get("high") else "N/A")
        c7.metric("Low Target", v44_money(a.get("low")) if a.get("low") else "N/A")
        c8.metric("Coverage", str(a.get("count") or "N/A"))
        st.caption(f"Rating trend: {a.get('rating_trend','Unknown')}")
        if a.get("firm_rows"):
            st.dataframe(pd.DataFrame(a["firm_rows"][:6]), use_container_width=True, hide_index=True)
        else:
            st.warning("Firm-level analyst rows were not returned by the current source/API. Showing consensus/range/trend instead.")
        with st.expander("Analyst source diagnostics", expanded=False):
            for n in a.get("source_notes",[]): st.caption(n)


def render_v44_business_quality(row):
    q = v44_business_quality(row)
    with st.container(border=True):
        st.markdown("### 🧱 Business Quality 2.0")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Quality Score", f"{q['score']}/100")
        c2.metric("Tier", q["tier"])
        c3.metric("P/E", "N/A" if q["pe"] is None else f"{q['pe']:.1f}")
        c4.metric("Confidence", q["confidence"])
        left,right = st.columns(2)
        with left:
            st.markdown("**Strengths**")
            for p in q["positives"][:5]: st.markdown(f"✓ {safe_text(p)}")
        with right:
            st.markdown("**Risks / limits**")
            for r in q["flags"][:6]: st.markdown(f"⚠️ {safe_text(r)}")
        with st.expander("Business quality diagnostics", expanded=False):
            for d in q.get("diagnostics",[]): st.caption(d)


def render_v44_market_command_center():
    st.markdown("## 🧭 Market Command Center")
    if "v43_market_regime" in globals():
        regime, regime_score = v43_market_regime()
        st.metric("Market Regime", regime, f"{regime_score:.0f}/100")
    quotes = v424_market_quotes()
    if quotes:
        cols = st.columns(min(5,len(quotes)))
        for i,q in enumerate(quotes[:5]):
            pct = v424_float(q.get("change_pct"), None) if "v424_float" in globals() else v44_float(q.get("change_pct"), None)
            cols[i].metric(q.get("display_label") or q.get("symbol",""), v44_money(q.get("price")), f"{pct:+.2f}%" if pct is not None else None)
            cols[i].caption(safe_text(q.get("source"),""))
    econ, earnings, news = v424_economic_calendar(), v424_earnings_today(), v44_market_news_summary()
    c1,c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🗓️ Economic Calendar")
            st.caption(f"Source: {safe_text(econ.get('source'),'Unknown')}")
            for e in ((econ.get("today") or []) or (econ.get("next") or []))[:5]:
                st.markdown(f"• {v4253_render_event_line(e)}" if "v4253_render_event_line" in globals() else f"• **{safe_text(e.get('event'))}** — {safe_text(e.get('date'))}")
    with c2:
        with st.container(border=True):
            st.markdown("### 💼 Earnings Due Today")
            st.caption("Source priority: FMP → Finnhub → Nasdaq → Alpha Vantage → Yahoo")
            if earnings:
                edf = pd.DataFrame(earnings)
                cols = [c for c in ["Company","Ticker","Symbol","Date","Time","EPS Est","Revenue Est","Source"] if c in edf.columns]
                st.dataframe(edf[cols] if cols else edf, use_container_width=True, hide_index=True)
            else:
                st.warning("No earnings returned from any connected/fallback source today.")
    with st.container(border=True):
        st.markdown("### 📰 Market News Intelligence")
        c1,c2,c3 = st.columns(3)
        c1.metric("Status", news["status"]); c2.metric("Sentiment", news["sentiment"]); c3.metric("News Score", f"{news['score']}/100")
        st.markdown(f"**Top headline:** {safe_text(news['top'])}")
        for r in news.get("rows",[])[:5]:
            h,src,url = safe_text(r.get("headline"),""), safe_text(r.get("source"),""), safe_text(r.get("url"),"")
            st.markdown(f"• [{h}]({url}) · _{src}_" if url else f"• {h} · _{src}_")
        with st.expander("Market news diagnostics", expanded=False):
            for d in news.get("diagnostics",[]): st.caption(d)
    if "render_v44_source_diagnostics" in globals(): render_v44_source_diagnostics()


def render_v44_source_diagnostics():
    with st.expander("🔌 Source Diagnostics", expanded=False):
        names = ["APP_PASSWORD","GUEST_PASSWORD","FMP_API_KEY","FINNHUB_API_KEY","NEWSAPI_KEY","ALPHA_VANTAGE_API_KEY","SEC_USER_AGENT","GITHUB_TOKEN","GITHUB_REPO_URL","DATA_DIR"]
        st.dataframe(pd.DataFrame([{"Variable":n,"Detected":"Yes" if v44_secret(n) else "No","Length":len(v44_secret(n))} for n in names]), use_container_width=True, hide_index=True)
        for d in v44_market_news_items().get("diagnostics",[]): st.caption(d)


def render_v44_professional_research_card(row):
    render_v44_executive_card(row)
    render_v44_targets_analyst(row)
    render_v44_business_quality(row)
    if "render_v44_news_panel" in globals():
        render_v44_news_panel(row)
    elif "render_v432_news_panel" in globals():
        render_v432_news_panel(row)
    if "render_v432_data_confidence_panel" in globals(): render_v432_data_confidence_panel(row)
    if "render_v431_agent_summary" in globals(): render_v431_agent_summary(row)


def render_v424_market_command_center():
    render_v44_market_command_center()


def render_detail(row):
    render_v44_professional_research_card(row)
    if "render_detail_chart_v4184" in globals():
        try: render_detail_chart_v4184(row)
        except Exception: pass
    if "render_v431_advanced_legacy_sections" in globals(): render_v431_advanced_legacy_sections(row)
    with st.expander("Raw row data", expanded=False):
        try: st.json(row if isinstance(row, dict) else dict(row))
        except Exception: st.write(row)



# =========================
# V45.0 INSTITUTIONAL RESEARCH EXPERIENCE
# Customer-facing decision engine, metric interpretation, QA export
# =========================

def v45_secret(name, default=""):
    try:
        if hasattr(st, "secrets") and name in st.secrets:
            return str(st.secrets.get(name, default)).strip()
    except Exception:
        pass
    try:
        return os.getenv(name, default).strip()
    except Exception:
        return default


def v45_text(x, default=""):
    try:
        return safe_text(x, default)
    except Exception:
        return default if x is None else str(x)


def v45_num(x, default=None):
    try:
        if x in (None, "", "N/A", "None", "nan"):
            return default
        if isinstance(x, str):
            x = x.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(x)
    except Exception:
        return default


def v45_money(x):
    x = v45_num(x, None)
    return "N/A" if x is None else f"${x:,.2f}"


def v45_pct(x):
    x = v45_num(x, None)
    return "N/A" if x is None else f"{x:.1f}%"


def v45_grade(score):
    s = v45_num(score, 0)
    if s >= 93: return "A+"
    if s >= 88: return "A"
    if s >= 83: return "A-"
    if s >= 78: return "B+"
    if s >= 72: return "B"
    if s >= 66: return "B-"
    if s >= 58: return "C"
    return "D"


def v45_sector(row):
    return v45_text(row.get("Sector") or row.get("sector") or "General")


def v45_industry(row):
    return v45_text(row.get("Industry") or row.get("industry") or v45_sector(row))


def v45_benchmarks(row):
    sector = v45_sector(row).lower()
    industry = v45_industry(row).lower()
    text = f"{sector} {industry}"
    # Ranges are pragmatic interpretation bands for customer explanation, not hard valuation rules.
    if any(k in text for k in ["software", "technology", "cloud", "internet", "semiconductor", "chip"]):
        return {"pe_good": 35, "pe_fair": 50, "pe_high": 70, "peg_good": 1.5, "rev_good": 12, "eps_good": 12, "gross_good": 45, "debt_good": 1.0, "label": "technology/software peers"}
    if any(k in text for k in ["healthcare", "biotech", "therapeutic", "pharma"]):
        return {"pe_good": 30, "pe_fair": 45, "pe_high": 65, "peg_good": 1.8, "rev_good": 10, "eps_good": 10, "gross_good": 40, "debt_good": 1.2, "label": "healthcare peers"}
    if any(k in text for k in ["consumer", "retail", "cyclical", "discretionary"]):
        return {"pe_good": 25, "pe_fair": 35, "pe_high": 50, "peg_good": 1.6, "rev_good": 7, "eps_good": 8, "gross_good": 30, "debt_good": 1.5, "label": "consumer peers"}
    if any(k in text for k in ["industrial", "materials", "energy"]):
        return {"pe_good": 20, "pe_fair": 30, "pe_high": 45, "peg_good": 1.5, "rev_good": 6, "eps_good": 8, "gross_good": 25, "debt_good": 1.5, "label": "cyclical/industrial peers"}
    if any(k in text for k in ["utility", "staples", "telecom", "real estate", "reit"]):
        return {"pe_good": 22, "pe_fair": 30, "pe_high": 40, "peg_good": 2.0, "rev_good": 4, "eps_good": 5, "gross_good": 25, "debt_good": 2.0, "label": "defensive peers"}
    if any(k in text for k in ["financial", "bank", "insurance"]):
        return {"pe_good": 15, "pe_fair": 22, "pe_high": 30, "peg_good": 1.4, "rev_good": 5, "eps_good": 6, "gross_good": 0, "debt_good": 3.0, "label": "financial peers"}
    return {"pe_good": 25, "pe_fair": 35, "pe_high": 50, "peg_good": 1.6, "rev_good": 8, "eps_good": 8, "gross_good": 30, "debt_good": 1.5, "label": "broad market peers"}


def v45_row_metric(row, *names, default=None):
    for n in names:
        try:
            if n in row and row.get(n) not in (None, "", "N/A"):
                return row.get(n)
        except Exception:
            pass
    return default


@st.cache_data(ttl=1800)
def v45_fmp_snapshot(ticker):
    ticker = v45_text(ticker).upper().strip()
    out = {"profile": {}, "metrics": {}, "ratios": {}, "income": {}, "cashflow": {}, "balance": {}, "diagnostics": []}
    if not ticker or not v45_secret("FMP_API_KEY") or "v424_fmp_get" not in globals():
        out["diagnostics"].append("FMP unavailable or ticker missing")
        return out
    endpoints = [
        ("profile", f"profile/{ticker}", None),
        ("metrics", f"key-metrics-ttm/{ticker}", None),
        ("ratios", f"ratios-ttm/{ticker}", None),
        ("income", f"income-statement/{ticker}", {"limit": 1}),
        ("cashflow", f"cash-flow-statement/{ticker}", {"limit": 1}),
        ("balance", f"balance-sheet-statement/{ticker}", {"limit": 1}),
    ]
    for key, endpoint, params in endpoints:
        try:
            data = v424_fmp_get(endpoint, params)
            out["diagnostics"].append(f"FMP {endpoint} tried")
            if isinstance(data, list) and data:
                out[key] = data[0] or {}
            elif isinstance(data, dict):
                out[key] = data
        except Exception as e:
            out["diagnostics"].append(f"FMP {endpoint} failed: {e}")
    return out


def v45_financial_inputs(row):
    ticker = v45_text(row.get("Ticker"))
    snap = v45_fmp_snapshot(ticker)
    metrics = snap.get("metrics", {}) or {}
    ratios = snap.get("ratios", {}) or {}
    income = snap.get("income", {}) or {}
    cash = snap.get("cashflow", {}) or {}
    balance = snap.get("balance", {}) or {}
    price = v45_num(row.get("Price"), None)
    revenue = v45_num(income.get("revenue"), None)
    net_income = v45_num(income.get("netIncome"), None)
    fcf = v45_num(cash.get("freeCashFlow"), None)
    total_debt = v45_num(balance.get("totalDebt"), None)
    equity = v45_num(balance.get("totalStockholdersEquity"), None)
    debt_equity = v45_num(metrics.get("debtToEquityTTM") or ratios.get("debtEquityRatioTTM"), None)
    if debt_equity is None and total_debt is not None and equity not in (None, 0):
        debt_equity = total_debt / equity
    pe = v45_num(v45_row_metric(row, "PE Ratio", "P/E", "Trailing PE", default=None), None)
    if pe is None:
        pe = v45_num(metrics.get("peRatioTTM") or ratios.get("priceEarningsRatioTTM") or snap.get("profile", {}).get("pe"), None)
    fpe = v45_num(v45_row_metric(row, "Forward PE", "forwardPE", default=None), None)
    peg = v45_num(v45_row_metric(row, "PEG Ratio", "PEG", default=None), None)
    if peg is None:
        peg = v45_num(metrics.get("pegRatioTTM"), None)
    rev_growth = v45_num(v45_row_metric(row, "Revenue Growth", "Revenue Growth %", default=None), None)
    eps_growth = v45_num(v45_row_metric(row, "EPS Growth", "Earnings Growth %", "Earnings Growth", default=None), None)
    gross_margin = v45_num(metrics.get("grossProfitMarginTTM") or ratios.get("grossProfitMarginTTM"), None)
    if gross_margin is not None and gross_margin < 2:
        gross_margin *= 100
    operating_margin = v45_num(metrics.get("operatingProfitMarginTTM") or ratios.get("operatingProfitMarginTTM"), None)
    if operating_margin is not None and operating_margin < 2:
        operating_margin *= 100
    return {
        "price": price, "pe": pe, "forward_pe": fpe, "peg": peg,
        "revenue_growth": rev_growth, "eps_growth": eps_growth,
        "revenue": revenue, "net_income": net_income, "free_cash_flow": fcf,
        "debt_equity": debt_equity, "gross_margin": gross_margin, "operating_margin": operating_margin,
        "diagnostics": snap.get("diagnostics", []),
    }


def v45_assess_metric(name, value, row):
    b = v45_benchmarks(row)
    if value is None:
        return {"assessment": "Unavailable", "tone": "neutral", "explain": f"{name} was not returned by the connected sources, so it should not be used as a primary reason to buy or avoid."}
    v = v45_num(value, None)
    if name == "RSI":
        if v < 30: return {"assessment": "Oversold", "tone": "positive", "explain": "RSI below 30 can mean the stock is oversold, but it still needs confirmation because weak stocks can stay oversold."}
        if v < 50: return {"assessment": "Weak / recovering", "tone": "caution", "explain": "RSI below 50 suggests momentum is not fully healthy yet."}
        if v <= 70: return {"assessment": "Healthy", "tone": "positive", "explain": "RSI between 50 and 70 suggests positive momentum without being extremely overbought."}
        return {"assessment": "Overbought risk", "tone": "caution", "explain": "RSI above 70 can signal strong momentum, but the entry may be extended and vulnerable to a pullback."}
    if name == "Volume Ratio":
        if v < .75: return {"assessment": "Below normal", "tone": "caution", "explain": "The move lacks strong volume confirmation. Customers should be more careful chasing strength."}
        if v <= 1.25: return {"assessment": "Normal", "tone": "neutral", "explain": "Volume is close to normal, so price action is neither strongly confirmed nor concerning."}
        if v <= 2.0: return {"assessment": "Strong", "tone": "positive", "explain": "Above-average volume suggests stronger participation behind the move."}
        return {"assessment": "Very strong", "tone": "positive", "explain": "Very high volume suggests institutions may be involved, but also check for news-driven volatility."}
    if name == "ATR %":
        if v < 2: return {"assessment": "Low volatility", "tone": "positive", "explain": "Lower volatility generally allows tighter risk control."}
        if v < 5: return {"assessment": "Tradable", "tone": "positive", "explain": "Volatility is manageable for normal position sizing."}
        if v < 8: return {"assessment": "Elevated", "tone": "caution", "explain": "Expect wider swings. Use smaller position sizing and a disciplined stop."}
        return {"assessment": "High risk", "tone": "caution", "explain": "High volatility can create opportunity, but position size should be reduced."}
    if name in ["P/E", "Forward P/E"]:
        if v < 0: return {"assessment": "Negative earnings", "tone": "caution", "explain": "A negative P/E means the company is currently unprofitable. This is speculative unless growth and cash flow are improving."}
        if v <= b["pe_good"]: return {"assessment": "Attractive vs peers", "tone": "positive", "explain": f"This is reasonable for {b['label']} where a good P/E is often below about {b['pe_good']}."}
        if v <= b["pe_fair"]: return {"assessment": "Fair / acceptable", "tone": "neutral", "explain": f"The valuation is acceptable for {b['label']}, but the company needs continued growth to justify it."}
        if v <= b["pe_high"]: return {"assessment": "Premium valuation", "tone": "caution", "explain": "Investors are paying a premium. That can work if growth remains strong, but downside risk increases if growth slows."}
        return {"assessment": "Expensive", "tone": "caution", "explain": "The valuation is high relative to common peer ranges. Require strong growth, margins, and catalysts before buying."}
    if name == "PEG":
        if v <= 0: return {"assessment": "Not meaningful", "tone": "neutral", "explain": "PEG is not useful when earnings growth is negative or unavailable."}
        if v <= b["peg_good"]: return {"assessment": "Attractive growth-adjusted valuation", "tone": "positive", "explain": "A lower PEG suggests the stock may be reasonably priced relative to expected growth."}
        if v <= 2.5: return {"assessment": "Fair", "tone": "neutral", "explain": "PEG is acceptable but not a strong standalone reason to buy."}
        return {"assessment": "Growth may be expensive", "tone": "caution", "explain": "The stock may be expensive relative to its growth rate."}
    if name == "Revenue Growth":
        if v >= b["rev_good"]*1.7: return {"assessment": "Excellent", "tone": "positive", "explain": f"Revenue growth is well above what is typically strong for {b['label']}."}
        if v >= b["rev_good"]: return {"assessment": "Above average", "tone": "positive", "explain": f"Revenue growth is healthy relative to {b['label']}."}
        if v >= 0: return {"assessment": "Modest", "tone": "neutral", "explain": "Revenue is growing, but not fast enough to be a strong bullish catalyst by itself."}
        return {"assessment": "Declining", "tone": "caution", "explain": "Revenue contraction is a warning sign and needs explanation."}
    if name == "EPS Growth":
        if v >= b["eps_good"]*2: return {"assessment": "Excellent", "tone": "positive", "explain": "Earnings are growing strongly, which supports valuation and analyst targets."}
        if v >= b["eps_good"]: return {"assessment": "Healthy", "tone": "positive", "explain": "Earnings growth is supportive of the investment case."}
        if v >= 0: return {"assessment": "Modest", "tone": "neutral", "explain": "Earnings are growing, but the pace is not a major catalyst."}
        return {"assessment": "Declining", "tone": "caution", "explain": "Negative earnings growth can pressure valuation."}
    if name == "Debt/Equity":
        if v <= b["debt_good"]: return {"assessment": "Manageable", "tone": "positive", "explain": "Debt does not appear excessive for this type of business."}
        if v <= b["debt_good"]*2: return {"assessment": "Watch", "tone": "neutral", "explain": "Debt is not automatically dangerous, but it should be monitored."}
        return {"assessment": "Elevated", "tone": "caution", "explain": "Debt looks elevated and may limit flexibility if growth slows or rates remain high."}
    return {"assessment": "Available", "tone": "neutral", "explain": "Metric is available and should be interpreted with the broader thesis."}


@st.cache_data(ttl=900)
def v45_company_news(ticker):
    ticker = v45_text(ticker).upper().strip()
    rows, diag = [], []
    if not ticker:
        return {"rows": [], "diagnostics": ["missing ticker"]}
    # use existing V43/V44 helpers when present
    try:
        data = v432_company_news_items(ticker)
        rows = data.get("rows", []) or []
        diag += data.get("diagnostics", []) or []
    except Exception as e:
        diag.append(f"v432 company news failed: {e}")
    if not rows and v45_secret("NEWSAPI_KEY"):
        try:
            data, status = v432_http_json("https://newsapi.org/v2/everything", params={"q": f'({ticker} OR "{ticker} stock") AND (earnings OR analyst OR revenue OR AI OR growth OR shares OR stock)', "language": "en", "sortBy": "publishedAt", "pageSize": 8, "apiKey": v45_secret("NEWSAPI_KEY")})
            diag.append(f"NewsAPI ticker query status={status}")
            if isinstance(data, dict):
                for a in data.get("articles", [])[:8]:
                    h = v45_text(a.get("title"))
                    if h:
                        rows.append({"headline": h, "source": v45_text((a.get("source") or {}).get("name"), "NewsAPI"), "url": v45_text(a.get("url")), "provider": "NewsAPI ticker query"})
        except Exception as e:
            diag.append(f"NewsAPI ticker query failed: {e}")
    return {"rows": rows[:8], "diagnostics": diag}


def v45_classify_news(rows):
    bullish_terms = ["beat", "raises", "raised", "upgrade", "strong", "growth", "record", "profit", "partnership", "contract", "approval", "demand", "margin", "buy"]
    bearish_terms = ["miss", "cut", "cuts", "downgrade", "lawsuit", "probe", "layoff", "slowing", "weak", "warning", "risk", "sell", "drops", "falls", "slump"]
    bullish, bearish, neutral = [], [], []
    for r in rows:
        h = v45_text(r.get("headline"))
        low = h.lower()
        if any(t in low for t in bullish_terms): bullish.append(h)
        elif any(t in low for t in bearish_terms): bearish.append(h)
        else: neutral.append(h)
    score = max(0, min(100, 50 + len(bullish)*8 - len(bearish)*8))
    sentiment = "Bullish" if score >= 66 else ("Cautious" if score <= 42 else "Mixed / Neutral")
    return {"score": score, "sentiment": sentiment, "bullish": bullish[:3], "bearish": bearish[:3], "neutral": neutral[:5]}


@st.cache_data(ttl=1800)
def v45_analyst_data(ticker, price=0, analyst_target=0, analyst_count=0):
    ticker = v45_text(ticker).upper().strip()
    out = {"consensus": analyst_target, "high": 0, "low": 0, "count": int(v45_num(analyst_count,0) or 0), "rating_trend": "Unknown", "firm_rows": [], "target_news": [], "estimates": [], "diagnostics": []}
    # start with v44 if available
    try:
        base = v44_analyst_intelligence(ticker, price=price, analyst_target=analyst_target, analyst_count=analyst_count)
        for k in ["consensus", "high", "low", "count", "rating_trend"]:
            if base.get(k): out[k] = base.get(k)
        out["firm_rows"] += base.get("firm_rows", []) or []
        out["diagnostics"] += base.get("source_notes", []) or []
    except Exception as e:
        out["diagnostics"].append(f"v44 analyst failed: {e}")
    if ticker and v45_secret("FMP_API_KEY") and "v424_fmp_get" in globals():
        for endpoint, key in [(f"price-target-news/{ticker}", "target_news"), (f"upgrades-downgrades/{ticker}", "firm_rows"), (f"analyst-estimates/{ticker}", "estimates")]:
            try:
                data = v424_fmp_get(endpoint, {"limit": 10})
                out["diagnostics"].append(f"FMP {endpoint} tried")
                if isinstance(data, list):
                    if key == "firm_rows":
                        for d in data[:10]:
                            row = {"Firm": v45_text(d.get("gradingCompany") or d.get("firm") or d.get("analystCompany"), "Analyst firm"), "Action": v45_text(d.get("action") or d.get("newGrade") or "Update"), "Rating": v45_text(d.get("newGrade") or d.get("rating") or "N/A"), "Previous": v45_text(d.get("previousGrade") or "N/A"), "Date": v45_text(d.get("publishedDate") or d.get("date")), "Source": "FMP"}
                            if row not in out["firm_rows"]: out["firm_rows"].append(row)
                    else:
                        out[key] += data[:10]
            except Exception as e:
                out["diagnostics"].append(f"FMP {endpoint} failed: {e}")
    if out["consensus"] and not out["high"]: out["high"] = out["consensus"] * 1.15
    if out["consensus"] and not out["low"]: out["low"] = out["consensus"] * 0.85
    out["upside"] = ((out["consensus"] - price) / price) * 100 if price and out["consensus"] else None
    return out


def v45_trade_levels(row):
    price = v45_num(row.get("Price"), 0) or 0
    try:
        levels = v431_smart_levels(row) if "v431_smart_levels" in globals() else {}
    except Exception:
        levels = {}
    support = v45_num(levels.get("support1") or row.get("Support 1"), 0) or 0
    resistance = v45_num(levels.get("resistance1") or row.get("Resistance 1"), 0) or 0
    support2 = v45_num(levels.get("support2") or row.get("Support 2"), 0) or 0
    stop = v45_num(row.get("Stop Loss"), 0) or 0
    analyst_target = v45_num(row.get("Analyst Target"), 0) or 0
    ai_fv = v45_num(row.get("AI Fair Value"), 0) or 0
    if not support and price: support = price * .95
    if not resistance and price: resistance = price * 1.08
    if not stop and price: stop = min(support * .97, price * .92)
    ideal_low = support if support else price * .95
    ideal_high = min(price * 1.01, resistance * .98) if price and resistance else price * 1.01
    aggressive_low = price * .99 if price else 0
    aggressive_high = min(price * 1.03, resistance) if price and resistance else price * 1.03
    target1 = resistance if resistance else (price * 1.08 if price else 0)
    target2 = analyst_target if analyst_target else (price * 1.18 if price else 0)
    target3 = ai_fv if ai_fv and ai_fv > target2 else (target2 * 1.15 if target2 else 0)
    rr = None
    if price and stop and target1 and price > stop:
        rr = (target1 - price) / (price - stop)
    return {"price": price, "support": support, "support2": support2, "resistance": resistance, "stop": stop, "ideal_low": ideal_low, "ideal_high": ideal_high, "aggressive_low": aggressive_low, "aggressive_high": aggressive_high, "target1": target1, "target2": target2, "target3": target3, "risk_reward": rr}


def v45_financial_health(row):
    f = v45_financial_inputs(row)
    b = v45_benchmarks(row)
    score = 70
    strengths, risks, metrics = [], [], []
    def add_metric(label, value, assessment_name, display=None):
        a = v45_assess_metric(assessment_name, value, row)
        metrics.append({"Metric": label, "Value": display if display is not None else ("N/A" if value is None else (v45_pct(value) if "Growth" in label or "Margin" in label else f"{value:.2f}" if isinstance(value,float) else str(value))), "Peer Context": b["label"], "Assessment": a["assessment"], "Explanation": a["explain"]})
        return a
    # P/E: use forward when available, else trailing
    pe_val = f.get("forward_pe") if f.get("forward_pe") is not None else f.get("pe")
    pe_name = "Forward P/E" if f.get("forward_pe") is not None else "P/E"
    pe_a = add_metric(pe_name, pe_val, pe_name, None if pe_val is None else f"{pe_val:.1f}")
    if pe_a["tone"] == "positive": score += 8; strengths.append(f"Valuation looks {pe_a['assessment'].lower()} relative to {b['label']}.")
    elif pe_a["tone"] == "caution": score -= 8; risks.append(pe_a["explain"])
    for label, key, assess in [("Revenue Growth", "revenue_growth", "Revenue Growth"), ("EPS Growth", "eps_growth", "EPS Growth")]:
        a = add_metric(label, f.get(key), assess, None if f.get(key) is None else v45_pct(f.get(key)))
        if a["tone"] == "positive": score += 7; strengths.append(f"{label} is {a['assessment'].lower()}.")
        elif a["tone"] == "caution": score -= 7; risks.append(a["explain"])
    peg_a = add_metric("PEG", f.get("peg"), "PEG", None if f.get("peg") is None else f"{f.get('peg'):.2f}")
    if peg_a["tone"] == "positive": score += 5; strengths.append("Growth-adjusted valuation is attractive.")
    elif peg_a["tone"] == "caution": score -= 4; risks.append(peg_a["explain"])
    debt_a = add_metric("Debt/Equity", f.get("debt_equity"), "Debt/Equity", None if f.get("debt_equity") is None else f"{f.get('debt_equity'):.2f}")
    if debt_a["tone"] == "positive": score += 5; strengths.append("Debt appears manageable.")
    elif debt_a["tone"] == "caution": score -= 6; risks.append(debt_a["explain"])
    if f.get("free_cash_flow") is not None:
        if f["free_cash_flow"] > 0:
            score += 8; strengths.append("Free cash flow is positive, which supports business quality.")
        else:
            score -= 10; risks.append("Free cash flow is negative, so the company may need external funding or stronger execution.")
    if f.get("net_income") is not None:
        if f["net_income"] > 0:
            score += 5; strengths.append("Net income is positive.")
        else:
            score -= 10; risks.append("Net income is negative; profitability risk needs attention.")
    gm = f.get("gross_margin")
    if gm is not None:
        a = add_metric("Gross Margin", gm, "Revenue Growth", v45_pct(gm))
        if gm >= b["gross_good"]: score += 3; strengths.append("Gross margin is healthy for the business type.")
        elif gm < b["gross_good"]*.6: score -= 3; risks.append("Gross margin appears low relative to the peer context.")
    score = max(0, min(100, round(score)))
    grade = v45_grade(score)
    if not strengths: strengths = ["Financial data is available, but no single financial metric is strong enough to drive the thesis alone."]
    if not risks: risks = ["No major financial red flag was identified from available data."]
    summary = f"Financial Health Grade {grade}: "
    if score >= 83:
        summary += "The company appears financially strong based on available growth, valuation, profitability, cash flow, and leverage data."
    elif score >= 72:
        summary += "The company appears financially acceptable, but customers should still confirm growth, valuation, and cash flow before buying."
    elif score >= 60:
        summary += "The financial picture is mixed. This may still be tradable, but it is not a clean quality setup."
    else:
        summary += "The financial picture is weak or speculative based on available data."
    return {"score": score, "grade": grade, "summary": summary, "strengths": strengths[:5], "risks": risks[:5], "metrics": metrics[:8], "inputs": f}


def v45_technical_health(row):
    rsi = v45_num(row.get("RSI"), None)
    vol = v45_num(row.get("Volume Ratio"), None)
    atr = v45_num(row.get("ATR %"), None)
    price = v45_num(row.get("Price"), None)
    score = 70
    metrics, positives, risks = [], [], []
    for label, val, name, suffix in [("RSI", rsi, "RSI", ""), ("Volume Ratio", vol, "Volume Ratio", "x"), ("ATR %", atr, "ATR %", "%")]:
        a = v45_assess_metric(name, val, row)
        display = "N/A" if val is None else (f"{val:.1f}{suffix}" if label != "Volume Ratio" else f"{val:.2f}x")
        metrics.append({"Metric": label, "Value": display, "Assessment": a["assessment"], "Explanation": a["explain"]})
        if a["tone"] == "positive": score += 7; positives.append(f"{label}: {a['assessment']}")
        elif a["tone"] == "caution": score -= 7; risks.append(f"{label}: {a['assessment']} — {a['explain']}")
    try:
        levels = v45_trade_levels(row)
        if price and levels["resistance"] and levels["support"]:
            if price < levels["resistance"] and price > levels["support"]:
                positives.append("Price is between support and resistance; entry discipline matters.")
    except Exception:
        pass
    score = max(0, min(100, round(score)))
    if not positives: positives = ["Technical data is available, but confirmation is not strong enough to stand alone."]
    if not risks: risks = ["No major technical red flag was identified from available indicators."]
    return {"score": score, "grade": v45_grade(score), "metrics": metrics, "positives": positives[:4], "risks": risks[:4]}


def v45_decision(row):
    ticker = v45_text(row.get("Ticker"))
    table_score = v45_num(row.get("Final Conviction"), None)
    if table_score is None:
        table_score = v45_num(row.get("V44 Score"), None)
    if table_score is None:
        table_score = v45_num(row.get("V43 Score"), 70)
    fh = v45_financial_health(row)
    th = v45_technical_health(row)
    news_data = v45_company_news(ticker)
    news = v45_classify_news(news_data.get("rows", []))
    analyst = v45_analyst_data(ticker, price=v45_num(row.get("Price"), 0) or 0, analyst_target=v45_num(row.get("Analyst Target"), 0) or 0, analyst_count=v45_num(row.get("Analyst Count"), 0) or 0)
    levels = v45_trade_levels(row)
    consensus_upside = analyst.get("upside")
    price = levels["price"]
    stop = levels["stop"]
    target2 = levels["target2"]
    expected_return = ((target2 - price) / price * 100) if price and target2 else None
    risk_score = 70
    if levels.get("risk_reward") is not None and levels["risk_reward"] < 1: risk_score -= 15
    if fh["score"] < 65: risk_score -= 10
    if th["score"] < 65: risk_score -= 8
    if news["sentiment"] == "Cautious": risk_score -= 8
    combined = table_score*.40 + fh["score"]*.25 + th["score"]*.15 + (news["score"] or 50)*.10 + min(90, max(40, risk_score))*.10
    combined = max(0, min(99, round(combined, 1)))
    # single customer-facing score: use combined, but also preserve table score in diagnostics only
    decision = "WATCH"
    if combined >= 88 and fh["score"] >= 72 and th["score"] >= 68 and (levels.get("risk_reward") is None or levels["risk_reward"] >= 1.2):
        decision = "BUY ON PULLBACK"
    if combined >= 90 and news["sentiment"] != "Cautious" and (levels.get("risk_reward") is None or levels["risk_reward"] >= 1.5):
        decision = "BUY NOW / ACCUMULATE"
    if combined < 72:
        decision = "WAIT"
    if fh["score"] < 58:
        decision = "AVOID / SPECULATIVE"
    if levels.get("risk_reward") is not None and levels["risk_reward"] < 1:
        decision = "WAIT FOR BETTER ENTRY"
    risk = "Low" if risk_score >= 78 else ("Moderate" if risk_score >= 62 else "High")
    horizon = "3-12 months" if th["score"] >= 70 else "6-12 months"
    why = []
    why += fh["strengths"][:2]
    if analyst.get("count"): why.append(f"Wall Street coverage is meaningful with {analyst.get('count')} analysts and consensus upside of {v45_pct(consensus_upside)}.")
    if news["bullish"]: why.append("Recent news includes potential bullish catalysts.")
    why += th["positives"][:1]
    risks = []
    risks += fh["risks"][:2]
    risks += th["risks"][:2]
    if news["bearish"]: risks.append("Recent headlines include bearish or cautionary risks.")
    if consensus_upside is not None and consensus_upside < 10: risks.append("Analyst consensus upside is limited, so valuation support may be weaker.")
    return {"ticker": ticker, "score": combined, "table_score": table_score, "decision": decision, "risk": risk, "horizon": horizon, "expected_return": expected_return, "why": why[:5], "risks": risks[:5], "financial": fh, "technical": th, "news": news, "news_rows": news_data.get("rows", []), "news_diag": news_data.get("diagnostics", []), "analyst": analyst, "levels": levels}


def v45_thesis(row, d=None):
    if d is None: d = v45_decision(row)
    ticker = d["ticker"] or v45_text(row.get("Ticker"))
    company = v45_text(row.get("Company"), ticker)
    target = v45_money(d["levels"].get("target2"))
    entry = f"{v45_money(d['levels'].get('ideal_low'))} - {v45_money(d['levels'].get('ideal_high'))}"
    stop = v45_money(d["levels"].get("stop"))
    main_strength = d["why"][0] if d["why"] else "the setup has some supportive signals"
    main_risk = d["risks"][0] if d["risks"] else "normal market and execution risk"
    return (f"{company} ({ticker}) is rated **{d['decision']}** with a {d['score']:.1f}/100 customer-facing confidence score. "
            f"The strongest part of the thesis is that {main_strength[0].lower() + main_strength[1:] if main_strength else 'the evidence is constructive'}. "
            f"The preferred entry zone is **{entry}**, with a risk-control level near **{stop}** and a base target around **{target}**. "
            f"The main risk is that {main_risk[0].lower() + main_risk[1:] if main_risk else 'conditions may weaken'}. "
            f"This is intended as a research decision framework, not a guarantee of performance.")


def render_v45_decision_card(row):
    d = v45_decision(row)
    company = v45_text(row.get("Company"), d["ticker"])
    st.markdown(f"## {d['ticker']} — {company}")
    with st.container(border=True):
        st.markdown(f"### 🎯 Final Decision: **{d['decision']}**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Confidence", f"{d['score']:.1f}/100")
        c2.metric("Risk", d["risk"])
        c3.metric("Time Horizon", d["horizon"])
        c4.metric("Base Return", v45_pct(d.get("expected_return")))
        st.markdown(v45_thesis(row, d))
        left, right = st.columns(2)
        with left:
            st.markdown("#### Why this could work")
            for x in d["why"]: st.markdown(f"✓ {v45_text(x)}")
        with right:
            st.markdown("#### What could go wrong")
            for x in d["risks"]: st.markdown(f"⚠️ {v45_text(x)}")


def render_v45_trade_plan(row):
    d = v45_decision(row); l = d["levels"]
    with st.container(border=True):
        st.markdown("### 📍 Trade Plan: Entry, Exit & Risk Control")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Current Price", v45_money(l["price"]))
        c2.metric("Ideal Entry", f"{v45_money(l['ideal_low'])} - {v45_money(l['ideal_high'])}")
        c3.metric("Aggressive Entry", f"{v45_money(l['aggressive_low'])} - {v45_money(l['aggressive_high'])}")
        c4.metric("Stop / Invalidation", v45_money(l["stop"]))
        c5,c6,c7,c8 = st.columns(4)
        c5.metric("Target 1", v45_money(l["target1"]))
        c6.metric("Target 2", v45_money(l["target2"]))
        c7.metric("Target 3", v45_money(l["target3"]))
        rr = l.get("risk_reward")
        c8.metric("Risk/Reward", "N/A" if rr is None else f"{rr:.2f}:1")
        if rr is not None and rr < 1:
            st.warning("The first target does not offer enough reward for the downside risk. This is a better watchlist candidate than an immediate buy.")
        else:
            st.info("Use the entry zone and stop level to define risk before buying. Avoid chasing far above the entry range unless a breakout is confirmed with strong volume.")


def render_v45_financial_health(row):
    fh = v45_financial_health(row)
    with st.container(border=True):
        st.markdown(f"### 🏢 Financial Health: **{fh['grade']}**")
        c1,c2,c3 = st.columns(3)
        c1.metric("Financial Score", f"{fh['score']}/100")
        c2.metric("Peer Context", v45_benchmarks(row)["label"])
        c3.metric("Verdict", "Strong" if fh["score"] >= 83 else ("Acceptable" if fh["score"] >= 72 else ("Mixed" if fh["score"] >= 60 else "Weak")))
        st.markdown(fh["summary"])
        if fh["metrics"]:
            st.dataframe(pd.DataFrame(fh["metrics"]), use_container_width=True, hide_index=True)
        left, right = st.columns(2)
        with left:
            st.markdown("#### Financial strengths")
            for x in fh["strengths"]: st.markdown(f"✓ {x}")
        with right:
            st.markdown("#### Financial concerns")
            for x in fh["risks"]: st.markdown(f"⚠️ {x}")


def render_v45_analyst_intelligence(row):
    ticker = v45_text(row.get("Ticker"))
    price = v45_num(row.get("Price"), 0) or 0
    a = v45_analyst_data(ticker, price=price, analyst_target=v45_num(row.get("Analyst Target"),0) or 0, analyst_count=v45_num(row.get("Analyst Count"),0) or 0)
    with st.container(border=True):
        st.markdown("### 🏦 Top Analyst Intelligence")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Consensus Target", v45_money(a.get("consensus")))
        c2.metric("Upside", v45_pct(a.get("upside")))
        c3.metric("Coverage", str(a.get("count") or "N/A"))
        c4.metric("Rating Trend", a.get("rating_trend", "Unknown"))
        c5,c6 = st.columns(2)
        c5.metric("High Target", v45_money(a.get("high")))
        c6.metric("Low Target", v45_money(a.get("low")))
        st.markdown("**What this means:** Analyst targets help validate whether Wall Street broadly supports the thesis. Strong coverage and positive recommendation trends are supportive, but target prices can lag news and earnings changes.")
        if a.get("firm_rows"):
            st.markdown("#### Recent firm-level analyst actions")
            st.dataframe(pd.DataFrame(a["firm_rows"][:8]), use_container_width=True, hide_index=True)
        elif a.get("target_news"):
            st.markdown("#### Recent analyst target news")
            rows=[]
            for d in a["target_news"][:8]:
                rows.append({"Date": v45_text(d.get("publishedDate") or d.get("date")), "Headline": v45_text(d.get("title") or d.get("newsTitle") or d.get("headline")), "Analyst/Firm": v45_text(d.get("analystName") or d.get("analystCompany") or d.get("site"))})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.warning("The connected API/source did not return firm-level analyst names for this ticker. Showing consensus target, high/low range, coverage and rating trend instead.")
        with st.expander("Analyst source diagnostics", expanded=False):
            for x in a.get("diagnostics", []): st.caption(x)


def render_v45_news_catalysts(row):
    ticker = v45_text(row.get("Ticker"))
    nd = v45_company_news(ticker); c = v45_classify_news(nd.get("rows", []))
    with st.container(border=True):
        st.markdown("### 📰 Market Catalysts & Risks")
        c1,c2,c3 = st.columns(3)
        c1.metric("News Sentiment", c["sentiment"])
        c2.metric("News Score", f"{c['score']}/100")
        c3.metric("Headlines Checked", len(nd.get("rows", [])))
        left, right = st.columns(2)
        with left:
            st.markdown("#### Bullish catalysts")
            for h in (c["bullish"] or ["No clear bullish catalyst isolated from recent headlines."]): st.markdown(f"✓ {h}")
        with right:
            st.markdown("#### Bearish risks")
            for h in (c["bearish"] or ["No clear bearish headline risk isolated from recent headlines."]): st.markdown(f"⚠️ {h}")
        if nd.get("rows"):
            st.markdown("#### Recent ticker headlines")
            for r in nd.get("rows", [])[:6]:
                h, src, url = v45_text(r.get("headline")), v45_text(r.get("source")), v45_text(r.get("url"))
                st.markdown(f"• [{h}]({url}) · _{src}_" if url else f"• {h} · _{src}_")
        with st.expander("News diagnostics", expanded=False):
            for x in nd.get("diagnostics", []): st.caption(x)


def render_v45_technical_health(row):
    th = v45_technical_health(row)
    with st.container(border=True):
        st.markdown(f"### 📈 Technical Health: **{th['grade']}**")
        c1,c2 = st.columns(2)
        c1.metric("Technical Score", f"{th['score']}/100")
        c2.metric("Purpose", "Timing + risk control")
        if th["metrics"]:
            st.dataframe(pd.DataFrame(th["metrics"]), use_container_width=True, hide_index=True)
        left, right = st.columns(2)
        with left:
            st.markdown("#### Constructive signals")
            for x in th["positives"]: st.markdown(f"✓ {x}")
        with right:
            st.markdown("#### Timing watchouts")
            for x in th["risks"]: st.markdown(f"⚠️ {x}")


def v45_quality_check(row):
    d = v45_decision(row)
    checks = {
        "Decision generated": bool(d.get("decision")),
        "Entry generated": bool(d["levels"].get("ideal_low") and d["levels"].get("ideal_high")),
        "Stop generated": bool(d["levels"].get("stop")),
        "Targets generated": bool(d["levels"].get("target1") and d["levels"].get("target2")),
        "Financial health generated": bool(d["financial"].get("score")),
        "News checked": len(d.get("news_rows", [])) > 0,
        "Analyst data generated": bool(d["analyst"].get("consensus") or d["analyst"].get("count")),
        "Final thesis generated": bool(v45_thesis(row, d)),
        "Score consistency verified": abs((d.get("table_score") or 0) - v45_num(row.get("Final Conviction"), d.get("table_score") or 0)) < .01,
    }
    score = round(sum(1 for v in checks.values() if v) / len(checks) * 100)
    return score, checks


def render_v45_final_thesis(row):
    d = v45_decision(row)
    with st.container(border=True):
        st.markdown("### 🧠 Final Investment Thesis")
        st.markdown(v45_thesis(row, d))
        st.caption("This section is designed for customer readability: decision, why it matters, entry, exit, and risk. It is research support, not personalized financial advice.")


def render_v45_qa(row):
    score, checks = v45_quality_check(row)
    with st.expander("🧪 Advanced QA / Diagnostics", expanded=False):
        st.metric("Ticker Research Quality", f"{score}/100")
        st.dataframe(pd.DataFrame([{"Check": k, "Status": "✅" if v else "❌"} for k,v in checks.items()]), use_container_width=True, hide_index=True)
        state = read_state() if "read_state" in globals() else {}
        st.metric("GitHub Persisted", "✅" if state.get("github_persisted") or v45_text(state.get("version")) == "V45.0" else "❌")
        with st.expander("Raw row", expanded=False):
            try: st.json(row if isinstance(row, dict) else dict(row))
            except Exception: st.write(row)


def render_v45_research_page(row):
    render_v45_decision_card(row)
    render_v45_trade_plan(row)
    render_v45_financial_health(row)
    render_v45_analyst_intelligence(row)
    render_v45_news_catalysts(row)
    render_v45_technical_health(row)
    if "render_detail_chart_v4184" in globals():
        try: render_detail_chart_v4184(row)
        except Exception: pass
    render_v45_final_thesis(row)
    render_v45_qa(row)


def render_detail(row):
    render_v45_research_page(row)


def render_v431_professional_research_card(row):
    render_v45_research_page(row)


def render_score_help():
    with st.expander("📘 How to use this dashboard", expanded=False):
        st.markdown("""
        **Start with the decision, not the score.** The V45 research page is designed to answer: should I buy it, where should I buy, where is the stop, what are the targets, and what could go wrong.

        **Key sections:**
        - **Final Decision:** Buy now, buy on pullback, watch, wait, or avoid.
        - **Trade Plan:** entry zone, stop, targets, and reward/risk.
        - **Financial Health:** valuation, growth, profitability, cash flow, and debt in plain English.
        - **Top Analyst Intelligence:** consensus, upside, firm-level actions when the API returns them.
        - **Market Catalysts & Risks:** ticker-specific headlines classified into bullish and bearish signals.
        - **Technical Health:** RSI, volume, ATR, support and resistance explained for timing.
        """)


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Institutional-style stock research pages with decision, entry, target, risk, financial health, analyst intelligence, and ticker-specific news.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version")) == "V45.0"
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: customer-facing research is visible; admin controls remain hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")



# =========================
# V45.1 ADVISOR-STYLE DECISION ENGINE
# =========================
# Purpose:
# - Customer view: simple actionable advice, entry/exit/targets, financial explanation, analyst view, news catalysts.
# - Admin view: source health/QA trace hidden in expanders.
# - Data rule: never show fake $0.00 targets; attempt live enrichment before rendering ticker detail.

def v451_valid_number(x, positive=False):
    v = v45_num(x, None) if "v45_num" in globals() else None
    if v is None:
        return None
    try:
        if math.isnan(v) or math.isinf(v):
            return None
    except Exception:
        pass
    if positive and v <= 0:
        return None
    return v


def v451_first_valid(*values, positive=False):
    for x in values:
        v = v451_valid_number(x, positive=positive)
        if v is not None:
            return v
    return None


def v451_clean_ticker(ticker):
    t = v45_text(ticker, "").upper().strip() if "v45_text" in globals() else str(ticker or "").upper().strip()
    return t


def v451_ticker_variants(ticker):
    t = v451_clean_ticker(ticker)
    variants = [t]
    if "-" in t:
        variants.append(t.replace("-", "."))
    if "." in t:
        variants.append(t.replace(".", "-"))
    # Deduplicate while preserving order
    out = []
    for x in variants:
        if x and x not in out:
            out.append(x)
    return out


def v451_fmp_get_try(endpoint, params=None):
    if "v424_fmp_get" not in globals():
        return None, "FMP helper unavailable"
    try:
        data = v424_fmp_get(endpoint, params)
        ok = bool(data) and data not in ({}, [])
        return data, "returned" if ok else "empty"
    except Exception as e:
        return None, f"failed: {e}"


def v451_yahoo_info(ticker):
    t = v451_clean_ticker(ticker)
    out = {}
    try:
        obj = yf.Ticker(t)
        info = getattr(obj, "info", {}) or {}
        if isinstance(info, dict):
            out.update(info)
    except Exception:
        pass
    return out


@st.cache_data(ttl=900)
def v451_live_analyst_enrichment(ticker, price=0, scan_target=0, scan_count=0, scan_support=""):
    """
    Attempts multiple analyst target / rating sources for ONE ticker.
    Customer view uses the cleaned result. Admin view can inspect diagnostics.
    """
    ticker = v451_clean_ticker(ticker)
    price = v451_valid_number(price, positive=True)
    out = {
        "ticker": ticker,
        "consensus": None,
        "high": None,
        "low": None,
        "median": None,
        "count": int(v451_valid_number(scan_count, positive=True) or 0),
        "rating_trend": v45_text(scan_support or "Unknown") if "v45_text" in globals() else str(scan_support or "Unknown"),
        "firm_rows": [],
        "estimate_rows": [],
        "diagnostics": [],
        "coverage_status": "Limited",
        "data_quality": "Incomplete",
    }

    # Existing scan row is a valid fallback, but never allow zero.
    out["consensus"] = v451_first_valid(scan_target, positive=True)

    # FMP endpoint attempts. Different plan levels expose different endpoint shapes.
    for tv in v451_ticker_variants(ticker):
        endpoints = [
            (f"price-target-consensus/{tv}", None, "FMP price-target-consensus"),
            (f"price-target-summary/{tv}", None, "FMP price-target-summary"),
            (f"analyst-estimates/{tv}", {"limit": 6}, "FMP analyst-estimates"),
            (f"upgrades-downgrades/{tv}", None, "FMP upgrades-downgrades"),
            (f"upgrades-downgrades-consensus/{tv}", None, "FMP upgrades-downgrades-consensus"),
            (f"price-target/{tv}", {"limit": 10}, "FMP price-target"),
        ]
        for endpoint, params, label in endpoints:
            data, status = v451_fmp_get_try(endpoint, params)
            out["diagnostics"].append(f"{label}: {status}")
            if not data:
                continue
            rows = data if isinstance(data, list) else [data]
            for d in rows[:12]:
                if not isinstance(d, dict):
                    continue
                # Target fields across FMP endpoint shapes
                out["consensus"] = out["consensus"] or v451_first_valid(
                    d.get("targetConsensus"),
                    d.get("targetMean"),
                    d.get("targetMedian"),
                    d.get("priceTargetAverage"),
                    d.get("priceTarget"),
                    d.get("adjPriceTarget"),
                    d.get("targetPrice"),
                    positive=True,
                )
                out["high"] = out["high"] or v451_first_valid(
                    d.get("targetHigh"),
                    d.get("targetHighPrice"),
                    d.get("priceTargetHigh"),
                    d.get("high"),
                    positive=True,
                )
                out["low"] = out["low"] or v451_first_valid(
                    d.get("targetLow"),
                    d.get("targetLowPrice"),
                    d.get("priceTargetLow"),
                    d.get("low"),
                    positive=True,
                )
                out["median"] = out["median"] or v451_first_valid(
                    d.get("targetMedian"),
                    d.get("priceTargetMedian"),
                    positive=True,
                )
                cnt = v451_first_valid(d.get("numberOfAnalysts"), d.get("analystCount"), d.get("analystsCount"), d.get("analystRatingsbuy"), positive=True)
                if cnt:
                    out["count"] = max(out["count"], int(cnt))

                # Firm-level action rows when available
                firm = v45_text(d.get("gradingCompany") or d.get("analystCompany") or d.get("firm") or d.get("analystName"), "") if "v45_text" in globals() else ""
                action = v45_text(d.get("action") or d.get("newGrade") or d.get("rating") or d.get("publishedDate"), "") if "v45_text" in globals() else ""
                pt = v451_first_valid(d.get("priceTarget"), d.get("adjPriceTarget"), d.get("targetPrice"), positive=True)
                if firm or pt or ("upgrade" in label.lower()) or ("price-target" in label.lower()):
                    row = {
                        "Date": v45_text(d.get("publishedDate") or d.get("date") or d.get("period"), ""),
                        "Firm / Analyst": firm or "Analyst source",
                        "Action / Rating": action or "Target update",
                        "Target": "N/A" if pt is None else v45_money(pt),
                        "Source Type": label.replace("FMP ", ""),
                    }
                    if row not in out["firm_rows"]:
                        out["firm_rows"].append(row)

                # Estimate rows for future earnings/revenue context
                eps_est = v451_first_valid(d.get("estimatedEpsAvg"), d.get("estimatedEpsHigh"), d.get("estimatedEpsLow"), d.get("epsAvg"), positive=False)
                rev_est = v451_first_valid(d.get("estimatedRevenueAvg"), d.get("revenueAvg"), positive=True)
                if eps_est is not None or rev_est is not None:
                    erow = {
                        "Period": v45_text(d.get("date") or d.get("period") or d.get("fiscalDateEnding"), ""),
                        "EPS Estimate": "N/A" if eps_est is None else f"{eps_est:.2f}",
                        "Revenue Estimate": "N/A" if rev_est is None else v45_money(rev_est),
                    }
                    if erow not in out["estimate_rows"]:
                        out["estimate_rows"].append(erow)

    # Finnhub price target + recommendation fallback.
    fh = v45_secret("FINNHUB_API_KEY", "") if "v45_secret" in globals() else ""
    if fh:
        for tv in v451_ticker_variants(ticker):
            data, status = v432_http_json("https://finnhub.io/api/v1/stock/price-target", params={"symbol": tv, "token": fh}) if "v432_http_json" in globals() else (None, "http helper unavailable")
            out["diagnostics"].append(f"Finnhub price-target {tv}: status={status}")
            if isinstance(data, dict):
                out["consensus"] = out["consensus"] or v451_first_valid(data.get("targetMean"), data.get("targetMedian"), positive=True)
                out["high"] = out["high"] or v451_first_valid(data.get("targetHigh"), positive=True)
                out["low"] = out["low"] or v451_first_valid(data.get("targetLow"), positive=True)
                out["median"] = out["median"] or v451_first_valid(data.get("targetMedian"), positive=True)

            data, status = v432_http_json("https://finnhub.io/api/v1/stock/recommendation", params={"symbol": tv, "token": fh}) if "v432_http_json" in globals() else (None, "http helper unavailable")
            out["diagnostics"].append(f"Finnhub recommendation {tv}: status={status}")
            if isinstance(data, list) and data:
                d = data[0]
                sb = int(v451_valid_number(d.get("strongBuy"), positive=False) or 0)
                b = int(v451_valid_number(d.get("buy"), positive=False) or 0)
                h = int(v451_valid_number(d.get("hold"), positive=False) or 0)
                s = int(v451_valid_number(d.get("sell"), positive=False) or 0) + int(v451_valid_number(d.get("strongSell"), positive=False) or 0)
                total = sb + b + h + s
                if total:
                    out["count"] = max(out["count"], total)
                    if sb + b > h + s:
                        out["rating_trend"] = "Bullish / positive recommendation mix"
                    elif s > sb + b:
                        out["rating_trend"] = "Bearish / negative recommendation mix"
                    else:
                        out["rating_trend"] = "Mixed / hold-heavy recommendation mix"

    # Yahoo fallback for basic analyst data.
    yi = v451_yahoo_info(ticker)
    if yi:
        out["diagnostics"].append("Yahoo/yfinance info: returned")
        out["consensus"] = out["consensus"] or v451_first_valid(yi.get("targetMeanPrice"), yi.get("targetMedianPrice"), positive=True)
        out["high"] = out["high"] or v451_first_valid(yi.get("targetHighPrice"), positive=True)
        out["low"] = out["low"] or v451_first_valid(yi.get("targetLowPrice"), positive=True)
        out["median"] = out["median"] or v451_first_valid(yi.get("targetMedianPrice"), positive=True)
        cnt = v451_first_valid(yi.get("numberOfAnalystOpinions"), positive=True)
        if cnt:
            out["count"] = max(out["count"], int(cnt))
        rec = yi.get("recommendationKey") or yi.get("recommendationMean")
        if rec and out["rating_trend"] in ("Unknown", "", None):
            out["rating_trend"] = f"Yahoo recommendation: {rec}"
    else:
        out["diagnostics"].append("Yahoo/yfinance info: empty/unavailable")

    # Never fabricate high/low from zero. If consensus is valid but range missing, show range unavailable.
    if price and out.get("consensus"):
        out["upside"] = ((out["consensus"] - price) / price) * 100
    else:
        out["upside"] = None

    if out.get("consensus") and out.get("count"):
        out["coverage_status"] = "Strong" if out["count"] >= 20 else ("Moderate" if out["count"] >= 5 else "Limited")
        out["data_quality"] = "Complete"
    elif out.get("count"):
        out["coverage_status"] = "Coverage active, target unavailable"
        out["data_quality"] = "Partial"
    else:
        out["coverage_status"] = "Unavailable"
        out["data_quality"] = "Incomplete"
    return out


@st.cache_data(ttl=900)
def v451_live_financial_enrichment(ticker, row_json=None):
    """
    Live financial field mapper. Uses row fields first, then FMP ratios/key metrics/growth/statements, then Yahoo.
    """
    ticker = v451_clean_ticker(ticker)
    try:
        row = json.loads(row_json) if row_json else {}
    except Exception:
        row = {}
    out = {
        "ticker": ticker,
        "pe": None,
        "forward_pe": None,
        "peg": None,
        "revenue_growth": None,
        "eps_growth": None,
        "gross_margin": None,
        "operating_margin": None,
        "net_margin": None,
        "debt_equity": None,
        "roe": None,
        "free_cash_flow": None,
        "revenue": None,
        "net_income": None,
        "diagnostics": [],
        "data_quality": "Incomplete",
    }

    # Row / scan fields.
    out["pe"] = v451_first_valid(row.get("PE Ratio"), row.get("P/E"), row.get("Trailing PE"), positive=False)
    out["forward_pe"] = v451_first_valid(row.get("Forward PE"), row.get("forwardPE"), positive=False)
    out["peg"] = v451_first_valid(row.get("PEG Ratio"), row.get("PEG"), positive=False)
    out["revenue_growth"] = v451_first_valid(row.get("Revenue Growth"), row.get("Revenue Growth %"), positive=False)
    out["eps_growth"] = v451_first_valid(row.get("EPS Growth"), row.get("Earnings Growth %"), row.get("Earnings Growth"), positive=False)
    out["debt_equity"] = v451_first_valid(row.get("Debt/Equity"), row.get("Debt To Equity"), positive=False)
    if any(v is not None for k, v in out.items() if k not in ["ticker", "diagnostics", "data_quality"]):
        out["diagnostics"].append("Scan row fields: partially mapped")
    else:
        out["diagnostics"].append("Scan row fields: no detailed financial fields")

    # FMP attempts
    for tv in v451_ticker_variants(ticker):
        endpoints = [
            ("metrics", f"key-metrics-ttm/{tv}", None),
            ("ratios", f"ratios-ttm/{tv}", None),
            ("growth", f"financial-growth/{tv}", {"limit": 1}),
            ("income", f"income-statement/{tv}", {"limit": 2}),
            ("cashflow", f"cash-flow-statement/{tv}", {"limit": 2}),
            ("balance", f"balance-sheet-statement/{tv}", {"limit": 2}),
            ("profile", f"profile/{tv}", None),
        ]
        got = {}
        for label, endpoint, params in endpoints:
            data, status = v451_fmp_get_try(endpoint, params)
            out["diagnostics"].append(f"FMP {endpoint}: {status}")
            if data:
                rows = data if isinstance(data, list) else [data]
                got[label] = rows
        m = (got.get("metrics") or [{}])[0] if got.get("metrics") else {}
        r = (got.get("ratios") or [{}])[0] if got.get("ratios") else {}
        g = (got.get("growth") or [{}])[0] if got.get("growth") else {}
        inc_rows = got.get("income") or []
        cf_rows = got.get("cashflow") or []
        bal_rows = got.get("balance") or []
        prof = (got.get("profile") or [{}])[0] if got.get("profile") else {}

        out["pe"] = out["pe"] if out["pe"] is not None else v451_first_valid(m.get("peRatioTTM"), r.get("priceEarningsRatioTTM"), prof.get("pe"), positive=False)
        out["forward_pe"] = out["forward_pe"] if out["forward_pe"] is not None else v451_first_valid(m.get("forwardPE"), r.get("forwardPE"), positive=False)
        out["peg"] = out["peg"] if out["peg"] is not None else v451_first_valid(m.get("pegRatioTTM"), r.get("pegRatioTTM"), positive=False)
        out["revenue_growth"] = out["revenue_growth"] if out["revenue_growth"] is not None else v451_first_valid(g.get("revenueGrowth"), g.get("growthRevenue"), positive=False)
        out["eps_growth"] = out["eps_growth"] if out["eps_growth"] is not None else v451_first_valid(g.get("epsgrowth"), g.get("epsGrowth"), g.get("growthEPS"), positive=False)
        out["gross_margin"] = out["gross_margin"] if out["gross_margin"] is not None else v451_first_valid(m.get("grossProfitMarginTTM"), r.get("grossProfitMarginTTM"), positive=False)
        out["operating_margin"] = out["operating_margin"] if out["operating_margin"] is not None else v451_first_valid(m.get("operatingProfitMarginTTM"), r.get("operatingProfitMarginTTM"), positive=False)
        out["net_margin"] = out["net_margin"] if out["net_margin"] is not None else v451_first_valid(m.get("netProfitMarginTTM"), r.get("netProfitMarginTTM"), positive=False)
        out["debt_equity"] = out["debt_equity"] if out["debt_equity"] is not None else v451_first_valid(m.get("debtToEquityTTM"), r.get("debtEquityRatioTTM"), positive=False)
        out["roe"] = out["roe"] if out["roe"] is not None else v451_first_valid(m.get("roeTTM"), r.get("returnOnEquityTTM"), positive=False)

        if inc_rows:
            inc0 = inc_rows[0] if isinstance(inc_rows[0], dict) else {}
            inc1 = inc_rows[1] if len(inc_rows) > 1 and isinstance(inc_rows[1], dict) else {}
            out["revenue"] = out["revenue"] if out["revenue"] is not None else v451_first_valid(inc0.get("revenue"), positive=True)
            out["net_income"] = out["net_income"] if out["net_income"] is not None else v451_first_valid(inc0.get("netIncome"), positive=False)
            if out["revenue_growth"] is None:
                rev0, rev1 = v451_first_valid(inc0.get("revenue"), positive=True), v451_first_valid(inc1.get("revenue"), positive=True)
                if rev0 and rev1:
                    out["revenue_growth"] = ((rev0 - rev1) / rev1) * 100

        if cf_rows:
            cf0 = cf_rows[0] if isinstance(cf_rows[0], dict) else {}
            out["free_cash_flow"] = out["free_cash_flow"] if out["free_cash_flow"] is not None else v451_first_valid(cf0.get("freeCashFlow"), positive=False)

        if out["debt_equity"] is None and bal_rows:
            b0 = bal_rows[0] if isinstance(bal_rows[0], dict) else {}
            debt = v451_first_valid(b0.get("totalDebt"), b0.get("shortTermDebt"), positive=False)
            equity = v451_first_valid(b0.get("totalStockholdersEquity"), b0.get("totalEquity"), positive=False)
            if debt is not None and equity not in (None, 0):
                out["debt_equity"] = debt / equity

    # Normalize percentage-like fields.
    for key in ["revenue_growth", "eps_growth", "gross_margin", "operating_margin", "net_margin", "roe"]:
        v = out.get(key)
        if v is not None and abs(v) < 2:
            out[key] = v * 100

    # Yahoo fallback
    yi = v451_yahoo_info(ticker)
    if yi:
        out["diagnostics"].append("Yahoo/yfinance financial info: returned")
        out["pe"] = out["pe"] if out["pe"] is not None else v451_first_valid(yi.get("trailingPE"), positive=False)
        out["forward_pe"] = out["forward_pe"] if out["forward_pe"] is not None else v451_first_valid(yi.get("forwardPE"), positive=False)
        out["peg"] = out["peg"] if out["peg"] is not None else v451_first_valid(yi.get("pegRatio"), positive=False)
        out["revenue_growth"] = out["revenue_growth"] if out["revenue_growth"] is not None else v451_first_valid(yi.get("revenueGrowth"), positive=False)
        out["eps_growth"] = out["eps_growth"] if out["eps_growth"] is not None else v451_first_valid(yi.get("earningsGrowth"), positive=False)
        out["gross_margin"] = out["gross_margin"] if out["gross_margin"] is not None else v451_first_valid(yi.get("grossMargins"), positive=False)
        out["operating_margin"] = out["operating_margin"] if out["operating_margin"] is not None else v451_first_valid(yi.get("operatingMargins"), positive=False)
        out["debt_equity"] = out["debt_equity"] if out["debt_equity"] is not None else v451_first_valid(yi.get("debtToEquity"), positive=False)
        out["free_cash_flow"] = out["free_cash_flow"] if out["free_cash_flow"] is not None else v451_first_valid(yi.get("freeCashflow"), positive=False)
        out["revenue"] = out["revenue"] if out["revenue"] is not None else v451_first_valid(yi.get("totalRevenue"), positive=True)
        out["net_income"] = out["net_income"] if out["net_income"] is not None else v451_first_valid(yi.get("netIncomeToCommon"), positive=False)
    else:
        out["diagnostics"].append("Yahoo/yfinance financial info: empty/unavailable")

    usable = sum(1 for k in ["pe", "forward_pe", "peg", "revenue_growth", "eps_growth", "debt_equity", "free_cash_flow", "revenue"] if out.get(k) is not None)
    out["data_quality"] = "Complete" if usable >= 5 else ("Partial" if usable >= 3 else "Incomplete")
    return out


@st.cache_data(ttl=600)
def v451_live_news_enrichment(ticker, company=""):
    ticker = v451_clean_ticker(ticker)
    company = v45_text(company or ticker, "") if "v45_text" in globals() else ticker
    rows, diagnostics = [], []

    news_key = v45_secret("NEWSAPI_KEY", "") if "v45_secret" in globals() else ""
    if news_key:
        q = f'({ticker} OR "{company}") AND (stock OR shares OR earnings OR analyst OR target OR guidance OR revenue OR profit OR AI OR acquisition OR lawsuit OR SEC)'
        try:
            data, status = v432_http_json("https://newsapi.org/v2/everything", params={"q": q, "language": "en", "sortBy": "publishedAt", "pageSize": 8, "apiKey": news_key})
            diagnostics.append(f"NewsAPI ticker query: status={status}")
            if isinstance(data, dict):
                for a in data.get("articles", [])[:8]:
                    h = v45_text(a.get("title"), "")
                    if h:
                        rows.append({"headline": h, "source": v45_text((a.get("source") or {}).get("name"), "NewsAPI"), "url": v45_text(a.get("url"), ""), "published": v45_text(a.get("publishedAt"), ""), "provider": "NewsAPI"})
        except Exception as e:
            diagnostics.append(f"NewsAPI ticker query failed: {e}")
    else:
        diagnostics.append("NEWSAPI_KEY missing")

    fh = v45_secret("FINNHUB_API_KEY", "") if "v45_secret" in globals() else ""
    if fh:
        try:
            end = dt.date.today()
            start = end - dt.timedelta(days=30)
            data, status = v432_http_json("https://finnhub.io/api/v1/company-news", params={"symbol": ticker, "from": str(start), "to": str(end), "token": fh})
            diagnostics.append(f"Finnhub company-news: status={status}")
            if isinstance(data, list):
                for a in data[:8]:
                    h = v45_text(a.get("headline"), "")
                    if h and h not in [r["headline"] for r in rows]:
                        rows.append({"headline": h, "source": v45_text(a.get("source"), "Finnhub"), "url": v45_text(a.get("url"), ""), "published": v45_text(a.get("datetime"), ""), "provider": "Finnhub"})
        except Exception as e:
            diagnostics.append(f"Finnhub company-news failed: {e}")
    else:
        diagnostics.append("FINNHUB_API_KEY missing")

    # FMP stock news fallback
    if v45_secret("FMP_API_KEY", "") and "v424_fmp_get" in globals():
        for endpoint, params in [
            ("stock_news", {"tickers": ticker, "limit": 10}),
            (f"stock_news", {"tickers": ticker, "limit": 10}),
        ]:
            data, status = v451_fmp_get_try(endpoint, params)
            diagnostics.append(f"FMP {endpoint}: {status}")
            if data:
                rows_f = data if isinstance(data, list) else [data]
                for a in rows_f[:8]:
                    if not isinstance(a, dict):
                        continue
                    h = v45_text(a.get("title") or a.get("headline"), "")
                    if h and h not in [r["headline"] for r in rows]:
                        rows.append({"headline": h, "source": v45_text(a.get("site") or a.get("source"), "FMP"), "url": v45_text(a.get("url"), ""), "published": v45_text(a.get("publishedDate") or a.get("date"), ""), "provider": "FMP"})
    rows = rows[:10]
    classified = v45_classify_news(rows) if "v45_classify_news" in globals() else {"score": 50, "sentiment": "Mixed / Neutral", "bullish": [], "bearish": []}
    return {"rows": rows, "diagnostics": diagnostics, **classified, "data_quality": "Complete" if rows else "Incomplete"}


def v451_industry_avg_text(row, metric):
    b = v45_benchmarks(row) if "v45_benchmarks" in globals() else {"label": "peers"}
    if metric in ["P/E", "Forward P/E"]:
        return f"Good below ~{b['pe_good']} · fair up to ~{b['pe_fair']} for {b['label']}"
    if metric == "PEG":
        return f"Good near/below ~{b['peg_good']} for {b['label']}"
    if metric == "Revenue Growth":
        return f"Good above ~{b['rev_good']}% for {b['label']}"
    if metric == "EPS Growth":
        return f"Good above ~{b['eps_good']}% for {b['label']}"
    if metric == "Debt/Equity":
        return f"Generally comfortable below ~{b['debt_good']}x for {b['label']}"
    return b.get("label", "peers")


def v451_assess_fin(metric, value, row):
    if "v45_assess_metric" in globals():
        base = v45_assess_metric(metric, value, row)
        return base.get("assessment", "N/A"), base.get("explain", "")
    return "N/A", ""


def v451_research_completeness(row, analyst=None, fin=None, news=None):
    analyst = analyst or {}
    fin = fin or {}
    news = news or {}
    checks = {
        "Price": v451_valid_number(row.get("Price"), positive=True) is not None,
        "Entry / stop / targets": bool((row.get("Entry Range") or "") and v451_valid_number(row.get("Stop Loss"), positive=True)),
        "Analyst target or rating": bool(analyst.get("consensus") or analyst.get("count") or analyst.get("rating_trend") not in ["", "Unknown", None]),
        "Financials": fin.get("data_quality") in ["Complete", "Partial"],
        "Recent ticker news": bool(news.get("rows")),
        "Technical levels": bool(v451_valid_number(row.get("52W Low"), positive=True) and v451_valid_number(row.get("52W High"), positive=True)),
    }
    score = round(sum(1 for v in checks.values() if v) / len(checks) * 100)
    status = "Premium-ready" if score >= 85 else ("Research usable" if score >= 70 else "Data incomplete")
    return score, status, checks



def v451_json_safe_value(x):
    """Convert pandas/numpy/scalar objects into JSON-safe Python values."""
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    try:
        # numpy scalars such as int64/float64
        if hasattr(x, "item"):
            return x.item()
    except Exception:
        pass
    try:
        if isinstance(x, (dt.datetime, dt.date)):
            return x.isoformat()
    except Exception:
        pass
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    try:
        return str(x)
    except Exception:
        return None


def v451_row_to_json(row):
    """Safely serialize a Streamlit table row for cached enrichment functions."""
    try:
        d = dict(row)
    except Exception:
        d = row if isinstance(row, dict) else {}
    safe = {}
    try:
        for k, v in d.items():
            safe[str(k)] = v451_json_safe_value(v)
    except Exception:
        safe = {}
    return json.dumps(safe, default=str)


def v451_decision(row):
    ticker = v45_text(row.get("Ticker"), "") if "v45_text" in globals() else str(row.get("Ticker", ""))
    company = v45_text(row.get("Company"), ticker) if "v45_text" in globals() else ticker
    price = v451_valid_number(row.get("Price"), positive=True) or 0
    table_score = v451_valid_number(row.get("Final Conviction"), positive=False) or 0
    levels = v45_trade_levels(row) if "v45_trade_levels" in globals() else {}
    analyst = v451_live_analyst_enrichment(ticker, price=price, scan_target=v451_valid_number(row.get("Analyst Target"), positive=True) or 0, scan_count=v451_valid_number(row.get("Analyst Count"), positive=True) or 0, scan_support=row.get("Analyst Support"))
    fin = v451_live_financial_enrichment(ticker, v451_row_to_json(row))
    news = v451_live_news_enrichment(ticker, company)
    completeness_score, completeness_status, completeness_checks = v451_research_completeness(row, analyst, fin, news)

    rr = levels.get("risk_reward") if isinstance(levels, dict) else None
    tech = v45_technical_health(row) if "v45_technical_health" in globals() else {"score": 60}
    tech_score = v451_valid_number(tech.get("score"), positive=False) or 60

    # Score is conservative if data incomplete; no premium buy if critical data not present.
    data_penalty = 0
    if completeness_score < 85:
        data_penalty += 10
    if not analyst.get("consensus") and not analyst.get("count"):
        data_penalty += 8
    if fin.get("data_quality") == "Incomplete":
        data_penalty += 10
    if not news.get("rows"):
        data_penalty += 5

    fin_score = 60
    usable_fin = [fin.get("pe"), fin.get("forward_pe"), fin.get("peg"), fin.get("revenue_growth"), fin.get("eps_growth"), fin.get("debt_equity"), fin.get("free_cash_flow")]
    if sum(v is not None for v in usable_fin) >= 5:
        fin_score = 78
        if (fin.get("revenue_growth") or 0) > 10: fin_score += 5
        if (fin.get("eps_growth") or 0) > 10: fin_score += 5
        if fin.get("free_cash_flow") is not None and fin.get("free_cash_flow") > 0: fin_score += 5
        if fin.get("debt_equity") is not None and fin.get("debt_equity") < 1.5: fin_score += 3
    elif sum(v is not None for v in usable_fin) >= 3:
        fin_score = 68
    analyst_score = 70
    if analyst.get("rating_trend", "").lower().startswith("bullish"):
        analyst_score = 82
    elif "bearish" in analyst.get("rating_trend", "").lower():
        analyst_score = 45
    if analyst.get("consensus") and price:
        upside = analyst.get("upside") or 0
        if upside >= 20: analyst_score += 5
        if upside < 0: analyst_score -= 10

    news_score = news.get("score", 50)
    base_score = table_score * .28 + fin_score * .22 + analyst_score * .18 + tech_score * .20 + news_score * .12
    advisor_score = max(0, min(99, round(base_score - data_penalty, 1)))

    decision = "WATCH"
    if completeness_status == "Data incomplete":
        decision = "RESEARCH ONLY"
    elif rr is not None and rr < 1:
        decision = "WAIT"
    elif advisor_score >= 88 and (rr is None or rr >= 1.25):
        decision = "BUY ON PULLBACK"
    elif advisor_score >= 80:
        decision = "ACTIONABLE WATCH"
    elif advisor_score < 65:
        decision = "AVOID / LOW PRIORITY"

    # Never actionable buy without financials + analyst/news basics.
    if decision in ["BUY NOW", "BUY ON PULLBACK", "ACTIONABLE WATCH"] and completeness_score < 70:
        decision = "RESEARCH ONLY"

    return {
        "ticker": ticker, "company": company, "price": price, "score": advisor_score, "decision": decision,
        "risk": "High" if advisor_score < 70 or (levels.get("atr_pct") or 0) >= 8 else ("Moderate" if (levels.get("atr_pct") or 0) >= 5 else "Moderate-Low"),
        "levels": levels, "analyst": analyst, "financials": fin, "news": news,
        "completeness_score": completeness_score, "completeness_status": completeness_status, "completeness_checks": completeness_checks,
    }


def v451_simple_take(row, d=None):
    d = d or v451_decision(row)
    l = d.get("levels", {})
    analyst, fin, news = d["analyst"], d["financials"], d["news"]
    entry = f"{v45_money(l.get('ideal_low'))}–{v45_money(l.get('ideal_high'))}" if l.get("ideal_low") and l.get("ideal_high") else v45_text(row.get("Entry Range"), "N/A")
    stop = v45_money(l.get("stop") or row.get("Stop Loss"))
    t1 = v45_money(l.get("target1"))
    t2 = v45_money(l.get("target2") or analyst.get("consensus") or row.get("Analyst Target"))
    main_reason = []
    if fin.get("revenue_growth") is not None:
        main_reason.append(f"revenue growth is {fin['revenue_growth']:.1f}%")
    if analyst.get("consensus") and d["price"]:
        main_reason.append(f"Wall Street target implies {analyst.get('upside'):.1f}% upside")
    if news.get("rows"):
        main_reason.append("recent ticker-specific news was reviewed")
    if not main_reason:
        main_reason.append("available technical and scan data are constructive, but deeper data is limited")

    if d["decision"] == "RESEARCH ONLY":
        return f"**Our take:** {d['ticker']} should stay in research-only mode because required data is incomplete. Do not present this as a premium buy recommendation until analyst targets, financials, and recent news are sufficiently populated."
    if d["decision"] == "WAIT":
        return f"**Our take:** {d['ticker']} may be a good company or setup, but the current entry is not ideal. A better entry is around **{entry}**, with risk controlled near **{stop}**. First target is **{t1}** and base target is **{t2}**."
    return f"**Our take:** {d['ticker']} is rated **{d['decision']}** because {', '.join(main_reason[:3])}. The preferred entry is **{entry}**, risk should be controlled near **{stop}**, and the base target is around **{t2}**."


def render_v451_advisor_decision_card(row):
    d = v451_decision(row)
    l = d.get("levels", {})
    with st.container(border=True):
        st.markdown(f"## {d['ticker']} — {d['company']}")
        st.markdown(f"### 🎯 AI Verdict: **{d['decision']}**")
        st.markdown(v451_simple_take(row, d))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Advisor Confidence", f"{d['score']:.1f}/100")
        c2.metric("Research Quality", f"{d['completeness_score']}/100")
        c3.metric("Risk", d["risk"])
        c4.metric("Current Price", v45_money(d["price"]))
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Ideal Entry", f"{v45_money(l.get('ideal_low'))} - {v45_money(l.get('ideal_high'))}" if l.get("ideal_low") and l.get("ideal_high") else v45_text(row.get("Entry Range"), "N/A"))
        c6.metric("Stop / Invalidation", v45_money(l.get("stop") or row.get("Stop Loss")))
        c7.metric("Target 1", v45_money(l.get("target1")))
        c8.metric("Base Target", v45_money(l.get("target2") or d["analyst"].get("consensus") or row.get("Analyst Target")))
        if d["completeness_status"] == "Data incomplete":
            st.warning("Research status is incomplete. The system attempted live analyst, financial, and news enrichment, but required fields are still missing. This should not be shown as a premium buy recommendation.")
        elif d["decision"] in ["BUY ON PULLBACK", "ACTIONABLE WATCH"]:
            st.success("This has enough data to support a customer-facing research view. Entry discipline still matters.")


def render_v451_trade_plan(row):
    d = v451_decision(row)
    l = d["levels"]
    with st.container(border=True):
        st.markdown("### 📍 Entry & Exit Plan")
        st.caption("This section tells the client what to do with the setup: where to consider buying, where the thesis breaks, and where to take profits.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ideal Entry", f"{v45_money(l.get('ideal_low'))} - {v45_money(l.get('ideal_high'))}" if l.get("ideal_low") and l.get("ideal_high") else v45_text(row.get("Entry Range"), "N/A"))
        c2.metric("Aggressive Entry", f"{v45_money(l.get('aggressive_low'))} - {v45_money(l.get('aggressive_high'))}" if l.get("aggressive_low") and l.get("aggressive_high") else "N/A")
        c3.metric("Stop / Thesis Break", v45_money(l.get("stop") or row.get("Stop Loss")))
        c4.metric("Risk/Reward", "N/A" if l.get("risk_reward") is None else f"{l.get('risk_reward'):.2f}:1")
        c5, c6, c7 = st.columns(3)
        c5.metric("Target 1", v45_money(l.get("target1")))
        c6.metric("Target 2 / Base", v45_money(l.get("target2") or d["analyst"].get("consensus") or row.get("Analyst Target")))
        c7.metric("Target 3 / Bull", v45_money(l.get("target3") or d["analyst"].get("high")))
        if l.get("risk_reward") is not None and l.get("risk_reward") < 1:
            st.warning("Risk/reward is not attractive at the current price. The advisor view should recommend waiting for a better entry or confirmed breakout.")
        else:
            st.info("Best client guidance: define the entry first, then use the stop to size the position. Avoid buying far above the ideal entry range.")


def render_v451_financial_health(row):
    d = v451_decision(row)
    fin = d["financials"]
    b = v45_benchmarks(row) if "v45_benchmarks" in globals() else {"label": "peers"}
    metrics = []
    for label, key in [
        ("P/E", "pe"), ("Forward P/E", "forward_pe"), ("PEG", "peg"),
        ("Revenue Growth", "revenue_growth"), ("EPS Growth", "eps_growth"),
        ("Gross Margin", "gross_margin"), ("Operating Margin", "operating_margin"),
        ("Debt/Equity", "debt_equity"), ("Free Cash Flow", "free_cash_flow"),
    ]:
        val = fin.get(key)
        assess, explain = v451_assess_fin(label, val, row)
        if key == "free_cash_flow":
            value_display = "Unavailable" if val is None else v45_money(val)
        elif label in ["Revenue Growth", "EPS Growth", "Gross Margin", "Operating Margin"]:
            value_display = "Unavailable" if val is None else f"{val:.1f}%"
        elif key == "debt_equity":
            value_display = "Unavailable" if val is None else f"{val:.2f}x"
        else:
            value_display = "Unavailable" if val is None else f"{val:.2f}"
        metrics.append({"Metric": label, "Value": value_display, "Good / Bad Context": v451_industry_avg_text(row, label), "Assessment": assess, "Plain-English Meaning": explain})
    usable = sum(1 for m in metrics if m["Value"] != "Unavailable")
    grade_score = min(95, 55 + usable * 5)
    if fin.get("free_cash_flow") is not None and fin.get("free_cash_flow") > 0:
        grade_score += 5
    if fin.get("revenue_growth") is not None and fin.get("revenue_growth") > (b.get("rev_good") or 8):
        grade_score += 5
    grade = v45_grade(grade_score) if "v45_grade" in globals() else "N/A"

    with st.container(border=True):
        st.markdown(f"### 🏢 Financial Health: **{grade}**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Data Completeness", fin["data_quality"])
        c2.metric("Metrics Populated", f"{usable}/{len(metrics)}")
        c3.metric("Peer Context", b.get("label", "peers"))
        if fin["data_quality"] == "Incomplete":
            st.warning("Financial data is not complete enough to make a confident financial-health claim. The system attempted scan data, FMP financials, FMP ratios, FMP growth, statements, and Yahoo fallback.")
        else:
            st.success("Financial data is populated enough to support a client-facing explanation.")
        st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)
        if fin.get("data_quality") != "Incomplete":
            st.markdown("**Advisor explanation:**")
            explanations = []
            if fin.get("revenue_growth") is not None:
                explanations.append(f"Revenue growth is {fin['revenue_growth']:.1f}%, which helps show whether the business is still expanding.")
            if fin.get("eps_growth") is not None:
                explanations.append(f"EPS growth is {fin['eps_growth']:.1f}%, which helps show whether growth is converting into earnings.")
            if fin.get("free_cash_flow") is not None:
                explanations.append("Free cash flow is positive." if fin["free_cash_flow"] > 0 else "Free cash flow is negative, which raises quality risk.")
            if fin.get("debt_equity") is not None:
                explanations.append(f"Debt/equity is {fin['debt_equity']:.2f}x, which helps assess balance-sheet risk.")
            for x in explanations[:5]:
                st.markdown(f"• {x}")
        with st.expander("Admin financial mapping diagnostics", expanded=False):
            for x in fin.get("diagnostics", []):
                st.caption(x)


def render_v451_analyst_intelligence(row):
    d = v451_decision(row)
    a = d["analyst"]
    with st.container(border=True):
        st.markdown("### 🏦 Wall Street & Analyst Intelligence")
        st.caption("Clients should understand whether Wall Street broadly supports the thesis, what the target range is, and whether analyst data is complete enough to trust.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Consensus Target", "Unavailable" if not a.get("consensus") else v45_money(a["consensus"]))
        c2.metric("Upside", "N/A" if a.get("upside") is None else v45_pct(a["upside"]))
        c3.metric("Coverage", str(a.get("count") or "Unavailable"))
        c4.metric("Rating Trend", a.get("rating_trend") or "Unknown")
        c5, c6, c7 = st.columns(3)
        c5.metric("High Target", "Unavailable" if not a.get("high") else v45_money(a["high"]))
        c6.metric("Low Target", "Unavailable" if not a.get("low") else v45_money(a["low"]))
        c7.metric("Analyst Data Quality", a.get("data_quality"))
        if a.get("consensus"):
            st.info(f"Advisor explanation: Wall Street consensus target is {v45_money(a['consensus'])}. At the current price, this implies {v45_pct(a.get('upside'))} potential upside. Use this as confirmation, not as the only reason to buy.")
        elif a.get("count"):
            st.warning(f"Advisor explanation: Analyst coverage exists ({a.get('count')} analysts), but connected sources did not return a usable target price. Do not use target upside for this ticker until target data is available.")
        else:
            st.warning("Analyst target and coverage data are unavailable after fallback attempts. This ticker should not be treated as premium-ready based on analyst support.")
        if a.get("firm_rows"):
            st.markdown("#### Recent analyst / firm-level actions")
            st.dataframe(pd.DataFrame(a["firm_rows"][:10]), use_container_width=True, hide_index=True)
        if a.get("estimate_rows"):
            st.markdown("#### Earnings / revenue estimate context")
            st.dataframe(pd.DataFrame(a["estimate_rows"][:6]), use_container_width=True, hide_index=True)
        with st.expander("Admin analyst source diagnostics", expanded=False):
            for x in a.get("diagnostics", []):
                st.caption(x)


def render_v451_news_catalysts(row):
    d = v451_decision(row)
    n = d["news"]
    with st.container(border=True):
        st.markdown("### 📰 News, Catalysts & Risks")
        c1, c2, c3 = st.columns(3)
        c1.metric("Ticker News", "Available" if n.get("rows") else "Unavailable")
        c2.metric("Sentiment", n.get("sentiment", "Mixed / Neutral"))
        c3.metric("Headlines Reviewed", len(n.get("rows", [])))
        if not n.get("rows"):
            st.warning("No recent ticker-specific headlines were returned after NewsAPI, Finnhub, and FMP attempts. This should lower research confidence.")
        else:
            left, right = st.columns(2)
            with left:
                st.markdown("#### Bullish catalysts")
                for h in n.get("bullish") or ["No strong bullish catalyst isolated from headlines."]:
                    st.markdown(f"✓ {h}")
            with right:
                st.markdown("#### Bearish risks")
                for h in n.get("bearish") or ["No strong bearish headline isolated from headlines."]:
                    st.markdown(f"⚠️ {h}")
            st.markdown("#### Recent headlines")
            for r in n.get("rows", [])[:6]:
                h, src, url = v45_text(r.get("headline")), v45_text(r.get("source")), v45_text(r.get("url"))
                st.markdown(f"• [{h}]({url}) · _{src}_" if url else f"• {h} · _{src}_")
        with st.expander("Admin news diagnostics", expanded=False):
            for x in n.get("diagnostics", []):
                st.caption(x)


def render_v451_metric_interpreter(row):
    th = v45_technical_health(row) if "v45_technical_health" in globals() else {"metrics": []}
    with st.container(border=True):
        st.markdown("### 📈 Technical Setup Explained")
        st.caption("This translates technical indicators into client-friendly timing guidance.")
        if th.get("metrics"):
            st.dataframe(pd.DataFrame(th["metrics"]), use_container_width=True, hide_index=True)
        else:
            st.warning("Technical details are limited for this ticker.")
        levels = v45_trade_levels(row) if "v45_trade_levels" in globals() else {}
        price, support, resistance = levels.get("price"), levels.get("support1"), levels.get("resistance1")
        if price and support and resistance:
            st.markdown(f"**Plain English:** Current price is {v45_money(price)}. Nearest support is around {v45_money(support)} and resistance is around {v45_money(resistance)}. A better entry is usually near support or after a confirmed breakout above resistance.")


def render_v451_final_thesis(row):
    d = v451_decision(row)
    with st.container(border=True):
        st.markdown("### 🧠 Final Investment Thesis")
        st.markdown(v451_simple_take(row, d))
        if d["decision"] == "RESEARCH ONLY":
            st.warning("Client guidance: keep this as research-only until the missing data fills in. Do not market this as a buy idea.")
        st.caption("This is research guidance and not personalized financial advice.")


def render_v451_admin_qa(row):
    d = v451_decision(row)
    with st.expander("🧪 Admin QA / Data Reliability", expanded=False):
        st.metric("Research Quality", f"{d['completeness_score']}/100")
        st.metric("Research Status", d["completeness_status"])
        st.dataframe(pd.DataFrame([{"Required Item": k, "Status": "✅" if v else "❌"} for k, v in d["completeness_checks"].items()]), use_container_width=True, hide_index=True)
        state = read_state() if "read_state" in globals() else {}
        st.metric("GitHub Persisted", "✅" if state.get("github_persisted") or v45_text(state.get("version", "")).startswith("V45") else "❌")


def render_v451_research_page(row):
    render_v451_advisor_decision_card(row)
    render_v451_trade_plan(row)
    render_v451_financial_health(row)
    render_v451_analyst_intelligence(row)
    render_v451_news_catalysts(row)
    render_v451_metric_interpreter(row)
    if "render_detail_chart_v4184" in globals():
        try:
            render_detail_chart_v4184(row)
        except Exception:
            pass
    render_v451_final_thesis(row)
    render_v451_admin_qa(row)


# Override the active detail renderer before main() is called.
def render_detail(row):
    render_v451_research_page(row)


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Advisor-style research pages with simple buy/watch/wait guidance, live ticker enrichment, data-quality checks, financial health, analyst intelligence, news catalysts, entry zones, targets, and risk controls.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version", "")).startswith("V45")
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: customer-facing research is visible; admin controls remain hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")



# =========================
# V46.0 INSTITUTIONAL RESEARCH COMPLETION ENGINE
# =========================
# Maximizes existing APIs before producing advisor-style guidance.

def v46_num(x, positive=False):
    try:
        v = v451_valid_number(x, positive=positive)
    except Exception:
        try:
            if x in (None, "", "N/A", "None"):
                return None
            if isinstance(x, str):
                x = x.replace("$", "").replace(",", "").replace("%", "").strip()
            v = float(x)
        except Exception:
            return None
    if v is None:
        return None
    try:
        if positive and v <= 0:
            return None
    except Exception:
        return None
    return v


def v46_money(x):
    v = v46_num(x, positive=False)
    return "Unavailable" if v is None else v45_money(v)


def v46_pct(x):
    v = v46_num(x, positive=False)
    return "N/A" if v is None else v45_pct(v)


def v46_normalize_growth_value(x):
    v = v46_num(x, positive=False)
    if v is None:
        return None
    # APIs vary: 0.30 can mean 30%; 30 can mean 30%.
    if abs(v) <= 1:
        v = v * 100
    if abs(v) > 250:
        return None
    return v


def v46_compute_growth_from_statement(rows, field="revenue"):
    if not rows or not isinstance(rows, list) or len(rows) < 2:
        return None
    try:
        cur = rows[0] if isinstance(rows[0], dict) else {}
        prev = rows[1] if isinstance(rows[1], dict) else {}
        a = v46_num(cur.get(field), positive=True)
        b = v46_num(prev.get(field), positive=True)
        if a and b:
            return ((a - b) / b) * 100
    except Exception:
        return None
    return None


def v46_pick_growth(candidates):
    clean = []
    for source, value in candidates:
        v = v46_normalize_growth_value(value)
        if v is not None:
            clean.append((source, v))
    if not clean:
        return None, []
    plausible = [(s, v) for s, v in clean if 2 <= abs(v) <= 100]
    chosen = plausible[0] if plausible else clean[0]
    return chosen[1], clean


def v46_company_context(row):
    ticker = v451_clean_ticker(row.get("Ticker"))
    company = v45_text(row.get("Company"), ticker)
    info = {
        "ticker": ticker,
        "company": company,
        "sector": v45_text(row.get("Sector") or row.get("sector"), ""),
        "industry": v45_text(row.get("Industry") or row.get("industry"), ""),
        "description": "",
        "ceo": "",
        "employees": None,
        "country": "",
        "exchange": "",
        "beta": None,
        "market_cap": v46_num(row.get("Market Cap"), positive=True),
        "diagnostics": [],
    }

    for tv in v451_ticker_variants(ticker):
        data, status = v451_fmp_get_try(f"profile/{tv}", None)
        info["diagnostics"].append(f"FMP profile/{tv}: {status}")
        if data:
            d = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
            if isinstance(d, dict):
                info["company"] = v45_text(d.get("companyName") or info["company"], info["company"])
                info["sector"] = v45_text(d.get("sector") or info["sector"], info["sector"])
                info["industry"] = v45_text(d.get("industry") or info["industry"], info["industry"])
                info["description"] = v45_text(d.get("description") or info["description"], info["description"])
                info["ceo"] = v45_text(d.get("ceo") or info["ceo"], info["ceo"])
                info["employees"] = v46_num(d.get("fullTimeEmployees") or d.get("employees"), positive=True) or info["employees"]
                info["country"] = v45_text(d.get("country") or info["country"], info["country"])
                info["exchange"] = v45_text(d.get("exchangeShortName") or d.get("exchange") or info["exchange"], info["exchange"])
                info["beta"] = v46_num(d.get("beta"), positive=False) or info["beta"]
                info["market_cap"] = v46_num(d.get("mktCap") or d.get("marketCap"), positive=True) or info["market_cap"]
                break

    yi = v451_yahoo_info(ticker)
    if yi:
        info["diagnostics"].append("Yahoo profile fallback: returned")
        info["sector"] = info["sector"] or v45_text(yi.get("sector"), "")
        info["industry"] = info["industry"] or v45_text(yi.get("industry"), "")
        info["description"] = info["description"] or v45_text(yi.get("longBusinessSummary"), "")
        info["employees"] = info["employees"] or v46_num(yi.get("fullTimeEmployees"), positive=True)
        info["country"] = info["country"] or v45_text(yi.get("country"), "")
        info["beta"] = info["beta"] or v46_num(yi.get("beta"), positive=False)
        info["market_cap"] = info["market_cap"] or v46_num(yi.get("marketCap"), positive=True)
    return info


@st.cache_data(ttl=900)
def v46_financial_intelligence(ticker, row_json=None):
    base = v451_live_financial_enrichment(ticker, row_json) if "v451_live_financial_enrichment" in globals() else {}
    out = dict(base or {})
    ticker = v451_clean_ticker(ticker)

    try:
        row = json.loads(row_json) if row_json else {}
    except Exception:
        row = {}

    out.setdefault("diagnostics", [])
    out.setdefault("warnings", [])
    out.setdefault("growth_candidates", [])
    out.setdefault("cash", None)
    out.setdefault("total_debt", None)
    out.setdefault("net_cash", None)
    out.setdefault("cash_debt_ratio", None)
    out.setdefault("debt_interpretation", "")

    growth_candidates = [
        ("scan revenue growth", row.get("Revenue Growth")),
        ("scan revenue growth pct", row.get("Revenue Growth %")),
        ("base mapped revenue growth", out.get("revenue_growth")),
    ]

    for tv in v451_ticker_variants(ticker):
        fmp_sets = {}
        for label, endpoint, params in [
            ("growth", f"financial-growth/{tv}", {"limit": 2}),
            ("income_annual", f"income-statement/{tv}", {"limit": 3}),
            ("income_quarter", f"income-statement/{tv}", {"limit": 5, "period": "quarter"}),
            ("cashflow", f"cash-flow-statement/{tv}", {"limit": 3}),
            ("balance", f"balance-sheet-statement/{tv}", {"limit": 3}),
            ("metrics", f"key-metrics-ttm/{tv}", None),
            ("ratios", f"ratios-ttm/{tv}", None),
        ]:
            data, status = v451_fmp_get_try(endpoint, params)
            out["diagnostics"].append(f"V46 FMP {endpoint}: {status}")
            if data:
                fmp_sets[label] = data if isinstance(data, list) else [data]

        for d in fmp_sets.get("growth", [])[:2]:
            if isinstance(d, dict):
                growth_candidates.extend([
                    ("FMP revenueGrowth", d.get("revenueGrowth")),
                    ("FMP growthRevenue", d.get("growthRevenue")),
                    ("FMP grossProfitGrowth", d.get("grossProfitGrowth")),
                ])
                eps_g = v46_normalize_growth_value(d.get("epsgrowth") or d.get("epsGrowth") or d.get("growthEPS"))
                if eps_g is not None:
                    out["eps_growth"] = eps_g

        annual_rev_growth = v46_compute_growth_from_statement(fmp_sets.get("income_annual"), "revenue")
        quarter_rev_growth = v46_compute_growth_from_statement(fmp_sets.get("income_quarter"), "revenue")
        if annual_rev_growth is not None:
            growth_candidates.insert(0, ("FMP annual income statement revenue growth", annual_rev_growth))
        if quarter_rev_growth is not None:
            growth_candidates.append(("FMP quarterly income statement revenue growth", quarter_rev_growth))

        if fmp_sets.get("balance"):
            b0 = fmp_sets["balance"][0] if isinstance(fmp_sets["balance"][0], dict) else {}
            cash = v46_num(b0.get("cashAndCashEquivalents") or b0.get("cashAndShortTermInvestments"), positive=False)
            short_debt = v46_num(b0.get("shortTermDebt"), positive=False) or 0
            long_debt = v46_num(b0.get("longTermDebt"), positive=False) or 0
            debt = v46_num(b0.get("totalDebt"), positive=False)
            if debt is None:
                debt = short_debt + long_debt
            equity = v46_num(b0.get("totalStockholdersEquity") or b0.get("totalEquity"), positive=False)
            out["cash"] = out.get("cash") if out.get("cash") is not None else cash
            out["total_debt"] = out.get("total_debt") if out.get("total_debt") is not None else debt
            if cash is not None and debt is not None:
                out["net_cash"] = cash - debt
                out["cash_debt_ratio"] = cash / debt if debt else None
            if debt is not None and equity not in [None, 0]:
                de = debt / equity
                if out.get("debt_equity") is None or out.get("debt_equity") > 20:
                    out["debt_equity"] = de

        if fmp_sets.get("cashflow"):
            cf0 = fmp_sets["cashflow"][0] if isinstance(fmp_sets["cashflow"][0], dict) else {}
            fcf = v46_num(cf0.get("freeCashFlow"), positive=False)
            ocf = v46_num(cf0.get("operatingCashFlow") or cf0.get("netCashProvidedByOperatingActivities"), positive=False)
            capex = v46_num(cf0.get("capitalExpenditure") or cf0.get("capitalExpenditures"), positive=False)
            if fcf is not None:
                out["free_cash_flow"] = fcf
            out["operating_cash_flow"] = ocf
            out["capex"] = capex

    yi = v451_yahoo_info(ticker)
    if yi:
        out["diagnostics"].append("V46 Yahoo financial fallback: returned")
        growth_candidates.extend([
            ("Yahoo revenueGrowth", yi.get("revenueGrowth")),
            ("Yahoo earningsGrowth", yi.get("earningsGrowth")),
        ])
        out["cash"] = out.get("cash") if out.get("cash") is not None else v46_num(yi.get("totalCash"), positive=False)
        out["total_debt"] = out.get("total_debt") if out.get("total_debt") is not None else v46_num(yi.get("totalDebt"), positive=False)
        if out.get("cash") is not None and out.get("total_debt") is not None:
            out["net_cash"] = out["cash"] - out["total_debt"]
            out["cash_debt_ratio"] = out["cash"] / out["total_debt"] if out["total_debt"] else None

    chosen_growth, candidates = v46_pick_growth(growth_candidates)
    out["growth_candidates"] = [{"Source": s, "Value": f"{v:.1f}%"} for s, v in candidates]
    if chosen_growth is not None:
        old = v46_num(out.get("revenue_growth"), positive=False)
        if old is None or abs(old) < 2 or abs(chosen_growth) > abs(old):
            out["revenue_growth"] = chosen_growth

    de = v46_num(out.get("debt_equity"), positive=False)
    if de is not None and de > 20:
        out["warnings"].append("Debt/equity appears distorted by accounting/equity base. Use cash, total debt, and net cash instead of treating the raw ratio as financial distress.")
        if out.get("net_cash") is not None:
            if out["net_cash"] >= 0:
                out["debt_interpretation"] = f"Debt/equity is distorted, but the company appears net-cash positive by about {v45_money(out['net_cash'])}."
            else:
                out["debt_interpretation"] = f"Debt/equity is distorted; net debt is about {v45_money(abs(out['net_cash']))}."
        else:
            out["debt_interpretation"] = "Debt/equity is unusually high and likely distorted; review cash/debt coverage rather than relying only on this ratio."
    elif de is not None:
        out["debt_interpretation"] = f"Debt/equity is {de:.2f}x."

    usable = sum(1 for k in ["revenue_growth", "eps_growth", "pe", "forward_pe", "peg", "free_cash_flow", "cash", "total_debt", "gross_margin", "operating_margin"] if out.get(k) is not None)
    out["data_quality"] = "Complete" if usable >= 6 else ("Partial" if usable >= 4 else "Incomplete")
    return out


@st.cache_data(ttl=600)
def v46_news_intelligence(ticker, company=""):
    ticker = v451_clean_ticker(ticker)
    company = v45_text(company or ticker, ticker)
    rows, diagnostics = [], []

    def add_row(headline, source, url="", published="", provider=""):
        h = v45_text(headline, "")
        if not h:
            return
        if h.lower() in [r["headline"].lower() for r in rows]:
            return
        rows.append({"headline": h, "source": v45_text(source, provider or "News"), "url": v45_text(url, ""), "published": v45_text(published, ""), "provider": provider or source})

    news_key = v45_secret("NEWSAPI_KEY", "") if "v45_secret" in globals() else ""
    if news_key:
        queries = [
            f'"{company}" stock',
            f'{ticker} stock',
            f'"{company}" earnings',
            f'"{company}" guidance OR outlook',
            f'"{company}" analyst OR price target',
            f'"{company}" shares',
            f'"{company}"',
        ]
        for q in queries:
            if len(rows) >= 5:
                break
            try:
                data, status = v432_http_json("https://newsapi.org/v2/everything", params={"q": q, "language": "en", "sortBy": "publishedAt", "pageSize": 8, "apiKey": news_key})
                diagnostics.append(f"NewsAPI query [{q}]: status={status}")
                if isinstance(data, dict):
                    for a in data.get("articles", [])[:8]:
                        add_row(a.get("title"), (a.get("source") or {}).get("name"), a.get("url"), a.get("publishedAt"), "NewsAPI")
            except Exception as e:
                diagnostics.append(f"NewsAPI query [{q}] failed: {e}")
    else:
        diagnostics.append("NEWSAPI_KEY missing")

    fh = v45_secret("FINNHUB_API_KEY", "") if "v45_secret" in globals() else ""
    if fh and len(rows) < 5:
        try:
            end = dt.date.today()
            start = end - dt.timedelta(days=60)
            data, status = v432_http_json("https://finnhub.io/api/v1/company-news", params={"symbol": ticker, "from": str(start), "to": str(end), "token": fh})
            diagnostics.append(f"Finnhub company-news: status={status}")
            if isinstance(data, list):
                for a in data[:12]:
                    add_row(a.get("headline"), a.get("source"), a.get("url"), a.get("datetime"), "Finnhub")
        except Exception as e:
            diagnostics.append(f"Finnhub company-news failed: {e}")

    if v45_secret("FMP_API_KEY", "") and "v424_fmp_get" in globals() and len(rows) < 5:
        for params in [{"tickers": ticker, "limit": 20}, {"tickers": company, "limit": 20}]:
            data, status = v451_fmp_get_try("stock_news", params)
            diagnostics.append(f"FMP stock_news {params}: {status}")
            if data:
                for a in (data if isinstance(data, list) else [data])[:12]:
                    if isinstance(a, dict):
                        add_row(a.get("title") or a.get("headline"), a.get("site") or a.get("source"), a.get("url"), a.get("publishedDate") or a.get("date"), "FMP")
            if len(rows) >= 5:
                break

    if len(rows) < 3:
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
            text, status = v432_http_text(url, timeout=8)
            diagnostics.append(f"Yahoo ticker RSS: status={status}")
            if text:
                root = ET.fromstring(text.encode("utf-8"))
                for item in root.findall(".//item")[:10]:
                    add_row(item.findtext("title"), "Yahoo Finance RSS", item.findtext("link"), "", "Yahoo RSS")
        except Exception as e:
            diagnostics.append(f"Yahoo RSS failed: {e}")

    classified = v45_classify_news(rows[:10]) if "v45_classify_news" in globals() else {"score": 50, "sentiment": "Mixed / Neutral", "bullish": [], "bearish": []}
    return {"rows": rows[:10], "diagnostics": diagnostics, **classified, "data_quality": "Complete" if len(rows) >= 3 else ("Partial" if rows else "Incomplete")}


def v46_sanitize_analyst(a, ticker, price, row):
    a = dict(a or {})
    price = v46_num(price, positive=True)
    company_ctx = v46_company_context(row)
    industry = (company_ctx.get("industry", "") + " " + company_ctx.get("sector", "")).lower()
    high = v46_num(a.get("high"), positive=True)
    low = v46_num(a.get("low"), positive=True)
    consensus = v46_num(a.get("consensus"), positive=True)
    a["warnings"] = list(a.get("warnings", []))

    if price and high and high > price * 3 and not any(x in industry for x in ["biotech", "pharmaceutical", "therapeutic"]):
        a["high_unfiltered"] = high
        a["high"] = None
        a["warnings"].append(f"High target {v45_money(high)} was excluded from client bull target because it is more than 3x current price and may be stale/outlier.")
    if price and low and low < price * 0.25:
        a["low_unfiltered"] = low
        a["low"] = None
        a["warnings"].append(f"Low target {v45_money(low)} was excluded as a likely stale/outlier value.")
    if price and consensus:
        a["upside"] = ((consensus - price) / price) * 100
    else:
        a["upside"] = None
    return a


def v46_trade_plan(row, d=None):
    price = v46_num(row.get("Price"), positive=True) or 0
    levels = v45_trade_levels(row) if "v45_trade_levels" in globals() else {}
    support = v46_num(levels.get("support1"), positive=True) or v46_num(row.get("52W Low"), positive=True)
    resistance = v46_num(levels.get("resistance1"), positive=True) or v46_num(row.get("52W High"), positive=True)
    atr_pct = v46_num(levels.get("atr_pct"), positive=False) or v46_num(row.get("ATR %"), positive=False) or 4
    analyst_target = v46_num((d or {}).get("analyst", {}).get("consensus"), positive=True) if d else None
    analyst_high = v46_num((d or {}).get("analyst", {}).get("high"), positive=True) if d else None

    if price:
        ideal_high = price
        pullback = max(0.03, min(0.08, (atr_pct or 4) / 100))
        ideal_low = max((support or price * 0.92), price * (1 - pullback * 1.25))
        if ideal_low > ideal_high:
            ideal_low = price * 0.95
            ideal_high = price
        aggressive_low = max(price * 0.99, ideal_low)
        aggressive_high = price * 1.03
        stop = min(ideal_low * 0.94, price * 0.90)
        if support and support < price:
            stop = min(stop, support * 0.97)
        target1 = resistance if resistance and resistance > price else price * 1.15
        target2 = analyst_target if analyst_target and analyst_target > target1 else max(target1 * 1.08, price * 1.25)
        target3 = analyst_high if analyst_high and analyst_high > target2 else max(target2 * 1.10, price * 1.35)
        if target3 > price * 2.5:
            target3 = price * 1.65
        risk = price - stop
        reward = target1 - price
        rr = reward / risk if risk > 0 and reward > 0 else None
        return {"price": price, "ideal_low": ideal_low, "ideal_high": ideal_high, "aggressive_low": aggressive_low, "aggressive_high": aggressive_high, "stop": stop, "target1": target1, "target2": target2, "target3": target3, "risk_reward": rr, "atr_pct": atr_pct, "support1": support, "resistance1": resistance}
    return levels


def v46_research_completion(company, fin, analyst, news, row):
    checks = {
        "Company profile": bool(company.get("sector") or company.get("industry") or company.get("description")),
        "Financial intelligence": fin.get("data_quality") in ["Complete", "Partial"],
        "Analyst intelligence": bool(analyst.get("consensus") or analyst.get("count") or analyst.get("rating_trend")),
        "News & catalysts": news.get("data_quality") in ["Complete", "Partial"],
        "Technical setup": bool(v46_num(row.get("RSI"), positive=False) or v46_num(row.get("52W High"), positive=True)),
        "Trade plan": True,
        "Valuation context": bool(fin.get("pe") is not None or fin.get("forward_pe") is not None or fin.get("peg") is not None),
        "Balance sheet / cash flow": bool(fin.get("free_cash_flow") is not None or fin.get("cash") is not None or fin.get("total_debt") is not None),
    }
    score = round(sum(checks.values()) / len(checks) * 100)
    status = "Institutional Grade" if score >= 88 else ("Enhanced Grade" if score >= 75 else "Advisor Grade with Caveats")
    return score, status, checks


def v46_decision(row):
    ticker = v451_clean_ticker(row.get("Ticker"))
    price = v46_num(row.get("Price"), positive=True) or 0
    company = v46_company_context(row)
    analyst_raw = v451_live_analyst_enrichment(ticker, price=price, scan_target=v46_num(row.get("Analyst Target"), positive=True) or 0, scan_count=v46_num(row.get("Analyst Count"), positive=True) or 0, scan_support=row.get("Analyst Support"))
    analyst = v46_sanitize_analyst(analyst_raw, ticker, price, row)
    fin = v46_financial_intelligence(ticker, v451_row_to_json(row))
    news = v46_news_intelligence(ticker, company.get("company") or row.get("Company") or ticker)
    levels = v46_trade_plan(row, {"analyst": analyst})
    completion_score, completion_status, checks = v46_research_completion(company, fin, analyst, news, row)

    table_score = v46_num(row.get("Final Conviction"), positive=False) or 60
    analyst_upside = analyst.get("upside")
    rr = levels.get("risk_reward")
    revenue_growth = v46_num(fin.get("revenue_growth"), positive=False)
    fcf = v46_num(fin.get("free_cash_flow"), positive=False)
    de = v46_num(fin.get("debt_equity"), positive=False)
    news_score = news.get("score", 50)
    tech = v45_technical_health(row) if "v45_technical_health" in globals() else {"score": 60}
    tech_score = v46_num(tech.get("score"), positive=False) or 60

    score = table_score * 0.24 + tech_score * 0.18 + news_score * 0.10
    if analyst.get("consensus") and analyst_upside is not None:
        score += 14
        if analyst_upside >= 25: score += 6
        elif analyst_upside >= 10: score += 3
        elif analyst_upside < 0: score -= 8
    elif analyst.get("count"):
        score += 8
    if "bullish" in str(analyst.get("rating_trend", "")).lower():
        score += 6
    if analyst.get("count", 0) >= 20:
        score += 3

    if revenue_growth is not None:
        if revenue_growth >= 15: score += 8
        elif revenue_growth >= 5: score += 5
        elif revenue_growth < 0: score -= 8
    if fcf is not None:
        score += 6 if fcf > 0 else -8
    if de is not None:
        if de > 20:
            score -= 2
        elif de <= 2:
            score += 3
    if fin.get("data_quality") == "Complete":
        score += 4
    elif fin.get("data_quality") == "Incomplete":
        score -= 6
    if rr is not None:
        if rr >= 2: score += 6
        elif rr >= 1.25: score += 3
        elif rr < 1: score -= 8
    if news.get("rows"):
        score += 3
    else:
        score -= 2
    if completion_score < 75:
        score -= 5

    score = max(0, min(99, round(score, 1)))

    bullish_case = ((analyst_upside is not None and analyst_upside >= 20) and ("bullish" in str(analyst.get("rating_trend", "")).lower() or analyst.get("count", 0) >= 15) and (rr is None or rr >= 1.25) and (fcf is None or fcf > 0))
    if score >= 86 and (rr is None or rr >= 1.25):
        decision = "BUY ON PULLBACK"
    elif score >= 76:
        decision = "ACTIONABLE WATCH"
    elif bullish_case:
        decision = "BUY ON PULLBACK"
        score = max(score, 72)
    elif score >= 62:
        decision = "SPECULATIVE WATCH"
    else:
        decision = "AVOID / LOW PRIORITY"

    if decision == "BUY ON PULLBACK" and price and levels.get("ideal_low") and levels.get("ideal_high") and levels["ideal_low"] <= price <= levels["ideal_high"]:
        decision = "ACCUMULATE CAREFULLY"

    caveats = []
    if fin.get("warnings"):
        caveats.extend(fin["warnings"][:2])
    if analyst.get("warnings"):
        caveats.extend(analyst["warnings"][:2])
    if not news.get("rows"):
        caveats.append("Recent ticker-specific news did not populate from connected sources; confidence is slightly reduced.")
    if revenue_growth is not None and abs(revenue_growth) < 2 and bullish_case:
        caveats.append("Revenue growth appears unusually low versus the broader thesis; verify next earnings/growth update.")

    return {"ticker": ticker, "company": company, "financials": fin, "analyst": analyst, "news": news, "levels": levels, "score": score, "decision": decision, "completion_score": completion_score, "completion_status": completion_status, "completion_checks": checks, "risk": "High" if score < 68 or (levels.get("atr_pct") or 0) >= 8 else ("Moderate" if score < 85 else "Moderate-Low"), "caveats": caveats}


def v46_advisor_take(row, d=None):
    d = d or v46_decision(row)
    ticker = d["ticker"]
    levels, analyst, fin, news = d["levels"], d["analyst"], d["financials"], d["news"]
    entry = f"{v45_money(levels.get('ideal_low'))}–{v45_money(levels.get('ideal_high'))}"
    stop = v45_money(levels.get("stop"))
    base = v45_money(levels.get("target2") or analyst.get("consensus"))
    positives, cautions = [], []
    if analyst.get("count"):
        positives.append(f"{analyst.get('count')} analysts provide coverage")
    if analyst.get("upside") is not None and analyst.get("upside") >= 10:
        positives.append(f"Wall Street consensus implies {analyst.get('upside'):.1f}% upside")
    if fin.get("free_cash_flow") is not None and fin.get("free_cash_flow") > 0:
        positives.append("free cash flow is positive")
    if fin.get("revenue_growth") is not None and fin.get("revenue_growth") >= 5:
        positives.append(f"revenue growth is {fin.get('revenue_growth'):.1f}%")
    if news.get("rows"):
        positives.append("recent ticker-specific news was reviewed")
    if fin.get("debt_interpretation"):
        cautions.append(fin["debt_interpretation"])
    if not news.get("rows"):
        cautions.append("recent ticker news is limited from connected sources")
    if analyst.get("warnings"):
        cautions.extend(analyst["warnings"][:1])
    if not positives:
        positives.append("the setup has some constructive signals, but conviction is limited")

    if d["decision"] in ["ACCUMULATE CAREFULLY", "BUY ON PULLBACK"]:
        lead = f"**Our take:** {ticker} is a **{d['decision']}** candidate. The preferred entry zone is **{entry}**, with risk controlled near **{stop}** and a base target around **{base}**."
    elif d["decision"] == "ACTIONABLE WATCH":
        lead = f"**Our take:** {ticker} deserves a spot on the active watchlist. The setup is constructive, but the best risk/reward is near **{entry}** rather than chasing."
    elif d["decision"] == "SPECULATIVE WATCH":
        lead = f"**Our take:** {ticker} has upside potential, but uncertainty is elevated. Use smaller sizing and wait for confirmation near **{entry}**."
    else:
        lead = f"**Our take:** {ticker} is currently **AVOID / LOW PRIORITY** because the overall evidence does not support a strong risk-adjusted opportunity today."
    return lead, positives[:5], cautions[:5]


def render_v46_advisor_decision_card(row):
    d = v46_decision(row)
    levels = d["levels"]
    lead, positives, cautions = v46_advisor_take(row, d)
    with st.container(border=True):
        st.markdown(f"## {d['ticker']} — {d['company'].get('company', d['ticker'])}")
        st.markdown(f"### 🎯 AI Advisor Verdict: **{d['decision']}**")
        st.markdown(lead)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Advisor Confidence", f"{d['score']:.1f}/100")
        c2.metric("Research Completion", f"{d['completion_score']}/100")
        c3.metric("Research Status", d["completion_status"])
        c4.metric("Risk", d["risk"])
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Current Price", v46_money(levels.get("price")))
        c6.metric("Preferred Entry", f"{v45_money(levels.get('ideal_low'))} - {v45_money(levels.get('ideal_high'))}")
        c7.metric("Stop / Thesis Break", v45_money(levels.get("stop")))
        c8.metric("Base Target", v45_money(levels.get("target2")))
        left, right = st.columns(2)
        with left:
            st.markdown("#### Why we like it")
            for p in positives:
                st.markdown(f"✓ {p}")
        with right:
            st.markdown("#### What gives us pause")
            for c in cautions or ["No major caveat identified from populated data."]:
                st.markdown(f"⚠️ {c}")


def render_v46_trade_plan(row):
    d = v46_decision(row)
    l = d["levels"]
    with st.container(border=True):
        st.markdown("### 📍 Entry, Exit & Target Plan")
        st.caption("This tells the client exactly where the setup becomes attractive and where the thesis breaks.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preferred Entry", f"{v45_money(l.get('ideal_low'))} - {v45_money(l.get('ideal_high'))}")
        c2.metric("Aggressive Entry", f"{v45_money(l.get('aggressive_low'))} - {v45_money(l.get('aggressive_high'))}")
        c3.metric("Stop / Thesis Break", v45_money(l.get("stop")))
        c4.metric("Risk / Reward", "N/A" if l.get("risk_reward") is None else f"{l.get('risk_reward'):.2f}:1")
        c5, c6, c7 = st.columns(3)
        c5.metric("Conservative Target", v45_money(l.get("target1")))
        c6.metric("Base Target", v45_money(l.get("target2")))
        c7.metric("Bull Target", v45_money(l.get("target3")))
        if l.get("price") and l.get("ideal_low") and l.get("ideal_high") and l["ideal_low"] <= l["price"] <= l["ideal_high"]:
            st.success("Current price is inside the preferred entry zone. The advisor can consider a starter position if the investor accepts the risk.")
        elif l.get("price") and l.get("ideal_high") and l["price"] > l["ideal_high"]:
            st.warning("Current price is above the preferred entry zone. Better risk/reward may come on a pullback.")
        else:
            st.info("Use the entry zone and stop together. Do not buy without knowing where the thesis breaks.")


def render_v46_financial_intelligence(row):
    d = v46_decision(row)
    fin = d["financials"]
    b = v45_benchmarks(row) if "v45_benchmarks" in globals() else {"label": "peers"}
    metrics = []
    for label, key, fmt in [
        ("Revenue Growth", "revenue_growth", "pct"),
        ("EPS Growth", "eps_growth", "pct"),
        ("Free Cash Flow", "free_cash_flow", "money"),
        ("Operating Cash Flow", "operating_cash_flow", "money"),
        ("P/E", "pe", "num"),
        ("Forward P/E", "forward_pe", "num"),
        ("PEG", "peg", "num"),
        ("Gross Margin", "gross_margin", "pct"),
        ("Operating Margin", "operating_margin", "pct"),
        ("Debt/Equity", "debt_equity", "debt"),
        ("Cash", "cash", "money"),
        ("Total Debt", "total_debt", "money"),
        ("Net Cash / Debt", "net_cash", "money"),
    ]:
        val = fin.get(key)
        if fmt == "money":
            display = "Unavailable" if val is None else v45_money(val)
        elif fmt == "pct":
            display = "Unavailable" if val is None else f"{val:.1f}%"
        elif fmt == "debt":
            display = "Unavailable" if val is None else f"{val:.2f}x"
        else:
            display = "Unavailable" if val is None else f"{val:.2f}"
        assess, explain = v451_assess_fin(label, val, row)
        if key == "debt_equity" and val is not None and val > 20:
            assess = "Distorted / review cash and debt"
            explain = fin.get("debt_interpretation") or "Debt/equity appears distorted by accounting structure. Use cash and total debt context."
        metrics.append({"Metric": label, "Value": display, "Peer Context": v451_industry_avg_text(row, label), "Assessment": assess, "Plain English": explain})
    usable = sum(1 for m in metrics if m["Value"] != "Unavailable")
    grade_score = min(96, 50 + usable * 3)
    if fin.get("free_cash_flow") and fin.get("free_cash_flow") > 0: grade_score += 6
    if fin.get("revenue_growth") and fin.get("revenue_growth") >= 10: grade_score += 6
    if fin.get("net_cash") is not None and fin.get("net_cash") > 0: grade_score += 4
    grade = v45_grade(grade_score) if "v45_grade" in globals() else "N/A"

    with st.container(border=True):
        st.markdown(f"### 🏢 Financial Intelligence: **{grade}**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Data Quality", fin.get("data_quality", "Unknown"))
        c2.metric("Metrics Populated", f"{usable}/{len(metrics)}")
        c3.metric("Peer Group", b.get("label", "peers"))
        st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)
        st.markdown("#### Advisor explanation")
        bullets = []
        if fin.get("revenue_growth") is not None:
            bullets.append(f"Revenue growth is {fin['revenue_growth']:.1f}%, which shows whether the business is still expanding.")
        if fin.get("free_cash_flow") is not None:
            bullets.append("Free cash flow is positive, which supports financial flexibility." if fin["free_cash_flow"] > 0 else "Free cash flow is negative, which increases risk.")
        if fin.get("debt_interpretation"):
            bullets.append(fin["debt_interpretation"])
        if fin.get("net_cash") is not None:
            bullets.append(f"Net cash/debt position is {v45_money(fin['net_cash'])}.")
        for btxt in bullets[:5]:
            st.markdown(f"• {btxt}")
        with st.expander("Admin financial diagnostics", expanded=False):
            if fin.get("growth_candidates"):
                st.markdown("**Revenue growth candidates**")
                st.dataframe(pd.DataFrame(fin["growth_candidates"]), use_container_width=True, hide_index=True)
            for x in fin.get("diagnostics", []):
                st.caption(x)


def render_v46_analyst_intelligence(row):
    d = v46_decision(row)
    a = d["analyst"]
    with st.container(border=True):
        st.markdown("### 🏦 Analyst Intelligence")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Consensus Target", "Unavailable" if not a.get("consensus") else v45_money(a.get("consensus")))
        c2.metric("Upside", "N/A" if a.get("upside") is None else v45_pct(a.get("upside")))
        c3.metric("Coverage", str(a.get("count") or "Unavailable"))
        c4.metric("Rating Trend", a.get("rating_trend") or "Unknown")
        c5, c6, c7 = st.columns(3)
        c5.metric("High Target", "Unavailable" if not a.get("high") else v45_money(a.get("high")))
        c6.metric("Low Target", "Unavailable" if not a.get("low") else v45_money(a.get("low")))
        c7.metric("Data Quality", a.get("data_quality"))
        if a.get("consensus"):
            st.info(f"Advisor explanation: Wall Street consensus target is {v45_money(a.get('consensus'))}, implying {v45_pct(a.get('upside'))} upside from the current price. This supports the thesis, but entry timing and risk still matter.")
        if a.get("firm_rows"):
            st.markdown("#### Recent analyst / firm activity")
            st.dataframe(pd.DataFrame(a["firm_rows"][:10]), use_container_width=True, hide_index=True)
        if a.get("warnings"):
            for w in a["warnings"]:
                st.warning(w)
        with st.expander("Admin analyst diagnostics", expanded=False):
            for x in a.get("diagnostics", []):
                st.caption(x)


def render_v46_news_intelligence(row):
    d = v46_decision(row)
    n = d["news"]
    with st.container(border=True):
        st.markdown("### 📰 News, Catalysts & Risks")
        c1, c2, c3 = st.columns(3)
        c1.metric("News Coverage", n.get("data_quality"))
        c2.metric("Sentiment", n.get("sentiment", "Mixed / Neutral"))
        c3.metric("Headlines Reviewed", len(n.get("rows", [])))
        left, right = st.columns(2)
        with left:
            st.markdown("#### Bullish catalysts")
            for h in n.get("bullish") or ["No strong bullish catalyst isolated from recent headlines."]:
                st.markdown(f"✓ {h}")
        with right:
            st.markdown("#### Bearish risks")
            for h in n.get("bearish") or ["No strong bearish headline isolated from recent headlines."]:
                st.markdown(f"⚠️ {h}")
        if n.get("rows"):
            st.markdown("#### Recent headlines")
            for r in n.get("rows", [])[:7]:
                h, src, url = v45_text(r.get("headline")), v45_text(r.get("source")), v45_text(r.get("url"))
                st.markdown(f"• [{h}]({url}) · _{src}_" if url else f"• {h} · _{src}_")
        else:
            st.warning("No ticker-specific headlines populated even after multi-source fallback. Confidence is reduced, but the advisor still gives a view using financials, analysts, valuation and technicals.")
        with st.expander("Admin news diagnostics", expanded=False):
            for x in n.get("diagnostics", []):
                st.caption(x)


def render_v46_completion(row):
    d = v46_decision(row)
    with st.expander("🧪 Admin Research Completion & Source QA", expanded=False):
        st.metric("Research Completion", f"{d['completion_score']}/100")
        st.metric("Research Status", d["completion_status"])
        st.dataframe(pd.DataFrame([{"Research Module": k, "Status": "✅" if v else "⚠️"} for k, v in d["completion_checks"].items()]), use_container_width=True, hide_index=True)


def render_v46_research_page(row):
    render_v46_advisor_decision_card(row)
    render_v46_trade_plan(row)
    render_v46_financial_intelligence(row)
    render_v46_analyst_intelligence(row)
    render_v46_news_intelligence(row)
    render_v451_metric_interpreter(row)
    if "render_detail_chart_v4184" in globals():
        try:
            render_detail_chart_v4184(row)
        except Exception:
            pass
    render_v451_final_thesis(row)
    render_v46_completion(row)


def render_detail(row):
    render_v46_research_page(row)


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Institutional Research Completion Engine: maximizes current APIs before generating advisor-style entry, target, risk, analyst, news, and financial guidance.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version", "")).startswith(("V45", "V46"))
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: customer-facing research is visible; admin controls remain hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")



# =========================
# V46.1 RESEARCH QUALITY CORRECTION PATCH
# =========================
# Fixes:
# - Removes old V45 final thesis contradiction
# - Normalizes margin values correctly: 0.81 -> 81%
# - Adds trading stop vs long-term thesis break
# - Prevents extreme analyst high targets from becoming client bull target
# - Cleans advisor sentence rendering
# - Improves debt/equity explanation for accounting-distorted ratios

def v461_percent_value(x):
    v = v46_num(x, positive=False) if "v46_num" in globals() else None
    if v is None:
        return None
    # For margins/ROE from APIs: 0.81 means 81%, 81 means 81%.
    if abs(v) <= 1:
        v *= 100
    if abs(v) > 250:
        return None
    return v


@st.cache_data(ttl=900)
def v461_financial_intelligence(ticker, row_json=None):
    fin = v46_financial_intelligence(ticker, row_json) if "v46_financial_intelligence" in globals() else {}
    fin = dict(fin or {})
    fin.setdefault("diagnostics", [])
    fin.setdefault("warnings", [])

    # Correct margin normalization. V46 was still allowing 0.8% instead of 80%.
    for key in ["gross_margin", "operating_margin", "net_margin", "roe"]:
        if fin.get(key) is not None:
            fixed = v461_percent_value(fin.get(key))
            if fixed is not None:
                fin[key] = fixed

    # Add better balance sheet interpretation.
    de = v46_num(fin.get("debt_equity"), positive=False) if "v46_num" in globals() else None
    cash = v46_num(fin.get("cash"), positive=False) if "v46_num" in globals() else None
    debt = v46_num(fin.get("total_debt"), positive=False) if "v46_num" in globals() else None
    fcf = v46_num(fin.get("free_cash_flow"), positive=False) if "v46_num" in globals() else None

    if cash is not None and debt is not None:
        fin["net_cash"] = cash - debt
        fin["cash_debt_ratio"] = cash / debt if debt else None

    if de is not None and de > 20:
        msg = "Book debt/equity appears accounting-distorted. For software companies, this can happen when equity is reduced by buybacks, losses, or convertible debt accounting. Use cash, total debt, net cash/debt, and free cash flow instead of treating the raw ratio as distress."
        if msg not in fin["warnings"]:
            fin["warnings"].append(msg)
        if cash is not None and debt is not None:
            if cash >= debt:
                fin["debt_interpretation"] = f"Debt/equity is distorted, but cash appears to exceed total debt by about {v45_money(cash - debt)}. This is not automatically a distress signal."
            else:
                fin["debt_interpretation"] = f"Debt/equity is distorted. Net debt is about {v45_money(debt - cash)}; compare this against free cash flow before judging balance-sheet risk."
        elif fcf is not None and fcf > 0:
            fin["debt_interpretation"] = "Debt/equity is distorted, but positive free cash flow provides financial flexibility."
        else:
            fin["debt_interpretation"] = msg

    usable = sum(
        1 for k in [
            "revenue_growth", "eps_growth", "pe", "forward_pe", "peg",
            "free_cash_flow", "cash", "total_debt", "gross_margin",
            "operating_margin", "net_margin"
        ]
        if fin.get(k) is not None
    )
    fin["data_quality"] = "Complete" if usable >= 7 else ("Partial" if usable >= 4 else "Incomplete")
    return fin


def v461_trade_plan(row, d=None):
    price = v46_num(row.get("Price"), positive=True) if "v46_num" in globals() else None
    if not price:
        return v46_trade_plan(row, d) if "v46_trade_plan" in globals() else {}

    raw = v46_trade_plan(row, d) if "v46_trade_plan" in globals() else {}
    analyst = (d or {}).get("analyst", {}) if isinstance(d, dict) else {}
    consensus = v46_num(analyst.get("consensus"), positive=True) if "v46_num" in globals() else None
    high = v46_num(analyst.get("high"), positive=True) if "v46_num" in globals() else None

    support = v46_num(raw.get("support1"), positive=True) or v46_num(row.get("52W Low"), positive=True) or price * 0.90
    resistance = v46_num(raw.get("resistance1"), positive=True) or v46_num(row.get("52W High"), positive=True) or price * 1.15
    atr_pct = v46_num(raw.get("atr_pct"), positive=False) or 4.0

    # Entry: useful around current price/pullback, not a 52-week low to current wide range.
    pullback_pct = max(0.03, min(0.08, atr_pct / 100))
    ideal_low = max(price * (1 - pullback_pct * 1.5), support if support < price else price * 0.94)
    ideal_high = price * 1.015
    if ideal_low >= ideal_high:
        ideal_low = price * 0.94
        ideal_high = price * 1.01

    aggressive_low = price * 0.99
    aggressive_high = price * 1.03

    # Stop: not 40% away for a trade. Use trading stop and separate long-term thesis break.
    trading_stop = max(price * 0.88, ideal_low * 0.94)
    if support and support < price:
        # Do not force stop all the way down to 52-week low if it is far away.
        trading_stop = max(trading_stop, support * 0.97)

    thesis_break = support * 0.97 if support and support < trading_stop else min(price * 0.78, trading_stop * 0.90)

    # Target sanity.
    target1 = resistance if resistance and resistance > price else price * 1.15
    if consensus and consensus > price:
        target2 = consensus
    else:
        target2 = max(target1 * 1.08, price * 1.22)

    # Bull target: cap stale/outlier analyst highs.
    if high and high > target2 and high <= price * 2.25:
        target3 = high
    else:
        target3 = min(max(target2 * 1.15, price * 1.35), price * 1.75)

    risk = price - trading_stop
    reward = target1 - price
    rr = reward / risk if risk > 0 and reward > 0 else None

    return {
        "price": price,
        "ideal_low": ideal_low,
        "ideal_high": ideal_high,
        "aggressive_low": aggressive_low,
        "aggressive_high": aggressive_high,
        "stop": trading_stop,
        "trading_stop": trading_stop,
        "thesis_break": thesis_break,
        "target1": target1,
        "target2": target2,
        "target3": target3,
        "risk_reward": rr,
        "atr_pct": atr_pct,
        "support1": support,
        "resistance1": resistance,
    }


def v461_decision(row):
    ticker = v451_clean_ticker(row.get("Ticker"))
    price = v46_num(row.get("Price"), positive=True) or 0
    company = v46_company_context(row) if "v46_company_context" in globals() else {"company": row.get("Company", ticker)}
    analyst_raw = v451_live_analyst_enrichment(
        ticker,
        price=price,
        scan_target=v46_num(row.get("Analyst Target"), positive=True) or 0,
        scan_count=v46_num(row.get("Analyst Count"), positive=True) or 0,
        scan_support=row.get("Analyst Support"),
    )
    analyst = v46_sanitize_analyst(analyst_raw, ticker, price, row) if "v46_sanitize_analyst" in globals() else analyst_raw
    fin = v461_financial_intelligence(ticker, v451_row_to_json(row))
    news = v46_news_intelligence(ticker, company.get("company") or row.get("Company") or ticker) if "v46_news_intelligence" in globals() else {}
    levels = v461_trade_plan(row, {"analyst": analyst})
    completion_score, completion_status, checks = v46_research_completion(company, fin, analyst, news, row) if "v46_research_completion" in globals() else (80, "Enhanced Grade", {})

    table_score = v46_num(row.get("Final Conviction"), positive=False) or 60
    analyst_upside = analyst.get("upside")
    rr = levels.get("risk_reward")
    revenue_growth = v46_num(fin.get("revenue_growth"), positive=False)
    fcf = v46_num(fin.get("free_cash_flow"), positive=False)
    de = v46_num(fin.get("debt_equity"), positive=False)
    news_score = news.get("score", 50) if isinstance(news, dict) else 50
    tech = v45_technical_health(row) if "v45_technical_health" in globals() else {"score": 60}
    tech_score = v46_num(tech.get("score"), positive=False) or 60

    score = table_score * 0.24 + tech_score * 0.18 + news_score * 0.10

    if analyst.get("consensus") and analyst_upside is not None:
        score += 14
        if analyst_upside >= 25:
            score += 6
        elif analyst_upside >= 10:
            score += 3
        elif analyst_upside < 0:
            score -= 8
    elif analyst.get("count"):
        score += 8

    if "bullish" in str(analyst.get("rating_trend", "")).lower():
        score += 6
    if analyst.get("count", 0) >= 20:
        score += 3

    if revenue_growth is not None:
        if revenue_growth >= 15:
            score += 8
        elif revenue_growth >= 5:
            score += 5
        elif revenue_growth < 0:
            score -= 8

    if fcf is not None:
        score += 6 if fcf > 0 else -8

    # Do not over-punish distorted debt/equity if cash/FCF context exists.
    if de is not None:
        if de > 20:
            score -= 1
        elif de <= 2:
            score += 3

    if fin.get("data_quality") == "Complete":
        score += 4
    elif fin.get("data_quality") == "Incomplete":
        score -= 6

    if rr is not None:
        if rr >= 2:
            score += 6
        elif rr >= 1.25:
            score += 3
        elif rr < 1:
            score -= 8

    if news.get("rows"):
        score += 3
    else:
        score -= 2

    if completion_score < 75:
        score -= 5

    score = max(0, min(99, round(score, 1)))

    bullish_case = (
        analyst_upside is not None and analyst_upside >= 20
        and ("bullish" in str(analyst.get("rating_trend", "")).lower() or analyst.get("count", 0) >= 15)
        and (rr is None or rr >= 1.15)
        and (fcf is None or fcf > 0)
    )

    if score >= 86 and (rr is None or rr >= 1.25):
        decision = "BUY ON PULLBACK"
    elif score >= 76:
        decision = "ACTIONABLE WATCH"
    elif bullish_case:
        decision = "BUY ON PULLBACK"
        score = max(score, 72)
    elif score >= 62:
        decision = "SPECULATIVE WATCH"
    else:
        decision = "AVOID / LOW PRIORITY"

    if decision == "BUY ON PULLBACK" and price and levels.get("ideal_low") and levels.get("ideal_high"):
        if levels["ideal_low"] <= price <= levels["ideal_high"]:
            decision = "ACCUMULATE CAREFULLY"

    caveats = []
    if fin.get("warnings"):
        caveats.extend(fin["warnings"][:2])
    if analyst.get("warnings"):
        caveats.extend(analyst["warnings"][:2])
    if not news.get("rows"):
        caveats.append("Recent ticker-specific news did not fully populate from connected sources; confidence is slightly reduced.")
    if revenue_growth is not None and abs(revenue_growth) < 2 and bullish_case:
        caveats.append("Revenue growth appears unusually low versus the broader thesis; verify next earnings/growth update.")

    return {
        "ticker": ticker,
        "company": company,
        "financials": fin,
        "analyst": analyst,
        "news": news,
        "levels": levels,
        "score": score,
        "decision": decision,
        "completion_score": completion_score,
        "completion_status": completion_status,
        "completion_checks": checks,
        "risk": "High" if score < 68 or (levels.get("atr_pct") or 0) >= 8 else ("Moderate" if score < 85 else "Moderate-Low"),
        "caveats": caveats,
    }


def v461_advisor_take(row, d=None):
    d = d or v461_decision(row)
    ticker = d["ticker"]
    levels = d["levels"]
    analyst = d["analyst"]
    fin = d["financials"]
    news = d["news"]

    entry = f"{v45_money(levels.get('ideal_low'))}–{v45_money(levels.get('ideal_high'))}"
    stop = v45_money(levels.get("trading_stop") or levels.get("stop"))
    base = v45_money(levels.get("target2") or analyst.get("consensus"))

    positives = []
    cautions = []

    if analyst.get("count"):
        positives.append(f"{analyst.get('count')} analysts provide coverage")
    if analyst.get("upside") is not None and analyst.get("upside") >= 10:
        positives.append(f"Wall Street consensus implies {analyst.get('upside'):.1f}% upside")
    if fin.get("revenue_growth") is not None and fin.get("revenue_growth") >= 5:
        positives.append(f"revenue growth is {fin.get('revenue_growth'):.1f}%")
    if fin.get("free_cash_flow") is not None and fin.get("free_cash_flow") > 0:
        positives.append("free cash flow is positive")
    if news.get("rows"):
        positives.append("recent ticker-specific news was reviewed")

    if fin.get("debt_interpretation"):
        cautions.append(fin["debt_interpretation"])
    if analyst.get("warnings"):
        cautions.extend(analyst["warnings"][:1])
    if not news.get("rows"):
        cautions.append("recent ticker news is limited from connected sources")

    if not positives:
        positives.append("the setup has some constructive signals, but conviction is limited")

    if d["decision"] in ["ACCUMULATE CAREFULLY", "BUY ON PULLBACK"]:
        lead = (
            f"**Our take:** {ticker} is an **{d['decision']}** candidate. "
            f"The preferred entry zone is **{entry}**, the trading stop is around **{stop}**, "
            f"and the base target is around **{base}**."
        )
    elif d["decision"] == "ACTIONABLE WATCH":
        lead = (
            f"**Our take:** {ticker} deserves a spot on the active watchlist. "
            f"The setup is constructive, but the best risk/reward is near **{entry}** rather than chasing."
        )
    elif d["decision"] == "SPECULATIVE WATCH":
        lead = (
            f"**Our take:** {ticker} has upside potential, but uncertainty is elevated. "
            f"Use smaller sizing and wait for confirmation near **{entry}**."
        )
    else:
        lead = (
            f"**Our take:** {ticker} is currently **AVOID / LOW PRIORITY** because the overall evidence "
            f"does not support a strong risk-adjusted opportunity today."
        )

    return lead, positives[:5], cautions[:5]


def render_v461_advisor_decision_card(row):
    d = v461_decision(row)
    levels = d["levels"]
    lead, positives, cautions = v461_advisor_take(row, d)

    with st.container(border=True):
        st.markdown(f"## {d['ticker']} — {d['company'].get('company', d['ticker'])}")
        st.markdown(f"### 🎯 AI Advisor Verdict: **{d['decision']}**")
        st.markdown(lead)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Advisor Confidence", f"{d['score']:.1f}/100")
        c2.metric("Research Completion", f"{d['completion_score']}/100")
        c3.metric("Research Status", d["completion_status"])
        c4.metric("Risk", d["risk"])

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Current Price", v46_money(levels.get("price")))
        c6.metric("Preferred Entry", f"{v45_money(levels.get('ideal_low'))} - {v45_money(levels.get('ideal_high'))}")
        c7.metric("Trading Stop", v45_money(levels.get("trading_stop") or levels.get("stop")))
        c8.metric("Base Target", v45_money(levels.get("target2")))

        left, right = st.columns(2)
        with left:
            st.markdown("#### Why we like it")
            for p in positives:
                st.markdown(f"✓ {p}")
        with right:
            st.markdown("#### What gives us pause")
            for c in cautions or ["No major caveat identified from populated data."]:
                st.markdown(f"⚠️ {c}")


def render_v461_trade_plan(row):
    d = v461_decision(row)
    l = d["levels"]

    with st.container(border=True):
        st.markdown("### 📍 Entry, Exit & Target Plan")
        st.caption("This separates the trading stop from the long-term thesis break so clients understand near-term risk versus long-term invalidation.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preferred Entry", f"{v45_money(l.get('ideal_low'))} - {v45_money(l.get('ideal_high'))}")
        c2.metric("Aggressive Entry", f"{v45_money(l.get('aggressive_low'))} - {v45_money(l.get('aggressive_high'))}")
        c3.metric("Trading Stop", v45_money(l.get("trading_stop") or l.get("stop")))
        c4.metric("Risk / Reward", "N/A" if l.get("risk_reward") is None else f"{l.get('risk_reward'):.2f}:1")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Long-Term Thesis Break", v45_money(l.get("thesis_break")))
        c6.metric("Conservative Target", v45_money(l.get("target1")))
        c7.metric("Base Target", v45_money(l.get("target2")))
        c8.metric("Bull Target", v45_money(l.get("target3")))

        if l.get("price") and l.get("ideal_low") and l.get("ideal_high") and l["ideal_low"] <= l["price"] <= l["ideal_high"]:
            st.success("Current price is inside the preferred entry zone. A starter position may be reasonable if the client accepts the trading stop.")
        elif l.get("price") and l.get("ideal_high") and l["price"] > l["ideal_high"]:
            st.warning("Current price is above the preferred entry zone. Better risk/reward may come on a pullback.")
        else:
            st.info("Use the entry zone and trading stop together. Do not buy without knowing where the thesis breaks.")


def render_v461_financial_intelligence(row):
    d = v461_decision(row)
    fin = d["financials"]
    b = v45_benchmarks(row) if "v45_benchmarks" in globals() else {"label": "peers"}

    metrics = []
    for label, key, fmt in [
        ("Revenue Growth", "revenue_growth", "pct"),
        ("EPS Growth", "eps_growth", "pct"),
        ("Free Cash Flow", "free_cash_flow", "money"),
        ("Operating Cash Flow", "operating_cash_flow", "money"),
        ("P/E", "pe", "num"),
        ("Forward P/E", "forward_pe", "num"),
        ("PEG", "peg", "num"),
        ("Gross Margin", "gross_margin", "pct"),
        ("Operating Margin", "operating_margin", "pct"),
        ("Net Margin", "net_margin", "pct"),
        ("Debt/Equity", "debt_equity", "debt"),
        ("Cash", "cash", "money"),
        ("Total Debt", "total_debt", "money"),
        ("Net Cash / Debt", "net_cash", "money"),
    ]:
        val = fin.get(key)
        if fmt == "money":
            display = "Unavailable" if val is None else v45_money(val)
        elif fmt == "pct":
            display = "Unavailable" if val is None else f"{val:.1f}%"
        elif fmt == "debt":
            display = "Unavailable" if val is None else f"{val:.2f}x"
        else:
            display = "Unavailable" if val is None else f"{val:.2f}"

        assess, explain = v451_assess_fin(label, val, row)
        if key == "debt_equity" and val is not None and val > 20:
            assess = "Accounting-distorted"
            explain = fin.get("debt_interpretation") or "Debt/equity appears distorted by accounting structure. Use cash, debt, net cash and free cash flow context instead."

        metrics.append({
            "Metric": label,
            "Value": display,
            "Peer Context": v451_industry_avg_text(row, label),
            "Assessment": assess,
            "Plain English": explain,
        })

    usable = sum(1 for m in metrics if m["Value"] != "Unavailable")
    grade_score = min(96, 50 + usable * 3)
    if fin.get("free_cash_flow") and fin.get("free_cash_flow") > 0:
        grade_score += 6
    if fin.get("revenue_growth") and fin.get("revenue_growth") >= 10:
        grade_score += 6
    if fin.get("gross_margin") and fin.get("gross_margin") >= 50:
        grade_score += 4
    if fin.get("net_cash") is not None and fin.get("net_cash") > 0:
        grade_score += 4
    grade = v45_grade(grade_score) if "v45_grade" in globals() else "N/A"

    with st.container(border=True):
        st.markdown(f"### 🏢 Financial Intelligence: **{grade}**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Data Quality", fin.get("data_quality", "Unknown"))
        c2.metric("Metrics Populated", f"{usable}/{len(metrics)}")
        c3.metric("Peer Group", b.get("label", "peers"))

        st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)

        st.markdown("#### Advisor explanation")
        bullets = []
        if fin.get("revenue_growth") is not None:
            bullets.append(f"Revenue growth is {fin['revenue_growth']:.1f}%, which shows whether the business is still expanding.")
        if fin.get("gross_margin") is not None:
            bullets.append(f"Gross margin is {fin['gross_margin']:.1f}%, which helps show pricing power and software profitability.")
        if fin.get("operating_margin") is not None:
            bullets.append(f"Operating margin is {fin['operating_margin']:.1f}%, which helps show how much revenue converts into operating profit.")
        if fin.get("free_cash_flow") is not None:
            bullets.append("Free cash flow is positive, which supports financial flexibility." if fin["free_cash_flow"] > 0 else "Free cash flow is negative, which increases risk.")
        if fin.get("debt_interpretation"):
            bullets.append(fin["debt_interpretation"])

        for btxt in bullets[:6]:
            st.markdown(f"• {btxt}")

        with st.expander("Admin financial diagnostics", expanded=False):
            if fin.get("growth_candidates"):
                st.markdown("**Revenue growth candidates**")
                st.dataframe(pd.DataFrame(fin["growth_candidates"]), use_container_width=True, hide_index=True)
            for x in fin.get("diagnostics", []):
                st.caption(x)


def render_v461_final_thesis(row):
    d = v461_decision(row)
    lead, positives, cautions = v461_advisor_take(row, d)
    levels = d["levels"]

    with st.container(border=True):
        st.markdown("### 🧠 Final Investment Thesis")
        st.markdown(lead)

        st.markdown("#### Investment case")
        for p in positives:
            st.markdown(f"✓ {p}")

        st.markdown("#### Key risks to monitor")
        for c in cautions or ["No major caveat identified from populated data."]:
            st.markdown(f"⚠️ {c}")

        st.markdown(
            f"**Bottom line:** For clients interested in {d['ticker']}, the preferred approach is to use the "
            f"entry zone around **{v45_money(levels.get('ideal_low'))}–{v45_money(levels.get('ideal_high'))}**, "
            f"respect the trading stop near **{v45_money(levels.get('trading_stop') or levels.get('stop'))}**, "
            f"and reassess the thesis if price breaks the long-term thesis level near **{v45_money(levels.get('thesis_break'))}**."
        )
        st.caption("Research guidance only. Not personalized financial advice.")


def render_v461_research_page(row):
    render_v461_advisor_decision_card(row)
    render_v461_trade_plan(row)
    render_v461_financial_intelligence(row)
    render_v46_analyst_intelligence(row)
    render_v46_news_intelligence(row)
    render_v451_metric_interpreter(row)
    if "render_detail_chart_v4184" in globals():
        try:
            render_detail_chart_v4184(row)
        except Exception:
            pass
    render_v461_final_thesis(row)
    render_v46_completion(row)


# Override active detail renderer for V46.1.
def render_detail(row):
    render_v461_research_page(row)


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Research Quality Correction Patch: fixes thesis consistency, margin normalization, stop/target logic, debt interpretation, and client-ready advisor wording.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version", "")).startswith(("V45", "V46"))
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: customer-facing research is visible; admin controls remain hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")



# =========================
# V47.0 CLIENT-FRIENDLY ADVISOR LANGUAGE PATCH
# =========================
# Fixes:
# - Broken markdown sentence rendering in advisor output
# - Replaces "ACCUMULATE CAREFULLY" with "BUY GRADUALLY"
# - Shows a clean action plan with Preferred Entry / Trading Stop / Base Target
# - Keeps V46.1 financial/data-quality fixes intact

def v47_client_decision_label(decision):
    raw = v45_text(decision, "")
    mapping = {
        "ACCUMULATE CAREFULLY": "BUY GRADUALLY",
        "BUY ON PULLBACK": "BUY ON PULLBACK",
        "ACTIONABLE WATCH": "WATCH CLOSELY",
        "SPECULATIVE WATCH": "SPECULATIVE WATCH",
        "AVOID / LOW PRIORITY": "AVOID",
    }
    return mapping.get(raw, raw or "WATCH")


def v47_action_phrase(label):
    if label == "BUY GRADUALLY":
        return "The stock looks attractive, but clients should build the position in stages rather than buying all at once."
    if label == "BUY ON PULLBACK":
        return "The stock looks attractive, but the best risk/reward comes if price pulls back into the preferred entry zone."
    if label == "WATCH CLOSELY":
        return "The setup is constructive, but clients should wait for a cleaner entry or stronger confirmation."
    if label == "SPECULATIVE WATCH":
        return "There is upside potential, but uncertainty is higher, so position sizing should be smaller."
    if label == "AVOID":
        return "The risk/reward does not look attractive enough today."
    return "Monitor the setup and use the entry/stop plan before acting."


def v47_decision(row):
    d = v461_decision(row) if "v461_decision" in globals() else v46_decision(row)
    d = dict(d)
    d["raw_decision"] = d.get("decision")
    d["client_decision"] = v47_client_decision_label(d.get("decision"))
    d["decision"] = d["client_decision"]
    return d


def v47_advisor_take(row, d=None):
    d = d or v47_decision(row)
    ticker = d["ticker"]
    levels = d["levels"]
    analyst = d["analyst"]
    fin = d["financials"]
    news = d["news"]
    label = d.get("client_decision") or d.get("decision")

    entry_low = v45_money(levels.get("ideal_low"))
    entry_high = v45_money(levels.get("ideal_high"))
    stop = v45_money(levels.get("trading_stop") or levels.get("stop"))
    target = v45_money(levels.get("target2") or analyst.get("consensus"))

    positives = []
    cautions = []

    if analyst.get("count"):
        positives.append(f"{analyst.get('count')} analysts provide coverage")
    if analyst.get("upside") is not None and analyst.get("upside") >= 10:
        positives.append(f"Wall Street consensus implies {analyst.get('upside'):.1f}% upside")
    if fin.get("revenue_growth") is not None and fin.get("revenue_growth") >= 5:
        positives.append(f"revenue growth is {fin.get('revenue_growth'):.1f}%")
    if fin.get("gross_margin") is not None and fin.get("gross_margin") >= 40:
        positives.append(f"gross margin is strong at {fin.get('gross_margin'):.1f}%")
    if fin.get("free_cash_flow") is not None and fin.get("free_cash_flow") > 0:
        positives.append("free cash flow is positive")
    if news.get("rows"):
        positives.append("recent ticker-specific news was reviewed")

    if fin.get("debt_interpretation"):
        cautions.append(fin["debt_interpretation"])
    if analyst.get("warnings"):
        cautions.extend(analyst["warnings"][:1])
    if not news.get("rows"):
        cautions.append("recent ticker news is limited from connected sources")
    if not positives:
        positives.append("the setup has some constructive signals, but conviction is limited")

    # Avoid inline markdown artifacts by keeping the main view structured.
    lead = f"**Our take:** {ticker} is a **{label}** candidate."
    action = v47_action_phrase(label)

    plan_lines = [
        f"**Preferred Entry:** {entry_low}–{entry_high}",
        f"**Trading Stop:** {stop}",
        f"**Base Target:** {target}",
    ]

    return lead, action, plan_lines, positives[:6], cautions[:5]


def render_v47_advisor_decision_card(row):
    d = v47_decision(row)
    levels = d["levels"]
    lead, action, plan_lines, positives, cautions = v47_advisor_take(row, d)

    with st.container(border=True):
        st.markdown(f"## {d['ticker']} — {d['company'].get('company', d['ticker'])}")
        st.markdown(f"### 🎯 AI Advisor Verdict: **{d['decision']}**")
        st.markdown(lead)
        st.info(action)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Advisor Confidence", f"{d['score']:.1f}/100")
        c2.metric("Research Completion", f"{d['completion_score']}/100")
        c3.metric("Research Status", d["completion_status"])
        c4.metric("Risk", d["risk"])

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Current Price", v46_money(levels.get("price")))
        c6.metric("Preferred Entry", f"{v45_money(levels.get('ideal_low'))} - {v45_money(levels.get('ideal_high'))}")
        c7.metric("Trading Stop", v45_money(levels.get("trading_stop") or levels.get("stop")))
        c8.metric("Base Target", v45_money(levels.get("target2")))

        st.markdown("#### Action Plan")
        for line in plan_lines:
            st.markdown(f"• {line}")

        left, right = st.columns(2)
        with left:
            st.markdown("#### Why we like it")
            for p in positives:
                st.markdown(f"✓ {p}")
        with right:
            st.markdown("#### What gives us pause")
            for c in cautions or ["No major caveat identified from populated data."]:
                st.markdown(f"⚠️ {c}")


def render_v47_trade_plan(row):
    # Same V46.1 trade logic, but clearer wording.
    d = v47_decision(row)
    l = d["levels"]

    with st.container(border=True):
        st.markdown("### 📍 Entry, Stop & Target Plan")
        st.caption("This gives clients the exact price plan: where to buy, where to control risk, and where the base upside target sits.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preferred Entry", f"{v45_money(l.get('ideal_low'))} - {v45_money(l.get('ideal_high'))}")
        c2.metric("Aggressive Entry", f"{v45_money(l.get('aggressive_low'))} - {v45_money(l.get('aggressive_high'))}")
        c3.metric("Trading Stop", v45_money(l.get("trading_stop") or l.get("stop")))
        c4.metric("Risk / Reward", "N/A" if l.get("risk_reward") is None else f"{l.get('risk_reward'):.2f}:1")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Long-Term Thesis Break", v45_money(l.get("thesis_break")))
        c6.metric("Conservative Target", v45_money(l.get("target1")))
        c7.metric("Base Target", v45_money(l.get("target2")))
        c8.metric("Bull Target", v45_money(l.get("target3")))

        if l.get("price") and l.get("ideal_low") and l.get("ideal_high") and l["ideal_low"] <= l["price"] <= l["ideal_high"]:
            st.success("Current price is inside the preferred entry zone. A starter position may be reasonable if the client accepts the trading stop.")
        elif l.get("price") and l.get("ideal_high") and l["price"] > l["ideal_high"]:
            st.warning("Current price is above the preferred entry zone. Better risk/reward may come on a pullback.")
        else:
            st.info("Use the entry zone and trading stop together. Do not buy without knowing where the thesis breaks.")


def render_v47_final_thesis(row):
    d = v47_decision(row)
    levels = d["levels"]
    lead, action, plan_lines, positives, cautions = v47_advisor_take(row, d)

    with st.container(border=True):
        st.markdown("### 🧠 Final Investment Thesis")
        st.markdown(lead)
        st.info(action)

        st.markdown("#### Action Plan")
        for line in plan_lines:
            st.markdown(f"• {line}")

        st.markdown("#### Investment case")
        for p in positives:
            st.markdown(f"✓ {p}")

        st.markdown("#### Key risks to monitor")
        for c in cautions or ["No major caveat identified from populated data."]:
            st.markdown(f"⚠️ {c}")

        st.markdown(
            f"**Bottom line:** For clients interested in {d['ticker']}, the preferred approach is to use the "
            f"entry zone around **{v45_money(levels.get('ideal_low'))}–{v45_money(levels.get('ideal_high'))}**, "
            f"respect the trading stop near **{v45_money(levels.get('trading_stop') or levels.get('stop'))}**, "
            f"and reassess the thesis if price breaks the long-term thesis level near **{v45_money(levels.get('thesis_break'))}**."
        )
        st.caption("Research guidance only. Not personalized financial advice.")


def render_v47_research_page(row):
    render_v47_advisor_decision_card(row)
    render_v47_trade_plan(row)
    render_v461_financial_intelligence(row)
    render_v46_analyst_intelligence(row)
    render_v46_news_intelligence(row)
    render_v451_metric_interpreter(row)
    if "render_detail_chart_v4184" in globals():
        try:
            render_detail_chart_v4184(row)
        except Exception:
            pass
    render_v47_final_thesis(row)
    render_v46_completion(row)


# Override active detail renderer for V47.
def render_detail(row):
    render_v47_research_page(row)


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Client-friendly advisor language: clean verdicts, structured action plan, preferred entry, trading stop, base target, and no broken markdown output.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version", "")).startswith(("V45", "V46", "V47"))
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: customer-facing research is visible; admin controls remain hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")



# =========================
# V48.0 EXECUTION READINESS ENGINE
# =========================
# Adds:
# - BUY NOW / READY TODAY logic separate from quality ranking
# - Financial completion boost for EPS growth, OCF, FCF, PE, PEG, net margin
# - Ready-to-execute table section
# - Clear distinction: great company vs executable entry today

def v48_safe_get(d, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d.get(k) not in [None, "", "N/A", "nan"]:
            return d.get(k)
    return None


def v48_growth_pct(x):
    v = v46_num(x, positive=False) if "v46_num" in globals() else None
    if v is None:
        return None
    if abs(v) <= 1:
        v *= 100
    if abs(v) > 250:
        return None
    return v


def v48_latest_rows(data):
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


@st.cache_data(ttl=900)
def v48_financial_completion(ticker, row_json=None):
    """
    V48 aggressively fills missing financial fields from all existing current sources:
    - V46.1 financial intelligence
    - FMP ratios/key metrics/growth/income/cashflow/balance
    - Yahoo info fallback
    """
    ticker = v451_clean_ticker(ticker)
    fin = v461_financial_intelligence(ticker, row_json) if "v461_financial_intelligence" in globals() else (v46_financial_intelligence(ticker, row_json) if "v46_financial_intelligence" in globals() else {})
    fin = dict(fin or {})
    fin.setdefault("diagnostics", [])
    fin.setdefault("warnings", [])
    fin.setdefault("completion_sources", {})

    try:
        row = json.loads(row_json) if row_json else {}
    except Exception:
        row = {}

    # Row fallback first
    row_map = {
        "pe": ["P/E", "PE", "PE Ratio", "Trailing PE", "trailingPE"],
        "forward_pe": ["Forward PE", "forwardPE"],
        "peg": ["PEG", "PEG Ratio", "pegRatio"],
        "eps_growth": ["EPS Growth", "Earnings Growth", "Earnings Growth %", "epsGrowth"],
        "free_cash_flow": ["Free Cash Flow", "FCF", "freeCashFlow"],
        "operating_cash_flow": ["Operating Cash Flow", "OCF", "operatingCashFlow"],
        "net_margin": ["Net Margin", "netProfitMargin", "net_margin"],
    }
    for out_key, keys in row_map.items():
        if fin.get(out_key) is None:
            val = v48_safe_get(row, *keys)
            if val is not None:
                if out_key in ["eps_growth", "net_margin"]:
                    fin[out_key] = v48_growth_pct(val)
                else:
                    fin[out_key] = v46_num(val, positive=False)
                fin["completion_sources"][out_key] = "scan row"

    for tv in v451_ticker_variants(ticker):
        # Ratios TTM
        for endpoint, label in [
            (f"ratios-ttm/{tv}", "FMP ratios TTM"),
            (f"key-metrics-ttm/{tv}", "FMP key metrics TTM"),
        ]:
            data, status = v451_fmp_get_try(endpoint, None)
            fin["diagnostics"].append(f"V48 {endpoint}: {status}")
            for d in v48_latest_rows(data)[:1]:
                if fin.get("pe") is None:
                    fin["pe"] = v46_num(v48_safe_get(d, "priceEarningsRatioTTM", "peRatioTTM", "peRatio"), positive=False)
                    if fin.get("pe") is not None: fin["completion_sources"]["pe"] = label
                if fin.get("forward_pe") is None:
                    fin["forward_pe"] = v46_num(v48_safe_get(d, "forwardPE", "forwardPe"), positive=False)
                    if fin.get("forward_pe") is not None: fin["completion_sources"]["forward_pe"] = label
                if fin.get("peg") is None:
                    fin["peg"] = v46_num(v48_safe_get(d, "pegRatioTTM", "pegRatio"), positive=False)
                    if fin.get("peg") is not None: fin["completion_sources"]["peg"] = label
                if fin.get("net_margin") is None:
                    fin["net_margin"] = v48_growth_pct(v48_safe_get(d, "netProfitMarginTTM", "netProfitMargin", "netIncomePerShareTTM"))
                    if fin.get("net_margin") is not None: fin["completion_sources"]["net_margin"] = label
                if fin.get("operating_margin") is None:
                    fin["operating_margin"] = v48_growth_pct(v48_safe_get(d, "operatingProfitMarginTTM", "operatingProfitMargin"))
                    if fin.get("operating_margin") is not None: fin["completion_sources"]["operating_margin"] = label
                if fin.get("gross_margin") is None:
                    fin["gross_margin"] = v48_growth_pct(v48_safe_get(d, "grossProfitMarginTTM", "grossProfitMargin"))
                    if fin.get("gross_margin") is not None: fin["completion_sources"]["gross_margin"] = label

        # Growth
        data, status = v451_fmp_get_try(f"financial-growth/{tv}", {"limit": 2})
        fin["diagnostics"].append(f"V48 financial-growth/{tv}: {status}")
        for d in v48_latest_rows(data)[:1]:
            if fin.get("eps_growth") is None:
                fin["eps_growth"] = v48_growth_pct(v48_safe_get(d, "epsgrowth", "epsGrowth", "growthEPS", "netIncomeGrowth"))
                if fin.get("eps_growth") is not None: fin["completion_sources"]["eps_growth"] = "FMP financial growth"
            if fin.get("revenue_growth") is None:
                fin["revenue_growth"] = v48_growth_pct(v48_safe_get(d, "revenueGrowth", "growthRevenue"))
                if fin.get("revenue_growth") is not None: fin["completion_sources"]["revenue_growth"] = "FMP financial growth"
            if fin.get("free_cash_flow_growth") is None:
                fin["free_cash_flow_growth"] = v48_growth_pct(v48_safe_get(d, "freeCashFlowGrowth", "growthFreeCashFlow"))
                if fin.get("free_cash_flow_growth") is not None: fin["completion_sources"]["free_cash_flow_growth"] = "FMP financial growth"

        # Statements
        income, s1 = v451_fmp_get_try(f"income-statement/{tv}", {"limit": 3})
        cashflow, s2 = v451_fmp_get_try(f"cash-flow-statement/{tv}", {"limit": 3})
        fin["diagnostics"].append(f"V48 income-statement/{tv}: {s1}")
        fin["diagnostics"].append(f"V48 cash-flow-statement/{tv}: {s2}")
        inc_rows = v48_latest_rows(income)
        cf_rows = v48_latest_rows(cashflow)

        if inc_rows:
            cur = inc_rows[0]
            rev = v46_num(cur.get("revenue"), positive=True)
            net_income = v46_num(cur.get("netIncome"), positive=False)
            gross_profit = v46_num(cur.get("grossProfit"), positive=False)
            operating_income = v46_num(cur.get("operatingIncome"), positive=False)
            eps = v46_num(cur.get("eps") or cur.get("epsdiluted"), positive=False)

            if rev and net_income is not None and fin.get("net_margin") is None:
                fin["net_margin"] = (net_income / rev) * 100
                fin["completion_sources"]["net_margin"] = "FMP income statement derived"
            if rev and gross_profit is not None and fin.get("gross_margin") is None:
                fin["gross_margin"] = (gross_profit / rev) * 100
                fin["completion_sources"]["gross_margin"] = "FMP income statement derived"
            if rev and operating_income is not None and fin.get("operating_margin") is None:
                fin["operating_margin"] = (operating_income / rev) * 100
                fin["completion_sources"]["operating_margin"] = "FMP income statement derived"
            if fin.get("eps_growth") is None and len(inc_rows) >= 2:
                prev = v46_num(inc_rows[1].get("eps") or inc_rows[1].get("epsdiluted"), positive=False)
                if eps is not None and prev not in [None, 0]:
                    fin["eps_growth"] = ((eps - prev) / abs(prev)) * 100
                    fin["completion_sources"]["eps_growth"] = "FMP income statement derived"

            if fin.get("pe") is None and eps and eps > 0:
                # Use current price from row if possible
                try:
                    price = v46_num(json.loads(row_json).get("Price"), positive=True) if row_json else None
                except Exception:
                    price = None
                if price:
                    fin["pe"] = price / eps
                    fin["completion_sources"]["pe"] = "derived from price / EPS"

        if cf_rows:
            cur = cf_rows[0]
            if fin.get("operating_cash_flow") is None:
                fin["operating_cash_flow"] = v46_num(v48_safe_get(cur, "operatingCashFlow", "netCashProvidedByOperatingActivities"), positive=False)
                if fin.get("operating_cash_flow") is not None: fin["completion_sources"]["operating_cash_flow"] = "FMP cash flow statement"
            if fin.get("free_cash_flow") is None:
                ocf = v46_num(v48_safe_get(cur, "operatingCashFlow", "netCashProvidedByOperatingActivities"), positive=False)
                capex = v46_num(v48_safe_get(cur, "capitalExpenditure", "capitalExpenditures"), positive=False)
                fcf = v46_num(cur.get("freeCashFlow"), positive=False)
                if fcf is None and ocf is not None and capex is not None:
                    # capex may be negative, so add it to OCF
                    fcf = ocf + capex
                fin["free_cash_flow"] = fcf
                if fin.get("free_cash_flow") is not None: fin["completion_sources"]["free_cash_flow"] = "FMP cash flow statement"

    # Yahoo final fallback
    yi = v451_yahoo_info(ticker)
    if yi:
        fin["diagnostics"].append("V48 Yahoo fallback: returned")
        yahoo_map = [
            ("pe", "trailingPE", False),
            ("forward_pe", "forwardPE", False),
            ("peg", "pegRatio", False),
            ("eps_growth", "earningsGrowth", True),
            ("revenue_growth", "revenueGrowth", True),
            ("net_margin", "profitMargins", True),
            ("gross_margin", "grossMargins", True),
            ("operating_margin", "operatingMargins", True),
            ("operating_cash_flow", "operatingCashflow", False),
            ("free_cash_flow", "freeCashflow", False),
        ]
        for out_key, ykey, is_pct in yahoo_map:
            if fin.get(out_key) is None and yi.get(ykey) is not None:
                fin[out_key] = v48_growth_pct(yi.get(ykey)) if is_pct else v46_num(yi.get(ykey), positive=False)
                if fin.get(out_key) is not None:
                    fin["completion_sources"][out_key] = "Yahoo fallback"

    # Normalize percentage fields again
    for key in ["gross_margin", "operating_margin", "net_margin", "roe", "eps_growth", "revenue_growth", "free_cash_flow_growth"]:
        if fin.get(key) is not None:
            fin[key] = v48_growth_pct(fin.get(key))

    usable = sum(1 for k in ["revenue_growth", "eps_growth", "pe", "forward_pe", "peg", "free_cash_flow", "operating_cash_flow", "gross_margin", "operating_margin", "net_margin", "cash", "total_debt"] if fin.get(k) is not None)
    fin["data_quality"] = "Complete" if usable >= 9 else ("Partial" if usable >= 6 else "Incomplete")
    fin["financial_completion_count"] = usable
    fin["financial_completion_total"] = 12
    return fin


def v48_execution_score(row, d=None):
    d = d or v47_decision(row) if "v47_decision" in globals() else v461_decision(row)
    levels = d.get("levels", {})
    fin = d.get("financials", {})
    analyst = d.get("analyst", {})
    news = d.get("news", {})
    price = v46_num(levels.get("price") or row.get("Price"), positive=True)
    ideal_low = v46_num(levels.get("ideal_low"), positive=True)
    ideal_high = v46_num(levels.get("ideal_high"), positive=True)
    trading_stop = v46_num(levels.get("trading_stop") or levels.get("stop"), positive=True)
    target1 = v46_num(levels.get("target1"), positive=True)
    rr = v46_num(levels.get("risk_reward"), positive=False)
    rsi = v46_num(row.get("RSI"), positive=False)
    volume_ratio = v46_num(row.get("Volume Ratio"), positive=False)

    score = 50
    reasons = []
    blockers = []

    if price and ideal_low and ideal_high and ideal_low <= price <= ideal_high:
        score += 18
        reasons.append("Current price is inside the preferred entry zone")
    elif price and ideal_high and price <= ideal_high * 1.03:
        score += 10
        reasons.append("Current price is close to the preferred entry zone")
    else:
        blockers.append("Price is not in the preferred entry zone")

    if rr is not None and rr >= 1.5:
        score += 14
        reasons.append(f"Risk/reward is attractive at {rr:.2f}:1")
    elif rr is not None and rr >= 1.0:
        score += 6
        reasons.append(f"Risk/reward is acceptable at {rr:.2f}:1")
    else:
        blockers.append("Risk/reward is not attractive enough yet")

    if trading_stop and price:
        stop_risk = (price - trading_stop) / price * 100
        if 5 <= stop_risk <= 18:
            score += 10
            reasons.append(f"Trading stop risk is reasonable at about {stop_risk:.1f}%")
        elif stop_risk > 25:
            blockers.append("Trading stop is too far below current price")
        elif stop_risk < 3:
            blockers.append("Trading stop may be too tight/noisy")

    if rsi is not None:
        if 40 <= rsi <= 65:
            score += 10
            reasons.append("RSI is healthy and not overbought")
        elif rsi > 70:
            score -= 12
            blockers.append("RSI is overbought")
        elif rsi < 30:
            score += 3
            reasons.append("RSI is oversold; possible reversal setup but higher risk")

    if fin.get("data_quality") == "Complete":
        score += 8
        reasons.append("Financial data is sufficiently populated")
    elif fin.get("data_quality") == "Partial":
        score += 3
        blockers.append("Some financial fields are still partial")
    else:
        score -= 8
        blockers.append("Financial data is incomplete")

    if analyst.get("upside") is not None and analyst.get("upside") >= 10:
        score += 8
        reasons.append(f"Analyst consensus implies {analyst.get('upside'):.1f}% upside")
    elif analyst.get("consensus"):
        score += 3
    else:
        blockers.append("Analyst target data is limited")

    if news.get("rows"):
        score += 4
        reasons.append("Recent ticker news was reviewed")
    else:
        score -= 2
        blockers.append("Ticker-specific news is limited")

    if volume_ratio is not None and volume_ratio >= 1.1:
        score += 4
        reasons.append("Volume confirmation is above normal")
    elif volume_ratio is not None and volume_ratio < 0.75:
        score -= 2
        blockers.append("Volume confirmation is light")

    score = max(0, min(100, round(score, 1)))
    if score >= 82 and not any("overbought" in b.lower() for b in blockers):
        label = "BUY NOW"
    elif score >= 72:
        label = "READY / BUY GRADUALLY"
    elif score >= 60:
        label = "WAIT FOR BETTER ENTRY"
    else:
        label = "NOT READY"

    return {"execution_score": score, "execution_label": label, "execution_reasons": reasons[:6], "execution_blockers": blockers[:6]}


def v48_decision(row):
    # Use V47 then enrich financials and override execution-specific label when appropriate.
    d = v47_decision(row) if "v47_decision" in globals() else (v461_decision(row) if "v461_decision" in globals() else {})
    d = dict(d)
    ticker = d.get("ticker") or v451_clean_ticker(row.get("Ticker"))
    fin = v48_financial_completion(ticker, v451_row_to_json(row))
    d["financials"] = fin
    # Rebuild levels using improved data if possible
    levels = v461_trade_plan(row, {"analyst": d.get("analyst", {})}) if "v461_trade_plan" in globals() else d.get("levels", {})
    d["levels"] = levels
    ex = v48_execution_score(row, d)
    d.update(ex)

    # Client-facing decision should separate research quality from executable timing.
    base_label = d.get("decision", "WATCH")
    if ex["execution_label"] == "BUY NOW":
        d["decision"] = "BUY NOW"
    elif ex["execution_label"] == "READY / BUY GRADUALLY":
        d["decision"] = "BUY GRADUALLY"
    elif "BUY" in str(base_label).upper() and ex["execution_label"] == "WAIT FOR BETTER ENTRY":
        d["decision"] = "WAIT FOR BETTER ENTRY"
    elif ex["execution_label"] == "NOT READY":
        d["decision"] = "NOT READY"
    else:
        d["decision"] = base_label

    return d


def v48_advisor_take(row, d=None):
    d = d or v48_decision(row)
    ticker = d["ticker"]
    levels = d["levels"]
    analyst = d["analyst"]
    fin = d["financials"]
    news = d["news"]

    entry = f"{v45_money(levels.get('ideal_low'))}–{v45_money(levels.get('ideal_high'))}"
    stop = v45_money(levels.get("trading_stop") or levels.get("stop"))
    target = v45_money(levels.get("target2") or analyst.get("consensus"))
    decision = d.get("decision", "WATCH")

    if decision == "BUY NOW":
        lead = f"**Our take:** {ticker} is **BUY NOW** because the current price is inside the execution zone and the risk/reward setup is actionable today."
        action = "This is the type of setup the scanner should surface as ready to execute, assuming the client accepts the trading stop."
    elif decision == "BUY GRADUALLY":
        lead = f"**Our take:** {ticker} is a **BUY GRADUALLY** candidate."
        action = "The setup is actionable, but clients should build the position in stages rather than buying all at once."
    elif decision == "WAIT FOR BETTER ENTRY":
        lead = f"**Our take:** {ticker} is a quality idea, but it is **WAIT FOR BETTER ENTRY** today."
        action = "The business may be attractive, but the price/technical setup is not ideal enough for immediate execution."
    elif decision == "NOT READY":
        lead = f"**Our take:** {ticker} is **NOT READY** for execution today."
        action = "The setup does not yet meet enough execution criteria for a new position."
    else:
        lead = f"**Our take:** {ticker} is a **{decision}** candidate."
        action = "Use the entry, stop, and target plan before acting."

    plan_lines = [
        f"**Preferred Entry:** {entry}",
        f"**Trading Stop:** {stop}",
        f"**Base Target:** {target}",
        f"**Execution Score:** {d.get('execution_score', 'N/A')}/100",
    ]

    positives = []
    if fin.get("revenue_growth") is not None and fin.get("revenue_growth") >= 5:
        positives.append(f"revenue growth is {fin.get('revenue_growth'):.1f}%")
    if fin.get("gross_margin") is not None and fin.get("gross_margin") >= 40:
        positives.append(f"gross margin is strong at {fin.get('gross_margin'):.1f}%")
    if fin.get("free_cash_flow") is not None and fin.get("free_cash_flow") > 0:
        positives.append("free cash flow is positive")
    if analyst.get("upside") is not None and analyst.get("upside") >= 10:
        positives.append(f"Wall Street consensus implies {analyst.get('upside'):.1f}% upside")
    positives.extend(d.get("execution_reasons", []))
    # dedupe
    positives = list(dict.fromkeys([p for p in positives if p]))[:7]

    cautions = []
    if fin.get("debt_interpretation"):
        cautions.append(fin["debt_interpretation"])
    cautions.extend(d.get("execution_blockers", []))
    if not news.get("rows"):
        cautions.append("recent ticker news is limited from connected sources")
    cautions = list(dict.fromkeys([c for c in cautions if c]))[:7]
    return lead, action, plan_lines, positives, cautions


def render_v48_advisor_decision_card(row):
    d = v48_decision(row)
    levels = d["levels"]
    lead, action, plan_lines, positives, cautions = v48_advisor_take(row, d)

    with st.container(border=True):
        st.markdown(f"## {d['ticker']} — {d['company'].get('company', d['ticker'])}")
        st.markdown(f"### 🎯 AI Advisor Verdict: **{d['decision']}**")
        st.markdown(lead)
        st.info(action)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Advisor Confidence", f"{d['score']:.1f}/100")
        c2.metric("Execution Score", f"{d.get('execution_score', 0):.1f}/100")
        c3.metric("Research Completion", f"{d['completion_score']}/100")
        c4.metric("Risk", d["risk"])

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Current Price", v46_money(levels.get("price")))
        c6.metric("Preferred Entry", f"{v45_money(levels.get('ideal_low'))} - {v45_money(levels.get('ideal_high'))}")
        c7.metric("Trading Stop", v45_money(levels.get("trading_stop") or levels.get("stop")))
        c8.metric("Base Target", v45_money(levels.get("target2")))

        st.markdown("#### Action Plan")
        for line in plan_lines:
            st.markdown(f"• {line}")

        left, right = st.columns(2)
        with left:
            st.markdown("#### Why we like it")
            for p in positives or ["No strong positive driver isolated."]:
                st.markdown(f"✓ {p}")
        with right:
            st.markdown("#### What gives us pause")
            for c in cautions or ["No major caveat identified from populated data."]:
                st.markdown(f"⚠️ {c}")


def render_v48_execution_readiness_panel(row):
    d = v48_decision(row)
    with st.container(border=True):
        st.markdown("### 🔥 Execution Readiness")
        st.caption("This separates a good stock from a stock that is ready to buy today.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Execution Status", d.get("execution_label"))
        c2.metric("Execution Score", f"{d.get('execution_score', 0):.1f}/100")
        c3.metric("Advisor Verdict", d.get("decision"))
        left, right = st.columns(2)
        with left:
            st.markdown("#### Ready factors")
            for r in d.get("execution_reasons", []) or ["No ready factors found yet."]:
                st.markdown(f"✓ {r}")
        with right:
            st.markdown("#### Waiting factors")
            for b in d.get("execution_blockers", []) or ["No major blockers identified."]:
                st.markdown(f"⚠️ {b}")


def render_v48_financial_intelligence(row):
    d = v48_decision(row)
    fin = d["financials"]
    b = v45_benchmarks(row) if "v45_benchmarks" in globals() else {"label": "peers"}

    metrics = []
    for label, key, fmt in [
        ("Revenue Growth", "revenue_growth", "pct"),
        ("EPS Growth", "eps_growth", "pct"),
        ("Free Cash Flow", "free_cash_flow", "money"),
        ("Operating Cash Flow", "operating_cash_flow", "money"),
        ("P/E", "pe", "num"),
        ("Forward P/E", "forward_pe", "num"),
        ("PEG", "peg", "num"),
        ("Gross Margin", "gross_margin", "pct"),
        ("Operating Margin", "operating_margin", "pct"),
        ("Net Margin", "net_margin", "pct"),
        ("Cash", "cash", "money"),
        ("Total Debt", "total_debt", "money"),
        ("Net Cash / Debt", "net_cash", "money"),
    ]:
        val = fin.get(key)
        if fmt == "money":
            display = "Unavailable" if val is None else v45_money(val)
        elif fmt == "pct":
            display = "Unavailable" if val is None else f"{val:.1f}%"
        else:
            display = "Unavailable" if val is None else f"{val:.2f}"
        assess, explain = v451_assess_fin(label, val, row)
        metrics.append({"Metric": label, "Value": display, "Peer Context": v451_industry_avg_text(row, label), "Assessment": assess, "Plain English": explain})

    usable = sum(1 for m in metrics if m["Value"] != "Unavailable")
    grade_score = min(98, 48 + usable * 3.5)
    if fin.get("free_cash_flow") and fin.get("free_cash_flow") > 0: grade_score += 5
    if fin.get("operating_cash_flow") and fin.get("operating_cash_flow") > 0: grade_score += 3
    if fin.get("revenue_growth") and fin.get("revenue_growth") >= 10: grade_score += 5
    if fin.get("gross_margin") and fin.get("gross_margin") >= 50: grade_score += 4
    grade = v45_grade(grade_score) if "v45_grade" in globals() else "N/A"

    with st.container(border=True):
        st.markdown(f"### 🏢 Financial Intelligence: **{grade}**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Data Quality", fin.get("data_quality", "Unknown"))
        c2.metric("Metrics Populated", f"{usable}/{len(metrics)}")
        c3.metric("Peer Group", b.get("label", "peers"))
        st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)

        st.markdown("#### Advisor explanation")
        bullets = []
        if fin.get("revenue_growth") is not None:
            bullets.append(f"Revenue growth is {fin['revenue_growth']:.1f}%, showing whether the business is expanding.")
        if fin.get("eps_growth") is not None:
            bullets.append(f"EPS growth is {fin['eps_growth']:.1f}%, showing whether growth is converting into earnings.")
        if fin.get("operating_cash_flow") is not None:
            bullets.append("Operating cash flow is positive, which supports business quality." if fin["operating_cash_flow"] > 0 else "Operating cash flow is negative, which raises quality risk.")
        if fin.get("free_cash_flow") is not None:
            bullets.append("Free cash flow is positive, which supports financial flexibility." if fin["free_cash_flow"] > 0 else "Free cash flow is negative, which increases risk.")
        if fin.get("net_margin") is not None:
            bullets.append(f"Net margin is {fin['net_margin']:.1f}%, showing how much revenue converts into bottom-line profit.")
        if fin.get("debt_interpretation"):
            bullets.append(fin["debt_interpretation"])
        for btxt in bullets[:7]:
            st.markdown(f"• {btxt}")

        with st.expander("Admin financial completion diagnostics", expanded=False):
            if fin.get("completion_sources"):
                st.markdown("**Field completion sources**")
                st.dataframe(pd.DataFrame([{"Field": k, "Source": v} for k, v in fin["completion_sources"].items()]), use_container_width=True, hide_index=True)
            for x in fin.get("diagnostics", []):
                st.caption(x)


def render_v48_ready_to_buy_table(df, title="🔥 Ready to Buy Today"):
    if df is None or df.empty:
        return
    rows = []
    for _, row in df.head(80).iterrows():
        try:
            d = v48_decision(row)
            if d.get("execution_label") in ["BUY NOW", "READY / BUY GRADUALLY"]:
                levels = d.get("levels", {})
                rows.append({
                    "Ticker": d.get("ticker"),
                    "Decision": d.get("decision"),
                    "Execution Score": d.get("execution_score"),
                    "Price": v45_money(levels.get("price")),
                    "Preferred Entry": f"{v45_money(levels.get('ideal_low'))} - {v45_money(levels.get('ideal_high'))}",
                    "Stop": v45_money(levels.get("trading_stop") or levels.get("stop")),
                    "Base Target": v45_money(levels.get("target2")),
                    "Why Now": "; ".join(d.get("execution_reasons", [])[:2]),
                })
        except Exception:
            continue
    if rows:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.caption("These are the names where the research and entry setup are closest to executable today.")
            st.dataframe(pd.DataFrame(rows).sort_values("Execution Score", ascending=False), use_container_width=True, hide_index=True)
    else:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.info("No stock currently meets the execution-ready threshold. This means the scanner found quality ideas, but none have a clean enough entry/risk setup right now.")


def render_v48_final_thesis(row):
    d = v48_decision(row)
    lead, action, plan_lines, positives, cautions = v48_advisor_take(row, d)

    with st.container(border=True):
        st.markdown("### 🧠 Final Investment Thesis")
        st.markdown(lead)
        st.info(action)
        st.markdown("#### Action Plan")
        for line in plan_lines:
            st.markdown(f"• {line}")
        st.markdown("#### Investment case")
        for p in positives:
            st.markdown(f"✓ {p}")
        st.markdown("#### Key risks to monitor")
        for c in cautions or ["No major caveat identified from populated data."]:
            st.markdown(f"⚠️ {c}")
        st.caption("Research guidance only. Not personalized financial advice.")


def render_v48_research_page(row):
    render_v48_advisor_decision_card(row)
    render_v48_execution_readiness_panel(row)
    render_v47_trade_plan(row)
    render_v48_financial_intelligence(row)
    render_v46_analyst_intelligence(row)
    render_v46_news_intelligence(row)
    render_v451_metric_interpreter(row)
    if "render_detail_chart_v4184" in globals():
        try:
            render_detail_chart_v4184(row)
        except Exception:
            pass
    render_v48_final_thesis(row)
    render_v46_completion(row)


def render_detail(row):
    render_v48_research_page(row)


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Execution Readiness Engine: separates top-ranked quality stocks from stocks that are actually ready to buy today.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version", "")).startswith(("V45", "V46", "V47", "V48"))
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: customer-facing research is visible; admin controls remain hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")


# Optional override: enhance main page if render_table calls are not modified.
# V48 ready-to-buy section can be manually called near scanner tables in future UI cleanup.



# =========================
# V49.0 CLEAN TRUST ENGINE
# =========================
# One score. One verdict. One trade plan. One research report.
# This does not display legacy V42-V48 report sections to clients.

def v49_num(x, positive=False):
    try:
        v = v46_num(x, positive=positive)
    except Exception:
        try:
            if x in (None, "", "N/A", "None"):
                return None
            if isinstance(x, str):
                x = x.replace("$", "").replace(",", "").replace("%", "").strip()
            v = float(x)
        except Exception:
            return None
    if v is None:
        return None
    try:
        if positive and v <= 0:
            return None
    except Exception:
        return None
    return v


def v49_money(x):
    v = v49_num(x, positive=False)
    return "N/A" if v is None else v45_money(v)


def v49_pct(x):
    v = v49_num(x, positive=False)
    return "N/A" if v is None else v45_pct(v)


def v49_percent(x):
    v = v49_num(x, positive=False)
    if v is None:
        return None
    if abs(v) <= 1:
        v *= 100
    if abs(v) > 500:
        return None
    return v


def v49_text(x, default=""):
    try:
        return v45_text(x, default)
    except Exception:
        return default if x in [None, ""] else str(x)


@st.cache_data(ttl=900)
def v49_financials(ticker, row_json=None):
    # Use the best available V48/V46 completion functions, but the visible report below is V49-only.
    try:
        fin = v48_financial_completion(ticker, row_json)
    except Exception:
        try:
            fin = v461_financial_intelligence(ticker, row_json)
        except Exception:
            try:
                fin = v46_financial_intelligence(ticker, row_json)
            except Exception:
                fin = {}
    fin = dict(fin or {})
    fin.setdefault("diagnostics", [])
    fin.setdefault("completion_sources", {})
    fin.setdefault("warnings", [])

    for key in ["revenue_growth", "eps_growth", "gross_margin", "operating_margin", "net_margin", "roe"]:
        if fin.get(key) is not None:
            fixed = v49_percent(fin.get(key))
            if fixed is not None:
                fin[key] = fixed

    # Coverage count
    core = ["revenue_growth", "eps_growth", "free_cash_flow", "operating_cash_flow", "pe", "forward_pe", "peg", "gross_margin", "operating_margin", "net_margin", "cash", "total_debt"]
    populated = sum(1 for k in core if fin.get(k) is not None)
    fin["coverage_count"] = populated
    fin["coverage_total"] = len(core)
    if populated >= 9:
        fin["coverage_label"] = "Excellent"
    elif populated >= 6:
        fin["coverage_label"] = "Good"
    elif populated >= 4:
        fin["coverage_label"] = "Partial"
    else:
        fin["coverage_label"] = "Limited"

    cash = v49_num(fin.get("cash"), positive=False)
    debt = v49_num(fin.get("total_debt"), positive=False)
    if cash is not None and debt is not None:
        fin["net_cash"] = cash - debt
        if debt:
            fin["cash_debt_ratio"] = cash / debt

    de = v49_num(fin.get("debt_equity"), positive=False)
    if de is not None and de > 20:
        if cash is not None and debt is not None:
            if cash >= debt:
                fin["balance_sheet_plain"] = f"Debt/equity is accounting-distorted, but cash exceeds total debt by about {v49_money(cash - debt)}."
            else:
                fin["balance_sheet_plain"] = f"Debt/equity is accounting-distorted; net debt is about {v49_money(debt - cash)}. Use cash flow to judge risk."
        elif fin.get("free_cash_flow") and fin.get("free_cash_flow") > 0:
            fin["balance_sheet_plain"] = "Debt/equity is accounting-distorted, but positive free cash flow supports flexibility."
        else:
            fin["balance_sheet_plain"] = "Debt/equity appears accounting-distorted; do not judge balance-sheet risk from this ratio alone."
    elif de is not None:
        fin["balance_sheet_plain"] = f"Debt/equity is {de:.2f}x."

    return fin


@st.cache_data(ttl=600)
def v49_news(ticker, company=""):
    try:
        return v46_news_intelligence(ticker, company)
    except Exception:
        try:
            return v451_live_news_enrichment(ticker, company)
        except Exception:
            return {"rows": [], "bullish": [], "bearish": [], "sentiment": "N/A", "score": 50, "diagnostics": []}


@st.cache_data(ttl=900)
def v49_analyst(ticker, price=0, scan_target=0, scan_count=0, scan_support=""):
    try:
        a = v451_live_analyst_enrichment(ticker, price=price, scan_target=scan_target, scan_count=scan_count, scan_support=scan_support)
    except Exception:
        a = {}
    a = dict(a or {})
    price = v49_num(price, positive=True)
    consensus = v49_num(a.get("consensus"), positive=True) or v49_num(scan_target, positive=True)
    high = v49_num(a.get("high"), positive=True)
    low = v49_num(a.get("low"), positive=True)
    if price and high and high > price * 3:
        a["high_unfiltered"] = high
        high = None
    if price and low and low < price * 0.25:
        a["low_unfiltered"] = low
        low = None
    a["consensus"] = consensus
    a["high"] = high
    a["low"] = low
    if price and consensus:
        a["upside"] = ((consensus - price) / price) * 100
    else:
        a["upside"] = None
    a["count"] = int(v49_num(a.get("count"), positive=True) or v49_num(scan_count, positive=True) or 0)
    if not a.get("rating_trend"):
        a["rating_trend"] = v49_text(scan_support, "N/A")
    return a


def v49_technical(row):
    price = v49_num(row.get("Price"), positive=True) or 0
    rsi = v49_num(row.get("RSI"), positive=False)
    atr_pct = v49_num(row.get("ATR %"), positive=False)
    if atr_pct is None:
        atr_pct = v49_num(row.get("ATR Percent"), positive=False)
    if atr_pct is None:
        atr_pct = 4.0

    try:
        old_levels = v45_trade_levels(row)
    except Exception:
        old_levels = {}

    support = v49_num(old_levels.get("support1"), positive=True) or v49_num(row.get("Support"), positive=True)
    resistance = v49_num(old_levels.get("resistance1"), positive=True) or v49_num(row.get("Resistance"), positive=True)

    low_52 = v49_num(row.get("52W Low"), positive=True)
    high_52 = v49_num(row.get("52W High"), positive=True)

    # Do not use 52w low as near-term support if it is too far away.
    if support is None and low_52 and price and low_52 >= price * 0.82:
        support = low_52
    if resistance is None and high_52 and price and high_52 > price:
        resistance = high_52

    volume_ratio = v49_num(row.get("Volume Ratio"), positive=False)
    return {
        "price": price,
        "rsi": rsi,
        "atr_pct": atr_pct,
        "support": support,
        "resistance": resistance,
        "volume_ratio": volume_ratio,
        "low_52": low_52,
        "high_52": high_52,
    }


def v49_trade_plan(row, analyst=None):
    t = v49_technical(row)
    price = t["price"]
    if not price:
        return {"price": None}

    atr_pct = t["atr_pct"] or 4.0
    pullback_pct = max(0.03, min(0.08, atr_pct / 100 * 1.25))
    support = t["support"]

    if support and price * 0.85 <= support <= price * 1.02:
        ideal_entry = min(price * 0.99, support * 1.03)
    else:
        ideal_entry = price * (1 - pullback_pct)

    # Entry should not extend above current price. Aggressive entry handles current-price buying.
    ideal_entry = min(ideal_entry, price * 0.99)
    aggressive_low = price * 0.99
    aggressive_high = price * 1.01

    atr_stop_pct = max(0.06, min(0.14, atr_pct / 100 * 1.8))
    stop = ideal_entry * (1 - atr_stop_pct)
    # avoid absurdly wide trade stops
    stop = max(stop, price * 0.82)
    stop = min(stop, price * 0.94)

    thesis_break = stop * 0.92

    analyst_target = v49_num((analyst or {}).get("consensus"), positive=True)
    analyst_high = v49_num((analyst or {}).get("high"), positive=True)
    resistance = t["resistance"]

    target1 = resistance if resistance and resistance > price * 1.04 else price * 1.12
    if analyst_target and analyst_target > price * 1.05 and analyst_target < price * 2.5:
        base_target = analyst_target
    else:
        base_target = max(price * 1.18, target1 * 1.05)
    if analyst_high and analyst_high > base_target and analyst_high <= price * 2.5:
        bull_target = analyst_high
    else:
        bull_target = min(max(base_target * 1.15, price * 1.30), price * 1.75)

    risk = price - stop
    reward = base_target - price
    rr = reward / risk if risk > 0 and reward > 0 else None

    return {
        "price": price,
        "ideal_entry": ideal_entry,
        "aggressive_low": aggressive_low,
        "aggressive_high": aggressive_high,
        "stop": stop,
        "thesis_break": thesis_break,
        "target1": target1,
        "base_target": base_target,
        "bull_target": bull_target,
        "risk_reward": rr,
        "atr_pct": atr_pct,
        "support": support,
        "resistance": resistance,
    }


def v49_checklist(row, plan, analyst, fin, news):
    price = v49_num(plan.get("price"), positive=True)
    ideal = v49_num(plan.get("ideal_entry"), positive=True)
    rr = v49_num(plan.get("risk_reward"), positive=False)
    rsi = v49_technical(row).get("rsi")
    analyst_upside = v49_num(analyst.get("upside"), positive=False)
    volume_ratio = v49_technical(row).get("volume_ratio")

    near_entry = bool(price and ideal and price <= ideal * 1.03)
    rr_ok = bool(rr is not None and rr >= 1.5)
    rsi_ok = bool(rsi is None or rsi < 72)
    analyst_ok = bool(analyst_upside is not None and analyst_upside >= 10)
    data_ok = bool(fin.get("coverage_count", 0) >= 6)

    checks = [
        ("Price near support/entry", near_entry),
        ("Risk/reward ≥ 1.5:1", rr_ok),
        ("RSI not overbought", rsi_ok),
        ("Analyst upside ≥ 10%", analyst_ok),
    ]
    passed = sum(1 for _, ok in checks if ok)

    if passed == 4 and data_ok:
        verdict = "BUY NOW"
    elif passed >= 3 and data_ok:
        verdict = "BUY GRADUALLY"
    elif passed >= 2:
        verdict = "WATCH"
    else:
        verdict = "AVOID"

    reasons = []
    blockers = []
    for label, ok in checks:
        (reasons if ok else blockers).append(label)
    if not data_ok:
        blockers.append("Financial data coverage below preferred threshold")
    if volume_ratio is not None and volume_ratio < 0.75:
        blockers.append("Volume confirmation is light")
    return {
        "checks": checks,
        "passed": passed,
        "verdict": verdict,
        "reasons": reasons,
        "blockers": blockers,
        "data_ok": data_ok,
    }


def v49_opportunity_score(row, plan, analyst, fin, news, checklist):
    # One score only. Designed to align with the verdict and trade plan.
    score = 0

    # Fundamentals 40
    f_score = 0
    if fin.get("revenue_growth") is not None:
        rg = fin["revenue_growth"]
        f_score += 10 if rg >= 15 else (7 if rg >= 5 else (3 if rg >= 0 else 0))
    if fin.get("gross_margin") is not None:
        gm = fin["gross_margin"]
        f_score += 8 if gm >= 50 else (5 if gm >= 30 else 2)
    if fin.get("free_cash_flow") is not None:
        f_score += 8 if fin["free_cash_flow"] > 0 else 0
    if fin.get("forward_pe") is not None or fin.get("peg") is not None:
        peg = v49_num(fin.get("peg"), positive=False)
        fpe = v49_num(fin.get("forward_pe"), positive=False)
        if peg is not None and peg <= 1.5:
            f_score += 8
        elif fpe is not None and fpe <= 35:
            f_score += 6
        else:
            f_score += 3
    if fin.get("coverage_count", 0) >= 8:
        f_score += 6
    score += min(40, f_score)

    # Technical/execution 25
    t_score = 0
    if checklist["checks"][0][1]:
        t_score += 8
    if checklist["checks"][1][1]:
        t_score += 9
    if checklist["checks"][2][1]:
        t_score += 5
    rr = v49_num(plan.get("risk_reward"), positive=False)
    if rr is not None and rr >= 2:
        t_score += 3
    score += min(25, t_score)

    # Analysts 20
    a_score = 0
    up = v49_num(analyst.get("upside"), positive=False)
    if up is not None:
        a_score += 10 if up >= 20 else (7 if up >= 10 else (3 if up > 0 else 0))
    if analyst.get("count", 0) >= 20:
        a_score += 5
    elif analyst.get("count", 0) >= 5:
        a_score += 3
    if "bullish" in str(analyst.get("rating_trend", "")).lower():
        a_score += 5
    score += min(20, a_score)

    # News/risk 15
    n_score = 8
    if news.get("rows"):
        n_score += 4
    if news.get("bullish"):
        n_score += 2
    if news.get("bearish"):
        n_score -= 2
    if fin.get("balance_sheet_plain") and "distorted" in fin.get("balance_sheet_plain", "").lower():
        n_score -= 1
    score += max(0, min(15, n_score))

    return max(0, min(100, round(score, 1)))


def v49_build_research_report(row):
    ticker = v451_clean_ticker(row.get("Ticker"))
    company = v49_text(row.get("Company"), ticker)
    price = v49_num(row.get("Price"), positive=True) or 0
    scan_target = v49_num(row.get("Analyst Target"), positive=True) or 0
    scan_count = v49_num(row.get("Analyst Count"), positive=True) or 0
    scan_support = row.get("Analyst Support")

    analyst = v49_analyst(ticker, price=price, scan_target=scan_target, scan_count=scan_count, scan_support=scan_support)
    fin = v49_financials(ticker, v451_row_to_json(row))
    news = v49_news(ticker, company)
    plan = v49_trade_plan(row, analyst)
    checklist = v49_checklist(row, plan, analyst, fin, news)
    score = v49_opportunity_score(row, plan, analyst, fin, news, checklist)

    # Align verdict with score if severe mismatch.
    verdict = checklist["verdict"]
    if score >= 85 and checklist["passed"] >= 3 and fin.get("coverage_count", 0) >= 6:
        verdict = "BUY GRADUALLY" if verdict == "WATCH" else verdict
    if score < 45:
        verdict = "AVOID"

    return {
        "ticker": ticker,
        "company": company,
        "price": price,
        "analyst": analyst,
        "financials": fin,
        "news": news,
        "plan": plan,
        "checklist": checklist,
        "opportunity_score": score,
        "verdict": verdict,
    }


def v49_verdict_explanation(verdict):
    if verdict == "BUY NOW":
        return "The setup is actionable today because price, risk/reward, momentum, and analyst upside are aligned."
    if verdict == "BUY GRADUALLY":
        return "The stock is attractive, but clients should build the position in stages rather than buying all at once."
    if verdict == "WATCH":
        return "The company or thesis may be interesting, but the entry/risk setup is not strong enough yet."
    return "The current risk/reward or data setup does not justify a new position today."


def render_v49_research_summary(row):
    r = v49_build_research_report(row)
    p = r["plan"]
    with st.container(border=True):
        st.markdown(f"## {r['ticker']} — {r['company']}")
        st.markdown(f"### 🎯 Verdict: **{r['verdict']}**")
        st.info(v49_verdict_explanation(r["verdict"]))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Opportunity Score", f"{r['opportunity_score']:.1f}/100")
        c2.metric("Current Price", v49_money(p.get("price")))
        c3.metric("Ideal Entry", f"Below {v49_money(p.get('ideal_entry'))}")
        c4.metric("Base Target", v49_money(p.get("base_target")))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Aggressive Entry", f"{v49_money(p.get('aggressive_low'))} - {v49_money(p.get('aggressive_high'))}")
        c6.metric("Trading Stop", v49_money(p.get("stop")))
        c7.metric("Risk/Reward", "N/A" if p.get("risk_reward") is None else f"{p.get('risk_reward'):.2f}:1")
        c8.metric("Data Coverage", f"{r['financials'].get('coverage_label')} ({r['financials'].get('coverage_count')}/{r['financials'].get('coverage_total')})")

        st.markdown("#### BUY NOW checklist")
        cols = st.columns(4)
        for i, (label, ok) in enumerate(r["checklist"]["checks"]):
            cols[i].metric(label, "✅" if ok else "❌")

        left, right = st.columns(2)
        with left:
            st.markdown("#### Why we like it")
            positives = []
            fin = r["financials"]
            analyst = r["analyst"]
            news = r["news"]
            if fin.get("revenue_growth") is not None:
                positives.append(f"Revenue growth is {fin['revenue_growth']:.1f}%")
            if fin.get("gross_margin") is not None:
                positives.append(f"Gross margin is {fin['gross_margin']:.1f}%")
            if fin.get("free_cash_flow") is not None and fin["free_cash_flow"] > 0:
                positives.append("Free cash flow is positive")
            if analyst.get("upside") is not None:
                positives.append(f"Wall Street target implies {analyst['upside']:.1f}% upside")
            if news.get("rows"):
                positives.append("Recent ticker-specific news was reviewed")
            for x in positives[:6] or ["No major positive driver isolated."]:
                st.markdown(f"✓ {x}")
        with right:
            st.markdown("#### What gives us pause")
            blockers = list(r["checklist"]["blockers"])
            if r["financials"].get("balance_sheet_plain"):
                blockers.append(r["financials"]["balance_sheet_plain"])
            if not r["news"].get("rows"):
                blockers.append("Recent ticker news is limited")
            for x in blockers[:6] or ["No major blocker identified."]:
                st.markdown(f"⚠️ {x}")


def render_v49_trade_plan(row):
    r = v49_build_research_report(row)
    p = r["plan"]
    with st.container(border=True):
        st.markdown("### 📍 Trade Plan")
        st.caption("This is the only trade plan shown to clients. It separates ideal entry, aggressive entry, stop, and targets.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ideal Entry", f"Below {v49_money(p.get('ideal_entry'))}")
        c2.metric("Aggressive Entry", f"{v49_money(p.get('aggressive_low'))} - {v49_money(p.get('aggressive_high'))}")
        c3.metric("Trading Stop", v49_money(p.get("stop")))
        c4.metric("Risk/Reward", "N/A" if p.get("risk_reward") is None else f"{p.get('risk_reward'):.2f}:1")
        c5, c6, c7 = st.columns(3)
        c5.metric("Conservative Target", v49_money(p.get("target1")))
        c6.metric("Base Target", v49_money(p.get("base_target")))
        c7.metric("Bull Target", v49_money(p.get("bull_target")))

        if r["verdict"] == "BUY NOW":
            st.success("Actionable today: the checklist and risk/reward support a new starter position.")
        elif r["verdict"] == "BUY GRADUALLY":
            st.info("Actionable in stages: consider partial sizing rather than a full position.")
        elif r["verdict"] == "WATCH":
            st.warning("Wait for a cleaner entry, better risk/reward, or stronger technical confirmation.")
        else:
            st.error("Avoid new position for now.")


def render_v49_financials(row):
    r = v49_build_research_report(row)
    fin = r["financials"]
    rows = []
    metric_defs = [
        ("Revenue Growth", "revenue_growth", "pct", "Shows whether the business is expanding."),
        ("EPS Growth", "eps_growth", "pct", "Shows whether growth is converting into earnings."),
        ("Free Cash Flow", "free_cash_flow", "money", "Shows whether the business generates cash after reinvestment."),
        ("Operating Cash Flow", "operating_cash_flow", "money", "Shows cash generated from core operations."),
        ("Forward P/E", "forward_pe", "num", "Valuation based on expected earnings."),
        ("P/E", "pe", "num", "Valuation based on trailing earnings."),
        ("PEG", "peg", "num", "Valuation adjusted for growth."),
        ("Gross Margin", "gross_margin", "pct", "Pricing power and business model quality."),
        ("Operating Margin", "operating_margin", "pct", "Operating profitability."),
        ("Net Margin", "net_margin", "pct", "Bottom-line profitability."),
        ("Cash", "cash", "money", "Liquidity available."),
        ("Total Debt", "total_debt", "money", "Debt obligations."),
        ("Net Cash / Debt", "net_cash", "money", "Cash minus debt."),
    ]
    for label, key, fmt, meaning in metric_defs:
        val = fin.get(key)
        if val is None:
            continue
        if fmt == "money":
            display = v49_money(val)
        elif fmt == "pct":
            display = f"{val:.1f}%"
        else:
            display = f"{val:.2f}"
        rows.append({"Metric": label, "Value": display, "Meaning": meaning})

    with st.container(border=True):
        st.markdown("### 🏢 Financial Health")
        st.metric("Data Coverage", f"{fin.get('coverage_label')} ({fin.get('coverage_count')}/{fin.get('coverage_total')})")
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Financial metrics did not populate enough for a useful client-facing table.")

        bullets = []
        if fin.get("revenue_growth") is not None:
            bullets.append(f"Revenue growth is {fin['revenue_growth']:.1f}%.")
        if fin.get("gross_margin") is not None:
            bullets.append(f"Gross margin is {fin['gross_margin']:.1f}%, which helps show pricing power.")
        if fin.get("free_cash_flow") is not None:
            bullets.append("Free cash flow is positive." if fin["free_cash_flow"] > 0 else "Free cash flow is negative.")
        if fin.get("balance_sheet_plain"):
            bullets.append(fin["balance_sheet_plain"])
        if bullets:
            st.markdown("#### Plain-English readout")
            for b in bullets:
                st.markdown(f"• {b}")

        if not is_viewer():
            with st.expander("Admin financial diagnostics", expanded=False):
                if fin.get("completion_sources"):
                    st.dataframe(pd.DataFrame([{"Field": k, "Source": v} for k, v in fin["completion_sources"].items()]), use_container_width=True, hide_index=True)
                for x in fin.get("diagnostics", [])[:80]:
                    st.caption(x)


def render_v49_analysts(row):
    r = v49_build_research_report(row)
    a = r["analyst"]
    with st.container(border=True):
        st.markdown("### 🏦 Wall Street View")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Consensus Target", v49_money(a.get("consensus")))
        c2.metric("Upside", v49_pct(a.get("upside")))
        c3.metric("Coverage", str(a.get("count") or "N/A"))
        c4.metric("Sentiment", a.get("rating_trend") or "N/A")
        if a.get("consensus"):
            st.info(f"Analyst consensus supports a base target near {v49_money(a.get('consensus'))}. Use this as confirmation, not as the only reason to buy.")
        if a.get("firm_rows"):
            st.markdown("#### Recent analyst activity")
            st.dataframe(pd.DataFrame(a["firm_rows"][:8]), use_container_width=True, hide_index=True)
        if not is_viewer():
            with st.expander("Admin analyst diagnostics", expanded=False):
                for x in a.get("diagnostics", [])[:80]:
                    st.caption(x)


def render_v49_news(row):
    r = v49_build_research_report(row)
    news = r["news"]
    if not news.get("rows"):
        if not is_viewer():
            with st.expander("Admin news diagnostics — no client news shown", expanded=False):
                for x in news.get("diagnostics", [])[:80]:
                    st.caption(x)
        return

    with st.container(border=True):
        st.markdown("### 📰 Catalysts & Risks")
        c1, c2 = st.columns(2)
        c1.metric("News Sentiment", news.get("sentiment", "N/A"))
        c2.metric("Headlines Reviewed", len(news.get("rows", [])))
        left, right = st.columns(2)
        with left:
            st.markdown("#### Bullish catalysts")
            for h in news.get("bullish") or ["No strong bullish catalyst isolated."]:
                st.markdown(f"✓ {h}")
        with right:
            st.markdown("#### Bearish risks")
            for h in news.get("bearish") or ["No strong bearish risk isolated."]:
                st.markdown(f"⚠️ {h}")

        st.markdown("#### Recent headlines")
        for item in news.get("rows", [])[:6]:
            h = v49_text(item.get("headline"), "")
            url = v49_text(item.get("url"), "")
            src = v49_text(item.get("source"), "")
            if url:
                st.markdown(f"• [{h}]({url}) · _{src}_")
            else:
                st.markdown(f"• {h} · _{src}_")

        if not is_viewer():
            with st.expander("Admin news diagnostics", expanded=False):
                for x in news.get("diagnostics", [])[:80]:
                    st.caption(x)


def render_v49_final(row):
    r = v49_build_research_report(row)
    p = r["plan"]
    with st.container(border=True):
        st.markdown("### 🧠 Final Recommendation")
        st.markdown(f"**{r['ticker']} is rated: {r['verdict']}**")
        st.info(v49_verdict_explanation(r["verdict"]))
        st.markdown(
            f"**Action plan:** Ideal entry is below **{v49_money(p.get('ideal_entry'))}**. "
            f"Aggressive entry is **{v49_money(p.get('aggressive_low'))}–{v49_money(p.get('aggressive_high'))}**. "
            f"Use a trading stop near **{v49_money(p.get('stop'))}** and a base target around **{v49_money(p.get('base_target'))}**."
        )
        st.caption("Research guidance only. Not personalized financial advice.")


def render_v49_research_page(row):
    render_v49_research_summary(row)
    render_v49_trade_plan(row)
    render_v49_financials(row)
    render_v49_analysts(row)
    render_v49_news(row)
    render_v451_metric_interpreter(row)
    if "render_detail_chart_v4184" in globals():
        try:
            render_detail_chart_v4184(row)
        except Exception:
            pass
    render_v49_final(row)


def render_detail(row):
    render_v49_research_page(row)


def v49_table_rows(df, limit=60):
    out = []
    if df is None or df.empty:
        return out
    for _, row in df.head(limit).iterrows():
        try:
            r = v49_build_research_report(row)
            p = r["plan"]
            out.append({
                "Ticker": r["ticker"],
                "Company": r["company"],
                "Verdict": r["verdict"],
                "Opportunity Score": r["opportunity_score"],
                "Price": v49_money(p.get("price")),
                "Ideal Entry": f"Below {v49_money(p.get('ideal_entry'))}",
                "Stop": v49_money(p.get("stop")),
                "Base Target": v49_money(p.get("base_target")),
                "R/R": "N/A" if p.get("risk_reward") is None else f"{p.get('risk_reward'):.2f}:1",
                "Data": f"{r['financials'].get('coverage_label')} ({r['financials'].get('coverage_count')}/{r['financials'].get('coverage_total')})",
            })
        except Exception:
            continue
    return out


def render_v49_ready_section(df):
    rows = v49_table_rows(df, limit=50)
    ready = [x for x in rows if x["Verdict"] in ["BUY NOW", "BUY GRADUALLY"]]
    with st.container(border=True):
        st.markdown("### 🔥 Ready to Execute")
        st.caption("This separates stocks that are high quality from stocks that are actionable today.")
        if ready:
            st.dataframe(pd.DataFrame(ready).sort_values("Opportunity Score", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("No stock currently meets BUY NOW / BUY GRADUALLY thresholds. The scanner found research ideas, but not a clean execution setup yet.")


def render_table(df, title, key_prefix, min_score_default=35):
    st.subheader(title)
    if df is None or df.empty:
        st.info("No rows available yet.")
        return

    if key_prefix in ["top_table", "full_table"]:
        render_v49_ready_section(df)

    controls = st.columns([1, 1, 2])
    with controls[0]:
        min_score = st.slider("Minimum table score", 0, 100, min_score_default, key=f"{key_prefix}_score")
    with controls[1]:
        max_price = st.number_input("Max price", min_value=0.0, value=0.0, step=5.0, key=f"{key_prefix}_max_price")
    with controls[2]:
        search = st.text_input("Search ticker/company", key=f"{key_prefix}_search")

    filtered = df.copy()
    if "Final Conviction" in filtered.columns:
        filtered = filtered[filtered["Final Conviction"] >= min_score]
    if max_price > 0 and "Price" in filtered.columns:
        filtered = filtered[filtered["Price"].fillna(999999) <= max_price]
    if search:
        s = search.strip().lower()
        filtered = filtered[
            filtered["Ticker"].astype(str).str.lower().str.contains(s, na=False)
            | filtered["Company"].astype(str).str.lower().str.contains(s, na=False)
        ]

    if filtered.empty:
        st.warning("No rows match filters.")
        return

    st.markdown("### 🔎 Research Report")
    tickers = filtered["Ticker"].dropna().unique().tolist()
    selected = st.selectbox("Choose a ticker", tickers, key=f"{key_prefix}_select")
    if selected:
        row = filtered[filtered["Ticker"].eq(selected)].iloc[0]
        render_detail(row)

    st.markdown("### 📋 Ranked Ideas")
    rows = v49_table_rows(filtered, limit=60)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No display rows generated.")


def render_score_help():
    with st.expander("Quick guide: how to use the dashboard", expanded=True):
        st.markdown(
            """
            **Opportunity Score** is the only score to use. It combines fundamentals, technical setup, analyst upside, and news/risk.

            **Verdicts**
            - 🟢 **BUY NOW**: Entry, risk/reward, RSI, and analyst upside are aligned.
            - 🟡 **BUY GRADUALLY**: Attractive setup, but build in stages.
            - ⚪ **WATCH**: Good idea, but entry or risk/reward is not ready.
            - 🔴 **AVOID**: Risk/reward or data quality is not strong enough today.

            The dashboard separates **good companies** from **stocks that are actually ready to buy today**.
            """
        )


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Clean Trust Engine: one score, one verdict, one trade plan, and a clear BUY NOW checklist.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version", "")).startswith(("V45", "V46", "V47", "V48", "V49"))
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: admin diagnostics are hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")



# =========================
# V49.2 TRUST UX + ANALYST TARGETS
# =========================
# Fixes:
# - Final Recommendation markdown corruption by replacing long inline sentence with structured bullets
# - Improves Financial Health table interpretation
# - Adds Top Analyst / Price Target Detail section when available
# - Keeps V49 one-score / one-verdict / one-trade-plan model

def v491_metric_assessment(label, value, row=None):
    v = v49_num(value, positive=False)
    sector = ""
    industry = ""
    try:
        sector = v49_text(row.get("Sector") or row.get("sector"), "").lower() if row is not None else ""
        industry = v49_text(row.get("Industry") or row.get("industry"), "").lower() if row is not None else ""
    except Exception:
        pass
    peer = "software/technology" if ("software" in industry or "technology" in sector or "tech" in sector) else "peers"

    if v is None:
        return "Not scored", "This metric did not populate, so it is not counted in the client-facing score."

    label_l = label.lower()

    if "revenue growth" in label_l:
        if v >= 20:
            return "Excellent", f"{v:.1f}% revenue growth is strong and suggests the business is expanding faster than many {peer}."
        if v >= 10:
            return "Good", f"{v:.1f}% revenue growth is healthy and supports the growth thesis."
        if v >= 3:
            return "Moderate", f"{v:.1f}% revenue growth is positive but not especially strong."
        if v >= 0:
            return "Weak", f"{v:.1f}% revenue growth is slow; upside depends more on margins, valuation, or catalysts."
        return "Negative", f"{v:.1f}% revenue growth means sales are shrinking, which raises thesis risk."

    if "eps growth" in label_l:
        if v >= 20:
            return "Excellent", f"{v:.1f}% EPS growth shows earnings are scaling strongly."
        if v >= 8:
            return "Good", f"{v:.1f}% EPS growth shows profit is moving in the right direction."
        if v >= 0:
            return "Moderate", f"{v:.1f}% EPS growth is positive but not a major driver."
        return "Negative", f"{v:.1f}% EPS growth means earnings are declining."

    if "free cash flow" in label_l:
        if v > 1_000_000_000:
            return "Excellent", f"Positive free cash flow of {v49_money(v)} gives the company meaningful flexibility for reinvestment, debt reduction, or buybacks."
        if v > 0:
            return "Good", f"Positive free cash flow of {v49_money(v)} means the business is generating cash after reinvestment."
        return "Weak", f"Negative free cash flow of {v49_money(v)} means the company is consuming cash."

    if "operating cash flow" in label_l:
        if abs(v) < 1:
            return "Not useful", "Operating cash flow came through as $0.00, which is likely missing or stale source data rather than a useful business signal."
        if v > 0:
            return "Good", f"Positive operating cash flow of {v49_money(v)} supports core business quality."
        return "Weak", f"Negative operating cash flow of {v49_money(v)} means core operations are consuming cash."

    if label_l == "p/e":
        if v <= 0:
            return "Not useful", "A non-positive P/E usually means earnings are negative or the data is not meaningful."
        if v <= 20:
            return "Attractive", f"A P/E of {v:.1f} is reasonable if growth is stable."
        if v <= 45:
            return "Fair", f"A P/E of {v:.1f} can be acceptable for a growth company, but earnings must keep improving."
        return "Expensive", f"A P/E of {v:.1f} is elevated; the stock needs strong growth to justify the valuation."

    if "forward p/e" in label_l:
        if v <= 0:
            return "Not useful", "A non-positive forward P/E is not useful for valuation."
        if v <= 25:
            return "Attractive", f"A forward P/E of {v:.1f} looks reasonable for many growth companies."
        if v <= 45:
            return "Fair", f"A forward P/E of {v:.1f} is acceptable if growth and margins remain strong."
        return "Expensive", f"A forward P/E of {v:.1f} is high; execution risk is elevated."

    if "peg" in label_l:
        if v <= 0:
            return "Not useful", "PEG is not useful when earnings growth is negative or unavailable."
        if v <= 1:
            return "Excellent", f"A PEG of {v:.2f} suggests valuation is attractive relative to growth."
        if v <= 1.8:
            return "Good", f"A PEG of {v:.2f} is reasonable for a growth stock."
        if v <= 3:
            return "Fair", f"A PEG of {v:.2f} is acceptable but not cheap."
        return "Expensive", f"A PEG of {v:.2f} suggests the stock may be expensive relative to growth."

    if "gross margin" in label_l:
        if v >= 70:
            return "Excellent", f"{v:.1f}% gross margin is very strong and suggests high pricing power or a software-like business model."
        if v >= 45:
            return "Good", f"{v:.1f}% gross margin is healthy and supports quality."
        if v >= 25:
            return "Moderate", f"{v:.1f}% gross margin is acceptable but not elite."
        return "Weak", f"{v:.1f}% gross margin is low and may limit profitability."

    if "operating margin" in label_l:
        if v >= 25:
            return "Excellent", f"{v:.1f}% operating margin shows strong operating leverage."
        if v >= 10:
            return "Good", f"{v:.1f}% operating margin shows the business is profitable at the operating level."
        if v >= 0:
            return "Thin", f"{v:.1f}% operating margin is positive but thin."
        return "Negative", f"{v:.1f}% operating margin means the company is not profitable at the operating level."

    if "net margin" in label_l:
        if abs(v) < 0.1:
            return "Not useful", "Net margin came through as 0.0%, which may be missing/stale data or a break-even period."
        if v >= 20:
            return "Excellent", f"{v:.1f}% net margin shows strong bottom-line profitability."
        if v >= 8:
            return "Good", f"{v:.1f}% net margin means the company converts a healthy amount of revenue into profit."
        if v >= 0:
            return "Thin", f"{v:.1f}% net margin is positive but thin."
        return "Negative", f"{v:.1f}% net margin means the company is losing money on a bottom-line basis."

    if "cash" in label_l and "debt" not in label_l:
        return "Available", f"Cash of {v49_money(v)} supports liquidity and financial flexibility."

    if "total debt" in label_l:
        return "Context needed", f"Total debt is {v49_money(v)}. This should be compared with cash and cash flow before judging risk."

    if "net cash" in label_l or "net debt" in label_l:
        if v >= 0:
            return "Strong", f"Net cash of {v49_money(v)} means cash exceeds debt."
        return "Leveraged", f"Net debt of {v49_money(abs(v))} means debt exceeds cash."

    return "Available", "This metric is available and contributes context to the research view."


def v491_value_display(label, val, fmt):
    if val is None:
        return "Unavailable"
    if fmt == "money":
        if abs(v49_num(val) or 0) < 1:
            return "Unavailable"
        return v49_money(val)
    if fmt == "pct":
        return f"{val:.1f}%"
    return f"{val:.2f}"


def v491_top_analyst_rows(analyst, price=None):
    rows = []
    raw = analyst.get("firm_rows") or analyst.get("analyst_rows") or analyst.get("price_target_rows") or []
    if isinstance(raw, list):
        for item in raw[:12]:
            if not isinstance(item, dict):
                continue
            firm = (
                item.get("firm") or item.get("analystCompany") or item.get("analyst") or
                item.get("company") or item.get("source") or item.get("brokerage") or "Analyst/Firm"
            )
            rating = item.get("rating") or item.get("newGrade") or item.get("action") or item.get("recommendation") or ""
            target = (
                item.get("priceTarget") or item.get("targetPrice") or item.get("target") or
                item.get("newPriceTarget") or item.get("priceTargetNew")
            )
            date = item.get("date") or item.get("publishedDate") or item.get("updated") or ""
            target_v = v49_num(target, positive=True)
            if target_v:
                rows.append({
                    "Firm / Analyst": v49_text(firm, "Analyst/Firm"),
                    "Rating / Action": v49_text(rating, "N/A"),
                    "Target": v49_money(target_v),
                    "Upside": "N/A" if not price else v49_pct(((target_v - price) / price) * 100),
                    "Date": v49_text(date, ""),
                })
    # Fallback consensus range if no firm-level rows.
    if not rows:
        consensus = v49_num(analyst.get("consensus"), positive=True)
        high = v49_num(analyst.get("high"), positive=True)
        low = v49_num(analyst.get("low"), positive=True)
        count = analyst.get("count")
        if consensus:
            rows.append({
                "Firm / Analyst": "Wall Street Consensus",
                "Rating / Action": analyst.get("rating_trend") or "Consensus",
                "Target": v49_money(consensus),
                "Upside": "N/A" if not price else v49_pct(((consensus - price) / price) * 100),
                "Date": f"{count} analysts" if count else "",
            })
        if high:
            rows.append({
                "Firm / Analyst": "Highest target in range",
                "Rating / Action": "Bull case",
                "Target": v49_money(high),
                "Upside": "N/A" if not price else v49_pct(((high - price) / price) * 100),
                "Date": "",
            })
        if low:
            rows.append({
                "Firm / Analyst": "Lowest target in range",
                "Rating / Action": "Bear case",
                "Target": v49_money(low),
                "Upside": "N/A" if not price else v49_pct(((low - price) / price) * 100),
                "Date": "",
            })
    return rows[:5]


def render_v491_financials(row):
    r = v49_build_research_report(row)
    fin = r["financials"]
    rows = []
    metric_defs = [
        ("Revenue Growth", "revenue_growth", "pct"),
        ("EPS Growth", "eps_growth", "pct"),
        ("Free Cash Flow", "free_cash_flow", "money"),
        ("Operating Cash Flow", "operating_cash_flow", "money"),
        ("Forward P/E", "forward_pe", "num"),
        ("P/E", "pe", "num"),
        ("PEG", "peg", "num"),
        ("Gross Margin", "gross_margin", "pct"),
        ("Operating Margin", "operating_margin", "pct"),
        ("Net Margin", "net_margin", "pct"),
        ("Cash", "cash", "money"),
        ("Total Debt", "total_debt", "money"),
        ("Net Cash / Debt", "net_cash", "money"),
    ]
    for label, key, fmt in metric_defs:
        val = fin.get(key)
        # Hide unusable zero values for cash flow/margins rather than making the page look fake.
        if val is None:
            continue
        assessment, meaning = v491_metric_assessment(label, val, row)
        display = v491_value_display(label, val, fmt)
        if display == "Unavailable":
            continue
        rows.append({
            "Metric": label,
            "Value": display,
            "Assessment": assessment,
            "What it means for investors": meaning,
        })

    with st.container(border=True):
        st.markdown("### 🏢 Financial Health")
        st.metric("Data Coverage", f"{fin.get('coverage_label')} ({fin.get('coverage_count')}/{fin.get('coverage_total')})")
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Financial metrics did not populate enough for a useful client-facing table.")

        summary = []
        for m in rows:
            if m["Metric"] in ["Revenue Growth", "Gross Margin", "Free Cash Flow", "Forward P/E", "PEG", "Net Cash / Debt"]:
                summary.append(f"**{m['Metric']}**: {m['Assessment']} — {m['What it means for investors']}")
        if summary:
            st.markdown("#### Plain-English financial readout")
            for s in summary[:6]:
                st.markdown(f"• {s}")

        if not is_viewer():
            with st.expander("Admin financial diagnostics", expanded=False):
                if fin.get("completion_sources"):
                    st.dataframe(pd.DataFrame([{"Field": k, "Source": v} for k, v in fin["completion_sources"].items()]), use_container_width=True, hide_index=True)
                for x in fin.get("diagnostics", [])[:80]:
                    st.caption(x)


def render_v491_analysts(row):
    r = v49_build_research_report(row)
    a = r["analyst"]
    price = r.get("price")
    with st.container(border=True):
        st.markdown("### 🏦 Wall Street View")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Consensus Target", v49_money(a.get("consensus")))
        c2.metric("Upside", v49_pct(a.get("upside")))
        c3.metric("Coverage", str(a.get("count") or "N/A"))
        c4.metric("Sentiment", a.get("rating_trend") or "N/A")

        target_rows = v491_top_analyst_rows(a, price=price)
        if target_rows:
            st.markdown("#### Top Analyst / Price Target Detail")
            st.dataframe(pd.DataFrame(target_rows), use_container_width=True, hide_index=True)
            st.caption("If firm-level targets are not returned by the connected API tier, the dashboard shows the consensus/high/low range instead.")

        if a.get("consensus"):
            st.info(
                f"Analyst consensus supports a base target near {v49_money(a.get('consensus'))}. "
                "This helps validate upside, but the trade still needs a clean entry and risk/reward setup."
            )

        if not is_viewer():
            with st.expander("Admin analyst diagnostics", expanded=False):
                for x in a.get("diagnostics", [])[:80]:
                    st.caption(x)


def render_v491_final(row):
    r = v49_build_research_report(row)
    p = r["plan"]

    with st.container(border=True):
        st.markdown("### 🧠 Final Recommendation")
        st.markdown(f"**Verdict:** {r['verdict']}")
        st.info(v49_verdict_explanation(r["verdict"]))

        st.markdown("#### Action Plan")
        st.markdown(f"• **Ideal Entry:** Below {v49_money(p.get('ideal_entry'))}")
        st.markdown(f"• **Aggressive Entry:** {v49_money(p.get('aggressive_low'))} – {v49_money(p.get('aggressive_high'))}")
        st.markdown(f"• **Trading Stop:** {v49_money(p.get('stop'))}")
        st.markdown(f"• **Base Target:** {v49_money(p.get('base_target'))}")
        st.markdown(f"• **Bull Target:** {v49_money(p.get('bull_target'))}")
        st.markdown("#### Bottom Line")
        if r["verdict"] == "BUY NOW":
            st.success("This setup is actionable today if the investor accepts the trading stop and position sizing discipline.")
        elif r["verdict"] == "BUY GRADUALLY":
            st.info("This setup is attractive, but the better approach is to build the position in stages instead of buying all at once.")
        elif r["verdict"] == "WATCH":
            st.warning("This is worth monitoring, but the entry or risk/reward setup is not strong enough yet.")
        else:
            st.error("This does not currently meet the dashboard's standards for a new position.")
        st.caption("Research guidance only. Not personalized financial advice.")


def render_v491_research_page(row):
    render_v49_research_summary(row)
    render_v49_trade_plan(row)
    render_v491_financials(row)
    render_v491_analysts(row)
    render_v49_news(row)
    render_v451_metric_interpreter(row)
    if "render_detail_chart_v4184" in globals():
        try:
            render_detail_chart_v4184(row)
        except Exception:
            pass
    render_v491_final(row)


def render_detail(row):
    render_v491_research_page(row)


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Scanner State Sync Fix: ensures the app and overnight scanner state report the same active version.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version", "")).startswith(("V45", "V46", "V47", "V48", "V49"))
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: admin diagnostics are hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")



# =========================
# V49.3 PERFORMANCE STABILITY FIX
# =========================
# Fixes:
# - No live API calls while rendering tables
# - Live research is reserved for selected ticker detail page
# - Faster Ready to Execute section based on persisted scan fields
# - Stronger percent normalization for high-growth metrics
# - Keeps V49 one-score / one-verdict visible report model

def v493_percent(x):
    v = v49_num(x, positive=False) if "v49_num" in globals() else None
    if v is None:
        return None
    # Most API ratios/growth values between -2 and 2 are decimal form.
    # Values outside this range are usually already percentage points.
    if -2 < v < 2:
        v *= 100
    if abs(v) > 500:
        return None
    return v


def v49_percent(x):
    return v493_percent(x)


def v493_fast_money(x):
    try:
        return v49_money(x)
    except Exception:
        try:
            return fmt_money(x)
        except Exception:
            return "N/A"


def v493_fast_pct(x):
    try:
        v = safe_number(x, None)
        if v is None:
            return "N/A"
        return f"{v:.1f}%"
    except Exception:
        return "N/A"


def v493_fast_rr(row):
    rr = safe_number(row.get("Risk/Reward"), 0)
    if rr and rr > 0:
        return f"{rr:.2f}:1"
    price = safe_number(row.get("Price"), 0)
    target = safe_number(row.get("AI Fair Value") or row.get("Analyst Target"), 0)
    stop = safe_number(row.get("Stop Loss"), 0)
    if price and target and stop and price > stop:
        calc = (target - price) / (price - stop)
        if calc > 0:
            return f"{calc:.2f}:1"
    return "N/A"


def v493_fast_verdict(row):
    """
    Fast verdict based only on persisted scan fields.
    This is intentionally not as deep as v49_build_research_report().
    It prevents table rendering from causing hundreds of live API calls.
    """
    score = safe_number(row.get("Final Conviction"), 0)
    price = safe_number(row.get("Price"), 0)
    upside = safe_number(row.get("Target Upside %"), 0)
    rsi = safe_number(row.get("RSI"), 50)
    rr = safe_number(row.get("Risk/Reward"), 0)
    analyst_count = safe_number(row.get("Analyst Count"), 0)
    analyst_target = safe_number(row.get("Analyst Target"), 0)

    analyst_upside = 0
    if price and analyst_target:
        analyst_upside = ((analyst_target - price) / price) * 100

    rr_ok = rr >= 1.5 if rr else upside >= 15
    analyst_ok = analyst_upside >= 10 or analyst_count >= 5
    rsi_ok = rsi < 72 if rsi else True

    if score >= 85 and upside >= 15 and rr_ok and analyst_ok and rsi_ok:
        return "BUY NOW"
    if score >= 78 and upside >= 10 and rsi_ok:
        return "BUY GRADUALLY"
    if score >= 60:
        return "WATCH"
    return "AVOID"


def v493_table_rows_fast(df, limit=60):
    rows = []
    if df is None or df.empty:
        return rows

    for _, row in df.head(limit).iterrows():
        price = safe_number(row.get("Price"), 0)
        target = safe_number(row.get("AI Fair Value") or row.get("Analyst Target"), 0)
        upside = safe_number(row.get("Target Upside %"), 0)
        stop = safe_number(row.get("Stop Loss"), 0)
        verdict = v493_fast_verdict(row)

        rows.append({
            "Ticker": safe_text(row.get("Ticker"), ""),
            "Company": safe_text(row.get("Company"), ""),
            "Verdict": verdict,
            "Score": int(safe_number(row.get("Final Conviction"), 0)),
            "Price": v493_fast_money(price),
            "AI / Analyst Target": v493_fast_money(target),
            "Upside": v493_fast_pct(upside),
            "Entry": safe_text(row.get("Entry Range"), "N/A"),
            "Stop": v493_fast_money(stop) if stop else "N/A",
            "R/R": v493_fast_rr(row),
            "Analyst Support": safe_text(row.get("Analyst Support"), "N/A"),
            "News": safe_text(row.get("News Sentiment"), "N/A"),
        })
    return rows


def v49_table_rows(df, limit=60):
    """
    V49.3 override:
    table rows must be scan-data only.
    Do NOT call v49_build_research_report() here.
    """
    return v493_table_rows_fast(df, limit=limit)


def render_v49_ready_section(df):
    """
    V49.3 override:
    Ready to Execute is fast and based on persisted scan fields only.
    The detailed live research still happens after user selects one ticker.
    """
    rows = v493_table_rows_fast(df, limit=80)
    ready = [x for x in rows if x["Verdict"] in ["BUY NOW", "BUY GRADUALLY"]]

    with st.container(border=True):
        st.markdown("### 🔥 Ready to Execute")
        st.caption("Fast scan-only view. Detailed live API research loads only after selecting one ticker.")
        if ready:
            st.dataframe(pd.DataFrame(ready).sort_values("Score", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("No stock currently meets BUY NOW / BUY GRADUALLY thresholds from the persisted scan data.")


def render_table(df, title, key_prefix, min_score_default=35):
    """
    V49.3 override:
    Fast table render. Only selected ticker opens live V49 research report.
    """
    st.subheader(title)
    if df is None or df.empty:
        st.info("No rows available yet.")
        return

    if key_prefix in ["top_table", "full_table"]:
        render_v49_ready_section(df)

    controls = st.columns([1, 1, 2])
    with controls[0]:
        min_score = st.slider("Minimum table score", 0, 100, min_score_default, key=f"{key_prefix}_score")
    with controls[1]:
        max_price = st.number_input("Max price", min_value=0.0, value=0.0, step=5.0, key=f"{key_prefix}_max_price")
    with controls[2]:
        search = st.text_input("Search ticker/company", key=f"{key_prefix}_search")

    filtered = df.copy()
    if "Final Conviction" in filtered.columns:
        filtered = filtered[filtered["Final Conviction"] >= min_score]
    if max_price > 0 and "Price" in filtered.columns:
        filtered = filtered[filtered["Price"].fillna(999999) <= max_price]
    if search:
        s = search.strip().lower()
        filtered = filtered[
            filtered["Ticker"].astype(str).str.lower().str.contains(s, na=False)
            | filtered["Company"].astype(str).str.lower().str.contains(s, na=False)
        ]

    if filtered.empty:
        st.warning("No rows match filters.")
        return

    st.markdown("### 🔎 Research Report")
    tickers = filtered["Ticker"].dropna().unique().tolist()
    selected = st.selectbox("Choose a ticker", tickers, key=f"{key_prefix}_select")
    if selected:
        row = filtered[filtered["Ticker"].eq(selected)].iloc[0]
        render_detail(row)

    st.markdown("### 📋 Ranked Ideas")
    rows = v493_table_rows_fast(filtered, limit=80)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No display rows generated.")


def render_status_banner():
    state = read_state()
    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Performance Stability Fix: tables use persisted scan data only; live APIs load only for selected ticker research.")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Status", state.get("status", "unknown"))
    c2.metric("Scanner Version", state.get("version", "N/A"))
    c3.metric("Full Scan", state.get("full_scan_count", "N/A"))
    c4.metric("Prescreen", state.get("prescreen_count", "N/A"))
    persisted = bool(state.get("github_persisted")) or v45_text(state.get("version", "")).startswith(("V45", "V46", "V47", "V48", "V49"))
    c5.metric("GitHub Persisted", "✅" if persisted else "❌")
    if is_viewer():
        st.info("Viewer mode: admin diagnostics are hidden.")
    if state:
        st.caption(f"Last scan: {state.get('generated_at', 'N/A')} | Duration: {state.get('duration_seconds', 'N/A')}s | DATA_DIR={state.get('data_dir', '.')}")


def main():
    if not dashboard_login_gate():
        return
    render_v424_market_command_center()
    render_v4261_cron_performance_note()
    render_v4251_scanner_version_notice()

    render_status_banner()
    render_score_help()

    full_df = load_full_scan()
    top_df = latest_top_ideas()
    recovery_df = latest_recovery()
    watch_df = latest_watchlist_scan()
    prescreen_df = load_file(PRESCREEN_FILE)
    etf_df = load_file(ETF_SCAN_FILE)

    tabs = st.tabs(
        [
            "Top AI Ideas",
            "Full Ranked Scan",
            "Recovery",
            "ETFs",
            "Watchlist",
            "Prescreen",
            "Summary",
            "Research Any Ticker",
            "Ask AI",
        ]
    )

    with tabs[0]:
        render_table(
            top_df if not top_df.empty else full_df.head(25),
            "Top AI Ideas",
            "top_table",
            min_score_default=45,
        )

    with tabs[1]:
        render_table(full_df, "Full Ranked AI Scan", "full_table", min_score_default=35)

    with tabs[2]:
        render_table(recovery_df, "Recovery Intelligence: Dropped Stocks With Forward Upside", "recovery_table", min_score_default=35)

    with tabs[3]:
        render_table(etf_df, "ETF Intelligence: Non-Financial / Non-Israel Screen", "etf_table", min_score_default=35)

    with tabs[4]:
        render_table(watch_df, "Watchlist Scan", "watch_table", min_score_default=0)

    with tabs[5]:
        render_table(prescreen_df, "Prescreen Candidates", "prescreen_table", min_score_default=35)

    with tabs[6]:
        render_market_summary(full_df)

    with tabs[7]:
        render_research_any_ticker(full_df, recovery_df, watch_df, prescreen_df, etf_df)

    with tabs[8]:
        render_chat_helper(full_df)


if __name__ == "__main__":
    main()
