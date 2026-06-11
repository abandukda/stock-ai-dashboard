#!/usr/bin/env python3
"""
V41.0 AI Committee Scanner - Exclusions + Insider Intelligence
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
import datetime as dt
import requests
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf



def v42_safe_float(value, default=0.0):
    try:
        if value in (None, "", "N/A", "Unknown"):
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return default


# =========================
# CONFIG
# =========================

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

FULL_SCAN_FILE = DATA_DIR / "market_full_scan.json"
PRESCREEN_FILE = DATA_DIR / "market_prescreen.json"
STATE_FILE = DATA_DIR / "market_scan_state.json"
UNIVERSE_FILE = DATA_DIR / "total_market_universe.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
RECOVERY_SCAN_FILE = DATA_DIR / "recovery_scan.json"
ETF_SCAN_FILE = DATA_DIR / "etf_scan.json"

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

# V40.0 external research data sources
# Add these in Render Environment Variables. Missing keys are handled safely.
FMP_API_KEY = os.getenv("FMP_API_KEY", "").strip()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Asif Bandukda abandukda@gmail.com").strip()



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


def safe_text(value: Any, default: str = "") -> str:
    """
    Safe text normalization helper used by V40.3 analyst/news intelligence.
    """
    try:
        if value is None:
            return default
        text = str(value).strip()
        if text.lower() in {"", "none", "nan", "null"}:
            return default
        return text
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


def http_get_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Any:
    """
    Safe HTTP JSON helper for external research APIs.
    All failures return None so cron never breaks.
    """
    try:
        response = requests.get(url, params=params or {}, timeout=timeout)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


# =========================
# EXCLUSIONS / PREFERENCES
# =========================

EXCLUDED_SECTORS = {
    "FINANCIAL SERVICES",
}

EXCLUDED_INDUSTRY_KEYWORDS = [
    "BANK", "BANKS", "BANKING", "CREDIT", "CREDIT SERVICES",
    "LENDER", "LENDING", "LOAN", "MORTGAGE", "INSURANCE",
    "REINSURANCE", "ASSET MANAGEMENT", "CAPITAL MARKETS",
    "INVESTMENT BANKING", "WEALTH MANAGEMENT", "BROKER", "BROKERAGE",
    "CONSUMER FINANCE", "FINANCIAL DATA", "PAYMENT PROCESSING",
    "PAYMENTS", "REIT - MORTGAGE", "MORTGAGE REIT",
]

EXCLUDED_BUSINESS_KEYWORDS = [
    "casino", "casinos", "gambling", "sports betting", "wagering",
    "alcohol", "beer", "wine", "spirits", "tobacco", "cannabis",
    "marijuana", "adult entertainment", "streaming entertainment",
]

EXCLUDED_COUNTRIES = {"IL", "ISR", "ISRAEL"}
EXCLUDED_EXCHANGES = {"TASE", "TLV"}


def exclusion_reason(meta: Dict[str, Any]) -> Optional[str]:
    """
    Centralized permanent exclusion rules based on user preferences.
    Excludes financial services, Israel-based companies, and restricted categories.
    """
    sector = safe_text(meta.get("sector"), "").upper()
    industry = safe_text(meta.get("industry"), "").upper()
    country = safe_text(meta.get("country"), "").upper()
    exchange = safe_text(meta.get("exchange"), "").upper()
    description = safe_text(meta.get("description"), "").lower()
    company = safe_text(meta.get("company_name"), "").lower()
    combined_text = f"{description} {company} {industry.lower()} {sector.lower()}"

    if country in EXCLUDED_COUNTRIES:
        return "Israel-based company"
    if exchange in EXCLUDED_EXCHANGES or "TEL AVIV" in exchange:
        return "Israel/Tel Aviv exchange listing"
    if sector in EXCLUDED_SECTORS:
        return "Financial Services sector"
    if any(keyword in industry for keyword in EXCLUDED_INDUSTRY_KEYWORDS):
        return "Excluded financial/bank/lender/insurance/asset management industry"
    if any(keyword in combined_text for keyword in EXCLUDED_BUSINESS_KEYWORDS):
        return "Excluded business category"

    return None


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



def load_watchlist_symbols() -> List[str]:
    """
    V41.2: Include manually-added watchlist tickers in future scans.
    """
    try:
        if not WATCHLIST_FILE.exists():
            return []

        data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            raw_symbols = data.get("symbols", [])
        elif isinstance(data, list):
            raw_symbols = data
        else:
            raw_symbols = []

        cleaned = []
        for item in raw_symbols:
            sym = str(item).upper().strip()
            if sym and "." not in sym and "/" not in sym and len(sym) <= 7:
                cleaned.append(sym)
        return list(dict.fromkeys(cleaned))
    except Exception:
        return []


def build_universe() -> List[str]:
    symbols = set(fallback_universe())

    yahoo_symbols = get_yahoo_screeners()
    symbols.update(yahoo_symbols)

    # V41.2: force user-added watchlist tickers into the scan universe.
    watchlist_symbols = load_watchlist_symbols()
    symbols.update(watchlist_symbols)

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

    for attempt in range(2):
        try:
            data = yf.download(
                tickers=" ".join(symbols),
                period="1y",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                prepost=False,
                threads=True,
                progress=False,
            )
            return data
        except Exception:
            if attempt == 0:
                time.sleep(1.0)
                continue
            return pd.DataFrame()

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


def get_fmp_data(symbol: str) -> Dict[str, Any]:
    """
    V40.0 FMP enrichment layer.
    Pulls company profile / reference data from Financial Modeling Prep when FMP_API_KEY exists.
    This is intentionally conservative: failures return {} so the scanner never breaks.
    """
    if not FMP_API_KEY:
        return {}

    try:
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        response = requests.get(url, params={"apikey": FMP_API_KEY}, timeout=10)

        if response.status_code != 200:
            return {}

        data = response.json()
        if not isinstance(data, list) or not data:
            return {}

        row = data[0] or {}

        return {
            "company_name": row.get("companyName"),
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "market_cap": safe_float(row.get("mktCap")),
            "country": row.get("country"),
            "exchange": row.get("exchangeShortName") or row.get("exchange"),
            "fmp_price": safe_float(row.get("price")),
            "beta": safe_float(row.get("beta")),
            "last_dividend": safe_float(row.get("lastDiv")),
            "range_52w": row.get("range"),
            "website": row.get("website"),
            "description": row.get("description"),
            "source_fmp_profile": True,
        }
    except Exception:
        return {}




def get_finnhub_research(symbol: str) -> Dict[str, Any]:
    """
    V40.3 Finnhub research layer.
    Pulls recommendation trend and price target when available.
    """
    if not FINNHUB_API_KEY:
        return {}

    result: Dict[str, Any] = {}

    rec_data = http_get_json(
        "https://finnhub.io/api/v1/stock/recommendation",
        params={"symbol": symbol, "token": FINNHUB_API_KEY},
        timeout=10,
    )

    if isinstance(rec_data, list) and rec_data:
        latest = rec_data[0] or {}
        strong_buy = safe_int(latest.get("strongBuy"), 0) or 0
        buy = safe_int(latest.get("buy"), 0) or 0
        hold = safe_int(latest.get("hold"), 0) or 0
        sell = safe_int(latest.get("sell"), 0) or 0
        strong_sell = safe_int(latest.get("strongSell"), 0) or 0
        total = strong_buy + buy + hold + sell + strong_sell

        if total > 0:
            bullish_votes = strong_buy * 1.0 + buy * 0.75 + hold * 0.35
            bearish_votes = sell * 0.65 + strong_sell * 1.0
            analyst_support_score = round(max(0, min(100, ((bullish_votes - bearish_votes) / total) * 100)), 1)
        else:
            analyst_support_score = None

        result.update({
            "finnhub_period": latest.get("period"),
            "strong_buy": strong_buy,
            "buy": buy,
            "hold": hold,
            "sell": sell,
            "strong_sell": strong_sell,
            "finnhub_analyst_total": total,
            "analyst_support_score": analyst_support_score,
            "source_finnhub_recommendation": True,
        })

    target_data = http_get_json(
        "https://finnhub.io/api/v1/stock/price-target",
        params={"symbol": symbol, "token": FINNHUB_API_KEY},
        timeout=10,
    )

    if isinstance(target_data, dict) and target_data:
        result.update({
            "finnhub_target_mean": safe_float(target_data.get("targetMean")),
            "finnhub_target_high": safe_float(target_data.get("targetHigh")),
            "finnhub_target_low": safe_float(target_data.get("targetLow")),
            "finnhub_target_median": safe_float(target_data.get("targetMedian")),
            "source_finnhub_target": True,
        })

    return {k: v for k, v in result.items() if v not in (None, "", "Unknown")}


def score_headline_sentiment(title: str, description: str = "") -> Tuple[int, List[str], List[str]]:
    """
    Lightweight keyword-based news sentiment.
    Keeps the scanner deterministic and cheap while still using real headlines.
    """
    text = f"{title} {description}".lower()

    positive_terms = [
        "beat", "beats", "upgrade", "upgraded", "raised target", "raises target",
        "strong demand", "record revenue", "growth", "profit jumps", "partnership",
        "contract", "approval", "expansion", "buyback", "guidance raised",
        "outperform", "accelerating", "surge", "wins", "launches"
    ]

    negative_terms = [
        "miss", "misses", "downgrade", "downgraded", "cuts target", "cut target",
        "lawsuit", "investigation", "sec probe", "guidance cut", "weak demand",
        "layoffs", "loss widens", "decline", "falls", "plunges", "recall",
        "underperform", "bankruptcy", "fraud", "slows", "warning"
    ]

    positives = [term for term in positive_terms if term in text]
    negatives = [term for term in negative_terms if term in text]
    score = len(positives) - len(negatives)

    return score, positives[:3], negatives[:3]


def get_news_research(symbol: str, company_name: str = "") -> Dict[str, Any]:
    """
    V40.3 NewsAPI intelligence.
    Pulls recent headlines and creates catalyst/risk summary.
    """
    if not NEWSAPI_KEY:
        return {}

    query = company_name if company_name and company_name != symbol else symbol

    data = http_get_json(
        "https://newsapi.org/v2/everything",
        params={
            "q": f'"{query}" OR {symbol}',
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 8,
            "apiKey": NEWSAPI_KEY,
        },
        timeout=10,
    )

    if not isinstance(data, dict):
        return {}

    articles = data.get("articles") or []
    if not isinstance(articles, list) or not articles:
        return {}

    headlines = []
    total_score = 0
    positive_hits: List[str] = []
    negative_hits: List[str] = []

    for article in articles[:8]:
        title = safe_text(article.get("title"), "")
        description = safe_text(article.get("description"), "")
        source_name = safe_text((article.get("source") or {}).get("name"), "")
        published_at = safe_text(article.get("publishedAt"), "")

        if not title:
            continue

        score, positives, negatives = score_headline_sentiment(title, description)
        total_score += score
        positive_hits.extend(positives)
        negative_hits.extend(negatives)

        headlines.append({
            "title": title,
            "source": source_name,
            "published_at": published_at,
            "sentiment_score": score,
        })

    if not headlines:
        return {}

    if total_score > 1:
        sentiment_label = "Positive"
    elif total_score < -1:
        sentiment_label = "Negative"
    else:
        sentiment_label = "Neutral"

    return {
        "news_headline_count": len(headlines),
        "news_sentiment_score": max(-100, min(100, total_score * 15)),
        "news_sentiment_label": sentiment_label,
        "recent_headlines": headlines[:5],
        "positive_news_terms": list(dict.fromkeys(positive_hits))[:5],
        "negative_news_terms": list(dict.fromkeys(negative_hits))[:5],
        "top_news_headline": headlines[0]["title"] if headlines else "",
        "top_news_source": headlines[0]["source"] if headlines else "",
        "source_newsapi": True,
    }




def get_finnhub_insider_activity(symbol: str, days: int = 180) -> Dict[str, Any]:
    """
    V41 Insider Agent data from Finnhub.
    Uses insider transactions and insider sentiment when available.
    All failures return {} so cron remains stable.
    """
    if not FINNHUB_API_KEY:
        return {}

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    result: Dict[str, Any] = {}

    tx_data = http_get_json(
        "https://finnhub.io/api/v1/stock/insider-transactions",
        params={"symbol": symbol, "from": str(start), "to": str(end), "token": FINNHUB_API_KEY},
        timeout=10,
    )

    transactions = []
    if isinstance(tx_data, dict):
        transactions = tx_data.get("data") or []
    elif isinstance(tx_data, list):
        transactions = tx_data

    buys = 0
    sells = 0
    buy_value = 0.0
    sell_value = 0.0
    key_people = []

    if isinstance(transactions, list):
        for tx in transactions[:80]:
            if not isinstance(tx, dict):
                continue
            shares = safe_float(tx.get("share") or tx.get("change") or tx.get("shares"), 0) or 0
            price = safe_float(tx.get("transactionPrice") or tx.get("price"), 0) or 0
            tx_value = abs(shares * price)
            code = safe_text(tx.get("transactionCode") or tx.get("code"), "").upper()
            name = safe_text(tx.get("name") or tx.get("reportingName"), "")

            # Finnhub commonly uses P for purchase and S for sale.
            if code == "P" or shares > 0:
                buys += 1
                buy_value += tx_value
            elif code == "S" or shares < 0:
                sells += 1
                sell_value += tx_value

            if name and len(key_people) < 3:
                key_people.append(name)

    sentiment_data = http_get_json(
        "https://finnhub.io/api/v1/stock/insider-sentiment",
        params={"symbol": symbol, "from": str(start), "to": str(end), "token": FINNHUB_API_KEY},
        timeout=10,
    )

    mspr_values = []
    change_values = []
    if isinstance(sentiment_data, dict):
        for row in sentiment_data.get("data") or []:
            if not isinstance(row, dict):
                continue
            mspr = safe_float(row.get("mspr"), None)
            change = safe_float(row.get("change"), None)
            if mspr is not None:
                mspr_values.append(mspr)
            if change is not None:
                change_values.append(change)

    avg_mspr = sum(mspr_values) / len(mspr_values) if mspr_values else None
    net_change = sum(change_values) if change_values else None

    if buys == 0 and sells == 0 and avg_mspr is None and net_change is None:
        return {}

    insider_score = 50.0
    if buy_value > 0 or sell_value > 0:
        net_value = buy_value - sell_value
        total_value = buy_value + sell_value
        value_ratio = net_value / total_value if total_value else 0
        insider_score += value_ratio * 30
    insider_score += min(buys, 6) * 2.0
    insider_score -= min(sells, 8) * 1.5
    if avg_mspr is not None:
        insider_score += max(min(avg_mspr * 25, 15), -15)
    insider_score = round(clamp(insider_score, 0, 100), 1)

    if insider_score >= 70:
        label = "Positive"
    elif insider_score >= 45:
        label = "Neutral/Mixed"
    else:
        label = "Negative"

    return {
        "insider_score": insider_score,
        "insider_activity_label": label,
        "insider_buy_count": buys,
        "insider_sell_count": sells,
        "insider_buy_value": round(buy_value, 2),
        "insider_sell_value": round(sell_value, 2),
        "insider_avg_mspr": round(avg_mspr, 3) if avg_mspr is not None else None,
        "insider_net_change": round(net_change, 2) if net_change is not None else None,
        "insider_key_people": list(dict.fromkeys(key_people))[:3],
        "source_finnhub_insider": True,
    }


def agent_score_label(score: Optional[float]) -> str:
    value = safe_float(score, None)
    if value is None:
        return "N/A"
    if value >= 80:
        return "Positive"
    if value >= 60:
        return "Constructive"
    if value >= 45:
        return "Neutral"
    if value >= 30:
        return "Caution"
    return "Negative"


def build_agent_summary(name: str, score: Optional[float], summary: str, findings: List[str], impact: str, data_used: str) -> Dict[str, Any]:
    clean_findings = [safe_text(x, "") for x in findings if safe_text(x, "")]
    return {
        "agent": name,
        "score": int(round(safe_float(score, 50) or 50)),
        "status": agent_score_label(score),
        "summary": safe_text(summary, "No summary available."),
        "findings": clean_findings[:6],
        "impact": safe_text(impact, "Neutral"),
        "data_used": safe_text(data_used, "Internal model data"),
    }


def build_ai_committee(symbol: str, meta: Dict[str, Any], ind: Dict[str, Any], target_model: Dict[str, Any], score: int, good: List[str], risks: List[str], plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    V41 AI Committee Summary.
    Turns the raw data into per-agent summaries so the dashboard can show why a stock ranked highly.
    """
    price = ind.get("price") or 0
    rsi = ind.get("rsi") or 50
    twenty = ind.get("twenty_day_pct") or 0
    sixty = ind.get("sixty_day_pct") or 0
    volume_ratio = ind.get("volume_ratio") or 1
    atr_pct = ind.get("atr_pct") or 4
    revenue_growth = meta.get("revenue_growth")
    earnings_growth = meta.get("earnings_growth")
    forward_pe = meta.get("forward_pe")
    peg_ratio = meta.get("peg_ratio")
    analyst_support = meta.get("analyst_support_score")
    news_score = meta.get("news_sentiment_score")
    news_label = meta.get("news_sentiment_label") or "N/A"
    insider_score = meta.get("insider_score")
    insider_label = meta.get("insider_activity_label") or "N/A"
    expected_upside = target_model.get("expected_upside_pct") or 0
    ai_adjust = target_model.get("ai_fair_value_adjustment_pct") or 0

    technical_score = 50
    if ind.get("sma20") and price > ind.get("sma20"):
        technical_score += 12
    if ind.get("sma50") and price > ind.get("sma50"):
        technical_score += 12
    if 2 <= twenty <= 25:
        technical_score += 10
    elif twenty < -8 or twenty > 35:
        technical_score -= 8
    if 5 <= sixty <= 45:
        technical_score += 8
    if 48 <= rsi <= 68:
        technical_score += 8
    elif rsi > 76:
        technical_score -= 10
    if volume_ratio >= 1.25:
        technical_score += 7
    technical_score = clamp(technical_score, 0, 100)

    fundamental_score = 50
    if revenue_growth is not None:
        fundamental_score += 18 if revenue_growth >= 0.20 else 9 if revenue_growth >= 0.08 else -8 if revenue_growth < 0 else 0
    if earnings_growth is not None:
        fundamental_score += 14 if earnings_growth >= 0.15 else 7 if earnings_growth >= 0.05 else -8 if earnings_growth < 0 else 0
    if forward_pe is not None and 0 < forward_pe <= 35:
        fundamental_score += 6
    if peg_ratio is not None and 0 < peg_ratio <= 2.5:
        fundamental_score += 6
    fundamental_score = clamp(fundamental_score, 0, 100)

    valuation_score = 50
    if expected_upside >= 40:
        valuation_score += 25
    elif expected_upside >= 20:
        valuation_score += 16
    elif expected_upside >= 8:
        valuation_score += 8
    elif expected_upside < 0:
        valuation_score -= 20
    valuation_score += clamp(ai_adjust, -20, 40) * 0.25
    valuation_score = clamp(valuation_score, 0, 100)

    analyst_score = safe_float(analyst_support, None)
    if analyst_score is None:
        analyst_score = 50
        analyst_summary = "Analyst support data was limited or unavailable."
    else:
        analyst_summary = f"Analyst support score is {analyst_score:.0f}/100 based on Finnhub recommendation mix."

    news_agent_score = 50 + clamp(safe_float(news_score, 0) or 0, -60, 60) * 0.45
    news_agent_score = clamp(news_agent_score, 0, 100)

    risk_score = 80
    if atr_pct > 9:
        risk_score -= 25
    elif atr_pct > 6:
        risk_score -= 12
    if rsi > 76:
        risk_score -= 10
    if twenty > 35:
        risk_score -= 8
    risk_score = clamp(risk_score, 0, 100)

    quality_score = 50
    if revenue_growth is not None and revenue_growth > 0.08:
        quality_score += 15
    if earnings_growth is not None and earnings_growth > 0.08:
        quality_score += 15
    if peg_ratio is not None and 0 < peg_ratio <= 2.5:
        quality_score += 8
    if forward_pe is not None and forward_pe > 75:
        quality_score -= 10
    quality_score = clamp(quality_score, 0, 100)

    insider_agent_score = safe_float(insider_score, 50) or 50

    divergence_pct = None
    analyst_target = target_model.get("analyst_target_mean")
    ai_target = target_model.get("ai_base_target")
    if analyst_target and ai_target:
        divergence_pct = ((ai_target - analyst_target) / analyst_target) * 100

    if divergence_pct is None:
        valuation_recon = "Analyst target was unavailable, so AI fair value relies more on technicals, growth, valuation, and risk."
    elif abs(divergence_pct) <= 20:
        valuation_recon = "AI fair value is broadly aligned with analyst consensus."
    elif divergence_pct > 20:
        valuation_recon = f"AI is {divergence_pct:.1f}% more optimistic than analyst consensus, mainly due to growth/trend/valuation adjustments."
    else:
        valuation_recon = f"AI is {abs(divergence_pct):.1f}% more conservative than analyst consensus due to risk or weaker confirmations."

    agents = [
        build_agent_summary(
            "Technical Agent", technical_score,
            "Evaluates trend, momentum, RSI, volume, and volatility.",
            [
                f"20-day move: {twenty:.1f}%",
                f"60-day move: {sixty:.1f}%",
                f"RSI: {rsi:.1f}",
                f"Volume ratio: {volume_ratio:.2f}x",
            ],
            "Positive" if technical_score >= 70 else "Neutral" if technical_score >= 50 else "Caution",
            "Yahoo/yfinance price history and volume",
        ),
        build_agent_summary(
            "Fundamental Agent", fundamental_score,
            "Evaluates growth, earnings, and valuation context.",
            [
                f"Revenue growth: {revenue_growth * 100:.1f}%" if revenue_growth is not None else "Revenue growth unavailable",
                f"Earnings growth: {earnings_growth * 100:.1f}%" if earnings_growth is not None else "Earnings growth unavailable",
                f"Forward PE: {forward_pe:.1f}" if forward_pe is not None else "Forward PE unavailable",
                f"PEG ratio: {peg_ratio:.2f}" if peg_ratio is not None else "PEG ratio unavailable",
            ],
            "Positive" if fundamental_score >= 70 else "Neutral" if fundamental_score >= 50 else "Caution",
            "Yahoo/FMP fundamentals and company profile",
        ),
        build_agent_summary(
            "Valuation Agent", valuation_score,
            valuation_recon,
            [
                f"Current price: ${price:.2f}" if price else "Current price unavailable",
                f"Analyst target: ${analyst_target:.2f}" if analyst_target else "Analyst target unavailable",
                f"AI fair value: ${ai_target:.2f}" if ai_target else "AI fair value unavailable",
                f"AI upside: {expected_upside:.1f}%",
            ],
            "Positive" if valuation_score >= 70 else "Neutral" if valuation_score >= 50 else "Caution",
            "Yahoo/Finnhub analyst targets plus AI fair value model",
        ),
        build_agent_summary(
            "News Agent", news_agent_score,
            f"Recent news flow is {str(news_label).lower()}.",
            [
                f"News sentiment score: {safe_float(news_score, 0) or 0:.0f}",
                f"Top headline: {meta.get('top_news_headline')}" if meta.get('top_news_headline') else "Top headline unavailable",
            ],
            "Positive" if news_agent_score >= 65 else "Neutral" if news_agent_score >= 45 else "Caution",
            "NewsAPI recent headlines",
        ),
        build_agent_summary(
            "Analyst Agent", analyst_score,
            analyst_summary,
            [
                f"Strong buy: {meta.get('strong_buy', 'N/A')}",
                f"Buy: {meta.get('buy', 'N/A')}",
                f"Hold: {meta.get('hold', 'N/A')}",
                f"Sell: {meta.get('sell', 'N/A')}",
            ],
            "Positive" if analyst_score >= 65 else "Neutral" if analyst_score >= 45 else "Caution",
            "Finnhub recommendation trends and price targets",
        ),
        build_agent_summary(
            "Insider Agent", insider_agent_score,
            f"Insider activity is {str(insider_label).lower()} over the recent lookback window.",
            [
                f"Insider buys: {meta.get('insider_buy_count', 0)}",
                f"Insider sells: {meta.get('insider_sell_count', 0)}",
                f"Buy value: ${safe_float(meta.get('insider_buy_value'), 0):,.0f}",
                f"Sell value: ${safe_float(meta.get('insider_sell_value'), 0):,.0f}",
            ],
            "Positive" if insider_agent_score >= 70 else "Neutral" if insider_agent_score >= 45 else "Caution",
            "Finnhub insider transactions and sentiment",
        ),
        build_agent_summary(
            "Risk Agent", risk_score,
            "Evaluates volatility, extension risk, and technical downside risk.",
            [
                f"ATR volatility: {atr_pct:.1f}%",
                f"RSI: {rsi:.1f}",
                f"Stop loss: ${plan.get('stop_loss')}" if plan.get('stop_loss') else "Stop loss unavailable",
            ],
            "Positive" if risk_score >= 70 else "Moderate Risk" if risk_score >= 45 else "High Risk",
            "ATR, RSI, price extension, and stop-loss model",
        ),
        build_agent_summary(
            "Quality Agent", quality_score,
            "Measures evidence quality and business durability using available growth and valuation signals.",
            [
                "Positive revenue growth" if revenue_growth is not None and revenue_growth > 0 else "Revenue growth not confirmed",
                "Positive earnings growth" if earnings_growth is not None and earnings_growth > 0 else "Earnings growth not confirmed",
                "Valuation not excessive" if forward_pe is not None and forward_pe <= 35 else "Valuation requires review",
            ],
            "Positive" if quality_score >= 70 else "Neutral" if quality_score >= 50 else "Caution",
            "Yahoo/FMP quality and valuation fields",
        ),
    ]

    positive_agents = sum(1 for a in agents if a["score"] >= 70)
    caution_agents = sum(1 for a in agents if a["score"] < 45)

    if positive_agents >= 6 and caution_agents == 0:
        thesis_strength = "Exceptional Thesis"
        evidence_confidence = "High"
    elif positive_agents >= 4:
        thesis_strength = "Strong Thesis"
        evidence_confidence = "Medium-High"
    elif positive_agents >= 2:
        thesis_strength = "Moderate Thesis"
        evidence_confidence = "Medium"
    else:
        thesis_strength = "Weak / Watchlist Thesis"
        evidence_confidence = "Low-Medium"

    committee_conclusion = (
        f"{symbol} has a {thesis_strength.lower()} with {positive_agents} supportive agents. "
        f"Main positives: {', '.join(good[:3]) if good else 'limited positive confirmations'}. "
        f"Main risks: {', '.join(risks[:2]) if risks else 'normal market pullback risk'}."
    )

    return {
        "agents": agents,
        "thesis_strength": thesis_strength,
        "evidence_confidence": evidence_confidence,
        "positive_agent_count": positive_agents,
        "caution_agent_count": caution_agents,
        "valuation_reconciliation": valuation_recon,
        "committee_conclusion": committee_conclusion,
    }


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



