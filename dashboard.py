import os
import io
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flask import Flask, request, redirect, session, Response
from scanner import scan_market
from portfolio import add_position, review_portfolio
from watchlist import add_watchlist_stock, review_watchlist
from alerts import send_alerts

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

USERNAME = os.environ.get("APP_USERNAME", "admin")
PASSWORD = os.environ.get("APP_PASSWORD", "password123")


def is_logged_in():
    return session.get("logged_in")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            return redirect("/")
        else:
            error = "Invalid credentials"

    return f"""
    <html>
    <body style="font-family: Arial; padding:50px;">
        <h2>🔐 Login</h2>
        <form method="POST">
            <input name="username" placeholder="Username"><br><br>
            <input name="password" type="password" placeholder="Password"><br><br>
            <button type="submit">Login</button>
        </form>
        <p style="color:red;">{error}</p>
    </body>
    </html>
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/chart/<ticker>")
def chart(ticker):
    if not is_logged_in():
        return redirect("/login")

    ticker = ticker.upper().strip()
    data = yf.Ticker(ticker).history(period="3mo")

    if data.empty:
        return Response("No chart data", mimetype="text/plain")

    close = data["Close"]
    ma20 = close.rolling(20).mean()

    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(close.index, close.values, label="Close")
    ax.plot(ma20.index, ma20.values, label="20-day MA")
    ax.set_title(f"{ticker} — 3 Month Trend")
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()

    img = io.BytesIO()
    plt.tight_layout()
    fig.savefig(img, format="png")
    plt.close(fig)
    img.seek(0)

    return Response(img.getvalue(), mimetype="image/png")


@app.route("/", methods=["GET", "POST"])
def home():
    if not is_logged_in():
        return redirect("/login")

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
        <div style="background:white; padding:15px; margin:10px 0; border-radius:10px;">
            <h3>{i}. {t['ticker']} — Score {t['score']} — Confidence {t.get('confidence', 0)} — {t['signal']}</h3>
            <img src="/chart/{t['ticker']}" style="max-width:100%; border:1px solid #ddd; border-radius:8px;">
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
            <td><img src="/chart/{p['ticker']}" style="width:260px;"></td>
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
            <td><img src="/chart/{w['ticker']}" style="width:260px;"></td>
        </tr>
        """

    html = f"""
    <html>
    <body style="font-family: Arial; padding: 25px; background:#f4f6f8;">

        <div style="display:flex; justify-content:space-between;">
            <h1>📊 AI Trading Dashboard</h1>
            <a href="/logout">Logout</a>
        </div>

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
            <p>Score represents how strong the stock setup is right now based on trend, momentum, RSI, and volume.</p>

            <h3>🎯 What Confidence Means</h3>
            <p>Confidence represents how reliable the signal is. Higher confidence means the signals are more aligned.</p>
        </div>

        <h2>🔥 Top 3 Daily Picks with Charts</h2>
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
                <th>Chart</th>
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
                <th>Chart</th>
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