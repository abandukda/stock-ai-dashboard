
import os
import json
import urllib.request
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st


APP_VERSION = "V40.5 Cleaner Layout + 30% Upside Filter"

st.set_page_config(
    page_title=f"AI Trading Dashboard {APP_VERSION}",
    page_icon="📈",
    layout="wide",
)

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
MIN_UPSIDE_PCT = float(os.getenv("MIN_UPSIDE_PCT", "0.30"))

FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
PRESCREEN_FILE = DATA_DIR / "market_prescreen.json"
SCAN_STATE_FILE = DATA_DIR / "market_scan_state.json"
UNIVERSE_FILE = DATA_DIR / "total_market_universe.json"
TOP_IDEAS_FILE = DATA_DIR / "top_ai_ideas.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
WATCHLIST_SCAN_FILE = DATA_DIR / "watchlist_scan.json"
RECOVERY_SCAN_FILE = DATA_DIR / "recovery_scan.json"

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
    "PLTR", "SOFI", "AVGO", "CRWD", "PANW"
]


def first_env(*names, default=""):
    for name in names:
        value = os.getenv(name)
        if value not in [None, ""]:
            return value
    return default


ADMIN_USER = first_env("ADMIN_USER", "APP_USERNAME", "APP_USER", "USERNAME", "LOGIN_USER", default="admin")
ADMIN_PASSWORD = first_env("ADMIN_PASSWORD", "APP_PASSWORD", "PASSWORD", "LOGIN_PASSWORD", default="admin")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")



def read_json_safe(path, default):
    try:
        p = Path(path)
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def write_json_safe(path, data):
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        st.error(f"Could not save file: {e}")
        return False


def normalize_ticker(value):
    return str(value or "").strip().upper().replace("$", "")


def safe_number(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            if cleaned in ["", "N/A", "None", "nan", "NaN", "$None"]:
                return default
            return float(cleaned)
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def money(value):
    try:
        if value is None or pd.isna(value):
            return "N/A"
        return f"${float(value):,.2f}"
    except Exception:
        return "N/A"


def compact_money(value):
    try:
        value = float(value)
        sign = "-" if value < 0 else ""
        value = abs(value)
        if value >= 1_000_000_000_000:
            return f"{sign}${value/1_000_000_000_000:.1f}T"
        if value >= 1_000_000_000:
            return f"{sign}${value/1_000_000_000:.1f}B"
        if value >= 1_000_000:
            return f"{sign}${value/1_000_000:.1f}M"
        return f"{sign}${value:,.0f}"
    except Exception:
        return "N/A"


def pick(row, *names, default=None):
    for name in names:
        if name in row:
            value = row.get(name)
            if value not in [None, "", "N/A", "None", "nan", "$None"]:
                return value
    return default


def price_bucket(price):
    p = safe_number(price)
    if p is None:
        return "Unknown"
    if 5 <= p <= 25:
        return "$5–$25"
    if 25 < p <= 100:
        return "$25–$100"
    if p > 100:
        return "$100+"
    return "Under $5"



def parse_money_value(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).replace("$", "").replace(",", "").strip()
        if " - " in text:
            parts = [p.strip() for p in text.split(" - ") if p.strip()]
            nums = []
            for part in parts:
                try:
                    nums.append(float(part.replace("$", "").replace(",", "")))
                except Exception:
                    pass
            return sum(nums) / len(nums) if nums else None
        return float(text)
    except Exception:
        return None


def target_upside_pct_from_values(price, target):
    p = safe_number(price)
    t = parse_money_value(target)
    if not p or not t or p <= 0:
        return None
    return ((t - p) / p) * 100


def qualifies_upside(row, min_pct=None):
    min_pct = MIN_UPSIDE_PCT * 100 if min_pct is None else min_pct
    upside = safe_number(row.get("Target Upside %"))
    if upside is None:
        upside = target_upside_pct_from_values(row.get("Price"), row.get("Target"))
    if upside is None:
        return False
    return upside >= min_pct


def login_gate():
    if st.session_state.get("authenticated"):
        return True

    st.title("🔐 AI Trading Dashboard Login")
    st.caption(APP_VERSION)

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        if username == ADMIN_USER and password == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid login. Check Render environment variables.")

    return False


def normalize_rows(raw_data):
    if not raw_data:
        return pd.DataFrame()

    if isinstance(raw_data, dict):
        raw_data = raw_data.get("rows", raw_data.get("data", raw_data.get("symbols", [])))

    if not isinstance(raw_data, list):
        return pd.DataFrame()

    rows = []
    for raw in raw_data:
        if not isinstance(raw, dict):
            continue

        ticker = normalize_ticker(pick(raw, "Ticker", "ticker", "symbol", default=""))
        if not ticker:
            continue

        price = safe_number(pick(raw, "Price", "price", "current_price", "last_price", default=None))
        score = safe_number(
            pick(raw, "Final Conviction", "conviction", "conviction_score", "score", "ai_score", "final_agent_score", default=0),
            0,
        )

        setup = pick(raw, "Setup Type", "setup_type", "bucket", "Investment Style", default="AI Setup")
        guidance = pick(raw, "AI Trade Plan", "ai_reasoning", "ai_guidance", "guidance", "summary", "Research Summary", default="")
        why = pick(raw, "Why Ranked Highly", "why_ranked_high", default=guidance)

        row = {
            "Ticker": ticker,
            "Company": pick(raw, "Company Name", "company_name", "company", "name", default=ticker),
            "Price": price,
            "Final Conviction": score,
            "Setup Type": setup,
            "Decision Rating": pick(raw, "Decision Rating", "decision_rating", "financial_safety", "Financial Safety", default="Needs Review"),
            "Price Bucket": price_bucket(price),
            "Sector": pick(raw, "Sector", "sector", default="Unknown"),
            "Industry": pick(raw, "Industry", "industry", default="Unknown"),
            "Market Cap": pick(raw, "Market Cap", "market_cap", default=None),
            "RSI": pick(raw, "RSI", "rsi", default="N/A"),
            "20D %": pick(raw, "20D %", "twenty_day_pct", default="N/A"),
            "60D %": pick(raw, "60D %", "sixty_day_pct", default="N/A"),
            "Volume Ratio": pick(raw, "Volume Ratio", "volume_ratio", default="N/A"),
            "Dollar Volume": safe_number(pick(raw, "Dollar Volume", "dollar_volume", default=0), 0),
            "Entry Range": pick(raw, "Entry Range", "entry_range", default="N/A"),
            "Stop Loss": pick(raw, "Stop Loss", "stop_loss", default="N/A"),
            "Target": pick(raw, "Target / Sell Zone", "target", "target_2", default="N/A"),
            "Target Upside %": pick(raw, "Target Upside %", "target_upside_pct", "upside_pct", default=None),
            "Risk/Reward": pick(raw, "Risk/Reward", "risk_reward", default="N/A"),
            "Why Ranked Highly": why or "No ranking explanation available.",
            "What Looks Good": pick(raw, "What Looks Good", "what_looks_good", default="Needs confirmation."),
            "What Could Go Wrong": pick(raw, "What Could Go Wrong", "what_could_go_wrong", default="Market weakness or failed follow-through."),
            "AI Trade Plan": guidance or "No AI trade plan available.",
            "Trade Plan": pick(raw, "trade_plan", "Trade Plan", default=""),
            "Financial Summary": pick(raw, "financial_summary", "Financial Summary", default=""),
            "Recovery Catalyst": pick(raw, "recovery_catalyst", "Recovery Catalyst", default=""),
            "Technical": pick(raw, "technical_agent_score", "Technical Agent", default="N/A"),
            "Fundamentals": pick(raw, "fundamentals_agent_score", "Fundamentals Agent", default="N/A"),
            "Valuation": pick(raw, "valuation_agent_score", "Valuation Agent", default="N/A"),
            "Risk": pick(raw, "risk_agent_score", "Risk Agent", default="N/A"),
            "Catalyst": pick(raw, "catalyst_agent_score", "Catalyst Agent", default="N/A"),
            "P/E": pick(raw, "pe_ratio", "P/E", default="N/A"),
            "Forward P/E": pick(raw, "forward_pe", "Forward P/E", default="N/A"),
            "PEG": pick(raw, "peg_ratio", "PEG", default="N/A"),
            "Price/Sales": pick(raw, "price_to_sales", "Price/Sales", default="N/A"),
            "Cash": pick(raw, "total_cash", "Cash", default=None),
            "Debt": pick(raw, "total_debt", "Debt", default=None),
            "Free Cash Flow": pick(raw, "free_cashflow", "Free Cash Flow", default=None),
            "Operating Cash Flow": pick(raw, "operating_cashflow", "Operating Cash Flow", default=None),
            "Revenue Growth": pick(raw, "revenue_growth", "Revenue Growth", default="N/A"),
            "Profit Margin": pick(raw, "profit_margin", "Profit Margin", default="N/A"),
            "Earnings Date": pick(raw, "earnings_date", "Earnings Date", default="N/A"),
            "_raw": raw,
        }

        if row.get("Target Upside %") is None:
            row["Target Upside %"] = target_upside_pct_from_values(row.get("Price"), row.get("Target"))

        setup_text = str(row["Setup Type"])
        if "Recovery" in setup_text or "Reversal" in setup_text:
            row["Opportunity Bucket"] = "Recovery / Reversal"
        elif row["Price Bucket"] == "$5–$25":
            row["Opportunity Bucket"] = "Growth Under $25"
        elif row["Price Bucket"] == "$25–$100":
            row["Opportunity Bucket"] = "Mid Price Opportunity"
        elif row["Price Bucket"] == "$100+":
            row["Opportunity Bucket"] = "Institutional Leader"
        else:
            row["Opportunity Bucket"] = "General AI Idea"

        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df["Final Conviction"] = pd.to_numeric(df["Final Conviction"], errors="coerce").fillna(0)
    df["Dollar Volume"] = pd.to_numeric(df["Dollar Volume"], errors="coerce").fillna(0)
    df = df.drop_duplicates(subset=["Ticker"], keep="first")
    return df.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False], na_position="last")