def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_conviction(raw_score: float, ind: Dict[str, Any], meta: Dict[str, Any]) -> int:
    """
    V40.1 normalized conviction model.
    Prevents too many 99s by translating raw stacked points into a realistic score band.
    Exceptional scores require multiple confirmations, not just momentum.
    """
    price = ind.get("price") or 0
    rsi = ind.get("rsi") or 50
    volume_ratio = ind.get("volume_ratio") or 1
    twenty = ind.get("twenty_day_pct") or 0
    sixty = ind.get("sixty_day_pct") or 0
    atr_pct = ind.get("atr_pct") or 4
    dollar_volume = ind.get("dollar_volume") or 0
    analyst_mean = meta.get("analyst_target_mean")
    analyst_count = meta.get("analyst_count") or 0
    revenue_growth = meta.get("revenue_growth")
    earnings_growth = meta.get("earnings_growth")
    forward_pe = meta.get("forward_pe")
    peg_ratio = meta.get("peg_ratio")

    base = 48 + (raw_score * 0.42)

    confirmations = 0
    penalties = 0

    if dollar_volume >= 100_000_000:
        confirmations += 1
    if 48 <= rsi <= 68:
        confirmations += 1
    if 2 <= twenty <= 25:
        confirmations += 1
    if 5 <= sixty <= 45:
        confirmations += 1
    if volume_ratio >= 1.25:
        confirmations += 1
    if price and analyst_mean and analyst_count >= 3:
        analyst_upside = ((analyst_mean - price) / price) * 100
        if analyst_upside >= 12:
            confirmations += 1
        elif analyst_upside < 0:
            penalties += 1
    if revenue_growth is not None and revenue_growth > 0.08:
        confirmations += 1
    if earnings_growth is not None and earnings_growth > 0.08:
        confirmations += 1
    if peg_ratio is not None and 0 < peg_ratio <= 2.5:
        confirmations += 1

    if rsi > 76:
        penalties += 1
    if twenty > 35:
        penalties += 1
    if atr_pct > 9:
        penalties += 1
    if forward_pe is not None and forward_pe > 75 and (revenue_growth or 0) < 0.15:
        penalties += 1

    score = base + confirmations * 2.1 - penalties * 4.0

    if confirmations < 4:
        score = min(score, 82)
    elif confirmations < 6:
        score = min(score, 89)
    elif confirmations < 8:
        score = min(score, 94)
    else:
        score = min(score, 97)

    if rsi > 78 or atr_pct > 10:
        score = min(score, 86)
    if twenty < -8:
        score = min(score, 78)
    if analyst_mean and price and analyst_count >= 3 and analyst_mean < price:
        score = min(score, 82)

    return int(round(clamp(score, 20, 97)))


def add_research_quality_adjustments(score: int, good: List[str], risks: List[str], meta: Dict[str, Any]) -> Tuple[int, List[str], List[str]]:
    """
    Adds light fundamental/valuation context from available data.
    """
    revenue_growth = meta.get("revenue_growth")
    earnings_growth = meta.get("earnings_growth")
    forward_pe = meta.get("forward_pe")
    peg_ratio = meta.get("peg_ratio")
    beta = meta.get("beta")

    if revenue_growth is not None:
        if revenue_growth >= 0.20:
            score += 3
            good.append(f"revenue growth is strong at {revenue_growth * 100:.1f}%")
        elif revenue_growth < 0:
            score -= 4
            risks.append("revenue growth is negative")

    if earnings_growth is not None:
        if earnings_growth >= 0.15:
            score += 3
            good.append(f"earnings growth is positive at {earnings_growth * 100:.1f}%")
        elif earnings_growth < 0:
            score -= 4
            risks.append("earnings growth is negative")

    if peg_ratio is not None:
        if 0 < peg_ratio <= 2.0:
            score += 2
            good.append("PEG ratio looks reasonable versus growth")
        elif peg_ratio > 4:
            score -= 3
            risks.append("PEG ratio suggests valuation risk")

    if forward_pe is not None:
        if 0 < forward_pe <= 30:
            score += 2
            good.append("forward valuation is not excessive")
        elif forward_pe > 70:
            score -= 3
            risks.append("forward valuation is elevated")

    if beta is not None and beta > 2:
        score -= 2
        risks.append("beta is high, so price swings may be larger")

    return score, good, risks


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

    # V40.3: external analyst/news intelligence.
    analyst_support_score = meta.get("analyst_support_score")
    if analyst_support_score is not None:
        if analyst_support_score >= 65:
            score += 5
            good.append(f"Finnhub analyst support is strong at {analyst_support_score:.0f}/100")
        elif analyst_support_score >= 45:
            score += 2
            good.append(f"Finnhub analyst support is constructive at {analyst_support_score:.0f}/100")
        elif analyst_support_score < 20:
            score -= 5
            risks.append("Finnhub analyst support is weak")

    news_sentiment_score = meta.get("news_sentiment_score")
    news_label = meta.get("news_sentiment_label")
    if news_sentiment_score is not None:
        if news_sentiment_score >= 30:
            score += 4
            good.append("recent news flow appears positive")
        elif news_sentiment_score <= -30:
            score -= 5
            risks.append("recent news flow appears negative")
        elif news_label:
            good.append(f"recent news flow is {str(news_label).lower()}")

    # V41: Insider activity intelligence.
    insider_score = meta.get("insider_score")
    insider_label = meta.get("insider_activity_label")
    if insider_score is not None:
        if insider_score >= 70:
            score += 4
            good.append(f"insider activity is positive ({insider_score:.0f}/100)")
        elif insider_score < 35:
            score -= 4
            risks.append(f"insider activity is weak ({insider_score:.0f}/100)")
        elif insider_label:
            good.append(f"insider activity is {str(insider_label).lower()}")

    # V40.1/V40.3/V41: add available research/fundamental context, then normalize.
    score, good, risks = add_research_quality_adjustments(score, good, risks, meta)
    normalized_score = normalize_conviction(score, ind, meta)

    return normalized_score, good[:10], risks[:10]



