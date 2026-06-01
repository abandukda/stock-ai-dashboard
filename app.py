import os
import json
from pathlib import Path

import pandas as pd
import streamlit as st


APP_VERSION = "V41.4 Explainable AI Agents Dashboard"

st.set_page_config(
    page_title="AI Trading Dashboard",
    page_icon="📈",
    layout="wide",
)

DATA_DIR = Path(os.getenv("DATA_DIR", "."))

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

VIEWER_PASSWORD = os.getenv("VIEWER_PASSWORD", "").strip()
ADMIN_PASSWORD = os.getenv("APP_PASSWORD", os.getenv("ADMIN_PASSWORD", "")).strip()


def get_user_role():
    if "user_role" not in st.session_state:
        st.session_state["user_role"] = "admin" if not VIEWER_PASSWORD and not ADMIN_PASSWORD else None
    return st.session_state.get("user_role")


def require_login():
    if not VIEWER_PASSWORD and not ADMIN_PASSWORD:
        st.session_state["user_role"] = "admin"
        return True

    role = get_user_role()
    if role in {"admin", "viewer"}:
        with st.sidebar:
            st.caption(f"Logged in as: {role}")
            if st.button("Log out"):
                st.session_state.pop("user_role", None)
                st.rerun()
        return True

    st.title("📈 AI Trading Dashboard")
    st.info("Enter your access password.")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
            st.session_state["user_role"] = "admin"
            st.rerun()
        elif VIEWER_PASSWORD and password == VIEWER_PASSWORD:
            st.session_state["user_role"] = "viewer"
            st.rerun()
        else:
            st.error("Invalid password.")
    return False


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
        return "N/A"
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
        "Analyst Support": analyst_support_label(pick(raw, "analyst_support_score", "Analyst Support", default=None)),
        "News Sentiment": sentiment_badge(pick(raw, "news_sentiment_label", "News Sentiment", default="N/A")),
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
        "Target Source": safe_text(pick(raw, "Target Source", "target_source", default="N/A"), "N/A"),
        "Target Confidence Note": safe_text(pick(raw, "Target Confidence Note", "target_confidence_note", default=""), ""),
        "ETF Screen": safe_text(pick(raw, "etf_preference_screen", "ETF Screen", default=""), ""),
        "Source FMP": bool(pick(raw, "source_fmp_profile", "Source FMP", default=False)),
        "Website": safe_text(pick(raw, "website", "Website", default=""), ""),
        "AI Committee": pick(raw, "ai_committee", default=[]),
        "Thesis Strength": safe_text(pick(raw, "thesis_strength", default=""), ""),
        "Evidence Confidence": safe_text(pick(raw, "evidence_confidence", default=""), ""),
        "Committee Conclusion": safe_text(pick(raw, "committee_conclusion", default=""), ""),
        "Valuation Reconciliation": safe_text(pick(raw, "valuation_reconciliation", default=""), ""),
        "Insider Score": safe_number(pick(raw, "insider_score", default=0), 0),
        "Insider Activity": safe_text(pick(raw, "insider_activity_label", default="N/A"), "N/A"),
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


# =========================
# UI
# =========================

def render_status_banner():
    state = read_state()

    st.title("📈 AI Trading Dashboard")
    st.caption(APP_VERSION)
    st.caption("Includes plain-English metric definitions, good/bad ranges, and AI interpretations inside each research card.")

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

    for col in ["Price", "AI Fair Value", "AI Bull Case", "AI Bear Case", "Analyst Target", "Stop Loss"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: f"${safe_number(x, 0):,.2f}" if safe_number(x, 0) else "N/A"
            )

    if "Target Upside %" in display_df.columns:
        display_df["Target Upside %"] = display_df["Target Upside %"].apply(fmt_pct)

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

    st.info(educational_bottom_line(row))

    with st.expander("📚 Explain these metrics: meanings, good ranges, bad ranges", expanded=False):
        render_metric_education(row)

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
            st.markdown(f"**News Sentiment:** {news_sentiment}")
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


def render_research_any_ticker(full_df, recovery_df, watch_df, prescreen_df, etf_df=None):
    st.subheader("🔍 Research Any Ticker")
    st.caption(
        "Search tickers already in the latest scan. If a ticker is not found, add it to the watchlist so the next scan includes it."
    )

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        ticker = st.text_input("Enter ticker", placeholder="NVDA, MSFT, PLTR, ZS", key="research_any_ticker").upper().strip()
    with c2:
        st.write("")
        st.write("")
        open_card = st.button("Open Research Card", key="research_any_ticker_btn")
    with c3:
        st.write("")
        st.write("")
        add_watch = st.button("➕ Add to Watchlist", key="add_any_ticker_watchlist_btn")

    if ticker:
        current_watchlist = read_watchlist_symbols()
        if ticker in current_watchlist:
            st.success(f"{ticker} is already in your watchlist.")

        if add_watch:
            if add_symbol_to_watchlist(ticker):
                st.success(
                    f"{ticker} added to watchlist. It will receive a full AI Committee card after the next scanner run."
                )

    if ticker and (open_card or ticker):
        row = find_ticker_row(ticker, full_df, recovery_df, watch_df, prescreen_df, etf_df)
        if row is not None:
            render_detail(row)
        else:
            st.warning(
                f"{ticker} was not found in the latest scan files. "
                "Click ➕ Add to Watchlist, then run the next scan so the AI agents can evaluate it."
            )

            st.info(
                "Why this happens: Research Any Ticker uses the latest generated scan files. "
                "Adding a ticker to the watchlist tells the next scanner run to include it in the universe."
            )


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

def main():
    if not require_login():
        return

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
