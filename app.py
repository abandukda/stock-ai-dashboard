
import os
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st


APP_VERSION = "V40.1 Detail + Ask AI Fix"

st.set_page_config(
    page_title=f"AI Trading Dashboard {APP_VERSION}",
    page_icon="📈",
    layout="wide",
)

DATA_DIR = Path(os.getenv("DATA_DIR", "."))

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


def actionable(df, min_score=35):
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work = work[pd.notna(work["Price"])]
    work = work[work["Price"] > 0]
    work = work[work["Final Conviction"] >= min_score]
    work = work[~work["Setup Type"].astype(str).str.contains("Prescreen Candidate", case=False, na=False)]
    return work.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False])


def load_full_scan():
    return load_file(FULL_SCAN_FILE)


def load_top_ideas():
    df = actionable(load_file(TOP_IDEAS_FILE), min_score=45)
    if not df.empty:
        return df
    return actionable(load_full_scan(), min_score=45).head(25)


def load_recovery():
    df = actionable(load_file(RECOVERY_SCAN_FILE), min_score=35)
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


def load_best_scan():
    full = actionable(load_full_scan(), min_score=35)
    pre = actionable(load_file(PRESCREEN_FILE), min_score=35)
    if len(full) >= 25:
        return full, "Full AI Scan"
    if len(pre) > len(full):
        return pre, "Broad Prescreen"
    return full, "Full AI Scan"


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
        with st.container(border=True):
            left, right = st.columns([0.72, 0.28])
            with left:
                st.markdown(f"### {ticker} — {row.get('Company', ticker)}")
                st.caption(
                    f"{row.get('Setup Type', 'AI Setup')} | "
                    f"Score: {int(safe_number(row.get('Final Conviction'), 0))} | "
                    f"Price: {money(row.get('Price'))} | "
                    f"Bucket: {row.get('Price Bucket', 'N/A')}"
                )
                agent_metric_row(row)
                st.write(row.get("AI Trade Plan") or row.get("Why Ranked Highly"))
                st.success(f"Looks good: {row.get('What Looks Good', 'Needs confirmation.')}")
                st.warning(f"Risk: {row.get('What Could Go Wrong', 'Market weakness or failed follow-through.')}")
            with right:
                st.metric("Entry", row.get("Entry Range", "N/A"))
                st.metric("Stop", money(row.get("Stop Loss")))
                st.metric("Target", money(row.get("Target")))
                st.metric("Risk/Reward", row.get("Risk/Reward", "N/A"))
                if st.button("Open Detail", key=f"{key_prefix}_detail_{ticker}"):
                    st.session_state.selected_ticker = ticker
                    st.session_state.page = "Detail"
                    st.session_state.nav_page = "Detail"
                    try:
                        st.query_params["detail"] = ticker
                    except Exception:
                        pass
                    st.rerun()


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
        "Entry Range", "Stop Loss", "Target", "Risk/Reward",
    ]
    cols = [c for c in cols if c in filtered.columns]
    display = filtered[cols].copy()

    for col in ["Price", "Stop Loss", "Target"]:
        if col in display.columns:
            display[col] = display[col].apply(money)

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
    st.subheader("⭐ Watchlist")
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
                st.success("Watchlist updated. Run next Cron scan to refresh analysis.")
                st.rerun()

    st.caption("Saved tickers: " + ", ".join(symbols))

    watch_df = scan_df[scan_df["Ticker"].isin(symbols)].copy() if scan_df is not None and not scan_df.empty else pd.DataFrame()
    if not watch_df.empty:
        render_cards(watch_df, "Watchlist AI Guidance", "watchlist_cards", limit=5)
        render_table(watch_df, "Watchlist Table", "watchlist_table", min_score_default=0)
    else:
        st.info("Your tickers are saved, but none appeared in the latest actionable scan.")

    with st.expander("Remove tickers"):
        for symbol in symbols:
            c1, c2 = st.columns([4, 1])
            c1.write(symbol)
            if c2.button("Remove", key=f"remove_{symbol}"):
                symbols = [x for x in symbols if x != symbol]
                save_watchlist_symbols(symbols)
                st.rerun()


