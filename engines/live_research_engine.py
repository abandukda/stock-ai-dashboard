from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

import pandas as pd
import requests
import yfinance as yf

from services.research_cache import load_cached_research, save_cached_research
from engines.decision_intelligence_engine import evidence_pack, primary_risk, decision

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()

POLICY_TERMS = {
    "government contract": "Government contract",
    "federal contract": "Federal contract",
    "defense contract": "Defense contract",
    "chips act": "CHIPS Act support",
    "subsidy": "Government subsidy",
    "tax credit": "Tax credit",
    "grant": "Government grant",
    "regulatory approval": "Regulatory approval",
    "public funding": "Public funding",
    "export restriction": "Export-control development",
    "tariff": "Tariff development",
}


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def _pct(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100 if -2 <= value <= 2 else value


def _request_json(url: str, params: Dict[str, Any], timeout: int = 10) -> Any:
    try:
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None




def _normalize_history_frame(hist: Any, ticker: str) -> pd.DataFrame:
    """Return a single-ticker OHLCV frame with flat canonical column names.

    yfinance can return flat columns, ticker-first MultiIndex columns, or
    price-field-first MultiIndex columns depending on version and endpoint.
    """
    if hist is None or not isinstance(hist, pd.DataFrame) or hist.empty:
        return pd.DataFrame()

    df = hist.copy()
    symbol = str(ticker or "").upper().strip()

    if isinstance(df.columns, pd.MultiIndex):
        # Prefer an exact ticker slice when the symbol is one of the levels.
        sliced = None
        for level in range(df.columns.nlevels):
            values = {str(v).upper() for v in df.columns.get_level_values(level)}
            if symbol and symbol in values:
                try:
                    sliced = df.xs(symbol, axis=1, level=level, drop_level=True)
                    break
                except Exception:
                    pass
        if isinstance(sliced, pd.DataFrame) and not sliced.empty:
            df = sliced
        else:
            # Otherwise retain the level that contains OHLCV field names.
            field_names = {"OPEN", "HIGH", "LOW", "CLOSE", "ADJ CLOSE", "VOLUME"}
            best_level = 0
            best_hits = -1
            for level in range(df.columns.nlevels):
                vals = [str(v).upper() for v in df.columns.get_level_values(level)]
                hits = sum(v in field_names for v in vals)
                if hits > best_hits:
                    best_level, best_hits = level, hits
            df.columns = [str(v) for v in df.columns.get_level_values(best_level)]

    # Flatten any residual tuple columns and normalize common aliases.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [next((str(part) for part in col if str(part).upper() in {"OPEN","HIGH","LOW","CLOSE","ADJ CLOSE","VOLUME"}), str(col[-1])) for col in df.columns]
    else:
        df.columns = [str(c) for c in df.columns]

    aliases = {}
    for col in df.columns:
        key = col.strip().lower().replace("_", " ")
        if key == "open": aliases[col] = "Open"
        elif key == "high": aliases[col] = "High"
        elif key == "low": aliases[col] = "Low"
        elif key in {"close", "closing price", "last"}: aliases[col] = "Close"
        elif key in {"adj close", "adjusted close"}: aliases[col] = "Adj Close"
        elif key == "volume": aliases[col] = "Volume"
    df = df.rename(columns=aliases)

    # When auto_adjust=True, Close is preferred. If only Adj Close exists, use it.
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df["Close"] = df["Adj Close"]

    # Duplicate canonical columns can occur after flattening; keep the first.
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def _download_history(ticker: str) -> pd.DataFrame:
    """Fetch history with a second yfinance path as a graceful fallback."""
    errors = []
    try:
        raw = yf.download(
            ticker, period="5y", interval="1d", auto_adjust=True,
            progress=False, threads=False, group_by="column"
        )
        normalized = _normalize_history_frame(raw, ticker)
        if not normalized.empty and "Close" in normalized.columns:
            return normalized
    except Exception as exc:
        errors.append(str(exc))

    try:
        raw = yf.Ticker(ticker).history(period="5y", interval="1d", auto_adjust=True)
        normalized = _normalize_history_frame(raw, ticker)
        if not normalized.empty and "Close" in normalized.columns:
            return normalized
    except Exception as exc:
        errors.append(str(exc))

    return pd.DataFrame()


def _latest_news(ticker: str, company: str) -> Dict[str, Any]:
    if not NEWSAPI_KEY:
        return {}
    query = company if company and company.upper() != ticker else ticker
    data = _request_json(
        "https://newsapi.org/v2/everything",
        {
            "q": f'"{query}" OR {ticker}',
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 8,
            "apiKey": NEWSAPI_KEY,
        },
    )
    articles = data.get("articles", []) if isinstance(data, dict) else []
    cleaned = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        if not title:
            continue
        description = str(article.get("description") or "").strip()
        if not _company_news_relevant(title, description, ticker, company):
            continue
        source = str((article.get("source") or {}).get("name") or "").strip()
        published = str(article.get("publishedAt") or "").strip()
        text = f"{title} {article.get('description') or ''}".lower()
        positive = sum(term in text for term in ("beat", "upgrade", "contract", "approval", "record", "growth", "partnership", "raised guidance"))
        negative = sum(term in text for term in ("miss", "downgrade", "lawsuit", "probe", "cuts guidance", "weak demand", "recall"))
        sentiment = "Positive" if positive > negative else "Negative" if negative > positive else "Neutral"
        cleaned.append({"title": title, "source": source, "published_at": published, "sentiment": sentiment})
    if not cleaned:
        return {}
    top = cleaned[0]
    policy = []
    combined = " ".join(item["title"].lower() for item in cleaned[:5])
    for needle, label in POLICY_TERMS.items():
        if needle in combined:
            policy.append(label)
    return {
        "latest_news_headline": top["title"],
        "latest_news_date": top["published_at"],
        "latest_news_source": top["source"],
        "latest_news_sentiment": top["sentiment"],
        "recent_headlines": cleaned[:5],
        "political_support": policy[0] if policy else "",
        "political_support_summary": f"Recent reporting identifies {policy[0].lower()} relevant to the company." if policy else "",
    }


def _company_news_relevant(title: str, description: str, ticker: str, company: str) -> bool:
    """Reject ticker-substring collisions such as ELF appearing in filesystem."""
    text = f"{title or ''} {description or ''}".lower()
    ticker = str(ticker or "").strip().upper()
    company = str(company or "").strip()
    aliases = []
    if company and company.upper() != ticker:
        aliases.append(company)
        aliases.append(re.sub(
            r"\b(inc\.?|corporation|corp\.?|ltd\.?|limited|plc|class a|common stock)\b",
            "",
            company,
            flags=re.I,
        ).strip(" ,.-"))
    aliases.extend({
        "ELF": ["e.l.f. beauty", "e.l.f. cosmetics", "elf beauty"],
        "CRM": ["salesforce"],
        "NVDA": ["nvidia"],
    }.get(ticker, []))
    if any(alias and alias.lower() in text for alias in aliases):
        return True
    return bool(re.search(
        rf"(?:\$|NASDAQ:\s*|NYSE:\s*|ticker\s+)" + re.escape(ticker) + r"\b",
        text,
        re.I,
    ))


def _analyst_context(ticker: str) -> Dict[str, Any]:
    if not FINNHUB_API_KEY:
        return {}
    target = _request_json(
        "https://finnhub.io/api/v1/stock/price-target",
        {"symbol": ticker, "token": FINNHUB_API_KEY},
    )
    if not isinstance(target, dict):
        return {}
    return {
        "Analyst Target": _num(target.get("targetMean")),
        "analyst_target_mean": _num(target.get("targetMean")),
        "analyst_target_high": _num(target.get("targetHigh")),
        "analyst_target_low": _num(target.get("targetLow")),
    }


def _fair_value(price: float, info: Dict[str, Any]) -> Dict[str, Any]:
    forward_pe = _num(info.get("forwardPE"))
    trailing_eps = _num(info.get("trailingEps"))
    forward_eps = _num(info.get("forwardEps"))
    revenue_growth = _pct(_num(info.get("revenueGrowth")))
    earnings_growth = _pct(_num(info.get("earningsGrowth")))
    op_margin = _pct(_num(info.get("operatingMargins")))
    analyst_target = _num(info.get("targetMeanPrice"))

    estimates = []
    methods = []
    eps = forward_eps or (price / forward_pe if forward_pe and forward_pe > 0 else trailing_eps)
    if eps and eps > 0:
        growth = earnings_growth if earnings_growth is not None else revenue_growth
        growth = max(-5.0, min(35.0, growth if growth is not None else 8.0))
        margin_bonus = 2.0 if op_margin is not None and op_margin >= 25 else 0.0
        justified_pe = max(12.0, min(38.0, 16.0 + 0.45 * growth + margin_bonus))
        estimates.append(eps * justified_pe)
        methods.append("growth-adjusted earnings multiple")
    if analyst_target and analyst_target > 0:
        estimates.append(analyst_target)
        methods.append("analyst-consensus cross-check")

    if not estimates:
        return {"Atlas Fair Value": None, "atlas_fair_value": None, "fair_value_status": "Insufficient valuation evidence"}

    base = sum(estimates) / len(estimates)
    upside = ((base / price) - 1) * 100 if price else None
    if base <= 0 or upside is None or upside < -60 or upside > 100 or 29.65 <= upside <= 30.35:
        return {"Atlas Fair Value": None, "atlas_fair_value": None, "fair_value_status": "Valuation requires review"}

    confidence = 58 + (12 if len(estimates) >= 2 else 0) + (8 if revenue_growth is not None else 0) + (8 if earnings_growth is not None else 0)
    return {
        "Atlas Fair Value": round(base, 2),
        "atlas_fair_value": round(base, 2),
        "fair_value_method": " + ".join(methods),
        "fair_value_confidence": min(confidence, 90),
        "fair_value_bear": round(base * 0.85, 2),
        "fair_value_bull": round(base * 1.15, 2),
        "expected_upside_pct": round(upside, 1),
        "Expected Return": round(upside, 1),
    }


def build_live_research(ticker: str, force_refresh: bool = False, cache_ttl_seconds: int = 900) -> Dict[str, Any]:
    symbol = ticker.upper().strip()
    if not symbol:
        return {"error": "Ticker is required"}
    if not force_refresh:
        cached = load_cached_research(symbol, cache_ttl_seconds)
        if cached:
            cached["research_source"] = "cache"
            return cached

    try:
        tk = yf.Ticker(symbol)
        try:
            info = tk.get_info() or {}
        except Exception:
            info = {}
        hist = _download_history(symbol)
    except Exception:
        info = {}
        hist = pd.DataFrame()

    if hist.empty or "Close" not in hist.columns:
        return {
            "error": "Live price history is temporarily unavailable from the market-data provider.",
            "error_code": "PRICE_HISTORY_UNAVAILABLE",
            "Ticker": symbol,
        }

    hist = hist.dropna(subset=["Close"]).copy()
    if hist.empty:
        return {
            "error": "The market-data provider returned no usable closing prices.",
            "error_code": "NO_USABLE_CLOSE",
            "Ticker": symbol,
        }
    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if close.empty:
        return {
            "error": "The market-data provider returned no usable closing prices.",
            "error_code": "NO_USABLE_CLOSE",
            "Ticker": symbol,
        }
    high = pd.to_numeric(hist["High"], errors="coerce") if "High" in hist.columns else close.reindex(hist.index)
    low = pd.to_numeric(hist["Low"], errors="coerce") if "Low" in hist.columns else close.reindex(hist.index)
    volume = pd.to_numeric(hist["Volume"], errors="coerce").fillna(0.0) if "Volume" in hist.columns else pd.Series(index=hist.index, data=0.0)
    price = float(close.iloc[-1])

    def sma(days: int) -> float:
        return float(close.rolling(days).mean().iloc[-1]) if len(close) >= days else price

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else 50.0
    avg_vol = float(volume.tail(20).mean()) if len(volume) else 0.0
    volume_ratio = float(volume.iloc[-1]) / avg_vol if avg_vol else 1.0
    tr = pd.concat([(high-low).abs(), (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(tr.mean())

    company = str(info.get("longName") or info.get("shortName") or symbol)
    row: Dict[str, Any] = {
        "Ticker": symbol,
        "symbol": symbol,
        "Company": company,
        "company_name": company,
        "Price": round(price, 2),
        "price": round(price, 2),
        "Sector": info.get("sector") or "Unknown",
        "Industry": info.get("industry") or "Unknown",
        "Market Cap": _num(info.get("marketCap")),
        "SMA 20": round(sma(20), 2),
        "SMA 50": round(sma(50), 2),
        "SMA 200": round(sma(200), 2),
        "RSI": round(rsi, 1),
        "Volume Ratio": round(volume_ratio, 2),
        "ATR %": round((atr / price) * 100, 2) if price else None,
        "Revenue Growth": _pct(_num(info.get("revenueGrowth"))),
        "Earnings Growth": _pct(_num(info.get("earningsGrowth"))),
        "Forward PE": _num(info.get("forwardPE")),
        "Operating Margin": _pct(_num(info.get("operatingMargins"))),
        "Free Cash Flow": _num(info.get("freeCashflow")),
        "Debt to Equity": _num(info.get("debtToEquity")),
        "Current Ratio": _num(info.get("currentRatio")),
        "Analyst Target": _num(info.get("targetMeanPrice")),
        "analyst_target_mean": _num(info.get("targetMeanPrice")),
        "Analyst Count": _num(info.get("numberOfAnalystOpinions")),
        "research_refreshed_at": datetime.now(timezone.utc).isoformat(),
        "research_source": "live",
        "data_freshness": {"price": "live request", "fundamentals": "latest provider snapshot", "news": "live request if configured"},
    }
    row.update(_analyst_context(symbol))
    row.update(_fair_value(price, info))
    row.update(_latest_news(symbol, company))

    reasons = []
    rev = row.get("Revenue Growth")
    margin = row.get("Operating Margin")
    fcf = row.get("Free Cash Flow")
    if rev is not None and rev > 8:
        reasons.append(f"Revenue growth is {rev:.1f}%, supporting a durable growth thesis.")
    if margin is not None and margin > 20:
        reasons.append(f"Operating margin is {margin:.1f}%, indicating strong business economics.")
    if fcf is not None and fcf > 0:
        reasons.append(f"Free cash flow is positive at ${fcf/1_000_000_000:.1f}B." if abs(fcf) >= 1_000_000_000 else "Free cash flow is positive.")
    if row.get("latest_news_sentiment") == "Positive" and row.get("latest_news_headline"):
        reasons.append(f"Recent catalyst: {row['latest_news_headline']}")
    if row.get("political_support_summary"):
        reasons.append(row["political_support_summary"])
    row["why_atlas_likes_it"] = reasons[:5]

    risk_candidates = []
    if row.get("Debt to Equity") and row["Debt to Equity"] > 150:
        risk_candidates.append((90, "Leverage is elevated and could reduce financial flexibility."))
    if row.get("Forward PE") and row["Forward PE"] > 45:
        risk_candidates.append((80, "Valuation is demanding, increasing sensitivity to execution misses."))
    if row.get("RSI") and row["RSI"] > 72:
        risk_candidates.append((65, "Shares are technically extended and vulnerable to a pullback."))
    if row.get("latest_news_sentiment") == "Negative":
        risk_candidates.append((85, f"Recent negative news flow: {row.get('latest_news_headline', '')}"))
    risk_candidates.append((40, "Execution must remain strong enough to support current expectations."))
    row["primary_risk"] = max(risk_candidates, key=lambda x: x[0])[1]

    completeness = sum(bool(row.get(key)) for key in ("price", "Revenue Growth", "Operating Margin", "atlas_fair_value", "latest_news_headline", "analyst_target_mean"))
    row["research_confidence"] = round(50 + completeness / 6 * 45)
    save_cached_research(symbol, row)
    return row

# ============================================================
# V81.0 PAID-CLIENT DATA COMPLETENESS OVERRIDES
# ============================================================

def _statement_value(frame: Any, labels: Iterable[str]) -> Optional[float]:
    try:
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            return None
        for label in labels:
            if label in frame.index:
                values = pd.to_numeric(frame.loc[label], errors="coerce").dropna()
                if not values.empty:
                    return _num(values.iloc[0])
    except Exception:
        pass
    return None


def _growth_from_statement(frame: Any, labels: Iterable[str]) -> Optional[float]:
    try:
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            return None
        for label in labels:
            if label in frame.index:
                values = pd.to_numeric(frame.loc[label], errors="coerce").dropna()
                if len(values) >= 2 and values.iloc[1] not in (0, None):
                    return ((float(values.iloc[0]) / float(values.iloc[1])) - 1) * 100
    except Exception:
        pass
    return None


def _fundamental_fallbacks(tk: Any, info: Dict[str, Any]) -> Dict[str, Any]:
    try:
        income = tk.quarterly_income_stmt
    except Exception:
        income = pd.DataFrame()
    try:
        cashflow = tk.quarterly_cashflow
    except Exception:
        cashflow = pd.DataFrame()
    try:
        balance = tk.quarterly_balance_sheet
    except Exception:
        balance = pd.DataFrame()

    revenue = _statement_value(income, ["Total Revenue", "Operating Revenue"])
    gross_profit = _statement_value(income, ["Gross Profit"])
    operating_income = _statement_value(income, ["Operating Income"])
    net_income = _statement_value(income, ["Net Income", "Net Income Common Stockholders"])
    operating_cash = _statement_value(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    capex = _statement_value(cashflow, ["Capital Expenditure", "Capital Expenditures"])
    free_cash = _statement_value(cashflow, ["Free Cash Flow"])
    if free_cash is None and operating_cash is not None and capex is not None:
        free_cash = operating_cash + capex if capex < 0 else operating_cash - capex
    cash = _statement_value(balance, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents", "Cash"])
    debt = _statement_value(balance, ["Total Debt"])
    current_assets = _statement_value(balance, ["Current Assets", "Total Current Assets"])
    current_liabilities = _statement_value(balance, ["Current Liabilities", "Total Current Liabilities"])

    revenue_growth = _pct(_num(info.get("revenueGrowth")))
    if revenue_growth is None:
        revenue_growth = _growth_from_statement(income, ["Total Revenue", "Operating Revenue"])
    earnings_growth = _pct(_num(info.get("earningsGrowth")))
    if earnings_growth is None:
        earnings_growth = _growth_from_statement(income, ["Net Income", "Net Income Common Stockholders"])

    gross_margin = _pct(_num(info.get("grossMargins")))
    if gross_margin is None and revenue and gross_profit is not None:
        gross_margin = gross_profit / revenue * 100
    op_margin = _pct(_num(info.get("operatingMargins")))
    if op_margin is None and revenue and operating_income is not None:
        op_margin = operating_income / revenue * 100
    net_margin = _pct(_num(info.get("profitMargins")))
    if net_margin is None and revenue and net_income is not None:
        net_margin = net_income / revenue * 100
    current_ratio = _num(info.get("currentRatio"))
    if current_ratio is None and current_assets is not None and current_liabilities:
        current_ratio = current_assets / current_liabilities

    return {
        "Revenue Growth": revenue_growth,
        "Earnings Growth": earnings_growth,
        "Gross Margin": gross_margin,
        "Operating Margin": op_margin,
        "Net Margin": net_margin,
        "Free Cash Flow": _num(info.get("freeCashflow"), free_cash),
        "Operating Cash Flow": _num(info.get("operatingCashflow"), operating_cash),
        "Cash": _num(info.get("totalCash"), cash),
        "Total Debt": _num(info.get("totalDebt"), debt),
        "Current Ratio": current_ratio,
        "Debt to Equity": _num(info.get("debtToEquity")),
        "Forward PE": _num(info.get("forwardPE")),
        "Trailing PE": _num(info.get("trailingPE")),
        "Price to Book": _num(info.get("priceToBook")),
        "ROE": _pct(_num(info.get("returnOnEquity"))),
        "ROA": _pct(_num(info.get("returnOnAssets"))),
        "institutional_ownership_pct": _pct(_num(info.get("heldPercentInstitutions"))),
        "insider_ownership_pct": _pct(_num(info.get("heldPercentInsiders"))),
    }


def _expanded_analyst_context(ticker: str, info: Dict[str, Any], tk: Any) -> Dict[str, Any]:
    result = _analyst_context(ticker)
    result.setdefault("analyst_target_mean", _num(info.get("targetMeanPrice")))
    result.setdefault("analyst_target_high", _num(info.get("targetHighPrice")))
    result.setdefault("analyst_target_low", _num(info.get("targetLowPrice")))
    result["analyst_count"] = _num(info.get("numberOfAnalystOpinions"))
    result["analyst_target_median"] = _num(info.get("targetMedianPrice"))
    result["Analyst Count"] = _num(info.get("numberOfAnalystOpinions"))
    result["analyst_recommendation"] = info.get("recommendationKey") or info.get("recommendationMean")
    try:
        recommendations = tk.recommendations_summary
        if isinstance(recommendations, pd.DataFrame) and not recommendations.empty:
            latest = recommendations.iloc[0].to_dict()
            result["analyst_recommendation_counts"] = {
                str(k): int(v) for k, v in latest.items() if _num(v) is not None and str(k).lower() != "period"
            }
    except Exception:
        pass
    return result


def _earnings_context(tk: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    try:
        calendar = tk.calendar
        if isinstance(calendar, dict):
            earnings_date = calendar.get("Earnings Date") or calendar.get("EarningsDate")
            if isinstance(earnings_date, (list, tuple)) and earnings_date:
                earnings_date = earnings_date[0]
            if earnings_date:
                result["next_earnings_date"] = str(earnings_date)
            result["earnings_eps_estimate"] = _num(calendar.get("Earnings Average"))
            result["earnings_revenue_estimate"] = _num(calendar.get("Revenue Average"))
    except Exception:
        pass
    try:
        dates = tk.get_earnings_dates(limit=8)
        if isinstance(dates, pd.DataFrame) and not dates.empty:
            now = pd.Timestamp.now(tz="UTC")
            idx = pd.to_datetime(dates.index, utc=True, errors="coerce")
            past = dates.loc[idx <= now]
            future = dates.loc[idx > now]
            history = []
            for date_index, earnings_row in past.head(8).iterrows():
                history.append({
                    "period": str(date_index),
                    "eps_actual": _num(earnings_row.get("Reported EPS")),
                    "eps_estimate": _num(earnings_row.get("EPS Estimate")),
                    "eps_surprise_pct": _num(earnings_row.get("Surprise(%)")),
                })
            if history:
                result["earnings_history"] = history
            if not future.empty and not result.get("next_earnings_date"):
                result["next_earnings_date"] = str(future.index[0])
            if not past.empty:
                latest = past.iloc[0]
                result["latest_earnings_date"] = str(past.index[0])
                result["reported_eps"] = _num(latest.get("Reported EPS"))
                result["eps_estimate"] = _num(latest.get("EPS Estimate"))
                surprise = _num(latest.get("Surprise(%)"))
                result["eps_surprise_pct"] = surprise
                if result["reported_eps"] is not None and result["eps_estimate"] is not None:
                    result["earnings_ai_summary"] = (
                        f"The latest reported EPS was {result['reported_eps']:.2f} versus a consensus estimate of "
                        f"{result['eps_estimate']:.2f}. The reported surprise was "
                        f"{surprise:+.1f}%." if surprise is not None else
                        f"The latest reported EPS was {result['reported_eps']:.2f} versus a consensus estimate of {result['eps_estimate']:.2f}."
                    )
    except Exception:
        pass
    result.setdefault("transcript_status", "Transcript not connected")
    result.setdefault("guidance_status", "Guidance summary requires transcript or structured earnings feed")
    return result


def _fair_value_complete(price: float, info: Dict[str, Any], fundamentals: Dict[str, Any], analyst: Dict[str, Any]) -> Dict[str, Any]:
    forward_eps = _num(info.get("forwardEps"))
    trailing_eps = _num(info.get("trailingEps"))
    forward_pe = _num(fundamentals.get("Forward PE"))
    revenue_growth = _pct(fundamentals.get("Revenue Growth"))
    earnings_growth = _pct(fundamentals.get("Earnings Growth"))
    op_margin = _pct(fundamentals.get("Operating Margin"))
    analyst_mean = _num(analyst.get("analyst_target_mean"))
    analyst_low = _num(analyst.get("analyst_target_low"))
    analyst_high = _num(analyst.get("analyst_target_high"))

    estimates = []
    methods = []
    eps = forward_eps or trailing_eps or (price / forward_pe if forward_pe and forward_pe > 0 else None)
    if eps and eps > 0:
        growth = earnings_growth if earnings_growth is not None else revenue_growth
        growth = max(-5.0, min(30.0, growth if growth is not None else 6.0))
        justified_pe = max(11.0, min(36.0, 15.0 + 0.42 * growth + (2.0 if op_margin and op_margin >= 25 else 0.0)))
        estimates.append(eps * justified_pe)
        methods.append("growth-adjusted earnings")
    if analyst_mean and analyst_mean > 0:
        # Use a conservative haircut so Atlas remains independent from Wall Street.
        estimates.append(price * 0.30 + analyst_mean * 0.70)
        methods.append("discounted analyst cross-check")
    if analyst_low and analyst_high and analyst_high >= analyst_low > 0:
        estimates.append((analyst_low + analyst_high) / 2)
        methods.append("analyst range midpoint")

    if not estimates:
        return {
            "Atlas Fair Value": None,
            "atlas_fair_value": None,
            "fair_value_status": "Insufficient valuation evidence",
        }

    base = sum(estimates) / len(estimates)
    # Avoid implausible targets in the paid-client card.
    base = max(price * 0.55, min(price * 1.75, base))
    upside = (base / price - 1) * 100 if price else 0.0
    dispersion = 0.15 if len(estimates) >= 2 else 0.22
    confidence = min(92, 55 + len(estimates) * 10 + (8 if revenue_growth is not None else 0) + (8 if earnings_growth is not None else 0))
    return {
        "Atlas Fair Value": round(base, 2),
        "atlas_fair_value": round(base, 2),
        "fair_value_method": " + ".join(methods),
        "fair_value_status": "Modeled",
        "fair_value_confidence": confidence,
        "fair_value_bear": round(base * (1 - dispersion), 2),
        "fair_value_base": round(base, 2),
        "fair_value_bull": round(base * (1 + dispersion), 2),
        "ai_bear_target": round(base * (1 - dispersion), 2),
        "ai_base_target": round(base, 2),
        "ai_bull_target": round(base * (1 + dispersion), 2),
        "expected_upside_pct": round(upside, 1),
        "expected_return_pct": round(upside, 1),
        "Expected Return": round(upside, 1),
    }


_build_live_research_v806 = build_live_research


def build_live_research(ticker: str, force_refresh: bool = False, cache_ttl_seconds: int = 900) -> Dict[str, Any]:
    symbol = str(ticker or "").upper().strip()
    if not symbol:
        return {"error": "Ticker is required"}
    if not force_refresh:
        cached = load_cached_research(symbol, cache_ttl_seconds)
        if cached:
            cached["research_source"] = "cache"
            return cached

    tk = yf.Ticker(symbol)
    try:
        info = tk.get_info() or {}
    except Exception:
        info = {}
    hist = _download_history(symbol)
    if hist.empty or "Close" not in hist.columns:
        return {"error": "Live market data is temporarily unavailable.", "error_code": "PRICE_HISTORY_UNAVAILABLE", "Ticker": symbol}
    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if close.empty:
        return {"error": "Live market data returned no usable closing prices.", "error_code": "NO_USABLE_CLOSE", "Ticker": symbol}

    price = float(close.iloc[-1])
    high = pd.to_numeric(hist["High"], errors="coerce") if "High" in hist.columns else close.reindex(hist.index)
    low = pd.to_numeric(hist["Low"], errors="coerce") if "Low" in hist.columns else close.reindex(hist.index)
    volume = pd.to_numeric(hist["Volume"], errors="coerce").fillna(0.0) if "Volume" in hist.columns else pd.Series(index=hist.index, data=0.0)

    def sma(days: int) -> float:
        return float(close.rolling(days).mean().iloc[-1]) if len(close) >= days else price

    delta = close.diff(); gain = delta.clip(lower=0).rolling(14).mean(); loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA); rsi_series = 100 - 100 / (1 + rs)
    rsi = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else 50.0
    avg_vol = float(volume.tail(20).mean()) if len(volume) else 0.0
    volume_ratio = float(volume.iloc[-1]) / avg_vol if avg_vol else 1.0
    tr = pd.concat([(high-low).abs(), (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().dropna().iloc[-1]) if not tr.rolling(14).mean().dropna().empty else float(tr.mean())

    company = str(info.get("longName") or info.get("shortName") or symbol)
    fundamentals = _fundamental_fallbacks(tk, info)
    analyst = _expanded_analyst_context(symbol, info, tk)
    earnings = _earnings_context(tk)
    valuation = _fair_value_complete(price, info, fundamentals, analyst)

    row: Dict[str, Any] = {
        "Ticker": symbol, "symbol": symbol, "Company": company, "company_name": company,
        "Price": round(price, 2), "price": round(price, 2),
        "Sector": info.get("sector") or "Unknown", "Industry": info.get("industry") or "Unknown",
        "Market Cap": _num(info.get("marketCap")),
        "SMA 20": round(sma(20), 2), "SMA 50": round(sma(50), 2), "SMA 200": round(sma(200), 2),
        "RSI": round(rsi, 1), "Volume Ratio": round(volume_ratio, 2),
        "ATR %": round((atr / price) * 100, 2) if price else None,
        "research_refreshed_at": datetime.now(timezone.utc).isoformat(),
        "research_source": "live", "data_freshness": {"price": "live request", "fundamentals": "latest available statements", "analysts": "latest provider snapshot", "earnings": "latest available calendar/history"},
    }
    row.update(fundamentals); row.update(analyst); row.update(earnings); row.update(valuation); row.update(_latest_news(symbol, company))

    reasons = []
    if row.get("Revenue Growth") is not None and row["Revenue Growth"] > 8: reasons.append(f"Revenue growth is {row['Revenue Growth']:.1f}%.")
    if row.get("Operating Margin") is not None and row["Operating Margin"] > 15: reasons.append(f"Operating margin is {row['Operating Margin']:.1f}%.")
    if row.get("Free Cash Flow") is not None and row["Free Cash Flow"] > 0: reasons.append("Free cash flow is positive.")
    if row.get("eps_surprise_pct") is not None: reasons.append(f"Latest EPS surprise was {row['eps_surprise_pct']:+.1f}%.")
    if row.get("latest_news_headline"): reasons.append(f"Recent catalyst: {row['latest_news_headline']}")
    row["why_atlas_likes_it"] = evidence_pack(row, 7)
    row["primary_risk"] = primary_risk(row)
    decision_pack = decision(row)
    row["Recommendation"] = decision_pack["label"]
    row["decision_action"] = decision_pack["label"]
    row["decision_guidance"] = decision_pack["action"]
    row["investment_thesis"] = " ".join(row["why_atlas_likes_it"][:5])

    critical = ["price", "Revenue Growth", "Operating Margin", "Free Cash Flow", "atlas_fair_value", "analyst_target_mean", "next_earnings_date"]
    available = sum(row.get(k) not in (None, "", "Unavailable") for k in critical)
    row["research_confidence"] = round(45 + available / len(critical) * 50)
    row["coverage_status"] = {k: row.get(k) not in (None, "", "Unavailable") for k in critical}
    save_cached_research(symbol, row)
    return row
