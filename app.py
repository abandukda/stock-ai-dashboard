# --- ADD THESE IMPORTS AT TOP (keep your existing ones too) ---
import re

# --- UPDATE BUTTON (PUT INSIDE SIDEBAR) ---
# Add this inside your sidebar section
if st.button("🔄 Update Data"):
    st.cache_data.clear()
    st.rerun()


# --- SIMPLE ASK AI SECTION (ADD NEAR TOP OR AFTER SCANNER) ---
st.subheader("🤖 Ask AI")

user_question = st.text_input("Ask about your dashboard (e.g., 'best stock', 'should I buy NVDA?')")

def simple_ai_response(question, df):
    if df is None or df.empty:
        return "No data available yet."

    q = question.lower()

    # --- BEST STOCK ---
    if "best" in q:
        best = df.sort_values(by="Confidence", ascending=False).iloc[0]
        return f"{best['Ticker']} is the best setup right now (Confidence {best['Confidence']}, {best['Trade Setup']}, {best['Entry Status']})"

    # --- TOP 3 ---
    if "top" in q:
        top3 = df.head(3)
        response = "Top setups:\n"
        for _, r in top3.iterrows():
            response += f"- {r['Ticker']} (Conf {r['Confidence']}, {r['Entry Status']})\n"
        return response

    # --- ACTIONABLE ---
    if "actionable" in q:
        actionable = df[
            (df["Confidence"] >= 60) &
            (df["Entry Status"].isin(["At / Below Entry", "Near Entry"]))
        ]
        if actionable.empty:
            return "No strong actionable trades right now."
        return "Actionable trades: " + ", ".join(actionable["Ticker"].tolist())

    # --- SPECIFIC TICKER ---
    tickers = df["Ticker"].tolist()
    for t in tickers:
        if t.lower() in q:
            row = df[df["Ticker"] == t].iloc[0]
            return f"{t}: {row['Trade Setup']}, Confidence {row['Confidence']}, Entry {row['Entry Status']}, R/R {row['Risk/Reward']}"

    # --- RISKY / AVOID ---
    if "risky" in q or "avoid" in q:
        risky = df[df["Confidence"] < 50]
        if risky.empty:
            return "No clearly risky stocks."
        return "Risky: " + ", ".join(risky["Ticker"].tolist())

    return "Try asking about best stocks, top setups, or a ticker."

if user_question:
    answer = simple_ai_response(user_question, scanner_df)
    st.success(answer)