def build_ai_target_model(ind: Dict[str, Any], meta: Dict[str, Any], score: int) -> Dict[str, Any]:
    """
    V40.1 AI Fair Value Engine.
    Builds bear/base/bull targets from analyst reference data when available,
    then adjusts using growth, valuation, trend quality, volume, and risk.
    This avoids generic ~30% upside behavior.
    """
    price = ind.get("price")
    if not price:
        return {}

    analyst_mean = meta.get("analyst_target_mean")
    analyst_high = meta.get("analyst_target_high")
    analyst_low = meta.get("analyst_target_low")
    analyst_count = meta.get("analyst_count") or 0

    # V40.3: use Finnhub target data as fallback or secondary source.
    finnhub_mean = meta.get("finnhub_target_mean")
    finnhub_high = meta.get("finnhub_target_high")
    finnhub_low = meta.get("finnhub_target_low")
    if (not analyst_mean or analyst_mean <= 0) and finnhub_mean:
        analyst_mean = finnhub_mean
    if (not analyst_high or analyst_high <= 0) and finnhub_high:
        analyst_high = finnhub_high
    if (not analyst_low or analyst_low <= 0) and finnhub_low:
        analyst_low = finnhub_low
    if analyst_count <= 0:
        analyst_count = meta.get("finnhub_analyst_total") or 0
    recommendation_key = meta.get("recommendation_key") or "unknown"
    recommendation_mean = meta.get("recommendation_mean")

    revenue_growth = meta.get("revenue_growth")
    earnings_growth = meta.get("earnings_growth")
    forward_pe = meta.get("forward_pe")
    peg_ratio = meta.get("peg_ratio")
    beta = meta.get("beta")

    twenty = ind.get("twenty_day_pct") or 0
    sixty = ind.get("sixty_day_pct") or 0
    rsi = ind.get("rsi") or 50
    volume_ratio = ind.get("volume_ratio") or 1
    atr_pct = ind.get("atr_pct") or 4
    high20 = ind.get("rolling_high_20") or price
    high60 = ind.get("rolling_high_60") or high20
    sma20 = ind.get("sma20") or price
    sma50 = ind.get("sma50") or price

    has_analyst_targets = (
        analyst_mean is not None and analyst_mean > 0 and
        analyst_high is not None and analyst_high > 0 and
        analyst_low is not None and analyst_low > 0 and
        analyst_count >= 3
    )

    growth_score = 0.0
    if revenue_growth is not None:
        if revenue_growth >= 0.30:
            growth_score += 0.18
        elif revenue_growth >= 0.15:
            growth_score += 0.11
        elif revenue_growth >= 0.05:
            growth_score += 0.05
        elif revenue_growth < 0:
            growth_score -= 0.12

    if earnings_growth is not None:
        if earnings_growth >= 0.30:
            growth_score += 0.16
        elif earnings_growth >= 0.15:
            growth_score += 0.09
        elif earnings_growth >= 0.05:
            growth_score += 0.04
        elif earnings_growth < 0:
            growth_score -= 0.12

    valuation_score = 0.0
    if peg_ratio is not None:
        if 0 < peg_ratio <= 1.5:
            valuation_score += 0.10
        elif 1.5 < peg_ratio <= 2.5:
            valuation_score += 0.04
        elif peg_ratio > 4:
            valuation_score -= 0.10

    if forward_pe is not None:
        if 0 < forward_pe <= 25:
            valuation_score += 0.07
        elif 25 < forward_pe <= 45:
            valuation_score += 0.02
        elif forward_pe > 75:
            valuation_score -= 0.10

    technical_score = 0.0
    if price > sma20:
        technical_score += 0.04
    if price > sma50:
        technical_score += 0.05
    if 2 <= twenty <= 25:
        technical_score += 0.07
    elif twenty > 35:
        technical_score -= 0.06
    elif twenty < -8:
        technical_score -= 0.10

    if 5 <= sixty <= 45:
        technical_score += 0.05
    elif sixty > 80:
        technical_score -= 0.06

    if 48 <= rsi <= 68:
        technical_score += 0.06
    elif rsi > 76:
        technical_score -= 0.10

    if volume_ratio >= 2.0:
        technical_score += 0.07
    elif volume_ratio >= 1.25:
        technical_score += 0.04
    elif volume_ratio < 0.65:
        technical_score -= 0.04

    risk_penalty = 0.0
    if atr_pct > 9:
        risk_penalty += 0.10
    elif atr_pct > 6:
        risk_penalty += 0.05

    if beta is not None and beta > 2:
        risk_penalty += 0.05

    if recommendation_key in {"sell", "underperform"}:
        risk_penalty += 0.12

    total_adjustment = growth_score + valuation_score + technical_score - risk_penalty
    total_adjustment = clamp(total_adjustment, -0.30, 0.70)

    if has_analyst_targets:
        analyst_upside_pct = ((analyst_mean - price) / price) * 100
        high_upside_pct = ((analyst_high - price) / price) * 100
        low_upside_pct = ((analyst_low - price) / price) * 100

        if total_adjustment >= 0:
            ai_base = analyst_mean + ((analyst_high - analyst_mean) * min(total_adjustment, 0.70))
        else:
            ai_base = analyst_mean + ((analyst_mean - analyst_low) * total_adjustment)

        if analyst_upside_pct < 8 and total_adjustment > 0.25:
            ai_base = max(ai_base, price * (1 + min(0.08 + total_adjustment, 0.38)))

        ai_bull = max(ai_base * 1.10, analyst_high if analyst_high > ai_base else ai_base * 1.15)
        ai_bull = min(ai_bull, price * 2.25)

        ai_bear = min(analyst_low, price * (1 - min(0.08 + risk_penalty, 0.28)))
        ai_bear = max(ai_bear, price * 0.55)

        target_source = "Multi-factor AI fair value using analyst consensus, growth, valuation, trend, volume, and risk"
        confidence_note = (
            f"AI blended {analyst_count} analyst opinions with growth, valuation, momentum, volume, and risk. "
            f"Consensus target ${analyst_mean:.2f}; AI adjustment {total_adjustment * 100:.1f}%."
        )
    else:
        analyst_upside_pct = None
        high_upside_pct = None
        low_upside_pct = None

        base_multiplier = 1.00 + clamp(0.08 + total_adjustment, -0.18, 0.65)

        technical_anchor = max(high20 * 1.02, high60 * 1.01)
        ai_base = max(price * base_multiplier, technical_anchor)
        ai_base = min(ai_base, price * 1.75)

        ai_bull = min(max(ai_base * 1.18, price * (1.15 + max(total_adjustment, 0))), price * 2.10)
        ai_bear = max(price * (0.82 - min(risk_penalty, 0.18)), price * 0.55)

        target_source = "Multi-factor AI fair value; analyst target unavailable"
        confidence_note = (
            f"Analyst target data unavailable. AI used growth, valuation, trend, volume, recent highs, and risk. "
            f"AI adjustment {total_adjustment * 100:.1f}%."
        )

    expected_upside_pct = ((ai_base - price) / price) * 100

    ai_bear = min(ai_bear, price * 0.98, ai_base * 0.90)
    ai_bull = max(ai_bull, ai_base * 1.08)

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
        "ai_fair_value_adjustment_pct": round(total_adjustment * 100, 1),
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
        rank_reason = "High conviction because multiple signals align across trend, liquidity, momentum, valuation/growth context, and risk control."
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
        "country": meta.get("country"),
        "exchange": meta.get("exchange"),
        "beta": meta.get("beta"),
        "range_52w": meta.get("range_52w"),
        "website": meta.get("website"),
        "source_fmp_profile": meta.get("source_fmp_profile", False),
        "source_fmp_financials": meta.get("source_fmp_financials", False),
        "source_fmp_earnings_surprises": meta.get("source_fmp_earnings_surprises", False),
        "latest_revenue": meta.get("latest_revenue"),
        "latest_eps": meta.get("latest_eps"),
        "revenue_qoq_pct": meta.get("revenue_qoq_pct"),
        "revenue_quarters": meta.get("revenue_quarters"),
        "eps_quarters": meta.get("eps_quarters"),
        "eps_surprises_last4": meta.get("eps_surprises_last4"),
        "eps_beats_last4": meta.get("eps_beats_last4"),
        "eps_misses_last4": meta.get("eps_misses_last4"),
        "total_debt": meta.get("total_debt"),
        "cash_and_equivalents": meta.get("cash_and_equivalents"),
        "net_cash": meta.get("net_cash"),
        "debt_to_equity": meta.get("debt_to_equity"),
        "debt_to_assets": meta.get("debt_to_assets"),
        "current_ratio": meta.get("current_ratio"),
        "gross_profit_margin": meta.get("gross_profit_margin"),
        "operating_profit_margin": meta.get("operating_profit_margin"),
        "net_profit_margin": meta.get("net_profit_margin"),
        "operating_cash_flow": meta.get("operating_cash_flow"),
        "free_cash_flow": meta.get("free_cash_flow"),
        "roic": meta.get("roic"),
        "ev_to_sales": meta.get("ev_to_sales"),
        "ev_to_ebitda": meta.get("ev_to_ebitda"),
        "peer_symbols": meta.get("peer_symbols"),

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
        "ai_confidence": score,
        "confidence": score,
        "ai_fair_value_adjustment_pct": target_model.get("ai_fair_value_adjustment_pct"),
        "target_source": target_model.get("target_source"),
        "target_confidence_note": target_model.get("target_confidence_note"),
        "recommendation_key": target_model.get("recommendation_key"),
        "recommendation_mean": target_model.get("recommendation_mean"),
        "analyst_support_score": meta.get("analyst_support_score"),
        "finnhub_analyst_total": meta.get("finnhub_analyst_total"),
        "strong_buy": meta.get("strong_buy"),
        "buy": meta.get("buy"),
        "hold": meta.get("hold"),
        "sell": meta.get("sell"),
        "strong_sell": meta.get("strong_sell"),
        "finnhub_target_mean": meta.get("finnhub_target_mean"),
        "finnhub_target_high": meta.get("finnhub_target_high"),
        "finnhub_target_low": meta.get("finnhub_target_low"),
        "news_sentiment_score": meta.get("news_sentiment_score"),
        "news_sentiment_label": meta.get("news_sentiment_label"),
        "top_news_headline": meta.get("top_news_headline"),
        "top_news_source": meta.get("top_news_source"),
        "recent_headlines": meta.get("recent_headlines"),
        "positive_news_terms": meta.get("positive_news_terms"),
        "negative_news_terms": meta.get("negative_news_terms"),

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
            f"Analyst support score: {meta.get('analyst_support_score', 'N/A')}. "
            f"News flow: {meta.get('news_sentiment_label', 'N/A')}. "
            f"Key risk: {guidance.get('what_could_go_wrong', '').lower()}."
        ),
        "table_reason": (
            f"AI target ${target_model.get('ai_base_target')} / upside {target_model.get('expected_upside_pct')}%. "
            f"{guidance.get('why_ranked_high')} "
            f"Watch entry {plan.get('entry_range')} with stop near ${plan.get('stop_loss')}."
        ),
        "opportunity_reason": (
            f"AI fair-value upside: {target_model.get('expected_upside_pct')}%. "
            f"{target_model.get('target_confidence_note')} "
            f"Analyst support score: {meta.get('analyst_support_score', 'N/A')}. "
            f"Latest news: {meta.get('top_news_headline', 'N/A')}"
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
        # V41.6 price history fields are merged after row creation.
        "scan_time": now_iso(),
    }

    committee = build_ai_committee(symbol, meta, ind, target_model, score, good, risks, plan)
    row["ai_committee"] = committee.get("agents", [])
    row["thesis_strength"] = committee.get("thesis_strength")
    row["evidence_confidence"] = committee.get("evidence_confidence")
    row["positive_agent_count"] = committee.get("positive_agent_count")
    row["caution_agent_count"] = committee.get("caution_agent_count")
    row["valuation_reconciliation"] = committee.get("valuation_reconciliation")
    row["committee_conclusion"] = committee.get("committee_conclusion")

    # V41 insider fields exposed to dashboard.
    row["insider_score"] = meta.get("insider_score")
    row["insider_activity_label"] = meta.get("insider_activity_label")
    row["insider_buy_count"] = meta.get("insider_buy_count")
    row["insider_sell_count"] = meta.get("insider_sell_count")
    row["insider_buy_value"] = meta.get("insider_buy_value")
    row["insider_sell_value"] = meta.get("insider_sell_value")
    row["source_finnhub_insider"] = meta.get("source_finnhub_insider", False)

    return row


def normalize_final_convictions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    V40.6 final ranking normalization.
    Prevents every strong idea from clustering at 97 by ranking completed rows
    against each other using conviction, upside, analyst support, news, risk/reward,
    liquidity, and valuation adjustment.

    This keeps the best ideas high, but creates useful separation:
    97, 95, 94, 92, 90, 88, etc.
    """
    if not rows:
        return rows

    enriched = []
    for row in rows:
        base = safe_float(row.get("conviction"), 0) or 0
        upside = safe_float(row.get("expected_upside_pct"), row.get("upside")) or 0
        analyst_support = safe_float(row.get("analyst_support_score"), 50)
        news_score = safe_float(row.get("news_sentiment_score"), 0) or 0
        rr = safe_float(row.get("risk_reward"), 0) or 0
        dollar_volume = safe_float(row.get("dollar_volume"), 0) or 0
        atr_pct = safe_float(row.get("atr_pct"), 4) or 4
        ai_adjust = safe_float(row.get("ai_fair_value_adjustment_pct"), 0) or 0
        analyst_count = safe_float(row.get("analyst_count"), 0) or 0

        # Weighted rank score. This is not displayed directly.
        rank_score = 0.0
        rank_score += base * 1.00
        rank_score += min(max(upside, -20), 80) * 0.22
        rank_score += (analyst_support - 50) * 0.12
        rank_score += max(min(news_score, 60), -60) * 0.05
        rank_score += min(rr, 5) * 1.10
        rank_score += min(max(ai_adjust, -20), 50) * 0.08
        rank_score += min(analyst_count, 40) * 0.06

        if dollar_volume >= 250_000_000:
            rank_score += 2.0
        elif dollar_volume >= 75_000_000:
            rank_score += 1.0

        if atr_pct > 9:
            rank_score -= 4.0
        elif atr_pct > 6:
            rank_score -= 2.0

        enriched.append((rank_score, row))

    enriched.sort(key=lambda item: item[0], reverse=True)

    n = len(enriched)
    normalized_rows = []

    for idx, (rank_score, row) in enumerate(enriched):
        pct_rank = idx / max(n - 1, 1)

        # Score bands by rank position.
        if pct_rank <= 0.02:
            new_score = 97
        elif pct_rank <= 0.05:
            new_score = 96
        elif pct_rank <= 0.10:
            new_score = 95
        elif pct_rank <= 0.16:
            new_score = 94
        elif pct_rank <= 0.24:
            new_score = 92
        elif pct_rank <= 0.34:
            new_score = 90
        elif pct_rank <= 0.48:
            new_score = 88
        elif pct_rank <= 0.64:
            new_score = 85
        elif pct_rank <= 0.80:
            new_score = 82
        else:
            new_score = 78

        # Risk and weak-evidence caps.
        upside = safe_float(row.get("expected_upside_pct"), row.get("upside")) or 0
        analyst_support = safe_float(row.get("analyst_support_score"), None)
        news_score = safe_float(row.get("news_sentiment_score"), 0) or 0
        atr_pct = safe_float(row.get("atr_pct"), 4) or 4

        if upside < 8:
            new_score = min(new_score, 86)
        if analyst_support is not None and analyst_support < 25:
            new_score = min(new_score, 84)
        if news_score <= -45:
            new_score = min(new_score, 84)
        if atr_pct > 9:
            new_score = min(new_score, 83)

        row["raw_conviction_before_normalization"] = row.get("conviction")
        row["relative_rank_score"] = round(rank_score, 2)
        row["conviction"] = int(new_score)
        row["conviction_score"] = int(new_score)
        row["score"] = int(new_score)
        row["ai_score"] = int(new_score)
        row["ai_confidence"] = int(new_score)
        row["confidence"] = int(new_score)

        # Refresh summary text with updated score if present.
        if row.get("company_name") and row.get("expected_upside_pct") is not None:
            row["summary"] = (
                f"{row.get('company_name')}: normalized conviction {new_score}/100, "
                f"AI target ${row.get('ai_base_target')} with {row.get('expected_upside_pct')}% upside."
            )

        normalized_rows.append(row)

    return normalized_rows


def build_recovery_case(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    V41.1 Recovery Intelligence.
    Finds stocks that dropped because of price/news/earnings pressure but still have forward upside.
    """
    twenty = safe_float(row.get("twenty_day_pct"), 0) or 0
    sixty = safe_float(row.get("sixty_day_pct"), 0) or 0
    upside = safe_float(row.get("expected_upside_pct"), row.get("upside")) or 0
    analyst_support = safe_float(row.get("analyst_support_score"), 50)
    news_score = safe_float(row.get("news_sentiment_score"), 0) or 0
    revenue_growth = safe_float(row.get("revenue_growth"), None)
    earnings_growth = safe_float(row.get("earnings_growth"), None)
    analyst_upside = safe_float(row.get("analyst_upside_pct"), None)
    rsi = safe_float(row.get("rsi"), 50) or 50
    atr_pct = safe_float(row.get("atr_pct"), 4) or 4

    drop_score = 0
    if twenty <= -8:
        drop_score += 30
    elif twenty <= -4:
        drop_score += 18

    if sixty <= -15:
        drop_score += 30
    elif sixty <= -8:
        drop_score += 18

    if rsi <= 42:
        drop_score += 12
    elif rsi <= 48:
        drop_score += 6

    forward_score = 0
    if upside >= 35:
        forward_score += 25
    elif upside >= 20:
        forward_score += 18
    elif upside >= 12:
        forward_score += 10

    if analyst_upside is not None:
        if analyst_upside >= 20:
            forward_score += 14
        elif analyst_upside >= 10:
            forward_score += 8

    if analyst_support is not None:
        if analyst_support >= 65:
            forward_score += 12
        elif analyst_support >= 45:
            forward_score += 6

    if news_score >= 30:
        forward_score += 8
    elif news_score <= -45:
        forward_score -= 10

    if revenue_growth is not None:
        if revenue_growth >= 0.15:
            forward_score += 10
        elif revenue_growth < 0:
            forward_score -= 8

    if earnings_growth is not None:
        if earnings_growth >= 0.10:
            forward_score += 8
        elif earnings_growth < 0:
            forward_score -= 8

    risk_penalty = 0
    if atr_pct > 10:
        risk_penalty += 12
    elif atr_pct > 7:
        risk_penalty += 6

    recovery_score = int(clamp(drop_score + forward_score - risk_penalty, 0, 100))

    if recovery_score >= 75:
        label = "🟢 Strong Recovery Candidate"
    elif recovery_score >= 60:
        label = "🟡 Recovery Watchlist"
    elif recovery_score >= 45:
        label = "🔵 Early Recovery Setup"
    else:
        label = "⚪ Not a recovery priority"

    drop_reason = []
    if twenty <= -4:
        drop_reason.append(f"20-day move is down {twenty:.1f}%")
    if sixty <= -8:
        drop_reason.append(f"60-day move is down {sixty:.1f}%")
    if rsi <= 48:
        drop_reason.append(f"RSI is depressed at {rsi:.1f}")

    rebound_reason = []
    if upside >= 12:
        rebound_reason.append(f"AI fair value still implies {upside:.1f}% upside")
    if analyst_upside is not None and analyst_upside >= 10:
        rebound_reason.append(f"analyst target implies {analyst_upside:.1f}% upside")
    if analyst_support is not None and analyst_support >= 45:
        rebound_reason.append(f"analyst support remains {analyst_support:.0f}/100")
    if revenue_growth is not None and revenue_growth >= 0.10:
        rebound_reason.append(f"revenue growth remains positive at {revenue_growth * 100:.1f}%")
    if news_score >= 0:
        rebound_reason.append("news flow is not strongly negative")

    row["recovery_score"] = recovery_score
    row["recovery_label"] = label
    row["recovery_drop_reason"] = "; ".join(drop_reason) if drop_reason else "No major price drop signal detected."
    row["recovery_rebound_reason"] = "; ".join(rebound_reason) if rebound_reason else "Forward rebound support is limited."
    row["recovery_risk"] = (
        "High volatility could make timing difficult."
        if atr_pct > 7 else
        "Main risk is that the selloff continues if news, earnings, or market sentiment worsens."
    )
    row["recovery_thesis"] = (
        f"{row.get('company_name', row.get('symbol'))} is a {label.replace('🟢 ', '').replace('🟡 ', '').replace('🔵 ', '').replace('⚪ ', '')}. "
        f"Drop reason: {row['recovery_drop_reason']} "
        f"Rebound case: {row['recovery_rebound_reason']} "
        f"Risk: {row['recovery_risk']}"
    )

    return row


def build_recovery_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    recovery_rows: List[Dict[str, Any]] = []
    for row in rows:
        updated = build_recovery_case(dict(row))
        if updated.get("recovery_score", 0) >= 45:
            recovery_rows.append(updated)

    recovery_rows.sort(
        key=lambda r: (
            r.get("recovery_score") or 0,
            r.get("expected_upside_pct") or 0,
            r.get("analyst_support_score") or 0,
        ),
        reverse=True,
    )
    return recovery_rows[:100]


def is_excluded_etf(symbol: str, meta: Dict[str, Any]) -> Tuple[bool, str]:
    sym = safe_text(symbol, "").upper()
    name = safe_text(meta.get("company_name"), "").upper()
    sector = safe_text(meta.get("sector"), "").upper()
    industry = safe_text(meta.get("industry"), "").upper()
    category = safe_text(meta.get("category"), "").upper()
    text = f"{sym} {name} {sector} {industry} {category}"

    blocked_symbols = {
        "XLF", "KBE", "KRE", "IYF", "VFH", "FNCL", "IAI", "KCE", "KBWB", "KBWR",
        "EIS", "ISRA", "IZRL",
        "BETZ", "BJK", "PEJ", "XLC", "IYZ", "VOX"
    }

    blocked_terms = [
        "FINANCIAL", "BANK", "BANKS", "INSURANCE", "BROKER", "CAPITAL MARKETS",
        "ASSET MANAGEMENT", "MORTGAGE", "CREDIT", "LENDER", "LENDING",
        "ISRAEL", "TEL AVIV",
        "GAMING", "GAMBLING", "CASINO", "BETTING",
        "ALCOHOL", "BREWERS", "TOBACCO",
        "ENTERTAINMENT", "MEDIA", "COMMUNICATION SERVICES"
    ]

    if sym in blocked_symbols:
        return True, f"Blocked ETF symbol/theme: {sym}"

    for term in blocked_terms:
        if term in text:
            return True, f"Blocked ETF theme: {term}"

    return False, ""


