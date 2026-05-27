#!/usr/bin/env python3
"""
V39.3 Overnight Market Scanner
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
    defaults = {"company_name": symbol, "sector": "Unknown", "industry": "Unknown", "market_cap": None, "quote_type": "EQUITY"}
    try:
        info = yf.Ticker(symbol).get_info() or {}
        name = info.get("shortName") or info.get("longName") or info.get("displayName") or symbol
        return {
            "company_name": name if name else symbol,
            "sector": info.get("sector") or info.get("category") or "Unknown",
            "industry": info.get("industry") or info.get("fundFamily") or "Unknown",
            "market_cap": safe_float(info.get("marketCap")),
            "quote_type": info.get("quoteType") or "EQUITY",
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

    rr = (target_1 - price) / risk if risk > 0 else None

    return {
        "entry_range": f"${lower_entry:.2f} - ${upper_entry:.2f}",
        "entry_low": round(lower_entry, 2),
        "entry_high": round(upper_entry, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target_1, 2),
        "target_2": round(target_2, 2),
        "risk_reward": round(rr, 2) if rr else None,
        "risk_reward_explanation": f"Approximate first target offers about {rr:.1f}:1 reward-to-risk." if rr else "",
    }


def build_ai_reasoning(symbol: str, meta: Dict[str, Any], ind: Dict[str, Any], score: int, setup_type: str, good: List[str], risks: List[str], plan: Dict[str, Any]) -> Dict[str, str]:
    company = meta.get("company_name", symbol)
    sector = meta.get("sector", "Unknown")
    price = ind.get("price")
    rsi = ind.get("rsi")
    twenty = ind.get("twenty_day_pct")
    sixty = ind.get("sixty_day_pct")
    volume_ratio = ind.get("volume_ratio")

    if setup_type == "AI Momentum Leader":
        why = "Ranks high because trend, momentum, liquidity, and volume confirmation are aligned."
    elif setup_type == "Recovery / Reversal Candidate":
        why = "Ranks as a recovery setup because it appears beaten down or below prior highs while showing early stabilization."
    elif setup_type == "Quality Watchlist Setup":
        why = "Ranks as a watchlist-quality setup with enough technical structure to monitor, but not yet top momentum."
    else:
        why = "Lower conviction monitor candidate. Needs stronger confirmation before becoming a priority."

    good_text = "; ".join(good) if good else "Needs stronger confirmation."
    risk_text = "; ".join(risks) if risks else "Broad market weakness or failed follow-through."

    reasoning = (
        f"{setup_type}: {company} ({symbol}) scores {score}/100. {why} "
        f"Sector: {sector}. Price: ${price}. RSI: {rsi}. 20-day move: {twenty}%. 60-day move: {sixty}%. "
        f"Volume is {volume_ratio}x average. Entry: {plan.get('entry_range')}. "
        f"Stop: ${plan.get('stop_loss')}. Target: ${plan.get('target')}. "
        f"What looks good: {good_text}. What could go wrong: {risk_text}."
    )

    return {
        "why_ranked_high": why,
        "what_looks_good": good_text,
        "what_could_go_wrong": risk_text,
        "guidance": reasoning,
        "ai_reasoning": reasoning,
        "action_note": "Avoid chasing a gap-up open. Prefer a controlled pullback or a breakout that holds with volume.",
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
        "price": ind.get("price"), "current_price": ind.get("price"), "last_price": ind.get("price"),
        "avg_volume_20d": ind.get("avg_volume_20d"), "dollar_volume": ind.get("dollar_volume"), "volume_ratio": ind.get("volume_ratio"),
        "conviction": score, "conviction_score": score, "score": score, "ai_score": score,
        "setup_type": setup_type, "bucket": setup_type,
        "rsi": ind.get("rsi"), "atr14": ind.get("atr14"), "atr_pct": ind.get("atr_pct"),
        "sma10": ind.get("sma10"), "sma20": ind.get("sma20"), "sma50": ind.get("sma50"), "sma100": ind.get("sma100"),
        "one_day_pct": ind.get("one_day_pct"), "five_day_pct": ind.get("five_day_pct"),
        "twenty_day_pct": ind.get("twenty_day_pct"), "sixty_day_pct": ind.get("sixty_day_pct"),
        "entry_range": plan.get("entry_range"), "entry_low": plan.get("entry_low"), "entry_high": plan.get("entry_high"),
        "stop_loss": plan.get("stop_loss"), "target": plan.get("target"), "target_2": plan.get("target_2"),
        "risk_reward": plan.get("risk_reward"), "risk_reward_explanation": plan.get("risk_reward_explanation"),
        "setup_tags": good, "risk_tags": risks, "scan_time": now_iso(),
        **guidance,
        "summary": guidance.get("guidance"), "ai_guidance": guidance.get("guidance"),
    }
    return row


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

    top_ai_ideas = full_rows[:25]

    state = {
        "generated_at": now_iso(),
        "status": "success",
        "version": "V39.3",
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
            "generated_at": now_iso(), "status": "error", "version": "V39.3",
            "error": str(exc), "data_dir": str(DATA_DIR), "github_persisted": False,
        }
        write_json(STATE_FILE, error_state)
        print(json.dumps(error_state, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
