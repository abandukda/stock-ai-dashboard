import os
from flask import Flask, request, redirect, session
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
    <body style="font-family: Arial; padding: 25px; background:#f4f6f8;">

        <div style="display:flex; justify-content:space-between;">
            <h1>📊 AI Trading Dashboard</h1>
            <a href="/logout">Logout</a>
        </div>

        <h2>🔥 Top 3 Picks</h2>
        {top3_html}

        <h2>Scanner</h2>
        <table border="1" cellpadding="8" style="background:white; width:100%;">
            <tr>
                <th>Ticker</th><th>Price</th><th>Score</th><th>Confidence</th><th>Signal</th>
            </tr>
            {scanner_rows}
        </table>

        <h2>Watchlist</h2>
        <form method="POST">
            <input name="ticker" placeholder="Add stock">
            <input type="hidden" name="action" value="add_watchlist">
            <button>Add</button>
        </form>

        <form method="POST">
            <input type="hidden" name="action" value="send_alerts">
            <button>Send Alerts</button>
        </form>

        <p>{alert_message}</p>

        <table border="1" cellpadding="8" style="background:white; width:100%;">
            <tr>
                <th>Ticker</th><th>Price</th><th>Score</th><th>Confidence</th><th>Signal</th><th>Alert</th>
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