def score_etf_row(symbol: str, meta: Dict[str, Any], ind: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    excluded, reason = is_excluded_etf(symbol, meta)
    if excluded:
        return None

    price = ind.get("price")
    if not price:
        return None

    score = 50
    good: List[str] = []
    risks: List[str] = []

    dollar_volume = ind.get("dollar_volume") or 0
    if dollar_volume >= 50_000_000:
        score += 12
        good.append("strong ETF liquidity")
    elif dollar_volume >= MIN_DOLLAR_VOLUME:
        score += 6
        good.append("acceptable ETF liquidity")
    else:
        return None

    if ind.get("sma20") and price > ind.get("sma20"):
        score += 10
        good.append("price is above 20-day trend")
    else:
        score -= 6
        risks.append("price is below 20-day trend")

    if ind.get("sma50") and price > ind.get("sma50"):
        score += 12
        good.append("price is above 50-day trend")
    else:
        score -= 8
        risks.append("price is below 50-day trend")

    twenty = ind.get("twenty_day_pct") or 0
    sixty = ind.get("sixty_day_pct") or 0
    rsi = ind.get("rsi") or 50
    atr_pct = ind.get("atr_pct") or 4

    if 1 <= twenty <= 18:
        score += 10
        good.append("healthy 20-day ETF momentum")
    elif twenty > 25:
        score -= 5
        risks.append("short-term ETF move may be stretched")
    elif twenty < -6:
        score -= 8
        risks.append("20-day ETF trend is weak")

    if 3 <= sixty <= 30:
        score += 8
        good.append("positive 60-day ETF trend")
    elif sixty < -10:
        score -= 8
        risks.append("60-day ETF trend is weak")

    if 45 <= rsi <= 68:
        score += 8
        good.append("RSI is constructive")
    elif rsi > 76:
        score -= 8
        risks.append("RSI is overheated")
    elif rsi < 38:
        score -= 5
        risks.append("RSI is weak")

    if atr_pct <= 4:
        score += 6
        good.append("ETF volatility is controlled")
    elif atr_pct > 7:
        score -= 8
        risks.append("ETF volatility is elevated")

    score = int(clamp(score, 20, 95))
    plan = build_trade_plan(ind, score)
    target = plan.get("target") or (price * 1.08)
    upside = ((target - price) / price) * 100 if price else 0

    return {
        "symbol": symbol,
        "ticker": symbol,
        "company": meta.get("company_name", symbol),
        "company_name": meta.get("company_name", symbol),
        "sector": "ETF",
        "industry": meta.get("industry", meta.get("sector", "ETF")),
        "quote_type": "ETF",
        "price": price,
        "current_price": price,
        "dollar_volume": ind.get("dollar_volume"),
        "avg_volume_20d": ind.get("avg_volume_20d"),
        "volume_ratio": ind.get("volume_ratio"),
        "conviction": score,
        "conviction_score": score,
        "score": score,
        "ai_score": score,
        "ai_confidence": score,
        "confidence": score,
        "rsi": ind.get("rsi"),
        "atr_pct": ind.get("atr_pct"),
        "sma20": ind.get("sma20"),
        "sma50": ind.get("sma50"),
        "twenty_day_pct": ind.get("twenty_day_pct"),
        "sixty_day_pct": ind.get("sixty_day_pct"),
        "entry_range": plan.get("entry_range"),
        "entry_low": plan.get("entry_low"),
        "entry_high": plan.get("entry_high"),
        "stop_loss": plan.get("stop_loss"),
        "target": round(target, 2),
        "target_2": plan.get("target_2"),
        "risk_reward": plan.get("risk_reward"),
        "expected_upside_pct": round(upside, 1),
        "upside": round(upside, 1),
        "ai_base_target": round(target, 2),
        "ai_bull_target": plan.get("target_2"),
        "ai_bear_target": plan.get("stop_loss"),
        "etf_preference_screen": "Passed non-financial / non-Israel / non-excluded-theme screen",
        "what_looks_good": "; ".join(good) if good else "ETF has acceptable technical traits.",
        "what_could_go_wrong": "; ".join(risks) if risks else "Main risk is a broad market or sector pullback.",
        "investment_thesis": (
            f"{meta.get('company_name', symbol)} ({symbol}) is an ETF candidate that passed your preference screen. "
            f"Score {score}/100. Positive factors: {'; '.join(good) if good else 'acceptable ETF setup'}. "
            f"Risks: {'; '.join(risks) if risks else 'market pullback risk'}."
        ),
        "guidance": (
            f"{symbol} ETF score is {score}/100. Preferred entry is {plan.get('entry_range')}. "
            f"Use stop around ${plan.get('stop_loss')} and first target near ${round(target, 2)}."
        ),
        "action_note": "ETF idea only. Review holdings/exposure before buying to ensure it aligns with your preferences.",
        "summary": f"{symbol}: ETF candidate, score {score}/100, estimated trade upside {round(upside, 1)}%.",
        "setup_tags": good,
        "risk_tags": risks,
        # V41.6 price history fields are merged after row creation.
        "scan_time": now_iso(),
    }


def get_fmp_financial_intelligence(symbol: str) -> Dict[str, Any]:
    """
    V41.5 Deep Finance Agent.
    Pulls financial statement, ratio, earnings surprise, and peer data from FMP when available.
    All failures return {} so cron never breaks.
    """
    if not FMP_API_KEY:
        return {}

    result: Dict[str, Any] = {}

    def get(endpoint: str, params: Optional[Dict[str, Any]] = None):
        base = f"https://financialmodelingprep.com/api/v3/{endpoint}"
        merged = {"apikey": FMP_API_KEY}
        if params:
            merged.update(params)
        return http_get_json(base, params=merged, timeout=12)

    # Quarterly financials
    income = get(f"income-statement/{symbol}", {"period": "quarter", "limit": 5})
    balance = get(f"balance-sheet-statement/{symbol}", {"period": "quarter", "limit": 5})
    cashflow = get(f"cash-flow-statement/{symbol}", {"period": "quarter", "limit": 5})
    ratios = get(f"ratios/{symbol}", {"period": "quarter", "limit": 4})
    key_metrics = get(f"key-metrics/{symbol}", {"period": "quarter", "limit": 4})
    earnings = get(f"earnings-surprises/{symbol}", {"limit": 4})
    peers = get(f"stock_peers", {"symbol": symbol})

    if isinstance(income, list) and income:
        latest_income = income[0] or {}
        prior_income = income[1] if len(income) > 1 else {}
        four_q = income[:4]

        revenues = [safe_float(x.get("revenue")) for x in four_q if isinstance(x, dict)]
        eps_values = [safe_float(x.get("eps")) for x in four_q if isinstance(x, dict)]
        net_income_values = [safe_float(x.get("netIncome")) for x in four_q if isinstance(x, dict)]

        latest_revenue = safe_float(latest_income.get("revenue"))
        prior_revenue = safe_float(prior_income.get("revenue")) if isinstance(prior_income, dict) else None
        revenue_qoq = pct_change(latest_revenue, prior_revenue)

        result.update({
            "latest_revenue": latest_revenue,
            "latest_eps": safe_float(latest_income.get("eps")),
            "latest_net_income": safe_float(latest_income.get("netIncome")),
            "latest_gross_profit": safe_float(latest_income.get("grossProfit")),
            "latest_operating_income": safe_float(latest_income.get("operatingIncome")),
            "revenue_qoq_pct": round(revenue_qoq, 1) if revenue_qoq is not None else None,
            "revenue_quarters": revenues,
            "eps_quarters": eps_values,
            "net_income_quarters": net_income_values,
            "source_fmp_financials": True,
        })

    if isinstance(balance, list) and balance:
        latest_balance = balance[0] or {}
        total_debt = safe_float(latest_balance.get("totalDebt"))
        total_assets = safe_float(latest_balance.get("totalAssets"))
        total_equity = safe_float(latest_balance.get("totalStockholdersEquity"))
        cash = safe_float(latest_balance.get("cashAndCashEquivalents"))

        debt_to_equity = (total_debt / total_equity) if total_debt is not None and total_equity and total_equity > 0 else None
        debt_to_assets = (total_debt / total_assets) if total_debt is not None and total_assets and total_assets > 0 else None
        net_cash = (cash - total_debt) if cash is not None and total_debt is not None else None

        result.update({
            "total_debt": total_debt,
            "total_assets": total_assets,
            "total_equity": total_equity,
            "cash_and_equivalents": cash,
            "debt_to_equity": round(debt_to_equity, 2) if debt_to_equity is not None else None,
            "debt_to_assets": round(debt_to_assets, 2) if debt_to_assets is not None else None,
            "net_cash": net_cash,
        })

    if isinstance(cashflow, list) and cashflow:
        latest_cf = cashflow[0] or {}
        result.update({
            "operating_cash_flow": safe_float(latest_cf.get("operatingCashFlow")),
            "free_cash_flow": safe_float(latest_cf.get("freeCashFlow")),
            "capex": safe_float(latest_cf.get("capitalExpenditure")),
        })

    if isinstance(ratios, list) and ratios:
        latest_ratios = ratios[0] or {}
        result.update({
            "gross_profit_margin": safe_float(latest_ratios.get("grossProfitMargin")),
            "operating_profit_margin": safe_float(latest_ratios.get("operatingProfitMargin")),
            "net_profit_margin": safe_float(latest_ratios.get("netProfitMargin")),
            "current_ratio": safe_float(latest_ratios.get("currentRatio")),
            "return_on_equity": safe_float(latest_ratios.get("returnOnEquity")),
            "return_on_assets": safe_float(latest_ratios.get("returnOnAssets")),
        })

    if isinstance(key_metrics, list) and key_metrics:
        latest_metrics = key_metrics[0] or {}
        result.update({
            "roic": safe_float(latest_metrics.get("roic")),
            "enterprise_value": safe_float(latest_metrics.get("enterpriseValue")),
            "ev_to_sales": safe_float(latest_metrics.get("evToSales")),
            "ev_to_ebitda": safe_float(latest_metrics.get("enterpriseValueOverEBITDA")),
            "revenue_per_share": safe_float(latest_metrics.get("revenuePerShare")),
            "net_income_per_share": safe_float(latest_metrics.get("netIncomePerShare")),
        })

    if isinstance(earnings, list) and earnings:
        surprises = []
        beats = 0
        misses = 0
        for item in earnings[:4]:
            if not isinstance(item, dict):
                continue
            actual = safe_float(item.get("actualEarningResult"))
            estimate = safe_float(item.get("estimatedEarning"))
            if actual is not None and estimate is not None:
                diff = actual - estimate
                surprises.append(round(diff, 3))
                if diff >= 0:
                    beats += 1
                else:
                    misses += 1

        result.update({
            "eps_surprises_last4": surprises,
            "eps_beats_last4": beats,
            "eps_misses_last4": misses,
            "source_fmp_earnings_surprises": True,
        })

    if isinstance(peers, list) and peers:
        # FMP stock_peers commonly returns list of symbols or dict with peersList.
        peer_symbols = []
        if peers and isinstance(peers[0], dict):
            peer_symbols = peers[0].get("peersList") or []
        elif all(isinstance(x, str) for x in peers):
            peer_symbols = peers
        result["peer_symbols"] = [str(x).upper() for x in peer_symbols[:8] if x]

    return {k: v for k, v in result.items() if v not in (None, "", "Unknown", [])}


def build_finance_agent(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    V41.5 Finance Agent score and bullet summary.
    Cross-checks growth, EPS execution, debt, margins, cash flow, and peer context.
    """
    score = 50
    positives: List[str] = []
    cautions: List[str] = []

    revenue_growth = safe_float(meta.get("revenue_growth"), None)
    earnings_growth = safe_float(meta.get("earnings_growth"), None)
    revenue_qoq = safe_float(meta.get("revenue_qoq_pct"), None)
    latest_eps = safe_float(meta.get("latest_eps"), None)
    eps_beats = safe_int(meta.get("eps_beats_last4"), 0) or 0
    eps_misses = safe_int(meta.get("eps_misses_last4"), 0) or 0
    debt_to_equity = safe_float(meta.get("debt_to_equity"), None)
    debt_to_assets = safe_float(meta.get("debt_to_assets"), None)
    current_ratio = safe_float(meta.get("current_ratio"), None)
    gross_margin = safe_float(meta.get("gross_profit_margin"), None)
    operating_margin = safe_float(meta.get("operating_profit_margin"), None)
    net_margin = safe_float(meta.get("net_profit_margin"), None)
    free_cash_flow = safe_float(meta.get("free_cash_flow"), None)
    operating_cash_flow = safe_float(meta.get("operating_cash_flow"), None)
    roic = safe_float(meta.get("roic"), None)
    forward_pe = safe_float(meta.get("forward_pe"), None)
    peg_ratio = safe_float(meta.get("peg_ratio"), None)
    ev_to_sales = safe_float(meta.get("ev_to_sales"), None)
    peers = meta.get("peer_symbols") or []

    if revenue_growth is not None:
        if revenue_growth >= 0.20:
            score += 10
            positives.append(f"Revenue growth is strong at {revenue_growth * 100:.1f}%")
        elif revenue_growth >= 0.08:
            score += 6
            positives.append(f"Revenue growth is healthy at {revenue_growth * 100:.1f}%")
        elif revenue_growth < 0:
            score -= 8
            cautions.append("Revenue growth is negative")

    if revenue_qoq is not None:
        if revenue_qoq > 5:
            score += 5
            positives.append(f"Latest quarter revenue improved {revenue_qoq:.1f}% sequentially")
        elif revenue_qoq < -5:
            score -= 5
            cautions.append(f"Latest quarter revenue declined {abs(revenue_qoq):.1f}% sequentially")

    if earnings_growth is not None:
        if earnings_growth >= 0.20:
            score += 9
            positives.append(f"Earnings growth is strong at {earnings_growth * 100:.1f}%")
        elif earnings_growth >= 0.05:
            score += 5
            positives.append(f"Earnings growth is positive at {earnings_growth * 100:.1f}%")
        elif earnings_growth < 0:
            score -= 8
            cautions.append("Earnings growth is negative")

    if latest_eps is not None:
        if latest_eps > 0:
            score += 4
            positives.append(f"Latest EPS is positive at {latest_eps:.2f}")
        else:
            score -= 4
            cautions.append(f"Latest EPS is negative at {latest_eps:.2f}")

    if eps_beats or eps_misses:
        if eps_beats >= 3:
            score += 6
            positives.append(f"EPS beat estimates in {eps_beats} of the last 4 reported quarters")
        elif eps_misses >= 2:
            score -= 6
            cautions.append(f"EPS missed estimates in {eps_misses} of the last 4 reported quarters")

    if debt_to_equity is not None:
        if debt_to_equity < 0.5:
            score += 6
            positives.append(f"Debt-to-equity is low at {debt_to_equity:.2f}")
        elif debt_to_equity <= 1.5:
            score += 2
            positives.append(f"Debt-to-equity is manageable at {debt_to_equity:.2f}")
        else:
            score -= 7
            cautions.append(f"Debt-to-equity is elevated at {debt_to_equity:.2f}")

    if debt_to_assets is not None:
        if debt_to_assets < 0.3:
            score += 3
            positives.append(f"Debt-to-assets is conservative at {debt_to_assets:.2f}")
        elif debt_to_assets > 0.6:
            score -= 4
            cautions.append(f"Debt-to-assets is high at {debt_to_assets:.2f}")

    if current_ratio is not None:
        if current_ratio >= 1.5:
            score += 3
            positives.append(f"Current ratio is healthy at {current_ratio:.2f}")
        elif current_ratio < 1:
            score -= 3
            cautions.append(f"Current ratio is below 1.0 at {current_ratio:.2f}")

    if gross_margin is not None:
        if gross_margin >= 0.50:
            score += 4
            positives.append(f"Gross margin is strong at {gross_margin * 100:.1f}%")
        elif gross_margin < 0.20:
            score -= 3
            cautions.append(f"Gross margin is thin at {gross_margin * 100:.1f}%")

    if operating_margin is not None:
        if operating_margin >= 0.20:
            score += 5
            positives.append(f"Operating margin is strong at {operating_margin * 100:.1f}%")
        elif operating_margin < 0:
            score -= 5
            cautions.append("Operating margin is negative")

    if net_margin is not None:
        if net_margin >= 0.15:
            score += 4
            positives.append(f"Net margin is healthy at {net_margin * 100:.1f}%")
        elif net_margin < 0:
            score -= 5
            cautions.append("Net margin is negative")

    if free_cash_flow is not None:
        if free_cash_flow > 0:
            score += 6
            positives.append("Free cash flow is positive")
        else:
            score -= 5
            cautions.append("Free cash flow is negative")

    if operating_cash_flow is not None:
        if operating_cash_flow > 0:
            score += 3
            positives.append("Operating cash flow is positive")
        else:
            score -= 3
            cautions.append("Operating cash flow is negative")

    if roic is not None:
        if roic >= 0.12:
            score += 5
            positives.append(f"ROIC is attractive at {roic * 100:.1f}%")
        elif roic < 0:
            score -= 4
            cautions.append("ROIC is negative")

    if peg_ratio is not None:
        if 0 < peg_ratio < 1:
            score += 5
            positives.append(f"PEG ratio is attractive at {peg_ratio:.2f}")
        elif peg_ratio > 3:
            score -= 4
            cautions.append(f"PEG ratio is expensive at {peg_ratio:.2f}")

    if forward_pe is not None:
        if 0 < forward_pe <= 25:
            score += 3
            positives.append(f"Forward PE is reasonable at {forward_pe:.1f}")
        elif forward_pe > 50:
            score -= 4
            cautions.append(f"Forward PE is elevated at {forward_pe:.1f}")

    if ev_to_sales is not None:
        if ev_to_sales <= 5:
            score += 2
            positives.append(f"EV/Sales is reasonable at {ev_to_sales:.1f}")
        elif ev_to_sales > 12:
            score -= 3
            cautions.append(f"EV/Sales is expensive at {ev_to_sales:.1f}")

    if peers:
        positives.append(f"Peer set identified for comparison: {', '.join(peers[:5])}")

    score = int(clamp(score, 15, 98))

    if score >= 85:
        status = "Positive"
        impact = "Positive"
    elif score >= 65:
        status = "Mixed / constructive"
        impact = "Moderate Positive"
    elif score >= 45:
        status = "Mixed"
        impact = "Neutral"
    else:
        status = "Weak"
        impact = "Negative"

    if not positives:
        positives.append("Financial data is limited; agent relied on available fundamentals only")
    if not cautions:
        cautions.append("No major financial red flag detected from available data")

    return {
        "score": score,
        "status": status,
        "impact": impact,
        "data_used": "FMP/Yahoo financial statements, ratios, earnings surprises, balance sheet, cash flow, and peer set",
        "summary": "Evaluates financial execution, EPS quality, revenue consistency, balance sheet risk, cash flow, margins, valuation, and peer context.",
        "findings": positives[:10],
        "risks": cautions[:8],
        "bottom_line": (
            "Financial execution looks strong across multiple checks."
            if score >= 85 else
            "Financial profile is constructive but has some items to monitor."
            if score >= 65 else
            "Financial profile is mixed and should be reviewed carefully before acting."
        ),
    }


def enhance_ai_committee(row: Dict[str, Any], meta: Dict[str, Any], ind: Dict[str, Any]) -> Dict[str, Any]:
    """
    V41.5: enrich or create AI committee data with deeper cross-checking bullets.
    """
    finance_agent = build_finance_agent(meta)

    technical_findings = []
    technical_risks = []
    price = ind.get("price")
    if price and ind.get("sma20"):
        technical_findings.append("Price is above the 20-day trend" if price > ind.get("sma20") else "Price is below the 20-day trend")
    if price and ind.get("sma50"):
        technical_findings.append("Price is above the 50-day trend" if price > ind.get("sma50") else "Price is below the 50-day trend")
    if ind.get("rsi") is not None:
        technical_findings.append(f"RSI is {ind.get('rsi')}")
    if ind.get("volume_ratio") is not None:
        technical_findings.append(f"Volume ratio is {ind.get('volume_ratio')}x")
    if ind.get("atr_pct") is not None:
        if ind.get("atr_pct") > 7:
            technical_risks.append(f"ATR volatility is elevated at {ind.get('atr_pct')}%")
        else:
            technical_findings.append(f"ATR volatility is manageable at {ind.get('atr_pct')}%")

    analyst_findings = []
    analyst_risks = []
    if meta.get("analyst_support_score") is not None:
        analyst_findings.append(f"Finnhub analyst support score is {meta.get('analyst_support_score')}/100")
    if row.get("analyst_upside_pct") is not None:
        analyst_findings.append(f"Analyst target implies {row.get('analyst_upside_pct')}% upside")
    if row.get("analyst_count"):
        analyst_findings.append(f"Analyst coverage count is {row.get('analyst_count')}")
    if not analyst_findings:
        analyst_risks.append("Analyst coverage data is limited")

    news_findings = []
    news_risks = []
    if meta.get("news_sentiment_label"):
        news_findings.append(f"Recent news sentiment is {meta.get('news_sentiment_label')}")
    if meta.get("top_news_headline"):
        news_findings.append(f"Top headline: {meta.get('top_news_headline')}")
    if meta.get("negative_news_terms"):
        news_risks.append(f"Negative news terms detected: {', '.join(meta.get('negative_news_terms')[:3])}")
    if not news_findings:
        news_risks.append("Recent news data is limited")

    valuation_findings = []
    valuation_risks = []
    if row.get("ai_base_target"):
        valuation_findings.append(f"AI fair value target is ${row.get('ai_base_target')}")
    if row.get("expected_upside_pct") is not None:
        valuation_findings.append(f"AI expected upside is {row.get('expected_upside_pct')}%")
        if row.get("expected_upside_pct") > 60:
            valuation_risks.append("Very high AI upside requires stronger confirmation")
    if row.get("analyst_target_mean"):
        valuation_findings.append(f"Analyst target is ${row.get('analyst_target_mean')}")

    committee = row.get("ai_committee") if isinstance(row.get("ai_committee"), dict) else {}
    committee.update({
        "Finance Agent": finance_agent,
        "Technical Agent": {
            "score": row.get("conviction", 0),
            "status": "Positive" if row.get("conviction", 0) >= 85 else "Mixed",
            "impact": "Positive" if row.get("conviction", 0) >= 85 else "Neutral",
            "data_used": "Yahoo price history, moving averages, RSI, volume, ATR, momentum",
            "summary": "Cross-checks trend quality, momentum, liquidity, volume confirmation, volatility, and entry risk.",
            "findings": technical_findings[:8],
            "risks": technical_risks[:6] or ["No major technical risk detected from available data"],
            "bottom_line": "Technical setup is constructive." if row.get("conviction", 0) >= 85 else "Technical setup is mixed and needs confirmation.",
        },
        "Analyst Agent": {
            "score": int(safe_float(meta.get("analyst_support_score"), 50) or 50),
            "status": "Positive" if (safe_float(meta.get("analyst_support_score"), 50) or 50) >= 60 else "Mixed",
            "impact": "Positive" if (safe_float(meta.get("analyst_support_score"), 50) or 50) >= 60 else "Neutral",
            "data_used": "Finnhub/Yahoo analyst recommendations, target prices, analyst count",
            "summary": "Checks whether Wall Street target data and recommendation trends support the thesis.",
            "findings": analyst_findings[:8],
            "risks": analyst_risks[:6] or ["No major analyst red flag detected from available data"],
            "bottom_line": "Analyst view supports the thesis." if (safe_float(meta.get("analyst_support_score"), 50) or 50) >= 60 else "Analyst view is mixed or limited.",
        },
        "News Agent": {
            "score": int(clamp(50 + (safe_float(meta.get("news_sentiment_score"), 0) or 0), 0, 100)),
            "status": meta.get("news_sentiment_label") or "Unknown",
            "impact": "Positive" if meta.get("news_sentiment_label") == "Positive" else "Negative" if meta.get("news_sentiment_label") == "Negative" else "Neutral",
            "data_used": "NewsAPI recent headlines, positive/negative keyword sentiment, catalyst terms",
            "summary": "Checks if recent headlines confirm or weaken the investment thesis.",
            "findings": news_findings[:8],
            "risks": news_risks[:6],
            "bottom_line": "News flow supports the thesis." if meta.get("news_sentiment_label") == "Positive" else "News flow is mixed or limited.",
        },
        "Valuation Agent": {
            "score": int(clamp(55 + (safe_float(row.get("expected_upside_pct"), 0) or 0) * 0.4, 20, 95)),
            "status": "Positive" if (safe_float(row.get("expected_upside_pct"), 0) or 0) >= 20 else "Neutral",
            "impact": "Positive" if (safe_float(row.get("expected_upside_pct"), 0) or 0) >= 20 else "Neutral",
            "data_used": "AI fair value, analyst target, growth/valuation adjustment, bull/bear target model",
            "summary": "Compares current price, analyst target, AI fair value, and expected upside.",
            "findings": valuation_findings[:8],
            "risks": valuation_risks[:6] or ["Valuation risk depends on whether growth assumptions hold"],
            "bottom_line": "Valuation supports upside." if (safe_float(row.get("expected_upside_pct"), 0) or 0) >= 20 else "Valuation upside is limited or still developing.",
        },
    })

    positive_agents = 0
    total_agents = 0
    for agent in committee.values():
        if isinstance(agent, dict):
            total_agents += 1
            if str(agent.get("impact", "")).lower().startswith("positive") or str(agent.get("status", "")).lower().startswith("positive"):
                positive_agents += 1

    if total_agents:
        agreement = positive_agents / total_agents
        if agreement >= 0.75:
            thesis_strength = "Exceptional Thesis"
        elif agreement >= 0.55:
            thesis_strength = "Strong Thesis"
        elif agreement >= 0.35:
            thesis_strength = "Moderate Thesis"
        else:
            thesis_strength = "Weak Thesis"
    else:
        thesis_strength = "Unknown"

    row["ai_committee"] = committee
    row["thesis_strength"] = thesis_strength
    row["finance_agent_score"] = finance_agent.get("score")
    row["finance_agent_status"] = finance_agent.get("status")
    row["finance_agent_bottom_line"] = finance_agent.get("bottom_line")
    row["finance_agent_findings"] = finance_agent.get("findings")
    row["finance_agent_risks"] = finance_agent.get("risks")

    return row


def build_price_history_intelligence(df: pd.DataFrame, ind: Dict[str, Any]) -> Dict[str, Any]:
    """
    V42.5.3 Official Economic Calendar Fallback.
    Adds 52-week low/high, current position in range, 6M/1Y/3Y/5Y returns when available.
    Uses available downloaded history, so it does not add extra API calls.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return {}

    close = df["Close"].dropna().astype(float)
    high = df["High"].dropna().astype(float) if "High" in df.columns else close
    low = df["Low"].dropna().astype(float) if "Low" in df.columns else close

    if close.empty:
        return {}

    price = safe_float(close.iloc[-1])
    if not price:
        return {}

    # Existing scan currently uses ~6 months of data, so 52-week and 5Y will be partial until scanner period is expanded.
    # The dashboard labels this clearly if full history is unavailable.
    history_days = len(close)

    high_52w = safe_float(high.tail(min(252, len(high))).max())
    low_52w = safe_float(low.tail(min(252, len(low))).min())
    all_period_high = safe_float(high.max())
    all_period_low = safe_float(low.min())

    range_position = None
    if high_52w and low_52w and high_52w > low_52w:
        range_position = ((price - low_52w) / (high_52w - low_52w)) * 100

    distance_from_52w_high = pct_change(price, high_52w)
    distance_from_52w_low = pct_change(price, low_52w)
    drawdown_from_period_high = pct_change(price, all_period_high)

    def ret_from_days(days: int):
        if len(close) > days:
            return pct_change(price, safe_float(close.iloc[-days-1]))
        return None

    ret_1m = ret_from_days(21)
    ret_3m = ret_from_days(63)
    ret_6m = ret_from_days(126)
    ret_1y = ret_from_days(252)
    ret_3y = ret_from_days(252 * 3)
    ret_5y = ret_from_days(252 * 5)

    if range_position is None:
        range_label = "N/A"
    elif range_position < 25:
        range_label = "Near lower range"
    elif range_position < 50:
        range_label = "Lower-middle range"
    elif range_position < 75:
        range_label = "Upper-middle range"
    else:
        range_label = "Near 52-week highs"

    if drawdown_from_period_high is None:
        drawdown_label = "N/A"
    elif drawdown_from_period_high > -10:
        drawdown_label = "Shallow drawdown"
    elif drawdown_from_period_high > -25:
        drawdown_label = "Moderate drawdown"
    elif drawdown_from_period_high > -45:
        drawdown_label = "Deep drawdown"
    else:
        drawdown_label = "Severe drawdown"

    return {
        "history_days_available": history_days,
        "price_history_note": "Scanner uses 1-year history for accurate 52-week range. Dashboard fetches 5-year chart data on demand." if history_days < 1000 else "Full long-term history available.",
        "high_52w": round(high_52w, 2) if high_52w else None,
        "low_52w": round(low_52w, 2) if low_52w else None,
        "all_period_high": round(all_period_high, 2) if all_period_high else None,
        "all_period_low": round(all_period_low, 2) if all_period_low else None,
        "range_position_pct": round(range_position, 1) if range_position is not None else None,
        "range_position_label": range_label,
        "distance_from_52w_high_pct": round(distance_from_52w_high, 1) if distance_from_52w_high is not None else None,
        "distance_from_52w_low_pct": round(distance_from_52w_low, 1) if distance_from_52w_low is not None else None,
        "drawdown_from_period_high_pct": round(drawdown_from_period_high, 1) if drawdown_from_period_high is not None else None,
        "drawdown_label": drawdown_label,
        "return_1m_pct": round(ret_1m, 1) if ret_1m is not None else None,
        "return_3m_pct": round(ret_3m, 1) if ret_3m is not None else None,
        "return_6m_pct": round(ret_6m, 1) if ret_6m is not None else None,
        "return_1y_pct": round(ret_1y, 1) if ret_1y is not None else None,
        "return_3y_pct": round(ret_3y, 1) if ret_3y is not None else None,
        "return_5y_pct": round(ret_5y, 1) if ret_5y is not None else None,
    }


def apply_research_field_fallbacks(row: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    V41.7 QA fix:
    Ensure dashboard research columns are useful even when an API endpoint returns no specific field.
    This prevents Analyst Support and News Sentiment from showing N/A when other data exists.
    """
    # Analyst Support fallback
    analyst_support = safe_float(row.get("analyst_support_score"), None)
    analyst_count = safe_float(row.get("analyst_count"), meta.get("analyst_count")) or 0
    analyst_upside = safe_float(row.get("analyst_upside_pct"), None)
    expected_upside = safe_float(row.get("expected_upside_pct"), None)
    recommendation_key = safe_text(row.get("recommendation_key") or meta.get("recommendation_key"), "").lower()

    if analyst_support is None:
        derived = 50.0

        if analyst_upside is not None:
            derived += clamp(analyst_upside, -30, 60) * 0.45
        elif expected_upside is not None:
            derived += clamp(expected_upside, -30, 60) * 0.25

        if analyst_count >= 30:
            derived += 8
        elif analyst_count >= 10:
            derived += 5
        elif analyst_count >= 3:
            derived += 2
        elif analyst_count == 0:
            derived -= 10

        if recommendation_key in {"buy", "strong_buy"}:
            derived += 10
        elif recommendation_key in {"hold", "neutral"}:
            derived += 0
        elif recommendation_key in {"sell", "underperform"}:
            derived -= 18

        analyst_support = round(clamp(derived, 0, 100), 1)
        row["analyst_support_score"] = analyst_support
        row["analyst_support_source"] = "Derived from analyst target/count/recommendation because Finnhub recommendation score was unavailable"
    else:
        row["analyst_support_source"] = "Finnhub recommendation trend"

    if analyst_support >= 70:
        row["analyst_support_label"] = f"Bullish ({analyst_support:.0f}/100)"
    elif analyst_support >= 45:
        row["analyst_support_label"] = f"Constructive ({analyst_support:.0f}/100)"
    elif analyst_support >= 25:
        row["analyst_support_label"] = f"Mixed ({analyst_support:.0f}/100)"
    else:
        row["analyst_support_label"] = f"Weak ({analyst_support:.0f}/100)"

    # News fallback
    news_label = safe_text(row.get("news_sentiment_label") or meta.get("news_sentiment_label"), "")
    news_score = safe_float(row.get("news_sentiment_score"), meta.get("news_sentiment_score"))

    if not news_label or news_label.upper() == "N/A":
        news_label = "Neutral"
        news_score = 0 if news_score is None else news_score
        row["news_sentiment_source"] = "No recent NewsAPI headline returned; defaulted to neutral"
        if not row.get("top_news_headline"):
            row["top_news_headline"] = "No recent high-confidence company headline returned by NewsAPI"
    else:
        row["news_sentiment_source"] = "NewsAPI headline sentiment"

    row["news_sentiment_label"] = news_label
    row["news_sentiment_score"] = 0 if news_score is None else news_score

    # Differentiated thesis strength fallback
    conviction = safe_float(row.get("conviction"), 0) or 0
    upside = safe_float(row.get("expected_upside_pct"), 0) or 0
    finance_score = safe_float(row.get("finance_agent_score"), None)

    evidence_score = 0
    if conviction >= 90:
        evidence_score += 30
    elif conviction >= 80:
        evidence_score += 22
    elif conviction >= 70:
        evidence_score += 15

    if upside >= 40:
        evidence_score += 25
    elif upside >= 20:
        evidence_score += 18
    elif upside >= 10:
        evidence_score += 10

    if analyst_support >= 70:
        evidence_score += 20
    elif analyst_support >= 45:
        evidence_score += 12

    if news_label == "Positive":
        evidence_score += 10
    elif news_label == "Negative":
        evidence_score -= 10
    elif news_label == "Neutral":
        evidence_score += 3

    if finance_score is not None:
        if finance_score >= 85:
            evidence_score += 15
        elif finance_score >= 65:
            evidence_score += 8
        elif finance_score < 45:
            evidence_score -= 10

    if evidence_score >= 80:
        row["thesis_strength"] = "Exceptional Thesis"
        row["evidence_confidence"] = "High"
    elif evidence_score >= 60:
        row["thesis_strength"] = "Strong Thesis"
        row["evidence_confidence"] = "Medium-High"
    elif evidence_score >= 40:
        row["thesis_strength"] = "Moderate Thesis"
        row["evidence_confidence"] = "Medium"
    else:
        row["thesis_strength"] = "Developing Thesis"
        row["evidence_confidence"] = "Low-Medium"

    return row

# =========================
# V42 AI INVESTMENT COMMITTEE
# =========================
ISRAEL_LINKED_EXCLUDED_TICKERS = {"ALLT","MBLY","WIX","FVRR","CYBR","CHKP","NICE","CAMT","TSEM","SPNS","GILT","MNDY"}
FINANCIAL_EXCLUDED_TERMS = {"bank","banks","financial","capital markets","credit services","insurance","asset management","brokerage","mortgage","lender","lending","reit"}

def v42_float(x, default=None):
    try:
        if x is None: return default
        return float(x)
    except Exception:
        return default

def v42_pct(x):
    x=v42_float(x,None)
    if x is None: return None
    return x*100 if abs(x)<=2 else x

def v42_is_excluded_company(symbol: str, meta: Dict[str, Any]) -> bool:
    s=str(symbol).upper()
    if s in ISRAEL_LINKED_EXCLUDED_TICKERS: return True
    text=' '.join(str(meta.get(k,'')) for k in ['sector','industry','companyName','company_name','longName','country']).lower()
    if 'israel' in text or 'israeli' in text: return True
    if any(t in text for t in FINANCIAL_EXCLUDED_TERMS): return True
    return False

def v42_agent(score, status, impact, data_used, summary, findings=None, risks=None, bottom_line=''):
    score=int(clamp(v42_float(score,50) or 50,0,100))
    if not status: status='Positive' if score>=70 else 'Mixed' if score>=45 else 'Weak'
    if not impact: impact='Positive' if score>=70 else 'Neutral' if score>=45 else 'Negative'
    return {'score':score,'status':status,'impact':impact,'data_used':data_used,'summary':summary,'findings':[str(x) for x in (findings or []) if x][:10],'risks':[str(x) for x in (risks or []) if x][:8],'bottom_line':bottom_line or ('Supportive signal.' if score>=70 else 'Mixed/limited signal.')}


def v42_company_aliases(symbol: str, company_name: str = "") -> List[str]:
    symbol = str(symbol or "").upper().strip()
    company_name = str(company_name or "").strip()
    aliases = [symbol]
    if company_name:
        aliases.append(company_name)
        # Strip common suffixes for better matching.
        short = re.sub(r"\b(Inc\.?|Corporation|Corp\.?|Ltd\.?|Limited|PLC|Class A|Common Stock)\b", "", company_name, flags=re.I).strip()
        short = re.sub(r"\s+", " ", short).strip(" ,.-")
        if short and short.lower() != company_name.lower():
            aliases.append(short)
    # Known ticker/company alias overrides.
    overrides = {
        "NVDA": ["NVIDIA", "Nvidia"],
        "TEAM": ["Atlassian", "Atlassian Corporation"],
        "GOOGL": ["Alphabet", "Google"],
        "GOOG": ["Alphabet", "Google"],
        "META": ["Meta", "Facebook"],
        "MSFT": ["Microsoft"],
        "AAPL": ["Apple"],
        "AMZN": ["Amazon"],
        "TSLA": ["Tesla"],
        "PLTR": ["Palantir"],
    }
    aliases.extend(overrides.get(symbol, []))
    # De-dupe
    out = []
    seen = set()
    for a in aliases:
        key = a.lower()
        if a and key not in seen:
            seen.add(key)
            out.append(a)
    return out


def v42_news_relevance(headline: str, symbol: str, company_name: str = "") -> str:
    """
    Classify headline relevance:
    direct = company is the main subject or action owner.
    indirect = company is mentioned as partner/customer/supplier/platform.
    low = not enough company-specific signal.
    """
    h = str(headline or "").strip()
    low = h.lower()
    aliases = v42_company_aliases(symbol, company_name)
    alias_hits = [a for a in aliases if a and a.lower() in low]
    if not alias_hits:
        return "low"

    indirect_patterns = [
        "with ", "powered by", "using ", "built on", "compatible with", "partnering with",
        "partnership with", "collaborates with", "supplier", "customer", "launches", "brings",
    ]
    # If the headline begins with company/alias, it is more likely direct.
    for a in alias_hits:
        if low.startswith(a.lower()):
            return "direct"

    direct_verbs = [
        "nvidia announces", "nvidia reports", "nvidia launches", "nvidia unveils", "nvidia expands",
        "nvidia beats", "nvidia raises", "nvidia partners", "nvidia invests", "nvidia acquires",
        "atlassian announces", "atlassian reports", "atlassian launches", "atlassian expands",
    ]
    if any(p in low for p in direct_verbs):
        return "direct"

    # If company appears after "with/using/powered by", treat as indirect.
    if any(p + alias_hits[0].lower() in low for p in ["with ", "using ", "powered by "]):
        return "indirect"

    # Otherwise, it is relevant but may not be direct.
    return "indirect"


def v42_news_stack(symbol: str, company_name: str = "") -> Dict[str, Any]:
    symbol=str(symbol).upper(); headlines=[]; sources=[]; today=dt.date.today(); start=today-dt.timedelta(days=30)
    if NEWSAPI_KEY:
        try:
            r=requests.get('https://newsapi.org/v2/everything',params={'q':f'"{symbol}" OR "{symbol} stock"','language':'en','sortBy':'publishedAt','pageSize':8,'apiKey':NEWSAPI_KEY},timeout=10)
            if r.status_code==200:
                for a in (r.json().get('articles') or [])[:8]:
                    if a.get('title'): headlines.append(a['title'])
                if headlines: sources.append('NewsAPI')
        except Exception: pass
    if FINNHUB_API_KEY:
        try:
            r=requests.get('https://finnhub.io/api/v1/company-news',params={'symbol':symbol,'from':start.isoformat(),'to':today.isoformat(),'token':FINNHUB_API_KEY},timeout=10)
            if r.status_code==200:
                before=len(headlines)
                for a in (r.json() or [])[:8]:
                    if a.get('headline'): headlines.append(a['headline'])
                if len(headlines)>before: sources.append('Finnhub company news')
        except Exception: pass
    if FMP_API_KEY:
        try:
            r=requests.get('https://financialmodelingprep.com/api/v3/stock_news',params={'tickers':symbol,'limit':8,'apikey':FMP_API_KEY},timeout=10)
            if r.status_code==200:
                before=len(headlines)
                for a in (r.json() or [])[:8]:
                    if a.get('title'): headlines.append(a['title'])
                if len(headlines)>before: sources.append('FMP stock news')
        except Exception: pass
    seen=set(); clean=[]
    for h in headlines:
        k=h.strip().lower()
        if k and k not in seen: seen.add(k); clean.append(h.strip())
    pos_terms=['beat','raised','raise','upgrade','growth','record','partnership','expands','ai','launch','strong','accelerat','profit','guidance','contract']
    neg_terms=['miss','downgrade','cut','lawsuit','probe','investigation','layoff','decline','weak','warning','risk','slump','loss']
    pos=[h for h in clean if any(t in h.lower() for t in pos_terms)]
    neg=[h for h in clean if any(t in h.lower() for t in neg_terms)]
    if clean:
        score=int(clamp(55+min(len(pos),5)*7-min(len(neg),5)*8,15,95)); status='Positive' if score>=70 else 'Mixed' if score>=45 else 'Negative'; conf='High' if len(clean)>=5 else 'Medium'
    else:
        score=45; status='Unknown / insufficient data'; conf='Low'
    return {'score':score,'status':status,'confidence':conf,'sources':sources or ['No source returned recent data'],'headlines':clean[:8],'catalysts':(pos or clean)[:6],'risks':(neg[:5] if neg else (['No negative high-confidence headline detected.'] if clean else ['No recent high-confidence news retrieved; treat as insufficient data, not neutral.']))}

def v42_sec_filings(symbol: str) -> Dict[str, Any]:
    headers={'User-Agent': SEC_USER_AGENT or 'Asif Bandukda abandukda@gmail.com'}; sym=str(symbol).upper()
    try:
        r=requests.get('https://www.sec.gov/files/company_tickers.json',headers=headers,timeout=12)
        if r.status_code!=200: return {'available':False,'reason':f'SEC ticker map HTTP {r.status_code}'}
        cik=None; title=None
        for item in (r.json() or {}).values():
            if str(item.get('ticker','')).upper()==sym:
                cik=str(item.get('cik_str')).zfill(10); title=item.get('title'); break
        if not cik: return {'available':False,'reason':'CIK not found'}
        r=requests.get(f'https://data.sec.gov/submissions/CIK{cik}.json',headers=headers,timeout=12)
        if r.status_code!=200: return {'available':False,'reason':f'SEC submissions HTTP {r.status_code}','cik':cik}
        recent=r.json().get('filings',{}).get('recent',{})
        forms=recent.get('form',[]) or []; dates=recent.get('filingDate',[]) or []
        rows=[{'form':f,'date':d} for f,d in list(zip(forms,dates))[:40]]
        return {'available':True,'cik':cik,'company':title,'recent_forms':rows[:15],'form4_count_recent':sum(1 for x in rows if x['form']=='4'),'form4_recent':[x for x in rows if x['form']=='4'][:5],'forms_8k_count_recent':sum(1 for x in rows if x['form']=='8-K'),'forms_13f_count_recent':sum(1 for x in rows if '13F' in x['form'])}
    except Exception as e:
        return {'available':False,'reason':str(e)[:120]}

def v42_support_resistance(hist: pd.DataFrame, ind: Dict[str,Any]) -> Dict[str, Any]:
    try:
        close=hist['Close'].dropna().astype(float); high=(hist['High'] if 'High' in hist else hist['Close']).dropna().astype(float); low=(hist['Low'] if 'Low' in hist else hist['Close']).dropna().astype(float)
        price=float(close.iloc[-1]); lows=[float(low.tail(20).min()),float(low.tail(50).min()),float(low.tail(min(252,len(low))).min())]; highs=[float(high.tail(20).max()),float(high.tail(50).max()),float(high.tail(min(252,len(high))).max())]
        s1=max([x for x in lows[:2] if x<price], default=min(lows[:2])); s2=min(lows); r1=min([x for x in highs[:2] if x>price], default=max(highs[:2])); r2=max(highs)
        guidance='Near resistance. Avoid chasing unless breakout holds with volume.' if price>=r1*.98 else ('Near support. Better risk/reward if support holds.' if price<=s1*1.04 else 'Between support and resistance. Prefer pullback entry or confirmed breakout.')
        return {'support_1':round(s1,2),'support_2':round(s2,2),'resistance_1':round(r1,2),'resistance_2':round(r2,2),'breakout_level':round(r1*1.01,2),'pullback_zone':f'${s1:.2f} - ${max(s1,price*.98):.2f}','guidance':guidance}
    except Exception:
        return {'guidance':'Support/resistance unavailable.'}

def v42_peer_context(symbol: str, meta: Dict[str,Any]) -> Dict[str,Any]:
    peers=meta.get('peer_symbols') or []
    peers=[str(p).upper() for p in peers if p and str(p).upper()!=str(symbol).upper()][:5]
    score=55; findings=[]; risks=[]
    if peers: findings.append('Peer set identified: '+', '.join(peers)); score+=5
    else: risks.append('Peer list unavailable in current scan.')
    rg=v42_pct(meta.get('revenue_growth')); pe=v42_float(meta.get('forward_pe'))
    if rg is not None: findings.append(f'Revenue growth available for peer context: {rg:.1f}%.'); score += 10 if rg>=15 else 3 if rg>=5 else 0
    if pe is not None and pe>0: findings.append(f'Forward PE available for peer context: {pe:.1f}.'); score += 5 if pe<=25 else 0
    return {'score':int(clamp(score,20,90)),'peers':peers,'findings':findings or ['Peer comparison framework active.'],'risks':risks or ['Peer comparison is directional; confirm exact peer metrics before investing.']}

def v42_build_committee(symbol: str, row: Dict[str,Any], meta: Dict[str,Any], ind: Dict[str,Any], hist: pd.DataFrame) -> Dict[str,Any]:
    news=v42_news_stack(symbol); sec=v42_sec_filings(symbol); sr=v42_support_resistance(hist,ind); peer=v42_peer_context(symbol,meta)
    conviction=v42_float(row.get('conviction'), row.get('Final Conviction') or 50) or 50; upside=v42_float(row.get('expected_upside_pct'), row.get('Target Upside %') or 0) or 0; analyst=v42_float(row.get('analyst_support_score'), meta.get('analyst_support_score') or 50) or 50
    rsi=ind.get('rsi'); atr=ind.get('atr_pct'); price=ind.get('price')
    tech_find=[f'Support 1: ${sr.get("support_1","N/A")} · Resistance 1: ${sr.get("resistance_1","N/A")}.']
    for label,key in [('20-day','sma20'),('50-day','sma50'),('200-day','sma200')]:
        if price and ind.get(key): tech_find.append(f'Price is {"above" if price>ind.get(key) else "below"} the {label} trend.')
    if rsi is not None: tech_find.append(f'RSI is {rsi}.')
    tech_risk=[]
    if rsi is not None and rsi>=70: tech_risk.append('RSI is overbought; avoid chasing.')
    if atr is not None and atr>=8: tech_risk.append('ATR volatility is high; use smaller position sizing.')
    rg=v42_pct(meta.get('revenue_growth')); eg=v42_pct(meta.get('earnings_growth')); finance_find=[]; finance_risk=[]
    if rg is not None: finance_find.append(f'Revenue growth: {rg:.1f}%.')
    if eg is not None: finance_find.append(f'Earnings growth: {eg:.1f}%.')
    for label,key in [('Debt/equity','debt_to_equity'),('Current ratio','current_ratio'),('Free cash flow','free_cash_flow'),('Operating cash flow','operating_cash_flow')]:
        if meta.get(key) not in (None,'',0): finance_find.append(f'{label}: {meta.get(key)}.')
    finance_score=v42_float(row.get('finance_agent_score'), row.get('Finance Agent Score') or 50) or 50
    insider_find=[]; insider_risk=[]; insider_score=50
    if sec.get('available'):
        insider_find += [f'SEC CIK found: {sec.get("cik")}.', f'Recent SEC Form 4 filings found: {sec.get("form4_count_recent",0)}.']; insider_score += min(sec.get('form4_count_recent',0)*3,15)
        insider_risk.append('SEC v1 counts Form 4 activity; transaction-level buy/sell classification will be expanded.')
    else: insider_risk.append('SEC insider data unavailable: '+str(sec.get('reason','unknown')))
    inst_find=[]; inst_score=50
    if sec.get('available'):
        inst_find.append('SEC recent filings reviewed.');
        if sec.get('forms_13f_count_recent',0): inst_find.append(f'Recent 13F-related filings found: {sec.get("forms_13f_count_recent")}.'); inst_score+=10
        else: inst_find.append('No recent issuer-level 13F form found in recent company submissions.')
    agents={
        'News Agent':v42_agent(news['score'],news['status'],'Positive' if news['score']>=70 else 'Neutral' if news['score']>=45 else 'Negative',', '.join(news['sources']),f'Reviews headlines/catalysts. Confidence: {news["confidence"]}.',news['catalysts'],news['risks'],'News flow supports the thesis.' if news['score']>=70 else 'News is mixed or insufficient.'),
        'Finance Agent':v42_agent(finance_score,'Positive' if finance_score>=75 else 'Mixed','Positive' if finance_score>=75 else 'Neutral','FMP/Yahoo fundamentals, financial statements, balance sheet, cash flow','Checks revenue, EPS, margins, leverage, liquidity, cash flow, valuation, and execution.',finance_find or row.get('finance_agent_findings') or ['Financial data limited.'],finance_risk or row.get('finance_agent_risks') or ['No major finance-specific red flag detected.'],row.get('finance_agent_bottom_line') or 'Financial profile reviewed.'),
        'Analyst Agent':v42_agent(analyst,'Positive' if analyst>=65 else 'Mixed','Positive' if analyst>=65 else 'Neutral','Finnhub/Yahoo/FMP analyst targets and recommendation trends','Checks whether Wall Street estimates support the AI thesis.',[f'Analyst support score: {analyst:.0f}/100.', f'Analyst target: ${row.get("analyst_target_mean") or row.get("Analyst Target") or "N/A"}.', f'Analyst count: {row.get("analyst_count") or row.get("Analyst Count") or "N/A"}.'],['Analyst data can lag fast-moving news.'] + (['AI fair value is far above analyst consensus; higher uncertainty.'] if upside>=50 else []),'Analyst view supports the thesis.' if analyst>=65 else 'Analyst view is mixed/limited.'),
        'Technical Agent':v42_agent(conviction,'Positive' if conviction>=75 else 'Mixed','Positive' if conviction>=75 else 'Neutral','Price history, RSI, ATR, volume, SMA, support/resistance','Evaluates trend, momentum, volatility, support/resistance and entry quality.',tech_find,tech_risk or ['No major technical risk detected.'],sr.get('guidance','Technical setup reviewed.')),
        'Insider Agent':v42_agent(insider_score,'Constructive' if insider_score>=60 else 'Limited','Neutral','SEC EDGAR Form 4 framework; Finnhub insider-ready','Checks insider filing activity and prepares buy/sell classification.',insider_find or ['No recent Form 4 activity retrieved.'],insider_risk,'Insider signal is limited until transaction-level parsing is expanded.'),
        'Institutional Agent':v42_agent(inst_score,'Constructive' if inst_score>=60 else 'Limited','Neutral','SEC EDGAR filings plus FMP institutional ownership-ready','Checks institutional context and 13F availability.',inst_find or ['Institutional data limited.'],['13F data is delayed by reporting schedule.'],'Institutional signal is directional and should be confirmed with holder details.'),
        'Competitor Agent':v42_agent(peer['score'],'Constructive' if peer['score']>=60 else 'Limited','Positive' if peer['score']>=70 else 'Neutral','FMP peer list and company fundamentals','Compares company fundamentals and valuation context against peers.',peer['findings'],peer['risks'],'Peer context supports the thesis.' if peer['score']>=70 else 'Peer context is limited/mixed.'),
        'Political Agent':v42_agent(50,'Not connected yet','Neutral','Capitol Trades public data planned; no API key required','Tracks congressional trading once public feed integration is enabled.',['Political Agent framework is active.'],['Capitol Trades ingestion not enabled yet; no political score applied.'],'No political trading signal applied yet.'),
        'Recovery Agent':v42_agent(65 if (v42_float(row.get('distance_from_52w_high_pct'),0) or 0)<-20 else 50,'Constructive' if (v42_float(row.get('distance_from_52w_high_pct'),0) or 0)<-20 else 'Limited','Positive' if (v42_float(row.get('distance_from_52w_high_pct'),0) or 0)<-20 else 'Neutral','52-week drawdown, growth, analyst support, technical recovery signals','Explains whether this is a recovery candidate or momentum setup.',['Recovery framework active.'],['Recovery thesis requires business outlook to remain intact.'],'Recovery setup exists only if fundamentals remain healthy.'),
        'ETF / Ownership Agent':v42_agent(55,'Framework active','Neutral','ETF inclusion and ownership flow framework','Checks ETF/index ownership support.',['ETF/ownership framework is active.'],['Detailed ETF flow data not fully connected yet.'],'ETF/ownership is not yet a primary scoring driver.')
    }
    pos=sum(1 for a in agents.values() if a['score']>=65); total=len(agents); agree=pos/total
    row.update({'ai_committee':agents,'v42_news_score':agents['News Agent']['score'],'v42_news_summary':agents['News Agent']['bottom_line'],'v42_news_catalysts':news['catalysts'],'v42_news_risks':news['risks'],'v42_news_sources':news['sources'],'v42_sec_available':sec.get('available',False),'v42_sec_cik':sec.get('cik'),'v42_support_1':sr.get('support_1'),'v42_support_2':sr.get('support_2'),'v42_resistance_1':sr.get('resistance_1'),'v42_resistance_2':sr.get('resistance_2'),'v42_breakout_level':sr.get('breakout_level'),'v42_pullback_zone':sr.get('pullback_zone'),'v42_chart_guidance':sr.get('guidance'),'thesis_strength':'Exceptional Thesis' if agree>=.75 and conviction>=85 else 'Strong Thesis' if agree>=.60 else 'Moderate Thesis' if agree>=.40 else 'Developing Thesis','evidence_confidence':'High' if agree>=.75 else 'Medium-High' if agree>=.60 else 'Medium' if agree>=.40 else 'Low-Medium','v42_committee_positive_agents':pos,'v42_committee_total_agents':total})
    return row


def v42_agent_translation(name: str, agent: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, str]:
    name_l = str(name).lower()
    price = v42_safe_float(row.get("price"), row.get("Price"))
    support_1 = v42_safe_float(row.get("v42_support_1"), row.get("Support 1"))
    resistance_1 = v42_safe_float(row.get("v42_resistance_1"), row.get("Resistance 1"))
    breakout = v42_safe_float(row.get("v42_breakout_level"), row.get("Breakout Level"))

    if "technical" in name_l:
        if price and support_1 and resistance_1:
            action = f"Do not chase. Better entries are a pullback near ${support_1:.2f} support or a confirmed breakout above ${breakout or resistance_1:.2f} with volume."
        else:
            action = "Use trend confirmation and avoid buying extended moves without a pullback or breakout confirmation."
        return {
            "what_it_means": "The stock trend and momentum are evaluated using moving averages, RSI, volatility, volume, and support/resistance.",
            "why_it_matters": "A strong technical score means the stock is moving well, but overbought momentum can increase pullback risk.",
            "investor_action": action,
            "green_flag": "Price trend is constructive when it stays above key moving averages.",
            "red_flag": "RSI above 70 means the stock may be overheated short term.",
        }

    if "news" in name_l:
        if agent.get("available") is False or agent.get("score") is None:
            return {
                "what_it_means": "The system did not retrieve recent direct company-specific headlines from connected sources.",
                "why_it_matters": "This is not bullish or bearish; it means the news source did not provide enough current evidence to score the catalyst backdrop.",
                "investor_action": "Do not treat missing news as neutral. Manually verify major headlines or use live research before acting on a high-conviction idea.",
                "green_flag": "No negative high-confidence company headline was detected.",
                "red_flag": "No confirmed catalyst was found, so the thesis relies more heavily on finance, analyst, and technical agents.",
            }
        return {
            "what_it_means": "The News Agent checks whether recent headlines provide a positive catalyst, negative risk, or mixed backdrop.",
            "why_it_matters": "Fresh news can explain why a stock is moving and whether the move is supported by a real catalyst.",
            "investor_action": "Use direct company headlines as decision support. Treat indirect ecosystem mentions as weaker evidence.",
            "green_flag": "Direct earnings, product, guidance, partnership, or analyst-upgrade headlines support the thesis.",
            "red_flag": "Lawsuits, guidance cuts, downgrades, weak earnings, or indirect-only mentions reduce confidence.",
        }

    if "finance" in name_l:
        return {
            "what_it_means": "The Finance Agent checks revenue growth, EPS, margins, debt, liquidity, valuation, and cash flow quality.",
            "why_it_matters": "A stock can look technically strong but still be risky if the business is not executing financially.",
            "investor_action": "Prefer stocks where revenue/EPS growth, margins, and cash flow support the technical setup. Be cautious if upside is high but financial execution is weak.",
            "green_flag": "Positive revenue growth, improving EPS, manageable debt, and positive free cash flow.",
            "red_flag": "Negative growth, high leverage, falling margins, or negative free cash flow.",
        }

    if "analyst" in name_l:
        return {
            "what_it_means": "The Analyst Agent compares AI fair value with Wall Street targets, analyst count, and recommendation support.",
            "why_it_matters": "Analyst support helps validate the thesis, but analyst targets can lag fast-moving news.",
            "investor_action": "If AI fair value is much higher than analyst consensus, treat upside as higher uncertainty and require stronger confirmation from other agents.",
            "green_flag": "Large analyst coverage, constructive target upside, and positive recommendation support.",
            "red_flag": "AI target far above analyst target, low analyst count, or recent downgrades.",
        }

    if "insider" in name_l:
        return {
            "what_it_means": "The Insider Agent currently detects SEC Form 4 filing activity, but does not yet fully classify buys versus sells.",
            "why_it_matters": "Insider buying can be a strong confidence signal; insider selling is more nuanced and may be routine compensation or diversification.",
            "investor_action": "Do not treat Form 4 count alone as bullish. Wait for buy/sell classification before using this as a major decision factor.",
            "green_flag": "Confirmed open-market insider purchases by executives or directors.",
            "red_flag": "Heavy discretionary selling without purchases, especially by multiple executives.",
        }

    if "institutional" in name_l:
        return {
            "what_it_means": "The Institutional Agent checks SEC/FMP ownership context and whether large funds may be accumulating or reducing exposure.",
            "why_it_matters": "Institutional buying can support demand, but 13F data is delayed and not real time.",
            "investor_action": "Use institutional data as confirmation, not as the primary reason to buy. Look for net fund accumulation over multiple quarters.",
            "green_flag": "Major holders increasing positions or more funds adding than reducing.",
            "red_flag": "Broad institutional reduction or falling ownership across several quarters.",
        }

    if "competitor" in name_l:
        return {
            "what_it_means": "The Competitor Agent compares growth, valuation, margin, and peer context where peer data is available.",
            "why_it_matters": "A stock is more attractive when it grows faster or has better margins while trading at a reasonable valuation versus peers.",
            "investor_action": "If peer data is unavailable, do not over-weight this agent. When available, prefer stocks with stronger growth and cheaper valuation than peers.",
            "green_flag": "Growth above peer average with equal or lower valuation.",
            "red_flag": "Expensive valuation while growth or margins lag competitors.",
        }

    if "political" in name_l:
        return {
            "what_it_means": "The Political Agent framework is present but congressional-trading ingestion is not fully connected yet.",
            "why_it_matters": "Political trading data can be interesting, but it should not drive the investment thesis by itself.",
            "investor_action": "Ignore this score until Capitol Trades ingestion is enabled. Do not treat the current framework status as positive or negative.",
            "green_flag": "Future signal: repeated congressional buys across multiple lawmakers.",
            "red_flag": "Future signal: repeated congressional sells or regulatory risk exposure.",
        }

    if "recovery" in name_l:
        return {
            "what_it_means": "The Recovery Agent evaluates whether a stock has dropped enough to create a recovery opportunity while fundamentals remain intact.",
            "why_it_matters": "A stock that is down sharply is not automatically cheap; the reason for the drop matters.",
            "investor_action": "Prefer recovery setups where the drop appears temporary, revenue/EPS outlook remains stable, and analyst/news support improves.",
            "green_flag": "Large drawdown with improving fundamentals or stabilizing guidance.",
            "red_flag": "Drop caused by broken business model, worsening guidance, debt stress, or repeated misses.",
        }

    if "etf" in name_l or "ownership" in name_l:
        return {
            "what_it_means": "The ETF / Ownership Agent checks whether index or ETF exposure may support demand for the stock.",
            "why_it_matters": "Stocks included in major ETFs can benefit from passive inflows, but this is usually a secondary signal.",
            "investor_action": "Use ETF ownership as a supporting confirmation only.",
            "green_flag": "Included in major growth/technology ETFs with strong inflows.",
            "red_flag": "Low ownership support or removal from key indexes/ETFs.",
        }

    return {
        "what_it_means": "This agent summarizes one part of the investment thesis.",
        "why_it_matters": "It helps determine whether the stock has enough supporting evidence.",
        "investor_action": "Use this as one input, not a standalone buy/sell signal.",
        "green_flag": "Supportive evidence from this agent.",
        "red_flag": "Weak or missing evidence from this agent.",
    }


def v42_apply_investor_translations(row: Dict[str, Any]) -> Dict[str, Any]:
    committee = row.get("ai_committee")
    if not isinstance(committee, dict):
        return row

    for name, agent in committee.items():
        if not isinstance(agent, dict):
            continue

        agent.update(v42_agent_translation(name, agent, row))

        if name == "Political Agent" and str(agent.get("status", "")).lower().startswith("not connected"):
            agent["score"] = None
            agent["impact"] = "Not scored"
        if name == "Insider Agent" and "transaction-level" in " ".join(agent.get("risks", [])).lower():
            agent["status"] = "Limited"
            agent["impact"] = "Not scored"
        if name == "Institutional Agent" and str(agent.get("status", "")).lower() == "limited":
            agent["impact"] = "Not scored"

    row["ai_committee"] = committee
    return row


def v42_apply_investor_translations_safe(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    V42.0.7 safety wrapper.
    Investor translation is a display enhancement. It must never crash the overnight scan.
    If anything goes wrong, keep the existing committee and add a diagnostic note.
    """
    try:
        return v42_apply_investor_translations(row)
    except Exception as e:
        try:
            committee = row.get("ai_committee")
            if isinstance(committee, dict):
                for name, agent in committee.items():
                    if isinstance(agent, dict):
                        agent.setdefault("what_it_means", "This agent summarizes one part of the investment thesis.")
                        agent.setdefault("why_it_matters", "It helps determine whether the stock has enough supporting evidence.")
                        agent.setdefault("investor_action", "Use this as one input, not a standalone buy/sell signal.")
                        agent.setdefault("green_flag", "Supportive evidence from this agent.")
                        agent.setdefault("red_flag", "Weak or missing evidence from this agent.")
                row["ai_committee"] = committee
            row["v42_translation_warning"] = f"Investor translation fallback used: {str(e)[:160]}"
        except Exception:
            row["v42_translation_warning"] = "Investor translation fallback used."
        return row


def v42_build_committee_safe(symbol: str, row: Dict[str, Any], meta: Dict[str, Any], ind: Dict[str, Any], hist: pd.DataFrame) -> Dict[str, Any]:
    """
    V42.0.7 safety wrapper around V42 committee creation.
    The scanner should continue even if a live API source is rate-limited or one ticker has malformed data.
    """
    try:
        return v42_build_committee(symbol, row, meta, ind, hist)
    except Exception as e:
        row["v42_committee_warning"] = f"V42 committee fallback used: {str(e)[:160]}"
        existing = row.get("ai_committee")
        if not isinstance(existing, dict):
            row["ai_committee"] = {
                "Technical Agent": {
                    "score": int(row.get("conviction", row.get("Final Conviction", 50)) or 50),
                    "status": "Available",
                    "impact": "Neutral",
                    "data_used": "Existing scan fields",
                    "summary": "Fallback technical/scan score used because V42 committee could not fully build.",
                    "findings": row.get("setup_tags", []) if isinstance(row.get("setup_tags"), list) else [],
                    "risks": row.get("risk_tags", []) if isinstance(row.get("risk_tags"), list) else [],
                    "bottom_line": "Use the existing scan score while V42 committee data is unavailable.",
                    "what_it_means": "The fallback uses existing scanner fields only.",
                    "why_it_matters": "This prevents one failed API source from breaking the full scan.",
                    "investor_action": "Review this ticker with Live Research or rerun the scan.",
                    "green_flag": "Core scan still completed for this ticker.",
                    "red_flag": "Full V42 committee did not populate for this ticker.",
                }
            }
        return row


# =========================
# V42.1 FAST TIERED SCAN
# =========================
# V42.6.1 hard cron controls
FAST_CRON_MODE = os.getenv("FAST_CRON_MODE", "true").strip().lower() not in {"0", "false", "no", "off"}
FULL_COMMITTEE_LIMIT = int(os.getenv("FULL_COMMITTEE_LIMIT", "15"))
RECOVERY_FULL_COMMITTEE_LIMIT = int(os.getenv("RECOVERY_FULL_COMMITTEE_LIMIT", "10"))
ETF_FULL_COMMITTEE_LIMIT = int(os.getenv("ETF_FULL_COMMITTEE_LIMIT", "10"))
NEWS_AGENT_LIMIT = int(os.getenv("NEWS_AGENT_LIMIT", "25"))
SEC_AGENT_LIMIT = int(os.getenv("SEC_AGENT_LIMIT", "10"))
COMPETITOR_AGENT_LIMIT = int(os.getenv("COMPETITOR_AGENT_LIMIT", "10"))
FULL_RESEARCH_MIN_CONVICTION = float(os.getenv("FULL_RESEARCH_MIN_CONVICTION", "96"))
FULL_RESEARCH_MIN_RECOVERY = float(os.getenv("FULL_RESEARCH_MIN_RECOVERY", "88"))
WATCHLIST_FULL_COMMITTEE_LIMIT = int(os.getenv("WATCHLIST_FULL_COMMITTEE_LIMIT", "25"))
FAST_CRON_SKIP_PRE_RANK_DEEP_APIS = os.getenv("FAST_CRON_SKIP_PRE_RANK_DEEP_APIS", "true").strip().lower() not in {"0", "false", "no", "off"}
HTTP_TIMEOUT_FAST = float(os.getenv("HTTP_TIMEOUT_FAST", "6"))




# V42.6.1 safety timeout patch: prevents one slow endpoint from dragging cron.
def v4261_patch_requests_timeouts():
    try:
        if getattr(requests, "_v4261_patched", False):
            return
        _orig_get = requests.get
        _orig_post = requests.post
        def _get(*args, **kwargs):
            kwargs.setdefault("timeout", HTTP_TIMEOUT_FAST)
            return _orig_get(*args, **kwargs)
        def _post(*args, **kwargs):
            kwargs.setdefault("timeout", HTTP_TIMEOUT_FAST)
            return _orig_post(*args, **kwargs)
        requests.get = _get
        requests.post = _post
        requests._v4261_patched = True
    except Exception:
        pass

v4261_patch_requests_timeouts()

def v421_watchlist_symbols() -> set:
    symbols = set()
    try:
        env_watch = os.getenv("WATCHLIST_SYMBOLS", "")
        if env_watch:
            symbols.update([x.strip().upper() for x in env_watch.split(",") if x.strip()])

        for fname in ["watchlist.json", "watchlist.txt"]:
            p = Path(DATA_DIR) / fname
            if not p.exists():
                continue
            txt = p.read_text()
            if fname.endswith(".json"):
                try:
                    data = json.loads(txt)
                    if isinstance(data, list):
                        symbols.update([str(x).upper() for x in data])
                    elif isinstance(data, dict):
                        for v in data.values():
                            if isinstance(v, list):
                                symbols.update([str(x).upper() for x in v])
                            elif isinstance(v, str):
                                symbols.add(v.upper())
                except Exception:
                    pass
            else:
                symbols.update([x.strip().upper() for x in txt.splitlines() if x.strip()])
    except Exception:
        pass
    return set(list(symbols)[:WATCHLIST_FULL_COMMITTEE_LIMIT])


def v421_should_run_full_research(symbol: str, row: Dict[str, Any]) -> bool:
    """
    V42.6.1 hard cap: scheduled cron full committee is only for the very best names.
    This prevents 150 rows from running expensive News/SEC/FMP/Finnhub/competitor calls.
    """
    if not FAST_CRON_MODE:
        return True

    symbol = str(symbol).upper().strip()
    conviction = v42_safe_float(row.get("conviction"), row.get("Final Conviction") or 0) or 0
    recovery_score = v42_safe_float(row.get("recovery_score"), row.get("Recovery Score") or 0) or 0
    upside = v42_safe_float(row.get("expected_upside_pct"), row.get("Target Upside %") or 0) or 0

    watch = v421_watchlist_symbols()
    if symbol in watch:
        return True

    # Function-level counter persists during this cron run.
    used = getattr(v421_should_run_full_research, "_used", 0)
    if used >= FULL_COMMITTEE_LIMIT:
        return False

    eligible = False
    if conviction >= FULL_RESEARCH_MIN_CONVICTION:
        eligible = True
    elif recovery_score >= FULL_RESEARCH_MIN_RECOVERY:
        eligible = True
    elif conviction >= 94 and upside >= 30:
        eligible = True

    if eligible:
        setattr(v421_should_run_full_research, "_used", used + 1)
        return True
    return False

def v421_build_light_committee(symbol: str, row: Dict[str, Any], meta: Dict[str, Any], ind: Dict[str, Any], hist: pd.DataFrame) -> Dict[str, Any]:
    """
    Lightweight committee for non-priority rows.
    No live News/Finnhub/FMP/SEC/Competitor calls.
    Keeps cron fast while preserving useful basic research.
    """
    try:
        sr = v42_support_resistance(hist, ind, row)
    except Exception:
        sr = {"guidance": "Support/resistance unavailable."}

    conviction = v42_safe_float(row.get("conviction"), row.get("Final Conviction") or 50) or 50
    finance_score = v42_safe_float(row.get("finance_agent_score"), row.get("Finance Agent Score") or 50) or 50
    analyst_score = v42_safe_float(row.get("analyst_support_score"), row.get("Analyst Support Score") or 50) or 50
    recovery_score = v42_safe_float(row.get("recovery_score"), row.get("Recovery Score") or 0) or 0

    committee = {
        "Technical Agent": v42_agent(
            conviction,
            "Positive" if conviction >= 75 else "Mixed",
            "Positive" if conviction >= 75 else "Neutral",
            "Price history, RSI, ATR, volume, SMA, support/resistance",
            "Lightweight scheduled scan: evaluates trend, momentum, volatility, support/resistance and entry quality.",
            [
                f"Support 1: {sr.get('support_1', 'N/A')} · Resistance 1: {sr.get('resistance_1', 'N/A')}.",
                f"RSI: {ind.get('rsi', 'N/A')}.",
            ],
            ["Latest news/SEC/competitor checks are deferred to full committee or live lookup."],
            sr.get("guidance", "Use pullback or breakout confirmation."),
        ),
        "Finance Agent": v42_agent(
            finance_score,
            "Positive" if finance_score >= 75 else "Mixed",
            "Positive" if finance_score >= 75 else "Neutral",
            "Existing scan fundamentals only",
            "Lightweight scheduled scan: uses already-fetched financial fields to avoid extra API calls.",
            row.get("finance_agent_findings") or ["Basic financial score available from scan."],
            row.get("finance_agent_risks") or ["Deep financial detail available in full committee or live research."],
            row.get("finance_agent_bottom_line") or "Financial profile requires full research for deeper detail.",
        ),
        "Analyst Agent": v42_agent(
            analyst_score,
            "Positive" if analyst_score >= 65 else "Mixed",
            "Positive" if analyst_score >= 65 else "Neutral",
            "Existing analyst target/count/recommendation fields",
            "Lightweight scheduled scan: checks analyst target and support using existing scan fields.",
            [f"Analyst target: {row.get('analyst_target_mean') or row.get('Analyst Target') or 'N/A'}."],
            ["Recent target revisions are checked in full committee or live research."],
            "Analyst support is directional in lightweight mode.",
        ),
        "News Agent": {
            "score": None,
            "status": "Deferred to full/live research",
            "impact": "Not scored",
            "available": False,
            "data_used": "Skipped in lightweight scheduled scan",
            "summary": "News was not pulled for this lower-tier row to keep the scheduled scan fast.",
            "findings": ["Use Live Research or wait for this ticker to rank into the full committee tier."],
            "risks": ["Do not assume no news; news was intentionally deferred."],
            "bottom_line": "News Agent deferred to full committee/live lookup.",
        },
        "Insider Agent": {
            "score": None,
            "status": "Deferred to full/live research",
            "impact": "Not scored",
            "data_used": "SEC skipped in lightweight scheduled scan",
            "summary": "Insider/SEC data is only run for priority tickers during cron.",
            "findings": [],
            "risks": ["Use Live Research for immediate insider/SEC check."],
            "bottom_line": "Insider Agent deferred.",
        },
        "Institutional Agent": {
            "score": None,
            "status": "Deferred to full/live research",
            "impact": "Not scored",
            "data_used": "SEC/FMP ownership skipped in lightweight scheduled scan",
            "summary": "Institutional data is not run for every row during cron.",
            "findings": [],
            "risks": ["Use Live Research for immediate ownership check."],
            "bottom_line": "Institutional Agent deferred.",
        },
        "Competitor Agent": {
            "score": None,
            "status": "Deferred to full/live research",
            "impact": "Not scored",
            "data_used": "Peer comparison skipped in lightweight scheduled scan",
            "summary": "Competitor comparison is deferred for lower-tier rows to reduce API calls.",
            "findings": [],
            "risks": ["Use full committee/live lookup for peer analysis."],
            "bottom_line": "Competitor Agent deferred.",
        },
        "Recovery Agent": v42_agent(
            recovery_score if recovery_score else 50,
            "Constructive" if recovery_score >= 65 else "Limited",
            "Positive" if recovery_score >= 65 else "Neutral",
            "Existing drawdown/recovery fields",
            "Lightweight recovery check from scan data.",
            row.get("recovery_findings") or ["Recovery scan field available if present."],
            row.get("recovery_risks") or ["Full recovery explanation available in full committee/live research."],
            "Recovery signal is directional in lightweight mode.",
        ),
        "ETF / Ownership Agent": {
            "score": None,
            "status": "Deferred to full/live research",
            "impact": "Not scored",
            "data_used": "ETF/ownership checks skipped in lightweight scheduled scan",
            "summary": "ETF ownership data is deferred unless this is a priority ETF/watchlist row.",
            "findings": [],
            "risks": ["Use ETF tab/detail or live lookup for deeper ETF/ownership context."],
            "bottom_line": "ETF/Ownership Agent deferred.",
        },
        "Political Agent": {
            "score": None,
            "status": "Not connected yet",
            "impact": "Not scored",
            "data_used": "Capitol Trades planned",
            "summary": "Political trading feed is not enabled yet.",
            "findings": [],
            "risks": ["No political score applied."],
            "bottom_line": "Political Agent not scored.",
        },
    }

    row["ai_committee"] = committee
    row["v42_tier"] = "light"
    row["v42_support_1"] = sr.get("support_1")
    row["v42_support_2"] = sr.get("support_2")
    row["v42_resistance_1"] = sr.get("resistance_1")
    row["v42_resistance_2"] = sr.get("resistance_2")
    row["v42_breakout_level"] = sr.get("breakout_level")
    row["v42_pullback_zone"] = sr.get("pullback_zone")
    row["v42_chart_guidance"] = sr.get("guidance")
    return row


def v421_apply_tiered_committee(symbol: str, row: Dict[str, Any], meta: Dict[str, Any], ind: Dict[str, Any], hist: pd.DataFrame) -> Dict[str, Any]:
    """
    V42.1 tiered scheduled scan:
      - Full committee for priority names.
      - Lightweight committee for the remaining Top 150.
      - Live lookup remains full research on demand.
    """
    try:
        if v421_should_run_full_research(symbol, row):
            if "v42_build_committee_safe" in globals():
                row = v42_build_committee_safe(symbol, row, meta, ind, hist)
            else:
                row = v42_build_committee(symbol, row, meta, ind, hist)
            row["v42_tier"] = "full"
        else:
            row = v421_build_light_committee(symbol, row, meta, ind, hist)

        if "v42_apply_investor_translations_safe" in globals():
            row = v42_apply_investor_translations_safe(row)
        elif "v42_apply_investor_translations" in globals():
            row = v42_apply_investor_translations(row)
        return row
    except Exception as e:
        row["v42_tier"] = "light_fallback"
        row["v42_tier_warning"] = f"Tiered committee fallback used: {str(e)[:160]}"
        return row


# =========================
# SCAN PIPELINE
# =========================

def passes_basic_filter(ind: Dict[str, Any], meta: Dict[str, Any]) -> bool:
    # V41 permanent exclusion rules: remove unwanted categories before scoring.
    reason = exclusion_reason(meta)
    if reason:
        return False

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
    etf_rows: List[Dict[str, Any]] = []

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

                # V40.0: enrich Yahoo metadata with FMP profile data when available.
                # FMP values only replace missing/weak fields; failures safely do nothing.
                fmp_meta = get_fmp_data(symbol)
                if fmp_meta:
                    for key, value in fmp_meta.items():
                        if value not in (None, "", "Unknown"):
                            current = meta.get(key)
                            if current in (None, "", "Unknown", symbol) or key.startswith("source_") or key in {
                                "country", "exchange", "fmp_price", "beta", "last_dividend",
                                "range_52w", "website", "description"
                            }:
                                meta[key] = value

                # V41: apply hard exclusions after FMP profile enrichment and before extra API calls.
                if exclusion_reason(meta):
                    metadata_cache[symbol] = meta
                    continue

                # V42.6.1: skip expensive deep APIs during pre-rank pass.
                # Full/deep enrichment should happen only for selected top names or live ticker research.
                if not FAST_CRON_SKIP_PRE_RANK_DEEP_APIS:
                    finance_meta = get_fmp_financial_intelligence(symbol)
                    if finance_meta:
                        for key, value in finance_meta.items():
                            if value not in (None, "", "Unknown"):
                                meta[key] = value

                    finnhub_meta = get_finnhub_research(symbol)
                    if finnhub_meta:
                        for key, value in finnhub_meta.items():
                            if value not in (None, "", "Unknown"):
                                meta[key] = value

                    insider_meta = get_finnhub_insider_activity(symbol)
                    if insider_meta:
                        for key, value in insider_meta.items():
                            if value not in (None, "", "Unknown"):
                                meta[key] = value

                    news_meta = get_news_research(symbol, meta.get("company_name", symbol))
                    if news_meta:
                        for key, value in news_meta.items():
                            if value not in (None, "", "Unknown"):
                                meta[key] = value
                else:
                    meta["fast_cron_pre_rank_deep_apis_skipped"] = True

                metadata_cache[symbol] = meta

            if v42_is_excluded_company(symbol, meta):
                continue

            quote_type = str(meta.get("quote_type", "")).upper()
            if quote_type == "ETF":
                etf_row = score_etf_row(symbol, meta, ind)
                if etf_row:
                    price_history = build_price_history_intelligence(hist, ind)
                    if price_history:
                        etf_row.update(price_history)
                    etf_row = apply_research_field_fallbacks(etf_row, meta)
                    if FAST_CRON_MODE and len(etf_rows) >= ETF_FULL_COMMITTEE_LIMIT:
                        etf_row = v421_build_light_committee(symbol, etf_row, meta, ind, hist)
                    else:
                        etf_row = v42_build_committee(symbol, etf_row, meta, ind, hist)
                    etf_rows.append(etf_row)
                continue

            if not passes_basic_filter(ind, meta):
                continue

            score, good, risks = score_stock(ind, meta)
            row = make_dashboard_row(symbol, meta, ind, score, good, risks)
            price_history = build_price_history_intelligence(hist, ind)
            if price_history:
                row.update(price_history)
            row = enhance_ai_committee(row, meta, ind)
            row = apply_research_field_fallbacks(row, meta)
            row = v421_apply_tiered_committee(symbol, row, meta, ind, hist)

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
    etf_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("dollar_volume") or 0), reverse=True)
    etf_rows = etf_rows[:150]

    # If full scan is too thin, only backfill with actual valid prescreen rows, not fake rows.
    if len(full_rows) < min(25, MAX_FULL_SCAN):
        seen = {r["symbol"] for r in full_rows}
        for row in prescreen_rows:
            if row["symbol"] not in seen and row.get("price") and row.get("conviction", 0) >= 38:
                full_rows.append(row)
                seen.add(row["symbol"])
            if len(full_rows) >= min(50, MAX_FULL_SCAN):
                break

    # V40.6: spread final conviction scores using relative ranking after all rows are known.
    full_rows = normalize_final_convictions(full_rows)
    prescreen_rows = normalize_final_convictions(prescreen_rows)

    full_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("relative_rank_score") or 0, r.get("dollar_volume") or 0), reverse=True)
    prescreen_rows.sort(key=lambda r: (r.get("conviction") or 0, r.get("relative_rank_score") or 0, r.get("dollar_volume") or 0), reverse=True)

    # V41.1: Recovery tab focuses on stocks that fell but still have a forward rebound case.
    recovery_rows = build_recovery_rows(prescreen_rows)

    state = {
        "generated_at": now_iso(),
        "status": "success",
        "version": "V47.0",
        "universe_count": len(universe),
        "prescreen_count": len(prescreen_rows),
        "full_scan_count": len(full_rows),
        "recovery_count": len(recovery_rows),
        "etf_count": len(etf_rows),
        "fallback_rows_allowed": False,
        "data_dir": str(DATA_DIR),
        "github_persisted": bool(os.getenv("GITHUB_ACTIONS")),
        "duration_seconds": round(time.time() - start_time, 2),
        "fast_cron_mode": FAST_CRON_MODE,
        "full_committee_limit": FULL_COMMITTEE_LIMIT,
        "pre_rank_deep_apis_skipped": FAST_CRON_SKIP_PRE_RANK_DEEP_APIS,
        "filters": {
            "min_price": MIN_PRICE,
            "max_price": MAX_PRICE,
            "min_dollar_volume": MIN_DOLLAR_VOLUME,
            "min_market_cap": MIN_MARKET_CAP,
        },
        "api_keys_detected": {
            "fmp": bool(FMP_API_KEY),
            "finnhub": bool(FINNHUB_API_KEY),
            "newsapi": bool(NEWSAPI_KEY),
        },
        "v40_3_changes": {
            "finnhub_analyst_intelligence": True,
            "newsapi_catalyst_intelligence": True,
            "research_thesis_enhanced": True,
        },
        "v40_1_changes": {
            "conviction_normalized": True,
            "ai_fair_value_engine": True,
            "generic_30pct_target_reduced": True,
        },
        "v40_6_changes": {
            "relative_conviction_distribution": True,
            "score_clustering_reduced": True,
        },
        "v41_1_changes": {
            "recovery_intelligence": True,
            "recovery_scan_file": True,
            "viewer_ticker_research": True,
        },
        "v41_2_changes": {
            "watchlist_add_from_ticker_search": True,
            "watchlist_symbols_included": True,
        },
        "v41_3_changes": {
            "etf_tab": True,
            "non_financial_non_israel_etf_screen": True,
        },
        "v41_4_changes": {
            "explainable_agent_cards": True,
            "metric_ranges_and_definitions": True,
        },
        "v41_4_1_changes": {
            "inline_metric_explanations": True,
            "agent_cards_more_educational": True,
        },
        "v41_5_changes": {
            "deep_finance_agent": True,
            "eps_revenue_debt_margin_cashflow_checks": True,
            "peer_comparison_scaffolding": True,
            "richer_agent_cross_checks": True,
        },
        "v41_6_changes": {
            "price_history_intelligence": True,
            "range_52w_position": True,
            "drawdown_analysis": True,
            "multi_period_return_fields": True,
        },
        "v41_6_1_changes": {
            "true_52w_scan_history": True,
            "interactive_5y_chart_supported_by_dashboard": True,
            "visible_52w_table_columns": True,
        },
        "v41_7_changes": {
            "analyst_support_fallbacks": True,
            "news_sentiment_fallbacks": True,
            "thesis_strength_differentiated": True,
            "research_field_quality_assurance": True,
        },
        "v41_8_changes": {
            "live_any_ticker_research_app_side": True,
            "no_wait_research_cards": True,
        },
        "v41_8_1_changes": {
            "fixed_interactive_detail_charts": True,
            "chart_dependency_warning": True,
        },
        "v41_8_2_changes": {
            "rate_limit_safe_live_research": True,
            "price_history_fallback_cards": True,
        },
        "v41_8_3_changes": {
            "forced_chart_rendering": True,
            "legacy_agent_detail_fallback": True,
        },
        "v41_8_4_changes": {
            "chart_inserted_inside_render_detail": True,
            "chart_above_quick_metric_guide": True,
        },
        "v41_8_5_changes": {
            "fmp_chart_fallback": True,
            "yahoo_then_fmp_history": True,
        },
        "v41_8_6_changes": {
            "unique_chart_widget_keys": True,
            "duplicate_chart_key_fix": True,
        },
        "v42_changes": {
            "universal_ai_investment_committee": True,
            "enhanced_news_agent_multi_source": True,
            "sec_edgar_agent_framework": True,
            "insider_institutional_competitor_political_framework": True,
            "support_resistance_intelligence": True,
            "applies_to_all_tabs_and_live_lookup": True,
        },
        "v41_changes": {
            "hard_exclusions": True,
            "ai_committee_summary": True,
            "finnhub_insider_agent": True,
            "valuation_reconciliation": True,
            "thesis_strength_and_confidence": True,
        },
    }

    write_json(PRESCREEN_FILE, prescreen_rows)
    write_json(FULL_SCAN_FILE, full_rows)
    write_json(RECOVERY_SCAN_FILE, recovery_rows)
    write_json(ETF_SCAN_FILE, etf_rows)
    write_json(STATE_FILE, state)

    if GITHUB_PERSIST:
        state["github_persisted"] = persist_to_github() or bool(os.getenv("GITHUB_ACTIONS"))
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
        str(RECOVERY_SCAN_FILE),
        str(ETF_SCAN_FILE),
        str(WATCHLIST_FILE),
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
            "version": "V42.6.1",
            "error": str(exc),
            "data_dir": str(DATA_DIR),
            "github_persisted": bool(os.getenv("GITHUB_ACTIONS")),
        }
        write_json(STATE_FILE, error_state)
        print(json.dumps(error_state, indent=2))
        sys.exit(1)




