import os
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

APP_VERSION = "V39.13 Stable Agent Help Dashboard"

st.set_page_config(
    page_title=f"AI Trading Dashboard {APP_VERSION}",
    page_icon="📈",
    layout="wide",
)

# ============================================================
# CONFIG
# ============================================================

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
PRESCREEN_FILE = DATA_DIR / "market_prescreen.json"
SCAN_STATE_FILE = DATA_DIR / "market_scan_state.json"
UNIVERSE_FILE = DATA_DIR / "total_market_universe.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
TOP_IDEAS_FILE = DATA_DIR / "top_ai_ideas.json"
WATCHLIST_SCAN_FILE = DATA_DIR / "watchlist_scan.json"
RECOVERY_SCAN_FILE = DATA_DIR / "recovery_scan.json"

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
    "PLTR", "ELF", "SNOW", "COST", "AVGO", "PANW", "CRWD", "SOFI"
]


def first_env(*names, default=""):
    for name in names:
        value = os.getenv(name)
        if value not in [None, ""]:
            return value
    return default


ADMIN_USER = first_env(
    "ADMIN_USER", "APP_USERNAME", "APP_USER", "USERNAME", "LOGIN_USER", default="admin"
)
ADMIN_PASSWORD = first_env(
    "ADMIN_PASSWORD", "APP_PASSWORD", "PASSWORD", "LOGIN_PASSWORD", default="admin"
)


# ============================================================
# BASIC HELPERS
# ============================================================

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


def safe_number(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, str) and value.strip() in ["", "N/A", "None", "nan", "NaN", "$N/A", "$None"]:
            return default
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def money_display(value):
    try:
        if value is None or pd.isna(value) or value == "":
            return "N/A"
        return f"${float(value):,.2f}"
    except Exception:
        s = str(value)
        return "N/A" if s in ["None", "nan", "$None", ""] else s


def compact_cap(value):
    try:
        value = float(value)
        if value >= 1_000_000_000_000:
            return f"${value/1_000_000_000_000:.1f}T"
        if value >= 1_000_000_000:
            return f"${value/1_000_000_000:.1f}B"
        if value >= 1_000_000:
            return f"${value/1_000_000:.1f}M"
        return f"${value:,.0f}"
    except Exception:
        return "N/A"


def normalize_ticker(ticker):
    return str(ticker or "").strip().upper().replace("$", "")


def pick(row, *names, default=None):
    for name in names:
        if name in row and row.get(name) not in [None, "", "N/A", "None", "nan", "$None"]:
            return row.get(name)
    return default


def company_display(row):
    ticker = row.get("Ticker", "")
    name = row.get("Company Name", "")
    if not name or str(name).strip() in ["", "None", "nan", ticker]:
        return ticker
    return name


# ============================================================
# LOGIN
# ============================================================

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
            st.session_state.is_admin = True
            st.rerun()
        else:
            st.error("Invalid login. Check your Render environment variables.")

    with st.expander("Login help"):
        st.write("This app checks these environment variables:")
        st.code("ADMIN_USER / ADMIN_PASSWORD\nor APP_USERNAME / APP_PASSWORD\nor APP_USER / APP_PASSWORD")
        st.write("For local testing, defaults are admin/admin if no variables are set.")

    return False


# ============================================================
# DATA LOADING / NORMALIZATION
# ============================================================

