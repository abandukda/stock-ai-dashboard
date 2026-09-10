"""Governed, presentation-only market briefing contracts for Home."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Mapping, Sequence

from services.live_market.models import classify_market_session

VERSION = "ATLAS_MARKET_TODAY_V1"
NEWS_VERSION = "ATLAS_MAJOR_MARKET_NEWS_V1"
_TAGS = {
    "FED": ("federal reserve", "fed ", "fomc"),
    "INFLATION": ("inflation", "cpi", "ppi"),
    "RATES": ("treasury yield", "interest rate", "bond yield"),
    "ENERGY": ("oil", "crude", "opec", "energy shock"),
    "GEOPOLITICS": ("war", "geopolitical", "sanction"),
    "EMPLOYMENT": ("jobs report", "payroll", "unemployment"),
    "TRADE_POLICY": ("tariff", "trade policy", "trade war"),
    "REGULATION": ("regulation", "regulator"),
    "SYSTEMIC_RISK": ("bank failure", "liquidity crisis", "systemic"),
    "EARNINGS": ("earnings",),
}
_IMPACT = {
    "FED": "Federal Reserve policy can change financing conditions and equity valuation multiples.",
    "INFLATION": "Inflation data can shift interest-rate expectations and pressure rate-sensitive valuations.",
    "RATES": "Treasury-yield moves affect discount rates, borrowing costs, and equity valuation multiples.",
    "ENERGY": "Oil-price changes can affect inflation, consumer spending, and energy-sector cash flows.",
    "GEOPOLITICS": "Geopolitical risk can raise volatility and disrupt trade, commodities, or supply chains.",
    "EMPLOYMENT": "Labor-market data can change expectations for growth, inflation, and monetary policy.",
    "TRADE_POLICY": "Trade-policy changes can affect costs, demand, and global supply chains.",
    "REGULATION": "Material regulation can change industry costs, competition, or addressable markets.",
    "SYSTEMIC_RISK": "Systemic stress can tighten liquidity and increase risk across broad markets.",
    "EARNINGS": "Broadly influential earnings can move index expectations and sector sentiment.",
}


def normalize_major_market_news(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    output=[]; seen=set()
    for item in records:
        headline=" ".join(str(item.get("headline") or item.get("title") or "").split())
        source=str(item.get("source") or item.get("publisher") or "").strip()
        published=item.get("published_at") or item.get("date")
        evidence_id=item.get("evidence_id")
        identity=re.sub(r"[^a-z0-9]+"," ",headline.lower()).strip()
        if not headline or not source or not published or not evidence_id or identity in seen:
            continue
        if re.search(r"\b(class action|law firm|shareholder alert|investor alert|litigation)\b", identity):
            continue
        tag=next((tag for tag,terms in _TAGS.items() if any(term in headline.lower() for term in terms)),None)
        if not tag or item.get("commercial_display_allowed") is not True:
            continue
        seen.add(identity)
        output.append({"headline":headline,"source":source,"published_at":published,"evidence_id":str(evidence_id),
                       "url":item.get("url"),"relevance":tag,"why_it_matters":_IMPACT[tag],"non_scoring":True})
    return tuple(output[:4])


def build_market_today(tape: Mapping[str, Any] | None, *, news: Sequence[Mapping[str, Any]]=(), now: datetime | None=None) -> dict[str, Any]:
    tape=dict(tape or {}); rows=[]
    for item in tape.get("rows") or ():
        if item.get("status") != "available" or item.get("price") is None:
            continue
        rows.append({key:item.get(key) for key in ("symbol","label","price","point_change","change_pct","direction","as_of","evidence_id")})
    instant=now or datetime.now(timezone.utc)
    session=classify_market_session(instant).value
    session={"REGULAR":"OPEN","OVERNIGHT":"CLOSED"}.get(session,session.replace("_"," "))
    changes=[float(row["change_pct"]) for row in rows if row.get("change_pct") is not None]
    if not changes:
        interpretation="Current governed broad-market readings are not available, so ATLAS is not inferring today's backdrop."
    elif sum(changes)/len(changes) >= .35:
        interpretation="Broad U.S. equity benchmarks are generally higher in the latest governed readings. The move is supportive context, but it does not change any company-level ATLAS rating."
    elif sum(changes)/len(changes) <= -.35:
        interpretation="Broad U.S. equity benchmarks are generally lower in the latest governed readings. Near-term risk appetite is softer, but individual ATLAS ratings remain determined by their own certified evidence."
    else:
        interpretation="Broad U.S. equity benchmarks are mixed or little changed in the latest governed readings. ATLAS continues to prioritize company-specific valuation, quality, and entry evidence."
    return {"version":VERSION,"status":"AVAILABLE" if rows else "DATA_UNAVAILABLE","market_session":session,
            "as_of":tape.get("market_data_as_of"),"source":"TWELVE_DATA","instruments":tuple(rows),
            "interpretation":interpretation,"major_market_news":normalize_major_market_news(news),"non_scoring":True}


__all__=["NEWS_VERSION","VERSION","build_market_today","normalize_major_market_news"]