def load_file(path):
    return normalize_rows(read_json_safe(path, []))


def actionable(df, min_score=35, require_upside=True):
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work = work[pd.notna(work["Price"])]
    work = work[work["Price"] > 0]
    work = work[work["Final Conviction"] >= min_score]
    work = work[~work["Setup Type"].astype(str).str.contains("Prescreen Candidate", case=False, na=False)]

    if require_upside and "Target Upside %" in work.columns:
        work = work[work.apply(lambda r: qualifies_upside(r), axis=1)]

    return work.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False])


def load_full_scan():
    return load_file(FULL_SCAN_FILE)


def load_top_ideas():
    df = actionable(load_file(TOP_IDEAS_FILE), min_score=45, require_upside=True)
    if not df.empty:
        return df
    return actionable(load_full_scan(), min_score=45, require_upside=True).head(25)


def load_recovery():
    df = actionable(load_file(RECOVERY_SCAN_FILE), min_score=35, require_upside=True)
    if not df.empty:
        return df
    full = load_full_scan()
    if full.empty:
        return full
    return full[full["Opportunity Bucket"].eq("Recovery / Reversal")].copy()


def load_watchlist_symbols():
    data = read_json_safe(WATCHLIST_FILE, {"symbols": DEFAULT_WATCHLIST})
    if isinstance(data, dict):
        data = data.get("symbols", DEFAULT_WATCHLIST)
    if not isinstance(data, list):
        data = DEFAULT_WATCHLIST
    return sorted(set([normalize_ticker(x) for x in data if normalize_ticker(x)]))


def save_watchlist_symbols(symbols):
    clean = sorted(set([normalize_ticker(x) for x in symbols if normalize_ticker(x)]))
    return write_json_safe(WATCHLIST_FILE, {"symbols": clean, "updated_at": datetime.utcnow().isoformat()})


def load_watchlist_scan():
    df = load_file(WATCHLIST_SCAN_FILE)
    if not df.empty:
        return df
    full = load_full_scan()
    symbols = load_watchlist_symbols()
    if full.empty:
        return full
    return full[full["Ticker"].isin(symbols)].copy()



def compute_rsi(series, period=14):
    try:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])
    except Exception:
        return None


