#!/usr/bin/env python3
"""
V39.3 Overnight Market Scanner - Analyst Driven AI Targets
- Render Cron compatible
- DATA_DIR defaults to "."
- Preserves dashboard output files:
  - market_full_scan.json
  - market_prescreen.json
  - market_scan_state.json
  - total_market_universe.json
- Improves conviction scoring, metadata, guidance, and filtering.
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


# =========================
# CONFIG
# =========================

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
PRESCREEN_FILE = DATA_DIR / "market_prescreen.json"
STATE_FILE = DATA_DIR / "market_scan_state.json"
UNIVERSE_FILE = DATA_DIR / "total_market_universe.json"

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


# =========================
# HELPERS
# =========================

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
        value = int(float(value))
        return value
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
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=90,
        )
        return result.returncode, result.stdout.strip()
    except Exception as exc:
        return 1, str(exc)


# =========================
# UNIVERSE
# =========================

def get_yahoo_screeners() -> List[str]:
    """
    Pull broad liquid lists from Yahoo predefined screeners.
    This avoids relying only on stale hardcoded symbols.
    """
    screeners = [
        "most_actives",
        "day_gainers",
        "day_losers",
        "growth_technology_stocks",
        "undervalued_growth_stocks",
        "aggressive_small_caps",
        "portfolio_anchors",
        "small_cap_gainers",
    ]

    symbols = set()
    for screener in screeners:
        try:
            df = yf.screen(screener, count=250)
            quotes = df.get("quotes", []) if isinstance(df, dict) else []
            for q in quotes:
                sym = q.get("symbol")
                quote_type = q.get("quoteType", "")
                if sym and quote_type in {"EQUITY", "ETF"}:
                    if "." not in sym and "/" not in sym and len(sym) <= 6:
                        symbols.add(sym.upper())
        except Exception:
            continue

    return sorted(symbols)


def fallback_universe() -> List[str]:
    """
    Stable broad universe fallback. Kept intentionally large enough for Render Cron,
    but the scanner will reject weak / invalid rows later.
    """
    mega_large = """
AAPL MSFT NVDA AMZN META GOOGL GOOG AVGO TSLA BRK-B JPM LLY V UNH XOM MA COST WMT NFLX ORCL HD PG JNJ ABBV BAC KO PLTR CRM CVX CSCO WFC IBM MRK GE AMD MCD LIN ADBE DIS TMO ABT PM CAT NOW QCOM TXN ISRG AMGN INTU VZ PEP GS RTX BKNG SPGI LOW PFE HON AXON C UNP MS NEE CMCSA AMAT DHR SCHW BLK GILD TJX PANW SYK ADP DE LRCX COP BSX MDLZ ETN CB ADI MMC UPS MU BX REGN FI BMY SO KLAC AMT CME MO ELV WM ICE ANET SHW EQIX PH KKR DUKE APH WELL TT CI MCK CDNS SNPS AON NKE COF USB MMM HCA MSI ITW ZTS CL TDG ORLY EMR MAR PGR ROP AJG ECL APD CTAS WMB CMG CRWD NOC
"""
    growth = """
SNOW DDOG NET MDB SHOP SE MELI UBER ABNB DASH RBLX COIN HOOD ROKU SQ PYPL AFRM SOFI UPST CELH ELF CAVA TOST DUOL HIMS APP ARM SMCI DELL VRT ANF ONON TTD FSLR ENPH RUN ALB RIVN LCID NIO LI XPEV
"""
    mid_small = """
AEHR ASTS IONQ RKLB SOUN BBAI AI PATH TEM RXRX DNA LMND OPEN ROOT UUUU URA CCJ SMR OKLO JOBY ACHR ENVX QS STEM CHPT EVGO BLNK
"""
    etfs = """
