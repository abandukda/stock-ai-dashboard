from analyzer import analyze_stock

STOCK_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "AMD", "TSLA", "CRM", "ORCL", "ADBE",
    "AVGO", "QCOM", "INTC", "NOW", "UBER",
    "SHOP", "COST", "HD", "LOW", "UNH",
    "ELF", "SNOW", "PLTR", "PANW", "CRWD"
]

EXCLUDED_TICKERS = {
    "JPM": "Financial company",
    "BAC": "Financial company",
    "WFC": "Financial company",
    "V": "Financial company",
    "MA": "Financial company",
    "AXP": "Financial company",

    "DIS": "Entertainment/media",
    "NFLX": "Entertainment/media",
    "WBD": "Entertainment/media",
    "PARA": "Entertainment/media",

    "MGM": "Gambling",
    "LVS": "Gambling",
    "WYNN": "Gambling",
    "DKNG": "Gambling",

    "BUD": "Alcohol",
    "TAP": "Alcohol",
    "DEO": "Alcohol"
}

MIN_PRICE = 20


def exclusion_reason(ticker):
    ticker = ticker.upper().strip()
    return EXCLUDED_TICKERS.get(ticker)


def scan_market(limit=15):
    results = []

    for ticker in STOCK_UNIVERSE:
        if exclusion_reason(ticker):
            continue

        analysis = analyze_stock(ticker)

        if not analysis:
            continue

        if analysis["price"] < MIN_PRICE:
            continue

        results.append(analysis)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]