# V39.8 PATCH NOTES
# Add these category sections into app.py dashboard tabs/layout.
#
# New categories:
# 1. Elite Institutional Leaders
# 2. Growth Under $25
# 3. Recovery / Reversal
# 4. Watchlist Conviction
# 5. High Risk / High Reward
#
# ============================================================
# ADD THIS FUNCTION INTO app.py
# ============================================================

def categorize_ai_opportunities(df):
    if df is None or df.empty:
        return {
            "elite": df,
            "growth_under_25": df,
            "recovery": df,
            "watchlist": df,
            "high_risk": df,
        }

    work = df.copy()

    # Elite institutional leaders
    elite = work[
        (work["Final Conviction"] >= 75)
        & (work["Price"] >= 50)
    ].sort_values("Final Conviction", ascending=False)

    # Growth opportunities under $25
    growth_under_25 = work[
        (work["Price"] >= 5)
        & (work["Price"] <= 25)
        & (work["Final Conviction"] >= 55)
    ].sort_values("Final Conviction", ascending=False)

    # Recovery / reversal
    recovery = work[
        work["Setup Type"].astype(str).str.contains(
            "Recovery|Reversal",
            case=False,
            na=False,
        )
    ].sort_values("Final Conviction", ascending=False)

    # Watchlist
    wl = load_watchlist()
    watchlist = work[
        work["Ticker"].isin(wl)
    ].sort_values("Final Conviction", ascending=False)

    # Higher risk / higher reward
    high_risk = work[
        (work["Price"] >= 5)
        & (work["Price"] <= 40)
        & (work["Final Conviction"] >= 50)
        & (
            work["Setup Type"].astype(str).str.contains(
                "Momentum|Growth|Recovery",
                case=False,
                na=False,
            )
        )
    ].sort_values("Final Conviction", ascending=False)

    return {
        "elite": elite.head(10),
        "growth_under_25": growth_under_25.head(10),
        "recovery": recovery.head(10),
        "watchlist": watchlist.head(10),
        "high_risk": high_risk.head(10),
    }


# ============================================================
# REPLACE render_dashboard_home()
# ============================================================

def render_dashboard_home(scan_df, source):
    c1, c2, c3, c4 = st.columns(4)

    state = read_json_safe(SCAN_STATE_FILE, {})

    c1.metric("Data Source", source)
    c2.metric("Rows Loaded", len(scan_df))
    c3.metric("Version", state.get("version", "N/A"))
    c4.metric(
        "Last Scan",
        state.get(
            "generated_at",
            state.get("finished_at", "N/A")
        ),
    )

    render_scan_status()

    categorized = categorize_ai_opportunities(scan_df)

    tabs = st.tabs([
        "Elite Leaders",
        "Growth Under $25",
        "Recovery Setups",
        "Watchlist",
        "High Risk / High Reward",
        "All Ranked Scan",
    ])

    with tabs[0]:
        render_idea_cards(
            categorized["elite"],
            "🏛️ Elite Institutional Leaders",
            limit=5,
        )
        render_main_table(
            categorized["elite"],
            "Elite Institutional Table",
            actionable_only=True,
        )

    with tabs[1]:
        render_idea_cards(
            categorized["growth_under_25"],
            "🚀 Growth Opportunities Under $25",
            limit=5,
        )
        render_main_table(
            categorized["growth_under_25"],
            "Growth Under $25 Table",
            actionable_only=False,
        )

    with tabs[2]:
        render_idea_cards(
            categorized["recovery"],
            "🔄 Recovery / Reversal Candidates",
            limit=5,
        )
        render_main_table(
            categorized["recovery"],
            "Recovery Table",
            actionable_only=False,
        )

    with tabs[3]:
        render_watchlist(categorized["watchlist"])

    with tabs[4]:
        render_idea_cards(
            categorized["high_risk"],
            "⚡ Higher Risk / Higher Reward",
            limit=5,
        )
        render_main_table(
            categorized["high_risk"],
            "High Risk / Reward Table",
            actionable_only=False,
        )

    with tabs[5]:
        render_main_table(
            scan_df,
            "📋 Full Ranked AI Scan",
            actionable_only=True,
        )
