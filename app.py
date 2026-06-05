import os
import math
import datetime as dt
import json
import csv
from pathlib import Path
from io import StringIO

import pandas as pd
import streamlit as st
import requests
import yfinance as yf
import plotly.graph_objects as go


APP_VERSION = "V43 Professional Intelligence Platform"

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
