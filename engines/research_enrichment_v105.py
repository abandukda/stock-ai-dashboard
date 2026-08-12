from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping
import math
import re

@dataclass(frozen=True)
class ResearchSection:
    status: str
    source: str
    as_of: str
    data: Any
    notes: str = ""

def _now():
    return datetime.now(timezone.utc).isoformat()

def _text(v, d=""):
    if v is None:
        return d
    s = str(v).strip()
    return d if s.lower() in {"", "none", "null", "nan", "n/a", "unknown", "unavailable", "under review"} else s

def _num(v, d=None):
    try:
        if v is None or v == "":
            return d
        x = float(str(v).replace("$","").replace(",","").replace("%","").strip())
        return x if math.isfinite(x) else d
    except Exception:
        return d

def _pct(v, d=None):
    value = _num(v, d)
    if value is None:
        return d
    return value * 100 if abs(value) <= 2 else value

def _map(v):
    return v if isinstance(v, Mapping) else {}

def _seq(v):
    return list(v) if isinstance(v, (list, tuple)) else []

def _sources(row):
    return [x for x in (
        row, _map(row.get("raw")), _map(row.get("Raw")),
        _map(row.get("financials")), _map(row.get("analysts")),
        _map(row.get("earnings")), _map(row.get("political")),
        _map(row.get("ownership")), _map(row.get("technical")),
    ) if x]

def _first(src, *keys):
    for source in src:
        for key in keys:
            if key in source and source.get(key) not in (None, ""):
                return source.get(key)
    return None

def _section(data, source, as_of="", notes=""):
    return asdict(ResearchSection(
        status="available" if data else "unavailable",
        source=source or "Current Atlas scan",
        as_of=as_of or _now(),
        data=data,
        notes=notes,
    ))

def build_financial_section(row):
    s = _sources(row)
    data = {
        "revenue_growth_pct": _pct(_first(s,"revenue_growth_pct","revenue_growth","Revenue Growth %","Revenue Growth","revenueGrowth")),
        "eps_growth_pct": _pct(_first(s,"eps_growth_pct","earnings_growth","EPS Growth %","Earnings Growth","epsGrowth")),
        "gross_margin_pct": _pct(_first(s,"gross_margin_pct","gross_profit_margin","Gross Margin %","Gross Margin","grossMargin")),
        "operating_margin_pct": _pct(_first(s,"operating_margin_pct","operating_profit_margin","Operating Margin %","Operating Margin","operatingMargin")),
        "net_margin_pct": _pct(_first(s,"net_margin_pct","net_profit_margin","Net Margin %","Net Margin","netMargin")),
        "free_cash_flow": _num(_first(s,"free_cash_flow","Free Cash Flow","freeCashFlow")),
        "operating_cash_flow": _num(_first(s,"operating_cash_flow","Operating Cash Flow","operatingCashFlow")),
        "roe_pct": _pct(_first(s,"roe_pct","return_on_equity","ROE","returnOnEquity")),
        "roic_pct": _pct(_first(s,"roic_pct","roic","ROIC","returnOnInvestedCapital")),
        "cash": _num(_first(s,"cash","cash_and_equivalents","Cash","cashAndCashEquivalents")),
        "debt": _num(_first(s,"debt","total_debt","Total Debt","totalDebt")),
        "current_ratio": _num(_first(s,"current_ratio","Current Ratio","currentRatio")),
        "forward_pe": _num(_first(s,"forward_pe","Forward P/E","Forward PE","forwardPE")),
        "peg_ratio": _num(_first(s,"peg_ratio","PEG Ratio","pegRatio")),
        "price_to_sales": _num(_first(s,"price_to_sales","Price/Sales","priceToSales")),
        "ev_ebitda": _num(_first(s,"ev_ebitda","EV/EBITDA","enterpriseValueToEBITDA")),
    }
    data = {k:v for k,v in data.items() if v is not None}
    return _section(data, _text(_first(s,"financial_source","source"),"Current Atlas financial payload"))

