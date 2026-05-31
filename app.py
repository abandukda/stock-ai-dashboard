import os
import json
from pathlib import Path

import pandas as pd
import streamlit as st


APP_VERSION = "V40.2.1 Dashboard - Fresh Full Scan Top Ideas"

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

MIN_UPSIDE_PCT = float(os.getenv("MIN_UPSIDE_PCT", "0"))


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
        "What Looks Good": safe_text(pick(raw, "What Looks Good", "what_looks_good", default=""), ""),
        "Why Ranked High": safe_text(pick(raw, "Why Ranked High", "why_ranked_high", default=""), ""),
        "Guidance": safe_text(pick(raw, "Guidance", "guidance", "ai_guidance", default=""), ""),
        "Action Note": safe_text(pick(raw, "Action Note", "action_note", default=""), ""),
        "Target Source": safe_text(pick(raw, "Target Source", "target_source", default="N/A"), "N/A"),
        "Target Confidence Note": safe_text(pick(raw, "Target Confidence Note", "target_confidence_note", default=""), ""),
        "Source FMP": bool(pick(raw, "source_fmp_profile", "Source FMP", default=False)),
        "Website": safe_text(pick(raw, "website", "Website", default=""), ""),
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

    if state:
        generated = state.get("generated_at", "N/A")
        duration = state.get("duration_seconds", "N/A")
        st.caption(
            f"Last scan: {generated} | Duration: {duration}s | DATA_DIR={state.get('data_dir', '.')}"
        )


def render_score_help():
    with st.expander("What changed in V40.2?", expanded=False):
        st.markdown(
            """
            **V40.2 dashboard change:** the dashboard now respects the normalized scanner conviction
            from `overnight_market_scan.py` instead of recalculating its own score. This prevents repeated
            artificial 99 scores.

            **What to look for:**
            - Better score spread
            - AI Fair Value instead of generic target
            - Expected upside from scanner data
            - Investment thesis and risk fields in the table
            """
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
        )
    with controls[1]:
        max_price = st.number_input(
            "Max price",
            min_value=0.0,
            value=0.0,
            step=5.0,
            key=f"{key_prefix}_max_price",
        )
    with controls[2]:
        min_upside = st.number_input(
            "Min upside %",
            value=float(MIN_UPSIDE_PCT * 100),
            step=1.0,
            key=f"{key_prefix}_min_upside",
        )
    with controls[3]:
        search = st.text_input("Search ticker/company", key=f"{key_prefix}_search")

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
        st.metric("Rows", len(filtered))
    with m2:
        st.metric("Top Score", int(filtered["Final Conviction"].max()) if not filtered.empty else 0)
    with m3:
        st.metric("Top Upside", fmt_pct(filtered["Target Upside %"].max()) if not filtered.empty else "N/A")
    with m4:
        st.metric("Median Score", int(filtered["Final Conviction"].median()) if not filtered.empty else 0)

    if filtered.empty:
        st.warning("No rows match filters.")
        return

    display_cols = [
        "Ticker",
        "Company",
        "Sector",
        "Price",
        "Final Conviction",
        "AI Fair Value",
        "Target Upside %",
        "AI Bull Case",
        "AI Bear Case",
        "Analyst Target",
        "Analyst Count",
        "Entry Range",
        "Stop Loss",
        "Investment Thesis",
        "Primary Risk",
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

    st.markdown("### Detail View")
    tickers = filtered["Ticker"].dropna().unique().tolist()
    selected = st.selectbox("Select ticker", tickers, key=f"{key_prefix}_select")

    if selected:
        row = filtered[filtered["Ticker"].eq(selected)].iloc[0]
        render_detail(row)


def render_detail(row):
    ticker = row.get("Ticker", "")
    company = row.get("Company", ticker)

    st.markdown(f"## {ticker} — {company}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Price", fmt_money(row.get("Price")))
    c2.metric("AI Score", int(safe_number(row.get("Final Conviction"), 0)))
    c3.metric("AI Fair Value", fmt_money(row.get("AI Fair Value")))
    c4.metric("Upside", fmt_pct(row.get("Target Upside %")))
    c5.metric("Analyst Count", int(safe_number(row.get("Analyst Count"), 0)))

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Bull Case", fmt_money(row.get("AI Bull Case")))
    c7.metric("Bear Case", fmt_money(row.get("AI Bear Case")))
    c8.metric("Stop Loss", fmt_money(row.get("Stop Loss")))
    c9.metric("Risk/Reward", safe_text(row.get("Risk/Reward"), "N/A"))

    st.markdown("### Investment Thesis")
    thesis = safe_text(row.get("Investment Thesis"), "")
    if thesis:
        st.write(thesis)
    else:
        st.info("No investment thesis provided yet.")

    st.markdown("### Main Risk")
    risk = safe_text(row.get("Primary Risk"), "")
    if risk:
        st.warning(risk)
    else:
        st.info("No primary risk provided yet.")

    st.markdown("### Guidance")
    guidance = safe_text(row.get("Guidance"), "")
    if guidance:
        st.write(guidance)

    st.markdown("### Target Logic")
    st.write(safe_text(row.get("Target Source"), "N/A"))
    note = safe_text(row.get("Target Confidence Note"), "")
    if note:
        st.caption(note)

    with st.expander("Raw row data", expanded=False):
        raw = row.get("Raw", {})
        st.json(raw if isinstance(raw, dict) else {})


def render_market_summary(full_df):
    st.subheader("Market Scan Summary")

    if full_df.empty:
        st.info("No scan data available.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Ideas", len(full_df))
    c2.metric("Avg Score", int(full_df["Final Conviction"].mean()))
    c3.metric("Median Upside", fmt_pct(full_df["Target Upside %"].median()))
    c4.metric("FMP Enriched", int(full_df["Source FMP"].sum()) if "Source FMP" in full_df else 0)

    if "Sector" in full_df.columns:
        sector_counts = full_df["Sector"].fillna("Unknown").value_counts().head(10)
        st.bar_chart(sector_counts)


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

    risk = safe_text(matched.get("Primary Risk"), "")
    if risk:
        st.warning(risk)


# =========================
# MAIN APP
# =========================

def main():
    render_status_banner()
    render_score_help()

    full_df = load_full_scan()
    top_df = latest_top_ideas()
    recovery_df = latest_recovery()
    watch_df = latest_watchlist_scan()
    prescreen_df = load_file(PRESCREEN_FILE)

    tabs = st.tabs(
        [
            "Top AI Ideas",
            "Full Ranked Scan",
            "Recovery",
            "Watchlist",
            "Prescreen",
            "Summary",
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
        render_table(recovery_df, "Recovery / Reversal Ideas", "recovery_table", min_score_default=35)

    with tabs[3]:
        render_table(watch_df, "Watchlist Scan", "watch_table", min_score_default=0)

    with tabs[4]:
        render_table(prescreen_df, "Prescreen Candidates", "prescreen_table", min_score_default=35)

    with tabs[5]:
        render_market_summary(full_df)

    with tabs[6]:
        render_chat_helper(full_df)


if __name__ == "__main__":
    main()
