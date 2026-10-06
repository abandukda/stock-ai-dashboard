"""Self-checking, non-scoring runtime contract for the customer Home surface."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from services.runtime_build_identity import HOME_RENDERER_VERSION, runtime_build_identity


def build_home_runtime_contract(
    story: Mapping[str, Any], *, market_health: Mapping[str, Any] | None = None,
    news_health: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    build = runtime_build_identity()
    action = dict(story.get("home_action_count_contract") or {})
    market_today = dict(story.get("market_today") or {})
    market = dict(market_health or {})
    news = dict(news_health or {})
    failures = []
    if not action.get("reconciled"):
        failures.append("HOME_ACTION_RECONCILIATION_FAILED")
    if not action.get("artifact_run_id") or not action.get("artifact_source_sha"):
        failures.append("PRODUCTION_ARTIFACT_IDENTITY_UNAVAILABLE")
    if not market_today.get("version"):
        failures.append("MARKET_TODAY_CONTRACT_MISSING")
    if "major_market_news" not in market_today:
        failures.append("MARKET_NEWS_CONTRACT_MISSING")
    per_ticker = []
    for card in story.get("home_featured_cards") or ():
        certified = dict(card.get("certified_customer_evaluation") or {})
        digests = dict(certified.get("digests") or {})
        revalidation = dict(card.get("targeted_revalidation") or {})
        certified_decision_digest = digests.get("decision_digest")
        if certified_decision_digest and card.get("decision_digest") != certified_decision_digest:
            failures.append(f'INCOMPATIBLE_SNAPSHOT_MIXING:{card.get("ticker") or "UNKNOWN"}')
        per_ticker.append({
            "ticker": card.get("ticker"), "live_price_timestamp": card.get("price_as_of"),
            "decision_timestamp": card.get("decision_as_of"), "snapshot_id": card.get("decision_snapshot_id"),
            "certification_status": certified.get("customer_publication_allowed"),
            "valuation_digest": digests.get("valuation_digest"), "decision_digest": card.get("decision_digest"),
            "revalidation_status": revalidation.get("state"),
            "revalidation_trigger_reason": list(revalidation.get("trigger_reasons") or ()),
        })
    return {
        "version": "ATLAS_HOME_RUNTIME_CONTRACT_V1", "code_sha": build["build_sha"],
        "deploy_branch": build["branch"],
        "production_artifact": {key: action.get(key) for key in ("artifact_run_id", "artifact_source_sha", "generated_at", "certification_digest")},
        "stock_data": {"publication_count": action.get("customer_publication_count"),
                       "home_featured_count": action.get("home_featured_count"),
                       "action_counts": action.get("home_featured_action_counts"), "live_quote_health": market},
        "market_today": {"status": market_today.get("status"), "source": market_today.get("source"),
                         "latest_timestamp": market_today.get("as_of"),
                         "available_symbols": market.get("symbols_available", []),
                         "unavailable_symbols": market.get("symbols_unavailable", [])},
        "market_news": {"status": "AVAILABLE" if market_today.get("major_market_news") else "TEMPORARILY_UNAVAILABLE",
                        "latest_story_timestamp": max((str(item.get("published_at") or "") for item in market_today.get("major_market_news") or ()), default=None),
                        "story_count": len(market_today.get("major_market_news") or ()), "runtime_health": news},
        "renderer": {"version": HOME_RENDERER_VERSION}, "per_ticker": per_ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(), "runtime_ready": not failures,
        "home_runtime_ready": not failures,
        "failure_reasons": list(dict.fromkeys(failures)), "non_scoring": True,
    }


__all__ = ["build_home_runtime_contract"]