def build_analyst_section(row):
    s = _sources(row)
    data = {
        "consensus": _text(_first(s,"analyst_consensus","Analyst Consensus","recommendationKey")),
        "buy_count": _num(_first(s,"analyst_buy_count","Buy Ratings")),
        "hold_count": _num(_first(s,"analyst_hold_count","Hold Ratings")),
        "sell_count": _num(_first(s,"analyst_sell_count","Sell Ratings")),
        "average_target": _num(_first(s,"analyst_target_mean","Analyst Target","targetMeanPrice")),
        "high_target": _num(_first(s,"analyst_target_high","Analyst Target High","targetHighPrice")),
        "low_target": _num(_first(s,"analyst_target_low","Analyst Target Low","targetLowPrice")),
        "analyst_count": _num(_first(s,"analyst_count","Analyst Count","numberOfAnalystOpinions")),
        "recent_rating_change": _text(_first(s,"recent_rating_change","Latest Upgrade/Downgrade")),
        "actions": normalize_analyst_actions(_first(s,"analyst_actions","analyst_ratings","ratings_actions","upgrades_downgrades")),
    }
    data = {k:v for k,v in data.items() if v not in (None,"")}
    if data.get("high_target") is not None:
        data["highest_published_target"] = data["high_target"]
        data["label_note"] = "No analyst-performance ranking was supplied; aggregate high/low targets are not attributed to an individual."
    return _section(data, _text(_first(s,"analyst_source","source"),"Current Atlas analyst payload"))

def normalize_analyst_actions(value):
    actions = []
    for item in _seq(value):
        if not isinstance(item, Mapping):
            continue
        firm = _text(item.get("firm") or item.get("brokerage") or item.get("company"))
        analyst = _text(item.get("analyst") or item.get("analyst_name"))
        date = _text(item.get("date") or item.get("publishedDate") or item.get("gradingDate"))
        current_target = _num(item.get("priceTarget") if item.get("priceTarget") is not None else item.get("current_target"))
        previous_target = _num(item.get("previousPriceTarget") if item.get("previousPriceTarget") is not None else item.get("previous_target"))
        if not (firm or analyst) or not date:
            continue
        change = current_target - previous_target if current_target is not None and previous_target is not None else None
        change_pct = change / abs(previous_target) * 100 if change is not None and previous_target not in (None, 0) else None
        actions.append({
            "analyst_name": analyst or None,
            "firm": firm or None,
            "date": date,
            "action": _text(item.get("action") or item.get("gradingAction")) or None,
            "current_rating": _text(item.get("rating") or item.get("newGrade") or item.get("current_rating")) or None,
            "previous_rating": _text(item.get("previousGrade") or item.get("previous_rating")) or None,
            "current_target": current_target,
            "previous_target": previous_target,
            "target_change": round(change, 2) if change is not None else None,
            "target_change_pct": round(change_pct, 1) if change_pct is not None else None,
        })
    return sorted(actions, key=lambda item: item["date"], reverse=True)


def _entity_tokens(row):
    ticker = _text(row.get("ticker") or row.get("symbol") or row.get("Ticker")).upper()
    company = _text(row.get("company") or row.get("company_name") or row.get("name") or row.get("Company")).lower()
    noise = {"inc", "incorporated", "corp", "corporation", "ltd", "limited", "plc", "company", "holdings", "group"}
    base = re.sub(r"\b(incorporated|corporation|corp|inc|limited|ltd|plc|company|holdings|group)\b.*$", "", company).strip(" ,.-")
    normalized_name = " ".join(re.findall(r"[a-z0-9]+", base))
    collapsed_name = re.sub(r"(?<=\b[a-z])\s+(?=[a-z]\b)", "", normalized_name)
    tokens = [token for token in re.findall(r"[a-z0-9]+", base) if len(token) >= 5 and token not in noise]
    aliases = [name for name in (normalized_name, collapsed_name) if len(name) >= 4]
    return ticker, tokens, aliases


def accepted_company_news(row, value=None):
    raw = value
    if raw is None:
        raw = row.get("news") or row.get("recent_news") or row.get("news_items") or []
    if not _seq(raw):
        nested_sources = _sources(row)
        headline = _text(_first(nested_sources, "latest_news_headline"))
        if headline:
            raw = [{"headline": headline, "source": _first(nested_sources, "latest_news_source"), "date": _first(nested_sources, "latest_news_date"), "sentiment": _first(nested_sources, "latest_news_sentiment"), "provider": _first(nested_sources, "source_news_provider")}]
    ticker, company_tokens, company_aliases = _entity_tokens(row)
    accepted, seen = [], set()
    for item in _seq(raw):
        if not isinstance(item, Mapping):
            continue
        headline = _text(item.get("headline") or item.get("title"))
        publisher = _text(item.get("publisher") or item.get("source"))
        date = _text(item.get("published_at") or item.get("date") or item.get("datetime"))
        if not headline or not publisher or not date:
            continue
        try:
            published = datetime.fromisoformat(date.replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - published.astimezone(timezone.utc)).days
            if age_days > 45 or age_days < -2:
                continue
        except ValueError:
            continue
        text = f"{headline} {_text(item.get('summary'))}".lower()
        explicit_symbols = [str(value).upper() for value in _seq(item.get("symbols") or item.get("tickers"))]
        ticker_match = ticker in explicit_symbols
        normalized_text = " ".join(re.findall(r"[a-z0-9]+", text))
        collapsed_text = re.sub(r"(?<=\b[a-z])\s+(?=[a-z]\b)", "", normalized_text)
        company_match = any(alias in normalized_text or alias in collapsed_text for alias in company_aliases)
        if not company_match and len(company_tokens) >= 2:
            company_match = all(re.search(rf"\b{re.escape(token)}\b", text) for token in company_tokens[:2])
        if not (ticker_match or company_match):
            continue
        fingerprint = re.sub(r"[^a-z0-9]", "", headline.lower())
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        accepted.append({
            "headline": headline, "publisher": publisher, "source": publisher,
            "date": date, "provider": _text(item.get("provider")) or None,
            "url": _text(item.get("url")) or None,
            "sentiment": _text(item.get("sentiment")) or None,
            "summary": _text(item.get("summary")) or None,
            "relevance": "Accepted company/ticker match",
            "classification": _text(item.get("classification")) or "Other Company-Specific",
        })
    return accepted[:10]


