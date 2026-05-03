import json
from datetime import datetime
from analyzer import analyze_stock

PORTFOLIO_FILE = "data/portfolio.json"


def load_portfolio():
    try:
        with open(PORTFOLIO_FILE, "r") as file:
            return json.load(file)
    except:
        return []


def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as file:
        json.dump(portfolio, file, indent=4)


def add_position(ticker, entry_price, shares=1, strategy="swing/long-term"):
    portfolio = load_portfolio()

    position = {
        "ticker": ticker.upper().strip(),
        "entry_price": float(entry_price),
        "shares": float(shares),
        "strategy": strategy,
        "date_added": datetime.now().strftime("%Y-%m-%d")
    }

    portfolio.append(position)
    save_portfolio(portfolio)


def get_hold_action(score, pnl_percent, long_term, dip_status):
    # 🚀 PROFIT PROTECTION LOGIC

    # Big winner + momentum still strong
    if pnl_percent >= 15 and score >= 75:
        return "🔥 Strong Winner — consider trimming or trailing stop"

    # Good profit but momentum fading
    if pnl_percent >= 10 and score < 70:
        return "⚠️ Protect Profit — momentum weakening, consider partial exit"

    # Profit + overextended risk
    if pnl_percent >= 20:
        return "💰 Take Profit Zone — consider locking gains"

    # Moderate gain, still healthy
    if pnl_percent >= 5 and score >= 60:
        return "✅ Hold Winner — trend still intact"

    # Long-term hold scenario
    if "Strong long-term" in long_term and pnl_percent > -10:
        return "🟢 Hold Long Term — ignore short-term noise"

    # Neutral watch
    if score >= 60:
        return "👀 Watch Closely — not strong enough yet"

    # Losing + weak setup
    if pnl_percent < -8 and score < 45:
        return "🚨 Exit Watch — weak + losing position"

    # Losing but long-term ok
    if pnl_percent < 0 and "Strong long-term" in long_term:
        return "🟡 Hold — possible dip in long-term trend"

    return "⚖️ Hold — neutral"


def review_portfolio():
    portfolio = load_portfolio()
    reviewed = []

    for position in portfolio:
        analysis = analyze_stock(position["ticker"])

        if not analysis:
            continue

        current_price = analysis["price"]
        entry_price = position["entry_price"]
        shares = position["shares"]

        pnl = (current_price - entry_price) * shares
        pnl_percent = ((current_price - entry_price) / entry_price) * 100

        action = get_hold_action(
            analysis["score"],
            pnl_percent,
            analysis["long_term"],
            analysis["dip_status"]
        )

        reviewed.append({
            "ticker": position["ticker"],
            "entry_price": entry_price,
            "current_price": current_price,
            "shares": shares,
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_percent, 2),
            "score": analysis["score"],
            "signal": analysis["signal"],
            "long_term": analysis["long_term"],
            "dip_status": analysis["dip_status"],
            "action": action,
            "strategy": position["strategy"],
            "date_added": position["date_added"]
        })

    return reviewed