def ask_ai_answer(row, question):
    q = (question or "").lower()

    if any(word in q for word in ["why", "score", "rank", "conviction"]):
        return (
            f"{row['Ticker']} scored {row.get('Final Conviction')} because the agent team reviewed technicals, fundamentals, "
            f"valuation, risk, and catalysts. Technical={row.get('Technical')}, Fundamentals={row.get('Fundamentals')}, "
            f"Valuation={row.get('Valuation')}, Risk={row.get('Risk')}, Catalyst={row.get('Catalyst')}. "
            f"Reasoning: {row.get('AI Trade Plan') or row.get('Why Ranked Highly')}"
        )

    if any(word in q for word in ["risk", "wrong", "bear", "avoid"]):
        return f"Main risks for {row['Ticker']}: {row.get('What Could Go Wrong', 'No risk explanation available.')}"

    if any(word in q for word in ["entry", "buy", "stop", "target", "sell"]):
        return (
            f"Trade plan for {row['Ticker']}: Entry {row.get('Entry Range')}, Stop {money(row.get('Stop Loss'))}, "
            f"Target {money(row.get('Target'))}, Risk/Reward {row.get('Risk/Reward')}."
        )

    if any(word in q for word in ["fundamental", "cash", "debt", "pe", "valuation", "financial"]):
        return (
            f"Financial view for {row['Ticker']}: P/E {row.get('P/E')}, Forward P/E {row.get('Forward P/E')}, "
            f"PEG {row.get('PEG')}, Cash {compact_money(row.get('Cash'))}, Debt {compact_money(row.get('Debt'))}, "
            f"Free Cash Flow {compact_money(row.get('Free Cash Flow'))}. "
            f"Summary: {row.get('Financial Summary') or 'No detailed financial summary available.'}"
        )

    if any(word in q for word in ["recovery", "earnings", "catalyst"]):
        return f"Recovery/catalyst view for {row['Ticker']}: {row.get('Recovery Catalyst') or 'No specific recovery catalyst available.'}"

    return (
        f"{row['Ticker']} overview: {row.get('AI Trade Plan') or row.get('Why Ranked Highly')} "
        f"Entry {row.get('Entry Range')}, Stop {money(row.get('Stop Loss'))}, Target {money(row.get('Target'))}."
    )


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
        st.warning("Ticker not found in latest scan results.")
        return

    row = row_df.iloc[0].to_dict()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company", row.get("Company", ticker))
    c2.metric("Price", money(row.get("Price")))
    c3.metric("AI Score", int(safe_number(row.get("Final Conviction"), 0)))
    c4.metric("Bucket", row.get("Opportunity Bucket", "N/A"))

    st.info("You are now in the stock detail page. The Ask AI field is near the bottom of this page.")
    render_agent_help()
    agent_metric_row(row)

    st.write("### AI Reasoning")
    st.write(row.get("AI Trade Plan") or row.get("Why Ranked Highly"))

    st.write("### Trade Plan")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Entry", row.get("Entry Range", "N/A"))
    t2.metric("Stop", money(row.get("Stop Loss")))
    t3.metric("Target", money(row.get("Target")))
    t4.metric("Risk/Reward", row.get("Risk/Reward", "N/A"))

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
    st.caption("This uses the latest scan data for this ticker: agent scores, entry/stop/target, fundamentals, risk, and catalyst text.")

    quick_q = st.selectbox(
        "Quick questions",
        [
            "",
            "Why did this score high?",
            "What are the main risks?",
            "What is the suggested entry, stop, and target?",
            "Explain the financial and valuation picture.",
            "Is this a recovery or catalyst idea?",
        ],
        key=f"ask_ai_quick_{ticker}",
    )

    custom_q = st.text_input(
        "Or type your own question",
        placeholder="Example: Is this better as a swing trade or long-term hold?",
        key=f"ask_ai_custom_{ticker}",
    )

    question = custom_q or quick_q
    if question:
        st.info(ask_ai_answer(row, question))

    with st.expander("Raw Scan Row"):
        st.json(row.get("_raw", row))


if not login_gate():
    st.stop()

st.sidebar.title("📈 AI Dashboard")
st.sidebar.caption(APP_VERSION)

pages = ["Dashboard", "Watchlist", "Detail", "Scan Status"]

# Keep navigation stable when a card button sends user to Detail.
current = st.session_state.get("nav_page", st.session_state.get("page", "Dashboard"))
if current not in pages:
    current = "Dashboard"

page = st.sidebar.radio("Navigation", pages, index=pages.index(current), key="nav_page")
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
