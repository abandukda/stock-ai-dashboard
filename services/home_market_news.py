"""Governed, non-scoring broad-market news acquisition for Home."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from typing import Any, Callable, Mapping

import requests

from services.live_market.twelve_data_phase1 import load_twelve_data_setting

NEWS_ENDPOINT = "https://newsapi.org/v2/everything"
QUERY = '("Federal Reserve" OR inflation OR "Treasury yields" OR payrolls OR oil OR geopolitics OR tariffs OR regulation)'


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def fetch_major_market_news(
    *, get: Callable[..., Any] = requests.get, now: datetime | None = None,
    secrets: Mapping[str, Any] | None = None, environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Acquire displayable macro headlines only when commercial rights are explicit."""
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    environment = environ or os.environ
    key = load_twelve_data_setting("NEWSAPI_KEY", secrets=secrets, environ=environ)
    entitled = _truthy(load_twelve_data_setting("NEWSAPI_COMMERCIAL_DISPLAY_ALLOWED", secrets=secrets, environ=environ))
    health = {"provider": "NEWSAPI", "credential_present": bool(key), "commercial_display_allowed": entitled,
              "records_available": 0, "failure_reason": None, "fetched_at": instant.isoformat()}
    if not key:
        health["failure_reason"] = "CREDENTIAL_UNAVAILABLE"
        return {"version": "ATLAS_MARKET_NEWS_ACQUISITION_V1", "records": [], "runtime_health": health}
    if not entitled:
        health["failure_reason"] = "COMMERCIAL_DISPLAY_RIGHTS_UNCONFIRMED"
        return {"version": "ATLAS_MARKET_NEWS_ACQUISITION_V1", "records": [], "runtime_health": health}
    try:
        response = get(NEWS_ENDPOINT, params={"q": QUERY, "language": "en", "sortBy": "publishedAt", "pageSize": 20, "apiKey": key}, timeout=8)
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        health["failure_reason"] = "RATE_LIMIT" if getattr(exc.response, "status_code", None) == 429 else "PROVIDER_ERROR"
        return {"version": "ATLAS_MARKET_NEWS_ACQUISITION_V1", "records": [], "runtime_health": health}
    except Exception:
        health["failure_reason"] = "PROVIDER_ERROR"
        return {"version": "ATLAS_MARKET_NEWS_ACQUISITION_V1", "records": [], "runtime_health": health}
    records = []
    cutoff = instant - timedelta(hours=72)
    for article in payload.get("articles", []) if isinstance(payload, Mapping) else ():
        if not isinstance(article, Mapping):
            continue
        headline = " ".join(str(article.get("title") or "").split())
        published = str(article.get("publishedAt") or "")
        source = str(dict(article.get("source") or {}).get("name") or "").strip()
        try:
            stamp = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if not headline or not source or stamp < cutoff:
            continue
        evidence = "NEWSAPI-MARKET-" + hashlib.sha256(f"{headline}|{published}|{source}".encode()).hexdigest()[:20]
        records.append({"headline": headline, "source": source, "published_at": published,
                        "evidence_id": evidence, "url": article.get("url"),
                        "commercial_display_allowed": True, "non_scoring": True})
    health["records_available"] = len(records)
    health["last_successful_fetch_at"] = instant.isoformat() if records else None
    if not records:
        health["failure_reason"] = "NO_RELEVANT_CURRENT_HEADLINES"
    return {"version": "ATLAS_MARKET_NEWS_ACQUISITION_V1", "records": records, "runtime_health": health}


__all__ = ["fetch_major_market_news"]