def analyze_ticker_now(symbol):
    """
    On-demand AI-agent style review for any ticker.
    This does not wait for the overnight scan.
    It pulls recent price history + available Yahoo fundamentals and maps it
    into the same dashboard row format used by the scan results.
    """
    symbol = normalize_ticker(symbol)
    if not symbol:
        return None, "Enter a valid ticker."

    try:
        import yfinance as yf
    except Exception:
        return None, "yfinance is not installed in this environment."

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo", interval="1d", auto_adjust=True)

        if hist is None or hist.empty or "Close" not in hist.columns:
            return None, f"No price history found for {symbol}."

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna() if "Volume" in hist.columns else pd.Series(dtype=float)

        if close.empty:
            return None, f"No valid price data found for {symbol}."

        price = float(close.iloc[-1])
        sma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        sma100 = float(close.rolling(100).mean().iloc[-1]) if len(close) >= 100 else None
        rsi = compute_rsi(close)
        one_day = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) >= 2 else None
        five_day = ((close.iloc[-1] / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else None
        twenty_day = ((close.iloc[-1] / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else None
        sixty_day = ((close.iloc[-1] / close.iloc[-61]) - 1) * 100 if len(close) >= 61 else None

        avg_volume = float(volume.tail(30).mean()) if not volume.empty else 0
        recent_volume = float(volume.iloc[-1]) if not volume.empty else 0
        volume_ratio = recent_volume / avg_volume if avg_volume else None
        dollar_volume = price * avg_volume if avg_volume else 0

        try:
            info = ticker.get_info() or {}
        except Exception:
            info = {}

        company = info.get("shortName") or info.get("longName") or symbol
        sector = info.get("sector") or "Unknown"
        industry = info.get("industry") or "Unknown"
        market_cap = safe_number(info.get("marketCap"))
        pe = safe_number(info.get("trailingPE"))
        forward_pe = safe_number(info.get("forwardPE"))
        peg = safe_number(info.get("pegRatio"))
        ps = safe_number(info.get("priceToSalesTrailing12Months"))
        cash = safe_number(info.get("totalCash"))
        debt = safe_number(info.get("totalDebt"))
        fcf = safe_number(info.get("freeCashflow"))
        ocf = safe_number(info.get("operatingCashflow"))
        revenue_growth = safe_number(info.get("revenueGrowth"))
        profit_margin = safe_number(info.get("profitMargins"))
        target_mean = safe_number(info.get("targetMeanPrice"))

        # Agent scoring
        technical = 40
        technical_reasons = []
        technical_risks = []

        if sma20 and price > sma20:
            technical += 12
            technical_reasons.append("price is above the 20-day trend")
        else:
            technical_risks.append("price is not clearly above the 20-day trend")

        if sma50 and price > sma50:
            technical += 14
            technical_reasons.append("price is above the 50-day trend")
        else:
            technical_risks.append("price is below or near the 50-day trend")

        if sma20 and sma50 and sma20 > sma50:
            technical += 8
            technical_reasons.append("20-day average is above the 50-day average")

        if rsi is not None and 45 <= rsi <= 68:
            technical += 10
            technical_reasons.append(f"RSI is constructive at {rsi:.1f}")
        elif rsi is not None and rsi > 75:
            technical -= 8
            technical_risks.append(f"RSI is overbought at {rsi:.1f}")
        elif rsi is not None and rsi < 40:
            technical -= 5
            technical_risks.append(f"RSI is weak at {rsi:.1f}")

        if volume_ratio and volume_ratio >= 1.25:
            technical += 8
            technical_reasons.append(f"volume is confirming at {volume_ratio:.2f}x average")
        elif volume_ratio and volume_ratio < 0.70:
            technical_risks.append("volume confirmation is light")

        if twenty_day and twenty_day > 5:
            technical += 6
            technical_reasons.append(f"20-day momentum is positive at {twenty_day:.1f}%")

        technical = max(0, min(100, int(round(technical))))

        fundamentals = 45
        fundamental_reasons = []
        fundamental_risks = []

        if revenue_growth is not None:
            if revenue_growth > 0.10:
                fundamentals += 12
                fundamental_reasons.append(f"revenue growth is positive at {revenue_growth*100:.1f}%")
            elif revenue_growth < 0:
                fundamentals -= 8
                fundamental_risks.append(f"revenue growth is negative at {revenue_growth*100:.1f}%")

        if profit_margin is not None:
            if profit_margin > 0.10:
                fundamentals += 12
                fundamental_reasons.append(f"profit margin is healthy at {profit_margin*100:.1f}%")
            elif profit_margin < 0:
                fundamentals -= 10
                fundamental_risks.append("company is not currently profitable")

        if fcf is not None:
            if fcf > 0:
                fundamentals += 12
                fundamental_reasons.append(f"free cash flow is positive at {compact_money(fcf)}")
            else:
                fundamentals -= 8
                fundamental_risks.append(f"free cash flow is negative at {compact_money(fcf)}")

        if cash is not None and debt is not None:
            if cash > debt:
                fundamentals += 10
                fundamental_reasons.append(f"cash exceeds debt: {compact_money(cash)} cash vs {compact_money(debt)} debt")
            elif debt > cash * 2 if cash else False:
                fundamentals -= 8
                fundamental_risks.append(f"debt is much higher than cash: {compact_money(debt)} debt vs {compact_money(cash)} cash")

        fundamentals = max(0, min(100, int(round(fundamentals))))

        valuation = 50
        valuation_reasons = []
        valuation_risks = []

        if pe is not None:
            if 0 < pe < 25:
                valuation += 10
                valuation_reasons.append(f"P/E looks reasonable at {pe:.1f}")
            elif pe > 60:
                valuation -= 8
                valuation_risks.append(f"P/E is elevated at {pe:.1f}")

        if forward_pe is not None:
            if 0 < forward_pe < 30:
                valuation += 8
                valuation_reasons.append(f"forward P/E is reasonable at {forward_pe:.1f}")
            elif forward_pe > 70:
                valuation -= 6
                valuation_risks.append(f"forward P/E is elevated at {forward_pe:.1f}")

        if peg is not None:
            if 0 < peg < 1.5:
                valuation += 6
                valuation_reasons.append(f"PEG is attractive at {peg:.2f}")
            elif peg > 3:
                valuation -= 5
                valuation_risks.append(f"PEG is rich at {peg:.2f}")

        if target_mean and price:
            upside = (target_mean - price) / price * 100
            if upside > 15:
                valuation += 8
                valuation_reasons.append(f"analyst mean target implies {upside:.1f}% upside")
            elif upside < 0:
                valuation -= 5
                valuation_risks.append(f"analyst mean target is below current price by {abs(upside):.1f}%")

        valuation = max(0, min(100, int(round(valuation))))

        risk = 70
        risk_reasons = []
        risk_risks = []

        if market_cap and market_cap >= 10_000_000_000:
            risk += 8
            risk_reasons.append("large-cap liquidity reduces execution risk")
        elif market_cap and market_cap < 300_000_000:
            risk -= 15
            risk_risks.append("small market cap increases liquidity and volatility risk")

        if dollar_volume >= 50_000_000:
            risk += 8
            risk_reasons.append("dollar volume is strong")
        elif dollar_volume and dollar_volume < 5_000_000:
            risk -= 10
            risk_risks.append("low dollar volume can make entries/exits harder")

        if rsi is not None and rsi > 75:
            risk -= 6
            risk_risks.append("overbought RSI raises pullback risk")

        risk = max(0, min(100, int(round(risk))))

        catalyst = 45
        catalyst_reasons = []
        catalyst_risks = []

        if target_mean and price and target_mean > price:
            upside = (target_mean - price) / price * 100
            if upside > 10:
                catalyst += 10
                catalyst_reasons.append(f"analyst target implies {upside:.1f}% upside")

        if sixty_day is not None and sixty_day < -15:
            catalyst += 10
            catalyst_reasons.append(f"recovery angle: stock is down {abs(sixty_day):.1f}% over ~60 trading days")
        elif sixty_day is not None and sixty_day > 15:
            catalyst += 5
            catalyst_reasons.append(f"momentum angle: stock is up {sixty_day:.1f}% over ~60 trading days")

        catalyst = max(0, min(100, int(round(catalyst))))

        final_score = int(round(
            technical * 0.32 +
            fundamentals * 0.22 +
            valuation * 0.14 +
            risk * 0.18 +
            catalyst * 0.14
        ))

        if final_score >= 80:
            decision = "Elite Candidate"
        elif final_score >= 70:
            decision = "Strong Candidate"
        elif final_score >= 60:
            decision = "Moderate Candidate"
        elif final_score >= 50:
            decision = "Watchlist Only"
        else:
            decision = "Low Priority"

        # Trade plan
        entry_low = price * 0.98
        entry_high = price * 1.01
        stop = price * 0.93
        target = price * (1 + MIN_UPSIDE_PCT)
        rr = (target - price) / max(price - stop, 0.01)

        good_items = technical_reasons + fundamental_reasons + valuation_reasons + risk_reasons + catalyst_reasons
        risk_items = technical_risks + fundamental_risks + valuation_risks + risk_risks + catalyst_risks

        good_text = "; ".join(good_items[:8]) if good_items else "Needs stronger confirmation."
        risk_text = "; ".join(risk_items[:8]) if risk_items else "No major red flags detected from available data."

        guidance = (
            f"{company} ({symbol}) was reviewed on-demand by the AI agent framework. "
            f"Final score is {final_score}/100 ({decision}). "
            f"Technical={technical}, Fundamentals={fundamentals}, Valuation={valuation}, Risk={risk}, Catalyst={catalyst}. "
            f"Current price is {price:.2f}; RSI is {rsi:.1f} if available; 20-day move is {twenty_day:.1f}% if available; "
            f"60-day move is {sixty_day:.1f}% if available. "
            f"Suggested entry range is {entry_low:.2f}–{entry_high:.2f}, stop around {stop:.2f}, target around {target:.2f} (minimum {MIN_UPSIDE_PCT*100:.0f}% upside screen). "
            f"Main support: {good_text}. Main risks: {risk_text}."
        )

        financial_summary = (
            f"P/E {pe if pe is not None else 'N/A'}, Forward P/E {forward_pe if forward_pe is not None else 'N/A'}, "
            f"PEG {peg if peg is not None else 'N/A'}, Cash {compact_money(cash)}, Debt {compact_money(debt)}, "
            f"Free Cash Flow {compact_money(fcf)}, Operating Cash Flow {compact_money(ocf)}."
        )

        raw = {
            "symbol": symbol,
            "company_name": company,
            "price": price,
            "conviction": final_score,
            "setup_type": "On-Demand Watchlist Review",
            "decision_rating": decision,
            "sector": sector,
            "industry": industry,
            "market_cap": market_cap,
            "rsi": round(rsi, 1) if rsi is not None else None,
            "twenty_day_pct": round(twenty_day, 2) if twenty_day is not None else None,
            "sixty_day_pct": round(sixty_day, 2) if sixty_day is not None else None,
            "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
            "dollar_volume": dollar_volume,
            "entry_range": f"{entry_low:.2f} – {entry_high:.2f}",
            "stop_loss": round(stop, 2),
            "target": round(target, 2),
            "risk_reward": round(rr, 2),
            "target_upside_pct": round(MIN_UPSIDE_PCT * 100, 1),
            "why_ranked_high": guidance,
            "what_looks_good": good_text,
            "what_could_go_wrong": risk_text,
            "ai_reasoning": guidance,
            "trade_plan": f"Entry {entry_low:.2f}–{entry_high:.2f}; Stop {stop:.2f}; Target {target:.2f}; Risk/reward {rr:.2f}x.",
            "financial_summary": financial_summary,
            "recovery_catalyst": "; ".join(catalyst_reasons + catalyst_risks) or "No clear catalyst detected from available data.",
            "technical_agent_score": technical,
            "fundamentals_agent_score": fundamentals,
            "valuation_agent_score": valuation,
            "risk_agent_score": risk,
            "catalyst_agent_score": catalyst,
            "pe_ratio": pe,
            "forward_pe": forward_pe,
            "peg_ratio": peg,
            "price_to_sales": ps,
            "total_cash": cash,
            "total_debt": debt,
            "free_cashflow": fcf,
            "operating_cashflow": ocf,
            "revenue_growth": revenue_growth,
            "profit_margin": profit_margin,
            "on_demand": True,
        }

        normalized = normalize_rows([raw])
        if normalized.empty:
            return None, f"Could not normalize analysis for {symbol}."

        return normalized.iloc[0].to_dict(), None

    except Exception as e:
        return None, f"Could not analyze {symbol}: {e}"


def load_best_scan():
    full = actionable(load_full_scan(), min_score=35, require_upside=True)
    pre = actionable(load_file(PRESCREEN_FILE), min_score=35, require_upside=True)
    if len(full) >= 25:
        return full, "Full AI Scan"
    if len(pre) > len(full):
        return pre, "Broad Prescreen"
    return full, "Full AI Scan"



def clean_display_text(value, max_chars=None):
    text = str(value or "")
    text = text.replace("`", "")
    text = text.replace("\\n", " ")
    text = " ".join(text.split())
    if max_chars and len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def render_agent_help():
    st.caption("Tip: Open this section to understand Technical, Fundamentals, Valuation, Risk, and Catalyst scores.")
    with st.expander("What do the AI agent scores mean?", expanded=False):
        st.markdown("""
        **Technical** — Trend, moving averages, RSI, momentum, volume confirmation, and volatility.

        **Fundamentals** — Revenue growth, earnings growth, margins, cash flow, cash, debt, and balance-sheet quality.

        **Valuation** — P/E, forward P/E, PEG, price-to-sales, price-to-book, and analyst target upside.

        **Risk** — Liquidity, market cap, volatility, large one-day moves, overbought conditions, and debt/cash risk.

        **Catalyst** — Earnings timing, recovery/reversal setup, analyst target upside, and event-driven potential.
        """)


def render_scan_status():
    state = read_json_safe(SCAN_STATE_FILE, {})
    universe = read_json_safe(UNIVERSE_FILE, {})
    full = load_full_scan()
    top = load_top_ideas()
    recovery = load_recovery()
    watch = load_watchlist_scan()

    with st.expander("Scan status", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Universe", universe.get("count", state.get("universe_count", "N/A")) if isinstance(universe, dict) else "N/A")
        c2.metric("Full Rows", len(full))
        c3.metric("Top Ideas", len(top))
        c4.metric("Recovery", len(recovery))
        c5.metric("Watchlist", len(watch))
        st.json(state)


def agent_metric_row(row):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Technical", row.get("Technical", "N/A"))
    c2.metric("Fundamentals", row.get("Fundamentals", "N/A"))
    c3.metric("Valuation", row.get("Valuation", "N/A"))
    c4.metric("Risk", row.get("Risk", "N/A"))
    c5.metric("Catalyst", row.get("Catalyst", "N/A"))


def render_cards(df, title, key_prefix, limit=5):
    st.subheader(title)

    if df is None or df.empty:
        st.info("No ideas available in this category yet.")
        return

    for _, row in df.head(limit).iterrows():
        ticker = row["Ticker"]
        company = row.get("Company", ticker)
        score = int(safe_number(row.get("Final Conviction"), 0))

        with st.container(border=True):
            # Compact header
            h1, h2, h3, h4 = st.columns([2.4, 0.8, 0.8, 0.9])
            with h1:
                st.markdown(f"### {ticker} — {company}")
                st.caption(f"{row.get('Setup Type', 'AI Setup')} • {row.get('Price Bucket', 'N/A')} • {row.get('Sector', 'Unknown')}")
            with h2:
                st.metric("AI Score", score)
            with h3:
                st.metric("Price", money(row.get("Price")))
            with h4:
                if st.button("Open Detail", key=f"{key_prefix}_detail_{ticker}", use_container_width=True):
                    st.session_state.selected_ticker = ticker
                    st.session_state.page = "Detail"
                    st.session_state.force_detail = True
                    try:
                        st.query_params["detail"] = ticker
                    except Exception:
                        pass
                    st.rerun()

            # Agent score row
            agent_metric_row(row)

            # Trade plan row
            t1, t2, t3, t4 = st.columns(4)
            t1.metric("Entry", row.get("Entry Range", "N/A"))
            t2.metric("Stop", money(row.get("Stop Loss")))
            t3.metric("Target", money(row.get("Target")))
            t4.metric("Risk/Reward", row.get("Risk/Reward", "N/A"))

            # Short readable summary instead of huge wall of text
            summary = clean_display_text(row.get("AI Trade Plan") or row.get("Why Ranked Highly"), max_chars=300)
            st.markdown("**Quick AI Summary**")
            st.write(summary)

            with st.expander(f"More reasoning for {ticker}", expanded=False):
                st.markdown("**Why it ranked:**")
                st.write(clean_display_text(row.get("Why Ranked Highly")))
                st.markdown("**What looks good:**")
                st.success(clean_display_text(row.get("What Looks Good", "Needs confirmation.")))
                st.markdown("**What could go wrong:**")
                st.warning(clean_display_text(row.get("What Could Go Wrong", "Market weakness or failed follow-through.")))
                st.caption("For Ask AI, click Open Detail.")


def render_table(df, title, key_prefix, min_score_default=35):
    st.subheader(title)
    if df is None or df.empty:
        st.info("No rows available.")
        return

    left, mid, right = st.columns(3)
    with left:
        min_score = st.slider("Minimum score", 0, 100, min_score_default, key=f"{key_prefix}_score")
    with mid:
        max_price = st.number_input("Max price", min_value=0.0, value=0.0, step=5.0, help="Use 0 for no max price.", key=f"{key_prefix}_max_price")
    with right:
        search = st.text_input("Search", key=f"{key_prefix}_search").strip().upper()

    filtered = df.copy()
    filtered = filtered[filtered["Final Conviction"] >= min_score]

    if max_price:
        filtered = filtered[filtered["Price"].fillna(999999) <= max_price]

    if search:
        mask = filtered["Ticker"].astype(str).str.upper().str.contains(search, na=False)
        mask |= filtered["Company"].astype(str).str.upper().str.contains(search, na=False)
        filtered = filtered[mask]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Shown", len(filtered))
    c2.metric("Loaded", len(df))
    c3.metric("Top Score", int(filtered["Final Conviction"].max()) if not filtered.empty else 0)
    c4.metric("Under $25", len(filtered[(filtered["Price"] >= 5) & (filtered["Price"] <= 25)]) if not filtered.empty else 0)

    cols = [
        "Ticker", "Company", "Opportunity Bucket", "Price Bucket", "Price",
        "Final Conviction", "Decision Rating",
        "Technical", "Fundamentals", "Valuation", "Risk", "Catalyst",
        "Sector", "Industry", "RSI", "20D %", "60D %",
        "Entry Range", "Stop Loss", "Target", "Target Upside %", "Risk/Reward",
    ]
    cols = [c for c in cols if c in filtered.columns]
    display = filtered[cols].copy()

    for col in ["Price", "Stop Loss", "Target"]:
        if col in display.columns:
            display[col] = display[col].apply(money)
    if "Target Upside %" in display.columns:
        display["Target Upside %"] = display["Target Upside %"].apply(lambda x: f"{float(x):.1f}%" if safe_number(x) is not None else "N/A")

    st.dataframe(display, use_container_width=True, hide_index=True, height=560)


def diversified_cards(df, limit=6):
    if df is None or df.empty:
        return pd.DataFrame()

    selected = []
    used = set()
    for bucket, count in [("$5–$25", 2), ("$25–$100", 2), ("$100+", 2)]:
        part = df[df["Price Bucket"] == bucket].copy()
        part = part.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False])
        for _, row in part.head(count).iterrows():
            if row["Ticker"] not in used:
                selected.append(row)
                used.add(row["Ticker"])

    rest = df.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False])
    for _, row in rest.iterrows():
        if row["Ticker"] not in used:
            selected.append(row)
            used.add(row["Ticker"])
        if len(selected) >= limit:
            break

    return pd.DataFrame(selected).head(limit) if selected else pd.DataFrame()


def page_dashboard(scan_df, source):
    state = read_json_safe(SCAN_STATE_FILE, {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Source", source)
    c2.metric("Rows", len(scan_df))
    c3.metric("Scan Version", state.get("version", "N/A"))
    c4.metric("Persisted", str(state.get("github_persisted", "N/A")))

    render_scan_status()
    st.info("Hover tooltips were removed for stability. Use the explainer below for AI score definitions.")
    render_agent_help()

    top = load_top_ideas()
    recovery = load_recovery()
    watch = load_watchlist_scan()

    lower = scan_df[(scan_df["Price"] >= 5) & (scan_df["Price"] <= 25)].copy() if not scan_df.empty else pd.DataFrame()
    mid = scan_df[(scan_df["Price"] > 25) & (scan_df["Price"] <= 100)].copy() if not scan_df.empty else pd.DataFrame()
    high = scan_df[scan_df["Price"] > 100].copy() if not scan_df.empty else pd.DataFrame()

    tabs = st.tabs(["Top AI Summary", "Lower $5–$25", "Mid $25–$100", "Higher $100+", "Recovery", "Watchlist", "Full Table"])

    with tabs[0]:
        render_cards(diversified_cards(top if not top.empty else scan_df), "Balanced Top AI Summary", "top_cards", limit=6)
        render_table(top if not top.empty else scan_df.head(25), "Top AI Table", "top_table", min_score_default=45)

    with tabs[1]:
        render_cards(lower, "Lower Price Opportunities", "lower_cards", limit=5)
        render_table(lower, "Lower Price Table", "lower_table", min_score_default=35)

    with tabs[2]:
        render_cards(mid, "Mid Price Opportunities", "mid_cards", limit=5)
        render_table(mid, "Mid Price Table", "mid_table", min_score_default=35)

    with tabs[3]:
        render_cards(high, "Higher Price Institutional Leaders", "high_cards", limit=5)
        render_table(high, "Higher Price Table", "high_table", min_score_default=45)

    with tabs[4]:
        render_cards(recovery, "Recovery / Reversal Candidates", "recovery_cards", limit=5)
        render_table(recovery, "Recovery Table", "recovery_table", min_score_default=35)

    with tabs[5]:
        page_watchlist(watch if not watch.empty else scan_df)

    with tabs[6]:
        render_table(scan_df, "Full Ranked AI Scan", "full_table", min_score_default=35)


def page_watchlist(scan_df):
    st.subheader("⭐ Watchlist + On-Demand AI Review")
    st.caption("Add any ticker. If it was not in the overnight scan, use Analyze Now to have the AI agents review it immediately.")

    symbols = load_watchlist_symbols()

    col1, col2 = st.columns([3, 1])
    with col1:
        new_symbols = st.text_input("Add ticker(s), comma separated", key="watchlist_add").strip().upper()
    with col2:
        if st.button("Add", key="watchlist_add_btn", use_container_width=True):
            if new_symbols:
                for symbol in new_symbols.replace("\n", ",").split(","):
                    sym = normalize_ticker(symbol)
                    if sym:
                        symbols.append(sym)
                save_watchlist_symbols(symbols)
                st.success("Watchlist updated.")
                st.rerun()

    st.write("### Analyze Any Ticker Now")
    a1, a2 = st.columns([3, 1])
    with a1:
        analyze_symbol = st.text_input("Ticker to analyze now", key="watchlist_analyze_symbol").strip().upper()
    with a2:
        analyze_clicked = st.button("Analyze Now", key="watchlist_analyze_btn", use_container_width=True)

    if analyze_clicked and analyze_symbol:
        row, err = analyze_ticker_now(analyze_symbol)
        if err:
            st.error(err)
        else:
            st.session_state[f"ondemand_{analyze_symbol}"] = row
            if analyze_symbol not in symbols:
                symbols.append(analyze_symbol)
                save_watchlist_symbols(symbols)
            st.success(f"AI agent review completed for {analyze_symbol}.")

    # Show any active on-demand analysis first.
    ondemand_rows = []
    for key, value in st.session_state.items():
        if str(key).startswith("ondemand_") and isinstance(value, dict):
            ondemand_rows.append(value)

    if ondemand_rows:
        ondemand_df = pd.DataFrame(ondemand_rows)
        st.write("### On-Demand AI Reviews")
        render_cards(ondemand_df, "Fresh AI Agent Analysis", "ondemand_cards", limit=10)
        render_table(ondemand_df, "On-Demand Analysis Table", "ondemand_table", min_score_default=0)

    st.write("### Saved Watchlist")
    st.caption("Saved tickers: " + ", ".join(symbols))

    watch_df = scan_df[scan_df["Ticker"].isin(symbols)].copy() if scan_df is not None and not scan_df.empty else pd.DataFrame()

    if not watch_df.empty:
        render_cards(watch_df, "Watchlist AI Guidance from Latest Scan", "watchlist_cards", limit=5)
        render_table(watch_df, "Watchlist Table", "watchlist_table", min_score_default=0)
    else:
        st.info("Your tickers are saved, but none appeared in the latest scheduled scan yet. Use Analyze Now above for immediate review.")

    with st.expander("Remove tickers"):
        for symbol in symbols:
            c1, c2 = st.columns([4, 1])
            c1.write(symbol)
            if c2.button("Remove", key=f"remove_{symbol}"):
                symbols = [x for x in symbols if x != symbol]
                save_watchlist_symbols(symbols)
                st.rerun()



def build_stock_context(row):
    fields = {
        "ticker": row.get("Ticker"),
        "company": row.get("Company"),
        "price": money(row.get("Price")),
        "ai_score": row.get("Final Conviction"),
        "decision": row.get("Decision Rating"),
        "setup_type": row.get("Setup Type"),
        "opportunity_bucket": row.get("Opportunity Bucket"),
        "price_bucket": row.get("Price Bucket"),
        "sector": row.get("Sector"),
        "industry": row.get("Industry"),
        "technical_agent": row.get("Technical"),
        "fundamentals_agent": row.get("Fundamentals"),
        "valuation_agent": row.get("Valuation"),
        "risk_agent": row.get("Risk"),
        "catalyst_agent": row.get("Catalyst"),
        "entry": row.get("Entry Range"),
        "stop": money(row.get("Stop Loss")),
        "target": money(row.get("Target")),
        "risk_reward": row.get("Risk/Reward"),
        "pe": row.get("P/E"),
        "forward_pe": row.get("Forward P/E"),
        "peg": row.get("PEG"),
        "price_sales": row.get("Price/Sales"),
        "cash": compact_money(row.get("Cash")),
        "debt": compact_money(row.get("Debt")),
        "free_cash_flow": compact_money(row.get("Free Cash Flow")),
        "operating_cash_flow": compact_money(row.get("Operating Cash Flow")),
        "rsi": row.get("RSI"),
        "twenty_day": row.get("20D %"),
        "sixty_day": row.get("60D %"),
        "volume_ratio": row.get("Volume Ratio"),
        "why_ranked": row.get("Why Ranked Highly"),
        "looks_good": row.get("What Looks Good"),
        "could_go_wrong": row.get("What Could Go Wrong"),
        "trade_plan": row.get("Trade Plan"),
        "financial_summary": row.get("Financial Summary"),
        "recovery_catalyst": row.get("Recovery Catalyst"),
    }
    return "\n".join([f"{k}: {v}" for k, v in fields.items() if v not in [None, "", "N/A", "$N/A"]])


def call_real_ai(row, question):
    if not OPENAI_API_KEY:
        return None

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a private AI stock research assistant inside a user's dashboard. "
                    "Use only the supplied dashboard context. Do not pretend to know live news or live prices unless provided. "
                    "Do not tell the user to buy or sell. Provide decision support: bull case, bear case, risks, valuation, "
                    "entry/stop/target interpretation, and what to verify before acting."
                ),
            },
            {
                "role": "user",
                "content": f"Dashboard stock context:\n{build_stock_context(row)}\n\nUser question: {question}\n\nAnswer clearly with practical reasoning.",
            },
        ],
        "temperature": 0.2,
        "max_tokens": 750,
    }

    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Real AI request failed. Built-in analysis below.\n\nError: {e}"


