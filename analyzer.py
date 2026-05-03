import yfinance as yf
from yahooquery import search
from scorer import calculate_score, long_term_outlook, dip_buy_status


def resolve_ticker(input_value):
    query = input_value.strip()

    if query.isalpha() and query.isupper() and len(query) <= 5:
        return query.upper()

    try:
        result = search(query)
        quotes = result.get("quotes", [])

        for item in quotes:
            if item.get("quoteType") == "EQUITY":
                return item.get("symbol").upper()
    except:
        pass

    return query.upper()


def analyze_stock(ticker):
    ticker = resolve_ticker(ticker)

    stock = yf.Ticker(ticker)
    data = stock.history(period="3mo")

    if data.empty:
        return None

    price = data["Close"].iloc[-1]
    score, reasons, confidence = calculate_score(data)
    lt_outlook = long_term_outlook(data)
    dip_status = dip_buy_status(data, score, lt_outlook)

    if score >= 75:
        signal = "BUY WATCH"
    elif score >= 60:
        signal = "WATCH"
    elif score >= 45:
        signal = "NEUTRAL"
    else:
        signal = "AVOID"

    return {
        "ticker": ticker,
        "price": round(price, 2),
        "score": score,
        "confidence": confidence,
        "signal": signal,
        "long_term": lt_outlook,
        "dip_status": dip_status,
        "reasons": reasons
    }