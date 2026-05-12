# AI Trading Dashboard V25.4

## Recovery Radar Patch

Add the following sections into your existing:

`app_v25_3_email_test.py`

---

# STEP 1 — ADD IMPORTS

Add near your existing imports:

```python
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
```

---

# STEP 2 — ADD RECOVERY RADAR ENGINE

Place this section ABOVE your dashboard tabs / layout sections.

```python
RECOVERY_TICKERS = [
    "PYPL", "NKE", "DIS", "ADBE", "SNOW", "SBUX", "TGT", "INTC",
    "AMD", "BA", "UPS", "CVS", "WBA", "ELF", "ENPH", "SEDG",
    "TSLA", "SHOP", "SQ", "ROKU", "F", "GM", "PFE", "MRNA"
]


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


@st.cache_data(ttl=3600)
def build_recovery_radar(tickers):
    rows = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")

            if hist.empty or len(hist) < 60:
                continue

            info = stock.info

            price = hist["Close"].iloc[-1]
            low_52 = hist["Low"].min()
            high_52 = hist["High"].max()
            rsi = calc_rsi(hist["Close"]).iloc[-1]

            distance_from_low = ((price - low_52) / low_52) * 100
            upside_to_high = ((high_52 - price) / price) * 100

            change_30d = ((price - hist["Close"].iloc[-22]) / hist["Close"].iloc[-22]) * 100
            change_90d = ((price - hist["Close"].iloc[-63]) / hist["Close"].iloc[-63]) * 100

            market_cap = info.get("marketCap", 0)
            forward_pe = info.get("forwardPE", None)
            target_price = info.get("targetMeanPrice", None)

            analyst_upside = None
```