def built_in_ai_answer(row, question):
    q = (question or "").lower()
    ticker = row.get("Ticker", "This stock")

    base = (
        f"{ticker} has an AI score of {row.get('Final Conviction')}. "
        f"Agent scores: Technical={row.get('Technical')}, Fundamentals={row.get('Fundamentals')}, "
        f"Valuation={row.get('Valuation')}, Risk={row.get('Risk')}, Catalyst={row.get('Catalyst')}. "
    )

    trade = (
        f"Trade plan: entry {row.get('Entry Range')}, stop {money(row.get('Stop Loss'))}, "
        f"target {money(row.get('Target'))}, risk/reward {row.get('Risk/Reward')}. "
    )

    financial = (
        f"Financial snapshot: P/E {row.get('P/E')}, forward P/E {row.get('Forward P/E')}, PEG {row.get('PEG')}, "
        f"cash {compact_money(row.get('Cash'))}, debt {compact_money(row.get('Debt'))}, "
        f"free cash flow {compact_money(row.get('Free Cash Flow'))}. "
    )

    if any(w in q for w in ["why", "score", "rank", "conviction"]):
        return base + f"Why it ranked: {row.get('Why Ranked Highly')}. What looks good: {row.get('What Looks Good')}. Main risk: {row.get('What Could Go Wrong')}."

    if any(w in q for w in ["risk", "wrong", "bear", "avoid", "invalidate"]):
        return (
            f"Main risks/invalidation points for {ticker}: {row.get('What Could Go Wrong')}. "
            "Also watch for a break below the stop area, fading volume/momentum, weaker fundamentals than expected, or a failed catalyst."
        )

    if any(w in q for w in ["entry", "buy", "stop", "target", "sell", "trade"]):
        return trade + "Use this as research guidance only and confirm current price/news before acting."

    if any(w in q for w in ["fundamental", "cash", "debt", "pe", "valuation", "financial"]):
        return financial + f"Financial summary: {row.get('Financial Summary') or 'No detailed financial summary available.'}"

    if any(w in q for w in ["recovery", "earnings", "catalyst"]):
        return f"Catalyst/recovery view for {ticker}: {row.get('Recovery Catalyst') or 'No specific catalyst detected.'} Catalyst score: {row.get('Catalyst')}."

    if any(w in q for w in ["long", "hold", "long-term", "investment"]):
        return (
            base + financial +
            "For long-term suitability, focus more on fundamentals, valuation, cash/debt, free cash flow, and durable revenue/profit trends than on short-term technical score alone."
        )

    if any(w in q for w in ["compare", "vs", "better"]):
        return (
            f"To compare {ticker} properly, analyze the other ticker too, then compare: AI score, fundamentals score, valuation score, risk score, cash/debt, free cash flow, "
            "growth profile, and whether the setup is momentum, recovery, or long-term quality."
        )

    return base + trade + f"Reasoning: {row.get('AI Trade Plan') or row.get('Why Ranked Highly')}"