def normalize_raw_rows(data):
    """
    Converts BOTH old V39 rows and new V39.3 scanner rows into one dashboard format.
    This is the key fix: the scanner now writes lowercase fields like symbol, price,
    conviction, ai_reasoning, setup_type, etc. The old dashboard expected Title Case.
    """
    if not data:
        return pd.DataFrame()

    if isinstance(data, dict):
        data = data.get("rows", data.get("symbols", []))

    if not isinstance(data, list):
        return pd.DataFrame()

    normalized = []

    for raw in data:
        if not isinstance(raw, dict):
            continue

        ticker = normalize_ticker(pick(raw, "Ticker", "ticker", "symbol", default=""))
        if not ticker:
            continue

        price = safe_number(pick(raw, "Price", "price", "current_price", "last_price", default=None), None)
        conviction = safe_number(
            pick(raw, "Final Conviction", "conviction", "conviction_score", "score", "ai_score", "Quick Score", default=0),
            0,
        )

        company = pick(raw, "Company Name", "company_name", "company", "name", default=ticker)
        setup_type = pick(raw, "Setup Type", "setup_type", "bucket", "Investment Style", default="Research Candidate")
        signal = pick(raw, "Signal", "signal", default=setup_type)

        entry = pick(raw, "Entry Range", "entry_range", default="")
        stop = pick(raw, "Stop Loss", "stop_loss", default="")
        target = pick(raw, "Target / Sell Zone", "target", "target_2", default="")
        rr = pick(raw, "Risk/Reward", "risk_reward", default="")

        guidance = pick(raw, "AI Trade Plan", "ai_reasoning", "ai_guidance", "guidance", "summary", "Research Summary", default="")
        why = pick(raw, "Why Ranked Highly", "why_ranked_high", default=guidance)
        good = pick(raw, "What Looks Good", "what_looks_good", default="")
        bad = pick(raw, "What Could Go Wrong", "what_could_go_wrong", default="")

        normalized.append({
            "Ticker": ticker,
            "Company Name": company if company else ticker,
            "Price": price,
            "Final Conviction": conviction,
            "Setup Type": setup_type,
            "Signal": signal,
            "Investment Style": setup_type,
            "Sector": pick(raw, "Sector", "sector", default="Unknown"),
            "Industry": pick(raw, "Industry", "industry", default="Unknown"),
            "Market Cap": pick(raw, "Market Cap", "market_cap", default=None),
            "RSI": pick(raw, "RSI", "rsi", default="N/A"),
            "20D %": pick(raw, "20D %", "twenty_day_pct", default="N/A"),
            "60D %": pick(raw, "60D %", "sixty_day_pct", default="N/A"),
            "Volume Ratio": pick(raw, "Volume Ratio", "volume_ratio", default="N/A"),
            "Dollar Volume": pick(raw, "Dollar Volume", "dollar_volume", default=0),
            "Entry Range": entry if entry else "N/A",
            "Stop Loss": stop if stop else "N/A",
            "Target / Sell Zone": target if target else "N/A",
            "Risk/Reward": rr if rr != "" else "N/A",
            "Why Ranked Highly": why if why else "No reasoning available.",
            "What Looks Good": good if good else "Needs confirmation.",
            "What Could Go Wrong": bad if bad else "Market weakness or failed follow-through.",
            "AI Trade Plan": guidance if guidance else "No AI trade plan available.",
            "Trade Plan": pick(raw, "trade_plan", "Trade Plan", default=""),
            "Financial Summary": pick(raw, "financial_summary", "Financial Summary", default=""),
            "Recovery Catalyst": pick(raw, "recovery_catalyst", "Recovery Catalyst", default=""),
            "Decision Rating": pick(raw, "decision_rating", "financial_safety", "Financial Safety", default="Needs Review"),
            "Technical Agent": pick(raw, "technical_agent_score", default="N/A"),
            "Fundamentals Agent": pick(raw, "fundamentals_agent_score", default="N/A"),
            "Valuation Agent": pick(raw, "valuation_agent_score", default="N/A"),
            "Risk Agent": pick(raw, "risk_agent_score", default="N/A"),
            "Catalyst Agent": pick(raw, "catalyst_agent_score", default="N/A"),
            "Final Agent Score": pick(raw, "final_agent_score", default=conviction),
            "P/E": pick(raw, "pe_ratio", default="N/A"),
            "Forward P/E": pick(raw, "forward_pe", default="N/A"),
            "Cash": pick(raw, "total_cash", default=None),
            "Debt": pick(raw, "total_debt", default=None),
            "Free Cash Flow": pick(raw, "free_cashflow", default=None),
            "Operating Cash Flow": pick(raw, "operating_cashflow", default=None),
            "Revenue Growth": pick(raw, "revenue_growth", default="N/A"),
            "Profit Margin": pick(raw, "profit_margin", default="N/A"),
            "Earnings Date": pick(raw, "earnings_date", default="N/A"),
            "Execution Quality": pick(raw, "Execution Quality", "execution_quality", default=setup_type),
            "Financial Safety": pick(raw, "Financial Safety", "financial_safety", default="Needs Review"),
            "Agent Greenlight": pick(raw, "Agent Greenlight", "agent_greenlight", default="Research Only"),
            "_raw": raw,
        })

    df = pd.DataFrame(normalized)
    if df.empty:
        return df

    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df["Final Conviction"] = pd.to_numeric(df["Final Conviction"], errors="coerce").fillna(0)
    df["Dollar Volume"] = pd.to_numeric(df["Dollar Volume"], errors="coerce").fillna(0)

    df = df.drop_duplicates(subset=["Ticker"], keep="first")
    df = df.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False], na_position="last")
    return df


