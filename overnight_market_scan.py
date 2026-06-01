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
import requests
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
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
        "scan_time": now_iso(),
    }


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

                # V40.3: analyst intelligence from Finnhub.
                finnhub_meta = get_finnhub_research(symbol)
                if finnhub_meta:
                    for key, value in finnhub_meta.items():
                        if value not in (None, "", "Unknown"):
                            meta[key] = value

                # V41: insider intelligence from Finnhub.
                insider_meta = get_finnhub_insider_activity(symbol)
                if insider_meta:
                    for key, value in insider_meta.items():
                        if value not in (None, "", "Unknown"):
                            meta[key] = value

                # V40.3: news/catalyst intelligence from NewsAPI.
                news_meta = get_news_research(symbol, meta.get("company_name", symbol))
                if news_meta:
                    for key, value in news_meta.items():
                        if value not in (None, "", "Unknown"):
                            meta[key] = value

                metadata_cache[symbol] = meta

            quote_type = str(meta.get("quote_type", "")).upper()
            if quote_type == "ETF":
                etf_row = score_etf_row(symbol, meta, ind)
                if etf_row:
                    etf_rows.append(etf_row)
                continue

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
        "version": "V41.4",
        "universe_count": len(universe),
        "prescreen_count": len(prescreen_rows),
        "full_scan_count": len(full_rows),
        "recovery_count": len(recovery_rows),
        "etf_count": len(etf_rows),
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
            "version": "V41.4",
            "error": str(exc),
            "data_dir": str(DATA_DIR),
            "github_persisted": False,
        }
        write_json(STATE_FILE, error_state)
        print(json.dumps(error_state, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
