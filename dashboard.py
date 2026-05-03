import os
from flask import Flask, request
from scanner import scan_market
from portfolio import add_position, review_portfolio
from watchlist import add_watchlist_stock, review_watchlist
from alerts import send_alerts

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def home():
    results = scan_market(limit=15)
    alert_message = ""

    if request.method == "POST":
        action = request.form.get("action")
        ticker = request.form.get("ticker", "")
        entry_price = request.form.get("entry_price")

        if action == "add_portfolio" and ticker and entry_price:
            add_position(ticker, entry_price)

        if action == "add_watchlist" and ticker:
            add_watchlist_stock(ticker)

        if action == "send_alerts":
            alert_message = send_alerts()

    top3 = sorted(results, key=lambda x: x["score"], reverse=True)[:3]

    top3_html = ""
    for i, t in enumerate(top3, 1):
        top3_html += f"""
        <div style="background:white; padding:12px; margin:8px 0; border-radius:8px;">
            <b>{i}. {t['ticker']}</b> — Score {t['score']} — Confidence {t.get('confidence', 0)} — {t['signal']}
        </div>
        """

    scanner_rows = ""
    for r in results:
        scanner_rows += f"""
        <tr>
            <td>{r['ticker']}</td>
            <td>${r['price']}</td>
            <td>{r['score']}</td>
            <td>{r.get('confidence', 0)}</td>
            <td>{r['signal']}</td>
        </tr>
        """

    portfolio = review_portfolio()
    portfolio_rows = ""
    for p in portfolio:
        portfolio_rows += f"""
        <tr>
            <td>{p['ticker']}</td>
            <td>${p['entry_price']}</td>
            <td>${p['current_price']}</td>
            <td>{p['pnl_percent']}%</td>
            <td>{p['score']}</td>
            <td>{p['signal']}</td>
            <td>{p['action']}</td>
        </tr>
        """

    watchlist = review_watchlist()
    watch_rows = ""
    for w in watchlist:
        watch_rows += f"""
        <tr>
            <td>{w['ticker']}</td>
            <td>${w['price']}</td>
            <td>{w['score']}</td>
            <td>{w.get('confidence', 0)}</td>
            <td>{w['signal']}</td>
            <td>{w['alert']}</td>
        </tr>
        """

    html = f"""
    <html>
    <head>
        <title>AI Trading Dashboard</title>
    </head>

    <body style="font-family: Arial; padding: 25px; background:#f4f6f8;">

        <h1>📊 AI Trading Dashboard</h1>

        <div style="background:#fff; padding:15px; border-radius:10px; margin-bottom:20px;">
            <h2>🧠 Quick Decision Cheat Sheet</h2>
            <ul>
                <li><b>Score ≥ 80 & Confidence ≥ 70</b> → ✅ Strong Buy Setup</li>
                <li><b>Score High + Confidence Low</b> → ⚠️ Risky / Possible Fakeout</li>
                <li><b>Score 60–70 + Confidence High</b> → 👀 Watch / Early Setup</li>
                <li><b>Low Score + Low Confidence</b> → ❌ Avoid</li>
            </ul>

            <hr>

            <h3>📊 What Score Means</h3>
            <p>
                Score represents how strong the stock setup is right now based on trend, momentum, and volume.
                Higher score = stronger opportunity.
            </p>

            <h3>🎯 What Confidence Means</h3>
            <p>
                Confidence represents how reliable the signal is.
                Higher confidence = signals are aligned and more likely to work.
            </p>
        </div>

        <h2>🔥 Top 3 Daily Picks</h2>
        {top3_html}

        <h2>Scanner — Top 15</h2>
        <table border="1" cellpadding="8" style="background:white; border-collapse:collapse; width:100%;">
            <tr>
                <th>Ticker</th>
                <th>Price</th>
                <th>Score</th>
                <th>Confidence</th>
                <th>Signal</th>
            </tr>
            {scanner_rows}
        </table>

        <h2>Add Position</h2>
        <form method="POST">
            <input name="ticker" placeholder="Ticker or Company">
            <input name="entry_price" placeholder="Entry Price">
            <input type="hidden" name="action" value="add_portfolio">
            <button type="submit">Add to Portfolio</button>
        </form>

        <h2>Add to Watchlist</h2>
        <form method="POST">
            <input name="ticker" placeholder="Ticker or Company">
            <input type="hidden" name="action" value="add_watchlist">
            <button type="submit">Add to Watchlist</button>
        </form>

        <h2>Portfolio Tracker</h2>
        <table border="1" cellpadding="8" style="background:white; border-collapse:collapse; width:100%;">
            <tr>
                <th>Ticker</th>
                <th>Entry</th>
                <th>Current</th>
                <th>P&L%</th>
                <th>Score</th>
                <th>Signal</th>
                <th>Action</th>
            </tr>
            {portfolio_rows}
        </table>

        <h2>Watchlist Tracker</h2>

        <div style="background:#fff; padding:15px; border-radius:10px; margin-bottom:15px;">
            <h3>📧 Watchlist Alerts</h3>
            <form method="POST">
                <input type="hidden" name="action" value="send_alerts">
                <button type="submit">Send Watchlist Alerts Now</button>
            </form>
            <p><b>{alert_message}</b></p>
        </div>

        <table border="1" cellpadding="8" style="background:white; border-collapse:collapse; width:100%;">
            <tr>
                <th>Ticker</th>
                <th>Price</th>
                <th>Score</th>
                <th>Confidence</th>
                <th>Signal</th>
                <th>Alert</th>
            </tr>
            {watch_rows}
        </table>

    </body>
    </html>
    """

    return html


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)