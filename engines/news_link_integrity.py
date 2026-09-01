"""Fail-closed provenance contract for customer-facing news links."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse


EXACT_ARTICLE = "EXACT_ARTICLE"
PUBLISHER_ONLY = "PUBLISHER_ONLY"
MISSING = "MISSING"
INVALID = "INVALID"

_ARTICLE_KEYS = ("article_url", "articleUrl", "newsURL", "news_url", "url", "link", "source_url")
_PUBLISHER_URL_KEYS = ("site", "base_url", "publisher_url")
_GENERIC_SEGMENTS = {
    "about", "articles", "business", "category", "finance", "home", "latest",
    "markets", "news", "search", "stocks", "topics",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parsed_http_url(value: Any):
    text = _text(value)
    if not text:
        return None
    try:
        parsed = urlparse(text)
    except (TypeError, ValueError):
        return False
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    return parsed


def _publisher_domain(*values: Any) -> str | None:
    for value in values:
        parsed = _parsed_http_url(value)
        if parsed and parsed.hostname:
            return parsed.hostname.lower().removeprefix("www.")
    return None


def _looks_like_exact_article(parsed: Any, *, explicit_article_field: bool) -> bool:
    host = parsed.hostname.lower().removeprefix("www.")
    parts = [part.lower() for part in parsed.path.split("/") if part]
    if not parts:
        return False
    if parts[0] in {"api", "category", "search", "topics"}:
        return False
    if len(parts) == 1 and parts[0] in _GENERIC_SEGMENTS:
        return False
    # Biztoc /x links are redirect/landing identifiers, not proven article pages.
    # A separately supplied article_url may still prove a concrete Biztoc article.
    if host == "biztoc.com" and parts[0] == "x" and not explicit_article_field:
        return False
    return len(parts) >= 2 or parts[0] not in _GENERIC_SEGMENTS


def normalize_news_link(item: Mapping[str, Any], *, publisher_name: str | None = None) -> dict[str, Any]:
    """Separate publisher identity from a proven exact-article destination."""
    article_key = next((key for key in _ARTICLE_KEYS if _text(item.get(key))), None)
    candidate = _text(item.get(article_key)) if article_key else ""
    publisher_url = next((_text(item.get(key)) for key in _PUBLISHER_URL_KEYS if _text(item.get(key))), "")
    publisher = _text(publisher_name or item.get("publisher") or item.get("source")) or None
    domain = _text(item.get("publisher_domain")) or _publisher_domain(publisher_url, candidate)

    if not candidate:
        status = PUBLISHER_ONLY if publisher_url else MISSING
        limitation = "Article link unavailable from source." if publisher or publisher_url else "Article source URL unavailable."
        return {
            "publisher_name": publisher,
            "publisher_domain": domain,
            "article_url": None,
            "article_url_status": status,
            "article_url_limitation": limitation,
        }

    parsed = _parsed_http_url(candidate)
    if parsed is False:
        return {
            "publisher_name": publisher,
            "publisher_domain": domain,
            "article_url": None,
            "article_url_status": INVALID,
            "article_url_limitation": "Article link supplied by source is invalid.",
        }

    exact = _looks_like_exact_article(parsed, explicit_article_field=article_key in {"article_url", "articleUrl"})
    return {
        "publisher_name": publisher,
        "publisher_domain": domain,
        "article_url": candidate if exact else None,
        "article_url_status": EXACT_ARTICLE if exact else PUBLISHER_ONLY,
        "article_url_limitation": None if exact else "Article link unavailable from source.",
    }


def news_source_presentation(item: Mapping[str, Any]) -> dict[str, str | None]:
    """Return the only customer CTA permitted by the canonical link status."""
    normalized = normalize_news_link(item, publisher_name=_text(item.get("publisher_name") or item.get("publisher") or item.get("source")))
    status = _text(item.get("article_url_status")) or normalized["article_url_status"]
    article_url = _text(item.get("article_url")) or normalized["article_url"]
    publisher = _text(item.get("publisher_name") or item.get("publisher") or item.get("source")) or "Source unavailable"
    if status == EXACT_ARTICLE and article_url:
        return {"label": "Open verified source", "href": article_url, "source": publisher, "limitation": None}
    return {
        "label": None,
        "href": None,
        "source": publisher,
        "limitation": _text(item.get("article_url_limitation") or normalized["article_url_limitation"]) or "Article link unavailable from source.",
    }


__all__ = [
    "EXACT_ARTICLE", "PUBLISHER_ONLY", "MISSING", "INVALID",
    "normalize_news_link", "news_source_presentation",
]