def build_news_section(row):
    s = _sources(row)
    raw = row.get("news") or _first(s,"recent_news","recent_headlines","news_items","articles","headlines") or []
    items = accepted_company_news(row, raw)
    return _section(items[:10], _text(_first(s,"news_source","source"),"Current Atlas news payload"))

def build_political_section(row):
    s = _sources(row)
    tx = _seq(row.get("political_transactions") or _first(s,"congressional_trades","political_trades","transactions"))
    normalized = []
    for item in tx:
        if isinstance(item, Mapping):
            normalized.append({
                "politician": _text(item.get("politician") or item.get("name")),
                "party": _text(item.get("party")),
                "chamber": _text(item.get("chamber")),
                "transaction": _text(item.get("transaction") or item.get("type")),
                "date": _text(item.get("date")),
                "value": _text(item.get("value") or item.get("amount")),
            })
    evidence = _seq(_first(s, "policy_evidence", "political_policy_evidence", "government_events"))
    verified = []
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        event = _text(item.get("event") or item.get("headline"))
        date = _text(item.get("date") or item.get("published_at"))
        source = _text(item.get("source") or item.get("publisher"))
        if event and date and source:
            verified.append({
                "event": event, "date": date, "source": source,
                "jurisdiction": _text(item.get("jurisdiction")) or None,
                "category": _text(item.get("category")) or None,
                "impact": _text(item.get("impact")) or None,
                "company_relevance": _text(item.get("company_relevance") or item.get("relevance")) or None,
            })
    data = {
        # The score is retained for transparency, but does not itself create
        # policy evidence or supportive presentation language.
        "political_component_score": _num(_first(s,"political_score","Political Score")),
        "buyers": _num(_first(s,"political_buyers","Political Buyers")),
        "sellers": _num(_first(s,"political_sellers","Political Sellers")),
        "government_contract_exposure": _text(_first(s,"government_contract_exposure","Government Contract Exposure")),
        "regulatory_exposure": _text(_first(s,"regulatory_exposure","Regulatory Exposure")),
        "tariff_exposure": _text(_first(s,"tariff_exposure","Tariff Exposure")),
        "export_control_exposure": _text(_first(s,"export_control_exposure","Export Control Exposure")),
        "transactions": normalized[:20],
        "policy_evidence": verified,
    }
    data = {k:v for k,v in data.items() if v not in (None,"",[])}
    section = _section(data, _text(_first(s,"political_source","source"),"Current Atlas political payload"))
    evidence_backed = bool(normalized or verified or any(data.get(key) for key in (
        "government_contract_exposure", "regulatory_exposure",
        "tariff_exposure", "export_control_exposure",
    )))
    if not evidence_backed:
        section["status"] = "unavailable"
        section["notes"] = "Numeric political component values alone are not company-specific policy evidence."
    return section

