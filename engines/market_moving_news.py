"""Deterministic contract for market-moving news, separate from company news."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE
from engines.news_link_integrity import normalize_news_link


_HIGH = ("federal reserve", "fed ", "inflation", "employment", "jobs report", "geopolitical", "war", "sanction", "oil shock", "rate decision")
_MEDIUM = ("rates", "treasury", "regulation", "tariff", "commodity", "mega-cap", "index", "sector")


def build_market_moving_news(items: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    accepted = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        headline = str(item.get("headline") or "").strip()
        source, timestamp, url = item.get("source"), item.get("timestamp") or item.get("published_at"), item.get("url")
        affected = item.get("affected_markets") or item.get("affected_sectors") or item.get("affected_tickers") or []
        if not headline or not source or not timestamp or not str(url or "").startswith("http") or not affected:
            continue
        lowered = headline.lower()
        impact = "HIGH" if any(term in lowered for term in _HIGH) else "MEDIUM" if any(term in lowered for term in _MEDIUM) else "LOW"
        if impact == "LOW" and not item.get("broad_market_relevance"):
            continue
        direction = str(item.get("direction") or "UNCLEAR").upper()
        if direction not in {"POSITIVE", "NEGATIVE", "MIXED", "UNCLEAR"}:
            direction = "UNCLEAR"
        link = normalize_news_link(item, publisher_name=str(source))
        accepted.append({
            "headline": headline,
            "source": source,
            "timestamp": timestamp,
            "url": link["article_url"],
            "publisher_name": link["publisher_name"],
            "publisher_domain": link["publisher_domain"],
            "article_url": link["article_url"],
            "article_url_status": link["article_url_status"],
            "article_url_limitation": link["article_url_limitation"],
            "impact": impact,
            "direction": direction,
            "affected": list(affected) if isinstance(affected, (list, tuple, set)) else [str(affected)],
            "why_it_matters": item.get("why_it_matters") or "This verified event may affect broad-market or sector risk pricing.",
        })
    accepted.sort(key=lambda item: ({"HIGH": 3, "MEDIUM": 2, "LOW": 1}[item["impact"]], str(item["timestamp"])), reverse=True)
    return {
        "version": "MARKET_MOVING_NEWS_V1",
        "semantic_status": AVAILABLE if accepted else DATA_UNAVAILABLE,
        "status_detail": "Verified broad-market stories only." if accepted else "Current evidence is insufficient for robust market-moving classification.",
        "stories": accepted[:6],
    }


__all__ = ["build_market_moving_news"]