SPY QQQ DIA IWM VTI VOO SCHD JEPI JEPQ QYLD XYLD RYLD SPYT QQQY TLT HYG LQD XLF XLK XLE XLV XLY XLI XLP XLU XLB XLRE SMH SOXX ARKK TAN BOTZ
"""
    combined = f"{mega_large} {growth} {mid_small} {etfs}"
    symbols = []
    for raw in combined.replace("\n", " ").split():
        sym = raw.strip().upper()
        if sym:
            symbols.append(sym)
    return list(dict.fromkeys(symbols))


def build_universe() -> List[str]:
    symbols = set(fallback_universe())

    yahoo_symbols = get_yahoo_screeners()
    symbols.update(yahoo_symbols)

    # Load prior universe if present to preserve continuity.
    try:
        if UNIVERSE_FILE.exists():
            prior = json.loads(UNIVERSE_FILE.read_text())
            if isinstance(prior, list):
                for item in prior:
                    sym = item.get("symbol") if isinstance(item, dict) else item
                    if sym:
                        symbols.add(str(sym).upper())
            elif isinstance(prior, dict):
                for item in prior.get("symbols", []):
                    symbols.add(str(item).upper())
    except Exception:
        pass

    clean = []
    for sym in sorted(symbols):
        if "." in sym or "/" in sym:
            continue
        if len(sym) > 7:
            continue
        clean.append(sym)

    return clean[:MAX_UNIVERSE]


# =========================
# DATA FETCH
# =========================

def download_price_batch(symbols: List[str]) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()

    try:
        data = yf.download(
            tickers=" ".join(symbols),
            period="6mo",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            prepost=False,
            threads=True,
            progress=False,
        )
        return data
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

        df = df.dropna(subset=["Close"])
        return df
    except Exception:
        return pd.DataFrame()


def get_metadata(symbol: str) -> Dict[str, Any]:
    defaults = {
        "company_name": symbol,
        "sector": "Unknown",
        "industry": "Unknown",
        "market_cap": None,
        "quote_type": "EQUITY",
    }

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.get_info() or {}

        name = (
            info.get("shortName")
            or info.get("longName")
            or info.get("displayName")
            or info.get("underlyingSymbol")
            or symbol
        )

        return {
            "company_name": name if name and name != symbol else symbol,
            "sector": info.get("sector") or info.get("category") or "Unknown",
            "industry": info.get("industry") or info.get("fundFamily") or "Unknown",
            "market_cap": safe_float(info.get("marketCap")),
            "quote_type": info.get("quoteType") or "EQUITY",
            "analyst_target_mean": safe_float(info.get("targetMeanPrice")),
            "analyst_target_high": safe_float(info.get("targetHighPrice")),
            "analyst_target_low": safe_float(info.get("targetLowPrice")),
            "analyst_count": safe_int(info.get("numberOfAnalystOpinions"), 0),
            "recommendation_mean": safe_float(info.get("recommendationMean")),
            "recommendation_key": info.get("recommendationKey") or "unknown",
            "revenue_growth": safe_float(info.get("revenueGrowth")),
            "earnings_growth": safe_float(info.get("earningsGrowth")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "peg_ratio": safe_float(info.get("pegRatio")),
        }
    except Exception:
        return defaults


# =========================
# SIGNALS / SCORING
# =========================

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

    # RSI
    delta = close.diff()
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)
    avg_gain = gains.rolling(14).mean()
    avg_loss = losses.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = safe_float(100 - (100 / (1 + rs.iloc[-1])), 50)

    # ATR
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr14 = safe_float(tr.rolling(14).mean().iloc[-1])
    atr_pct = (atr14 / price * 100.0) if atr14 and price else None

    # Volume surge
    latest_vol = safe_float(volume.iloc[-1], 0)
    volume_ratio = latest_vol / vol20 if vol20 and vol20 > 0 else 1.0

    distance_from_20_high = pct_change(price, rolling_high_20)
    distance_from_60_high = pct_change(price, rolling_high_60)
    distance_above_20_low = pct_change(price, rolling_low_20)

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
        "distance_from_20_high": round(distance_from_20_high, 2) if distance_from_20_high is not None else None,
        "distance_from_60_high": round(distance_from_60_high, 2) if distance_from_60_high is not None else None,
        "distance_above_20_low": round(distance_above_20_low, 2) if distance_above_20_low is not None else None,
    }


def score_stock(ind: Dict[str, Any], meta: Dict[str, Any]) -> Tuple[int, List[str], List[str]]:
    """
    Meaningfully varied 0-100 score.
    Rewards trend, momentum, liquidity, volume confirmation, relative setup quality.
    Penalizes overextended or weak/liquid names.
    """
    score = 0
    good: List[str] = []
    risks: List[str] = []

    price = ind.get("price")
    sma10 = ind.get("sma10")
    sma20 = ind.get("sma20")
    sma50 = ind.get("sma50")
    sma100 = ind.get("sma100")
    rsi = ind.get("rsi")
    vol_ratio = ind.get("volume_ratio") or 1
    dollar_volume = ind.get("dollar_volume") or 0
    one = ind.get("one_day_pct")
    five = ind.get("five_day_pct")
    twenty = ind.get("twenty_day_pct")
    sixty = ind.get("sixty_day_pct")
    dist20h = ind.get("distance_from_20_high")
    atr_pct = ind.get("atr_pct")
    market_cap = meta.get("market_cap")

    # Liquidity / investability
    if dollar_volume >= 100_000_000:
        score += 12
        good.append("Strong liquidity")
    elif dollar_volume >= 25_000_000:
        score += 9
        good.append("Good liquidity")
    elif dollar_volume >= MIN_DOLLAR_VOLUME:
        score += 5
    else:
        score -= 20
        risks.append("Weak dollar volume")

    if market_cap and market_cap >= 10_000_000_000:
        score += 8
    elif market_cap and market_cap >= 1_000_000_000:
        score += 5
    elif market_cap and market_cap < MIN_MARKET_CAP:
        score -= 15
        risks.append("Very small market cap")

    # Trend stack
    if price and sma20 and price > sma20:
        score += 10
        good.append("Price is above the 20-day trend")
    else:
        score -= 8
        risks.append("Price is below the 20-day trend")

    if price and sma50 and price > sma50:
        score += 12
        good.append("Price is above the 50-day trend")
    else:
        score -= 8
        risks.append("Price is below or near the 50-day trend")

    if sma20 and sma50 and sma20 > sma50:
        score += 8
        good.append("Short-term trend is above intermediate trend")
    elif sma20 and sma50:
        score -= 5

    if sma50 and sma100 and sma50 > sma100:
        score += 6

    # Momentum
    if five is not None:
        if 1 <= five <= 12:
            score += 12
            good.append("Healthy 5-day momentum")
        elif five > 18:
            score -= 6
            risks.append("Short-term move may be extended")
        elif five < -4:
            score -= 8
            risks.append("Recent momentum is weak")

    if twenty is not None:
        if 2 <= twenty <= 25:
            score += 14
            good.append("Positive 20-day momentum")
        elif twenty > 35:
            score -= 7
            risks.append("20-day move is stretched")
        elif twenty < -8:
            score -= 10
            risks.append("20-day trend is negative")

    if sixty is not None:
        if 5 <= sixty <= 45:
            score += 9
        elif sixty > 75:
            score -= 5
            risks.append("Longer move may be overextended")
        elif sixty < -12:
            score -= 7

    # RSI
    if rsi is not None:
        if 48 <= rsi <= 68:
            score += 12
            good.append("RSI is constructive without looking overheated")
        elif 68 < rsi <= 76:
            score += 4
            risks.append("RSI is warm; avoid chasing")
        elif rsi > 76:
            score -= 10
            risks.append("RSI is overbought")
        elif 35 <= rsi < 48:
            score += 2
            risks.append("RSI is not yet showing strong momentum")
        else:
            score -= 8
            risks.append("RSI is weak")

    # Volume confirmation
    if vol_ratio >= 2.0:
        score += 10
        good.append("Volume is meaningfully above average")
    elif vol_ratio >= 1.25:
        score += 6
        good.append("Volume is above average")
    elif vol_ratio < 0.65:
        score -= 5
        risks.append("Volume confirmation is light")

    # Near highs but not too extended
    if dist20h is not None:
        if -8 <= dist20h <= -1:
            score += 8
            good.append("Trading near recent highs without being at the absolute top")
        elif -1 < dist20h <= 1:
            score += 5
            good.append("Testing recent highs")
        elif dist20h < -18:
            score -= 6
            risks.append("Still far from recent highs")

    # Volatility control
    if atr_pct is not None:
        if 1 <= atr_pct <= 5:
            score += 7
            good.append("Volatility is tradable")
        elif atr_pct > 9:
            score -= 8
            risks.append("High volatility could make stops difficult")
        elif atr_pct < 0.5:
            score -= 3

    # One-day noise guard
    if one is not None and one < -6:
        score -= 10
        risks.append("Sharp down day needs confirmation")
    elif one is not None and one > 12:
        score -= 5
        risks.append("Large one-day jump may pull back")

    # Analyst target support: reward real consensus upside, penalize downside.
    analyst_mean = meta.get("analyst_target_mean")
    analyst_count = meta.get("analyst_count") or 0
    if price and analyst_mean and analyst_count >= 3:
        analyst_upside = ((analyst_mean - price) / price) * 100
        if analyst_upside >= 25:
            score += 10
            good.append(f"analyst consensus implies strong upside of {analyst_upside:.1f}%")
        elif analyst_upside >= 12:
            score += 6
            good.append(f"analyst consensus implies upside of {analyst_upside:.1f}%")
        elif analyst_upside < -5:
            score -= 10
            risks.append("analyst consensus target is below current price")

    # Normalize away from common weak 20 score problem.
    score = max(1, min(99, score))
    if score < 35:
        score = max(score, 20)
    return int(round(score)), good[:6], risks[:6]



def build_ai_target_model(ind: Dict[str, Any], meta: Dict[str, Any], score: int) -> Dict[str, Any]:
    """
    V39.3 analyst-driven AI target model.
    Uses analyst consensus when available, then adjusts by technical strength,
    growth quality, risk, and volume confirmation.
    """
    price = ind.get("price")
    if not price:
        return {}

    analyst_mean = meta.get("analyst_target_mean")
    analyst_high = meta.get("analyst_target_high")
    analyst_low = meta.get("analyst_target_low")
    analyst_count = meta.get("analyst_count") or 0
    recommendation_key = meta.get("recommendation_key") or "unknown"
    recommendation_mean = meta.get("recommendation_mean")
    revenue_growth = meta.get("revenue_growth")
    earnings_growth = meta.get("earnings_growth")

    twenty = ind.get("twenty_day_pct") or 0
    rsi = ind.get("rsi") or 50
    volume_ratio = ind.get("volume_ratio") or 1
    atr_pct = ind.get("atr_pct") or 3

    has_analyst_targets = (
        analyst_mean is not None
        and analyst_mean > 0
        and analyst_count >= 3
        and analyst_high is not None
        and analyst_high > 0
        and analyst_low is not None
        and analyst_low > 0
    )

    if has_analyst_targets:
        analyst_upside_pct = ((analyst_mean - price) / price) * 100
        high_upside_pct = ((analyst_high - price) / price) * 100
        low_upside_pct = ((analyst_low - price) / price) * 100

        adjustment = 0.0
        if score >= 80:
            adjustment += 0.18
        elif score >= 70:
            adjustment += 0.10
        elif score < 55:
            adjustment -= 0.12

        if twenty > 8:
            adjustment += 0.08
        elif twenty < -5:
            adjustment -= 0.10

        if 48 <= rsi <= 68:
            adjustment += 0.05
        elif rsi > 75:
            adjustment -= 0.08

        if volume_ratio >= 1.25:
            adjustment += 0.05

        if revenue_growth is not None and revenue_growth > 0.10:
            adjustment += 0.06
        if earnings_growth is not None and earnings_growth > 0.10:
            adjustment += 0.06

        if atr_pct > 8:
            adjustment -= 0.08

        adjustment = max(-0.25, min(0.35, adjustment))

        if adjustment >= 0:
            ai_base = analyst_mean + ((analyst_high - analyst_mean) * adjustment)
        else:
            ai_base = analyst_mean + ((analyst_mean - analyst_low) * adjustment)

        ai_bull = min(analyst_high, ai_base * 1.12)
        ai_bear = max(analyst_low, price * 0.88)
        expected_upside_pct = ((ai_base - price) / price) * 100

        target_source = "Analyst consensus + AI adjustment"
        confidence_note = (
            f"Based on {analyst_count} analyst opinions, consensus target ${analyst_mean:.2f}, "
            f"high target ${analyst_high:.2f}, and AI adjustment for trend, volume, growth, and risk."
        )
    else:
        atr = ind.get("atr14") or price * 0.035
        high20 = ind.get("rolling_high_20") or price
        high60 = ind.get("rolling_high_60") or high20

        technical_target = max(high20 * 1.03, high60 * 1.01, price + atr * 2.2)
        ai_base = technical_target
        ai_bull = max(ai_base * 1.08, price + atr * 3.2)
        ai_bear = max(price - atr * 2.0, price * 0.88)

        analyst_upside_pct = None
        high_upside_pct = None
        low_upside_pct = None
        expected_upside_pct = ((ai_base - price) / price) * 100
        target_source = "Technical AI target; analyst target unavailable"
        confidence_note = "Analyst target data was not available, so AI used trend, recent highs, ATR, and momentum."

    return {
        "analyst_target_mean": round(analyst_mean, 2) if analyst_mean else None,
        "analyst_target_high": round(analyst_high, 2) if analyst_high else None,
        "analyst_target_low": round(analyst_low, 2) if analyst_low else None,
        "analyst_count": analyst_count,
        "recommendation_key": recommendation_key,
        "recommendation_mean": round(recommendation_mean, 2) if recommendation_mean else None,
        "analyst_upside_pct": round(analyst_upside_pct, 1) if analyst_upside_pct is not None else None,
        "analyst_high_upside_pct": round(high_upside_pct, 1) if high_upside_pct is not None else None,
        "analyst_low_upside_pct": round(low_upside_pct, 1) if low_upside_pct is not None else None,
        "ai_base_target": round(ai_base, 2),
        "ai_bull_target": round(ai_bull, 2),
        "ai_bear_target": round(ai_bear, 2),
        "expected_upside_pct": round(expected_upside_pct, 1),
        "target_source": target_source,
        "target_confidence_note": confidence_note,
    }


def build_trade_plan(ind: Dict[str, Any], score: int) -> Dict[str, Any]:
    price = ind.get("price")
    atr = ind.get("atr14") or (price * 0.035 if price else 1)
    sma20 = ind.get("sma20")
    high20 = ind.get("rolling_high_20")

    if not price:
        return {}

    # Entry prefers controlled pullback or break near 20-day high.
    lower_entry = max(price - atr * 0.5, price * 0.96)
    upper_entry = min(price + atr * 0.25, price * 1.03)

    support_anchor = sma20 if sma20 and sma20 < price else price - atr
    stop_loss = min(price - atr * 1.4, support_anchor - atr * 0.35)
    stop_loss = max(stop_loss, price * 0.80)

    risk_per_share = max(price - stop_loss, price * 0.02)
    target_1 = price + risk_per_share * 1.8
    target_2 = price + risk_per_share * 2.7

    if high20 and high20 > price:
        target_1 = max(target_1, high20 * 1.01)

    rr = (target_1 - price) / risk_per_share if risk_per_share > 0 else None

    return {
        "entry_range": f"${lower_entry:.2f} - ${upper_entry:.2f}",
        "entry_low": round(lower_entry, 2),
        "entry_high": round(upper_entry, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target_1, 2),
        "target_2": round(target_2, 2),
        "risk_reward": round(rr, 2) if rr else None,
        "risk_reward_explanation": (
            f"Approximate first target offers about {rr:.1f}:1 reward-to-risk based on current price, "
            f"ATR-based stop, and recent trend structure."
            if rr else
            "Risk/reward could not be calculated cleanly."
        ),
    }


def plain_english_guidance(symbol: str, company: str, ind: Dict[str, Any], score: int, good: List[str], risks: List[str], plan: Dict[str, Any]) -> Dict[str, str]:
    good_text = "; ".join(good) if good else "The setup has some improving technical traits, but confirmation is limited."
    risk_text = "; ".join(risks) if risks else "Main risk is a normal pullback if broader market momentum fades."

    if score >= 75:
        rank_reason = "High conviction because trend, momentum, liquidity, and volume confirmation are aligned."
    elif score >= 60:
        rank_reason = "Moderate-to-strong setup with enough technical support to watch closely."
    elif score >= 45:
        rank_reason = "Watchlist candidate, but it needs stronger confirmation before becoming a high-priority idea."
    else:
        rank_reason = "Lower conviction; included only if it has some relative strength or liquidity worth monitoring."

    return {
        "why_ranked_high": rank_reason,
        "what_looks_good": good_text,
        "what_could_go_wrong": risk_text,
        "guidance": (
            f"{company} ({symbol}) is scoring {score}/100. "
            f"Preferred entry is {plan.get('entry_range', 'near current support')}. "
            f"Use a stop around ${plan.get('stop_loss')} and first target near ${plan.get('target')}. "
            f"{plan.get('risk_reward_explanation', '')}"
        ),
        "action_note": (
            "Do not chase a gap-up open. Best setup is either a controlled pullback into the entry range "
            "or a breakout that holds above prior resistance with volume."
        ),
    }


def make_dashboard_row(symbol: str, meta: Dict[str, Any], ind: Dict[str, Any], score: int, good: List[str], risks: List[str]) -> Dict[str, Any]:
    plan = build_trade_plan(ind, score)
    target_model = build_ai_target_model(ind, meta, score)
    guidance = plain_english_guidance(symbol, meta.get("company_name", symbol), ind, score, good, risks, plan)

    # Keep a broad set of field names so V39 app.py has backward-compatible options.
    row = {
        "symbol": symbol,
        "ticker": symbol,
        "company": meta.get("company_name", symbol),
        "company_name": meta.get("company_name", symbol),
        "name": meta.get("company_name", symbol),
        "sector": meta.get("sector", "Unknown"),
        "industry": meta.get("industry", "Unknown"),
        "market_cap": meta.get("market_cap"),
        "quote_type": meta.get("quote_type", "EQUITY"),

        "price": ind.get("price"),
        "current_price": ind.get("price"),
        "last_price": ind.get("price"),
        "avg_volume_20d": ind.get("avg_volume_20d"),
        "dollar_volume": ind.get("dollar_volume"),
        "volume_ratio": ind.get("volume_ratio"),

        "conviction": score,
        "conviction_score": score,
        "score": score,
        "ai_score": score,

        "rsi": ind.get("rsi"),
        "atr14": ind.get("atr14"),
        "atr_pct": ind.get("atr_pct"),
        "sma10": ind.get("sma10"),
        "sma20": ind.get("sma20"),
        "sma50": ind.get("sma50"),
        "sma100": ind.get("sma100"),
        "one_day_pct": ind.get("one_day_pct"),
        "five_day_pct": ind.get("five_day_pct"),
        "twenty_day_pct": ind.get("twenty_day_pct"),
        "sixty_day_pct": ind.get("sixty_day_pct"),

        "entry_range": plan.get("entry_range"),
        "entry_low": plan.get("entry_low"),
        "entry_high": plan.get("entry_high"),
        "stop_loss": plan.get("stop_loss"),

        "target": target_model.get("ai_base_target") or plan.get("target"),
        "target_2": target_model.get("ai_bull_target") or plan.get("target_2"),
        "ai_base_target": target_model.get("ai_base_target"),
        "ai_bull_target": target_model.get("ai_bull_target"),
        "ai_bear_target": target_model.get("ai_bear_target"),
        "analyst_target_mean": target_model.get("analyst_target_mean"),
        "analyst_target_high": target_model.get("analyst_target_high"),
        "analyst_target_low": target_model.get("analyst_target_low"),
        "analyst_count": target_model.get("analyst_count"),
        "analyst_upside_pct": target_model.get("analyst_upside_pct"),
        "analyst_high_upside_pct": target_model.get("analyst_high_upside_pct"),
        "expected_upside_pct": target_model.get("expected_upside_pct"),
        "upside": target_model.get("expected_upside_pct"),
        "target_source": target_model.get("target_source"),
        "target_confidence_note": target_model.get("target_confidence_note"),
        "recommendation_key": target_model.get("recommendation_key"),
        "recommendation_mean": target_model.get("recommendation_mean"),

        "risk_reward": plan.get("risk_reward"),
        "risk_reward_explanation": plan.get("risk_reward_explanation"),

        "why_ranked_high": guidance.get("why_ranked_high"),
        "what_looks_good": guidance.get("what_looks_good"),
        "what_could_go_wrong": guidance.get("what_could_go_wrong"),
        "investment_thesis": (
            f"{meta.get('company_name', symbol)} screens as a potential opportunity because "
            f"{guidance.get('what_looks_good', '').lower()}. "
            f"AI target is ${target_model.get('ai_base_target')} with expected upside of "
            f"{target_model.get('expected_upside_pct')}%, using {target_model.get('target_source')}. "
            f"Key risk: {guidance.get('what_could_go_wrong', '').lower()}."
        ),
        "table_reason": (
            f"AI target ${target_model.get('ai_base_target')} / upside {target_model.get('expected_upside_pct')}%. "
            f"{guidance.get('why_ranked_high')} "
            f"Watch entry {plan.get('entry_range')} with stop near ${plan.get('stop_loss')}."
        ),
        "opportunity_reason": (
            f"Analyst-driven upside: {target_model.get('expected_upside_pct')}%. "
            f"{target_model.get('target_confidence_note')}"
        ),
        "guidance": (
            f"{guidance.get('guidance')} "
            f"Analyst/AI target view: {target_model.get('target_confidence_note')} "
            f"AI base target ${target_model.get('ai_base_target')}, bull case ${target_model.get('ai_bull_target')}, "
            f"bear case ${target_model.get('ai_bear_target')}."
        ),
        "action_note": guidance.get("action_note"),
        "ai_guidance": guidance.get("guidance"),
        "summary": (
            f"{meta.get('company_name', symbol)}: AI target ${target_model.get('ai_base_target')} "
            f"with {target_model.get('expected_upside_pct')}% upside. "
            f"{guidance.get('why_ranked_high')}"
        ),

        "setup_tags": good,
        "risk_tags": risks,
        "scan_time": now_iso(),
    }

    return row


# =========================
# SCAN PIPELINE
# =========================

def passes_basic_filter(ind: Dict[str, Any], meta: Dict[str, Any]) -> bool:
    price = ind.get("price")
    if price is None or price < MIN_PRICE or price > MAX_PRICE:
        return False

    if (ind.get("dollar_volume") or 0) < MIN_DOLLAR_VOLUME:
        return False

    market_cap = meta.get("market_cap")
    if market_cap is not None and market_cap < MIN_MARKET_CAP:
        return False

    # Must have enough valid technicals.
    if ind.get("sma20") is None or ind.get("sma50") is None:
        return False

    return True


def scan_market() -> Dict[str, Any]:
    start_time = time.time()
    universe = build_universe()

    universe_payload = {
        "generated_at": now_iso(),
        "count": len(universe),
        "symbols": universe,
    }
    write_json(UNIVERSE_FILE, universe_payload)

    prescreen_rows: List[Dict[str, Any]] = []
    full_rows: List[Dict[str, Any]] = []

    metadata_cache: Dict[str, Dict[str, Any]] = {}

    for i in range(0, len(universe), BATCH_SIZE):
        batch = universe[i:i + BATCH_SIZE]
        price_data = download_price_batch(batch)

        for symbol in batch:
            hist = extract_symbol_history(price_data, symbol)
            ind = compute_indicators(hist)
            if not ind:
                continue

            # Light price/liquidity filter before metadata calls.
            if ind.get("price") is None or ind.get("price") < MIN_PRICE:
                continue
            if (ind.get("dollar_volume") or 0) < MIN_DOLLAR_VOLUME:
                continue

            meta = metadata_cache.get(symbol)
            if meta is None:
                meta = get_metadata(symbol)
                metadata_cache[symbol] = meta

            if not passes_basic_filter(ind, meta):
                continue

            score, good, risks = score_stock(ind, meta)
            row = make_dashboard_row(symbol, meta, ind, score, good, risks)

            # Prescreen can include moderate setups, but weak fallback rows are reduced.
            if score >= 38:
                prescreen_rows.append(row)

            # Full scan requires better score quality.
            if score >= 45:
                full_rows.append(row)

        if SLEEP_BETWEEN_BATCHES > 0:
            time.sleep(SLEEP_BETWEEN_BATCHES)

    prescreen_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("dollar_volume") or 0), reverse=True)
    full_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("dollar_volume") or 0), reverse=True)

    prescreen_rows = prescreen_rows[:MAX_PRESCREEN]
    full_rows = full_rows[:MAX_FULL_SCAN]

    # If full scan is too thin, only backfill with actual valid prescreen rows, not fake rows.
    if len(full_rows) < min(25, MAX_FULL_SCAN):
        seen = {r["symbol"] for r in full_rows}
        for row in prescreen_rows:
            if row["symbol"] not in seen and row.get("price") and row.get("conviction", 0) >= 38:
                full_rows.append(row)
                seen.add(row["symbol"])
            if len(full_rows) >= min(50, MAX_FULL_SCAN):
                break

    state = {
        "generated_at": now_iso(),
        "status": "success",
        "version": "V39.3",
        "universe_count": len(universe),
        "prescreen_count": len(prescreen_rows),
        "full_scan_count": len(full_rows),
        "fallback_rows_allowed": False,
        "data_dir": str(DATA_DIR),
        "github_persisted": False,
        "duration_seconds": round(time.time() - start_time, 2),
        "filters": {
            "min_price": MIN_PRICE,
            "max_price": MAX_PRICE,
            "min_dollar_volume": MIN_DOLLAR_VOLUME,
            "min_market_cap": MIN_MARKET_CAP,
        },
    }

    write_json(PRESCREEN_FILE, prescreen_rows)
    write_json(FULL_SCAN_FILE, full_rows)
    write_json(STATE_FILE, state)

    if GITHUB_PERSIST:
        state["github_persisted"] = persist_to_github()
        write_json(STATE_FILE, state)

    return state


# =========================
# GITHUB PERSISTENCE
# =========================

def persist_to_github() -> bool:
    """
    Uses existing Render repo checkout and credentials.
    Safe no-op if nothing changed.
    """
    files = [
        str(FULL_SCAN_FILE),
        str(PRESCREEN_FILE),
        str(STATE_FILE),
        str(UNIVERSE_FILE),
    ]

    code, out = run_cmd(["git", "status", "--porcelain"])
    if code != 0:
        print(f"git status failed: {out}")
        return False

    code, out = run_cmd(["git", "add"] + files)
    if code != 0:
        print(f"git add failed: {out}")
        return False

    code, out = run_cmd(["git", "diff", "--cached", "--quiet"])
    if code == 0:
        print("No scan data changes to commit.")
        return True

    run_cmd(["git", "config", "user.email", os.getenv("GIT_USER_EMAIL", "render-cron@example.com")])
    run_cmd(["git", "config", "user.name", os.getenv("GIT_USER_NAME", "Render Cron")])

    commit_msg = f"{GIT_COMMIT_MESSAGE} - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    code, out = run_cmd(["git", "commit", "-m", commit_msg])
    if code != 0:
        print(f"git commit failed: {out}")
        return False

    # Rebase first to avoid non-fast-forward errors.
    run_cmd(["git", "pull", "--rebase", "origin", "main"])

    repo_url = os.getenv("GITHUB_REPO_URL") or "origin"
    code, out = run_cmd(["git", "push", repo_url, "HEAD:main"])
    if code != 0:
        print(f"git push failed: {out}")
        return False

    return True


# =========================
# MAIN
# =========================

def main() -> None:
    try:
        state = scan_market()
        print(json.dumps(state, indent=2))
        if state.get("full_scan_count", 0) <= 0:
            sys.exit(2)
    except Exception as exc:
        error_state = {
            "generated_at": now_iso(),
            "status": "error",
            "version": "V39.3",
            "error": str(exc),
            "data_dir": str(DATA_DIR),
            "github_persisted": False,
        }
        write_json(STATE_FILE, error_state)
        print(json.dumps(error_state, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
