import os
import json
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import yfinance as yf

EASTERN = ZoneInfo("America/New_York")
DATA_DIR = Path(os.getenv("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

TOTAL_UNIVERSE_FILE = DATA_DIR / "total_market_universe.json"
PRESCREEN_FILE = DATA_DIR / "market_prescreen.json"
FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
SCAN_STATE_FILE = DATA_DIR / "market_scan_state.json"

MIN_PRICE = float(os.getenv("MARKET_SCAN_MIN_PRICE", "2"))
MIN_AVG_VOLUME = int(os.getenv("MARKET_SCAN_MIN_AVG_VOLUME", "150000"))
PRESCREEN_WORKERS = int(os.getenv("PRESCREEN_WORKERS", "8"))
FULL_SCAN_WORKERS = int(os.getenv("FULL_SCAN_WORKERS", "6"))
FULL_AGENT_LIMIT = int(os.getenv("FULL_AGENT_LIMIT", "350"))

EXCLUDED_TICKERS = {
    "JPM","BAC","WFC","C","GS","MS","SCHW","COF","AXP","USB","PNC","TFC","BK","BLK","BX",
    "BUD","TAP","STZ","SAM","DEO","ABEV","DIS","NFLX","WBD","PARA","CMCSA","LYV","SIRI",
    "FOX","FOXA","RBLX","SNAP","MTCH","IAC","DKNG","PENN","MGM","WYNN","LVS","CZR","MLCO",
    "MO","PM","BTI","VGR","SPCE","GOEV","FCEL","BLNK","WKHS","MVST","LCID","LAZR","CHPT",
    "DNA","RIDE","NKLA","HYLN"
}

EXCLUDED_KEYWORDS = [
    "bank","insurance","capital markets","asset management","mortgage","financial services",
    "brokerage","credit services","investment banking","entertainment","media","broadcast",
    "streaming","music","film","television","publishing","advertising","alcohol","distillers",
    "wineries","brewers","beer","wine","spirits","gaming","casino","gambling","tobacco",
    "reit","real estate"
]

def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        json.dump(data, f, indent=2, default=str)

def normalize_ticker(t):
    return str(t or "").strip().upper().replace("$", "")

def get_price_bucket(price):
    try:
        price = float(price)
        if price < 10: return "Under $10"
        if price < 30: return "$10-$30"
        if price < 75: return "$30-$75"
        if price < 150: return "$75-$150"
        return "$150+"
    except Exception:
        return "Unknown"

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def fmt_money(value):
    try:
        if value is None or pd.isna(value): return "N/A"
        v = float(value); a = abs(v)
        if a >= 1e12: return f"${v/1e12:.2f}T"
        if a >= 1e9: return f"${v/1e9:.2f}B"
        if a >= 1e6: return f"${v/1e6:.2f}M"
        return f"${v:,.0f}"
    except Exception:
        return "N/A"

def fmt_pct(value):
    try:
        if value is None or pd.isna(value): return "N/A"
        return f"{float(value)*100:.1f}%"
    except Exception:
        return "N/A"

def fetch_universe():
    tickers = set()
    for url, col in [
        ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", "Symbol"),
        ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", "ACT Symbol"),
    ]:
        try:
            df = pd.read_csv(url, sep="|")
            if col not in df.columns: continue
            if "Test Issue" in df.columns:
                df = df[df["Test Issue"].astype(str).str.upper() != "Y"]
            if "ETF" in df.columns:
                df = df[df["ETF"].astype(str).str.upper() != "Y"]
            tickers.update(df[col].dropna().astype(str).tolist())
        except Exception as e:
            print(f"Universe fetch failed: {e}")

    cleaned = []
    for t in tickers:
        t = normalize_ticker(t)
        if not t or t in EXCLUDED_TICKERS: continue
        if any(x in t for x in ["^", "/", "$", "."]): continue
        if len(t) > 5: continue
        if not t.replace("-", "").isalpha(): continue
        if t.endswith(("W","WS","WT","U","R")) and len(t) >= 4: continue
        cleaned.append(t)

    cleaned = sorted(set(cleaned))
    write_json(TOTAL_UNIVERSE_FILE, {"created_at": datetime.now(EASTERN).isoformat(), "count": len(cleaned), "tickers": cleaned})
    return cleaned

def get_hist(ticker, period="6mo"):
    try:
        return yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False).dropna()
    except Exception:
        return pd.DataFrame()

def quick_prescreen_one(ticker):
    ticker = normalize_ticker(ticker)
    if not ticker or ticker in EXCLUDED_TICKERS: return None
    try:
        hist = get_hist(ticker, "6mo")
        if hist.empty or len(hist) < 50: return None
        price = float(hist["Close"].iloc[-1])
        if price < MIN_PRICE: return None
        avg_vol = float(hist["Volume"].tail(20).mean())
        if avg_vol < MIN_AVG_VOLUME: return None
        close = hist["Close"]
        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma120 = float(close.rolling(120).mean().iloc[-1])
        rsi = float(calc_rsi(close).iloc[-1])
        high = float(hist["High"].max())
        from_high = ((price-high)/high)*100 if high else 0
        if not (price > sma20 or price > sma50 or (25 <= rsi <= 55 and from_high <= -12)):
            return None
        quick = 0
        if price > sma20: quick += 18
        if price > sma50: quick += 22
        if price > sma120: quick += 18
        if 40 <= rsi <= 70: quick += 18
        if avg_vol >= 500000: quick += 10
        if from_high <= -15: quick += 8
        if price < 75: quick += 8
        return {"Ticker": ticker, "Price": round(price,2), "Avg Volume": int(avg_vol), "RSI": round(rsi,1),
                "From 52W High %": round(from_high,1), "Quick Score": round(quick,0), "Price Bucket": get_price_bucket(price)}
    except Exception:
        return None

def is_excluded_by_info(info):
    combined = " ".join([str(info.get(k,"")) for k in ["sector","industry","longName","shortName"]]).lower()
    return any(k in combined for k in EXCLUDED_KEYWORDS)

def financial_safety(info):
    red = 0; yellow = 0; reasons = []
    try:
        dte = info.get("debtToEquity")
        if dte is not None:
            dte = float(dte)
            if dte > 250: red += 1; reasons.append(f"very high debt/equity {dte:.1f}")
            elif dte > 150: yellow += 1; reasons.append(f"elevated debt/equity {dte:.1f}")
    except Exception: pass
    for key, label in [("freeCashflow","free cash flow"),("operatingCashflow","operating cash flow")]:
        try:
            v = info.get(key)
            if v is not None:
                if float(v) < 0: red += 1; reasons.append(f"negative {label}")
                else: reasons.append(f"positive {label}")
        except Exception: pass
    try:
        rg = info.get("revenueGrowth")
        if rg is not None:
            if float(rg) < -0.05: red += 1; reasons.append("revenue declining")
            elif float(rg) < 0.03: yellow += 1; reasons.append("low revenue growth")
    except Exception: pass
    if red >= 2: return "🔴 Financial Risk — Not Execution Safe", -25, "; ".join(reasons)
    if red == 1: return "🟠 Financial Caution — Starter/Watch Only", -15, "; ".join(reasons)
    if yellow >= 2: return "🟡 Financial Watch — Use Smaller Size", -8, "; ".join(reasons)
    return "🟢 Financially Safer", 5, "; ".join(reasons) or "no major financial red flags"

def deep_analyze_one(item):
    ticker = item["Ticker"]
    try:
        hist = get_hist(ticker, "1y")
        if hist.empty or len(hist) < 60: return None
        info = yf.Ticker(ticker).info or {}
        if ticker in EXCLUDED_TICKERS or is_excluded_by_info(info): return None
        price = float(hist["Close"].iloc[-1])
        close = hist["Close"]
        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float(close.rolling(120).mean().iloc[-1])
        rsi = float(calc_rsi(close).iloc[-1])
        avg_vol = float(hist["Volume"].tail(20).mean())
        vol_ratio = float(hist["Volume"].iloc[-1] / avg_vol) if avg_vol else 1
        high52 = float(hist["High"].max())
        from_high = ((price-high52)/high52)*100 if high52 else 0

        tech = (18 if price>sma20 else 0)+(22 if price>sma50 else 0)+(25 if price>sma200 else 0)+(20 if 45<=rsi<=70 else 12 if 30<=rsi<45 else 0)+(10 if vol_ratio>=1.2 else 0)
        f_score, f_adj, f_reason = financial_safety(info)
        valuation = 50
        pe = info.get("forwardPE") or info.get("trailingPE")
        try:
            if pe and 0 < float(pe) < 22: valuation += 15
            elif pe and float(pe) > 60: valuation -= 12
        except Exception: pass
        growth = 50
        for g in [info.get("revenueGrowth"), info.get("earningsGrowth")]:
            try:
                if g is not None and float(g) > 0.10: growth += 10
                elif g is not None and float(g) < 0: growth -= 10
            except Exception: pass
        cashflow = 50
        try:
            if info.get("freeCashflow") and info.get("freeCashflow") > 0: cashflow += 20
            if info.get("operatingCashflow") and info.get("operatingCashflow") > 0: cashflow += 15
        except Exception: pass
        recovery = 50 + (25 if from_high <= -20 and 30 <= rsi <= 55 else 0)
        risk = 50 + (20 if rsi > 75 else 0) + (10 if vol_ratio > 2 else 0) + (20 if "🔴" in f_score else 0)
        final = round(max(0, min(100, (tech*.28 + valuation*.16 + growth*.16 + cashflow*.18 + recovery*.12 + (100-risk)*.10) + f_adj)), 0)
        if "🔴" in f_score: execution = "🔴 Avoid Execution"
        elif "🟠" in f_score: execution = "🟠 Watch Only / Very Small"
        elif final >= 72: execution = "🟢 Execution Candidate"
        elif final >= 58: execution = "🟡 Starter Candidate"
        else: execution = "⚪ Research Only"
        signal = "🟢 BUY NOW" if final >= 72 and "🔴" not in execution else "🟡 WATCH"
        stop = round(price*.92, 2); target = round(price*1.15, 2)
        return {
            "Ticker": ticker, "Company Name": info.get("shortName") or info.get("longName") or ticker,
            "Price": round(price,2), "Price Bucket": get_price_bucket(price), "Final Conviction": final,
            "Signal": signal, "Agent Verdict": execution, "Execution Quality": execution,
            "Financial Safety": f_score, "Financial Safety Detail": f_reason,
            "Agent Greenlight": "🟢 All-Agent Green Light" if final >= 65 and "🔴" not in f_score else "🟡 Partial Green Light",
            "Technical Agent": round(tech,0), "Valuation Agent": round(valuation,0), "Earnings Quality Agent": round(growth,0),
            "Cash Flow Agent": round(cashflow,0), "Recovery Agent": round(recovery,0), "Risk Score": round(risk,0),
            "RSI": round(rsi,1), "Volume Ratio": round(vol_ratio,2), "From 52W High %": round(from_high,1),
            "Entry Range": f"${round(price*.98,2)} - ${round(price*1.02,2)}", "Stop Loss": stop,
            "Target / Sell Zone": f"${target}", "Risk / Reward": "Approx 1.8+",
            "Revenue Growth": fmt_pct(info.get("revenueGrowth")), "Earnings Growth": fmt_pct(info.get("earningsGrowth")),
            "Free Cash Flow": fmt_money(info.get("freeCashflow")), "Operating Cash Flow": fmt_money(info.get("operatingCashflow")),
            "Total Cash": fmt_money(info.get("totalCash")), "Total Debt": fmt_money(info.get("totalDebt")),
            "Debt/Equity": info.get("debtToEquity", "N/A"), "Forward PE": info.get("forwardPE") or "N/A",
            "Why Ranked Highly": f"Scored {final}/100 from trend, liquidity, financial safety, cash flow, valuation, and recovery potential.",
            "Research Summary": f"{ticker} passed automated market scan with {execution}. Financial safety: {f_score}.",
            "AI Trade Plan": f"Entry near {round(price,2)}, stop near {stop}, initial target near {target}.",
            "Investment Style": "Recovery / Momentum" if recovery >= 65 else "Quality / Momentum",
        }
    except Exception:
        return None

def run_prescreen(universe):
    results = []
    with ThreadPoolExecutor(max_workers=PRESCREEN_WORKERS) as executor:
        for i, item in enumerate(executor.map(quick_prescreen_one, universe), start=1):
            if item: results.append(item)
            if i % 250 == 0: print(f"Prescreened {i}/{len(universe)}; candidates={len(results)}")
    results = sorted(results, key=lambda x: x.get("Quick Score", 0), reverse=True)
    write_json(PRESCREEN_FILE, results)
    return results

def run_deep_scan(prescreen):
    pre_df = pd.DataFrame(prescreen)
    if pre_df.empty: return []
    selected = []
    if "Price Bucket" in pre_df.columns:
        per_bucket = max(25, FULL_AGENT_LIMIT // 5)
        for _, sub in pre_df.groupby("Price Bucket"):
            selected += sub.sort_values("Quick Score", ascending=False)["Ticker"].head(per_bucket).tolist()
    selected += pre_df.sort_values("Quick Score", ascending=False)["Ticker"].head(FULL_AGENT_LIMIT).tolist()
    selected = list(dict.fromkeys(selected))[:FULL_AGENT_LIMIT]
    rows = [{"Ticker": t} for t in selected]
    results = []
    with ThreadPoolExecutor(max_workers=FULL_SCAN_WORKERS) as executor:
        for i, item in enumerate(executor.map(deep_analyze_one, rows), start=1):
            if item: results.append(item)
            if i % 50 == 0: print(f"Deep scanned {i}/{len(rows)}; results={len(results)}")
    results = sorted(results, key=lambda x: x.get("Final Conviction", 0), reverse=True)
    write_json(FULL_SCAN_FILE, results)
    return results

def main():
    started = datetime.now(EASTERN).isoformat()
    print("Starting automated overnight market scan...")
    universe = fetch_universe()
    print(f"Universe count: {len(universe)}")
    prescreen = run_prescreen(universe)
    print(f"Prescreen candidates: {len(prescreen)}")
    full = run_deep_scan(prescreen)
    print(f"Full scan rows: {len(full)}")
    state = {"started_at": started, "finished_at": datetime.now(EASTERN).isoformat(),
             "universe_count": len(universe), "prescreen_count": len(prescreen), "full_scan_count": len(full),
             "data_dir": str(DATA_DIR)}
    write_json(SCAN_STATE_FILE, state)
    print(json.dumps(state, indent=2))

if __name__ == "__main__":
    main()
