from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping
import math

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
        "top_analyst_name": _text(_first(s,"top_analyst_name","Top Analyst")),
        "top_analyst_rating": _text(_first(s,"top_analyst_rating","Top Analyst Rating")),
        "top_analyst_target": _num(_first(s,"top_analyst_target","Top Analyst Target")),
        "top_analyst_status": _text(_first(s,"top_analyst_status","Top Analyst Status")),
        "recent_rating_change": _text(_first(s,"recent_rating_change","Latest Upgrade/Downgrade")),
    }
    data = {k:v for k,v in data.items() if v not in (None,"")}
    if "top_analyst_name" not in data and data.get("high_target") is not None:
        data["highest_published_target"] = data["high_target"]
        data["label_note"] = "No analyst-accuracy ranking was supplied; this is the highest published target."
    return _section(data, _text(_first(s,"analyst_source","source"),"Current Atlas analyst payload"))

def build_news_section(row):
    s = _sources(row)
    raw = row.get("news") or _first(s,"recent_news","recent_headlines","news_items","articles","headlines") or []
    items = []
    for item in _seq(raw):
        if isinstance(item, Mapping):
            items.append({
                "headline": _text(item.get("headline") or item.get("title")),
                "source": _text(item.get("source") or item.get("publisher")),
                "date": _text(item.get("date") or item.get("published_at")),
                "sentiment": _text(item.get("sentiment")),
                "impact": _num(item.get("impact") or item.get("impact_score")),
                "summary": _text(item.get("summary")),
            })
        elif _text(item):
            items.append({"headline": _text(item)})
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
    data = {
        "political_support_score": _num(_first(s,"political_score","Political Score")),
        "buyers": _num(_first(s,"political_buyers","Political Buyers")),
        "sellers": _num(_first(s,"political_sellers","Political Sellers")),
        "government_contract_exposure": _text(_first(s,"government_contract_exposure","Government Contract Exposure")),
        "regulatory_exposure": _text(_first(s,"regulatory_exposure","Regulatory Exposure")),
        "tariff_exposure": _text(_first(s,"tariff_exposure","Tariff Exposure")),
        "export_control_exposure": _text(_first(s,"export_control_exposure","Export Control Exposure")),
        "transactions": normalized[:20],
    }
    data = {k:v for k,v in data.items() if v not in (None,"",[])}
    return _section(data, _text(_first(s,"political_source","source"),"Current Atlas political payload"))

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