# =========================
# V43 BUSINESS QUALITY + SCORE DISTRIBUTION HELPERS
# =========================

def v43s_float(value, default=0.0):
    try:
        if value in (None, "", "N/A", "None"):
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return default


def v43s_business_quality(row):
    sector = str(row.get("Sector") or "").lower() if hasattr(row, "get") else ""
    ticker = str(row.get("Ticker") or row.get("Symbol") or "").upper() if hasattr(row, "get") else ""
    pe = row.get("PE Ratio") if hasattr(row, "get") else None
    if pe is None and hasattr(row, "get"):
        pe = row.get("P/E") or row.get("Forward PE") or row.get("Trailing PE")
    pe = v43s_float(pe, None)
    analyst_count = int(v43s_float(row.get("Analyst Count") if hasattr(row, "get") else 0, 0))
    score = 70
    flags = []
    if pe is not None:
        if pe < 0:
            score -= 25
            flags.append("negative_pe")
        elif pe > 80:
            score -= 8
            flags.append("high_pe")
        elif pe <= 35:
            score += 8
    else:
        flags.append("pe_unavailable")
    if analyst_count >= 20:
        score += 4
    elif 0 < analyst_count < 5:
        score -= 4
    if any(k in (sector + " " + ticker.lower()) for k in ["biotech", "therapeutics", "pharma"]):
        if pe is not None and pe < 0:
            score -= 12
            flags.append("speculative_biotech_losses")
    score = max(0, min(100, round(score)))
    if score >= 85:
        tier = "Quality Compounder"
    elif score >= 70:
        tier = "Growth Leader"
    elif score >= 55:
        tier = "Recovery / Mixed Quality"
    else:
        tier = "Speculative"
    return score, tier, flags