def ask_ai_answer(row, question):
    if row is None:
        return "Select or analyze a stock first."

    if not question:
        return "Ask a question about the selected stock."

    real_ai = call_real_ai(row, question)
    if real_ai:
        if real_ai.startswith("Real AI request failed"):
            return real_ai + "

" + built_in_ai_answer(row, question)
        return real_ai

    return built_in_ai_answer(row, question)


def page_detail(scan_df):
    st.subheader("🔎 Stock Detail")

    default_ticker = st.session_state.get("selected_ticker", "")
    try:
        if "detail" in st.query_params:
            default_ticker = str(st.query_params.get("detail", default_ticker)).upper()
    except Exception:
        pass

    ticker = st.text_input("Ticker", value=default_ticker, key="detail_ticker").strip().upper()

    if not ticker:
        st.info("Select a ticker from the dashboard or enter one above.")
        return

    combined = pd.concat([scan_df, load_top_ideas(), load_recovery(), load_watchlist_scan()], ignore_index=True) if not scan_df.empty else pd.DataFrame()
    combined = combined.drop_duplicates(subset=["Ticker"], keep="first") if not combined.empty else combined

    row_df = combined[combined["Ticker"] == ticker] if not combined.empty else pd.DataFrame()
    if row_df.empty:
        st.warning("Ticker not found in latest scheduled scan results. Running on-demand AI agent review...")
        row, err = analyze_ticker_now(ticker)
        if err:
            st.error(err)
            return
        st.session_state[f"ondemand_{ticker}"] = row
    else:
        row = row_df.iloc[0].to_dict()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company", row.get("Company", ticker))
    c2.metric("Price", money(row.get("Price")))
    c3.metric("AI Score", int(safe_number(row.get("Final Conviction"), 0)))
    c4.metric("Bucket", row.get("Opportunity Bucket", "N/A"))

    st.info("You are now in the stock detail page. Ask AI is available below the trade plan.")
    render_agent_help()
    agent_metric_row(row)

    st.write("### AI Reasoning")
    st.write(row.get("AI Trade Plan") or row.get("Why Ranked Highly"))

    st.write("### Trade Plan")
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Entry", row.get("Entry Range", "N/A"))
    t2.metric("Stop", money(row.get("Stop Loss")))
    t3.metric("Target", money(row.get("Target")))
    t4.metric("Upside", f"{safe_number(row.get('Target Upside %')):.1f}%" if safe_number(row.get("Target Upside %")) is not None else "N/A")
    t5.metric("Risk/Reward", row.get("Risk/Reward", "N/A"))

    st.write("### What Looks Good")
    st.success(row.get("What Looks Good", "Needs confirmation."))

    st.write("### What Could Go Wrong")
    st.warning(row.get("What Could Go Wrong", "Market weakness or failed follow-through."))

    st.write("### Financial Details")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("P/E", row.get("P/E", "N/A"))
    f2.metric("Forward P/E", row.get("Forward P/E", "N/A"))
    f3.metric("PEG", row.get("PEG", "N/A"))
    f4.metric("Price/Sales", row.get("Price/Sales", "N/A"))

    f5, f6, f7, f8 = st.columns(4)
    f5.metric("Cash", compact_money(row.get("Cash")))
    f6.metric("Debt", compact_money(row.get("Debt")))
    f7.metric("Free Cash Flow", compact_money(row.get("Free Cash Flow")))
    f8.metric("Operating Cash Flow", compact_money(row.get("Operating Cash Flow")))

    st.write(row.get("Financial Summary") or "No financial summary available.")

    st.write("### Recovery / Catalyst")
    st.write(row.get("Recovery Catalyst") or "No specific recovery catalyst available.")

    st.write("### Ask AI About This Stock")
    if OPENAI_API_KEY:
        st.success("Real Ask AI is enabled.")
    else:
        st.warning("Built-in Ask AI is active. Add OPENAI_API_KEY in Render to enable real AI responses.")

    quick_question = st.selectbox(
        "Quick question",
        [
            "",
            "Why did this score high?",
            "What are the biggest risks?",
            "What would invalidate this setup?",
            "Explain the entry, stop, target, and risk/reward.",
            "Explain the valuation and financial picture.",
            "Is this better for a swing trade or long-term hold?",
            "What should I verify before acting?",
        ],
        key=f"ask_ai_quick_{ticker}",
    )

    custom_question = st.text_input(
        "Or type your own question",
        placeholder="Example: Is this a good stock to hold for 3 months?",
        key=f"ask_ai_custom_{ticker}",
    )

    question = custom_question or quick_question
    if question:
        st.info(ask_ai_answer(row, question))

    with st.expander("Raw Scan Row"):
        st.json(row.get("_raw", row))


