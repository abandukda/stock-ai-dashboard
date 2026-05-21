import os
from pathlib import Path
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False

# ============================================================
# AI TRADING DASHBOARD  V36.0 MARKET INTELLIGENCE
# Merged: Fundamental Research Engine + Adaptive Intelligence
# 9-Agent scoring · MACD timing · Adaptive threshold
# Morning briefing · Trade checklist · Volatility sizing
# Valuation · Cash flow · Earnings context · Sector rotation
# ============================================================

st.set_page_config(
    page_title="AI Trading Dashboard V36.0",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { --bg-main:#f3f6fb; --bg-card:#ffffff; --text-main:#111827; --text-muted:#475569; --border-soft:#d8e0ec; --blue-main:#2563eb; }
.stApp { background:#f3f6fb !important; color:#111827 !important; }
html,body,p,div,span,label { color:#111827; }
.block-container { padding-top:1.5rem; padding-bottom:2rem; max-width:1500px; }
section[data-testid="stSidebar"] { background:#0f172a !important; border-right:1px solid rgba(255,255,255,0.08); }
section[data-testid="stSidebar"] h1,section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div { color:#f8fafc !important; }
section[data-testid="stSidebar"] input { color:#111827 !important; background:#ffffff !important; }
section[data-testid="stSidebar"] .stButton button { background:#1e293b !important; border:1px solid #334155 !important; color:#ffffff !important; border-radius:12px !important; }
h1,h2,h3 { color:#111827 !important; letter-spacing:-0.03em; }
h1 { font-size:2.25rem !important; font-weight:850 !important; }
h2 { font-size:1.55rem !important; font-weight:800 !important; }
.modern-hero { padding:26px; border-radius:24px; background:linear-gradient(135deg,#0f172a 0%,#1e40af 58%,#0f766e 100%); color:#ffffff !important; box-shadow:0 18px 42px rgba(15,23,42,0.22); margin-bottom:20px; border:1px solid rgba(255,255,255,0.12); }
.modern-hero h1,.modern-hero p,.modern-hero span,.modern-hero div { color:#ffffff !important; }
.modern-hero p { color:#e0f2fe !important; font-size:1.03rem; margin-bottom:0; }
.modern-section-title { padding:14px 0 8px 0; font-size:1.25rem; font-weight:850; color:#111827 !important; }
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p { color:#475569 !important; }
[data-testid="stMetric"] { background:#ffffff !important; border:1px solid #d8e0ec; border-radius:18px; padding:15px 16px; box-shadow:0 8px 20px rgba(15,23,42,0.07); }
[data-testid="stMetric"] * { color:#111827 !important; }
[data-testid="stMetricLabel"] { color:#475569 !important; }
[data-testid="stMetricValue"] { color:#111827 !important; font-weight:850 !important; }
.stButton button,.stDownloadButton button,.stLinkButton a { border-radius:13px !important; border:1px solid #bfdbfe !important; background:#ffffff !important; color:#1d4ed8 !important; box-shadow:0 5px 14px rgba(15,23,42,0.08); font-weight:750 !important; }
.stButton button:hover,.stDownloadButton button:hover,.stLinkButton a:hover { background:#eff6ff !important; color:#1e40af !important; border-color:#93c5fd !important; }
.stTextInput input,.stNumberInput input,textarea { border-radius:12px !important; background:#ffffff !important; color:#111827 !important; border:1px solid #cbd5e1 !important; }
.stAlert { border-radius:16px !important; color:#111827 !important; }
.stAlert * { color:#111827 !important; }
.streamlit-expanderHeader { border-radius:14px !important; font-weight:750 !important; color:#111827 !important; background:#ffffff !important; }
[data-testid="stDataFrame"],[data-testid="stDataEditor"] { border-radius:18px; overflow:hidden; box-shadow:0 10px 24px rgba(15,23,42,0.08); border:1px solid #d8e0ec; background:#ffffff !important; }
[data-testid="stDataFrame"] div,[data-testid="stDataEditor"] div,[data-testid="stDataFrame"] span,[data-testid="stDataEditor"] span,[data-testid="stDataFrame"] p,[data-testid="stDataEditor"] p { color:#111827 !important; }
[data-testid="stDataEditor"] [role="columnheader"],[data-testid="stDataFrame"] [role="columnheader"] { background:#e8eef8 !important; color:#111827 !important; font-weight:800 !important; }
a { color:#1d4ed8 !important; font-weight:650; }
@media (max-width:768px) { .block-container{padding-left:0.8rem;padding-right:0.8rem;} .modern-hero{padding:18px;border-radius:18px;} h1{font-size:1.75rem !important;} h2{font-size:1.25rem !important;} [data-testid="stMetric"]{padding:12px;} }
</style>
""", unsafe_allow_html=True)


def modern_hero(title, subtitle):
    st.markdown(f'<div class="modern-hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)

def modern_section(title, subtitle=None):
    st.markdown(f'<div class="modern-section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)



def get_query_param_value(name, default=None):
    try:
        val = st.query_params.get(name, default)
        if isinstance(val, list):
            return val[0] if val else default
        return val
    except Exception:
        try:
            params = st.experimental_get_query_params()
            vals = params.get(name, [])
            return vals[0] if vals else default
        except Exception:
            return default

# ── Formatting helpers ──────────────────────────────────────

def fmt_pct(value):
    try:
        if value is None or pd.isna(value): return "N/A"
        return f"{float(value)*100:.1f}%"
    except Exception: return "N/A"

def fmt_money(value):
    try:
        if value is None or pd.isna(value): return "N/A"
        v = float(value); a = abs(v)
        if a >= 1e12: return f"${v/1e12:.2f}T"
        if a >= 1e9:  return f"${v/1e9:.2f}B"
        if a >= 1e6:  return f"${v/1e6:.2f}M"
        return f"${v:,.0f}"
    except Exception: return "N/A"

def fmt_num(value, digits=2):
    try:
        if value is None or pd.isna(value): return "N/A"
        return f"{float(value):.{digits}f}"
    except Exception: return "N/A"

def conviction_bar_html(score):
    try: score = float(score or 0)
    except Exception: score = 0
    pct = max(0, min(100, int(score)))
    color = "#16a34a" if pct >= 75 else "#f59e0b" if pct >= 60 else "#ef4444"
    return f"""
    <div style="background:#e5e7eb;border-radius:999px;height:9px;width:100%;overflow:hidden;">
        <div style="background:{color};width:{pct}%;height:9px;border-radius:999px;"></div>
    </div>
    <div style="font-size:0.78rem;color:#475569;margin-top:3px;">{pct}/100 conviction</div>
    """


# ── Signal Cards ────────────────────────────────────────────


def add_ticker_to_watchlist(ticker):
    ticker = normalize_ticker(str(ticker))
    if not ticker:
        return False, "Invalid ticker."
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = load_watchlist()
    if ticker in st.session_state.watchlist:
        return False, f"{ticker} is already in your watchlist."
    st.session_state.watchlist.append(ticker)
    st.session_state.watchlist = sorted(set(st.session_state.watchlist))
    save_watchlist()
    return True, f"{ticker} added to watchlist."

def render_signal_card(row, show_checklist=False):
    ticker    = row.get("Ticker","N/A")
    company_name = row.get("Company Name", ticker)
    price     = row.get("Price","N/A")
    verdict   = row.get("Agent Verdict", row.get("Signal",""))
    signal    = row.get("Signal","")
    conviction= row.get("Final Conviction", row.get("AI Score",0))
    entry     = row.get("Entry Range","N/A")
    stop      = row.get("Stop Loss","N/A")
    target    = row.get("Target / Sell Zone","N/A")
    rr        = row.get("Risk / Reward","N/A")
    rs        = row.get("Relative Strength vs SPY %","N/A")
    earnings  = row.get("Earnings","")
    macd_note = row.get("MACD Note","")
    confidence= row.get("Signal Confidence","")
    style     = row.get("Investment Style","")
    financial_safety = row.get("Financial Safety", "⚪ Not scored")
    agent_greenlight = row.get("Agent Greenlight", "⚪ Not scored")
    execution_quality = row.get("Execution Quality", "⚪ Research Only")
    plan      = str(row.get("AI Trade Plan",""))
    research  = str(row.get("Research Summary",""))
    valuation = str(row.get("Valuation Detail",""))
    financial = str(row.get("Financial Strength Detail",""))

    plan_short      = plan[:180]     + ("..." if len(plan)>180     else "")
    research_short  = research[:280] + ("..." if len(research)>280 else "")
    valuation_short = valuation[:200]+ ("..." if len(valuation)>200 else "")
    financial_short = financial[:200]+ ("..." if len(financial)>200 else "")

    if "High" in str(verdict) or "BUY" in str(signal):
        bc,pb,pc = "#16a34a","#dcfce7","#166534"
    elif "Watch" in str(verdict) or "Watch" in str(signal):
        bc,pb,pc = "#f59e0b","#fef3c7","#92400e"
    else:
        bc,pb,pc = "#64748b","#f1f5f9","#334155"
    # V36.0 defensive financial card defaults
    financial_safety = row.get("Financial Safety", locals().get("financial_safety", "⚪ Not scored"))
    agent_greenlight = row.get("Agent Greenlight", locals().get("agent_greenlight", "⚪ Not scored"))
    execution_quality = row.get("Execution Quality", locals().get("execution_quality", "⚪ Research Only"))


    st.markdown(f"""
    <div style="background:#ffffff;border:1px solid #d8e0ec;border-left:6px solid {bc};border-radius:18px;padding:18px;margin-bottom:14px;box-shadow:0 8px 22px rgba(15,23,42,0.08);">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
            <div>
                <div style="font-size:1.35rem;font-weight:850;color:#111827;">{ticker}
                    <span style="font-size:1rem;color:#475569;margin-left:8px;">${price}</span>
                </div>
                <div style="margin-top:2px;color:#334155;font-size:0.95rem;font-weight:700;">{company_name}</div>
                <div style="margin-top:4px;color:#64748b;font-size:0.88rem;">{signal} &nbsp;·&nbsp; {style}</div>
            </div>
            <div style="background:{pb};color:{pc};padding:6px 12px;border-radius:999px;font-weight:800;font-size:0.85rem;white-space:nowrap;">{verdict}</div>
        </div>
        <div style="margin-top:10px;">{conviction_bar_html(conviction)}</div>
        <div style="margin-top:6px;color:#475569;font-size:0.82rem;font-style:italic;">{confidence}</div>
        <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:12px;">
            <div><div style="font-size:0.75rem;color:#64748b;">Entry</div><div style="font-weight:800;color:#111827;">{entry}</div></div>
            <div><div style="font-size:0.75rem;color:#64748b;">Stop</div><div style="font-weight:800;color:#111827;">${stop}</div></div>
            <div><div style="font-size:0.75rem;color:#64748b;">Target</div><div style="font-weight:800;color:#111827;">{target}</div></div>
            <div><div style="font-size:0.75rem;color:#64748b;">R/R</div><div style="font-weight:800;color:#111827;">{rr}</div></div>
        </div>
        <div style="margin-top:10px;color:#475569;font-size:0.88rem;"><b>RS vs SPY:</b> {rs}% &nbsp;|&nbsp; <b>Earnings:</b> {earnings}</div>\n        <div style="margin-top:6px;color:#334155;font-size:0.86rem;"><b>Financial Safety:</b> {financial_safety} &nbsp;|&nbsp; <b>Agents:</b> {agent_greenlight}</div>\n        <div style="margin-top:6px;color:#334155;font-size:0.86rem;"><b>Execution Quality:</b> {execution_quality}</div>\n        <div style="margin-top:8px;color:#0f172a;font-size:0.87rem;line-height:1.45;"><b>Why It Ranked Highly:</b> {row.get("Why Ranked Highly", "")}</div>
        <div style="margin-top:6px;color:#475569;font-size:0.85rem;">{macd_note}</div>
        <div style="margin-top:10px;color:#334155;font-size:0.9rem;line-height:1.45;"><b>Why consider it:</b> {research_short}</div>
        <div style="margin-top:8px;color:#334155;font-size:0.88rem;line-height:1.45;"><b>Valuation:</b> {valuation_short}</div>
        <div style="margin-top:8px;color:#334155;font-size:0.88rem;line-height:1.45;"><b>Financial strength:</b> {financial_short}</div>
        <div style="margin-top:8px;color:#64748b;font-size:0.85rem;line-height:1.4;"><b>Technical timing:</b> {plan_short}</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([1,1,1,3])
    with c1:
        st.link_button("Open chart", f"https://finance.yahoo.com/quote/{ticker}", use_container_width=True)
    with c2:
        if st.button("View Details", key=f"details_{ticker}_{abs(hash(str(ticker))) % 100000}", use_container_width=True):
            st.session_state.nav_override = "Detail View"
            st.session_state.selected_detail_ticker = ticker
            st.rerun()
    with c3:
        already_saved = ticker in st.session_state.get("watchlist", [])
        add_label = "Saved" if already_saved else "Add Watch"
        if st.button(add_label, key=f"add_watch_{ticker}_{abs(hash('watch_'+str(ticker))) % 100000}", use_container_width=True, disabled=already_saved):
            ok, msg = add_ticker_to_watchlist(ticker)
            if ok:
                st.success(msg)
            else:
                st.info(msg)
            st.rerun()
    with c4:
        if show_checklist:
            with st.expander(f"✅ Trade Checklist — {ticker}"):
                render_trade_checklist(row)
        else:
            st.caption("Use Detail View for full chart, agents, fundamental deep-dive, and position sizing.")


def render_signal_cards(df, limit=50, show_checklist=False):
    if df is None or df.empty:
        st.info("No signals to show.")
        return
    for i, (_, row) in enumerate(df.head(limit).iterrows()):
        render_signal_card(row, show_checklist=show_checklist)


def render_mobile_signal_summary(df):
    if df is None or df.empty:
        st.info("No mobile summary available.")
        return
    cols = ["Ticker","Company Name","Price","Signal Confidence","Financial Safety","Execution Quality","Entry Range","Stop Loss","Target / Sell Zone","Risk / Reward"]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(df[cols].head(75), use_container_width=True, hide_index=True)


def render_trade_checklist(row):
    checks = []; all_green = True
    conviction = float(row.get("Final Conviction") or 0)
    threshold  = st.session_state.get("adaptive_threshold", 68)
    if conviction >= threshold:
        checks.append(f"✅ Conviction {conviction:.0f} meets threshold ({threshold})")
    else:
        checks.append(f"❌ Conviction {conviction:.0f} below threshold ({threshold})"); all_green = False

    regime = str(row.get("Market Regime",""))
    if "Bear" in regime:
        checks.append("⚠️ Bear market — reduce size, require stronger setup"); all_green = False
    else:
        checks.append(f"✅ Market regime: {regime}")

    if row.get("MACD Bullish", False):
        checks.append("✅ MACD bullish crossover — entry timing confirmed")
    else:
        checks.append("⚠️ No MACD crossover — consider waiting for entry timing")

    rsi = float(row.get("RSI") or 50)
    if rsi > 72:
        checks.append(f"❌ RSI {rsi:.1f} — overbought, avoid chasing"); all_green = False
    elif rsi < 30:
        checks.append(f"⚠️ RSI {rsi:.1f} — oversold, use staged entries")
    else:
        checks.append(f"✅ RSI {rsi:.1f} — healthy zone")

    earnings = str(row.get("Earnings",""))
    if "🔴" in earnings:
        checks.append(f"❌ {earnings} — binary risk, avoid or very small size"); all_green = False
    else:
        checks.append(f"✅ Earnings: {earnings}")

    vol = float(row.get("Volume Ratio") or 1)
    if vol >= 1.2:    checks.append(f"✅ Volume {vol:.1f}x — confirms interest")
    elif vol < 0.8:   checks.append(f"⚠️ Volume {vol:.1f}x — weak confirmation")
    else:             checks.append(f"✅ Volume {vol:.1f}x — normal")

    rs = row.get("Relative Strength vs SPY %")
    if rs is not None:
        try:
            rs = float(rs)
            if rs > 5:    checks.append(f"✅ Outperforming SPY by +{rs:.1f}%")
            elif rs < -10: checks.append(f"⚠️ Lagging SPY by {rs:.1f}%")
            else:          checks.append(f"✅ RS vs SPY: {rs:.1f}%")
        except Exception: pass

    fcf = str(row.get("Free Cash Flow",""))
    if fcf and fcf not in ["N/A",""] and "-" not in fcf:
        checks.append(f"✅ Free cash flow: {fcf} — positive cash generation")
    elif fcf and "-" in fcf:
        checks.append(f"⚠️ Free cash flow: {fcf} — negative, monitor closely")

    for check in checks: st.markdown(check)
    st.markdown("---")
    if all_green:
        st.success("🟢 All checks passed — high-quality setup. Use position calculator and respect your size rules.")
    else:
        st.warning("🟡 Some checks flagged — smaller size or wait for improvement.")


# ============================================================
# CONSTANTS
# ============================================================

EASTERN = ZoneInfo("America/New_York")
DATA_DIR = Path(os.getenv("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

WATCHLIST_FILE     = DATA_DIR / "watchlist.json"
PAPER_TRADES_FILE  = DATA_DIR / "paper_trades.json"
ALERT_HISTORY_FILE = DATA_DIR / "alert_history.json"
SIGNAL_LOG_FILE    = DATA_DIR / "signal_log.json"

DEFAULT_WATCHLIST = ["AAPL","MSFT","NVDA","AMD","TSLA","AMZN","GOOGL","META","SNOW","ELF","PLTR","SHOP"]

CORE_SCAN_TICKERS = [
    "AAPL","MSFT","NVDA","AMD","TSLA","AMZN","GOOGL","META","AVGO","COST","LLY","UNH","CRM","ADBE","NOW","PANW","CRWD",
    "SHOP","SNOW","NET","DDOG","TEAM","MDB","ZS","CELH","DECK","NKE","SBUX","TGT","UBER","ABNB","TTD",
    "PYPL","SQ","PLTR","HIMS","ONON","CHWY","TOST","U","PATH","GTLB","AFRM","CAVA","WOLF","ENPH","SEDG",
    "SOFI","IONQ","RKLB","JOBY","ACHR","F","GM","RIVN","NIO","BROS","NU","RIOT","MARA","SOUN","BBAI","AI"
]
RECOVERY_TICKERS = [
    "SOFI","PLTR","HIMS","CHWY","TOST","U","PATH","IONQ","RKLB","JOBY","ACHR","RIVN","F","GM",
    "PYPL","NKE","SBUX","TGT","SHOP","SNOW","NET","CELH","ENPH","SEDG","SQ","BROS","ONON","AFRM","CAVA",
    "ADBE","AMD","TSLA","CRM","PANW","CRWD","DECK"
]
ETF_TICKERS = ["SPY","QQQ","IWM","DIA","XLK","XLF","XLV","XLE","XLY","XLP","SMH","ARKK"]


# ============================================================
# V36.0 EXPANDED OPPORTUNITY UNIVERSE
# ============================================================

ELITE_COMPOUNDERS = [
    "MSFT","AVGO","COST","LIN","MA","V","SPGI","ADBE","INTU","ORLY","MCD","WM","PG","PEP","TJX","SHW",
    "AAPL","GOOGL","META","AMZN","UNH","LLY","ISRG","ADP","CDNS","SNPS","KLAC","LRCX"
]

GROWTH_LEADERS = [
    "NVDA","CRWD","PANW","DDOG","MDB","CELH","SNOW","NET","AMD","SHOP","PLTR","TSLA","NOW","TEAM",
    "ZS","FTNT","ANET","TTD","UBER","ABNB","DECK","ONON","ELF"
]

MIDCAP_GROWTH = [
    "APP","DUOL","RKLB","IOT","CAVA","SYM","HIMS","SOFI","UPST","AFRM","TOST","GTLB","PATH","U",
    "BROS","CHWY","WOLF","IONQ","JOBY","ACHR","RIVN","NIO","SOUN","BBAI","AI"
]

RECOVERY_VALUE = [
    "PYPL","NKE","SBUX","ENPH","SEDG","SQ","DOCU","TGT","ADBE","CRM","AMD","TSLA","SHOP","SNOW",
    "NET","CELH","CHWY","TOST","F","GM"
]

DEFENSIVE_QUALITY = [
    "KO","PEP","PG","JNJ","ABBV","MCD","WM","DUK","SO","NEE","CME","CL","KMB","MDLZ","TMO","DHR"
]

ETF_ROTATION = [
    "QQQ","SPY","IWM","DIA","SMH","SOXX","XLK","XLI","XLE","XLY","XLP","XLV","XLU","ARKK","VUG","VTV"
]

CORE_SCAN_TICKERS = sorted(set(
    ELITE_COMPOUNDERS
    + GROWTH_LEADERS
    + MIDCAP_GROWTH
    + RECOVERY_VALUE
    + DEFENSIVE_QUALITY
))

RECOVERY_TICKERS = sorted(set(RECOVERY_TICKERS + RECOVERY_VALUE + MIDCAP_GROWTH))
ETF_TICKERS = ETF_ROTATION

EXCLUDED_SECTOR_KEYWORDS = [
    "financial","bank","banks","insurance","capital markets","asset management","mortgage",
    "reit","real estate","entertainment","media","broadcast","streaming","gaming","casino","resort"
]
EXCLUDED_TICKERS = {
    "JPM","BAC","WFC","C","GS","MS","SCHW","COF","AXP","USB","PNC","TFC","BK","BLK","BX","KKR",
    "AIG","MET","PRU","ALL","TRV","DIS","NFLX","WBD","PARA","CMCSA","ROKU","LYV","DKNG","PENN","MGM","WYNN","LVS",
    "SPCE","GOEV","QS","FCEL","PLUG","BLNK","WKHS","MVST","LCID","OPEN","LAZR","CHPT","DNA"
}

# ============================================================
# LOGIN
# ============================================================

def clean_secret(v):
    """
    Secure but tolerant:
    - trims hidden spaces
    - removes accidental surrounding quotes
    - removes non-breaking spaces
    """
    return str(v or "").replace("\u00a0", " ").strip().strip('"').strip("'")


def first_env(*names):
    """
    Reads the first non-empty Render env var from a list of accepted aliases.
    This prevents login failures from naming ADMIN_USERNAME instead of ADMIN_USER, etc.
    """
    for name in names:
        value = clean_secret(os.getenv(name, ""))
        if value:
            return value
    return ""


ADMIN_USER = first_env("ADMIN_USER", "ADMIN_USERNAME", "ADMIN_LOGIN", "APP_ADMIN_USER")
ADMIN_PASSWORD = first_env("ADMIN_PASSWORD", "ADMIN_PASS", "APP_ADMIN_PASSWORD", "APP_PASSWORD")

VIEW_USER = first_env("VIEW_USER", "VIEW_USERNAME", "VIEWER_USER", "VIEWER_USERNAME", "APP_VIEW_USER")
VIEW_PASSWORD = first_env("VIEW_PASSWORD", "VIEW_PASS", "VIEWER_PASSWORD", "APP_VIEW_PASSWORD")


def require_login():
    for k, d in [("logged_in", False), ("user_role", None), ("login_user", "")]:
        if k not in st.session_state:
            st.session_state[k] = d

    if st.session_state.logged_in:
        return

    st.title("🔐 AI Trading Dashboard V36.0 Login Fix")
    st.caption("Secure login uses Render environment variables only. No passwords are stored in source code.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        eu = clean_secret(username).lower()
        ep = clean_secret(password)

        admin_match = (
            bool(ADMIN_USER)
            and bool(ADMIN_PASSWORD)
            and eu == ADMIN_USER.lower()
            and ep == ADMIN_PASSWORD
        )

        viewer_match = (
            bool(VIEW_USER)
            and bool(VIEW_PASSWORD)
            and eu == VIEW_USER.lower()
            and ep == VIEW_PASSWORD
        )

        if admin_match:
            st.session_state.logged_in = True
            st.session_state.user_role = "admin"
            st.session_state.login_user = ADMIN_USER
            st.rerun()
        elif viewer_match:
            st.session_state.logged_in = True
            st.session_state.user_role = "viewer"
            st.session_state.login_user = VIEW_USER
            st.rerun()
        else:
            st.error("Invalid credentials.")
            st.caption("Username is not case-sensitive. Password is case-sensitive. Hidden spaces, non-breaking spaces, and surrounding quotes are trimmed.")

    with st.expander("🔧 Login Diagnostics"):
        st.write(f"ADMIN_USER / alias set: {'✅' if ADMIN_USER else '❌'}")
        st.write(f"ADMIN_PASSWORD / alias set: {'✅' if ADMIN_PASSWORD else '❌'}")
        st.write(f"VIEW_USER / alias set: {'✅' if VIEW_USER else '❌'}")
        st.write(f"VIEW_PASSWORD / alias set: {'✅' if VIEW_PASSWORD else '❌'}")
        st.caption("Values are hidden for security. Lengths help confirm Render is passing what you expect.")
        st.write(f"Admin username length: {len(ADMIN_USER)}")
        st.write(f"Admin password length: {len(ADMIN_PASSWORD)}")
        st.write(f"Viewer username length: {len(VIEW_USER)}")
        st.write(f"Viewer password length: {len(VIEW_PASSWORD)}")
        st.caption("Accepted admin env names: ADMIN_USER, ADMIN_USERNAME, ADMIN_LOGIN, APP_ADMIN_USER.")
        st.caption("Accepted admin password env names: ADMIN_PASSWORD, ADMIN_PASS, APP_ADMIN_PASSWORD, APP_PASSWORD.")

    if st.button("Reset login session"):
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.login_user = ""
        st.rerun()

    st.stop()


def is_admin():
    return st.session_state.get("user_role") == "admin"


require_login()

# ============================================================
# STORAGE
# ============================================================

def normalize_ticker(t: str) -> str: return t.strip().upper().replace("$","")

def load_json_file(path, default):
    try:
        p = Path(path)
        if p.exists():
            with p.open("r") as f: return json.load(f)
    except Exception: pass
    return default

def save_json_file(path, data):
    try:
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f: json.dump(data, f, indent=2)
        return True
    except Exception as e: st.error(f"Save error: {e}"); return False

def load_watchlist():
    saved = load_json_file(WATCHLIST_FILE, DEFAULT_WATCHLIST)
    clean = []
    for t in saved:
        n = normalize_ticker(str(t))
        if n and n not in clean: clean.append(n)
    return clean or DEFAULT_WATCHLIST

def save_watchlist():  return save_json_file(WATCHLIST_FILE, st.session_state.watchlist)
def load_paper_trades(): return load_json_file(PAPER_TRADES_FILE, [])
def save_paper_trades(): return save_json_file(PAPER_TRADES_FILE, st.session_state.paper_trades)

if "watchlist" not in st.session_state:    st.session_state.watchlist    = load_watchlist()
if "paper_trades" not in st.session_state: st.session_state.paper_trades = load_paper_trades()

# ============================================================
# ALPACA
# ============================================================

ALPACA_KEY    = os.getenv("ALPACA_API_KEY","")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY","")
alpaca_client = None
if ALPACA_AVAILABLE and ALPACA_KEY and ALPACA_SECRET:
    try: alpaca_client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
    except Exception: alpaca_client = None
ALPACA_STATUS = "🟢 Alpaca Connected" if alpaca_client else "🟡 Yahoo Finance"

def _alpaca_bars_to_df(bars, ticker):
    try:
        df = bars.df
        if df.empty: return pd.DataFrame()
        if isinstance(df.index, pd.MultiIndex): df = df.xs(ticker, level="symbol")
        df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume","vwap":"VWAP"})
        if hasattr(df.index,"tz") and df.index.tz is not None: df.index = df.index.tz_localize(None)
        return df.dropna(subset=["Close"])
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=60)
def get_history(ticker, period="1y", interval="1d"):
    ticker = normalize_ticker(ticker)
    if alpaca_client and ALPACA_AVAILABLE:
        try:
            days = {"1y":365,"6mo":182,"3mo":91,"1mo":31,"5d":7,"1d":2}.get(period,365)
            tf_map = {"1d":TimeFrame.Day,"1h":TimeFrame.Hour,"15m":TimeFrame(15,TimeFrameUnit.Minute),"5m":TimeFrame(5,TimeFrameUnit.Minute)}
            tf = tf_map.get(interval, TimeFrame.Day)
            start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days+5)
            req = StockBarsRequest(symbol_or_symbols=ticker, timeframe=tf, start=start)
            bars = alpaca_client.get_stock_bars(req)
            df = _alpaca_bars_to_df(bars, ticker)
            if not df.empty and len(df) >= 10: return df
        except Exception: pass
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        if df is not None and not df.empty: return df.dropna()
    except Exception: pass
    return pd.DataFrame()

@st.cache_data(ttl=30)
def get_live_quote(ticker):
    ticker = normalize_ticker(ticker)
    if alpaca_client and ALPACA_AVAILABLE:
        try:
            req = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            result = alpaca_client.get_stock_latest_quote(req)
            q = result[ticker]; bid = float(q.bid_price or 0); ask = float(q.ask_price or 0)
            if bid > 0 and ask > 0:
                return {"price":round((bid+ask)/2,2),"bid":round(bid,2),"ask":round(ask,2),"spread":round(ask-bid,3),"source":"🟢 Alpaca Live"}
        except Exception: pass
    hist = get_history(ticker, period="5d")
    if not hist.empty:
        return {"price":round(float(hist["Close"].iloc[-1]),2),"bid":None,"ask":None,"spread":None,"source":"🟡 Yahoo"}
    return None

@st.cache_data(ttl=3600)
def get_info(ticker):
    try: return yf.Ticker(ticker).info or {}
    except Exception: return {}

@st.cache_data(ttl=3600)
def get_earnings_flag(ticker):
    try:
        info = get_info(ticker)
        ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        if ts:
            days = (pd.Timestamp(ts, unit="s") - pd.Timestamp.now()).days
            if 0 <= days <= 7:   return f"🔴 Earnings in {days}d — binary risk, reduce size", days
            elif 0 <= days <= 14: return f"🟡 Earnings in {days}d — elevated event risk", days
            elif days < 0:        return "🟢 Earnings recently passed", days
            else:                 return f"🟢 Earnings in {days}d", days
    except Exception: pass
    return "⚪ Earnings unknown", None


# ============================================================
# SIGNAL LOG + ACCURACY + ADAPTIVE THRESHOLD
# ============================================================

def load_signal_log(): return load_json_file(SIGNAL_LOG_FILE, [])
def save_signal_log(log): return save_json_file(SIGNAL_LOG_FILE, log)

def get_adaptive_conviction_threshold(log):
    """Adjusts BUY NOW threshold 63-78 based on last 20 resolved signals."""
    base = 68
    recent = [e for e in log if e.get("outcome_5d")][-20:]
    if len(recent) < 10: return base, "default (need 10+ resolved signals to adapt)"
    wins = sum(1 for e in recent if "Win" in str(e.get("outcome_5d","")))
    wr = wins / len(recent)
    if wr >= 0.65: return 63, f"lowered to 63 — signals working well ({wr*100:.0f}% win rate)"
    elif wr >= 0.55: return 68, f"baseline 68 — performing as expected ({wr*100:.0f}%)"
    elif wr >= 0.45: return 72, f"raised to 72 — tightening ({wr*100:.0f}% win rate)"
    else: return 78, f"raised to 78 — signals underperforming ({wr*100:.0f}%)"

def auto_log_signals(df, threshold=68):
    if df is None or df.empty: return 0
    log = load_signal_log(); existing = {e["id"] for e in log}
    today = datetime.now(EASTERN).strftime("%Y%m%d"); added = 0
    candidates = df[
        (df.get("Signal", pd.Series(dtype=str)).astype(str).str.contains("BUY NOW", na=False)) |
        (df.get("Final Conviction", pd.Series(dtype=float)).fillna(0) >= threshold)
    ] if "Signal" in df.columns else pd.DataFrame()
    for _, row in candidates.iterrows():
        ticker = row.get("Ticker","")
        if not ticker: continue
        sid = f"{ticker}_{today}"
        if sid in existing: continue
        target_low = None
        try: target_low = float(str(row.get("Target / Sell Zone","")).replace("$","").split(" - ")[0])
        except Exception: pass
        log.append({
            "id":sid,"ticker":ticker,"date":datetime.now(EASTERN).strftime("%Y-%m-%d"),
            "timestamp":datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M %p ET"),
            "signal":str(row.get("Signal","")),"conviction":row.get("Final Conviction"),
            "agent_verdict":str(row.get("Agent Verdict","")),"entry_price":row.get("Price"),
            "stop_loss":row.get("Stop Loss"),"target":target_low,
            "risk_reward":str(row.get("Risk / Reward","")),
            "outcome_1d":None,"outcome_5d":None,"outcome_10d":None,
            "pct_1d":None,"pct_5d":None,"pct_10d":None,
        })
        existing.add(sid); added += 1
    if added > 0: save_signal_log(log[-500:])
    return added

def check_signal_outcomes():
    log = load_signal_log(); updated = False
    for entry in log:
        signal_date = entry.get("date"); entry_price = entry.get("entry_price"); ticker = entry.get("ticker")
        if not all([signal_date, entry_price, ticker]): continue
        if entry.get("outcome_10d") is not None: continue
        try:
            hist = get_history(ticker, period="3mo")
            if hist.empty: continue
            signal_dt = pd.Timestamp(signal_date)
            hist_idx = hist.index.normalize() if hasattr(hist.index,"normalize") else hist.index
            hist_after = hist[hist_idx > signal_dt]
            for days,kp,ko in [(1,"pct_1d","outcome_1d"),(5,"pct_5d","outcome_5d"),(10,"pct_10d","outcome_10d")]:
                if entry.get(ko) is None and len(hist_after) >= days:
                    fp = float(hist_after["Close"].iloc[days-1])
                    pct = ((fp - entry_price) / entry_price) * 100
                    entry[kp] = round(pct,2); entry[ko] = "✅ Win" if pct > 0 else "❌ Loss"; updated = True
        except Exception: continue
    if updated: save_signal_log(log)
    return log

def get_weak_signal_patterns(log):
    weak = []
    if not log: return weak
    low  = [e for e in log if e.get("conviction") is not None and float(e.get("conviction") or 0) < 70 and e.get("outcome_5d")]
    high = [e for e in log if e.get("conviction") is not None and float(e.get("conviction") or 0) >= 75 and e.get("outcome_5d")]
    if len(low) >= 5:
        wr = sum(1 for e in low if "Win" in str(e.get("outcome_5d",""))) / len(low)
        if wr < 0.45: weak.append(f"Low conviction signals under 70 have only {wr*100:.0f}% 5D win rate. Consider raising threshold.")
    if len(high) >= 5:
        wr = sum(1 for e in high if "Win" in str(e.get("outcome_5d",""))) / len(high)
        if wr >= 0.60: weak.append(f"High conviction signals 75+ performing well: {wr*100:.0f}% 5D win rate.")
    return weak

def get_accuracy_stats(log):
    stats = {}
    for period,ko,kp in [("1D","outcome_1d","pct_1d"),("5D","outcome_5d","pct_5d"),("10D","outcome_10d","pct_10d")]:
        outcomes = [e[ko] for e in log if e.get(ko)]
        pcts     = [e[kp] for e in log if e.get(kp) is not None]
        if outcomes:
            wins = sum(1 for o in outcomes if "Win" in o)
            stats[period] = {"win_rate":round(wins/len(outcomes)*100,1),"total":len(outcomes),"wins":wins,"avg_return":round(sum(pcts)/len(pcts),2) if pcts else 0}
    return stats

# ============================================================
# POSITION SIZE CALCULATOR
# ============================================================

def calc_position_size(account, risk_pct, entry, stop):
    if entry <= 0 or stop <= 0 or entry <= stop: return None
    risk_dollars = account * (risk_pct / 100)
    risk_per_share = entry - stop
    shares = int(risk_dollars / risk_per_share)
    if shares <= 0: return None
    position_value = shares * entry
    return {"Shares":shares,"Position $":round(position_value,2),"Risk $":round(risk_dollars,2),"Risk per Share":round(risk_per_share,2),"% of Account":round(position_value/account*100,1)}

def render_position_calculator(entry_price=None, stop_price=None):
    modern_section("📐 Position Size Calculator")
    vol_mult, vol_label, vol_note = get_market_volatility_regime()
    if vol_mult != 1.0:
        st.info(f"{vol_label} — {vol_note}")
    c1,c2,c3,c4 = st.columns(4)
    account  = c1.number_input("Account Size ($)", min_value=1000, value=25000, step=1000, key="ps_account")
    risk_pct = c2.number_input("Risk per Trade (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="ps_risk")
    entry    = c3.number_input("Entry Price ($)", min_value=0.01, value=float(entry_price) if entry_price else 100.0, step=0.01, key="ps_entry")
    stop     = c4.number_input("Stop Loss ($)", min_value=0.01, value=float(stop_price) if stop_price else 90.0, step=0.01, key="ps_stop")
    result = calc_position_size(account, risk_pct, entry, stop)
    if result:
        adjusted = int(result["Shares"] * vol_mult)
        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("Raw Shares", result["Shares"])
        m2.metric("Volatility-Adjusted", adjusted, delta=f"{adjusted-result['Shares']:+d}")
        m3.metric("Max Risk $", f"${result['Risk $']:,.2f}")
        m4.metric("Risk/Share", f"${result['Risk per Share']:.2f}")
        m5.metric("% of Account", f"{result['% of Account']}%")
        if vol_mult < 1.0:
            st.caption(f"Shares reduced from {result['Shares']} to {adjusted} due to elevated market volatility. Use the adjusted number.")
        if result["% of Account"] > 20:
            st.warning("Position exceeds 20% of account — reduce size or widen stop.")
    else:
        st.info("Enter a valid entry price higher than stop price.")


# ============================================================
# DIVERSIFICATION ENGINE
# ============================================================

def get_price_bucket(price):
    try:
        price = float(price)
        if price < 10: return "Under $10"
        if price < 30: return "$10-$30"
        if price < 75: return "$30-$75"
        if price < 150: return "$75-$150"
        return "$150+"
    except Exception: return "Unknown"

def is_excluded_company(ticker, info=None):
    ticker = normalize_ticker(str(ticker))
    if ticker in EXCLUDED_TICKERS: return True
    info = info or get_info(ticker)
    combined = " ".join([str(info.get("sector","")),str(info.get("industry","")),str(info.get("longName",""))]).lower()
    return any(kw in combined for kw in EXCLUDED_SECTOR_KEYWORDS)

def filter_excluded_companies(tickers):
    clean = []
    for t in tickers:
        n = normalize_ticker(str(t))
        if not n: continue
        try:
            if not is_excluded_company(n): clean.append(n)
        except Exception: clean.append(n)
    return clean

def diversify_by_price_bucket(df, per_bucket=6, min_conviction=55):
    if df is None or df.empty or "Price" not in df.columns: return df
    work = df.copy()
    work["Price Bucket"] = work["Price"].apply(get_price_bucket)
    sort_col = "Final Conviction" if "Final Conviction" in work.columns else "AI Score" if "AI Score" in work.columns else "Recovery Score" if "Recovery Score" in work.columns else None
    pieces = []
    for bucket in ["Under $10","$10-$30","$30-$75","$75-$150","$150+"]:
        sub = work[work["Price Bucket"] == bucket]
        if sort_col:
            sub = sub[sub[sort_col].fillna(0) >= min_conviction]
            sub = sub.sort_values(sort_col, ascending=False)
        pieces.append(sub.head(per_bucket))
    out = pd.concat(pieces, ignore_index=True) if pieces else work
    if not out.empty and sort_col: out = out.sort_values([sort_col,"Price"], ascending=[False,True])
    return out

# ============================================================
# INDICATORS
# ============================================================

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_atr(hist, period=14):
    try:
        tr = pd.concat([hist["High"]-hist["Low"],(hist["High"]-hist["Close"].shift()).abs(),(hist["Low"]-hist["Close"].shift()).abs()],axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not pd.isna(atr) else None
    except Exception: return None

def calc_macd(close, fast=12, slow=26, signal=9):
    try:
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        bullish = (macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-3] < signal_line.iloc[-3])
        return round(float(macd_line.iloc[-1]),4), round(float(signal_line.iloc[-1]),4), round(float(histogram.iloc[-1]),4), bullish
    except Exception: return None, None, None, False

def get_relative_strength_from_hist(ticker_hist, spy_hist, lookback=63):
    try:
        if any(h is None or h.empty for h in [ticker_hist, spy_hist]): return None
        if len(ticker_hist) < lookback+1 or len(spy_hist) < lookback+1: return None
        t_ret = (ticker_hist["Close"].iloc[-1] / ticker_hist["Close"].iloc[-lookback]) - 1
        s_ret = (spy_hist["Close"].iloc[-1] / spy_hist["Close"].iloc[-lookback]) - 1
        return round(float((t_ret - s_ret) * 100), 1)
    except Exception: return None

def safe_round(v, digits=2):
    try:
        if v is None or pd.isna(v): return None
        return round(float(v), digits)
    except Exception: return None

# ============================================================
# MARKET INTELLIGENCE
# ============================================================

@st.cache_data(ttl=300)
def get_market_regime():
    spy = get_history("SPY", period="1y")
    if spy.empty or len(spy) < 200: return "unknown","⚪ Market Regime Unknown","SPY data unavailable."
    close = spy["Close"]; price = close.iloc[-1]; sma200 = close.rolling(200).mean().iloc[-1]
    if price > sma200 * 1.02:   return "bull","🟢 Bull Market","Momentum signals more reliable. Standard thresholds active."
    elif price < sma200 * 0.98: return "bear","🔴 Bear Market","Signals less reliable. Threshold raised, reduce position sizes."
    return "neutral","🟡 Neutral Market","Near long-term trend. Use starter sizes only."

@st.cache_data(ttl=300)
def get_market_volatility_regime():
    spy = get_history("SPY", period="1mo")
    if spy.empty: return 1.0,"⚪ Volatility Unknown","Use standard sizes."
    vol = spy["Close"].pct_change().dropna().std() * 100
    if vol > 2.0:   return 0.5,  "🔴 High Volatility",     "Very choppy — halve normal position sizes."
    elif vol > 1.5: return 0.75, "🟡 Elevated Volatility",  "Reduce position sizes by 25%."
    elif vol > 1.0: return 1.0,  "🟢 Normal Volatility",    "Standard sizes appropriate."
    else:           return 1.1,  "🟢 Low Volatility",       "Calm market — slightly larger starter size acceptable."

@st.cache_data(ttl=3600)
def get_sector_performance():
    sector_etfs = {"Technology":"XLK","Healthcare":"XLV","Energy":"XLE","Consumer Disc":"XLY","Industrials":"XLI","Semiconductors":"SMH","Utilities":"XLU"}
    perf = {}
    for sector, etf in sector_etfs.items():
        try:
            hist = get_history(etf, period="1mo")
            if not hist.empty and len(hist) >= 2:
                perf[sector] = round(float((hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100), 1)
        except Exception: pass
    return dict(sorted(perf.items(), key=lambda x: x[1], reverse=True))

def get_signal_confidence_rating(row, market_regime):
    conviction  = float(row.get("Final Conviction") or 0)
    macd_bullish= row.get("MACD Bullish", False)
    rs          = row.get("Relative Strength vs SPY %")
    earnings    = str(row.get("Earnings",""))
    rsi         = float(row.get("RSI") or 50)
    fcf         = str(row.get("Free Cash Flow",""))
    score = 0
    if conviction >= 78: score += 3
    elif conviction >= 70: score += 2
    elif conviction >= 63: score += 1
    if macd_bullish: score += 2
    if rs is not None:
        try:
            if float(rs) > 5: score += 1
        except Exception: pass
    if "🔴" not in earnings: score += 1
    if 45 <= rsi <= 68: score += 1
    if fcf and fcf not in ["N/A",""] and "-" not in fcf: score += 1
    if market_regime == "bear": score -= 2
    if score >= 8:   return "🟢 Strong Setup — all factors aligned, best quality entry"
    elif score >= 6: return "🟡 Good Setup — most factors aligned, suitable for starter size"
    elif score >= 4: return "🟠 Partial Setup — some concerns, wait or use very small size"
    else:            return "🔴 Weak Setup — multiple flags, avoid or watch only"

@st.cache_data(ttl=300)
def macro_agent():
    spy = get_history("SPY", period="6mo"); qqq = get_history("QQQ", period="6mo")
    score, reasons = 50, []
    for symbol, hist in [("SPY",spy),("QQQ",qqq)]:
        try:
            close = hist["Close"]; price = close.iloc[-1]
            sma20 = close.rolling(20).mean().iloc[-1]; sma50 = close.rolling(50).mean().iloc[-1]
            if price > sma20 and price > sma50: score += 20; reasons.append(f"{symbol} trend supportive")
            elif price > sma50: score += 8; reasons.append(f"{symbol} above 50-day")
            elif price < sma50: score -= 15; reasons.append(f"{symbol} below 50-day")
        except Exception: reasons.append(f"{symbol} unavailable")
    return max(0, min(100, score)), "; ".join(reasons)


# ============================================================
# 9-AGENT SCORING ENGINE
# ============================================================

def technical_agent(price, sma20, sma50, sma200, rsi, volume_ratio, relative_strength=None):
    score, reasons = 0, []
    if price > sma20: score += 18; reasons.append("above 20-day trend")
    else: reasons.append("below 20-day trend")
    if price > sma50: score += 22; reasons.append("above 50-day trend")
    else: reasons.append("below 50-day trend")
    if price > sma200: score += 25; reasons.append("above 200-day trend")
    else: reasons.append("below 200-day trend")
    if 45 <= rsi <= 70: score += 20; reasons.append("RSI healthy zone")
    elif 30 <= rsi < 45: score += 12; reasons.append("RSI beaten down, stabilizing")
    elif rsi < 30: score += 8; reasons.append("RSI oversold")
    else: score -= 10; reasons.append("RSI overbought")
    if volume_ratio >= 1.3: score += 15; reasons.append("volume confirms interest")
    elif volume_ratio >= 0.9: score += 8; reasons.append("volume normal")
    else: score -= 5; reasons.append("weak volume")
    if relative_strength is not None:
        if relative_strength > 10: score += 15; reasons.append(f"strong RS vs SPY +{relative_strength:.1f}%")
        elif relative_strength > 0: score += 8; reasons.append(f"outperforming SPY +{relative_strength:.1f}%")
        elif relative_strength < -10: score -= 15; reasons.append(f"lagging SPY {relative_strength:.1f}%")
        else: score -= 5; reasons.append(f"slightly lagging SPY {relative_strength:.1f}%")
    return max(0, min(100, score)), "; ".join(reasons)

def risk_agent(price, stop_loss, target_low, risk_score, hist):
    try:
        close = hist["Close"]
        volatility = close.pct_change().dropna().tail(30).std() * 100
        drawdown = ((price - close.tail(90).max()) / close.tail(90).max()) * 100
    except Exception: volatility, drawdown = 3, -10
    rr = max(target_low - price, 0.01) / max(price - stop_loss, 0.01)
    score, reasons = 100, []
    if rr >= 2: reasons.append("R/R attractive")
    elif rr >= 1.2: score -= 15; reasons.append("R/R acceptable")
    else: score -= 30; reasons.append("R/R weak")
    if risk_score >= 55: score -= 25; reasons.append("risk score elevated")
    elif risk_score < 35: reasons.append("risk controlled")
    if volatility > 4: score -= 15; reasons.append("high volatility")
    elif volatility < 2.5: reasons.append("volatility manageable")
    if drawdown < -25: score -= 10; reasons.append("deep recent drawdown")
    else: reasons.append("drawdown not extreme")
    return max(0, min(100, score)), "; ".join(reasons)

def fundamental_agent(info):
    score, reasons = 50, []
    pe = info.get("forwardPE") or info.get("trailingPE")
    profit_margin = info.get("profitMargins"); revenue_growth = info.get("revenueGrowth")
    debt_to_equity = info.get("debtToEquity"); market_cap = info.get("marketCap")
    if market_cap and market_cap > 10_000_000_000: score += 10; reasons.append("large-cap quality")
    elif market_cap: reasons.append("smaller/mid-cap")
    if pe and 0 < pe < 25: score += 15; reasons.append("reasonable valuation")
    elif pe and 25 <= pe < 50: score += 5; reasons.append("elevated valuation")
    elif pe and pe >= 50: score -= 10; reasons.append("expensive valuation")
    if profit_margin and profit_margin > 0.15: score += 15; reasons.append("strong margins")
    elif profit_margin and profit_margin > 0: score += 5; reasons.append("positive margins")
    elif profit_margin is not None: score -= 10; reasons.append("weak margins")
    if revenue_growth and revenue_growth > 0.10: score += 15; reasons.append("healthy revenue growth")
    elif revenue_growth and revenue_growth > 0: score += 5; reasons.append("modest growth")
    elif revenue_growth is not None: score -= 10; reasons.append("negative revenue growth")
    if debt_to_equity and debt_to_equity > 200: score -= 10; reasons.append("elevated debt")
    elif debt_to_equity is not None: score += 5; reasons.append("manageable debt")
    if not reasons: reasons.append("limited fundamental data")
    return max(0, min(100, score)), "; ".join(reasons)

def valuation_agent(info, price=None):
    score, reasons = 50, []
    pe = info.get("forwardPE") or info.get("trailingPE"); peg = info.get("pegRatio")
    ps = info.get("priceToSalesTrailing12Months"); revenue_growth = info.get("revenueGrowth")
    profit_margin = info.get("profitMargins")
    if pe and 0 < pe < 20: score += 18; reasons.append("reasonable PE valuation")
    elif pe and 20 <= pe < 35: score += 8; reasons.append("premium PE but explainable if growth continues")
    elif pe and pe >= 50: score -= 12; reasons.append("high PE requires strong growth")
    if peg and 0 < peg < 1.5: score += 16; reasons.append("PEG supports growth-adjusted valuation")
    elif peg and peg > 2.5: score -= 8; reasons.append("PEG suggests growth may be priced in")
    if ps and 0 < ps < 6: score += 8; reasons.append("price-to-sales not extreme")
    elif ps and ps > 12: score -= 8; reasons.append("price-to-sales is high")
    if revenue_growth and revenue_growth > 0.20: score += 12; reasons.append("strong revenue growth supports valuation")
    elif revenue_growth and revenue_growth < 0: score -= 10; reasons.append("negative revenue growth weakens valuation")
    if profit_margin and profit_margin > 0.15: score += 8; reasons.append("healthy margins support valuation")
    if not reasons: reasons.append("valuation data limited")
    return max(0, min(100, score)), "; ".join(reasons)

def earnings_quality_agent(info):
    score, reasons = 50, []
    revenue_growth = info.get("revenueGrowth"); earnings_growth = info.get("earningsGrowth")
    gross_margin = info.get("grossMargins"); operating_margin = info.get("operatingMargins")
    eps_forward = info.get("forwardEps"); eps_trailing = info.get("trailingEps")
    if revenue_growth and revenue_growth > 0.20: score += 18; reasons.append("strong revenue growth")
    elif revenue_growth and revenue_growth > 0.05: score += 8; reasons.append("positive revenue growth")
    elif revenue_growth and revenue_growth < 0: score -= 12; reasons.append("revenue shrinking")
    if earnings_growth and earnings_growth > 0.20: score += 18; reasons.append("strong earnings growth")
    elif earnings_growth and earnings_growth > 0: score += 8; reasons.append("earnings growing")
    elif earnings_growth and earnings_growth < 0: score -= 12; reasons.append("earnings declining")
    if gross_margin and gross_margin > 0.50: score += 10; reasons.append("very strong gross margins")
    elif gross_margin and gross_margin > 0.30: score += 5; reasons.append("healthy gross margins")
    if operating_margin and operating_margin > 0.20: score += 10; reasons.append("strong operating margins")
    elif operating_margin and operating_margin < 0: score -= 10; reasons.append("negative operating margins")
    if eps_forward and eps_trailing and eps_forward > eps_trailing: score += 8; reasons.append("forward EPS above trailing — improvement expected")
    if not reasons: reasons.append("earnings data limited")
    return max(0, min(100, score)), "; ".join(reasons)

def cashflow_agent(info):
    score, reasons = 50, []
    fcf = info.get("freeCashflow"); ocf = info.get("operatingCashflow")
    cash = info.get("totalCash"); debt_to_equity = info.get("debtToEquity"); current_ratio = info.get("currentRatio")
    if fcf and fcf > 0: score += 20; reasons.append("positive free cash flow")
    elif fcf and fcf < 0: score -= 15; reasons.append("negative free cash flow")
    if ocf and ocf > 0: score += 15; reasons.append("positive operating cash flow")
    elif ocf and ocf < 0: score -= 12; reasons.append("negative operating cash flow")
    if cash and cash > 1_000_000_000: score += 10; reasons.append("large cash reserve")
    elif cash and cash > 100_000_000: score += 5; reasons.append("some cash cushion")
    if debt_to_equity and debt_to_equity < 100: score += 10; reasons.append("debt manageable")
    elif debt_to_equity and debt_to_equity > 200: score -= 12; reasons.append("debt elevated")
    if current_ratio and current_ratio > 1.5: score += 6; reasons.append("healthy short-term liquidity")
    elif current_ratio and current_ratio < 1: score -= 8; reasons.append("possible liquidity pressure")
    if not reasons: reasons.append("cash flow data limited")
    return max(0, min(100, score)), "; ".join(reasons)

def moat_agent(info):
    score, reasons = 50, []
    profit_margin = info.get("profitMargins"); gross_margin = info.get("grossMargins")
    roe = info.get("returnOnEquity"); market_cap = info.get("marketCap")
    if market_cap and market_cap > 50_000_000_000: score += 10; reasons.append("large scale indicates durable position")
    if profit_margin and profit_margin > 0.20: score += 15; reasons.append("strong margins suggest pricing power")
    elif profit_margin and profit_margin > 0.08: score += 6; reasons.append("positive margins, viable business model")
    if gross_margin and gross_margin > 0.50: score += 10; reasons.append("high gross margins indicate product strength")
    if roe and roe > 0.20: score += 12; reasons.append("strong return on equity")
    if not reasons: reasons.append("moat data limited")
    return max(0, min(100, score)), "; ".join(reasons)

def analyst_agent(info, price):
    score, reasons = 50, []
    target = info.get("targetMeanPrice"); rec = str(info.get("recommendationKey","")).lower()
    opinions = info.get("numberOfAnalystOpinions")
    if target and price:
        upside = ((target - price) / price) * 100
        if upside > 20: score += 18; reasons.append(f"analyst target implies strong upside ~{upside:.1f}%")
        elif upside > 8: score += 10; reasons.append(f"analyst target implies moderate upside ~{upside:.1f}%")
        elif upside < -5: score -= 10; reasons.append(f"analyst target below current price by ~{abs(upside):.1f}%")
    if rec in ["buy","strong_buy"]: score += 12; reasons.append("analyst recommendation positive")
    elif rec in ["sell","strong_sell","underperform"]: score -= 15; reasons.append("analyst recommendation negative")
    elif rec: reasons.append(f"analyst recommendation: {rec}")
    if opinions and opinions >= 15: score += 5; reasons.append("wide analyst coverage")
    if not reasons: reasons.append("analyst data limited")
    return max(0, min(100, score)), "; ".join(reasons)

def recovery_agent(price, high_52, low_52, rsi, delta_to_high_pct):
    score, reasons = 0, []
    from_low_pct = ((price - low_52) / low_52 * 100) if low_52 else 0
    if delta_to_high_pct and delta_to_high_pct >= 40: score += 30; reasons.append("large upside gap to 52W high")
    elif delta_to_high_pct and delta_to_high_pct >= 20: score += 20; reasons.append("moderate upside gap")
    else: score += 8; reasons.append("limited recovery gap")
    if from_low_pct <= 15: score += 25; reasons.append("near 52W low")
    elif from_low_pct <= 30: score += 15; reasons.append("close to lower range")
    if rsi < 35: score += 25; reasons.append("oversold rebound setup")
    elif rsi < 50: score += 15; reasons.append("beaten down, stabilizing")
    if price > low_52 * 1.05: score += 10; reasons.append("bounced off lows")
    return max(0, min(100, score)), "; ".join(reasons)


# ============================================================
# FUNDAMENTAL RESEARCH SUMMARY BUILDER
# ============================================================

def classify_investment_style(info, data):
    revenue_growth = info.get("revenueGrowth") or 0; fcf = info.get("freeCashflow") or 0
    margin = info.get("profitMargins") or 0
    rs = data.get("Relative Strength vs SPY %") or 0; rsi = data.get("RSI") or 50
    conviction = data.get("Final Conviction") or 0
    try: rs = float(rs); rsi = float(rsi); conviction = float(conviction)
    except Exception: pass
    if revenue_growth > 0.15 and fcf > 0 and margin > 0.08 and rs > 0: return "💎 Long-Term Compounder"
    if rsi < 40 and conviction >= 55:   return "🔥 Recovery Rebound"
    if rs > 5 and conviction >= 68:     return "📈 Institutional Momentum"
    if revenue_growth > 0.20 and margin <= 0: return "⚠️ Speculative Growth"
    if fcf > 0 and margin > 0.12:       return "🛡 Quality Compounder"
    return "🟡 Swing / Watchlist Candidate"


# ============================================================
# V36.0 FACTOR RANKING ENGINE
# ============================================================

def build_factor_breakdown(row):
    """
    Explains WHY the stock ranks highly versus other candidates.
    Creates institutional-style factor commentary.
    """

    positives = []
    negatives = []
    style_tags = []

    conviction = float(row.get("Final Conviction") or 0)
    rs = float(row.get("Relative Strength vs SPY %") or 0)
    risk = float(row.get("Risk Score") or 50)

    revenue_growth = parse_percent_value(row.get("Revenue Growth"))
    earnings_growth = parse_percent_value(row.get("Earnings Growth"))
    gross_margin = parse_percent_value(row.get("Gross Margin"))
    operating_margin = parse_percent_value(row.get("Operating Margin"))
    debt_equity = row.get("Debt/Equity")
    pe = row.get("Forward PE")
    peg = row.get("PEG Ratio")

    financial_safety = str(row.get("Financial Safety", ""))
    execution_quality = str(row.get("Execution Quality", ""))

    # --------------------------------------------------------
    # Strengths
    # --------------------------------------------------------
    if conviction >= 75:
        positives.append("High overall conviction score across technical, fundamental, and macro analysis.")
    elif conviction >= 65:
        positives.append("Strong overall conviction score relative to the broader opportunity set.")

    if rs > 10:
        positives.append("Outperforming the broader market, showing relative strength versus SPY.")
        style_tags.append("Momentum")
    elif rs > 3:
        positives.append("Holding up better than the market during recent trading periods.")

    if revenue_growth is not None:
        if revenue_growth > 15:
            positives.append(f"Revenue growth is strong at approximately {revenue_growth:.1f}%.")
            style_tags.append("Growth")
        elif revenue_growth > 5:
            positives.append(f"Revenue growth remains healthy at approximately {revenue_growth:.1f}%.")

    if earnings_growth is not None and earnings_growth > 10:
        positives.append(f"Earnings growth is solid at approximately {earnings_growth:.1f}%.")
        style_tags.append("Earnings Compounder")

    if gross_margin is not None and gross_margin > 45:
        positives.append("Gross margins are strong, supporting business quality and pricing power.")
        style_tags.append("Quality")

    if operating_margin is not None and operating_margin > 15:
        positives.append("Operating margins are healthy, indicating operational efficiency.")

    if "🟢" in financial_safety:
        positives.append("Financial safety checks passed with healthy cash flow and manageable balance sheet characteristics.")
        style_tags.append("Financially Stable")

    if risk < 35:
        positives.append("Risk profile is lower than many comparable growth names.")
        style_tags.append("Lower Volatility")

    if pe not in [None, "N/A"]:
        try:
            pe_val = float(pe)
            if pe_val < 22 and revenue_growth and revenue_growth > 10:
                positives.append("Valuation appears reasonable relative to growth expectations.")
                style_tags.append("Reasonable Valuation")
        except Exception:
            pass

    # --------------------------------------------------------
    # Risks / weaknesses
    # --------------------------------------------------------
    if debt_equity not in [None, "N/A"]:
        try:
            dte = float(debt_equity)
            if dte > 150:
                negatives.append(f"Debt-to-equity is elevated at {dte:.1f}, increasing balance sheet risk.")
        except Exception:
            pass

    if revenue_growth is not None and revenue_growth < 3:
        negatives.append("Revenue growth is relatively slow.")

    if earnings_growth is not None and earnings_growth < 0:
        negatives.append("Earnings growth is negative, which weakens forward expectations.")

    if operating_margin is not None and operating_margin < 8:
        negatives.append("Operating margins are thinner than ideal.")

    if pe not in [None, "N/A"]:
        try:
            pe_val = float(pe)
            if pe_val > 45:
                negatives.append(f"Forward PE is elevated at {pe_val:.1f}, limiting valuation margin of safety.")
        except Exception:
            pass

    if peg not in [None, "N/A"]:
        try:
            peg_val = float(peg)
            if peg_val > 3:
                negatives.append(f"PEG ratio is elevated at {peg_val:.2f}, meaning growth may already be priced in.")
        except Exception:
            pass

    if "🔴" in execution_quality:
        negatives.append("Execution quality screen flagged the setup as higher risk.")

    if "🟠" in financial_safety:
        negatives.append("Financial safety gate suggests smaller sizing or watchlist-only positioning.")

    # --------------------------------------------------------
    # Style summary
    # --------------------------------------------------------
    if not style_tags:
        style_tags.append("Balanced")

    style_summary = " • ".join(sorted(set(style_tags)))

    # --------------------------------------------------------
    # Final explanation
    # --------------------------------------------------------
    positive_text = " ".join(positives) if positives else "No major strengths identified."
    negative_text = " ".join(negatives) if negatives else "No major financial or valuation concerns identified."

    summary = (
        f"This stock ranks highly because: {positive_text} "
        f"Key risks or weaker areas: {negative_text}"
    )

    return {
        "Factor Strengths": positive_text,
        "Factor Risks": negative_text,
        "Factor Style": style_summary,
        "Why Ranked Highly": summary
    }



def build_research_summary(ticker, info, data):
    price = data.get("Price")
    forward_pe = info.get("forwardPE"); trailing_pe = info.get("trailingPE"); peg = info.get("pegRatio")
    ps = info.get("priceToSalesTrailing12Months"); revenue_growth = info.get("revenueGrowth")
    earnings_growth = info.get("earningsGrowth"); gross_margin = info.get("grossMargins")
    operating_margin = info.get("operatingMargins"); profit_margin = info.get("profitMargins")
    fcf = info.get("freeCashflow"); ocf = info.get("operatingCashflow")
    cash = info.get("totalCash"); debt = info.get("totalDebt"); debt_to_equity = info.get("debtToEquity")
    target = info.get("targetMeanPrice"); rs = data.get("Relative Strength vs SPY %")
    high_gap = data.get("Delta to 52W High %")

    pe = forward_pe or trailing_pe
    valuation_text = []
    pe_explainer = "PE ratio means how much investors pay for each $1 of earnings. High PE is not automatically bad if the company is growing quickly — it means expectations are higher."
    if pe:
        valuation_text.append(f"The company trades at a PE ratio of about {fmt_num(pe,1)}. {pe_explainer}")
        if pe < 20: valuation_text.append("For many growth companies this is not aggressive if growth remains healthy.")
        elif pe < 35: valuation_text.append("This is a moderate-to-premium valuation, so continued earnings growth matters.")
        else: valuation_text.append("This is a premium valuation — the stock needs strong future growth to justify the price.")
    else:
        valuation_text.append("PE data is limited — valuation should be judged with extra caution.")
    if peg: valuation_text.append(f"PEG ratio is about {fmt_num(peg,2)}. PEG compares valuation to growth; under 1.5 often means the stock is cheaper than it looks relative to its growth rate.")
    if ps: valuation_text.append(f"Price-to-sales is about {fmt_num(ps,2)}, which helps evaluate valuation when earnings are uneven.")
    if target and price:
        try:
            upside = ((target - price) / price) * 100
            valuation_text.append(f"Analyst average target implies about {upside:.1f}% potential upside from the current price.")
        except Exception: pass

    financial_text = ["Revenue growth shows whether the company is selling more over time. Strong revenue growth supports future earnings potential."]
    if revenue_growth is not None:
        financial_text.append(f"Revenue growth is {fmt_pct(revenue_growth)}.")
        if revenue_growth > 0.20: financial_text.append("That is strong growth and can support a higher valuation.")
        elif revenue_growth > 0: financial_text.append("That is positive growth, but not necessarily explosive.")
        else: financial_text.append("Revenue is shrinking, which increases risk at any valuation.")
    if earnings_growth is not None: financial_text.append(f"Earnings growth is {fmt_pct(earnings_growth)}.")
    if gross_margin is not None: financial_text.append(f"Gross margin is {fmt_pct(gross_margin)}, showing how much profit remains after direct costs.")
    if operating_margin is not None: financial_text.append(f"Operating margin is {fmt_pct(operating_margin)}, showing how efficiently the company runs.")
    if profit_margin is not None: financial_text.append(f"Net profit margin is {fmt_pct(profit_margin)}.")

    cashflow_text = [
        "Free cash flow is the cash left after the company pays operating costs and reinvests in the business. It is one of the most honest measures of financial health.",
        f"Free cash flow: {fmt_money(fcf)}.",
        f"Operating cash flow: {fmt_money(ocf)}.",
        f"Cash on hand: {fmt_money(cash)}.",
        f"Total debt: {fmt_money(debt)}.",
    ]
    if debt_to_equity is not None:
        cashflow_text.append(f"Debt-to-equity is {fmt_num(debt_to_equity,1)}. Lower is generally safer; very high debt can pressure the business during downturns.")

    earnings_text = [
        "The market often reacts more to future guidance than to the headline beat or miss.",
        "A company can beat current earnings but fall if guidance is weak, or miss slightly and rise if future guidance improves.",
    ]
    if revenue_growth is not None or earnings_growth is not None:
        earnings_text.append(f"Current data shows revenue growth of {fmt_pct(revenue_growth)} and earnings growth of {fmt_pct(earnings_growth)}.")
    earnings_text.append("For detailed management guidance, verify directly from the earnings release or investor relations page.")

    near_high_text = []
    try: high_gap_val = float(high_gap) if high_gap is not None else None
    except Exception: high_gap_val = None
    if high_gap_val is not None and high_gap_val < 10:
        near_high_text.append("This stock is close to its 52-week high. Strong companies often stay near highs when earnings, cash flow, and institutional demand remain strong — a high price does not automatically mean expensive.")
        if revenue_growth and revenue_growth > 0.15: near_high_text.append("Revenue growth is still strong, which helps explain why investors continue paying a premium.")
        try:
            if rs is not None and float(rs) > 0: near_high_text.append(f"Relative strength vs SPY is positive at +{rs}%, suggesting the stock is outperforming the market.")
        except Exception: pass
    else:
        near_high_text.append("The stock is not near its 52-week high, so the setup may have more recovery upside — but business quality still matters.")

    risk_text = []
    if pe and pe > 35: risk_text.append("Valuation risk: PE ratio is high — stock could fall sharply if growth slows.")
    if revenue_growth is not None and revenue_growth < 0: risk_text.append("Growth risk: revenue is currently declining.")
    if fcf is not None and fcf < 0: risk_text.append("Cash flow risk: free cash flow is negative.")
    if debt_to_equity is not None and debt_to_equity > 200: risk_text.append("Balance sheet risk: debt-to-equity is elevated.")
    if data.get("Risk Score") and float(data.get("Risk Score") or 0) >= 55: risk_text.append("Technical risk: dashboard risk score is elevated.")
    if not risk_text: risk_text.append("Main risks are valuation compression, slower future growth, earnings disappointment, or broader market weakness.")

    thesis_parts = []
    if revenue_growth and revenue_growth > 0.15: thesis_parts.append("growth remains strong")
    if fcf and fcf > 0: thesis_parts.append("free cash flow is positive")
    try:
        if rs is not None and float(rs) > 0: thesis_parts.append("the stock is outperforming SPY")
    except Exception: pass
    if profit_margin and profit_margin > 0.10: thesis_parts.append("profit margins are healthy")
    if target and price:
        try:
            if ((target - price) / price) * 100 > 8: thesis_parts.append("analyst targets imply upside")
        except Exception: pass

    if thesis_parts:
        thesis = f"{ticker} may be attractive because " + ", ".join(thesis_parts) + ". The strongest setups combine business quality, reasonable valuation, cash generation, and good technical timing."
    else:
        thesis = f"{ticker} warrants caution — the available data does not show a strong combination of growth, cash flow, valuation support, and market leadership. Require extra confirmation before acting."

    return {
        "Research Summary": thesis,
        "Valuation Detail": " ".join(valuation_text),
        "Financial Strength Detail": " ".join(financial_text),
        "Cash Flow Detail": " ".join(cashflow_text),
        "Earnings Detail": " ".join(earnings_text),
        "Why Buy Near Highs": " ".join(near_high_text),
        "Risk Factors Detail": " ".join(risk_text),
    }


# ============================================================
# TRADE PLAN
# ============================================================

def build_ai_trade_plan(ticker, price, sma20, sma50, sma200, rsi, ai_score, risk_score,
                         high_52, low_52, upside_to_high, volume_ratio,
                         atr=None, relative_strength=None, market_regime="neutral"):
    delta_to_high_pct = ((high_52 - price) / price * 100) if high_52 and price else None
    delta_to_high_dollars = high_52 - price if high_52 and price else None
    above_20 = price > sma20; above_50 = price > sma50; above_200 = price > sma200
    far_from_high = delta_to_high_pct and delta_to_high_pct >= 20

    if ai_score >= 75 and risk_score < 35 and above_20 and above_50:
        entry_range = f"${price*0.97:.2f} - ${price*1.01:.2f}"; entry_reason = "trend strong; near-current entry reasonable."
    elif rsi < 35 and far_from_high:
        entry_range = f"${price*0.94:.2f} - ${price*0.99:.2f}"; entry_reason = "oversold rebound — staged entries safer."
    elif above_50:
        entry_range = f"${max(sma20*0.98, price*0.96):.2f} - ${price:.2f}"; entry_reason = "holding medium trend — enter near short-term support."
    else:
        entry_range = f"Wait for reclaim above ${sma50:.2f} or pullback to ${price*0.90:.2f} - ${price*0.95:.2f}"; entry_reason = "trend not confirmed — patience."

    if atr and atr > 0:
        atr_mult = 1.6 if market_regime == "bear" else 2.2 if rsi < 35 else 2.0
        atr_stop = price - (atr * atr_mult)
        technical_stop = sma50 * 0.98 if above_50 else price * 0.90
        stop_loss = max(atr_stop, price * 0.82)
        if above_50: stop_loss = min(stop_loss, technical_stop) if technical_stop < price else stop_loss
        stop_reason = f"ATR-based ({atr_mult:.1f}x ATR), adapts to this stock's volatility."
    elif above_50 and risk_score < 40:
        stop_loss = min(sma50 * 0.98, price * 0.92); stop_reason = "below 50-day trend."
    elif rsi < 35:
        stop_loss = price * 0.90; stop_reason = "oversold bounce protection."
    else:
        stop_loss = price * 0.88; stop_reason = "wider stop, weaker confirmation."

    if delta_to_high_pct and delta_to_high_pct > 35:
        target_low = price * 1.12; target_high = min(high_52, price * 1.30); sell_reason = "partial recovery first."
    elif delta_to_high_pct and delta_to_high_pct > 15:
        target_low = price * 1.07; target_high = min(high_52, price * 1.16); sell_reason = "moderate target."
    else:
        target_low = price * 1.04; target_high = price * 1.08; sell_reason = "tight target — limited gap to highs."

    target_zone = f"${target_low:.2f} - ${target_high:.2f}"
    rr = max(target_low - price, 0.01) / max(price - stop_loss, 0.01)
    risk_reward = f"{rr:.2f}:1"
    if rr >= 2 and risk_score < 45: position_note = "Normal starter position reasonable."
    elif rr >= 1.2: position_note = "Smaller starter — add on confirmation."
    else: position_note = "Watch only or very small — R:R not attractive."
    if ai_score >= 80 and risk_score < 30 and above_50: hold_style = "Short swing / momentum"
    elif rsi < 40 and far_from_high: hold_style = "Recovery swing / staged hold"
    elif above_200 and ai_score >= 60: hold_style = "Longer swing / possible long-term"
    elif risk_score >= 55: hold_style = "Watch only"
    else: hold_style = "Watchlist candidate"

    trend_parts = ["above 20-day" if above_20 else "below 20-day","above 50-day" if above_50 else "below 50-day","above 200-day" if above_200 else "below 200-day"]
    rsi_d = f"RSI {rsi:.1f} — {'oversold' if rsi < 30 else 'beaten down stabilizing' if rsi <= 45 else 'healthy zone' if rsi <= 70 else 'overbought avoid chasing'}."
    rs_text = f" RS vs SPY: {'+' if (relative_strength or 0) > 0 else ''}{relative_strength:.1f}%." if relative_strength is not None else ""
    regime_text = " Bear market — smaller size required." if market_regime == "bear" else " Bull backdrop supports momentum." if market_regime == "bull" else ""

    plan = (f"Price is {', '.join(trend_parts)}. {rsi_d}{rs_text}{regime_text} "
            f"Entry: {entry_range} — {entry_reason} "
            f"Stop: ${stop_loss:.2f} — {stop_reason} "
            f"Target: {target_zone} — {sell_reason} R/R: {risk_reward}. {position_note}")

    return {
        "52W High": round(high_52,2) if high_52 else None,
        "Delta to 52W High $": round(delta_to_high_dollars,2) if delta_to_high_dollars is not None else None,
        "Delta to 52W High %": round(delta_to_high_pct,1) if delta_to_high_pct is not None else None,
        "AI Trade Plan": plan, "Entry Range": entry_range,
        "Stop Loss": round(stop_loss,2), "Target / Sell Zone": target_zone,
        "Risk / Reward": risk_reward, "ATR": round(atr,2) if atr else None,
        "Relative Strength vs SPY %": relative_strength,
        "Position Size Note": position_note, "Hold Style": hold_style,
    }

# ============================================================
# ANALYZE TICKER — Full 9-Agent + Regime-Adjusted Conviction
# ============================================================


# ============================================================
# V36.0 FINANCIAL SAFETY GATE
# ============================================================

def financial_safety_gate(info):
    reasons = []
    red_flags = 0
    yellow_flags = 0

    debt_to_equity = info.get("debtToEquity")
    current_ratio = info.get("currentRatio")
    free_cashflow = info.get("freeCashflow")
    operating_cashflow = info.get("operatingCashflow")
    total_cash = info.get("totalCash")
    total_debt = info.get("totalDebt")
    revenue_growth = info.get("revenueGrowth")
    profit_margin = info.get("profitMargins")
    operating_margin = info.get("operatingMargins")
    pe = info.get("forwardPE") or info.get("trailingPE")
    peg = info.get("pegRatio")

    try:
        if debt_to_equity is not None:
            dte = float(debt_to_equity)
            if dte > 250:
                red_flags += 1
                reasons.append(f"Debt-to-equity is very high at {dte:.1f}.")
            elif dte > 150:
                yellow_flags += 1
                reasons.append(f"Debt-to-equity is elevated at {dte:.1f}.")
            else:
                reasons.append(f"Debt-to-equity is manageable at {dte:.1f}.")
    except Exception:
        pass

    try:
        if total_cash is not None and total_debt is not None and float(total_debt) > 0:
            cash_debt = float(total_cash) / float(total_debt)
            if cash_debt < 0.25:
                yellow_flags += 1
                reasons.append("Cash is low relative to debt.")
            elif cash_debt >= 0.75:
                reasons.append("Cash position is healthy relative to debt.")
    except Exception:
        pass

    try:
        if current_ratio is not None:
            cr = float(current_ratio)
            if cr < 0.8:
                red_flags += 1
                reasons.append(f"Current ratio is weak at {cr:.2f}.")
            elif cr < 1.1:
                yellow_flags += 1
                reasons.append(f"Current ratio is low at {cr:.2f}.")
            elif cr >= 1.5:
                reasons.append(f"Current ratio is healthy at {cr:.2f}.")
    except Exception:
        pass

    try:
        if free_cashflow is not None:
            fcf = float(free_cashflow)
            if fcf < 0:
                red_flags += 1
                reasons.append("Free cash flow is negative.")
            elif fcf > 0:
                reasons.append("Free cash flow is positive.")
    except Exception:
        pass

    try:
        if operating_cashflow is not None:
            ocf = float(operating_cashflow)
            if ocf < 0:
                red_flags += 1
                reasons.append("Operating cash flow is negative.")
            elif ocf > 0:
                reasons.append("Operating cash flow is positive.")
    except Exception:
        pass

    try:
        if revenue_growth is not None:
            rg = float(revenue_growth)
            if rg < -0.05:
                red_flags += 1
                reasons.append(f"Revenue is declining by {rg*100:.1f}%.")
            elif rg < 0.03:
                yellow_flags += 1
                reasons.append(f"Revenue growth is low at {rg*100:.1f}%.")
            elif rg > 0.10:
                reasons.append(f"Revenue growth is healthy at {rg*100:.1f}%.")
    except Exception:
        pass

    try:
        if profit_margin is not None:
            pm = float(profit_margin)
            if pm < -0.05:
                red_flags += 1
                reasons.append(f"Profit margin is negative at {pm*100:.1f}%.")
            elif pm < 0.03:
                yellow_flags += 1
                reasons.append(f"Profit margin is thin at {pm*100:.1f}%.")
            elif pm > 0.10:
                reasons.append(f"Profit margin is healthy at {pm*100:.1f}%.")
    except Exception:
        pass

    try:
        if operating_margin is not None:
            om = float(operating_margin)
            if om < -0.05:
                red_flags += 1
                reasons.append(f"Operating margin is negative at {om*100:.1f}%.")
            elif om > 0.10:
                reasons.append(f"Operating margin is healthy at {om*100:.1f}%.")
    except Exception:
        pass

    try:
        if pe is not None and float(pe) > 80:
            yellow_flags += 1
            reasons.append(f"PE ratio is very high at {float(pe):.1f}.")
    except Exception:
        pass

    try:
        if peg is not None and float(peg) > 3:
            yellow_flags += 1
            reasons.append(f"PEG ratio is elevated at {float(peg):.2f}.")
    except Exception:
        pass

    if red_flags >= 2:
        return "🔴 Financial Risk — Not Execution Safe", -25, " ".join(reasons)
    if red_flags == 1:
        return "🟠 Financial Caution — Starter/Watch Only", -15, " ".join(reasons)
    if yellow_flags >= 2:
        return "🟡 Financial Watch — Use Smaller Size", -8, " ".join(reasons)

    if not reasons:
        reasons.append("Financial data is limited; verify before acting.")

    return "🟢 Financially Safer", 5, " ".join(reasons)


def agents_greenlight_status(row):
    agent_cols = [
        "Technical Agent", "Risk Agent", "Fundamental Agent",
        "Valuation Agent", "Earnings Quality Agent", "Cash Flow Agent",
        "Moat Agent", "Analyst Agent", "Macro Agent"
    ]
    weak = []
    caution = []
    available = 0
    for col in agent_cols:
        if col in row and row.get(col) is not None:
            try:
                score = float(row.get(col))
                available += 1
                if score < 45:
                    weak.append(col.replace(" Agent", ""))
                elif score < 55:
                    caution.append(col.replace(" Agent", ""))
            except Exception:
                pass
    if weak:
        return "🔴 Not Green-Lighted", "Weak agents: " + ", ".join(weak)
    if caution:
        return "🟡 Partial Green Light", "Caution agents: " + ", ".join(caution)
    if available >= 5:
        return "🟢 All-Agent Green Light", "Core agents are aligned above minimum thresholds."
    return "🟡 Partial Green Light", "Not enough agent data for a full green light."


def execution_quality_label(row):
    financial = str(row.get("Financial Safety", ""))
    greenlight = str(row.get("Agent Greenlight", ""))
    conviction = float(row.get("Final Conviction") or 0)
    risk_score = float(row.get("Risk Score") or 50)
    if "🔴" in financial or "🔴" in greenlight:
        return "🔴 Avoid Execution"
    if "🟠" in financial:
        return "🟠 Watch Only / Very Small"
    if "🟢" in financial and "🟢" in greenlight and conviction >= 72 and risk_score < 45:
        return "🟢 Execution Candidate"
    if "🟢" in financial and conviction >= 60:
        return "🟡 Starter Candidate"
    return "⚪ Research Only"


def analyze_ticker(ticker):
    ticker = normalize_ticker(ticker)
    hist = get_history(ticker, period="1y")
    if hist.empty or len(hist) < 60: return None

    close = hist["Close"]
    market_status, _ = get_market_status()
    live_quote = None
    if "Open" in market_status and alpaca_client:
        live_quote = get_live_quote(ticker)

    price = float(live_quote["price"]) if live_quote else float(close.iloc[-1])
    price_source = live_quote["source"] if live_quote else "Yahoo close"
    prev = float(close.iloc[-2]) if len(close) > 1 else price
    change_pct = ((price - prev) / prev) * 100 if prev else 0

    sma20  = close.rolling(20).mean().iloc[-1]
    sma50  = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.rolling(100).mean().iloc[-1]
    rsi    = calc_rsi(close).iloc[-1]
    high_52 = hist["High"].max(); low_52 = hist["Low"].min()
    from_low  = ((price - low_52) / low_52) * 100 if low_52 else 0
    from_high = ((price - high_52) / high_52) * 100 if high_52 else 0
    upside_to_high = ((high_52 - price) / price) * 100 if price else 0
    vol = hist["Volume"].iloc[-1]; avg_vol = hist["Volume"].rolling(20).mean().iloc[-1]
    volume_ratio = vol / avg_vol if avg_vol else 1

    atr = calc_atr(hist)
    macd_line, macd_signal_val, macd_hist_val, macd_bullish = calc_macd(close)
    spy_hist = get_history("SPY", period="1y")
    relative_strength = get_relative_strength_from_hist(hist, spy_hist)
    market_regime, market_regime_label, _ = get_market_regime()
    info = get_info(ticker)

    trend_score = 0
    if price > sma20: trend_score += 20
    if price > sma50: trend_score += 20
    if price > sma200: trend_score += 20
    if sma20 > sma50: trend_score += 15
    if 45 <= rsi <= 70: trend_score += 15
    if volume_ratio > 1.1: trend_score += 10

    risk_score = 0
    if rsi > 75: risk_score += 25
    if price < sma50: risk_score += 20
    if price < sma200: risk_score += 25
    if from_high < -25: risk_score += 15
    if volume_ratio < 0.6: risk_score += 10

    ai_score = max(0, min(100, trend_score - (risk_score * 0.65)))
    if ai_score >= 75 and risk_score < 35: signal = "🟢 BUY NOW"
    elif ai_score >= 60: signal = "🟡 Watch"
    elif ai_score >= 45: signal = "⚪ Neutral"
    else: signal = "🔴 Avoid"

    trade_plan = build_ai_trade_plan(
        ticker=ticker, price=price, sma20=sma20, sma50=sma50, sma200=sma200,
        rsi=rsi, ai_score=ai_score, risk_score=risk_score,
        high_52=high_52, low_52=low_52, upside_to_high=upside_to_high,
        volume_ratio=volume_ratio, atr=atr, relative_strength=relative_strength,
        market_regime=market_regime,
    )
    try: target_low = float(trade_plan["Target / Sell Zone"].replace("$","").split(" - ")[0])
    except Exception: target_low = price * 1.08

    tech_score,   tech_reason   = technical_agent(price, sma20, sma50, sma200, rsi, volume_ratio, relative_strength)
    risk_a_score, risk_reason   = risk_agent(price, trade_plan["Stop Loss"], target_low, risk_score, hist)
    fund_score,   fund_reason   = fundamental_agent(info)
    val_score,    val_reason    = valuation_agent(info, price)
    earn_score,   earn_reason   = earnings_quality_agent(info)
    cf_score,     cf_reason     = cashflow_agent(info)
    moat_score,   moat_reason   = moat_agent(info)
    analyst_score,analyst_reason= analyst_agent(info, price)
    financial_status, financial_adjustment, financial_reasons = financial_safety_gate(info)
    rec_score,    rec_reason    = recovery_agent(price, high_52, low_52, rsi, trade_plan["Delta to 52W High %"])
    mac_score,    mac_reason    = macro_agent()

    # Regime-adjusted conviction weights
    if market_regime == "bull":
        final_conviction = round(tech_score*0.22 + risk_a_score*0.10 + mac_score*0.08 + fund_score*0.08 + val_score*0.14 + earn_score*0.14 + cf_score*0.12 + moat_score*0.07 + analyst_score*0.05, 0)
    elif market_regime == "bear":
        final_conviction = round(tech_score*0.15 + risk_a_score*0.18 + mac_score*0.07 + fund_score*0.10 + val_score*0.14 + earn_score*0.13 + cf_score*0.14 + moat_score*0.05 + analyst_score*0.04, 0)
    else:
        final_conviction = round(tech_score*0.20 + risk_a_score*0.12 + mac_score*0.08 + fund_score*0.10 + val_score*0.14 + earn_score*0.14 + cf_score*0.12 + moat_score*0.05 + analyst_score*0.05, 0)

    final_conviction = max(0, min(100, final_conviction + financial_adjustment))

    if final_conviction >= 80:   agent_verdict = "🟢 High Conviction"
    elif final_conviction >= 68: agent_verdict = "🟢 Strong Candidate"
    elif final_conviction >= 55: agent_verdict = "🟡 Watch / Starter Size"
    elif final_conviction >= 45: agent_verdict = "⚪ Mixed Setup"
    else:                        agent_verdict = "🔴 Avoid / Wait"

    if market_regime == "bear" and final_conviction < 75:
        if signal == "🟢 BUY NOW": signal = "🟡 Watch (Bear Market)"
        if agent_verdict in ("🟢 High Conviction","🟢 Strong Candidate"): agent_verdict = "🟡 Bear Market Caution"

    earnings_label, days_to_earnings = get_earnings_flag(ticker)
    if days_to_earnings is not None and 0 <= days_to_earnings <= 7:
        if signal == "🟢 BUY NOW": signal = "🟡 Watch (⚠️ Earnings)"
        if agent_verdict in ("🟢 High Conviction","🟢 Strong Candidate"): agent_verdict = "🟡 Earnings Risk"

    if macd_bullish:
        macd_note = "🟢 MACD bullish crossover — entry timing confirmed."
    elif macd_hist_val is not None and macd_hist_val > 0:
        macd_note = "🟡 MACD positive but no fresh crossover — momentum improving."
    else:
        macd_note = "🔴 MACD still bearish — consider waiting for crossover before entering."

    prelim_data = {
        "Price": safe_round(price), "Final Conviction": safe_round(final_conviction,0),
        "RSI": safe_round(rsi,1), "Relative Strength vs SPY %": relative_strength,
        "Delta to 52W High %": trade_plan["Delta to 52W High %"], "Risk Score": safe_round(risk_score,0),
    }
    research = build_research_summary(ticker, info, prelim_data)
    investment_style = classify_investment_style(info, prelim_data)

    row_data = {
        "Ticker": ticker, "Company Name": info.get("shortName") or info.get("longName") or ticker, "Price": safe_round(price), "Price Bucket": get_price_bucket(price),
        "Price Source": price_source, "Daily %": safe_round(change_pct),
        "AI Score": safe_round(ai_score,0), "Signal": signal, "Earnings": earnings_label,
        "Market Regime": market_regime_label, "Relative Strength vs SPY %": relative_strength,
        "ATR": safe_round(atr), "Risk Score": safe_round(risk_score,0),
        "MACD Bullish": macd_bullish, "MACD Note": macd_note,
        "Technical Agent": safe_round(tech_score,0), "Risk Agent": safe_round(risk_a_score,0),
        "Fundamental Agent": safe_round(fund_score,0), "Valuation Agent": safe_round(val_score,0),
        "Earnings Quality Agent": safe_round(earn_score,0), "Cash Flow Agent": safe_round(cf_score,0),
        "Moat Agent": safe_round(moat_score,0), "Analyst Agent": safe_round(analyst_score,0),
        "Financial Safety": financial_status, "Financial Safety Detail": financial_reasons,
        "Recovery Agent": safe_round(rec_score,0), "Macro Agent": safe_round(mac_score,0),
        "Final Conviction": safe_round(final_conviction,0), "Agent Verdict": agent_verdict,
        "RSI": safe_round(rsi,1), "52W High": trade_plan["52W High"],
        "Delta to 52W High $": trade_plan["Delta to 52W High $"],
        "Delta to 52W High %": trade_plan["Delta to 52W High %"],
        "From 52W Low %": safe_round(from_low,1), "From 52W High %": safe_round(from_high,1),
        "Volume Ratio": safe_round(volume_ratio,2), "Entry Range": trade_plan["Entry Range"],
        "Stop Loss": trade_plan["Stop Loss"], "Target / Sell Zone": trade_plan["Target / Sell Zone"],
        "Risk / Reward": trade_plan["Risk / Reward"], "Hold Style": trade_plan["Hold Style"],
        "Investment Style": investment_style, "Position Size Note": trade_plan["Position Size Note"],
        "Agent Summary": (f"Technical: {tech_reason}. Risk: {risk_reason}. Fundamental: {fund_reason}. "
                         f"Valuation: {val_reason}. Earnings: {earn_reason}. Cash Flow: {cf_reason}. "
                         f"Moat: {moat_reason}. Analyst: {analyst_reason}. Financial Safety: {financial_reasons}. Recovery: {rec_reason}. Macro: {mac_reason}."),
        "Research Summary": research["Research Summary"],
        "Valuation Detail": research["Valuation Detail"],
        "Financial Strength Detail": research["Financial Strength Detail"],
        "Cash Flow Detail": research["Cash Flow Detail"],
        "Earnings Detail": research["Earnings Detail"],
        "Why Buy Near Highs": research["Why Buy Near Highs"],
        "Risk Factors Detail": research["Risk Factors Detail"],
        "AI Trade Plan": trade_plan["AI Trade Plan"],
        "Forward PE": safe_round(info.get("forwardPE"),1), "Trailing PE": safe_round(info.get("trailingPE"),1),
        "PEG Ratio": safe_round(info.get("pegRatio"),2), "Price/Sales": safe_round(info.get("priceToSalesTrailing12Months"),2),
        "Revenue Growth": fmt_pct(info.get("revenueGrowth")), "Earnings Growth": fmt_pct(info.get("earningsGrowth")),
        "Gross Margin": fmt_pct(info.get("grossMargins")), "Operating Margin": fmt_pct(info.get("operatingMargins")),
        "Profit Margin": fmt_pct(info.get("profitMargins")),
        "Free Cash Flow": fmt_money(info.get("freeCashflow")),
        "Operating Cash Flow": fmt_money(info.get("operatingCashflow")),
        "Total Cash": fmt_money(info.get("totalCash")), "Total Debt": fmt_money(info.get("totalDebt")),
        "Debt/Equity": safe_round(info.get("debtToEquity"),1),
        "Analyst Target": safe_round(info.get("targetMeanPrice")), "Analyst Rating": info.get("recommendationKey"),
        "SMA20": safe_round(sma20), "SMA50": safe_round(sma50), "SMA200": safe_round(sma200),
    }
    gl_status, gl_detail = agents_greenlight_status(row_data)
    row_data["Agent Greenlight"] = gl_status
    row_data["Agent Greenlight Detail"] = gl_detail
    row_data["Execution Quality"] = execution_quality_label(row_data)
    factor_breakdown = build_factor_breakdown(row_data)
    row_data["Factor Strengths"] = factor_breakdown["Factor Strengths"]
    row_data["Factor Risks"] = factor_breakdown["Factor Risks"]
    row_data["Factor Style"] = factor_breakdown["Factor Style"]
    row_data["Why Ranked Highly"] = factor_breakdown["Why Ranked Highly"]

    row_data["Signal Confidence"] = get_signal_confidence_rating(row_data, market_regime)
    return row_data


# ============================================================
# V36.0 OPPORTUNITY CATEGORIZATION + DIVERSITY
# ============================================================

def parse_percent_value(value):
    try:
        if value is None:
            return None
        if isinstance(value, str):
            v = value.replace("%", "").replace("+", "").strip()
            if v in ["", "N/A", "None"]:
                return None
            return float(v)
        return float(value)
    except Exception:
        return None


def market_cap_bucket(market_cap):
    try:
        mc = float(market_cap or 0)
        if mc >= 200_000_000_000:
            return "Mega Cap"
        if mc >= 10_000_000_000:
            return "Large Cap"
        if mc >= 2_000_000_000:
            return "Mid Cap"
        if mc > 0:
            return "Small Cap"
        return "Unknown"
    except Exception:
        return "Unknown"


def starter_position_label(row):
    conviction = float(row.get("Final Conviction") or 0)
    risk = float(row.get("Risk Score") or 50)
    earnings = str(row.get("Earnings", ""))

    if "🔴" in earnings:
        return "⚪ Watchlist Candidate — earnings risk"
    if conviction >= 80 and risk < 35:
        return "🟢 Full Position Candidate"
    if conviction >= 65:
        return "🟡 Starter Position Candidate"
    if conviction >= 50:
        return "⚪ Watchlist Candidate"
    return "🔴 Avoid / Wait"


def categorize_opportunity(row):
    style = str(row.get("Investment Style", ""))
    conviction = float(row.get("Final Conviction") or 0)
    rsi = float(row.get("RSI") or 50)
    rs = row.get("Relative Strength vs SPY %")
    revenue = parse_percent_value(row.get("Revenue Growth"))
    fcf = str(row.get("Free Cash Flow", ""))

    try:
        rs = float(rs) if rs is not None else 0
    except Exception:
        rs = 0

    if "Compounder" in style:
        return "💎 Long-Term Compounders"
    if rs > 5 and conviction >= 70:
        return "📈 Institutional Momentum"
    if rsi < 40 and conviction >= 55:
        return "🔥 Recovery Opportunities"
    if revenue is not None and revenue > 20 and conviction >= 60:
        return "💰 Undervalued Growth"
    if "Quality" in style:
        return "🛡 Defensive Quality"
    if conviction >= 55:
        return "🟡 General Opportunities"
    return "⚠ Speculative / Watch Only"


def add_v35_opportunity_columns(df):
    if df is None or df.empty or "Ticker" not in df.columns:
        return df

    work = df.copy()
    sectors = []
    industries = []
    market_caps = []
    market_cap_buckets = []

    for ticker in work["Ticker"].tolist():
        info = get_info(ticker)
        sectors.append(info.get("sector", "Unknown"))
        industries.append(info.get("industry", "Unknown"))
        market_caps.append(fmt_money(info.get("marketCap")))
        market_cap_buckets.append(market_cap_bucket(info.get("marketCap")))

    work["Sector"] = sectors
    work["Industry"] = industries
    work["Market Cap"] = market_caps
    work["Market Cap Bucket"] = market_cap_buckets
    work["Opportunity Category"] = work.apply(categorize_opportunity, axis=1)
    work["Position Recommendation"] = work.apply(starter_position_label, axis=1)

    return work


def enforce_sector_diversity(df, max_per_sector=3):
    if df is None or df.empty or "Sector" not in df.columns:
        return df

    output = []
    sector_counts = {}
    sort_col = "Final Conviction" if "Final Conviction" in df.columns else None
    work = df.sort_values(sort_col, ascending=False) if sort_col else df.copy()

    for _, row in work.iterrows():
        sector = row.get("Sector", "Unknown") or "Unknown"
        if sector_counts.get(sector, 0) < max_per_sector:
            output.append(row)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

    return pd.DataFrame(output) if output else work.head(0)


def show_opportunity_category_tabs(df):
    if df is None or df.empty or "Opportunity Category" not in df.columns:
        st.info("No categorized opportunities available.")
        return

    categories = [
        "💎 Long-Term Compounders",
        "📈 Institutional Momentum",
        "💰 Undervalued Growth",
        "🔥 Recovery Opportunities",
        "🛡 Defensive Quality",
        "🟡 General Opportunities",
        "⚠ Speculative / Watch Only",
    ]

    tabs = st.tabs(["Compounders", "Momentum", "Undervalued", "Recovery", "Defensive", "General", "Speculative"])
    for tab, category in zip(tabs, categories):
        with tab:
            sub = df[df["Opportunity Category"] == category]
            if sub.empty:
                st.info(f"No current names in {category}.")
            else:
                st.caption(f"{category} — ranked by conviction with trade checklist available.")
                render_signal_cards(sub, limit=25, show_checklist=True)



@st.cache_data(ttl=300)
def build_scan(tickers, diversified=True, per_bucket=6, sector_diverse=True, min_conviction=55):
    unique = []
    for t in tickers:
        n = normalize_ticker(str(t))
        if n and n not in unique:
            unique.append(n)

    unique = filter_excluded_companies(unique)

    if not unique:
        return pd.DataFrame()

    try:
        with ThreadPoolExecutor(max_workers=min(8, len(unique))) as ex:
            results = list(ex.map(analyze_ticker, unique))
        rows = [r for r in results if r]
    except Exception:
        rows = [r for r in (analyze_ticker(t) for t in unique) if r]

    df = pd.DataFrame(rows)

    if not df.empty:
        if "Ticker" in df.columns:
            df = df[~df["Ticker"].apply(lambda t: is_excluded_company(t))]

        df = add_v35_opportunity_columns(df)

        sort_col = "Final Conviction" if "Final Conviction" in df.columns else "AI Score"
        df = df.sort_values([sort_col, "Risk Score"], ascending=[False, True])

        if diversified:
            df = diversify_by_price_bucket(df, per_bucket=per_bucket, min_conviction=min_conviction)
            if sector_diverse:
                df = enforce_sector_diversity(df, max_per_sector=3)

    return df

@st.cache_data(ttl=3600)
def build_recovery_radar(tickers):
    rows = []
    for ticker in tickers:
        try:
            ticker = normalize_ticker(ticker)
            if is_excluded_company(ticker): continue
            hist = get_history(ticker, period="1y")
            if hist.empty or len(hist) < 60: continue
            info = get_info(ticker)
            price = float(hist["Close"].iloc[-1])
            low_52 = hist["Low"].min(); high_52 = hist["High"].max()
            rsi = float(calc_rsi(hist["Close"]).iloc[-1]); atr = calc_atr(hist)
            spy_hist = get_history("SPY", period="1y")
            relative_strength = get_relative_strength_from_hist(hist, spy_hist)
            distance_from_low = ((price - low_52) / low_52) * 100
            upside_to_high = ((high_52 - price) / price) * 100
            change_21d_1m = ((price - hist["Close"].iloc[-22]) / hist["Close"].iloc[-22]) * 100
            change_90d = ((price - hist["Close"].iloc[-63]) / hist["Close"].iloc[-63]) * 100
            market_cap = info.get("marketCap",0)
            target_price = info.get("targetMeanPrice")
            analyst_upside = ((target_price - price) / price * 100) if target_price and price else None

            score = 0
            if distance_from_low <= 10: score += 25
            elif distance_from_low <= 20: score += 18
            elif distance_from_low <= 30: score += 10
            if rsi < 30: score += 25
            elif rsi < 40: score += 18
            elif rsi < 50: score += 8
            if upside_to_high > 50: score += 20
            elif upside_to_high > 30: score += 15
            elif upside_to_high > 15: score += 8
            if change_21d_1m < -15: score += 15
            elif change_21d_1m < -8: score += 10
            elif change_21d_1m < 0: score += 5
            if analyst_upside and analyst_upside > 25: score += 15
            elif analyst_upside and analyst_upside > 10: score += 8
            if market_cap and market_cap > 10_000_000_000: score += 10

            if score >= 75: rating = "🟢 Strong Recovery Candidate"; hold = "Recovery swing / staged long-term hold"
            elif score >= 55: rating = "🟡 Watchlist Bounce Candidate"; hold = "Watchlist bounce candidate"
            else: rating = "🔴 Risky / Possible Value Trap"; hold = "Watch only"

            rows.append({
                "Ticker":ticker,"Price":safe_round(price),"Price Bucket":get_price_bucket(price),
                "Recovery Score":safe_round(score,0),"Rating":rating,
                "RSI":safe_round(rsi,1),"ATR":safe_round(atr),"Relative Strength vs SPY %":relative_strength,
                "52W High":safe_round(high_52),"Delta to 52W High $":safe_round(high_52-price),
                "Delta to 52W High %":safe_round(((high_52-price)/price*100),1),
                "From 52W Low %":safe_round(distance_from_low,1),
                "Entry Range":f"${price*0.95:.2f} - ${price:.2f}",
                "Stop Loss":safe_round(price*0.90),
                "Target / Sell Zone":f"${price*1.10:.2f} - ${min(high_52,price*1.25):.2f}",
                "Risk / Reward":"~1.5:1 est.","Hold Style":hold,
                "Position Size Note":"Use staged entries; add only after trend confirmation.",
                "AI Trade Plan":f"{ticker} has {upside_to_high:.1f}% upside to 52W high. {'Strong recovery setup.' if score >= 75 else 'Watchlist candidate.' if score >= 55 else 'Value-trap risk — wait for confirmation.'}",
                "21D / 1M Change %":safe_round(change_21d_1m,1),"90D Change %":safe_round(change_90d,1),
                "Analyst Upside %":safe_round(analyst_upside,1),"Forward PE":safe_round(info.get("forwardPE"),1),
            })
        except Exception: continue
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Recovery Score", ascending=False)
        df = diversify_by_price_bucket(df, per_bucket=5, min_conviction=55)
    return df

def check_sector_concentration(df):
    if df is None or df.empty or "Ticker" not in df.columns: return {}
    sectors = {}
    for ticker in df["Ticker"].dropna().tolist():
        try:
            sector = get_info(ticker).get("sector","Unknown") or "Unknown"
            sectors[sector] = sectors.get(sector,0) + 1
        except Exception: sectors["Unknown"] = sectors.get("Unknown",0) + 1
    return sectors

def show_sector_concentration_warning(df):
    sectors = check_sector_concentration(df); total = sum(sectors.values())
    if not sectors or total == 0: return
    top_sector, top_count = max(sectors.items(), key=lambda x: x[1])
    if total >= 3 and (top_count / total) > 0.50:
        st.warning(f"⚠️ Sector concentration: {top_count} of {total} signals are in {top_sector}. Diversify before committing capital.")

def load_alert_history(): return load_json_file(ALERT_HISTORY_FILE, [])
def save_alert_history(h): return save_json_file(ALERT_HISTORY_FILE, h)
def log_alert(alert_type, tickers):
    history = load_alert_history()
    history.append({"timestamp":datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M:%S %p ET"),"alert_type":alert_type,"tickers":", ".join(str(t) for t in tickers) if isinstance(tickers,list) else str(tickers)})
    save_alert_history(history[-100:])
def send_email_alert(subject, body):
    sender = os.getenv("EMAIL_SENDER",""); password = os.getenv("EMAIL_PASSWORD",""); recipients = os.getenv("EMAIL_RECIPIENTS","")
    if not sender or not password or not recipients: return False,"Missing EMAIL_SENDER, EMAIL_PASSWORD, or EMAIL_RECIPIENTS."
    msg = MIMEText(body); msg["Subject"] = subject; msg["From"] = sender; msg["To"] = recipients
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com",465) as server:
            server.login(sender, password)
            server.sendmail(sender, [x.strip() for x in recipients.split(",")], msg.as_string())
        return True,"Email sent."
    except Exception as e: return False,str(e)


# ============================================================
# TABLE HELPERS
# ============================================================

COLUMN_HELP = {
    "Ticker":"Click to open Yahoo Finance.", "Price":"Live from Alpaca during market hours; otherwise Yahoo close.",
    "Signal Confidence":"Plain-English rating based on all signal factors combined.",
    "MACD Note":"Entry timing confirmation using MACD crossover.",
    "Investment Style":"Classifies as Long-Term Compounder, Recovery Rebound, Momentum, Quality, or Speculative.",
    "Relative Strength vs SPY %":"3-month performance vs SPY. Positive = outperforming.",
    "ATR":"Average True Range used for volatility-adjusted stops.",
    "Market Regime":"SPY vs 200-day MA — bull/neutral/bear.",
    "Final Conviction":"9-agent weighted synthesis, regime-adjusted.",
    "Agent Verdict":"Final multi-agent label.",
    "RSI":"Below 30 oversold, above 70 overbought.",
    "Forward PE":"What you pay for each $1 of next year's expected earnings. S&P 500 avg ~21x.",
    "PEG Ratio":"P/E divided by growth rate. Under 1.5 often means undervalued relative to growth.",
    "Revenue Growth":"Year-over-year revenue growth. Above 15% is strong.",
    "Free Cash Flow":"Cash left after operating costs and reinvestment. Most honest financial health indicator.",
    "Analyst Target":"Average analyst price target.",
    "Entry Range":"Suggested entry zone.", "Stop Loss":"Setup invalidated below this level.",
    "Target / Sell Zone":"Profit-taking area.", "Risk / Reward":"Reward vs risk ratio.",
    "Hold Style":"Suggested hold duration.", "Recovery Score":"Rebound potential 0-100.",
    "Research Summary":"Plain-English investment thesis explaining the business case.",
    "Valuation Detail":"Explains PE, PEG, price/sales, and whether valuation looks justified.",
    "Financial Strength Detail":"Revenue, margins, and business quality explained.",
    "Cash Flow Detail":"Free cash flow, operating cash flow, cash, and debt explained.",
    "Why Buy Near Highs":"Why strong stocks can still be attractive near highs.",
    "P/L $":"Paper trade dollar P/L.", "P/L %":"Paper trade % P/L.",
    "Stop Status":"Whether price is above or below paper trade stop.",
}

COMPACT_COLUMNS = [
    "Ticker","Price","Signal Confidence","Signal","Investment Style","Earnings","Market Regime","RSI",
    "MACD Note","Relative Strength vs SPY %","Final Conviction","Agent Verdict",
    "Forward PE","PEG Ratio","Revenue Growth","Free Cash Flow",
    "Entry Range","Stop Loss","Target / Sell Zone","Risk / Reward","Hold Style",
    "52W High","Delta to 52W High %"
]

def build_column_config(df, symbol_col=None):
    config = {}
    if df is None or df.empty: return config
    for col in df.columns:
        help_text = COLUMN_HELP.get(str(col),"")
        if symbol_col and col == symbol_col:
            config[col] = st.column_config.LinkColumn(label=col, help=help_text, display_text=r"https://finance\.yahoo\.com/quote/(.*)")
        elif pd.api.types.is_numeric_dtype(df[col]):
            config[col] = st.column_config.NumberColumn(label=col, help=help_text)
        else:
            config[col] = st.column_config.TextColumn(label=col, help=help_text)
    return config

def compact_table(df):
    if df is None or df.empty: return df
    cols = [c for c in COMPACT_COLUMNS if c in df.columns]
    return df[cols] if cols else df

def prepare_display_table(df):
    if df is None or df.empty: return df
    hidden = ["SMA20","SMA50","SMA200","Price Source","MACD Bullish",
              "Research Summary","Valuation Detail","Financial Strength Detail",
              "Cash Flow Detail","Earnings Detail","Why Buy Near Highs","Risk Factors Detail"]
    return df.drop(columns=[c for c in hidden if c in df.columns], errors="ignore")

def render_clickable_table(df, symbol_col="Ticker", default_compact=True, table_id="default"):
    if df.empty: st.info("No data to show."); return
    use_compact = st.toggle("Compact view", value=default_compact, key=f"compact_view_{table_id}")
    display_df = prepare_display_table(compact_table(df) if use_compact else df).copy()
    if symbol_col in display_df.columns:
        display_df[symbol_col] = display_df[symbol_col].apply(lambda x: f"https://finance.yahoo.com/quote/{x}")
    st.data_editor(display_df, column_config=build_column_config(display_df, symbol_col if symbol_col in display_df.columns else None), hide_index=True, use_container_width=True, disabled=True)

def show_last_refresh():
    st.caption(f"Last refreshed: {datetime.now(EASTERN).strftime('%Y-%m-%d %I:%M:%S %p ET')}")

# ============================================================
# MARKET STATUS
# ============================================================

def get_market_status():
    now = datetime.now(EASTERN)
    if now.weekday() >= 5: return "🔴 Market Closed","Weekend."
    open_t  = now.replace(hour=9,minute=30,second=0,microsecond=0)
    close_t = now.replace(hour=16,minute=0,second=0,microsecond=0)
    pre_t   = now.replace(hour=4,minute=0,second=0,microsecond=0)
    after_t = now.replace(hour=20,minute=0,second=0,microsecond=0)
    if pre_t <= now < open_t:     return "🟡 Pre-Market","Market opens at 9:30 AM ET."
    elif open_t <= now <= close_t: return "🟢 Market Open","Live prices active."
    elif close_t < now <= after_t: return "🟡 After Hours","Regular session closed."
    return "🔴 Market Closed","Market closed."

def show_market_status_banner():
    status, note = get_market_status()
    if "Open" in status:                  st.success(f"{status} — {note}")
    elif "Pre" in status or "After" in status: st.info(f"{status} — {note}")
    else:                                 st.warning(f"{status} — {note}")

def show_market_regime_banner():
    regime, label, note = get_market_regime()
    if regime == "bull":    st.success(f"{label} — {note}")
    elif regime == "bear":  st.error(f"{label} — {note}")
    elif regime == "neutral": st.warning(f"{label} — {note}")
    else:                   st.info(f"{label} — {note}")

# ============================================================
# CHART
# ============================================================

def plot_candlestick_chart(ticker, hist):
    if hist is None or hist.empty: st.info("No chart data."); return
    chart_df = hist.copy(); n = len(chart_df)
    if n >= 180: periods,labels = [20,50,200],["SMA20","SMA50","SMA200"]
    elif n >= 60: periods,labels = [5,10,20],["MA5","MA10","MA20"]
    else: periods,labels = [3,5,10],["MA3","MA5","MA10"]
    for p,l in zip(periods,labels):
        if n >= p: chart_df[l] = chart_df["Close"].rolling(p).mean()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.72,0.28], subplot_titles=(f"{ticker} Price Action","Volume"))
    fig.add_trace(go.Candlestick(x=chart_df.index, open=chart_df["Open"], high=chart_df["High"], low=chart_df["Low"], close=chart_df["Close"], name="Candles"), row=1, col=1)
    for l in labels:
        if l in chart_df.columns and chart_df[l].notna().sum() > 0:
            fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df[l], mode="lines", name=l), row=1, col=1)
    fig.add_trace(go.Bar(x=chart_df.index, y=chart_df["Volume"], name="Volume"), row=2, col=1)
    fig.update_layout(height=720, margin=dict(l=10,r=10,t=55,b=10), xaxis_rangeslider_visible=False, template="plotly_white", legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="left",x=0))
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# DETAIL PAGE — Full fundamental deep-dive
# ============================================================

def detail_page(ticker):
    ticker = normalize_ticker(ticker)
    st.markdown(f"## 🔎 Deep Detail: {ticker}")
    data = analyze_ticker(ticker)
    chart_mode = st.radio("Chart timeframe", ["1Y Daily","5D 15-Min","1D 5-Min"], horizontal=True, key=f"chart_mode_{ticker}")
    if chart_mode == "1D 5-Min":   hist = get_history(ticker, period="1d", interval="5m")
    elif chart_mode == "5D 15-Min": hist = get_history(ticker, period="5d", interval="15m")
    else:                           hist = get_history(ticker, period="1y", interval="1d")
    if not data or hist.empty: st.warning("No data found."); return

    live = get_live_quote(ticker)
    if live:
        lc1,lc2,lc3,lc4 = st.columns(4)
        lc1.metric("Live Price", f"${live['price']}")
        if live["bid"]: lc2.metric("Bid / Ask", f"${live['bid']} / ${live['ask']}")
        if live["spread"]: lc3.metric("Spread", f"${live['spread']}")
        lc4.caption(live["source"])

    earnings_label, days_to_earnings = get_earnings_flag(ticker)
    if days_to_earnings is not None and 0 <= days_to_earnings <= 14: st.warning(f"⚠️ {earnings_label}")
    else: st.caption(earnings_label)

    st.info(data.get("Signal Confidence",""))
    st.caption(data.get("MACD Note",""))
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Final Conviction", data.get("Final Conviction","N/A"))
    c2.metric("AI Score", data["AI Score"])
    c3.metric("RSI", data["RSI"])
    c4.metric("Signal", data["Signal"])
    c5.metric("Investment Style", data.get("Investment Style",""))

    plot_candlestick_chart(ticker, hist)

    modern_section("🔬 AI Investment Research")
    st.info(data.get("Research Summary","No research summary available."))

    with st.expander("💰 Valuation — PE, PEG, and whether the price makes sense", expanded=True):
        st.write(data.get("Valuation Detail",""))
        vcols = st.columns(4)
        vcols[0].metric("Forward PE", data.get("Forward PE","N/A"), help="What you pay per $1 of expected earnings. S&P avg ~21x.")
        vcols[1].metric("PEG Ratio", data.get("PEG Ratio","N/A"), help="Under 1.5 = often undervalued relative to growth rate.")
        vcols[2].metric("Price/Sales", data.get("Price/Sales","N/A"), help="Market cap vs annual revenue. Lower is cheaper.")
        vcols[3].metric("Analyst Target", f"${data.get('Analyst Target','N/A')}", help="Average analyst price target.")

    with st.expander("📊 Financial Strength — revenue, margins, and business quality", expanded=True):
        st.write(data.get("Financial Strength Detail",""))
        fcols = st.columns(4)
        fcols[0].metric("Revenue Growth", data.get("Revenue Growth","N/A"))
        fcols[1].metric("Gross Margin", data.get("Gross Margin","N/A"))
        fcols[2].metric("Operating Margin", data.get("Operating Margin","N/A"))
        fcols[3].metric("Profit Margin", data.get("Profit Margin","N/A"))

    with st.expander("💵 Cash Flow — how healthy the company's cash engine is", expanded=True):
        st.write(data.get("Cash Flow Detail",""))
        ccols = st.columns(4)
        ccols[0].metric("Free Cash Flow", data.get("Free Cash Flow","N/A"), help="Most honest financial health indicator.")
        ccols[1].metric("Operating Cash Flow", data.get("Operating Cash Flow","N/A"))
        ccols[2].metric("Total Cash", data.get("Total Cash","N/A"))
        ccols[3].metric("Total Debt", data.get("Total Debt","N/A"))

    with st.expander("📈 Earnings Context — why beats, misses, and guidance matter", expanded=False):
        st.write(data.get("Earnings Detail",""))

    with st.expander("🏔 Why Buy Near Highs? — when a high price is still a good price", expanded=False):
        st.write(data.get("Why Buy Near Highs",""))

    with st.expander("⚠️ Risk Factors — what could go wrong", expanded=False):
        st.write(data.get("Risk Factors Detail",""))

    modern_section("🚪 Exit Strategy — When to Sell")
    stop   = data.get("Stop Loss", 0)
    target = data.get("Target / Sell Zone","")
    price  = data.get("Price", 0)
    rsi_v  = data.get("RSI", 50)
    st.markdown(get_exit_strategy(price, stop, target, rsi_v))

    modern_section("📋 Trade Checklist")
    render_trade_checklist(data)

    modern_section("📐 Trade Plan")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Hold Style:** {data.get('Hold Style','N/A')}")
        st.markdown(f"**Entry Range:** {data.get('Entry Range','N/A')}")
        st.markdown(f"**Stop Loss:** ${data.get('Stop Loss','N/A')}")
    with col2:
        st.markdown(f"**Target / Sell Zone:** {data.get('Target / Sell Zone','N/A')}")
        st.markdown(f"**Risk / Reward:** {data.get('Risk / Reward','N/A')}")
        st.markdown(f"**Gap to 52W High:** {data.get('Delta to 52W High %','N/A')}%")
        st.markdown(f"**RS vs SPY:** {data.get('Relative Strength vs SPY %','N/A')}%")
        st.markdown(f"**ATR:** ${data.get('ATR','N/A')}")
    st.info(data.get("AI Trade Plan",""))

    modern_section("🤖 9-Agent Breakdown")
    agent_cols = ["Technical Agent","Risk Agent","Fundamental Agent","Valuation Agent","Earnings Quality Agent","Cash Flow Agent","Moat Agent","Analyst Agent","Recovery Agent","Macro Agent","Final Conviction","Agent Verdict"]
    st.dataframe(pd.DataFrame([{k: data.get(k,"N/A") for k in agent_cols}]), use_container_width=True, hide_index=True)
    st.caption(data.get("Agent Summary",""))

    render_position_calculator(entry_price=data.get("Price"), stop_price=data.get("Stop Loss"))

    modern_section("📋 Full Snapshot")
    st.dataframe(pd.DataFrame([data]), use_container_width=True, hide_index=True)


# ============================================================
# V36.0 FEATURE 1: TRADE HEALTH MONITOR
# ============================================================

def get_exit_strategy(entry_price, stop_loss, target_zone, rsi=None):
    """Returns plain-English exit guidance for an open position."""
    try:
        target_low = float(str(target_zone).replace("$","").split(" - ")[0])
        target_high = float(str(target_zone).replace("$","").split(" - ")[1])
    except Exception:
        target_low = entry_price * 1.07
        target_high = entry_price * 1.15

    rsi_take_profit = 75
    hold_condition  = entry_price * 0.97  # 3% pullback is normal noise

    lines = [
        f"🎯 **Take profits when:** Price reaches ${target_low:.2f} – ${target_high:.2f}. "
        f"Also consider trimming if RSI exceeds {rsi_take_profit}.",
        f"🛑 **Cut losses when:** Price closes below ${stop_loss:.2f} — do not average down below the stop.",
        f"⏸ **Hold through normal noise:** Pullbacks above ${hold_condition:.2f} (3% from entry) are normal. "
        f"Only re-evaluate if price closes below the 20-day moving average on heavy volume.",
        "📋 **Rule:** Sell in stages — take 50% off at the first target, let the rest run to the higher target with a trailing stop.",
    ]
    return "\n\n".join(lines)


def render_trade_health_monitor(trade, data):
    """
    Evaluates an open paper trade and shows plain-English health status.
    """
    if not data:
        st.caption("Could not fetch current data for health check.")
        return

    entry      = float(trade.get("Entry Price") or 0)
    stop       = float(trade.get("Stop Loss") or 0)
    current    = float(data.get("Price") or 0)
    target_str = str(data.get("Target / Sell Zone",""))
    rsi        = float(data.get("RSI") or 50)
    macd_bull  = data.get("MACD Bullish", False)
    sma20      = float(data.get("SMA20") or 0)

    if entry <= 0 or current <= 0:
        st.caption("Insufficient data for health check.")
        return

    pct_from_entry = ((current - entry) / entry) * 100
    pct_from_stop  = ((current - stop) / stop * 100) if stop > 0 else None

    # Target parsing
    try:
        target_low  = float(target_str.replace("$","").split(" - ")[0])
        target_high = float(target_str.replace("$","").split(" - ")[1])
    except Exception:
        target_low  = entry * 1.07
        target_high = entry * 1.15

    # Determine health status
    if stop > 0 and current <= stop:
        status = "🛑 STOP BREACHED"
        color  = "#ef4444"
        msg    = f"Price ${current:.2f} is at or below stop ${stop:.2f}. Exit this position — the setup has been invalidated. Do not hold hoping for a recovery."
    elif current >= target_low:
        status = "🎯 TARGET ZONE REACHED"
        color  = "#2563eb"
        msg    = f"Price ${current:.2f} has entered the target zone (${target_low:.2f} – ${target_high:.2f}). Consider taking 50% off here and raising your stop to breakeven on the rest."
    elif rsi > 75 and not macd_bull:
        status = "⚠️ EXIT SIGNAL FORMING"
        color  = "#f59e0b"
        msg    = f"RSI is elevated at {rsi:.1f} and MACD momentum is fading. Price is {pct_from_entry:+.1f}% from entry. Consider tightening your stop or taking partial profits."
    elif sma20 > 0 and current < sma20 and pct_from_entry < 0:
        status = "⚠️ WEAKENING"
        color  = "#f59e0b"
        msg    = f"Price ${current:.2f} has dropped below the 20-day moving average and is {pct_from_entry:.1f}% from your entry. Watch closely — if it doesn't reclaim the 20-day within 1-2 sessions, consider exiting."
    elif pct_from_entry > 0 and (rsi < 70 or macd_bull):
        status = "🟢 ON TRACK"
        color  = "#16a34a"
        msg    = f"Price is {pct_from_entry:+.1f}% from your entry of ${entry:.2f}. RSI is {rsi:.1f} — momentum is healthy. {'MACD is bullish, supporting continuation.' if macd_bull else 'Hold your position and respect the stop.'}"
    elif pct_from_entry >= -3:
        status = "🟡 NORMAL PULLBACK"
        color  = "#f59e0b"
        msg    = f"Price is {pct_from_entry:.1f}% from entry — within normal noise range. Stop at ${stop:.2f} is still intact. Hold and monitor."
    else:
        status = "🟡 MONITOR CLOSELY"
        color  = "#f59e0b"
        msg    = f"Position is {pct_from_entry:.1f}% from entry. Not at stop yet, but requires attention. Check if the original thesis still holds."

    st.markdown(f"""
    <div style="background:#ffffff;border-left:5px solid {color};border-radius:12px;padding:14px 18px;margin-bottom:10px;box-shadow:0 4px 12px rgba(15,23,42,0.07);">
        <div style="font-size:1rem;font-weight:800;color:#111827;">{status}</div>
        <div style="margin-top:6px;color:#334155;font-size:0.9rem;line-height:1.5;">{msg}</div>
    </div>
    """, unsafe_allow_html=True)

    # Exit strategy
    with st.expander("📋 Exit Strategy for this position"):
        st.markdown(get_exit_strategy(entry, stop, target_str, rsi))


# ============================================================
# V36.0 FEATURE 2: ENTRY RANGE EMAIL ALERTS
# ============================================================

def check_entry_range_alerts(watchlist_tickers, threshold=68):
    """
    Checks each watchlist ticker to see if current price has entered the entry range.
    Returns list of alert-worthy signals.
    """
    alerts = []
    alert_history = load_alert_history()
    today = datetime.now(EASTERN).strftime("%Y-%m-%d")

    # Avoid re-alerting the same ticker today
    already_alerted_today = {
        h["tickers"] for h in alert_history
        if h.get("alert_type") == "Entry Range Alert" and h.get("timestamp","")[:10] == today
    }

    for ticker in watchlist_tickers:
        try:
            ticker = normalize_ticker(ticker)
            if ticker in already_alerted_today:
                continue

            data = analyze_ticker(ticker)
            if not data:
                continue

            conviction = float(data.get("Final Conviction") or 0)
            if conviction < threshold:
                continue

            price = float(data.get("Price") or 0)
            entry_str = str(data.get("Entry Range",""))

            # Parse entry range
            try:
                parts = entry_str.replace("$","").replace("Wait for reclaim above","").split(" - ")
                nums = [float(p.strip().split(" ")[0]) for p in parts if p.strip()]
                if len(nums) >= 2:
                    entry_low, entry_high = nums[0], nums[1]
                else:
                    continue
            except Exception:
                continue

            if entry_low <= price <= entry_high:
                alerts.append({
                    "ticker": ticker,
                    "price": price,
                    "entry_range": entry_str,
                    "conviction": conviction,
                    "signal": data.get("Signal",""),
                    "macd_note": data.get("MACD Note",""),
                    "stop": data.get("Stop Loss",""),
                    "target": data.get("Target / Sell Zone",""),
                    "rr": data.get("Risk / Reward",""),
                })
        except Exception:
            continue

    return alerts


def send_entry_range_email(alerts):
    """Sends email alert when watchlist stocks enter their entry zones."""
    if not alerts:
        return False, "No alerts to send."

    subject = f"📈 Entry Zone Alert — {len(alerts)} watchlist stock(s) in buy zone"
    body = "AI Trading Dashboard — Entry Range Alerts\n"
    body += f"Generated: {datetime.now(EASTERN).strftime('%Y-%m-%d %I:%M %p ET')}\n"
    body += "=" * 50 + "\n\n"

    for a in alerts:
        body += f"🟢 {a['ticker']} — ${a['price']:.2f}\n"
        body += f"   Signal: {a['signal']}\n"
        body += f"   Conviction: {a['conviction']:.0f}/100\n"
        body += f"   Entry Range: {a['entry_range']}\n"
        body += f"   Stop Loss: ${a['stop']}\n"
        body += f"   Target: {a['target']}\n"
        body += f"   R/R: {a['rr']}\n"
        body += f"   Timing: {a['macd_note']}\n\n"

    body += "This is an automated alert. Always verify with the full checklist before acting.\n"
    body += "Not financial advice.\n"

    ok, msg = send_email_alert(subject, body)
    if ok:
        for a in alerts:
            log_alert("Entry Range Alert", [a["ticker"]])
    return ok, msg


# ============================================================
# V36.0 FEATURE 3: BACKTESTING ENGINE
# ============================================================

def compute_historical_signal(close_series, high_series, low_series, volume_series, lookback_end_idx):
    """
    Computes what signal the dashboard would have given on a specific historical date.
    Uses the same scoring logic as analyze_ticker but on historical slices.
    Returns (signal_score, signal_label)
    """
    try:
        close = close_series.iloc[:lookback_end_idx]
        high  = high_series.iloc[:lookback_end_idx]
        low   = low_series.iloc[:lookback_end_idx]
        vol   = volume_series.iloc[:lookback_end_idx]

        if len(close) < 60:
            return None, None

        price   = float(close.iloc[-1])
        sma20   = close.rolling(20).mean().iloc[-1]
        sma50   = close.rolling(50).mean().iloc[-1]
        sma200  = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.rolling(min(100, len(close))).mean().iloc[-1]
        rsi_val = float(calc_rsi(close).iloc[-1])
        avg_vol = vol.rolling(20).mean().iloc[-1]
        vol_ratio = float(vol.iloc[-1]) / avg_vol if avg_vol else 1

        from_high = ((price - high.max()) / high.max()) * 100

        trend_score = 0
        if price > sma20:   trend_score += 20
        if price > sma50:   trend_score += 20
        if price > sma200:  trend_score += 20
        if sma20 > sma50:   trend_score += 15
        if 45 <= rsi_val <= 70: trend_score += 15
        if vol_ratio > 1.1: trend_score += 10

        risk_score = 0
        if rsi_val > 75:    risk_score += 25
        if price < sma50:   risk_score += 20
        if price < sma200:  risk_score += 25
        if from_high < -25: risk_score += 15
        if vol_ratio < 0.6: risk_score += 10

        ai_score = max(0, min(100, trend_score - (risk_score * 0.65)))
        return ai_score, price
    except Exception:
        return None, None


@st.cache_data(ttl=86400)
def run_simple_backtest(tickers, lookback_days=504):
    """
    Simulates dashboard signals over the past ~2 years of daily data.
    For each ticker, scans for BUY NOW signals (ai_score >= 75, risk_score < 35)
    and checks actual returns at 5D, 10D, 21D / 1M.
    Returns a DataFrame of all historical signals and outcomes.
    """
    results = []
    spy_hist = get_history("SPY", period="2y")

    for ticker in tickers:
        try:
            ticker = normalize_ticker(ticker)
            hist = get_history(ticker, period="2y")
            if hist.empty or len(hist) < 120:
                continue

            close  = hist["Close"].reset_index(drop=True)
            high   = hist["High"].reset_index(drop=True)
            low    = hist["Low"].reset_index(drop=True)
            volume = hist["Volume"].reset_index(drop=True)
            dates  = hist.index

            # Scan every 5 trading days (avoid overcrowding)
            scan_indices = list(range(60, len(close) - 30, 5))

            for idx in scan_indices:
                ai_score, price = compute_historical_signal(close, high, low, volume, idx)
                if ai_score is None or price is None:
                    continue

                # Only log BUY NOW equivalent signals
                if ai_score < 70:
                    continue

                signal_date = dates[idx]

                # Actual future returns
                ret_5d  = ((float(close.iloc[min(idx+5,  len(close)-1)]) - price) / price * 100) if idx+5  < len(close) else None
                ret_10d = ((float(close.iloc[min(idx+10, len(close)-1)]) - price) / price * 100) if idx+10 < len(close) else None
                ret_21d_1m = ((float(close.iloc[min(idx+21, len(close)-1)]) - price) / price * 100) if idx+21 < len(close) else None

                # SPY return over same window (benchmark)
                try:
                    spy_close = spy_hist["Close"]
                    spy_idx = spy_close.index.searchsorted(signal_date)
                    spy_price = float(spy_close.iloc[spy_idx])
                    spy_5d = ((float(spy_close.iloc[min(spy_idx+5, len(spy_close)-1)]) - spy_price) / spy_price * 100) if spy_idx+5 < len(spy_close) else None
                except Exception:
                    spy_5d = None

                results.append({
                    "Ticker":       ticker,
                    "Signal Date":  str(signal_date)[:10],
                    "Price at Signal": round(price, 2),
                    "AI Score":     round(ai_score, 0),
                    "Signal":       "🟢 BUY NOW" if ai_score >= 75 else "🟡 Watch",
                    "5D Return %":  round(ret_5d,  2) if ret_5d  is not None else None,
                    "10D Return %": round(ret_10d, 2) if ret_10d is not None else None,
                    "21D / 1M Return %": round(ret_21d_1m, 2) if ret_21d_1m is not None else None,
                    "5D vs SPY %":  round(ret_5d - spy_5d, 2) if ret_5d is not None and spy_5d is not None else None,
                    "5D Win":       "✅ Win" if ret_5d  is not None and ret_5d  > 0 else ("❌ Loss" if ret_5d  is not None else None),
                    "10D Win":      "✅ Win" if ret_10d is not None and ret_10d > 0 else ("❌ Loss" if ret_10d is not None else None),
                    "21D / 1M Win":      "✅ Win" if ret_21d_1m is not None and ret_21d_1m > 0 else ("❌ Loss" if ret_21d_1m is not None else None),
                })
        except Exception:
            continue

    return pd.DataFrame(results) if results else pd.DataFrame()


def render_simple_backtest_summary(df):
    """Renders simple_backtest results with win rates, avg returns, and best/worst signals."""
    if df is None or df.empty:
        st.info("No simple_backtest results. Run the simple_backtest above.")
        return

    total_signals = len(df)
    st.markdown(f"**{total_signals} historical signals scanned across selected tickers**")

    # Win rates
    for period, col_win, col_ret in [("5D","5D Win","5D Return %"),("10D","10D Win","10D Return %"),("21D / 1M","21D / 1M Win","21D / 1M Return %")]:
        resolved = df[df[col_win].notna()]
        if resolved.empty:
            continue
        wins     = (resolved[col_win] == "✅ Win").sum()
        total    = len(resolved)
        win_rate = wins / total * 100
        avg_ret  = resolved[col_ret].mean()
        color    = "🟢" if win_rate >= 55 else "🟡" if win_rate >= 45 else "🔴"
        st.metric(
            f"{color} {period} Win Rate",
            f"{win_rate:.1f}%",
            f"{wins}/{total} signals | avg {avg_ret:+.2f}%"
        )

    st.markdown("---")

    # Best performers
    modern_section("🏆 Best Performing Signals (5D)")
    best = df.nlargest(10, "5D Return %")[["Ticker","Signal Date","Price at Signal","AI Score","5D Return %","10D Return %","21D / 1M Return %","5D vs SPY %"]]
    st.dataframe(best, use_container_width=True, hide_index=True)

    # Worst performers
    modern_section("⚠️ Worst Performing Signals (5D)")
    worst = df.nsmallest(10, "5D Return %")[["Ticker","Signal Date","Price at Signal","AI Score","5D Return %","10D Return %","21D / 1M Return %","5D vs SPY %"]]
    st.dataframe(worst, use_container_width=True, hide_index=True)

    # Per-ticker breakdown
    modern_section("📊 Per-Ticker Win Rate Breakdown")
    ticker_stats = []
    for ticker, group in df.groupby("Ticker"):
        resolved = group[group["5D Win"].notna()]
        if len(resolved) < 2:
            continue
        wins = (resolved["5D Win"] == "✅ Win").sum()
        ticker_stats.append({
            "Ticker": ticker,
            "Signals": len(resolved),
            "5D Win Rate": f"{wins/len(resolved)*100:.0f}%",
            "Avg 5D Return": f"{resolved['5D Return %'].mean():+.2f}%",
            "Avg 21D / 1M Return": f"{resolved['21D / 1M Return %'].mean():+.2f}%" if resolved["21D / 1M Return %"].notna().any() else "N/A",
            "Best Trade": f"{resolved['5D Return %'].max():+.2f}%",
            "Worst Trade": f"{resolved['5D Return %'].min():+.2f}%",
        })
    if ticker_stats:
        stats_df = pd.DataFrame(ticker_stats).sort_values("5D Win Rate", ascending=False)
        st.dataframe(stats_df, use_container_width=True, hide_index=True)

    # Full log
    with st.expander("📋 Full Signal Log"):
        st.dataframe(df.sort_values("Signal Date", ascending=False), use_container_width=True, hide_index=True)

        if st.download_button("⬇️ Download Simple Backtest CSV", df.to_csv(index=False).encode(), "simple_backtest_results.csv", "text/csv"):
            pass


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("📈 AI Trading Dashboard")
st.sidebar.caption("V36.0 — Exit Signals · Simple Backtesting · Entry Alerts · Trade Health")
role_label = "Admin" if is_admin() else "View Only"
st.sidebar.success(f"Logged in as: {role_label}")
if alpaca_client: st.sidebar.success("🟢 Alpaca: Connected")
else: st.sidebar.info("🟡 Data: Yahoo Finance")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False; st.session_state.user_role = None; st.rerun()
show_last_refresh()

st.sidebar.markdown("### Navigation")
pages = ["Home","Scanner","Watchlist","Paper Trades","Simple Backtest","Settings & Logs","Detail View"]
requested_page = st.session_state.pop("nav_override", None) or get_query_param_value("page", None)
default_page_index = pages.index(requested_page) if requested_page in pages else 0
nav_page = st.sidebar.radio("Go to", pages, index=default_page_index)
page = nav_page
if nav_page == "Home":           page = "Dashboard"
elif nav_page == "Scanner":      page = "Scanner Hub"
elif nav_page == "Paper Trades": page = "Paper Trading"
elif nav_page == "Simple Backtest":     page = "Simple Backtest"

st.sidebar.markdown("### Refresh")
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear(); st.rerun()
auto_refresh = st.sidebar.toggle("🔄 Auto Refresh (60s)", value=False)
if auto_refresh:
    if st_autorefresh: st_autorefresh(interval=60_000, key="v33f_autorefresh")
    else: st.sidebar.warning("Add streamlit-autorefresh to requirements.txt")

st.sidebar.markdown("### Watchlist Quick Add")
if is_admin():
    quick_ticker = st.sidebar.text_input("Ticker", placeholder="NVDA", key="sidebar_add_ticker")
    if st.sidebar.button("Add to Watchlist"):
        t = normalize_ticker(quick_ticker)
        if not t: st.sidebar.warning("Enter a ticker.")
        elif t in st.session_state.watchlist: st.sidebar.info(f"{t} already in watchlist.")
        else:
            st.session_state.watchlist.append(t); save_watchlist()
            st.sidebar.success(f"Added {t}"); st.rerun()
else:
    st.sidebar.info("View-only: watchlist editing disabled.")

# ============================================================
# MAIN APP + ADAPTIVE THRESHOLD INIT
# ============================================================


# ============================================================
# MORNING BRIEFING
# ============================================================

def build_morning_briefing(scan_df, recovery_df=None, etf_df=None):
    """Beginner-friendly daily briefing summarizing market, best setups, and risks."""
    regime_key, regime_label, regime_note = get_market_regime()
    vol_mult, vol_label, vol_note = get_market_volatility_regime()
    sectors = get_sector_performance()

    lines = []
    lines.append(f"**Market Regime:** {regime_label} — {regime_note}")
    lines.append(f"**Volatility:** {vol_label} — {vol_note}")

    if sectors:
        top = list(sectors.items())[:3]
        bottom = list(sectors.items())[-3:]
        lines.append("**Leading sectors:** " + ", ".join([f"{s} ({p:+.1f}%)" for s, p in top]))
        lines.append("**Weak sectors:** " + ", ".join([f"{s} ({p:+.1f}%)" for s, p in bottom]))

    if scan_df is not None and not scan_df.empty:
        threshold = st.session_state.get("adaptive_threshold", 68)
        candidates = scan_df[scan_df["Final Conviction"].fillna(0) >= threshold] if "Final Conviction" in scan_df.columns else scan_df.head(0)
        if not candidates.empty:
            names = candidates.head(5)["Ticker"].tolist()
            lines.append(f"**Top watchlist today:** {', '.join(names)}")
            lines.append("These are not automatic buys. Use the trade checklist, valuation section, cash-flow section, and position-size calculator before acting.")
        else:
            lines.append("**Top watchlist today:** No names currently clear the adaptive threshold. Patience may be better than forcing a trade.")

    if recovery_df is not None and not recovery_df.empty:
        rec_names = recovery_df.head(5)["Ticker"].tolist()
        lines.append(f"**Recovery setups to monitor:** {', '.join(rec_names)}")

    if regime_key == "bear":
        lines.append("**Risk note:** Bear market conditions mean smaller position sizes, tighter selectivity, and fewer trades.")
    elif regime_key == "neutral":
        lines.append("**Risk note:** Neutral conditions favor starter positions instead of full-sized entries.")
    else:
        lines.append("**Risk note:** Bullish backdrop supports momentum, but still avoid chasing overextended entries.")

    return "\n\n".join(lines)


def render_morning_briefing(scan_df, recovery_df=None, etf_df=None):
    modern_section("🌅 Morning Briefing", "A plain-English summary of today’s market backdrop, top setups, and risk controls.")
    st.markdown(build_morning_briefing(scan_df, recovery_df, etf_df))


modern_hero(
    "📈 AI Trading Dashboard V36.0",
    "9 Agents · Fundamentals · Exit signals · Simple Backtesting · Entry alerts · Trade health monitor"
)
st.caption("V36.0 — Exit signals, simple_backtesting, entry range email alerts, and trade health monitoring added. Not financial advice.")

_log_for_threshold = load_signal_log()
_threshold, _threshold_note = get_adaptive_conviction_threshold(_log_for_threshold)
st.session_state["adaptive_threshold"] = _threshold

# ============================================================
# PAGES — clean 6-branch router
# ============================================================

if page == "Dashboard":
    market_status, market_note = get_market_status()
    market_regime, regime_label, regime_note = get_market_regime()
    vol_mult, vol_label, vol_note = get_market_volatility_regime()
    sector_perf = get_sector_performance()

    show_market_status_banner()
    show_market_regime_banner()

    now_et = datetime.now(EASTERN)
    if "Open" not in market_status and now_et.hour < 9:
        modern_section("☀️ Pre-Market Setup", "Plan your day before the open.")
        st.caption("Markets open at 9:30 AM ET. Use this time to identify top signals and set your plan. Avoid entering in the first 15 minutes after open.")
    elif "Open" in market_status:
        modern_section("⚡ Live Opportunities", "Market is open — confirm MACD and check your checklist before acting.")
        st.caption("Focus on signals showing ✅ MACD confirmed and 🟢 Strong Setup rating. Avoid entering between 9:30–9:45 AM and 3:45–4:00 PM.")
    else:
        modern_section("🌙 After Hours Review", "Plan for tomorrow's session.")
        st.caption("Review today's signals, update paper trades, and prepare your watchlist for tomorrow.")

    if is_admin(): st.success("Admin mode active.")
    else: st.info("View-only mode.")

    broad_scan_df = build_scan(CORE_SCAN_TICKERS, diversified=False, sector_diverse=False, min_conviction=45)
    scan_df = build_scan(CORE_SCAN_TICKERS, diversified=True, sector_diverse=False, min_conviction=50)
    top_source_df = broad_scan_df if not broad_scan_df.empty else scan_df
    log = load_signal_log(); threshold, threshold_note = get_adaptive_conviction_threshold(log)
    buy_count = int(scan_df["Signal"].str.contains("BUY NOW", na=False).sum()) if not scan_df.empty else 0
    macd_confirmed = int(scan_df["MACD Bullish"].sum()) if not scan_df.empty and "MACD Bullish" in scan_df.columns else 0

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Market", regime_label.split(" ",1)[-1] if " " in regime_label else regime_label)
    c2.metric("Volatility", vol_label.split(" ",1)[-1] if " " in vol_label else vol_label)
    c3.metric("BUY NOW Signals", buy_count)
    c4.metric("MACD Confirmed", macd_confirmed)
    c5.metric("Adaptive Threshold", threshold)

    modern_section("🟢 Today's Top Signals")
    if not scan_df.empty:
        top = scan_df[scan_df["Signal"].str.contains("BUY NOW", na=False)].head(6)
        if top.empty: st.info("No BUY NOW signals right now. Check Scanner for Watch candidates.")
        else: render_signal_cards(top, limit=25, show_checklist=False)
    else: st.info("Loading scanner data...")

    if sector_perf:
        modern_section("📊 Sector Rotation — 30 Day Performance")
        sec_cols = st.columns(min(len(sector_perf),4))
        for i,(sector,ret) in enumerate(list(sector_perf.items())[:4]):
            sec_cols[i].metric(sector, f"{ret:+.1f}%", delta_color="normal" if ret >= 0 else "inverse")
        st.caption("Signals in the top-performing sectors tend to have stronger momentum backing.")

    modern_section("🔥 Recovery Radar Snapshot")
    recovery_df = build_recovery_radar(RECOVERY_TICKERS)
    if not recovery_df.empty: render_clickable_table(recovery_df.head(5), "Ticker", table_id="dash_recovery")
    else: st.info("No recovery candidates.")


elif page == "Scanner Hub":
    show_market_status_banner(); show_market_regime_banner()
    modern_section("🔎 Scanner Hub", "Signal cards · All scanner · Recovery · ETF timing")
    log = load_signal_log(); threshold, threshold_note = get_adaptive_conviction_threshold(log)
    st.caption(f"📊 Adaptive conviction threshold: **{threshold}** — {threshold_note}")
    top_source_df = build_scan(CORE_SCAN_TICKERS, diversified=False, sector_diverse=False, min_conviction=45)
    scan_df = build_scan(CORE_SCAN_TICKERS)
    recovery_df = build_recovery_radar(RECOVERY_TICKERS)
    etf_df = build_scan(ETF_TICKERS, diversified=False)

    tab0,tab1,tab2,tab3,tab4 = st.tabs(["🧭 Categories","🟢 Signal Cards","📋 All Scanner","🔥 Recovery Radar","📊 ETF Timing"])

    with tab0:
        modern_section("🧭 Opportunity Categories", "Broader choices grouped by investment style so you are not limited to the same expensive names.")
        show_opportunity_category_tabs(scan_df)

    with tab1:
        modern_section("BUY NOW / High Conviction — with Checklists")
        st.caption("Top Signals now uses the broad scan and shows more choices, including company names. Use Add Watch to save promising names to your watchlist. Category tabs still group/diversify names separately.")
        if not scan_df.empty:
            buy_df = top_source_df[(scan_df["Signal"].astype(str).str.contains("BUY NOW",na=False)) | (scan_df["Final Conviction"].fillna(0) >= max(55, threshold - 10))] if "Final Conviction" in scan_df.columns else scan_df[scan_df["Signal"].astype(str).str.contains("BUY NOW",na=False)]
            if buy_df.empty:
                st.info("No signals above the adaptive threshold right now.")
            else:
                show_sector_concentration_warning(buy_df)
                added = auto_log_signals(buy_df, threshold=threshold)
                if added and added > 0: st.caption(f"📝 {added} new signal(s) logged for accuracy tracking.")
                mobile_view = st.toggle("📱 Mobile Summary", value=False, key="scanner_mobile")
                show_cl = st.toggle("✅ Show Trade Checklists", value=True, key="scanner_show_checklist")
                if mobile_view: render_mobile_signal_summary(buy_df)
                else: render_signal_cards(buy_df, limit=50, show_checklist=show_cl)
        else: st.info("No scanner data.")

    with tab2:
        modern_section("All Scanner Results")
        if not scan_df.empty: render_clickable_table(scan_df, "Ticker", table_id="scanner_all")
        else: st.info("No scanner data.")

    with tab3:
        modern_section("Recovery Radar")
        if not recovery_df.empty: render_clickable_table(recovery_df, "Ticker", table_id="scanner_recovery")
        else: st.info("No recovery candidates.")

    with tab4:
        modern_section("ETF Timing")
        if not etf_df.empty: render_clickable_table(etf_df, "Ticker", table_id="scanner_etf")
        else: st.info("No ETF data.")


elif page == "Watchlist":
    modern_section("⭐ Persistent Watchlist")
    if is_admin():
        st.success(f"Saved to: {WATCHLIST_FILE}")
        add_col,reset_col = st.columns([3,1])
        with add_col: new_ticker = st.text_input("Add ticker", placeholder="AAPL, NVDA", key="watchlist_add")
        with reset_col:
            st.write(""); st.write("")
            if st.button("Reset Default"):
                st.session_state.watchlist = DEFAULT_WATCHLIST.copy(); save_watchlist(); st.rerun()
        if st.button("➕ Add"):
            t = normalize_ticker(new_ticker)
            if not t: st.warning("Enter a ticker.")
            elif t in st.session_state.watchlist: st.info(f"{t} already in watchlist.")
            else:
                st.session_state.watchlist.append(t); save_watchlist(); st.success(f"Added {t}"); st.rerun()
    else: st.info("View-only: editing disabled.")

    modern_section("Current Watchlist")
    if not st.session_state.watchlist: st.info("Watchlist is empty.")
    else:
        for ticker in list(st.session_state.watchlist):
            if is_admin():
                c1,c2,c3 = st.columns([2,2,1])
                c1.write(f"**{ticker}**"); c2.link_button("Open Yahoo", f"https://finance.yahoo.com/quote/{ticker}")
                if c3.button("Remove", key=f"remove_{ticker}"):
                    st.session_state.watchlist.remove(ticker); save_watchlist(); st.rerun()
            else:
                c1,c2 = st.columns([2,2]); c1.write(f"**{ticker}**")
                c2.link_button("Open Yahoo", f"https://finance.yahoo.com/quote/{ticker}")
        modern_section("Watchlist Analysis")
        render_clickable_table(build_scan(st.session_state.watchlist), "Ticker", table_id="watchlist_analysis")


elif page == "Paper Trading":
    modern_section("🧾 Paper Trading", "Track practice trades. Validate signals before real capital.")

    # ── Entry Range Alert Check ──────────────────────────────
    modern_section("🔔 Entry Range Alerts", "Check if any watchlist stocks have entered their buy zone.")
    col_al1, col_al2 = st.columns([2,3])
    with col_al1:
        if st.button("🔍 Check Watchlist Entry Zones"):
            with st.spinner("Checking entry zones..."):
                log = load_signal_log()
                threshold, _ = get_adaptive_conviction_threshold(log)
                alerts = check_entry_range_alerts(st.session_state.watchlist, threshold=threshold)
            if alerts:
                st.success(f"🟢 {len(alerts)} watchlist stock(s) are in their entry zone right now!")
                for a in alerts:
                    st.markdown(f"""
                    **{a['ticker']}** @ ${a['price']:.2f} — {a['signal']}
                    Entry: {a['entry_range']} | Stop: ${a['stop']} | Target: {a['target']} | R/R: {a['rr']}
                    {a['macd_note']}
                    """)
                if is_admin():
                    if st.button("📧 Send Entry Alert Email"):
                        ok, msg = send_entry_range_email(alerts)
                        st.success(msg) if ok else st.error(msg)
            else:
                st.info("No watchlist stocks are currently in their entry zone.")
    with col_al2:
        st.caption("This checks each ticker on your watchlist against its current entry range. Only stocks with high conviction are flagged. An email alert is sent once per stock per day if configured.")

    st.markdown("---")

    # ── Add New Trade ────────────────────────────────────────
    if is_admin():
        modern_section("➕ Log a Paper Trade")
        c1,c2,c3,c4 = st.columns(4)
        pt_ticker = c1.text_input("Ticker", placeholder="NVDA")
        pt_price  = c2.number_input("Entry Price", min_value=0.0, step=0.01)
        pt_qty    = c3.number_input("Shares", min_value=0.0, step=1.0)
        pt_stop   = c4.number_input("Stop Loss", min_value=0.0, step=0.01)
        if st.button("Add Paper Trade"):
            t = normalize_ticker(pt_ticker)
            if not t or pt_price <= 0 or pt_qty <= 0:
                st.warning("Enter ticker, price, and shares.")
            else:
                st.session_state.paper_trades.append({
                    "Ticker":t,"Entry Price":pt_price,"Shares":pt_qty,
                    "Stop Loss":pt_stop if pt_stop > 0 else None,
                    "Date":datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M %p ET")
                })
                save_paper_trades(); st.success(f"Added {t}"); st.rerun()
    else:
        st.info("View-only: editing disabled.")

    # ── Open Trades with Health Monitor ─────────────────────
    trades = st.session_state.paper_trades
    if not trades:
        st.info("No paper trades yet. Log signals from the Scanner, paper trade them seriously, then check accuracy after 5-10 trading days.")
    else:
        modern_section("📊 Open Positions — Portfolio Overview")
        rows = []; total_at_risk = 0
        trade_data_cache = {}
        for i, trade in enumerate(trades):
            ticker  = trade["Ticker"]
            data    = analyze_ticker(ticker)
            trade_data_cache[i] = data
            current = data["Price"] if data else None
            entry   = trade["Entry Price"]; shares = trade["Shares"]
            pnl     = ((current - entry) * shares) if current else None
            pnl_pct = ((current - entry) / entry * 100) if current and entry else None
            stop    = trade.get("Stop Loss")
            stop_status = "⚪ No stop" if not stop or not current else ("🔴 Stop breached" if current < stop else "🟢 Above stop")
            risk_on_trade = (entry - stop) * shares if stop and stop > 0 else 0
            total_at_risk += max(0, risk_on_trade)
            rows.append({
                "ID":i,"Ticker":ticker,"Entry Price":entry,"Current Price":current,"Shares":shares,
                "Stop Loss":stop,"Stop Status":stop_status,
                "P/L $":safe_round(pnl),"P/L %":safe_round(pnl_pct),"Date":trade["Date"],
            })

        trade_df = pd.DataFrame(rows)
        st.dataframe(trade_df, column_config=build_column_config(trade_df), use_container_width=True, hide_index=True)

        total_pnl = sum(r["P/L $"] for r in rows if r["P/L $"] is not None)
        breached  = sum(1 for r in rows if r["Stop Status"] == "🔴 Stop breached")
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total P/L", f"${total_pnl:,.2f}", delta_color="normal" if total_pnl >= 0 else "inverse")
        m2.metric("Capital at Risk", f"${total_at_risk:,.2f}")
        m3.metric("Open Positions", len(trades))
        m4.metric("Stop Breaches", breached, delta_color="inverse" if breached > 0 else "normal")

        if breached > 0:
            st.error(f"⚠️ {breached} position(s) have breached their stop loss. Exit or reassess immediately.")

        # ── Per-trade health monitors ────────────────────────
        modern_section("🩺 Trade Health Monitor", "Real-time status and exit guidance for each open position.")
        st.caption("Updated each time you load this page. Gives you a plain-English read on whether to hold, tighten, or exit each trade.")

        for i, trade in enumerate(trades):
            ticker = trade["Ticker"]
            data   = trade_data_cache.get(i)
            entry  = trade["Entry Price"]
            stop   = trade.get("Stop Loss", 0) or 0
            target = str(data.get("Target / Sell Zone","")) if data else ""
            current= data["Price"] if data else None
            pnl_pct= ((current - entry) / entry * 100) if current and entry else None

            with st.expander(f"**{ticker}** — Entry ${entry:.2f} | Current ${current:.2f if current else 0:.2f} ({pnl_pct:+.1f}%)" if current and pnl_pct is not None else f"**{ticker}** — Entry ${entry:.2f}"):
                render_trade_health_monitor(trade, data)

        # ── Remove trade ─────────────────────────────────────
        if is_admin():
            st.markdown("---")
            remove_id = st.number_input("Remove trade ID", min_value=0, max_value=max(0,len(trades)-1), step=1)
            if st.button("Remove Paper Trade"):
                try:
                    st.session_state.paper_trades.pop(int(remove_id))
                    save_paper_trades(); st.rerun()
                except Exception:
                    st.error("Could not remove trade.")

    render_position_calculator()


elif page == "Simple Backtest":
    modern_section("📈 Simple Backtesting Engine", "Simulate how the dashboard's signals would have performed over the past 2 years.")
    st.caption(
        "This runs the same scoring rules against historical price data to show hypothetical signal performance. "
        "It does not guarantee future results, but reveals whether the scoring logic has historically had edge."
    )

    with st.expander("ℹ️ How this works", expanded=False):
        st.markdown("""
**What the simple_backtest does:**
- Scans each selected ticker every 5 trading days over the past ~2 years
- Applies the same AI Score formula used in the live scanner
- Records every signal where AI Score ≥ 70 (equivalent to a BUY NOW / high-conviction signal)
- Checks actual price returns at 5, 10, and 30 trading days after the signal
- Compares 5D return vs SPY (to measure alpha, not just market beta)

**What a good result looks like:**
- 5D win rate above 55% — signals are directionally correct more often than not
- Positive average 5D return — profitable on average even accounting for losses
- Positive vs SPY — the signals beat just holding the index

**Limitations:**
- No slippage, fees, or taxes are modeled
- Signals are computed end-of-day — intraday entries may be different
- Past performance doesn't guarantee future results
- The adaptive threshold and MACD confirmation layers were not applied (they require live market data)
        """)

    # Ticker selection
    bt_options = st.radio("Scan which tickers?", ["Watchlist Only", "Core Scanner (Top 30)", "Full Core Scanner"], horizontal=True, key="bt_scope")

    if bt_options == "Watchlist Only":
        bt_tickers = st.session_state.watchlist
    elif bt_options == "Core Scanner (Top 30)":
        bt_tickers = CORE_SCAN_TICKERS[:30]
    else:
        bt_tickers = CORE_SCAN_TICKERS

    st.caption(f"Will scan {len(bt_tickers)} tickers. More tickers = longer runtime (cached for 24 hours after first run).")

    if st.button("🚀 Run Simple Backtest", type="primary"):
        with st.spinner(f"Running simple_backtest across {len(bt_tickers)} tickers over ~2 years of data. This may take 60-90 seconds on first run..."):
            bt_df = run_simple_backtest(tuple(bt_tickers))
        if bt_df.empty:
            st.warning("No signals found. Try expanding the ticker scope.")
        else:
            st.success(f"✅ Simple Backtest complete — {len(bt_df)} historical signals found.")
            render_simple_backtest_summary(bt_df)
    else:
        st.info("Click 'Run Simple Backtest' to simulate historical signal performance. Results are cached for 24 hours.")

        # Show any previously cached results
        try:
            cached = run_simple_backtest(tuple(bt_tickers))
            if not cached.empty:
                st.caption("Showing cached results from previous run:")
                render_simple_backtest_summary(cached)
        except Exception:
            pass


elif page == "Settings & Logs":
    modern_section("⚙️ Settings & Logs")
    tab1,tab2,tab3 = st.tabs(["Signal Accuracy","Alert History","Email & Diagnostics"])

    with tab1:
        modern_section("📈 Signal Accuracy Engine")
        if st.button("🔄 Update Signal Outcomes", key="update_outcomes"):
            with st.spinner("Fetching outcomes..."): log = check_signal_outcomes()
            st.success("Outcomes updated.")
        else: log = load_signal_log()
        threshold, threshold_note = get_adaptive_conviction_threshold(log)
        st.info(f"📊 Adaptive threshold: **{threshold}** — {threshold_note}")
        stats = get_accuracy_stats(log); patterns = get_weak_signal_patterns(log)
        if patterns:
            modern_section("📋 Pattern Insights")
            for p in patterns: st.info(p)
        if stats:
            cols = st.columns(len(stats))
            for i,(period,s) in enumerate(stats.items()):
                color = "🟢" if s["win_rate"] >= 55 else "🟡" if s["win_rate"] >= 45 else "🔴"
                cols[i].metric(f"{color} {period} Win Rate", f"{s['win_rate']}%", f"{s['wins']}/{s['total']} | avg {s['avg_return']:+.2f}%")
            st.caption("Target: >55% win rate at 5D with positive avg return before trading real capital.")
        else: st.info("No resolved signals yet. Visit the Scanner daily to build up signal history.")
        if log:
            modern_section("Signal Log")
            log_df = pd.DataFrame(log)
            show_cols = [c for c in ["ticker","date","signal","conviction","entry_price","stop_loss","risk_reward","outcome_1d","pct_1d","outcome_5d","pct_5d","outcome_10d","pct_10d"] if c in log_df.columns]
            st.dataframe(log_df[show_cols].sort_values("date", ascending=False), use_container_width=True, hide_index=True)
            if is_admin():
                if st.button("🗑 Clear Signal Log"): save_signal_log([]); st.success("Cleared."); st.rerun()

    with tab2:
        modern_section("📜 Alert History")
        history = load_alert_history()
        if not history: st.info("No alerts yet.")
        else: st.dataframe(pd.DataFrame(history).sort_index(ascending=False), use_container_width=True, hide_index=True)

    with tab3:
        modern_section("📧 Email & Diagnostics")
        if not is_admin(): st.warning("Admin only.")
        else:
            st.write(f"EMAIL_SENDER: {'✅' if os.getenv('EMAIL_SENDER','') else '❌'}")
            st.write(f"EMAIL_PASSWORD: {'✅' if os.getenv('EMAIL_PASSWORD','') else '❌'}")
            st.write(f"EMAIL_RECIPIENTS: {'✅' if os.getenv('EMAIL_RECIPIENTS','') else '❌'}")
            st.write(f"Alpaca: {ALPACA_STATUS}")
            if st.button("Send Test Email"):
                ok,msg = send_email_alert("AI Dashboard V36.0 Test", f"Test from V36.0 at {datetime.now(EASTERN)}")
                st.success(msg) if ok else st.error(msg)


elif page == "Detail View":
    query_ticker = normalize_ticker(str(st.session_state.get("selected_detail_ticker", "") or get_query_param_value("ticker", "")))
    detail_options = list(st.session_state.watchlist)

    if query_ticker and query_ticker not in detail_options:
        detail_options.insert(0, query_ticker)

    default_detail_ticker = query_ticker or (detail_options[0] if detail_options else "NVDA")

    if query_ticker:
        st.caption(f"Opened from signal card: {query_ticker}")

    modern_section("🔎 Detail View", "Full single-stock analysis: chart · 9 agents · fundamental deep-dive · checklist · position sizing.")
    selected = st.text_input("Enter ticker", value=default_detail_ticker, key="detail_ticker_input")
    selected = normalize_ticker(selected)

    if selected:
        st.session_state.selected_detail_ticker = selected
        detail_page(selected)


st.markdown("---")
st.caption("Not financial advice. Use for research and paper-trading validation only. | AI Trading Dashboard V36.0")
