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

    if short_ma > long_ma:
        score += 20
        confidence += 10
        reasons.append("short-term trend stronger than 20-day trend")
    else:
        score -= 20
        confidence -= 10
        reasons.append("short-term trend weaker than 20-day trend")

    if rsi < 30:
        score += 20
        confidence += 5
        reasons.append("RSI oversold")
    elif rsi > 70:
        score -= 15
        confidence -= 5
        reasons.append("RSI overbought")
    else:
        reasons.append("RSI normal")

    if close.iloc[-1] > close.iloc[-5]:
        score += 10
        confidence += 5
        reasons.append("price rising vs 5 days ago")
    else:
        confidence -= 5
        reasons.append("price not rising")

    avg_vol = volume.tail(20).mean()
    if volume.iloc[-1] > 1.3 * avg_vol:
        score += 10
        confidence += 10
        reasons.append("volume confirms move")

    return round(max(0, min(100, score)), 1), reasons, round(max(0, min(100, confidence)), 1)


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
    ma20 = close.tail(20).mean()
    ma50 = close.tail(50).mean()
    rsi = get_rsi(close).iloc[-1]

    recent_pullback = price_now < price_5_days_ago
    long_term_intact = price_now >= ma50 * 0.95
    near_ma20 = price_now <= ma20 * 1.03
    not_overbought = rsi < 70

    if recent_pullback and long_term_intact and near_ma20 and not_overbought:
        return "🟢 Dip-Buy Candidate — pullback inside healthy trend"

    if recent_pullback and long_term_intact:
        return "🟡 Possible Dip Setup — wait for stabilization"

    if score >= 80 and not recent_pullback:
        return "⚡ Momentum Setup — strong but not a dip"

    if price_now < ma50 * 0.95:
        return "🔴 Avoid Dip — trend may be breaking"

    return "⚖️ No clear dip setup"