def load_rows_file(path):
    return normalize_raw_rows(read_json_safe(path, []))


def load_full_scan():
    return load_rows_file(FULL_SCAN_FILE)


def load_prescreen():
    return load_rows_file(PRESCREEN_FILE)


def load_top_ideas():
    top = load_rows_file(TOP_IDEAS_FILE)
    if not top.empty:
        return filter_actionable(top, min_score=45)
    full = load_full_scan()
    return filter_actionable(full, min_score=45).head(25)


def load_recovery_scan():
    recovery = load_rows_file(RECOVERY_SCAN_FILE)
    if not recovery.empty:
        return filter_actionable(recovery, min_score=38)
    full = load_full_scan()
    if full.empty:
        return full
    mask = full["Setup Type"].astype(str).str.contains("Recovery", case=False, na=False)
    return filter_actionable(full[mask], min_score=38)


def load_watchlist_scan():
    scanned = load_rows_file(WATCHLIST_SCAN_FILE)
    if not scanned.empty:
        return scanned
    full = load_full_scan()
    wl = load_watchlist()
    return full[full["Ticker"].isin(wl)].copy() if not full.empty else pd.DataFrame()


def filter_actionable(df, min_score=45):
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()

    # Kill the junk/fallback rows the user saw.
    work = work[pd.notna(work["Price"])]
    work = work[work["Price"] > 0]
    work = work[work["Final Conviction"] >= min_score]
    work = work[~work["Setup Type"].astype(str).str.contains("Prescreen Candidate", case=False, na=False)]
    work = work[~work["Signal"].astype(str).str.contains("Research Only", case=False, na=False)]
    work = work[~work["Entry Range"].astype(str).isin(["", "N/A", "Use Detail View"])]
    return work.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False])


def load_best_scan():
    full = filter_actionable(load_full_scan(), min_score=38)
    pre = filter_actionable(load_prescreen(), min_score=38)

    if len(full) >= 25:
        return full, "Full AI Scan"
    if len(pre) > len(full):
        return pre, "Broad Prescreen"
    if not full.empty:
        return full, "Full AI Scan"
    return pre, "Broad Prescreen"


def load_watchlist():
    wl = read_json_safe(WATCHLIST_FILE, {"symbols": DEFAULT_WATCHLIST})
    if isinstance(wl, dict):
        wl = wl.get("symbols", DEFAULT_WATCHLIST)
    if not isinstance(wl, list):
        wl = DEFAULT_WATCHLIST
    return sorted(set([normalize_ticker(x) for x in wl if normalize_ticker(x)]))


def save_watchlist(watchlist):
    cleaned = sorted(set([normalize_ticker(x) for x in watchlist if normalize_ticker(x)]))
    return write_json_safe(WATCHLIST_FILE, {"symbols": cleaned, "updated_at": datetime.utcnow().isoformat()})



# ============================================================
# DASHBOARD GUIDANCE HELPERS
# ============================================================