def v43s_rebalanced_score(row):
    existing = v43s_float(row.get("Final Conviction") if hasattr(row, "get") else 0, 0)
    quality_score, tier, flags = v43s_business_quality(row)
    analyst_support = str(row.get("Analyst Support") or "") if hasattr(row, "get") else ""
    news = str(row.get("News Sentiment") or "") if hasattr(row, "get") else ""
    upside = v43s_float(row.get("Target Upside %") if hasattr(row, "get") else 0, 0)
    ai = v43s_float(row.get("AI Fair Value") if hasattr(row, "get") else 0, 0)
    analyst_target = v43s_float(row.get("Analyst Target") if hasattr(row, "get") else 0, 0)
    vol = v43s_float(row.get("Volume Ratio") if hasattr(row, "get") else 0, 0)
    atr = v43s_float(row.get("ATR %") if hasattr(row, "get") else 0, 0)

    analyst_score = 60
    if "Bullish" in analyst_support:
        analyst_score = 82
    elif "Constructive" in analyst_support:
        analyst_score = 68
    elif "Weak" in analyst_support:
        analyst_score = 45

    news_score = 50
    if "Positive" in news:
        news_score = 75
    elif "Negative" in news:
        news_score = 35

    valuation_score = 72
    if ai and analyst_target:
        gap = ((ai - analyst_target) / analyst_target) * 100
        if gap > 75:
            valuation_score = 48
        elif gap > 50:
            valuation_score = 58
        elif gap > 20:
            valuation_score = 70
        else:
            valuation_score = 82

    risk_score = 75
    if vol and vol < 0.75:
        risk_score -= 8
    if atr >= 5:
        risk_score -= 8
    if upside > 150:
        risk_score -= 5

    raw = (
        quality_score * 0.25 +
        analyst_score * 0.15 +
        valuation_score * 0.20 +
        news_score * 0.10 +
        risk_score * 0.15 +
        existing * 0.15
    )
    adjusted = 50 + (raw - 50) * 0.9
    if "Speculative" in tier:
        adjusted -= 8
    return max(0, min(99, round(adjusted, 1))), tier, quality_score, flags