def build_earnings_section(row):
    s = _sources(row)
    has_guidance_evidence = bool(_first(s,"source_management_guidance","source_earnings_transcript","guidance_evidence_available"))
    data = {
        "latest_reported_date": _text(_first(s,"latest_earnings_date","Latest Earnings Date")),
        "reported_eps": _num(_first(s,"reported_eps","Reported EPS","epsActual")),
        "estimated_eps": _num(_first(s,"eps_estimate","estimated_eps","Estimated EPS","epsEstimated")),
        "next_earnings_date": _text(_first(s,"next_earnings_date","Next Earnings","Earnings Date","earnings_date")),
        "timing": _text(_first(s,"earnings_timing","Earnings Timing")),
        "eps_surprise_pct": _num(_first(s,"eps_surprise_pct","EPS Surprise %")),
        "revenue_surprise_pct": _num(_first(s,"revenue_surprise_pct","Revenue Surprise %")),
        "reported_revenue": _num(_first(s,"reported_revenue","Reported Revenue","revenueActual")),
        "estimated_revenue": _num(_first(s,"revenue_estimate","estimated_revenue","Estimated Revenue","revenueEstimated")),
        "guidance": _text(_first(s,"management_guidance","earnings_guidance","Guidance")) if has_guidance_evidence else "",
        "management_tone": _text(_first(s,"management_tone","Management Tone")) if has_guidance_evidence else "",
        "transcript_summary": _text(_first(s,"transcript_summary","Latest Earnings Summary")) if has_guidance_evidence else "",
        "important_quote": _text(_first(s,"important_quote","Most Important Quote")),
    }
    data = {k:v for k,v in data.items() if v not in (None,"")}
    return _section(data, _text(_first(s,"earnings_source","source"),"Current Atlas earnings payload"))

def build_ownership_section(row):
    s = _sources(row)
    data = {
        "institutional_ownership_pct": _num(_first(s,"institutional_ownership_pct","Institutional Ownership %")),
        "insider_ownership_pct": _num(_first(s,"insider_ownership_pct","Insider Ownership %")),
        "institutional_change_pct": _num(_first(s,"institutional_change_pct","Institutional Change %")),
        "major_holders": _seq(_first(s,"major_holders","institutional_holders","holders"))[:15],
        "insider_transactions": _seq(_first(s,"insider_transactions","insider_trades"))[:20],
        "institutional_support_score": _num(_first(s,"institutional_score","Institutional Score")),
        "insider_support_score": _num(_first(s,"insider_score","Insider Score")),
        "insider_activity_label": _text(_first(s,"insider_activity_label")),
        "insider_buy_count": _num(_first(s,"insider_buy_count")),
        "insider_sell_count": _num(_first(s,"insider_sell_count")),
    }
    data = {k:v for k,v in data.items() if v not in (None,"",[])}
    return _section(data, _text(_first(s,"ownership_source","source"),"Current Atlas ownership payload"))

def build_technical_section(row):
    s = _sources(row)
    data = {
        "price": _num(_first(s,"current_price","Price")),
        "sma20": _num(_first(s,"sma20","SMA20")),
        "sma50": _num(_first(s,"sma50","SMA50")),
        "sma200": _num(_first(s,"sma200","SMA200")),
        "rsi": _num(_first(s,"rsi","RSI")),
        "atr": _num(_first(s,"atr","ATR")),
        "support": _num(_first(s,"support","Support")),
        "resistance": _num(_first(s,"resistance","Resistance")),
        "relative_strength": _num(_first(s,"relative_strength","Relative Strength")),
        "volume_confirmation": _text(_first(s,"volume_confirmation","Volume Confirmation")),
        "trend": _text(_first(s,"technical_trend","Trend")),
    }
    data = {k:v for k,v in data.items() if v not in (None,"")}
    return _section(data, _text(_first(s,"technical_source","source"),"Current Atlas technical payload"))

def build_enriched_research_report(row):
    return {
        "version":"V105",
        "ticker":_text(row.get("ticker"),"UNKNOWN"),
        "company":_text(row.get("company"),_text(row.get("ticker"),"UNKNOWN")),
        "sector":_text(row.get("sector"),"Unknown"),
        "committee_verdict":_text(row.get("committee_verdict") or row.get("action_code"),"MONITOR"),
        "opportunity_score":_num(row.get("opportunity_score")),
        "confidence_pct":_num(row.get("confidence_pct")),
        "position_size_range":_text(row.get("position_size_range"),"0–2%"),
        "executive_summary":_text(row.get("investment_thesis") or row.get("executive_summary")),
        "positive_drivers":_seq(row.get("positive_drivers")),
        "reasons_to_wait":_seq(row.get("reasons_to_wait")),
        "financials":build_financial_section(row),
        "analysts":build_analyst_section(row),
        "news":build_news_section(row),
        "political":build_political_section(row),
        "earnings":build_earnings_section(row),
        "ownership":build_ownership_section(row),
        "technical":build_technical_section(row),
    }

def validate_enriched_report(report):
    errors=[]
    if report.get("version")!="V105": errors.append("version must be V105")
    if not report.get("ticker"): errors.append("ticker is required")
    for key in ("financials","analysts","news","political","earnings","ownership","technical"):
        section=report.get(key)
        if not isinstance(section,Mapping): errors.append(f"{key} section missing")
        elif any(field not in section for field in ("status","source","as_of","data")):
            errors.append(f"{key} contract incomplete")
    return errors

__all__=["build_enriched_research_report","validate_enriched_report"]
