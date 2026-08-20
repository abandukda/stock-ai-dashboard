"""Stable customer watchlist-intelligence projection over research evidence."""

from __future__ import annotations

from typing import Any, Mapping

from engines.semantic_fields import DATA_UNAVAILABLE, evidence_state
from services.live_market.models import normalize_ticker


def build_watchlist_intelligence(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = normalize_ticker(str(row.get("ticker") or row.get("symbol") or ""))
    fair_value = row.get("atlas_fair_value")
    earnings = row.get("earnings_intelligence") or {}
    market = row.get("market_context") or {}
    news = (row.get("sections") or {}).get("news") or {}
    technical = (row.get("sections") or {}).get("technical") or {}
    freshness = row.get("_evidence_freshness") or row.get("evidence_freshness") or {}
    return {
        "version": "WATCHLIST_INTELLIGENCE_V1",
        "security": {
            "security_id": row.get("security_id") or ticker,
            "ticker": ticker,
            "security_type": row.get("security_type") or row.get("quote_type") or "UNKNOWN",
        },
        "recommendation": row.get("committee_verdict"),
        "opportunity": row.get("opportunity_score"),
        "confidence": row.get("confidence_pct"),
        "atlas_fair_value": {
            "status": row.get("atlas_valuation_status") or evidence_state(fair_value),
            "value": fair_value,
        },
        "wall_street_consensus": row.get("analyst_target_mean"),
        "earnings_intelligence_status": earnings.get("semantic_status") or DATA_UNAVAILABLE,
        "next_earnings_date": row.get("next_earnings_date"),
        "market_regime": market.get("market_regime") or "UNAVAILABLE",
        "company_news": list(news.get("data") or [])[:3],
        "technical_context": technical.get("interpretation"),
        "sma200": row.get("sma200") if row.get("sma200") is not None else (technical.get("data") or {}).get("sma200"),
        "evidence_freshness": dict(freshness) if isinstance(freshness, Mapping) else {},
        "live_extension": None,
        "radar_extension": None,
    }


__all__ = ["build_watchlist_intelligence"]