def v43s_apply_quality_overlay(rows):
    if rows is None:
        return rows
    out = []
    try:
        for row in rows:
            if not hasattr(row, "get"):
                out.append(row)
                continue
            score, tier, quality_score, flags = v43s_rebalanced_score(row)
            row["V43 Score"] = score
            row["Quality Tier"] = tier
            row["Business Quality Score"] = quality_score
            row["Quality Flags"] = ", ".join(flags)
            if "Speculative" in tier:
                row["Setup Rating"] = "⚠️ Speculative High-Upside" if score >= 80 else "⚠️ Speculative"
            elif score >= 92:
                row["Setup Rating"] = "🟢 Elite Quality Setup"
            elif score >= 86:
                row["Setup Rating"] = "🟢 Strong Setup"
            elif score >= 78:
                row["Setup Rating"] = "🟡 Actionable Watch"
            else:
                row["Setup Rating"] = "🟡 Watchlist"
            out.append(row)
        return sorted(out, key=lambda r: v43s_float(r.get("V43 Score") if hasattr(r, "get") else 0, 0), reverse=True)
    except Exception:
        return rows


if __name__ == "__main__":
    main()

# V42.6 changes:
# - paid_client_verdict_first_layout
# - agent_scorecard_condensed
# - earnings_sources_fmp_finnhub_nasdaq_alpha_yahoo
# - source_health_card
# - framework_agents_not_primary_signals

