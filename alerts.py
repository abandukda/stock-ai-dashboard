import smtplib
import os
from email.mime.text import MIMEText
from watchlist import review_watchlist
from portfolio import review_portfolio

EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")


def send_email(subject, body):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("Email credentials not set.")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)


def build_alert_report():
    watchlist = review_watchlist()
    portfolio = review_portfolio()

    alerts = []

    for item in watchlist:
        score = item.get("score", 0)
        confidence = item.get("confidence", 0)

        if score >= 80 and confidence >= 70:
            alerts.append(
                f"🚨 HIGH PRIORITY BUY WATCH\n"
                f"{item['ticker']}\n"
                f"Score: {score} | Confidence: {confidence}\n"
                f"Price: ${item['price']}\n"
            )

    for item in portfolio:
        action = item["action"]

        if (
            "Protect Profit" in action
            or "Exit Watch" in action
            or "Take Profit" in action
            or "Strong Winner" in action
        ):
            alerts.append(
                f"💼 PORTFOLIO ALERT\n"
                f"{item['ticker']}\n"
                f"P&L: {item['pnl_percent']}%\n"
                f"Score: {item['score']} | Confidence: {item.get('confidence', 'N/A')}\n"
                f"Action: {action}\n"
            )

    if not alerts:
        return None

    report = "AI HIGH-CONVICTION ALERTS\n\n"
    report += "\n".join(alerts)

    return report


def send_alerts():
    report = build_alert_report()

    if not report:
        return "No HIGH PRIORITY alerts."

    send_email("🚨 AI High-Conviction Alerts", report)
    return "High priority alerts sent."