#!/usr/bin/env python3
"""
V40.5 Multi-Agent Scanner with 30 Percent Upside Filter
- Keeps Render Cron compatibility
- Keeps DATA_DIR="."
- Preserves V39 dashboard files
- Adds:
  - top_ai_ideas.json
  - watchlist.json
  - watchlist_scan.json
  - recovery_scan.json
- Adds AI reasoning layer and setup buckets:
  - AI Momentum Leader
  - Recovery / Reversal Candidate
  - Quality Watchlist Setup
  - Monitor Only
"""

import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf


DATA_DIR = Path(os.getenv("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
PRESCREEN_FILE = DATA_DIR / "market_prescreen.json"
STATE_FILE = DATA_DIR / "market_scan_state.json"
UNIVERSE_FILE = DATA_DIR / "total_market_universe.json"

TOP_IDEAS_FILE = DATA_DIR / "top_ai_ideas.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
WATCHLIST_SCAN_FILE = DATA_DIR / "watchlist_scan.json"
RECOVERY_SCAN_FILE = DATA_DIR / "recovery_scan.json"

MAX_UNIVERSE = int(os.getenv("MAX_UNIVERSE", "6500"))
MAX_PRESCREEN = int(os.getenv("MAX_PRESCREEN", "650"))
MAX_FULL_SCAN = int(os.getenv("MAX_FULL_SCAN", "150"))
BATCH_SIZE = int(os.getenv("SCAN_BATCH_SIZE", "80"))
SLEEP_BETWEEN_BATCHES = float(os.getenv("SCAN_SLEEP", "1.0"))

MIN_PRICE = float(os.getenv("MIN_PRICE", "2.00"))
MAX_PRICE = float(os.getenv("MAX_PRICE", "1000.00"))
MIN_DOLLAR_VOLUME = float(os.getenv("MIN_DOLLAR_VOLUME", "2500000"))
MIN_MARKET_CAP = float(os.getenv("MIN_MARKET_CAP", "50000000"))

GITHUB_PERSIST = os.getenv("GITHUB_PERSIST", "true").lower() == "true"
GIT_COMMIT_MESSAGE = os.getenv("GIT_COMMIT_MESSAGE", "Update overnight market scan data")

# User preference filter:
# Excludes financial companies, entertainment/gambling/casino names,
# alcohol/tobacco-related industries from all ranked outputs.
EXCLUDED_SECTOR_KEYWORDS = [
    "financial",
    "bank",
    "banks",
    "banking",
    "insurance",
    "capital markets",
    "asset management",
    "credit services",
    "mortgage",
    "reit",
    "entertainment",
    "casino",
    "casinos",
    "gambling",
    "gaming",
    "resort",
    "alcohol",
    "alcoholic",
    "beverages - wineries",
    "brewers",
    "distillers",
    "tobacco",
]

# Price bucket diversity:
# Prevents the Top AI Ideas from being dominated only by high-priced stocks.
# Lower-priced names still must pass liquidity, price, market cap, and AI quality filters.
PRICE_BUCKETS = [
    {"name": "Lower Price", "min": 5.0, "max": 25.0, "target": 7, "min_score": 55},
    {"name": "Mid Price", "min": 25.0, "max": 100.0, "target": 8, "min_score": 55},
    {"name": "Higher Price", "min": 100.0, "max": 100000.0, "target": 10, "min_score": 55},
]

TOP_AI_IDEAS_TARGET = int(os.getenv("TOP_AI_IDEAS_TARGET", "25"))
MIN_UPSIDE_PCT = float(os.getenv("MIN_UPSIDE_PCT", "0.30"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / old * 100.0


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    tmp.replace(path)


def run_cmd(cmd: List[str]) -> Tuple[int, str]:
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
        return result.returncode, result.stdout.strip()
    except Exception as exc:
        return 1, str(exc)


def load_watchlist() -> List[str]:
    default_symbols = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "PLTR", "SOFI"]
    try:
        if not WATCHLIST_FILE.exists():
            write_json(WATCHLIST_FILE, {"symbols": default_symbols, "updated_at": now_iso()})
            return default_symbols

        raw = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        symbols = raw if isinstance(raw, list) else raw.get("symbols", [])
        cleaned = []
        for s in symbols:
            sym = str(s).strip().upper()
            if sym and "." not in sym and "/" not in sym and len(sym) <= 7:
                cleaned.append(sym)
        return list(dict.fromkeys(cleaned)) or default_symbols
    except Exception:
        return default_symbols


def get_yahoo_screeners() -> List[str]:
    screeners = [
        "most_actives", "day_gainers", "day_losers", "growth_technology_stocks",
        "undervalued_growth_stocks", "aggressive_small_caps", "portfolio_anchors",
        "small_cap_gainers",
    ]
    symbols = set()
    for screener in screeners:
        try:
            data = yf.screen(screener, count=250)
            quotes = data.get("quotes", []) if isinstance(data, dict) else []
            for q in quotes:
                sym = q.get("symbol")
                quote_type = q.get("quoteType", "")
                if sym and quote_type in {"EQUITY", "ETF"} and "." not in sym and "/" not in sym and len(sym) <= 7:
                    symbols.add(sym.upper())
        except Exception:
            continue
    return sorted(symbols)


def fallback_universe() -> List[str]:
    symbols = """
AAPL MSFT NVDA AMZN META GOOGL GOOG AVGO TSLA BRK-B JPM LLY V UNH XOM MA COST WMT NFLX ORCL HD PG JNJ ABBV BAC KO PLTR CRM CVX CSCO WFC IBM MRK GE AMD MCD LIN ADBE DIS TMO ABT PM CAT NOW QCOM TXN ISRG AMGN INTU VZ PEP GS RTX BKNG SPGI LOW PFE HON AXON C UNP MS NEE CMCSA AMAT DHR SCHW BLK GILD TJX PANW SYK ADP DE LRCX COP BSX MDLZ ETN CB ADI MMC UPS MU BX REGN FI BMY SO KLAC AMT CME MO ELV WM ICE ANET SHW EQIX PH KKR DUKE APH WELL TT CI MCK CDNS SNPS AON NKE COF USB MMM HCA MSI ITW ZTS CL TDG ORLY EMR MAR PGR ROP AJG ECL APD CTAS WMB CMG CRWD NOC
SNOW DDOG NET MDB SHOP SE MELI UBER ABNB DASH RBLX COIN HOOD ROKU SQ PYPL AFRM SOFI UPST CELH ELF CAVA TOST DUOL HIMS APP ARM SMCI DELL VRT ANF ONON TTD FSLR ENPH RUN ALB RIVN LCID NIO LI XPEV
AEHR ASTS IONQ RKLB SOUN BBAI AI PATH TEM RXRX DNA LMND OPEN ROOT UUUU CCJ SMR OKLO JOBY ACHR ENVX QS STEM CHPT EVGO BLNK
SPY QQQ DIA IWM VTI VOO SCHD JEPI JEPQ QYLD XYLD RYLD TLT HYG LQD XLF XLK XLE XLV XLY XLI XLP XLU XLB XLRE SMH SOXX ARKK TAN BOTZ
"""
    return list(dict.fromkeys([s.strip().upper() for s in symbols.split() if s.strip()]))


def build_universe() -> List[str]:
    symbols = set(fallback_universe())
    symbols.update(get_yahoo_screeners())
    symbols.update(load_watchlist())

    try:
        if UNIVERSE_FILE.exists():
            prior = json.loads(UNIVERSE_FILE.read_text())
            prior_symbols = prior.get("symbols", []) if isinstance(prior, dict) else prior
            for item in prior_symbols:
                sym = item.get("symbol") if isinstance(item, dict) else item
                if sym:
                    symbols.add(str(sym).upper())
    except Exception:
        pass

    clean = []
    for sym in sorted(symbols):
        if "." in sym or "/" in sym or len(sym) > 7:
            continue
        clean.append(sym)
    return clean[:MAX_UNIVERSE]


def download_price_batch(symbols: List[str]) -> pd.DataFrame:
    try:
        return yf.download(
            tickers=" ".join(symbols), period="6mo", interval="1d", group_by="ticker",
            auto_adjust=True, prepost=False, threads=True, progress=False,
        )
    except Exception:
        return pd.DataFrame()


def extract_symbol_history(data: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if symbol not in data.columns.get_level_values(0):
                return pd.DataFrame()
            df = data[symbol].copy()
        else:
            df = data.copy()
        if df.empty or "Close" not in df.columns:
            return pd.DataFrame()
        return df.dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


def get_metadata(symbol: str) -> Dict[str, Any]:
    defaults = {
        "company_name": symbol,
        "sector": "Unknown",
        "industry": "Unknown",
        "market_cap": None,
        "quote_type": "EQUITY",
        "pe_ratio": None,
        "forward_pe": None,
        "peg_ratio": None,
        "price_to_sales": None,
        "price_to_book": None,
        "profit_margin": None,
        "gross_margin": None,
        "operating_margin": None,
        "revenue_growth": None,
        "earnings_growth": None,
        "total_cash": None,
        "total_debt": None,
        "debt_to_equity": None,
        "free_cashflow": None,
        "operating_cashflow": None,
        "current_ratio": None,
        "recommendation": None,
        "target_mean_price": None,
        "target_high_price": None,
        "target_low_price": None,
        "earnings_date": None,
    }

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.get_info() or {}
        name = info.get("shortName") or info.get("longName") or info.get("displayName") or symbol

        earnings_date = None
        try:
            cal = ticker.calendar
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date") or cal.get("EarningsDate")
                if isinstance(ed, list) and ed:
                    earnings_date = str(ed[0])
                elif ed is not None:
                    earnings_date = str(ed)
        except Exception:
            earnings_date = None

        return {
            **defaults,
            "company_name": name if name else symbol,
            "sector": info.get("sector") or info.get("category") or "Unknown",
            "industry": info.get("industry") or info.get("fundFamily") or "Unknown",
            "market_cap": safe_float(info.get("marketCap")),
            "quote_type": info.get("quoteType") or "EQUITY",
            "pe_ratio": safe_float(info.get("trailingPE")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "peg_ratio": safe_float(info.get("pegRatio")),
            "price_to_sales": safe_float(info.get("priceToSalesTrailing12Months")),
            "price_to_book": safe_float(info.get("priceToBook")),
            "profit_margin": safe_float(info.get("profitMargins")),
            "gross_margin": safe_float(info.get("grossMargins")),
            "operating_margin": safe_float(info.get("operatingMargins")),
            "revenue_growth": safe_float(info.get("revenueGrowth")),
            "earnings_growth": safe_float(info.get("earningsGrowth")),
            "total_cash": safe_float(info.get("totalCash")),
            "total_debt": safe_float(info.get("totalDebt")),
            "debt_to_equity": safe_float(info.get("debtToEquity")),
            "free_cashflow": safe_float(info.get("freeCashflow")),
            "operating_cashflow": safe_float(info.get("operatingCashflow")),
            "current_ratio": safe_float(info.get("currentRatio")),
            "recommendation": info.get("recommendationKey") or info.get("recommendationMean"),
            "target_mean_price": safe_float(info.get("targetMeanPrice")),
            "target_high_price": safe_float(info.get("targetHighPrice")),
            "target_low_price": safe_float(info.get("targetLowPrice")),
            "earnings_date": earnings_date,
        }
    except Exception:
        return defaults


def compute_indicators(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if df is None or df.empty or len(df) < 45:
        return None

    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series([0] * len(df), index=df.index)
    high = df["High"].astype(float) if "High" in df.columns else close
    low = df["Low"].astype(float) if "Low" in df.columns else close

    price = safe_float(close.iloc[-1])
    if price is None or price <= 0:
        return None

    sma10 = safe_float(close.rolling(10).mean().iloc[-1])
    sma20 = safe_float(close.rolling(20).mean().iloc[-1])
    sma50 = safe_float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma100 = safe_float(close.rolling(100).mean().iloc[-1]) if len(close) >= 100 else None

    vol20 = safe_float(volume.rolling(20).mean().iloc[-1], 0)
    dollar_volume = price * (vol20 or 0)

    one_day = pct_change(price, safe_float(close.iloc[-2])) if len(close) >= 2 else None
    five_day = pct_change(price, safe_float(close.iloc[-6])) if len(close) >= 6 else None
    twenty_day = pct_change(price, safe_float(close.iloc[-21])) if len(close) >= 21 else None
    sixty_day = pct_change(price, safe_float(close.iloc[-61])) if len(close) >= 61 else None

    rolling_high_20 = safe_float(high.rolling(20).max().iloc[-1])
    rolling_low_20 = safe_float(low.rolling(20).min().iloc[-1])
    rolling_high_60 = safe_float(high.rolling(60).max().iloc[-1]) if len(high) >= 60 else rolling_high_20
    rolling_low_60 = safe_float(low.rolling(60).min().iloc[-1]) if len(low) >= 60 else rolling_low_20

    delta = close.diff()
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)
    avg_gain = gains.rolling(14).mean()
    avg_loss = losses.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = safe_float(100 - (100 / (1 + rs.iloc[-1])), 50)

    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr14 = safe_float(tr.rolling(14).mean().iloc[-1])
    atr_pct = (atr14 / price * 100.0) if atr14 and price else None

    latest_vol = safe_float(volume.iloc[-1], 0)
    volume_ratio = latest_vol / vol20 if vol20 and vol20 > 0 else 1.0

    return {
        "price": round(price, 2),
        "sma10": round(sma10, 2) if sma10 else None,
        "sma20": round(sma20, 2) if sma20 else None,
        "sma50": round(sma50, 2) if sma50 else None,
        "sma100": round(sma100, 2) if sma100 else None,
        "avg_volume_20d": safe_int(vol20, 0),
        "dollar_volume": round(dollar_volume, 2),
        "one_day_pct": round(one_day, 2) if one_day is not None else None,
        "five_day_pct": round(five_day, 2) if five_day is not None else None,
        "twenty_day_pct": round(twenty_day, 2) if twenty_day is not None else None,
        "sixty_day_pct": round(sixty_day, 2) if sixty_day is not None else None,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "atr14": round(atr14, 2) if atr14 else None,
        "atr_pct": round(atr_pct, 2) if atr_pct else None,
        "volume_ratio": round(volume_ratio, 2),
        "rolling_high_20": round(rolling_high_20, 2) if rolling_high_20 else None,
        "rolling_low_20": round(rolling_low_20, 2) if rolling_low_20 else None,
        "rolling_high_60": round(rolling_high_60, 2) if rolling_high_60 else None,
        "rolling_low_60": round(rolling_low_60, 2) if rolling_low_60 else None,
        "distance_from_20_high": round(pct_change(price, rolling_high_20), 2) if rolling_high_20 else None,
        "distance_from_60_high": round(pct_change(price, rolling_high_60), 2) if rolling_high_60 else None,
        "distance_above_20_low": round(pct_change(price, rolling_low_20), 2) if rolling_low_20 else None,
    }


def score_stock(ind: Dict[str, Any], meta: Dict[str, Any]) -> Tuple[int, List[str], List[str]]:
    score = 0
    good, risks = [], []

    price, sma20, sma50, sma100 = ind.get("price"), ind.get("sma20"), ind.get("sma50"), ind.get("sma100")
    rsi, vol_ratio = ind.get("rsi"), ind.get("volume_ratio") or 1
    dollar_volume, market_cap = ind.get("dollar_volume") or 0, meta.get("market_cap")
    one, five, twenty, sixty = ind.get("one_day_pct"), ind.get("five_day_pct"), ind.get("twenty_day_pct"), ind.get("sixty_day_pct")
    dist20h, dist60h, atr_pct = ind.get("distance_from_20_high"), ind.get("distance_from_60_high"), ind.get("atr_pct")

    if dollar_volume >= 100_000_000:
        score += 12; good.append("Strong liquidity")
    elif dollar_volume >= 25_000_000:
        score += 9; good.append("Good liquidity")
    elif dollar_volume >= MIN_DOLLAR_VOLUME:
        score += 5
    else:
        score -= 20; risks.append("Weak dollar volume")

    if market_cap and market_cap >= 10_000_000_000:
        score += 8
    elif market_cap and market_cap >= 1_000_000_000:
        score += 5
    elif market_cap and market_cap < MIN_MARKET_CAP:
        score -= 15; risks.append("Very small market cap")

    if price and sma20 and price > sma20:
        score += 10; good.append("Price is above the 20-day trend")
    else:
        score -= 8; risks.append("Price is below the 20-day trend")

    if price and sma50 and price > sma50:
        score += 12; good.append("Price is above the 50-day trend")
    else:
        score -= 8; risks.append("Price is below or near the 50-day trend")

    if sma20 and sma50 and sma20 > sma50:
        score += 8; good.append("Short-term trend is above intermediate trend")
    elif sma20 and sma50:
        score -= 5

    if sma50 and sma100 and sma50 > sma100:
        score += 6

    if five is not None:
        if 1 <= five <= 12:
            score += 12; good.append("Healthy 5-day momentum")
        elif five > 18:
            score -= 6; risks.append("Short-term move may be extended")
        elif five < -4:
            score -= 8; risks.append("Recent momentum is weak")

    if twenty is not None:
        if 2 <= twenty <= 25:
            score += 14; good.append("Positive 20-day momentum")
        elif twenty > 35:
            score -= 7; risks.append("20-day move is stretched")
        elif twenty < -8:
            score -= 10; risks.append("20-day trend is negative")

    if sixty is not None:
        if 5 <= sixty <= 45:
            score += 9
        elif sixty > 75:
            score -= 5; risks.append("Longer move may be overextended")
        elif sixty < -12:
            score -= 3

    # Recovery bonus: beaten down but stabilizing.
    if dist60h is not None and dist60h < -20 and rsi and 42 <= rsi <= 62 and twenty is not None and twenty > -5:
        score += 10
        good.append("Recovery setup: still below prior highs but stabilizing")

    if rsi is not None:
        if 48 <= rsi <= 68:
            score += 12; good.append("RSI constructive, not overheated")
        elif 68 < rsi <= 76:
            score += 4; risks.append("RSI is warm; avoid chasing")
        elif rsi > 76:
            score -= 10; risks.append("RSI is overbought")
        elif 35 <= rsi < 48:
            score += 2; risks.append("RSI still needs confirmation")
        else:
            score -= 8; risks.append("RSI is weak")

    if vol_ratio >= 2.0:
        score += 10; good.append("Volume is meaningfully above average")
    elif vol_ratio >= 1.25:
        score += 6; good.append("Volume is above average")
    elif vol_ratio < 0.65:
        score -= 5; risks.append("Volume confirmation is light")

    if dist20h is not None:
        if -8 <= dist20h <= -1:
            score += 8; good.append("Near recent highs without being fully extended")
        elif -1 < dist20h <= 1:
            score += 5; good.append("Testing recent highs")
        elif dist20h < -18:
            score -= 3; risks.append("Still far from recent highs")

    if atr_pct is not None:
        if 1 <= atr_pct <= 5:
            score += 7; good.append("Volatility is tradable")
        elif atr_pct > 9:
            score -= 8; risks.append("High volatility could make stops difficult")

    if one is not None and one < -6:
        score -= 10; risks.append("Sharp down day needs confirmation")
    elif one is not None and one > 12:
        score -= 5; risks.append("Large one-day jump may pull back")

    return int(max(1, min(99, round(score)))), good[:6], risks[:6]


def classify_setup(ind: Dict[str, Any], score: int) -> str:
    price, sma20, sma50 = ind.get("price"), ind.get("sma20"), ind.get("sma50")
    rsi, twenty, sixty = ind.get("rsi") or 50, ind.get("twenty_day_pct") or 0, ind.get("sixty_day_pct") or 0
    dist60h, volume_ratio = ind.get("distance_from_60_high"), ind.get("volume_ratio") or 1

    if price and sma20 and sma50 and price > sma20 > sma50 and score >= 65:
        return "AI Momentum Leader"
    if price and sma20 and price > sma20 and sixty < -8 and rsi >= 42 and volume_ratio >= 0.9:
        return "Recovery / Reversal Candidate"
    if dist60h is not None and dist60h < -20 and rsi >= 45 and twenty > -5:
        return "Recovery / Reversal Candidate"
    if score >= 55:
        return "Quality Watchlist Setup"
    return "Monitor Only"


def build_trade_plan(ind: Dict[str, Any]) -> Dict[str, Any]:
    price = ind.get("price")
    if not price:
        return {}

    atr = ind.get("atr14") or (price * 0.035)
    sma20 = ind.get("sma20")
    high20 = ind.get("rolling_high_20")

    lower_entry = max(price - atr * 0.5, price * 0.96)
    upper_entry = min(price + atr * 0.25, price * 1.03)
    support_anchor = sma20 if sma20 and sma20 < price else price - atr
    stop_loss = min(price - atr * 1.4, support_anchor - atr * 0.35)
    stop_loss = max(stop_loss, price * 0.80)

    risk = max(price - stop_loss, price * 0.02)
    target_1 = price + risk * 1.8
    target_2 = price + risk * 2.7
    if high20 and high20 > price:
        target_1 = max(target_1, high20 * 1.01)

    # User preference: only track ideas where the planned target has meaningful upside.
    target_1 = max(target_1, price * (1 + MIN_UPSIDE_PCT))
    target_2 = max(target_2, price * (1 + max(MIN_UPSIDE_PCT + 0.15, 0.45)))

    rr = (target_1 - price) / risk if risk > 0 else None

    return {
        "entry_range": f"${lower_entry:.2f} - ${upper_entry:.2f}",
        "entry_low": round(lower_entry, 2),
        "entry_high": round(upper_entry, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target_1, 2),
        "target_2": round(target_2, 2),
        "target_upside_pct": round(((target_1 - price) / price) * 100, 2) if price else None,
        "risk_reward": round(rr, 2) if rr else None,
        "risk_reward_explanation": f"Approximate first target offers about {rr:.1f}:1 reward-to-risk." if rr else "",
    }



# =========================
# MULTI-AGENT ANALYSIS LAYER
# =========================

def fmt_money(value: Any) -> str:
    try:
        value = float(value)
        if abs(value) >= 1_000_000_000_000:
            return f"${value/1_000_000_000_000:.1f}T"
        if abs(value) >= 1_000_000_000:
            return f"${value/1_000_000_000:.1f}B"
        if abs(value) >= 1_000_000:
            return f"${value/1_000_000:.1f}M"
        return f"${value:,.0f}"
    except Exception:
        return "N/A"


def fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "N/A"


def clamp_score(score: float) -> int:
    return int(max(0, min(100, round(score))))


def technical_agent(ind: Dict[str, Any]) -> Dict[str, Any]:
    score = 0
    positives, risks = [], []

    price = ind.get("price")
    sma20 = ind.get("sma20")
    sma50 = ind.get("sma50")
    sma100 = ind.get("sma100")
    rsi = ind.get("rsi")
    five = ind.get("five_day_pct")
    twenty = ind.get("twenty_day_pct")
    sixty = ind.get("sixty_day_pct")
    volume_ratio = ind.get("volume_ratio") or 1
    atr_pct = ind.get("atr_pct")

    if price and sma20 and price > sma20:
        score += 18; positives.append("price is above the 20-day trend")
    else:
        risks.append("price is not clearly above the 20-day trend")

    if price and sma50 and price > sma50:
        score += 20; positives.append("price is above the 50-day trend")
    else:
        risks.append("price is below or near the 50-day trend")

    if sma20 and sma50 and sma20 > sma50:
        score += 12; positives.append("20-day average is above the 50-day average")

    if sma50 and sma100 and sma50 > sma100:
        score += 8; positives.append("50-day trend is stronger than the 100-day trend")

    if five is not None and 1 <= five <= 12:
        score += 10; positives.append(f"healthy 5-day momentum of {five}%")
    elif five is not None and five < -4:
        score -= 8; risks.append(f"weak 5-day momentum of {five}%")

    if twenty is not None and 2 <= twenty <= 25:
        score += 14; positives.append(f"positive 20-day momentum of {twenty}%")
    elif twenty is not None and twenty < -8:
        score -= 10; risks.append(f"negative 20-day move of {twenty}%")

    if rsi is not None and 48 <= rsi <= 68:
        score += 12; positives.append(f"RSI is constructive at {rsi}, not overheated")
    elif rsi is not None and rsi > 76:
        score -= 12; risks.append(f"RSI is overbought at {rsi}")
    elif rsi is not None and rsi < 40:
        score -= 8; risks.append(f"RSI is weak at {rsi}")

    if volume_ratio >= 1.25:
        score += 10; positives.append(f"volume is confirming at {volume_ratio}x average")
    elif volume_ratio < 0.65:
        score -= 5; risks.append("volume confirmation is light")

    if atr_pct is not None and 1 <= atr_pct <= 6:
        score += 6; positives.append(f"ATR volatility is tradable at {atr_pct}%")
    elif atr_pct is not None and atr_pct > 9:
        score -= 8; risks.append(f"volatility is high at {atr_pct}% ATR")

    return {
        "name": "Technical Momentum Agent",
        "score": clamp_score(score),
        "positives": positives[:6],
        "risks": risks[:6],
        "summary": "Reviews trend, momentum, RSI, volume confirmation, and volatility."
    }


def fundamentals_agent(meta: Dict[str, Any]) -> Dict[str, Any]:
    score = 0
    positives, risks = [], []

    revenue_growth = meta.get("revenue_growth")
    earnings_growth = meta.get("earnings_growth")
    profit_margin = meta.get("profit_margin")
    gross_margin = meta.get("gross_margin")
    fcf = meta.get("free_cashflow")
    ocf = meta.get("operating_cashflow")
    cash = meta.get("total_cash")
    debt = meta.get("total_debt")
    current_ratio = meta.get("current_ratio")

    if revenue_growth is not None:
        if revenue_growth > 0.15:
            score += 18; positives.append(f"strong revenue growth at {fmt_pct(revenue_growth)}")
        elif revenue_growth > 0:
            score += 10; positives.append(f"positive revenue growth at {fmt_pct(revenue_growth)}")
        else:
            score -= 10; risks.append(f"negative/weak revenue growth at {fmt_pct(revenue_growth)}")

    if earnings_growth is not None:
        if earnings_growth > 0.10:
            score += 14; positives.append(f"earnings growth is positive at {fmt_pct(earnings_growth)}")
        elif earnings_growth < 0:
            score -= 8; risks.append(f"earnings growth is negative at {fmt_pct(earnings_growth)}")

    if profit_margin is not None:
        if profit_margin > 0.15:
            score += 16; positives.append(f"healthy profit margin at {fmt_pct(profit_margin)}")
        elif profit_margin > 0:
            score += 8; positives.append(f"profitable with {fmt_pct(profit_margin)} margin")
        else:
            score -= 14; risks.append("not currently profitable")

    if gross_margin is not None and gross_margin > 0.40:
        score += 8; positives.append(f"strong gross margin at {fmt_pct(gross_margin)}")

    if fcf is not None:
        if fcf > 0:
            score += 16; positives.append(f"positive free cash flow of {fmt_money(fcf)}")
        else:
            score -= 10; risks.append(f"negative free cash flow of {fmt_money(fcf)}")

    if ocf is not None and ocf > 0:
        score += 8; positives.append(f"positive operating cash flow of {fmt_money(ocf)}")

    if cash is not None and debt is not None:
        if cash > debt:
            score += 14; positives.append(f"cash exceeds debt: {fmt_money(cash)} cash vs {fmt_money(debt)} debt")
        elif debt > cash * 2:
            score -= 10; risks.append(f"debt is much higher than cash: {fmt_money(debt)} debt vs {fmt_money(cash)} cash")
        else:
            score += 4; positives.append(f"cash/debt is manageable: {fmt_money(cash)} cash vs {fmt_money(debt)} debt")

    if current_ratio is not None:
        if current_ratio >= 1.2:
            score += 6; positives.append(f"current ratio is acceptable at {current_ratio:.2f}")
        elif current_ratio < 1:
            score -= 6; risks.append(f"current ratio is below 1.0 at {current_ratio:.2f}")

    return {
        "name": "Fundamentals Quality Agent",
        "score": clamp_score(score),
        "positives": positives[:6],
        "risks": risks[:6],
        "summary": "Reviews growth, profitability, cash flow, cash balance, debt, and balance-sheet quality."
    }


def valuation_agent(meta: Dict[str, Any], ind: Dict[str, Any]) -> Dict[str, Any]:
    score = 50
    positives, risks = [], []

    pe = meta.get("pe_ratio")
    fpe = meta.get("forward_pe")
    peg = meta.get("peg_ratio")
    ps = meta.get("price_to_sales")
    pb = meta.get("price_to_book")
    target = meta.get("target_mean_price")
    price = ind.get("price")

    if pe is not None:
        if 0 < pe < 25:
            score += 12; positives.append(f"P/E looks reasonable at {pe:.1f}")
        elif pe > 60:
            score -= 12; risks.append(f"P/E is expensive at {pe:.1f}")

    if fpe is not None:
        if 0 < fpe < 30:
            score += 10; positives.append(f"forward P/E is reasonable at {fpe:.1f}")
        elif fpe > 70:
            score -= 8; risks.append(f"forward P/E is expensive at {fpe:.1f}")

    if peg is not None:
        if 0 < peg < 1.5:
            score += 8; positives.append(f"PEG is attractive at {peg:.2f}")
        elif peg > 3:
            score -= 6; risks.append(f"PEG is rich at {peg:.2f}")

    if ps is not None:
        if ps < 5:
            score += 8; positives.append(f"price/sales is not excessive at {ps:.1f}")
        elif ps > 15:
            score -= 8; risks.append(f"price/sales is rich at {ps:.1f}")

    if pb is not None:
        if 0 < pb < 5:
            score += 4; positives.append(f"price/book is reasonable at {pb:.1f}")
        elif pb > 12:
            score -= 4; risks.append(f"price/book is elevated at {pb:.1f}")

    if price and target:
        upside = (target - price) / price * 100
        if upside > 20:
            score += 10; positives.append(f"analyst mean target implies {upside:.1f}% upside")
        elif upside < 0:
            score -= 8; risks.append(f"analyst mean target is below current price by {abs(upside):.1f}%")

    if not positives and not risks:
        risks.append("valuation data is limited, so this agent cannot strongly confirm value")

    return {
        "name": "Valuation Agent",
        "score": clamp_score(score),
        "positives": positives[:6],
        "risks": risks[:6],
        "summary": "Reviews P/E, forward P/E, PEG, sales/book valuation, and analyst target upside."
    }


def risk_agent(meta: Dict[str, Any], ind: Dict[str, Any]) -> Dict[str, Any]:
    score = 70
    positives, risks = [], []

    market_cap = meta.get("market_cap")
    dollar_volume = ind.get("dollar_volume") or 0
    atr_pct = ind.get("atr_pct")
    one_day = ind.get("one_day_pct")
    rsi = ind.get("rsi")
    debt = meta.get("total_debt")
    cash = meta.get("total_cash")

    if market_cap and market_cap >= 10_000_000_000:
        score += 8; positives.append("large-cap liquidity reduces execution risk")
    elif market_cap and market_cap < 300_000_000:
        score -= 15; risks.append("small market cap increases volatility and liquidity risk")

    if dollar_volume >= 100_000_000:
        score += 10; positives.append("very strong dollar volume")
    elif dollar_volume < 5_000_000:
        score -= 12; risks.append("low dollar volume can make entries/exits difficult")

    if atr_pct is not None:
        if atr_pct > 9:
            score -= 14; risks.append(f"ATR volatility is high at {atr_pct}%")
        elif 1 <= atr_pct <= 5:
            score += 8; positives.append(f"volatility is tradable at {atr_pct}% ATR")

    if one_day is not None and one_day > 12:
        score -= 8; risks.append("large one-day move can mean chasing risk")
    if one_day is not None and one_day < -8:
        score -= 10; risks.append("sharp down day needs confirmation")

    if rsi is not None and rsi > 76:
        score -= 8; risks.append("overbought RSI raises pullback risk")

    if cash is not None and debt is not None and debt > cash * 2:
        score -= 8; risks.append("debt is much higher than cash")

    return {
        "name": "Risk Management Agent",
        "score": clamp_score(score),
        "positives": positives[:6],
        "risks": risks[:6],
        "summary": "Reviews liquidity, market cap, volatility, debt/cash risk, and chasing risk."
    }


def catalyst_agent(meta: Dict[str, Any], ind: Dict[str, Any], setup_type: str) -> Dict[str, Any]:
    score = 50
    positives, risks = [], []

    earnings_date = meta.get("earnings_date")
    recommendation = meta.get("recommendation")
    target = meta.get("target_mean_price")
    price = ind.get("price")
    dist60 = ind.get("distance_from_60_high")
    sixty = ind.get("sixty_day_pct")
    twenty = ind.get("twenty_day_pct")

    if earnings_date:
        positives.append(f"earnings date available: {earnings_date}")
        risks.append("earnings can create gap risk; avoid oversized positions before the report")

    if recommendation:
        positives.append(f"analyst recommendation signal: {recommendation}")

    if price and target and target > price:
        upside = (target - price) / price * 100
        if upside > 15:
            score += 12; positives.append(f"analyst target implies {upside:.1f}% potential upside")

    if "Recovery" in setup_type:
        score += 10
        positives.append("classified as a recovery/reversal setup")
        if sixty is not None and sixty < -10:
            positives.append(f"60-day decline of {sixty}% creates recovery potential if reversal confirms")
        if dist60 is not None:
            positives.append(f"currently {dist60}% from 60-day high")

    if twenty is not None and twenty < -8:
        score -= 8; risks.append("20-day trend is still negative, so recovery needs confirmation")

    if not positives:
        risks.append("no clear catalyst detected from available data")

    return {
        "name": "Catalyst & Earnings Agent",
        "score": clamp_score(score),
        "positives": positives[:6],
        "risks": risks[:6],
        "summary": "Reviews earnings timing, analyst target upside, recovery context, and catalyst/risk events."
    }


def final_decision_agent(agent_results: Dict[str, Dict[str, Any]], setup_type: str) -> Dict[str, Any]:
    weights = {
        "technical": 0.32,
        "fundamentals": 0.22,
        "valuation": 0.14,
        "risk": 0.18,
        "catalyst": 0.14,
    }

    final_score = 0
    for key, weight in weights.items():
        final_score += agent_results[key]["score"] * weight

    final_score = clamp_score(final_score)

    if final_score >= 80:
        rating = "Elite Candidate"
        action = "High-priority research candidate. Still wait for clean entry and validate news/earnings."
    elif final_score >= 70:
        rating = "Strong Candidate"
        action = "Good candidate for focused research. Watch entry range and stop discipline."
    elif final_score >= 60:
        rating = "Moderate Candidate"
        action = "Interesting, but needs stronger confirmation or better risk/reward."
    elif final_score >= 50:
        rating = "Watchlist Only"
        action = "Monitor only. Do not force a trade unless setup improves."
    else:
        rating = "Avoid / Low Priority"
        action = "Low-quality setup based on current agent review."

    return {
        "final_agent_score": final_score,
        "decision_rating": rating,
        "decision_action": action,
        "agent_weights": weights,
    }


def run_agent_team(symbol: str, meta: Dict[str, Any], ind: Dict[str, Any], setup_type: str) -> Dict[str, Any]:
    agents = {
        "technical": technical_agent(ind),
        "fundamentals": fundamentals_agent(meta),
        "valuation": valuation_agent(meta, ind),
        "risk": risk_agent(meta, ind),
        "catalyst": catalyst_agent(meta, ind, setup_type),
    }
    decision = final_decision_agent(agents, setup_type)
    return {"agents": agents, **decision}


def build_ai_reasoning(symbol: str, meta: Dict[str, Any], ind: Dict[str, Any], score: int, setup_type: str, good: List[str], risks: List[str], plan: Dict[str, Any]) -> Dict[str, Any]:
    company = meta.get("company_name", symbol)
    sector = meta.get("sector", "Unknown")
    industry = meta.get("industry", "Unknown")
    price = ind.get("price")
    rsi = ind.get("rsi")
    five = ind.get("five_day_pct")
    twenty = ind.get("twenty_day_pct")
    sixty = ind.get("sixty_day_pct")
    volume_ratio = ind.get("volume_ratio")

    agent_team = run_agent_team(symbol, meta, ind, setup_type)
    agents = agent_team["agents"]
    final_agent_score = agent_team["final_agent_score"]
    decision_rating = agent_team["decision_rating"]
    decision_action = agent_team["decision_action"]

    technical = agents["technical"]
    fundamentals = agents["fundamentals"]
    valuation = agents["valuation"]
    risk = agents["risk"]
    catalyst = agents["catalyst"]

    why = (
        f"The AI agent team ranks this as {decision_rating}. "
        f"Technical score {technical['score']}/100, fundamentals score {fundamentals['score']}/100, "
        f"valuation score {valuation['score']}/100, risk score {risk['score']}/100, "
        f"and catalyst score {catalyst['score']}/100. {decision_action}"
    )

    trade_plan = (
        f"Preferred entry range: {plan.get('entry_range')}. "
        f"Suggested stop loss: ${plan.get('stop_loss')}. "
        f"First target: ${plan.get('target')}. Stretch target: ${plan.get('target_2')}. "
        f"Risk/reward: {plan.get('risk_reward')}x. {plan.get('risk_reward_explanation')}"
    )

    positives = []
    risks_all = []
    for key in ["technical", "fundamentals", "valuation", "risk", "catalyst"]:
        positives.extend(agents[key].get("positives", []))
        risks_all.extend(agents[key].get("risks", []))

    good_text = "; ".join(positives[:8]) if positives else "Needs stronger confirmation."
    risk_text = "; ".join(risks_all[:8]) if risks_all else "No major red flags detected from available data."

    financial_summary = (
        f"Cash: {fmt_money(meta.get('total_cash'))}. Debt: {fmt_money(meta.get('total_debt'))}. "
        f"Free cash flow: {fmt_money(meta.get('free_cashflow'))}. Operating cash flow: {fmt_money(meta.get('operating_cashflow'))}. "
        f"P/E: {meta.get('pe_ratio') if meta.get('pe_ratio') is not None else 'N/A'}. "
        f"Forward P/E: {meta.get('forward_pe') if meta.get('forward_pe') is not None else 'N/A'}. "
        f"Revenue growth: {fmt_pct(meta.get('revenue_growth'))}. Profit margin: {fmt_pct(meta.get('profit_margin'))}."
    )

    recovery_catalyst = " ".join(catalyst.get("positives", []) + catalyst.get("risks", []))
    if not recovery_catalyst:
        recovery_catalyst = "No strong recovery or earnings catalyst detected from available data."

    reasoning = (
        f"{company} ({symbol}) is classified as {setup_type} with final AI agent score {final_agent_score}/100. "
        f"{why} It operates in {sector} / {industry}. Current price is ${price}; RSI is {rsi}; "
        f"5-day move is {five}%, 20-day move is {twenty}%, and 60-day move is {sixty}%. "
        f"Volume is {volume_ratio}x average. {trade_plan} "
        f"Financial review: {financial_summary} "
        f"Best supporting evidence: {good_text}. Main risks: {risk_text}."
    )

    return {
        "why_ranked_high": why,
        "what_looks_good": good_text,
        "what_could_go_wrong": risk_text,
        "guidance": reasoning,
        "ai_reasoning": reasoning,
        "trade_plan": trade_plan,
        "financial_summary": financial_summary,
        "financial_safety": decision_rating,
        "financial_score": fundamentals["score"],
        "recovery_catalyst": recovery_catalyst,
        "agent_team": agent_team,
        "technical_agent_score": technical["score"],
        "fundamentals_agent_score": fundamentals["score"],
        "valuation_agent_score": valuation["score"],
        "risk_agent_score": risk["score"],
        "catalyst_agent_score": catalyst["score"],
        "final_agent_score": final_agent_score,
        "decision_rating": decision_rating,
        "decision_action": decision_action,
        "action_note": "This is research guidance only, not a buy/sell order. Validate current news, earnings date, and market conditions before investing.",
    }


def make_row(symbol: str, meta: Dict[str, Any], ind: Dict[str, Any], score: int, good: List[str], risks: List[str]) -> Dict[str, Any]:
    plan = build_trade_plan(ind)
    setup_type = classify_setup(ind, score)
    guidance = build_ai_reasoning(symbol, meta, ind, score, setup_type, good, risks, plan)

    row = {
        "symbol": symbol, "ticker": symbol,
        "company": meta.get("company_name", symbol), "company_name": meta.get("company_name", symbol), "name": meta.get("company_name", symbol),
        "sector": meta.get("sector", "Unknown"), "industry": meta.get("industry", "Unknown"),
        "market_cap": meta.get("market_cap"), "quote_type": meta.get("quote_type", "EQUITY"),
        "pe_ratio": meta.get("pe_ratio"),
        "forward_pe": meta.get("forward_pe"),
        "peg_ratio": meta.get("peg_ratio"),
        "price_to_sales": meta.get("price_to_sales"),
        "price_to_book": meta.get("price_to_book"),
        "profit_margin": meta.get("profit_margin"),
        "gross_margin": meta.get("gross_margin"),
        "operating_margin": meta.get("operating_margin"),
        "revenue_growth": meta.get("revenue_growth"),
        "earnings_growth": meta.get("earnings_growth"),
        "total_cash": meta.get("total_cash"),
        "total_debt": meta.get("total_debt"),
        "debt_to_equity": meta.get("debt_to_equity"),
        "free_cashflow": meta.get("free_cashflow"),
        "operating_cashflow": meta.get("operating_cashflow"),
        "current_ratio": meta.get("current_ratio"),
        "recommendation": meta.get("recommendation"),
        "target_mean_price": meta.get("target_mean_price"),
        "target_high_price": meta.get("target_high_price"),
        "target_low_price": meta.get("target_low_price"),
        "earnings_date": meta.get("earnings_date"),
        "price": ind.get("price"), "current_price": ind.get("price"), "last_price": ind.get("price"),
        "avg_volume_20d": ind.get("avg_volume_20d"), "dollar_volume": ind.get("dollar_volume"), "volume_ratio": ind.get("volume_ratio"),
        "conviction": score, "conviction_score": score, "score": score, "ai_score": score,
        "setup_type": setup_type, "bucket": setup_type,
        "price_bucket": price_bucket_name(ind.get("price")),
        "rsi": ind.get("rsi"), "atr14": ind.get("atr14"), "atr_pct": ind.get("atr_pct"),
        "sma10": ind.get("sma10"), "sma20": ind.get("sma20"), "sma50": ind.get("sma50"), "sma100": ind.get("sma100"),
        "one_day_pct": ind.get("one_day_pct"), "five_day_pct": ind.get("five_day_pct"),
        "twenty_day_pct": ind.get("twenty_day_pct"), "sixty_day_pct": ind.get("sixty_day_pct"),
        "entry_range": plan.get("entry_range"), "entry_low": plan.get("entry_low"), "entry_high": plan.get("entry_high"),
        "stop_loss": plan.get("stop_loss"), "target": plan.get("target"), "target_2": plan.get("target_2"),
        "risk_reward": plan.get("risk_reward"),
        "target_upside_pct": plan.get("target_upside_pct"),
        "minimum_upside_required_pct": round(MIN_UPSIDE_PCT * 100, 1), "risk_reward_explanation": plan.get("risk_reward_explanation"),
        "setup_tags": good, "risk_tags": risks, "scan_time": now_iso(),
        **guidance,
        "summary": guidance.get("guidance"), "ai_guidance": guidance.get("guidance"),
    }
    return row



def is_excluded_by_user_preference(symbol: str, meta: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Exclude user-restricted sectors/industries:
    - Financial companies
    - Entertainment/gambling/casinos
    - Alcohol/tobacco-related industries

    ETFs are generally not excluded because their sector/industry fields can be
    unavailable and they may be useful for market context.
    """
    quote_type = str(meta.get("quote_type") or "").upper()
    if quote_type in {"ETF", "MUTUALFUND", "INDEX"}:
        return False, ""

    sector = str(meta.get("sector") or "")
    industry = str(meta.get("industry") or "")
    company = str(meta.get("company_name") or symbol or "")

    combined = f"{sector} {industry} {company}".lower()

    for keyword in EXCLUDED_SECTOR_KEYWORDS:
        if keyword.lower() in combined:
            return True, keyword

    return False, ""


def passes_basic_filter(ind: Dict[str, Any], meta: Dict[str, Any]) -> bool:
    price = ind.get("price")
    if price is None or price < MIN_PRICE or price > MAX_PRICE:
        return False
    if (ind.get("dollar_volume") or 0) < MIN_DOLLAR_VOLUME:
        return False
    market_cap = meta.get("market_cap")
    if market_cap is not None and market_cap < MIN_MARKET_CAP:
        return False
    if ind.get("sma20") is None or ind.get("sma50") is None:
        return False
    return True




def row_has_min_upside(row: Dict[str, Any]) -> bool:
    try:
        price = safe_float(row.get("price") or row.get("current_price"))
        target = safe_float(row.get("target") or row.get("Target / Sell Zone"))
        if not price or not target:
            return False
        return ((target - price) / price) >= MIN_UPSIDE_PCT
    except Exception:
        return False


def price_bucket_name(price: Any) -> str:
    p = safe_float(price)
    if p is None:
        return "Unknown"
    for bucket in PRICE_BUCKETS:
        if bucket["min"] <= p < bucket["max"]:
            return bucket["name"]
    return "Unknown"


def build_diversified_top_ideas(rows: List[Dict[str, Any]], target_count: int = TOP_AI_IDEAS_TARGET) -> List[Dict[str, Any]]:
    """
    Creates a more useful top list by price bucket:
    - Lower Price: $5–$25
    - Mid Price: $25–$100
    - Higher Price: $100+

    This prevents the top list from showing only expensive mega-cap names.
    It does NOT allow weak rows: every selected row still needs a valid price,
    liquidity, and minimum AI score.
    """
    if not rows:
        return []

    clean = []
    for row in rows:
        price = safe_float(row.get("price") or row.get("current_price"))
        score = safe_float(row.get("conviction") or row.get("final_agent_score") or row.get("score"), 0)
        if price is None or price <= 0:
            continue
        if price < 5:
            continue
        if score < 50:
            continue
        row["price_bucket"] = price_bucket_name(price)
        clean.append(row)

    clean.sort(key=lambda r: (
        safe_float(r.get("conviction") or r.get("final_agent_score") or r.get("score"), 0),
        safe_float(r.get("dollar_volume"), 0),
    ), reverse=True)

    selected = []
    used = set()

    for bucket in PRICE_BUCKETS:
        bucket_rows = [
            r for r in clean
            if r.get("price_bucket") == bucket["name"]
            and safe_float(r.get("conviction") or r.get("final_agent_score") or r.get("score"), 0) >= bucket["min_score"]
        ]
        bucket_rows.sort(key=lambda r: (
            safe_float(r.get("conviction") or r.get("final_agent_score") or r.get("score"), 0),
            safe_float(r.get("dollar_volume"), 0),
        ), reverse=True)

        for row in bucket_rows[:bucket["target"]]:
            sym = row.get("symbol") or row.get("ticker")
            if sym and sym not in used:
                selected.append(row)
                used.add(sym)

    # Fill remaining slots with best overall names if any bucket is thin.
    for row in clean:
        sym = row.get("symbol") or row.get("ticker")
        if sym and sym not in used:
            selected.append(row)
            used.add(sym)
        if len(selected) >= target_count:
            break

    selected = selected[:target_count]

    # Add rank labels after final ordering.
    for i, row in enumerate(selected, start=1):
        row["top_ai_rank"] = i
        row["top_ai_bucket_note"] = f"{row.get('price_bucket', 'Unknown')} bucket candidate"

    return selected


def scan_market() -> Dict[str, Any]:
    started = time.time()
    universe = build_universe()
    write_json(UNIVERSE_FILE, {"generated_at": now_iso(), "count": len(universe), "symbols": universe})

    metadata_cache, prescreen_rows, full_rows = {}, [], []

    for i in range(0, len(universe), BATCH_SIZE):
        batch = universe[i:i + BATCH_SIZE]
        data = download_price_batch(batch)

        for symbol in batch:
            hist = extract_symbol_history(data, symbol)
            ind = compute_indicators(hist)
            if not ind:
                continue
            if ind.get("price") is None or ind.get("price") < MIN_PRICE:
                continue
            if (ind.get("dollar_volume") or 0) < MIN_DOLLAR_VOLUME:
                continue

            meta = metadata_cache.get(symbol)
            if meta is None:
                meta = get_metadata(symbol)
                metadata_cache[symbol] = meta

            excluded, exclusion_reason = is_excluded_by_user_preference(symbol, meta)
            if excluded:
                continue

            if not passes_basic_filter(ind, meta):
                continue

            score, good, risks = score_stock(ind, meta)
            row = make_row(symbol, meta, ind, score, good, risks)

            if score >= 38:
                prescreen_rows.append(row)
            if score >= 45:
                full_rows.append(row)

        print(f"Scanned {min(i + BATCH_SIZE, len(universe))}/{len(universe)}; prescreen={len(prescreen_rows)} full={len(full_rows)}")
        if SLEEP_BETWEEN_BATCHES > 0:
            time.sleep(SLEEP_BETWEEN_BATCHES)

    prescreen_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("dollar_volume") or 0), reverse=True)
    full_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("dollar_volume") or 0), reverse=True)

    prescreen_rows = prescreen_rows[:MAX_PRESCREEN]
    full_rows = full_rows[:MAX_FULL_SCAN]

    if len(full_rows) < min(25, MAX_FULL_SCAN):
        seen = {r["symbol"] for r in full_rows}
        for row in prescreen_rows:
            if row["symbol"] not in seen and row.get("price") and row.get("conviction", 0) >= 38:
                full_rows.append(row)
                seen.add(row["symbol"])
            if len(full_rows) >= min(50, MAX_FULL_SCAN):
                break

    watchlist_symbols = set(load_watchlist())
    watchlist_rows = [r for r in prescreen_rows if r.get("symbol") in watchlist_symbols]
    watchlist_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("dollar_volume") or 0), reverse=True)

    recovery_rows = [r for r in prescreen_rows if "Recovery" in str(r.get("setup_type", ""))]
    recovery_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("twenty_day_pct") or 0), reverse=True)
    recovery_rows = recovery_rows[:50]

    top_ai_ideas = build_diversified_top_ideas([r for r in full_rows if row_has_min_upside(r)], TOP_AI_IDEAS_TARGET)

    state = {
        "generated_at": now_iso(),
        "status": "success",
        "version": "V40.5",
        "universe_count": len(universe),
        "prescreen_count": len(prescreen_rows),
        "full_scan_count": len(full_rows),
        "top_ai_ideas_count": len(top_ai_ideas),
        "watchlist_count": len(watchlist_rows),
        "recovery_count": len(recovery_rows),
        "fallback_rows_allowed": False,
        "data_dir": str(DATA_DIR),
        "github_persisted": False,
        "duration_seconds": round(time.time() - started, 2),
        "filters": {
            "min_price": MIN_PRICE,
            "max_price": MAX_PRICE,
            "min_dollar_volume": MIN_DOLLAR_VOLUME,
            "min_market_cap": MIN_MARKET_CAP,
            "excluded_sector_keywords": EXCLUDED_SECTOR_KEYWORDS,
            "price_bucket_diversity": PRICE_BUCKETS,
            "top_ai_ideas_target": TOP_AI_IDEAS_TARGET,
            "min_upside_pct": MIN_UPSIDE_PCT,
        },
    }

    write_json(PRESCREEN_FILE, prescreen_rows)
    write_json(FULL_SCAN_FILE, full_rows)
    write_json(TOP_IDEAS_FILE, top_ai_ideas)
    write_json(WATCHLIST_SCAN_FILE, watchlist_rows)
    write_json(RECOVERY_SCAN_FILE, recovery_rows)
    write_json(STATE_FILE, state)

    if GITHUB_PERSIST:
        state["github_persisted"] = persist_to_github()
        write_json(STATE_FILE, state)

    return state


def persist_to_github() -> bool:
    files = [
        str(FULL_SCAN_FILE), str(PRESCREEN_FILE), str(STATE_FILE), str(UNIVERSE_FILE),
        str(TOP_IDEAS_FILE), str(WATCHLIST_FILE), str(WATCHLIST_SCAN_FILE), str(RECOVERY_SCAN_FILE),
    ]

    code, out = run_cmd(["git", "add"] + files)
    if code != 0:
        print(f"git add failed: {out}")
        return False

    code, _ = run_cmd(["git", "diff", "--cached", "--quiet"])
    if code == 0:
        print("No scan data changes to commit.")
        return True

    run_cmd(["git", "config", "user.email", os.getenv("GIT_USER_EMAIL", "render-cron@example.com")])
    run_cmd(["git", "config", "user.name", os.getenv("GIT_USER_NAME", "Render Cron")])

    msg = f"{GIT_COMMIT_MESSAGE} - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    code, out = run_cmd(["git", "commit", "-m", msg])
    if code != 0:
        print(f"git commit failed: {out}")
        return False

    repo_url = os.getenv("GITHUB_REPO_URL") or "origin"
    run_cmd(["git", "pull", "--rebase", repo_url, "main"])
    code, out = run_cmd(["git", "push", repo_url, "HEAD:main"])
    if code != 0:
        print(f"git push failed: {out}")
        return False

    return True


def main() -> None:
    try:
        state = scan_market()
        print(json.dumps(state, indent=2))
        if state.get("full_scan_count", 0) <= 0:
            sys.exit(2)
    except Exception as exc:
        error_state = {
            "generated_at": now_iso(), "status": "error", "version": "V40.5",
            "error": str(exc), "data_dir": str(DATA_DIR), "github_persisted": False,
        }
        write_json(STATE_FILE, error_state)
        print(json.dumps(error_state, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