# V42.7 changes:
# - paid customer verdict-first layout in app
# - cleaner agent scorecard and readiness labels
# - command center source transparency
# - detailed legacy content kept lower on page

# V43 changes:
# - Business Quality Agent
# - Quality/Growth/Recovery/Speculative tiering
# - AI Fair Value conservative/base/aggressive target logic
# - Valuation confidence penalty
# - Score distribution overlay
# - Paid-client decision-card layout



# =========================
# V43.1 SCANNER WIRING CLEANUP
# =========================

def v431s_apply_final_score_overlay(rows):
    """
    Applies V43 score into both V43 fields and the legacy Final Conviction field so existing tables stop showing 96/97 compression.
    """
    if rows is None:
        return rows
    try:
        processed = []
        for row in rows:
            if not hasattr(row, "get"):
                processed.append(row)
                continue
            if "v43s_rebalanced_score" in globals():
                score, tier, quality_score, flags = v43s_rebalanced_score(row)
            else:
                score = v43s_float(row.get("Final Conviction"), 0) if "v43s_float" in globals() else 0
                tier, quality_score, flags = "N/A", 0, []
            row["V43 Score"] = score
            row["Final Conviction"] = score
            row["Quality Tier"] = tier
            row["Business Quality Score"] = quality_score
            row["Quality Flags"] = ", ".join(flags) if isinstance(flags, list) else str(flags)
            if "Speculative" in tier:
                row["Setup Rating"] = "⚠️ Speculative High-Upside" if score >= 78 else "⚠️ Speculative"
            elif score >= 90:
                row["Setup Rating"] = "🟢 Elite Quality Setup"
            elif score >= 84:
                row["Setup Rating"] = "🟢 Strong Setup"
            elif score >= 76:
                row["Setup Rating"] = "🟡 Actionable Watch"
            elif score >= 68:
                row["Setup Rating"] = "🟡 Watchlist"
            else:
                row["Setup Rating"] = "⚪ Low Priority"
            processed.append(row)
        return sorted(processed, key=lambda r: float(r.get("V43 Score") or 0), reverse=True)
    except Exception:
        return rows

# V43.1 changes:
# - legacy Final Conviction overwritten with V43 Score after scan overlay
# - V43 fields written into scan rows
# - old 96/97 score compression reduced once scan output uses overlay



# =========================
# V43.2 SCANNER DATA INTELLIGENCE MARKERS
# =========================
def v432s_source_config_status():
    import os
    names = ["FMP_API_KEY", "FINNHUB_API_KEY", "NEWSAPI_KEY", "ALPHA_VANTAGE_API_KEY", "SEC_USER_AGENT", "GITHUB_TOKEN", "GITHUB_REPO_URL"]
    return {n: {"configured": bool((os.getenv(n) or "").strip()), "length": len((os.getenv(n) or "").strip())} for n in names}

# V43.2 changes:
# - app-level NewsAPI/Finnhub/Yahoo/CNBC/MarketWatch news fallback
# - Analyst Intelligence V2 source diagnostics and upgrade/downgrade attempts
# - improved business quality logic: missing P/E lowers confidence, not score collapse
# - data confidence panel
# - source diagnostics panel



# =========================
# V43.2.1 STRICT SCANNER ENVIRONMENT VARIABLE NAMES
# =========================
# Exact Render variable names only. No legacy aliases.
def v432s_source_config_status():
    import os
    names = [
        "APP_PASSWORD",
        "GUEST_PASSWORD",
        "FMP_API_KEY",
        "FINNHUB_API_KEY",
        "NEWSAPI_KEY",
        "ALPHA_VANTAGE_API_KEY",
        "SEC_USER_AGENT",
        "GITHUB_TOKEN",
        "GITHUB_REPO_URL",
        "DATA_DIR",
    ]
    return {
        n: {
            "configured": bool((os.getenv(n) or "").strip()),
            "length": len((os.getenv(n) or "").strip())
        }
        for n in names
    }

# V43.2.1 changes:
# - strict 1:1 Render variable names only
# - removed alias logic for NEWS_API_KEY, FINNHUB_TOKEN, VIEW_PASSWORD, VIEWER_PASSWORD
# - source diagnostics report detected length safely without exposing secrets


# V44.0 scanner marker:
# App adds paid-client intelligence, analyst/quality overlays, and market-news improvements.
def v44s_marker():
    return {"version": "V47.0", "paid_client_intelligence": True}


# V47.0 marker: Advisor-Style Decision Engine with GitHub Actions persistence compatibility.


# V47.0 marker: Institutional Research Completion Engine compatibility.


# V47.0 marker: Research Quality Correction Patch.


# V47.0 marker: Client-Friendly Advisor Language Patch.
