# (Only showing NEW section to avoid breaking your working app)
# 👉 ADD THIS RIGHT AFTER YOUR TRADE JOURNAL SECTION

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

        profit_factor = abs(wins["P/L $"].sum() / losses["P/L $"].sum()) if not losses.empty else 0

        best_trade = closed_trades["P/L $"].max()
        worst_trade = closed_trades["P/L $"].min()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total P/L", f"${total_pl:,.2f}")
        c2.metric("Win Rate", f"{win_rate:.1f}%")
        c3.metric("Avg Win", f"${avg_win:,.2f}")
        c4.metric("Avg Loss", f"${avg_loss:,.2f}")

        c5, c6, c7 = st.columns(3)
        c5.metric("Profit Factor", f"{profit_factor:.2f}")
        c6.metric("Best Trade", f"${best_trade:,.2f}")
        c7.metric("Worst Trade", f"${worst_trade:,.2f}")

        # Equity Curve
        closed_trades = closed_trades.sort_values("Date")
        closed_trades["Equity"] = closed_trades["P/L $"].cumsum()

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=closed_trades["Date"],
            y=closed_trades["Equity"],
            mode="lines+markers",
            name="Equity Curve"
        ))

        fig.update_layout(
            title="Equity Curve",
            height=400
        )

        st.plotly_chart(fig, use_container_width=True)