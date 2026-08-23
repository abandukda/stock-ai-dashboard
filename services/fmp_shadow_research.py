"""Bounded research-only FMP shadow evidence for Phase 9FMP.2.

Nothing in this module selects an investment provider winner or writes root
scanner fields. Callers persist its result only under a developer/research
namespace after the existing ranking and bounded-union selection are complete.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import time
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
FMP_SHADOW_MAX_ANALYST_ACTIONS = 25
FMP_SHADOW_MAX_INSTITUTIONAL_HOLDERS = 50
FMP_SHADOW_SOURCE_VERSION = "services.fmp_shadow_research.v2"


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


def _payload(
    client: FMPStableClient,
    endpoint: str,
    params: Mapping[str, Any],
    endpoint_diagnostics: dict[str, Any],
) -> tuple[list[Mapping[str, Any]] | None, str | None]:
    started = time.monotonic()
    response = client.get(endpoint, params)
    rows = _rows(response.payload) if response.outcome in {SUCCESS, AUTHORIZED_EMPTY} else []
    endpoint_diagnostics[endpoint] = {
        "calls": int(getattr(response, "attempts", 1) or 1),
        "outcome": str(response.outcome),
        "provider_rows_returned": len(rows),
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }
    if response.outcome not in {SUCCESS, AUTHORIZED_EMPTY}:
        return None, None
    return rows, response.fetched_at


def _available(item: Mapping[str, Any]) -> bool:
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    return provenance.get("semantic_status") == "AVAILABLE"


def _action_identity(item: Mapping[str, Any]) -> tuple[str, ...]:
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    return tuple(str(item.get(key) or "") for key in ("firm", "action", "from_grade", "to_grade")) + (
        str(provenance.get("endpoint_family") or ""),
        json.dumps(item, sort_keys=True, default=str),
    )


def _bounded_actions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (str(item.get("date") or ""), _action_identity(item)),
        reverse=True,
    )[:FMP_SHADOW_MAX_ANALYST_ACTIONS]


def _holder_identity(item: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(item.get(key) or "") for key in (
        "investor_name", "investor_cik", "security_symbol", "security_name", "security_cusip",
    )) + (json.dumps(item, sort_keys=True, default=str),)


def _holder_rank(item: Mapping[str, Any]) -> tuple[Any, ...]:
    # Presence is ranked separately from value; missing evidence is never
    # silently converted to zero. Each subsequent metric is a deterministic
    # tie-break, while identity makes equal ranks stable.
    values = tuple(item.get(key) for key in ("weight", "market_value", "shares"))
    ranked = tuple(part for value in values for part in (value is not None, value if value is not None else 0.0))
    return ranked + (_holder_identity(item),)


def _bounded_holders(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=_holder_rank, reverse=True)[:FMP_SHADOW_MAX_INSTITUTIONAL_HOLDERS]


def _counts(
    returned: int,
    normalized: int,
    retained: int,
    *,
    discarded_by_cap: int | None = None,
) -> dict[str, int]:
    return {
        "provider_rows_returned": returned,
        "normalized_rows": normalized,
        "retained_rows": retained,
        "discarded_by_cap": max(0, normalized - retained) if discarded_by_cap is None else discarded_by_cap,
    }


def _fetch_analyst(client: FMPStableClient, symbol: str, diagnostic: dict[str, Any]) -> dict[str, Any]:
    params = {"symbol": symbol}
    endpoints = diagnostic.setdefault("endpoints", {})
    estimates, estimates_at = _payload(client, "analyst-estimates", {**params, "period": "annual", "limit": 12}, endpoints)
    consensus, consensus_at = _payload(client, "grades-consensus", params, endpoints)
    actions, actions_at = _payload(client, "grades", {**params, "limit": 25}, endpoints)
    targets, targets_at = _payload(client, "price-target-consensus", params, endpoints)
    target_summary, summary_at = _payload(client, "price-target-summary", params, endpoints)
    if any(value is None for value in (estimates, consensus, actions, targets, target_summary)):
        return {}
    normalized_estimates = [normalize_analyst_estimate(row, fetched_at=estimates_at) for row in estimates or []]
    normalized_consensus = [normalize_analyst_consensus(row, fetched_at=consensus_at) for row in consensus or []]
    normalized_actions_all = [normalize_analyst_action(row, fetched_at=actions_at) for row in actions or []]
    normalized_actions = _bounded_actions(normalized_actions_all)
    normalized_targets = [normalize_price_target(row, endpoint_family="price-target-consensus", fetched_at=targets_at) for row in targets or []]
    normalized_summary = [normalize_price_target(row, endpoint_family="price-target-summary", fetched_at=summary_at) for row in target_summary or []]
    diagnostic["row_counts"] = {
        "estimates": _counts(len(estimates or []), len(normalized_estimates), len(normalized_estimates)),
        "consensus": _counts(len(consensus or []), len(normalized_consensus), len(normalized_consensus)),
        "actions": _counts(len(actions or []), len(normalized_actions_all), len(normalized_actions)),
        "targets": _counts(len(targets or []), len(normalized_targets), len(normalized_targets)),
        "target_summary": _counts(len(target_summary or []), len(normalized_summary), len(normalized_summary)),
    }
    return {
        "provider": "FMP",
        "semantic_status": "AVAILABLE" if any(map(_available, normalized_estimates + normalized_consensus + normalized_actions + normalized_targets + normalized_summary)) else "DATA_UNAVAILABLE",
        "estimates": normalized_estimates,
        "consensus": normalized_consensus,
        "actions": normalized_actions,
        "targets": normalized_targets,
        "target_summary": normalized_summary,
        "estimate_vintage_status": "NOT_POINT_IN_TIME_VINTAGE",
        "row_counts": diagnostic["row_counts"],
    }


def _fetch_ownership_summary(client: FMPStableClient, symbol: str, diagnostic: dict[str, Any]) -> dict[str, Any]:
    rows, fetched_at = _payload(client, "institutional-ownership/symbol-positions-summary", {"symbol": symbol}, diagnostic.setdefault("endpoints", {}))
    if rows is None:
        return {}
    normalized = [normalize_institutional_ownership_summary(row, fetched_at=fetched_at) for row in rows]
    diagnostic["row_counts"] = {"summary": _counts(len(rows), len(normalized), len(normalized))}
    return {
        "provider": "FMP",
        "semantic_status": "AVAILABLE" if any(map(_available, normalized)) else "DATA_UNAVAILABLE",
        "summary": normalized,
        "row_counts": diagnostic["row_counts"],
    }


def _fetch_fund_disclosures(client: FMPStableClient, symbol: str, diagnostic: dict[str, Any]) -> dict[str, Any]:
    rows, fetched_at = _payload(client, "funds/disclosure-holders-latest", {"symbol": symbol, "limit": 50}, diagnostic.setdefault("endpoints", {}))
    if rows is None:
        return {}
    normalized_all = [normalize_fund_disclosure(row, fetched_at=fetched_at) for row in rows]
    normalized = _bounded_holders(normalized_all)
    diagnostic["row_counts"] = {"holders": _counts(len(rows), len(normalized_all), len(normalized))}
    return {
        "provider": "FMP",
        "semantic_status": "AVAILABLE" if any(map(_available, normalized)) else "DATA_UNAVAILABLE",
        "holders": normalized,
        "row_counts": diagnostic["row_counts"],
    }


def _fetch_news(
    client: FMPStableClient,
    symbol: str,
    company_name: str,
    endpoint: str,
    relevance_check: Callable[[str, str, str, str], bool],
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    rows, fetched_at = _payload(client, endpoint, {"symbols": symbol, "limit": 10}, diagnostic.setdefault("endpoints", {}))
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
    diagnostic["row_counts"] = {
        "articles": _counts(len(rows), len(accepted), len(accepted), discarded_by_cap=0),
    }
    return {
        "provider": "FMP",
        "semantic_status": "AVAILABLE" if accepted else "DATA_UNAVAILABLE",
        "article_count": len(rows),
        "accepted_relevance_count": len(accepted),
        "relevance_rejected_count": rejected,
        "articles": accepted,
        "row_counts": diagnostic["row_counts"],
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
    live_diagnostics: dict[str, dict[str, Any]] = {family: {} for family in FMP_SHADOW_TTLS}
    fetchers = {
        "fmp_shadow_analyst": lambda: _fetch_analyst(client, ticker, live_diagnostics["fmp_shadow_analyst"]),
        "fmp_shadow_ownership_summary": lambda: _fetch_ownership_summary(client, ticker, live_diagnostics["fmp_shadow_ownership_summary"]),
        "fmp_shadow_fund_disclosures": lambda: _fetch_fund_disclosures(client, ticker, live_diagnostics["fmp_shadow_fund_disclosures"]),
        "fmp_shadow_company_news": lambda: _fetch_news(client, ticker, company_name, "news/stock", relevance_check, live_diagnostics["fmp_shadow_company_news"]),
        "fmp_shadow_press_releases": lambda: _fetch_news(client, ticker, company_name, "news/press-releases", relevance_check, live_diagnostics["fmp_shadow_press_releases"]),
    }
    families: dict[str, Any] = {}
    freshness: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    shadow_started = time.monotonic()
    for family, fetcher in fetchers.items():
        family_started = time.monotonic()
        families[family], freshness[family] = cached_evidence(
            ticker, family, FMP_SHADOW_TTLS[family], fetcher,
            source_version=FMP_SHADOW_SOURCE_VERSION,
        )
        live = live_diagnostics[family]
        endpoints = live.get("endpoints") if isinstance(live.get("endpoints"), Mapping) else {}
        status = freshness[family].get("status")
        row_counts = live.get("row_counts") or (
            families[family].get("row_counts", {})
            if isinstance(families.get(family), Mapping) else {}
        )
        diagnostics[family] = {
            "calls": sum(int(item.get("calls") or 0) for item in endpoints.values()),
            "live_fetches": 1 if endpoints else 0,
            "fresh_cache_hits": 1 if status == "FRESH_CACHE" else 0,
            "stale_fallbacks": 1 if status == "STALE_FALLBACK" else 0,
            "unavailable": 1 if status == "TEMPORARILY_UNAVAILABLE" else 0,
            "outcomes": dict(sorted((str(name), str(item.get("outcome"))) for name, item in endpoints.items())),
            "provider_rows_returned": (
                sum(int(item.get("provider_rows_returned") or 0) for item in endpoints.values())
                if endpoints else
                sum(int(item.get("provider_rows_returned") or 0) for item in row_counts.values())
            ),
            "normalized_rows": sum(int(item.get("normalized_rows") or 0) for item in row_counts.values()),
            "retained_rows": sum(int(item.get("retained_rows") or 0) for item in row_counts.values()),
            "discarded_by_cap": sum(int(item.get("discarded_by_cap") or 0) for item in row_counts.values()),
            "row_counts": row_counts,
            "elapsed_seconds": round(time.monotonic() - family_started, 6),
            "endpoints": endpoints,
        }
    return {
        "provider": "FMP", "mode": "RESEARCH_ONLY_SHADOW", "families": families,
        "freshness": freshness,
        "diagnostics": {
            "fmp_shadow_seconds": round(time.monotonic() - shadow_started, 6),
            "families": diagnostics,
        },
    }


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
    "FMP_SHADOW_MAX_ANALYST_ACTIONS", "FMP_SHADOW_MAX_INSTITUTIONAL_HOLDERS",
    "FMP_SHADOW_MAX_REQUESTS_PER_SYMBOL", "FMP_SHADOW_TTLS", "build_fmp_shadow_research",
    "build_provider_comparison",
]