def tooltip_title(title, tooltip):
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:8px; margin-top:6px;">
            <h3 style="margin-bottom:0;">{title}</h3>
            <span title="{tooltip}" style="cursor:help; color:#6b7280; font-size:18px;">ⓘ</span>
        </div>
        """,
        unsafe_allow_html=True,
    )



def agent_help_text(agent_name):
    explanations = {
        "Technical": "Technical Agent reviews trend, moving averages, RSI, momentum, volume confirmation, and volatility. It answers: is the stock technically acting strong right now?",
        "Fundamentals": "Fundamentals Agent reviews revenue growth, earnings growth, margins, free cash flow, operating cash flow, cash, debt, and balance-sheet health. It answers: is the business financially healthy?",
        "Valuation": "Valuation Agent reviews P/E, forward P/E, PEG, price-to-sales, price-to-book, and analyst target upside. It answers: is the stock reasonably priced for its quality and growth?",
        "Risk": "Risk Agent reviews liquidity, market cap, volatility, large one-day moves, overbought conditions, and debt/cash risk. It answers: what could hurt the trade or investment?",
        "Catalyst": "Catalyst Agent reviews earnings timing, analyst target upside, recovery/reversal context, and event risk. It answers: is there a near-term reason this stock could move?",
    }
    return explanations.get(agent_name, "")


def agent_metric(label, value):
    # Stable Streamlit-native metric. Explanations live in the expander below.
    st.metric(label, value)


def diversify_for_cards(df, limit=6):
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()
    work = work[pd.notna(work["Price"])]
    work = work[work["Price"] > 0]
    work["__bucket"] = work["Price"].apply(price_bucket_label)

    selected = []
    used = set()

    for bucket, count in [("Lower Price", 2), ("Mid Price", 2), ("Higher Price", 2)]:
        bucket_df = work[work["__bucket"] == bucket].copy()
        bucket_df = bucket_df.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False])
        for _, row in bucket_df.head(count).iterrows():
            ticker = row.get("Ticker")
            if ticker not in used:
                selected.append(row)
                used.add(ticker)

    remainder = work.sort_values(["Final Conviction", "Dollar Volume"], ascending=[False, False])
    for _, row in remainder.iterrows():
        ticker = row.get("Ticker")
        if ticker not in used:
            selected.append(row)
            used.add(ticker)
        if len(selected) >= limit:
            break

    if not selected:
        return pd.DataFrame()

    return pd.DataFrame(selected).head(limit).drop(columns=["__bucket"], errors="ignore")


def make_category_tabs(scan_df):
    if scan_df is None or scan_df.empty:
        st.warning("No scan data found.")
        return

    lower = scan_df[(scan_df["Price"] >= 5) & (scan_df["Price"] <= 25)].copy()
    mid = scan_df[(scan_df["Price"] > 25) & (scan_df["Price"] <= 100)].copy()
    higher = scan_df[scan_df["Price"] > 100].copy()
    recovery = scan_df[
        scan_df["Setup Type"].astype(str).str.contains("Recovery|Reversal", case=False, na=False)
    ].copy()

    tabs = st.tabs([
        "Top AI Summary",
        "Lower Price $5–$25",
        "Mid Price $25–$100",
        "Higher Price $100+",
        "Recovery",
        "Full Ranked Table",
    ])

    with tabs[0]:
        tooltip_title(
            "Balanced Top AI Summary",
            "Shows a diversified sample from lower, mid, and higher price buckets so the cards are not dominated only by expensive stocks. The table below still shows the full ranking."
        )
        card_df = diversify_for_cards(scan_df, limit=6)
        render_idea_cards(card_df, title="", limit=6, key_prefix="top_summary")
        render_main_table(scan_df.head(25), "Top AI Table — Full Ranking", actionable_only=True, key_prefix="top_ai_table")

    with tabs[1]:
        tooltip_title(
            "Lower Price Opportunities ($5–$25)",
            "Lower-priced stocks that still passed liquidity, price, and AI quality filters. They may offer more upside but usually carry higher volatility/risk."
        )
        render_idea_cards(lower, title="", limit=5, key_prefix="lower_price")
        render_main_table(lower, "Lower Price Ranked Table", actionable_only=False, key_prefix="lower_price_table")

    with tabs[2]:
        tooltip_title(
            "Mid Price Opportunities ($25–$100)",
            "Mid-priced stocks that may balance upside potential with better liquidity and more stable fundamentals."
        )
        render_idea_cards(mid, title="", limit=5, key_prefix="mid_price")
        render_main_table(mid, "Mid Price Ranked Table", actionable_only=False, key_prefix="mid_price_table")

    with tabs[3]:
        tooltip_title(
            "Higher Price Institutional Leaders ($100+)",
            "Higher-priced large-cap or institutional-quality names with stronger fundamentals, liquidity, and trend quality."
        )
        render_idea_cards(higher, title="", limit=5, key_prefix="higher_price")
        render_main_table(higher, "Higher Price Ranked Table", actionable_only=False, key_prefix="higher_price_table")

    with tabs[4]:
        tooltip_title(
            "Recovery / Reversal Candidates",
            "Names that may have pulled back, dropped post-earnings, or remain below prior highs but show early stabilization/reversal potential."
        )
        render_idea_cards(recovery, title="", limit=5, key_prefix="recovery")
        render_main_table(recovery, "Recovery Ranked Table", actionable_only=False, key_prefix="recovery_old_table")

    with tabs[5]:
        tooltip_title(
            "Full Ranked AI Scan",
            "Complete actionable scan sorted by AI conviction and liquidity after exclusions, watchlist scoring, and multi-agent review."
        )
        render_main_table(scan_df, "Full Ranked AI Scan", actionable_only=True, key_prefix="full_ranked_table")



def render_agent_score_explainer():
    with st.expander("What do the AI agent scores mean?", expanded=False):
        st.markdown("""
        **Technical** — Reviews price trend, moving averages, RSI, momentum, volume confirmation, and volatility.  
        Higher score means the stock is acting strong technically right now.

        **Fundamentals** — Reviews revenue growth, earnings growth, margins, cash flow, cash, debt, and balance-sheet quality.  
        Higher score means the underlying business looks financially stronger.

        **Valuation** — Reviews P/E, forward P/E, PEG, price-to-sales, price-to-book, and analyst target upside.  
        Higher score means the stock looks more reasonably priced relative to quality and growth.

        **Risk** — Reviews liquidity, market cap, volatility, large one-day moves, overbought conditions, and debt/cash risk.  
        Higher score means the setup has fewer obvious risk flags.

        **Catalyst** — Reviews earnings timing, recovery/reversal setup, analyst target upside, and event-driven potential.  
        Higher score means there may be a clearer reason the stock could move.
        """)


# ============================================================
# UI SECTIONS
# ============================================================

def render_scan_status():
    state = read_json_safe(SCAN_STATE_FILE, {})
    universe = read_json_safe(UNIVERSE_FILE, {})
    full = load_full_scan()
    pre = load_prescreen()
    top = load_top_ideas()
    recovery = load_recovery_scan()
    watch = load_watchlist_scan()

    with st.expander("Scan status", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Universe", universe.get("count", state.get("universe_count", "N/A")) if isinstance(universe, dict) else "N/A")
        c2.metric("Prescreen Rows", len(pre))
        c3.metric("Full Scan Rows", len(full))
        c4.metric("Top Ideas", len(top))
        c5.metric("Recovery", len(recovery))

        st.json(state)


def render_idea_cards(df, title="Highest Ranked AI Setups", limit=5, key_prefix="cards"):
    if title:
        if title:
            st.subheader(title)

    clean = filter_actionable(df, min_score=45) if df is not None and not df.empty else pd.DataFrame()

    if clean.empty:
        st.warning("No actionable AI setups found yet. Run the Cron Job again or lower filters.")
        return

    for _, row in clean.head(limit).iterrows():
        ticker = row["Ticker"]
        company = company_display(row)
        setup = row.get("Setup Type", "AI Setup")
        score = int(safe_number(row.get("Final Conviction"), 0))

        with st.container(border=True):
            left, right = st.columns([0.72, 0.28])

            with left:
                st.markdown(f"### {ticker} — {company}")
                st.caption(f"{setup} | AI Score: {score} | Decision: {row.get('Decision Rating', 'Needs Review')} | Price: {money_display(row.get('Price'))}")
                st.write(row.get("AI Trade Plan") or row.get("Why Ranked Highly"))
                agent_cols = st.columns(5)
                with agent_cols[0]:
                    agent_metric("Technical", row.get("Technical Agent", "N/A"))
                with agent_cols[1]:
                    agent_metric("Fundamentals", row.get("Fundamentals Agent", "N/A"))
                with agent_cols[2]:
                    agent_metric("Valuation", row.get("Valuation Agent", "N/A"))
                with agent_cols[3]:
                    agent_metric("Risk", row.get("Risk Agent", "N/A"))
                with agent_cols[4]:
                    agent_metric("Catalyst", row.get("Catalyst Agent", "N/A"))

                st.success(f"Looks good: {row.get('What Looks Good', 'Needs confirmation.')}")
                st.warning(f"What could go wrong: {row.get('What Could Go Wrong', 'Market weakness or failed follow-through.')}")

                if st.button(f"Open Detail View for {ticker}", key=f"{key_prefix}_card_detail_{ticker}"):
                    st.session_state.selected_ticker = ticker
                    st.session_state.page = "Detail View"
                    st.rerun()

            with right:
                st.metric("Entry", row.get("Entry Range", "N/A"))
                st.metric("Stop", money_display(row.get("Stop Loss")))
                st.metric("Target", money_display(row.get("Target / Sell Zone")))
                st.metric("Risk/Reward", row.get("Risk/Reward", "N/A"))


def render_main_table(df, title="📋 All Stock Ideas", actionable_only=True, key_prefix="main_table"):
    st.subheader(title)

    if df is None or df.empty:
        st.warning("No stock ideas found yet. Check the overnight Cron job.")
        return

    left, mid, right = st.columns(3)

    with left:
        min_score = st.slider("Minimum score", 0, 100, 45 if actionable_only else 0, key=f"{key_prefix}_min_score")

    with mid:
        max_price = st.number_input("Max price", min_value=0.0, value=0.0, step=5.0, help="Use 0 for no max price.", key=f"{key_prefix}_max_price")

    with right:
        search = st.text_input("Search ticker/company", key=f"{key_prefix}_search").strip().upper()

    filtered = df.copy()
    filtered = filtered[filtered["Final Conviction"].fillna(0) >= min_score]

    if actionable_only:
        filtered = filter_actionable(filtered, min_score=min_score)

    if max_price:
        filtered = filtered[filtered["Price"].fillna(999999) <= max_price]

    if search:
        mask = filtered["Ticker"].astype(str).str.upper().str.contains(search, na=False)
        mask = mask | filtered["Company Name"].astype(str).str.upper().str.contains(search, na=False)
        filtered = filtered[mask]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Shown", len(filtered))
    c2.metric("Total Loaded", len(df))
    c3.metric("Top Score", int(filtered["Final Conviction"].max()) if not filtered.empty else 0)
    c4.metric("With Guidance", len(filtered[filtered["AI Trade Plan"].astype(str).str.len() > 20]) if "AI Trade Plan" in filtered.columns else 0)

    show_cols = [
        "Ticker", "Company Name", "Setup Type", "Decision Rating", "Price", "Final Conviction",
        "Technical Agent", "Fundamentals Agent", "Valuation Agent", "Risk Agent", "Catalyst Agent",
        "Sector", "Industry", "RSI", "20D %", "60D %",
        "Entry Range", "Stop Loss", "Target / Sell Zone", "Risk/Reward",
        "Why Ranked Highly",
    ]
    show_cols = [c for c in show_cols if c in filtered.columns]

    display_df = filtered[show_cols].copy()
    for col in ["Price", "Stop Loss", "Target / Sell Zone"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(money_display)

    st.dataframe(display_df, use_container_width=True, hide_index=True, height=600)

    with st.expander("Actions for visible stocks", expanded=False):
        for _, row in filtered.head(75).iterrows():
            ticker = row["Ticker"]
            name = company_display(row)
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.write(f"**{ticker}** — {name}")
            with c2:
                if st.button("Details", key=f"{key_prefix}_detail_{ticker}"):
                    st.session_state.selected_ticker = ticker
                    st.session_state.page = "Detail View"
                    st.rerun()
            with c3:
                if st.button("Add Watch", key=f"{key_prefix}_watch_{ticker}"):
                    wl = load_watchlist()
                    wl.append(ticker)
                    save_watchlist(wl)
                    st.success(f"Added {ticker}")


def render_dashboard_home(scan_df, source):
    c1, c2, c3, c4 = st.columns(4)
    state = read_json_safe(SCAN_STATE_FILE, {})
    c1.metric("Data Source", source)
    c2.metric("Rows Loaded", len(scan_df))
    c3.metric("Version", state.get("version", "N/A"))
    c4.metric("Last Scan", state.get("generated_at", state.get("finished_at", "N/A")))

    render_scan_status()

    tooltip_title(
        "AI Trading Command Center",
        "Uses multiple AI-style agents: technical, fundamentals, valuation, risk, and catalyst. Ideas are organized by price bucket so you can compare aggressive lower-priced setups against institutional-quality leaders."
    )

    make_category_tabs(scan_df)


def render_watchlist(df):
    st.subheader("⭐ Watchlist")

    wl = load_watchlist()

    c1, c2 = st.columns([3, 1])
    with c1:
        new_ticker = st.text_input("Add ticker").strip().upper()
    with c2:
        if st.button("Add", use_container_width=True):
            if new_ticker:
                wl.append(new_ticker)
                save_watchlist(wl)
                st.success(f"Added {new_ticker}. Run Cron Job to refresh AI scoring.")
                st.rerun()

    st.caption("Your watchlist is saved in watchlist.json. The next Cron Job will score these tickers separately.")

    if not wl:
        st.info("Watchlist is empty.")
        return

    if df is None or df.empty:
        st.write(", ".join(wl))
    else:
        watch_df = df[df["Ticker"].isin(wl)].copy() if "Ticker" in df.columns else pd.DataFrame()
        if watch_df.empty:
            st.write(", ".join(wl))
            st.info("These tickers are saved, but they did not appear in the latest actionable scan yet.")
        else:
            render_idea_cards(watch_df, "Watchlist AI Guidance", limit=5, key_prefix="watchlist")
            render_main_table(watch_df, title="Watchlist Analysis", actionable_only=False, key_prefix="watchlist_table")

    with st.expander("Remove tickers"):
        for ticker in wl:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(ticker)
            with c2:
                if st.button("Remove", key=f"remove_{ticker}"):
                    wl = [x for x in wl if x != ticker]
                    save_watchlist(wl)
                    st.rerun()


def render_detail(df):
    ticker = st.session_state.get("selected_ticker", "")

    typed = st.text_input("Ticker", value=ticker).strip().upper()
    if typed:
        ticker = typed
        st.session_state.selected_ticker = ticker

    if not ticker:
        st.info("Select a ticker from the table.")
        return

    row_df = df[df["Ticker"] == ticker] if df is not None and not df.empty else pd.DataFrame()

    st.subheader(f"🔎 Detail View: {ticker}")

    if row_df.empty:
        st.warning("Ticker not found in latest scan results.")
        return

    row = row_df.iloc[0].to_dict()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company", company_display(row))
    c2.metric("Price", money_display(row.get("Price")))
    c3.metric("Conviction", int(safe_number(row.get("Final Conviction"), 0)))
    c4.metric("Setup", row.get("Setup Type", "N/A"))

    st.write("### AI Reasoning")
    st.write(row.get("AI Trade Plan") or row.get("Why Ranked Highly") or "No reasoning available.")

    st.write("### What Looks Good")
    st.success(row.get("What Looks Good", "Needs confirmation."))

    st.write("### What Could Go Wrong")
    st.warning(row.get("What Could Go Wrong", "Market weakness or failed follow-through."))

    render_agent_score_explainer()

    st.write("### AI Agent Team Scores")
    a1, a2, a3, a4, a5 = st.columns(5)
    with a1:
        agent_metric("Technical", row.get("Technical Agent", "N/A"))
    with a2:
        agent_metric("Fundamentals", row.get("Fundamentals Agent", "N/A"))
    with a3:
        agent_metric("Valuation", row.get("Valuation Agent", "N/A"))
    with a4:
        agent_metric("Risk", row.get("Risk Agent", "N/A"))
    with a5:
        agent_metric("Catalyst", row.get("Catalyst Agent", "N/A"))

    st.write("### Trade Plan")
    st.write(row.get("Trade Plan") or "No detailed trade plan available.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entry", row.get("Entry Range", "N/A"))
    c2.metric("Stop", money_display(row.get("Stop Loss")))
    c3.metric("Target", money_display(row.get("Target / Sell Zone")))
    c4.metric("Risk/Reward", row.get("Risk/Reward", "N/A"))

    st.write("### Financial Review")
    st.write(row.get("Financial Summary") or "No financial summary available.")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("P/E", row.get("P/E", "N/A"))
    f2.metric("Forward P/E", row.get("Forward P/E", "N/A"))
    f3.metric("Cash", compact_cap(row.get("Cash")))
    f4.metric("Debt", compact_cap(row.get("Debt")))
    f5, f6, f7, f8 = st.columns(4)
    f5.metric("Free Cash Flow", compact_cap(row.get("Free Cash Flow")))
    f6.metric("Operating Cash Flow", compact_cap(row.get("Operating Cash Flow")))
    f7.metric("Revenue Growth", row.get("Revenue Growth", "N/A"))
    f8.metric("Profit Margin", row.get("Profit Margin", "N/A"))

    st.write("### Recovery / Earnings Catalyst")
    st.write(row.get("Recovery Catalyst") or "No recovery catalyst available.")

    st.write("### Details")
    detail = {
        "Sector": row.get("Sector"),
        "Industry": row.get("Industry"),
        "Market Cap": compact_cap(row.get("Market Cap")),
        "RSI": row.get("RSI"),
        "20D %": row.get("20D %"),
        "60D %": row.get("60D %"),
        "Volume Ratio": row.get("Volume Ratio"),
    }
    st.json(detail)

    with st.expander("Raw Scan Row"):
        st.json(row.get("_raw", row))


# ============================================================
# APP
# ============================================================

if not login_gate():
    st.stop()

st.sidebar.title("📈 AI Dashboard")
st.sidebar.caption(APP_VERSION)

pages = ["Dashboard", "Watchlist", "Detail View", "Scan Status"]
page = st.sidebar.radio(
    "Navigation",
    pages,
    index=pages.index(st.session_state.get("page", "Dashboard")) if st.session_state.get("page", "Dashboard") in pages else 0,
)
st.session_state.page = page

scan_df, source = load_best_scan()

st.title(f"📈 AI Trading Dashboard {APP_VERSION}")
st.caption("AI-ranked research dashboard. Not financial advice. Validate every setup before trading.")

if page == "Dashboard":
    render_dashboard_home(scan_df, source)

elif page == "Watchlist":
    render_watchlist(load_watchlist_scan())

elif page == "Detail View":
    # Use all actionable rows plus watchlist/recovery rows for detail lookup.
    combined = pd.concat(
        [scan_df, load_top_ideas(), load_recovery_scan(), load_watchlist_scan()],
        ignore_index=True,
    ).drop_duplicates(subset=["Ticker"], keep="first") if not scan_df.empty else scan_df
    render_detail(combined)

elif page == "Scan Status":
    render_scan_status()
    st.write("### Files")
    st.write({
        "DATA_DIR": str(DATA_DIR),
        "FULL_SCAN_FILE": str(FULL_SCAN_FILE),
        "PRESCREEN_FILE": str(PRESCREEN_FILE),
        "SCAN_STATE_FILE": str(SCAN_STATE_FILE),
        "UNIVERSE_FILE": str(UNIVERSE_FILE),
        "TOP_IDEAS_FILE": str(TOP_IDEAS_FILE),
        "WATCHLIST_SCAN_FILE": str(WATCHLIST_SCAN_FILE),
        "RECOVERY_SCAN_FILE": str(RECOVERY_SCAN_FILE),
    })