if not login_gate():
    st.stop()

st.sidebar.title("📈 AI Dashboard")
st.sidebar.caption(APP_VERSION)
st.sidebar.caption('Ask AI mode: Real AI' if OPENAI_API_KEY else 'Ask AI mode: Built-in')

pages = ["Dashboard", "Watchlist", "Detail", "Scan Status"]

# Keep navigation stable when a card button sends user to Detail.
current = st.session_state.get("nav_page", st.session_state.get("page", "Dashboard"))
if current not in pages:
    current = "Dashboard"

page = st.sidebar.radio("Navigation", pages, index=pages.index(current), key="nav_page")

# If a card button was clicked, force the app into Detail for this run.
if st.session_state.get("force_detail"):
    page = "Detail"
    st.session_state.page = "Detail"
    st.session_state.nav_page = "Detail"
    st.session_state.force_detail = False
else:
    st.session_state.page = page

scan_df, source = load_best_scan()

st.title("📈 AI Trading Dashboard")
st.caption(f"{APP_VERSION}. Research tool only, not financial advice.")

if page == "Dashboard":
    page_dashboard(scan_df, source)
elif page == "Watchlist":
    watch_scan = load_watchlist_scan()
    page_watchlist(watch_scan if not watch_scan.empty else scan_df)
elif page == "Detail":
    page_detail(scan_df)
elif page == "Scan Status":
    render_scan_status()
    st.write("### Files")
    st.json({
        "DATA_DIR": str(DATA_DIR),
        "FULL_SCAN_FILE": str(FULL_SCAN_FILE),
        "PRESCREEN_FILE": str(PRESCREEN_FILE),
        "SCAN_STATE_FILE": str(SCAN_STATE_FILE),
        "UNIVERSE_FILE": str(UNIVERSE_FILE),
        "TOP_IDEAS_FILE": str(TOP_IDEAS_FILE),
        "WATCHLIST_FILE": str(WATCHLIST_FILE),
        "WATCHLIST_SCAN_FILE": str(WATCHLIST_SCAN_FILE),
        "RECOVERY_SCAN_FILE": str(RECOVERY_SCAN_FILE),
    })
