import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go


st.set_page_config(page_title="AI Trading Dashboard", layout="wide")

APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "password")
TRADE_JOURNAL_FILE = "trade_journal.csv"


def login():
    st.title("AI Trading Dashboard Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username == APP_USERNAME and password == APP_PASSWORD:
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("Invalid login")


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
    st.stop()


DEFAULT_WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META",
    "GOOGL", "TSLA", "AMD", "PLTR", "SNOW",
    "ELF", "COST", "TSM", "AVGO", "QQQ", "COIN"
]


@st.cache_data(ttl=300)
def get_stock_data(ticker, period="6mo"):
    try:
        data = yf.Ticker(ticker).history(period=period)
        if data.empty:
            return None
        return data
    except Exception:
        return None


def calculate_rsi(data, window=14):
    delta = data["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_trade_metrics(data, risk_budget):
    if data is None or data.empty or len(data) < 50:
        return None

    current = data["Close"].iloc[-1]
    previous = data["Close"].iloc[-2]
    daily_change = ((current - previous) / previous) * 100

    rsi = calculate_rsi(data).iloc[-1]

    ma20 = data["Close"].rolling(20).mean().iloc[-1]
    ma50 = data["Close"].rolling(50).mean().iloc[-1]

    high_20 = data["Close"].tail(20).max()
    high_50 = data["Close"].tail(50).max()
    low_20 = data["Low"].tail(20).min()
    low_50 = data["Low"].tail(50).min()

    drop_20 = ((current - high_20) / high_20) * 100
    drop_50 = ((current - high_50) / high_50) * 100

    if drop_50 <= -20 and rsi < 35:
        dip_status = "Deep Dip"
    elif drop_20 <= -10 and rsi < 40:
        dip_status = "Dip"
    elif drop_20 <= -5:
        dip_status = "Small Dip"
    elif rsi > 70:
        dip_status = "Overbought"
    else:
        dip_status = "No Dip"

    strong_uptrend = current > ma20 > ma50
    deep_dip = drop_50 <= -20 or rsi < 35
    normal_dip = drop_20 <= -7 or rsi < 45
    choppy = abs(ma20 - ma50) / current < 0.03

    if strong_uptrend and not deep_dip:
        setup = "Pullback Buy"
        entry = max(ma20, low_20)
        target = high_50
        stop = entry * 0.94
    elif deep_dip:
        setup = "Deep Dip"
        entry = max(low_20, low_50)
        target = max(ma50, high_20)
        stop = low_50 * 0.95
    elif normal_dip:
        setup = "Dip Buy"
        entry = low_20
        target = high_20
        stop = low_20 * 0.95
    elif choppy:
        setup = "Range"
        entry = low_20
        target = high_20
        stop = low_20 * 0.96
    else:
        setup = "Watch"
        entry = min(ma20, low_20)
        target = high_20
        stop = entry * 0.95

    upside = ((target - current) / current) * 100
    risk_per_share = entry - stop
    reward = target - entry
    rr = reward / risk_per_share if risk_per_share > 0 else 0

    if current <= entry:
        entry_status = "At / Below Entry"
    elif current <= entry * 1.02:
        entry_status = "Near Entry"
    elif current <= entry * 1.05:
        entry_status = "Close to Entry"
    elif current <= entry * 1.10:
        entry_status = "Wait for Pullback"
    else:
        entry_status = "Too Extended"

    entry_distance = ((current - entry) / entry) * 100 if entry > 0 else 0

    shares = int(risk_budget // risk_per_share) if risk_per_share > 0 else 0
    capital_needed = shares * entry
    max_loss = shares * risk_per_share

    confidence = 0

    if dip_status == "Deep Dip":
        confidence += 30
    elif dip_status == "Dip":
        confidence += 24
    elif dip_status == "Small Dip":
        confidence += 16
    elif dip_status == "No Dip":
        confidence += 8

    if 30 <= rsi <= 45:
        confidence += 20
    elif 45 < rsi <= 55:
        confidence += 14
    elif rsi > 70:
        confidence -= 10

    if current > ma20 > ma50:
        confidence += 20
    elif current > ma50:
        confidence += 14
    elif current > ma20:
        confidence += 10

    if rr >= 3:
        confidence += 20
    elif rr >= 2:
        confidence += 16
    elif rr >= 1.5:
        confidence += 12
    elif rr >= 1:
        confidence += 6
    else:
        confidence -= 8

    if upside >= 20:
        confidence += 10
    elif upside >= 12:
        confidence += 8
    elif upside >= 7:
        confidence += 5
    elif upside < 3:
        confidence -= 5

    if entry_status in ["At / Below Entry", "Near Entry"]:
        confidence += 5
    elif entry_status == "Too Extended":
        confidence -= 10

    confidence = max(0, min(100, round(confidence)))

    if confidence >= 80:
        confidence_level = "High"
    elif confidence >= 60:
        confidence_level = "Medium"
    else:
        confidence_level = "Low"

    if current > ma20 > ma50 and rsi < 70:
        signal = "Buy"
    elif current < ma20 and rsi > 60:
        signal = "Sell"
    else:
        signal = "Hold"

    return {
        "Price": round(current, 2),
        "Daily Change %": round(daily_change, 2),
        "RSI": round(rsi, 2),
        "Signal": signal,
        "DIP STATUS": dip_status,
        "Trade Setup": setup,
        "Entry Status": entry_status,
        "Entry Distance %": round(entry_distance, 2),
        "Confidence": confidence,
        "Confidence Level": confidence_level,
        "Suggested Entry": round(entry, 2),
        "Target Price": round(target, 2),
        "Stop Loss": round(stop, 2),
        "Upside %": round(upside, 2),
        "Risk/Reward": round(rr, 2),
        "Risk/Share": round(risk_per_share, 2),
        "Suggested Shares": shares,
        "Capital Needed": round(capital_needed, 2),
        "Max Loss": round(max_loss, 2),
        "Drop From 20D High %": round(drop_20, 2),
        "Drop From 50D High %": round(drop_50, 2),
    }


def build_scanner(tickers, risk_budget):
    rows = []

    for ticker in tickers:
        data = get_stock_data(ticker)
        metrics = calculate_trade_metrics(data, risk_budget)

        if metrics:
            metrics["Ticker"] = ticker
            rows.append(metrics)

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return df.sort_values(
        by=["Confidence", "Risk/Reward", "Upside %"],
        ascending=[False, False, False]
    ).head(15)


def load_trade_journal():
    columns = [
        "Date", "Ticker", "Status", "Setup", "Entry", "Current Price",
        "Stop", "Target", "Shares", "Capital", "Max Loss",
        "Exit Price", "P/L $", "P/L %", "Notes"
    ]

    if not os.path.exists(TRADE_JOURNAL_FILE):
        return pd.DataFrame(columns=columns)

    try:
        df = pd.read_csv(TRADE_JOURNAL_FILE)
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        return df[columns]
    except Exception:
        return pd.DataFrame(columns=columns)


def save_trade_journal(df):
    df.to_csv(TRADE_JOURNAL_FILE, index=False)


def calculate_trade_pl(entry, exit_price, shares):
    try:
        entry = float(entry)
        exit_price = float(exit_price)
        shares = int(shares)

        pl_dollars = (exit_price - entry) * shares
        pl_percent = ((exit_price - entry) / entry) * 100 if entry > 0 else 0

        return round(pl_dollars, 2), round(pl_percent, 2)
    except Exception:
        return 0, 0


def simple_ai_response(question, df):
    if df is None or df.empty:
        return "No scanner data is available yet. Click Update Data or check your watchlist."

    q = question.lower().strip()

    if "best" in q or "top pick" in q:
        best = df.iloc[0]
        return (
            f"{best['Ticker']} is the strongest setup right now. "
            f"Confidence is {best['Confidence']}/100, setup is {best['Trade Setup']}, "
            f"entry status is {best['Entry Status']}, and R/R is {best['Risk/Reward']}."
        )

    if "top 3" in q or "top three" in q:
        response = "Top 3 setups right now:\n"
        for _, row in df.head(3).iterrows():
            response += (
                f"- {row['Ticker']}: Confidence {row['Confidence']}/100, "
                f"{row['Trade Setup']}, {row['Entry Status']}, R/R {row['Risk/Reward']}\n"
            )
        return response

    if "actionable" in q or "buy now" in q or "near entry" in q:
        actionable = df[
            (df["Confidence"] >= 60)
            & (df["Risk/Reward"] >= 1.5)
            & (df["Entry Status"].isin(["At / Below Entry", "Near Entry"]))
        ]

        if actionable.empty:
            return "No high-quality actionable trades right now. Best move is to wait for prices to get closer to entry."

        response = "Actionable setups:\n"
        for _, row in actionable.iterrows():
            response += (
                f"- {row['Ticker']}: {row['Trade Setup']}, "
                f"Entry {row['Suggested Entry']}, R/R {row['Risk/Reward']}, "
                f"Shares {row['Suggested Shares']}\n"
            )
        return response

    if "risky" in q or "avoid" in q or "bad" in q:
        risky = df[
            (df["Confidence"] < 50)
            | (df["Entry Status"] == "Too Extended")
            | (df["DIP STATUS"] == "Overbought")
        ]

        if risky.empty:
            return "No clearly risky or overextended names based on the current scanner."
        return "Risky / avoid for now: " + ", ".join(risky["Ticker"].tolist())

    tickers = df["Ticker"].tolist()
    for ticker in tickers:
        pattern = r"\b" + re.escape(ticker.lower()) + r"\b"
        if re.search(pattern, q):
            row = df[df["Ticker"] == ticker].iloc[0]
            return (
                f"{ticker}: {row['Trade Setup']} with {row['Confidence']}/100 confidence. "
                f"Entry status is {row['Entry Status']} ({row['Entry Distance %']}% from entry). "
                f"Suggested entry is ${row['Suggested Entry']}, target is ${row['Target Price']}, "
                f"stop is ${row['Stop Loss']}, and R/R is {row['Risk/Reward']}. "
                f"Suggested shares based on your risk budget: {row['Suggested Shares']}."
            )

    if "what is confidence" in q or "confidence" in q:
        return "Confidence measures how aligned the setup is across dip status, RSI, trend, R/R, upside, and entry timing. Higher is better."

    if "what is r/r" in q or "risk reward" in q:
        return "R/R means risk/reward. It compares possible reward to possible loss. A value above 1.5 is decent; above 2 is stronger."

    return (
        "Try asking: 'best stock', 'top 3', 'actionable trades', "
        "'should I buy NVDA?', 'risky stocks', or 'what is R/R?'"
    )


st.title("📊 AI Trading Dashboard")

with st.sidebar:
    st.header("Controls")

    risk_budget = st.number_input(
        "Risk Budget Per Trade ($)",
        min_value=25,
        max_value=10000,
        value=500,
        step=25
    )

    if st.button("🔄 Update Data"):
        st.cache_data.clear()
        st.rerun()

    tickers_input = st.text_area(
        "Watchlist",
        value=", ".join(DEFAULT_WATCHLIST)
    )

    watchlist = [
        ticker.strip().upper()
        for ticker in tickers_input.split(",")
        if ticker.strip()
    ]

    selected_ticker = st.selectbox("Chart Ticker", watchlist)

    chart_period = st.selectbox(
        "Chart Period",
        ["1mo", "3mo", "6mo", "1y", "2y"],
        index=2
    )

    if st.button("Logout"):
        st.session_state["logged_in"] = False
        st.rerun()


scanner_df = build_scanner(watchlist, risk_budget)


st.subheader("🤖 Ask AI")

ai_question = st.text_input(
    "Ask about your dashboard",
    placeholder="Examples: best stock, top 3, actionable trades, should I buy NVDA?"
)

if ai_question:
    st.info(simple_ai_response(ai_question, scanner_df))


st.markdown("### 🎯 Top Setups Cheat Sheet")
st.markdown("""
- **Confidence ≥ 80** → Strongest setup.
- **Confidence 60–79** → Good/watchable setup.
- **R/R ≥ 1.5** → Reward may be worth the risk.
- **Entry Status = At / Below Entry or Near Entry** → Most actionable.
- **Too Extended** → Avoid chasing.
- **Shares** = suggested position size based on your risk budget.
""")


st.subheader("🔥 Top 5 High-Confidence Trade Setups")

if scanner_df.empty:
    st.warning("No scanner data available.")
else:
    for _, row in scanner_df.head(5).iterrows():
        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([1, 1, 1.3, 1.3, 1, 1, 1, 1])

        c1.metric("Ticker", row["Ticker"])
        c2.metric("Conf", f"{int(row['Confidence'])}/100")
        c3.markdown(f"**Setup**  \n{row['Trade Setup']}")
        c4.markdown(f"**Timing**  \n{row['Entry Status']}")
        c5.metric("Entry", f"${row['Suggested Entry']}")
        c6.metric("R/R", row["Risk/Reward"])
        c7.metric("Shares", int(row["Suggested Shares"]))
        c8.metric("Max Loss", f"${row['Max Loss']}")


st.markdown("### 📌 Current Opportunities Cheat Sheet")
st.markdown("""
- **DIP STATUS** tells you whether the stock is pulled back or extended.
- **Trade Setup** explains the type of opportunity.
- **Entry Distance %** shows how far price is from suggested entry.
- **Capital Needed** is the estimated money required for the suggested shares.
- **Max Loss** is the approximate loss if stop loss is hit.
""")


st.subheader("📌 Current Opportunities")

if scanner_df.empty:
    st.warning("No current opportunities.")
else:
    st.dataframe(
        scanner_df[
            [
                "Ticker", "Price", "DIP STATUS", "Trade Setup", "Entry Status",
                "Entry Distance %", "Confidence", "Confidence Level",
                "Suggested Entry", "Target Price", "Stop Loss",
                "Risk/Reward", "Suggested Shares", "Capital Needed", "Max Loss", "RSI"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )


st.markdown("### 🧠 Scanner Cheat Sheet")
st.markdown("""
- **Green rows** → Higher confidence setups.
- **Yellow rows** → Watchlist setups, but not perfect.
- **Red rows** → Too extended or avoid chasing.
- Best setups usually have **Confidence ≥ 60**, **R/R ≥ 1.5**, and **Near Entry**.
""")


st.subheader("Top 15 Scanner")

if scanner_df.empty:
    st.warning("No scanner data available.")
else:
    def highlight_rows(row):
        confidence = row["Confidence"]
        entry_status = row["Entry Status"]

        if confidence >= 80 and entry_status in ["At / Below Entry", "Near Entry"]:
            return ["background-color: #14532d; color: white"] * len(row)
        elif confidence >= 70:
            return ["background-color: #166534; color: white"] * len(row)
        elif confidence >= 60:
            return ["background-color: #facc15; color: black"] * len(row)
        elif entry_status == "Too Extended":
            return ["background-color: #7f1d1d; color: white"] * len(row)
        else:
            return [""] * len(row)

    st.dataframe(
        scanner_df.style.apply(highlight_rows, axis=1),
        use_container_width=True,
        hide_index=True
    )


st.markdown("### 📈 Chart Cheat Sheet")
st.markdown("""
- **Entry line** = suggested buy zone.
- **Target line** = first profit target.
- **Stop line** = risk control level.
- Do not chase if price is far above entry.
""")


st.subheader(f"{selected_ticker} Chart")

chart_data = get_stock_data(selected_ticker, chart_period)

if chart_data is not None and not chart_data.empty:
    chart_data["MA20"] = chart_data["Close"].rolling(20).mean()
    chart_data["MA50"] = chart_data["Close"].rolling(50).mean()

    metrics = calculate_trade_metrics(chart_data, risk_budget)

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=chart_data.index,
        open=chart_data["Open"],
        high=chart_data["High"],
        low=chart_data["Low"],
        close=chart_data["Close"],
        name="Price"
    ))

    fig.add_trace(go.Scatter(
        x=chart_data.index,
        y=chart_data["MA20"],
        mode="lines",
        name="20D MA"
    ))

    fig.add_trace(go.Scatter(
        x=chart_data.index,
        y=chart_data["MA50"],
        mode="lines",
        name="50D MA"
    ))

    if metrics:
        fig.add_hline(y=metrics["Suggested Entry"], line_dash="dash", annotation_text="Entry")
        fig.add_hline(y=metrics["Target Price"], line_dash="dot", annotation_text="Target")
        fig.add_hline(y=metrics["Stop Loss"], line_dash="dashdot", annotation_text="Stop")

    fig.update_layout(height=550, xaxis_rangeslider_visible=False)

    st.plotly_chart(fig, use_container_width=True)

    if metrics:
        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)

        c1.metric("Price", f"${metrics['Price']}")
        c2.metric("Confidence", f"{metrics['Confidence']}/100")
        c3.markdown(f"**Timing**  \n{metrics['Entry Status']}")
        c4.metric("Entry Dist", f"{metrics['Entry Distance %']}%")
        c5.metric("Entry", f"${metrics['Suggested Entry']}")
        c6.metric("Stop", f"${metrics['Stop Loss']}")
        c7.metric("R/R", metrics["Risk/Reward"])
        c8.metric("Shares", metrics["Suggested Shares"])
else:
    st.warning("No chart data available.")


st.markdown("### 📓 Trade Journal Cheat Sheet")
st.markdown("""
- **Planned** → setup identified, but not entered yet.
- **Open** → trade is active.
- **Closed - Win** → exited with profit.
- **Closed - Loss** → exited at a loss or stop.
- **Closed - Manual** → exited early by choice.
- Always enter an **Exit Price** when closing a trade so performance updates correctly.
""")


st.subheader("📓 Trade Journal")

journal_df = load_trade_journal()

with st.expander("Add Trade to Journal", expanded=False):
    if scanner_df.empty:
        st.info("Scanner needs data before adding a trade.")
    else:
        selected_setup = st.selectbox("Select Setup", scanner_df["Ticker"].tolist())
        selected_row = scanner_df[scanner_df["Ticker"] == selected_setup].iloc[0]

        c1, c2, c3 = st.columns(3)

        with c1:
            trade_entry = st.number_input("Entry", value=float(selected_row["Suggested Entry"]), step=0.01)
            trade_stop = st.number_input("Stop", value=float(selected_row["Stop Loss"]), step=0.01)

        with c2:
            trade_target = st.number_input("Target", value=float(selected_row["Target Price"]), step=0.01)
            trade_shares = st.number_input("Shares", min_value=0, value=int(selected_row["Suggested Shares"]), step=1)

        with c3:
            trade_status = st.selectbox(
                "Status",
                ["Planned", "Open", "Closed - Win", "Closed - Loss", "Closed - Manual"],
            )
            trade_notes = st.text_area(
                "Notes",
                value=f"{selected_row['Trade Setup']} | {selected_row['Entry Status']}"
            )

        if st.button("Add Trade"):
            capital = round(trade_entry * trade_shares, 2)
            max_loss = round((trade_entry - trade_stop) * trade_shares, 2) if trade_entry > trade_stop else 0

            new_trade = {
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Ticker": selected_setup,
                "Status": trade_status,
                "Setup": selected_row["Trade Setup"],
                "Entry": round(trade_entry, 2),
                "Current Price": round(selected_row["Price"], 2),
                "Stop": round(trade_stop, 2),
                "Target": round(trade_target, 2),
                "Shares": int(trade_shares),
                "Capital": capital,
                "Max Loss": max_loss,
                "Exit Price": "",
                "P/L $": "",
                "P/L %": "",
                "Notes": trade_notes,
            }

            journal_df = pd.concat([journal_df, pd.DataFrame([new_trade])], ignore_index=True)
            save_trade_journal(journal_df)
            st.success("Trade added to journal.")
            st.rerun()


if journal_df.empty:
    st.info("No trades in journal yet.")
else:
    st.dataframe(journal_df, use_container_width=True, hide_index=True)

    st.subheader("Update / Close Trade")

    trade_options = [
        f"{idx} | {row['Ticker']} | {row['Status']} | Entry {row['Entry']}"
        for idx, row in journal_df.iterrows()
    ]

    selected_trade = st.selectbox("Select Trade", trade_options)
    selected_index = int(selected_trade.split(" | ")[0])
    selected_trade_row = journal_df.loc[selected_index]

    c1, c2, c3 = st.columns(3)

    with c1:
        status_options = ["Planned", "Open", "Closed - Win", "Closed - Loss", "Closed - Manual"]
        current_status = selected_trade_row["Status"]
        current_index = status_options.index(current_status) if current_status in status_options else 0
        new_status = st.selectbox("New Status", status_options, index=current_index)

    with c2:
        exit_raw = str(selected_trade_row["Exit Price"]).strip()
        exit_default = float(exit_raw) if exit_raw not in ["", "nan"] else 0.0
        exit_price = st.number_input("Exit Price", min_value=0.0, value=exit_default, step=0.01)

    with c3:
        update_notes = st.text_area(
            "Updated Notes",
            value=str(selected_trade_row["Notes"]) if str(selected_trade_row["Notes"]) != "nan" else ""
        )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("Update Trade"):
            journal_df.at[selected_index, "Status"] = new_status
            journal_df.at[selected_index, "Notes"] = update_notes

            if exit_price > 0:
                journal_df.at[selected_index, "Exit Price"] = round(exit_price, 2)
                pl_dollars, pl_percent = calculate_trade_pl(
                    journal_df.at[selected_index, "Entry"],
                    exit_price,
                    journal_df.at[selected_index, "Shares"]
                )
                journal_df.at[selected_index, "P/L $"] = pl_dollars
                journal_df.at[selected_index, "P/L %"] = pl_percent

            save_trade_journal(journal_df)
            st.success("Trade updated.")
            st.rerun()

    with c2:
        if st.button("Delete Trade"):
            journal_df = journal_df.drop(index=selected_index).reset_index(drop=True)
            save_trade_journal(journal_df)
            st.warning("Trade deleted.")
            st.rerun()


st.markdown("### 📊 Performance Dashboard Cheat Sheet")
st.markdown("""
- **Total P/L** = total profit/loss from closed trades.
- **Win Rate** = percentage of closed trades that made money.
- **Avg Win vs Avg Loss** = shows whether winners are bigger than losers.
- **Profit Factor > 1.5** = healthy trading edge.
- **Equity Curve** should trend upward over time.
""")


st.subheader("📊 Performance Dashboard")

journal_df = load_trade_journal()

if journal_df.empty:
    st.info("No trades to analyze yet.")
else:
    closed_trades = journal_df[
        journal_df["Status"].astype(str).str.contains("Closed", na=False)
    ].copy()

    if closed_trades.empty:
        st.info("No closed trades yet.")
    else:
        closed_trades["P/L $"] = pd.to_numeric(closed_trades["P/L $"], errors="coerce").fillna(0)

        total_pl = closed_trades["P/L $"].sum()
        wins = closed_trades[closed_trades["P/L $"] > 0]
        losses = closed_trades[closed_trades["P/L $"] < 0]

        win_rate = (len(wins) / len(closed_trades)) * 100 if len(closed_trades) > 0 else 0
        avg_win = wins["P/L $"].mean() if not wins.empty else 0
        avg_loss = losses["P/L $"].mean() if not losses.empty else 0
        gross_profit = wins["P/L $"].sum()
        gross_loss = abs(losses["P/L $"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        best_trade = closed_trades["P/L $"].max()
        worst_trade = closed_trades["P/L $"].min()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total P/L", f"${total_pl:,.2f}")
        c2.metric("Win Rate", f"{win_rate:.1f}%")
        c3.metric("Avg Win", f"${avg_win:,.2f}")
        c4.metric("Avg Loss", f"${avg_loss:,.2f}")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Closed Trades", len(closed_trades))
        c6.metric("Profit Factor", f"{profit_factor:.2f}")
        c7.metric("Best Trade", f"${best_trade:,.2f}")
        c8.metric("Worst Trade", f"${worst_trade:,.2f}")

        closed_trades = closed_trades.sort_values("Date")
        closed_trades["Equity"] = closed_trades["P/L $"].cumsum()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=closed_trades["Date"],
            y=closed_trades["Equity"],
            mode="lines+markers",
            name="Equity Curve"
        ))
        fig.update_layout(title="Equity Curve", height=400)
        st.plotly_chart(fig, use_container_width=True)