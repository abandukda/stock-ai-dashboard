import numpy as np


def get_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_score(data):
    if len(data) < 20:
        return 0, ["Not enough data"], 0

    close = data["Close"]
    volume = data["Volume"]

    short_ma = close.tail(5).mean()
    long_ma = close.tail(20).mean()
    rsi = get_rsi(close).iloc[-1]

    score = 50
    confidence = 50
    reasons = []

    # Trend
    if short_ma > long_ma:
        score += 20
        confidence += 10
        reasons.append("short-term trend stronger than 20-day trend")
    else:
        score -= 20
        confidence -= 10
        reasons.append("short-term trend weaker than 20-day trend")

    # RSI
    if rsi < 30:
        score += 20
        confidence += 5
        reasons.append("RSI oversold (potential bounce)")
    elif rsi > 70:
        score -= 15
        confidence -= 5
        reasons.append("RSI overbought (risk of pullback)")
    else:
        reasons.append("RSI normal")

    # Momentum
    if close.iloc[-1] > close.iloc[-5]:
        score += 10
        confidence += 5
        reasons.append("price rising vs 5 days ago")
    else:
        confidence -= 5
        reasons.append("price not rising")

    # Volume confirmation
    avg_vol = volume.tail(20).mean()
    if volume.iloc[-1] > 1.3 * avg_vol:
        score += 10
        confidence += 10
        reasons.append("volume spike confirms move")

    score = round(max(0, min(100, score)), 1)
    confidence = round(max(0, min(100, confidence)), 1)

    return score, reasons, confidence


def long_term_outlook(data):
    close = data["Close"]

    if len(close) < 50:
        return "Insufficient data"

    ma50 = close.tail(50).mean()

    if close.iloc[-1] > ma50:
        return "🟢 Strong long-term trend"
    elif close.iloc[-1] > ma50 * 0.95:
        return "🟡 Neutral long-term"
    else:
        return "🔴 Weak long-term trend"


def dip_buy_status(data, score, long_term):
    close = data["Close"]

    if len(close) < 50:
        return "Not enough data"

    price_now = close.iloc[-1]
    price_5_days_ago = close.iloc[-5]
    ma50 = close.tail(50).mean()

    if score < 50 and price_now >= ma50 * 0.95 and price_now < price_5_days_ago:
        return "🟢 Potential dip-buy candidate"

    if score >= 75:
        return "⚡ Momentum setup"

    return "⚖️ No clear dip setup"