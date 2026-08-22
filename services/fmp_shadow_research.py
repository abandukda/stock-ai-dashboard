"""Bounded research-only FMP shadow evidence for Phase 9FMP.2.

Nothing in this module selects an investment provider winner or writes root
scanner fields. Callers persist its result only under a developer/research
namespace after the existing ranking and bounded-union selection are complete.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from engines.fmp_normalization import (
    normalize_analyst_action,
    normalize_analyst_consensus,
    normalize_analyst_estimate,
    normalize_fmp_news,
    normalize_fund_disclosure,
    normalize_institutional_ownership_summary,
    normalize_price_target,
)
from services.deep_research_cache import cached_evidence
from services.fmp_stable_client import AUTHORIZED_EMPTY, FMPStableClient, SUCCESS


FMP_SHADOW_TTLS = {
    "fmp_shadow_analyst": 4 * 60 * 60,
    "fmp_shadow_ownership_summary": 12 * 60 * 60,
    "fmp_shadow_fund_disclosures": 24 * 60 * 60,
    "fmp_shadow_company_news": 60 * 60,
    "fmp_shadow_press_releases": 60 * 60,
}

FMP_SHADOW_MAX_REQUESTS_PER_SYMBOL = 9


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        return [payload]
    return []


def _payload(client: FMPStableClient, endpoint: str, params: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]] | None, str | None]:
    response = client.get(endpoint, params)
    if response.outcome not in {SUCCESS, AUTHORIZED_EMPTY}:
        return None, None
    return _rows(response.payload), response.fetched_at


def _available(item: Mapping[str, Any]) -> bool:
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    return provenance.get("semantic_status") == "AVAILABLE"


def _fetch_analyst(client: FMPStableClient, symbol: str) -> dict[str, Any]:
    params = {"symbol": symbol}
    estimates, estimates_at = _payload(client, "analyst-estimates", {**params, "period": "annual", "limit": 12})
    consensus, consensus_at = _payload(client, "grades-consensus", params)
    actions, actions_at = _payload(client, "grades", {**params, "limit": 20})
    targets, targets_at = _payload(client, "price-target-consensus", params)
    target_summary, summary_at = _payload(client, "price-target-summary", params)
    if any(value is None for value in (estimates, consensus, actions, targets, target_summary)):
        return {}
    normalized_estimates = [normalize_analyst_estimate(row, fetched_at=estimates_at) for row in estimates or []]
    normalized_consensus = [normalize_analyst_consensus(row, fetched_at=consensus_at) for row in consensus or []]
    normalized_actions = [normalize_analyst_action(row, fetched_at=actions_at) for row in actions or []]
    normalized_targets = [normalize_price_target(row, endpoint_family="price-target-consensus", fetched_at=targets_at) for row in targets or []]
    normalized_summary = [normalize_price_target(row, endpoint_family="price-target-summary", fetched_at=summary_at) for row in target_summary or []]
    return {
        "provider": "FMP",
        "semantic_status": "AVAILABLE" if any(map(_available, normalized_estimates + normalized_consensus + normalized_actions + normalized_targets + normalized_summary)) else "DATA_UNAVAILABLE",
        "estimates": normalized_estimates,
        "consensus": normalized_consensus,
        "actions": normalized_actions,
        "targets": normalized_targets,
        "target_summary": normalized_summary,
        "estimate_vintage_status": "NOT_POINT_IN_TIME_VINTAGE",
    }


def _fetch_ownership_summary(client: FMPStableClient, symbol: str) -> dict[str, Any]:
    rows, fetched_at = _payload(client, "institutional-ownership/symbol-positions-summary", {"symbol": symbol})
    if rows is None:
        return {}
    normalized = [normalize_institutional_ownership_summary(row, fetched_at=fetched_at) for row in rows]
    return {"provider": "FMP", "semantic_status": "AVAILABLE" if any(map(_available, normalized)) else "DATA_UNAVAILABLE", "summary": normalized}


def _fetch_fund_disclosures(client: FMPStableClient, symbol: str) -> dict[str, Any]:
    rows, fetched_at = _payload(client, "funds/disclosure-holders-latest", {"symbol": symbol, "limit": 20})
    if rows is None:
        return {}
    normalized = [normalize_fund_disclosure(row, fetched_at=fetched_at) for row in rows]
    return {"provider": "FMP", "semantic_status": "AVAILABLE" if any(map(_available, normalized)) else "DATA_UNAVAILABLE", "holders": normalized}


def _fetch_news(
    client: FMPStableClient,
    symbol: str,
    company_name: str,
    endpoint: str,
    relevance_check: Callable[[str, str, str, str], bool],
) -> dict[str, Any]:
    rows, fetched_at = _payload(client, endpoint, {"symbols": symbol, "limit": 10})
    if rows is None:
        return {}
    accepted = []
    rejected = 0
    for row in rows:
        title = str(row.get("title") or row.get("headline") or "").strip()
        description = str(row.get("text") or row.get("description") or "").strip()
        if not title or not relevance_check(title, description, symbol, company_name):
            rejected += 1
            continue
        normalized = normalize_fmp_news(row, symbol=symbol, endpoint_family=endpoint, fetched_at=fetched_at)
        if _available(normalized):
            accepted.append(normalized)
    return {
        "provider": "FMP",
        "semantic_status": "AVAILABLE" if accepted else "DATA_UNAVAILABLE",
        "article_count": len(rows),
        "accepted_relevance_count": len(accepted),
        "relevance_rejected_count": rejected,
        "articles": accepted,
    }


def build_fmp_shadow_research(
    symbol: str,
    company_name: str,
    *,
    api_key: str,
    relevance_check: Callable[[str, str, str, str], bool],
    client: FMPStableClient | None = None,
) -> dict[str, Any]:
    """Fetch/cache five separate shadow families for one already-selected symbol."""
    ticker = str(symbol or "").strip().upper()
    if not ticker or not str(api_key or "").strip():
        return {}
    client = client or FMPStableClient(api_key, timeout_seconds=12, retries=0)
    fetchers = {
        "fmp_shadow_analyst": lambda: _fetch_analyst(client, ticker),
        "fmp_shadow_ownership_summary": lambda: _fetch_ownership_summary(client, ticker),
        "fmp_shadow_fund_disclosures": lambda: _fetch_fund_disclosures(client, ticker),
        "fmp_shadow_company_news": lambda: _fetch_news(client, ticker, company_name, "news/stock", relevance_check),
        "fmp_shadow_press_releases": lambda: _fetch_news(client, ticker, company_name, "news/press-releases", relevance_check),
    }
    families: dict[str, Any] = {}
    freshness: dict[str, Any] = {}
    for family, fetcher in fetchers.items():
        families[family], freshness[family] = cached_evidence(
            ticker, family, FMP_SHADOW_TTLS[family], fetcher,
            source_version="services.fmp_shadow_research.v1",
        )
    return {"provider": "FMP", "mode": "RESEARCH_ONLY_SHADOW", "families": families, "freshness": freshness}


def build_provider_comparison(current: Mapping[str, Any], shadow: Mapping[str, Any]) -> dict[str, Any]:
    """Report coexistence and disagreement without choosing a winner."""
    families = shadow.get("families") if isinstance(shadow.get("families"), Mapping) else {}
    analyst = families.get("fmp_shadow_analyst") if isinstance(families.get("fmp_shadow_analyst"), Mapping) else {}
    company_news = families.get("fmp_shadow_company_news") if isinstance(families.get("fmp_shadow_company_news"), Mapping) else {}
    press = families.get("fmp_shadow_press_releases") if isinstance(families.get("fmp_shadow_press_releases"), Mapping) else {}

    def availability(current_available: bool, fmp_available: bool) -> str:
        if current_available and fmp_available:
            return "BOTH_AVAILABLE"
        if current_available:
            return "ONLY_CURRENT_PROVIDER_AVAILABLE"
        if fmp_available:
            return "ONLY_FMP_AVAILABLE"
        return "BOTH_UNAVAILABLE"

    fmp_consensus = bool(analyst.get("consensus")) and analyst.get("semantic_status") == "AVAILABLE"
    fmp_targets = bool(analyst.get("targets") or analyst.get("target_summary")) and analyst.get("semantic_status") == "AVAILABLE"
    fmp_actions = bool(analyst.get("actions")) and analyst.get("semantic_status") == "AVAILABLE"
    fmp_estimates = bool(analyst.get("estimates")) and analyst.get("semantic_status") == "AVAILABLE"
    newsapi_articles = current.get("news_evidence") if isinstance(current.get("news_evidence"), list) else []
    fmp_articles = list(company_news.get("articles") or []) + list(press.get("articles") or [])
    return {
        "mode": "DIAGNOSTIC_NO_WINNER_SELECTION",
        "analyst": {
            "selection_policy": "NO_AUTOMATIC_WINNER_OR_DISAGREEMENT_RESOLUTION",
            "recommendation_consensus": availability(bool(current.get("source_finnhub_recommendation")), fmp_consensus),
            "target": availability(bool(current.get("source_finnhub_target")), fmp_targets),
            "actions": availability(bool(current.get("source_finnhub_analyst_actions")), fmp_actions),
            "estimates": availability(False, fmp_estimates),
        },
        "news": {
            "selection_policy": "NEWSAPI_REMAINS_AUTHORITATIVE_FMP_IS_SHADOW_ONLY",
            "availability": availability(bool(current.get("source_newsapi")), bool(fmp_articles)),
            "newsapi_article_count": len(newsapi_articles),
            "newsapi_url_count": sum(bool(item.get("url")) for item in newsapi_articles if isinstance(item, Mapping)),
            "fmp_article_count": int(company_news.get("article_count") or 0) + int(press.get("article_count") or 0),
            "fmp_accepted_relevance_count": len(fmp_articles),
            "fmp_url_count": sum(bool(item.get("url")) for item in fmp_articles if isinstance(item, Mapping)),
            "most_recent_newsapi": max((str(item.get("published_at") or "") for item in newsapi_articles if isinstance(item, Mapping)), default=None),
            "most_recent_fmp": max((str(item.get("published_at") or "") for item in fmp_articles if isinstance(item, Mapping)), default=None),
        },
        "ownership": {
            "finnhub_insider_available": bool(current.get("source_finnhub_insider")),
            "fmp_institutional_summary_available": bool((families.get("fmp_shadow_ownership_summary") or {}).get("semantic_status") == "AVAILABLE"),
            "fmp_fund_disclosures_available": bool((families.get("fmp_shadow_fund_disclosures") or {}).get("semantic_status") == "AVAILABLE"),
            "semantic_note": "INSTITUTIONAL_AND_INSIDER_EVIDENCE_REMAIN_SEPARATE",
        },
    }


__all__ = [
    "FMP_SHADOW_MAX_REQUESTS_PER_SYMBOL", "FMP_SHADOW_TTLS", "build_fmp_shadow_research",
    "build_provider_comparison",
]
