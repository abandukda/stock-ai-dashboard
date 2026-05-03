import json
from datetime import datetime
from analyzer import analyze_stock

WATCHLIST_FILE = "data/watchlist.json"


def load_watchlist():
    try:
        with open(WATCHLIST_FILE, "r") as file:
            return json.load(file)
    except:
        return []


def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w") as file:
        json.dump(watchlist, file, indent=4)


def add_watchlist_stock(ticker, note=""):
    watchlist = load_watchlist()

    ticker = ticker.upper().strip()

    for item in watchlist:
        if item["ticker"] == ticker:
            return

    watchlist.append({
        "ticker": ticker,
        "note": note,
        "date_added": datetime.now().strftime("%Y-%m-%d")
    })

    save_watchlist(watchlist)


def review_watchlist():
    watchlist = load_watchlist()
    reviewed = []

    for item in watchlist:
        analysis = analyze_stock(item["ticker"])

        if not analysis:
            continue

        score = analysis["score"]
        confidence = analysis["confidence"]

        # 🚨 Alert logic (aligned with alerts.py)
        if score >= 80 and confidence >= 70:
            alert = "🚨 HIGH PRIORITY"
        elif score >= 75 and confidence >= 60:
            alert = "⚠️ MEDIUM PRIORITY"
        else:
            alert = "—"

        reviewed.append({
            "ticker": analysis["ticker"],
            "price": analysis["price"],
            "score": score,
            "confidence": confidence,
            "signal": analysis["signal"],
            "long_term": analysis["long_term"],
            "dip_status": analysis["dip_status"],
            "alert": alert,
            "note": item.get("note", ""),
            "date_added": item.get("date_added", "")
        })

    reviewed.sort(key=lambda x: x["score"], reverse=True)
    return reviewed