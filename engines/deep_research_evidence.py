"""Normalized, reporting-only evidence helpers for Phase 9B deep research.

This module deliberately contains no scoring, recommendation, ranking, valuation,
or trade-plan logic.  It turns already-authorized provider responses into stable
evidence objects and selects the bounded post-ranking enrichment population.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from services.evidence_lineage_governance import is_disallowed_provider, is_disallowed_url


NEWS_EVIDENCE_SCHEMA_VERSION = "ATLAS_GOVERNED_NEWS_EVIDENCE_V2"
_GOVERNED_NEWS_TRANSPORTS = {"NEWSAPI", "FINNHUB"}


def normalize_governed_news_article(
    raw: Mapping[str, Any], *, symbol: str, transport_provider: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any] | None:
    """Normalize optional news while keeping transport and publisher distinct.

    Prohibited publishers and URL lineage are omitted rather than relabelled.
    This reporting-only boundary never changes an investment decision.
    """
    transport = str(transport_provider or raw.get("transport_provider") or raw.get("provider") or "").strip().upper()
    if transport == "FINNHUB COMPANY NEWS":
        transport = "FINNHUB"
    publisher = str(raw.get("article_publisher") or raw.get("publisher") or raw.get("source") or "").strip()
    url = str(raw.get("article_url") or raw.get("url") or "").strip()
    headline = str(raw.get("headline") or raw.get("title") or "").strip()
    article_timestamp = str(raw.get("article_timestamp") or raw.get("published_at") or raw.get("publishedAt") or raw.get("published") or "").strip()
    capture_timestamp = str(captured_at or raw.get("capture_timestamp") or datetime.now(timezone.utc).isoformat()).strip()
    if not headline or transport not in _GOVERNED_NEWS_TRANSPORTS:
        return None
    if is_disallowed_provider(publisher) or is_disallowed_url(url):
        return None
    evidence_seed = "|".join((transport, symbol.upper(), headline, article_timestamp, url))
    evidence_id = str(raw.get("evidence_id") or f"NEWS-{hashlib.sha256(evidence_seed.encode('utf-8')).hexdigest()[:20].upper()}")
    return {
        "headline": headline,
        "title": headline,
        "transport_provider": transport,
        "provider": transport,
        "article_publisher": publisher or None,
        "evidence_id": evidence_id,
        "article_timestamp": article_timestamp or None,
        "published_at": article_timestamp or None,
        "capture_timestamp": capture_timestamp,
        "article_url": url or None,
        "url": url or None,
        "ticker": symbol.upper(),
        "ticker_relevance": "VERIFIED_ENTITY_MATCH",
        "category": raw.get("category") or "COMPANY_NEWS",
        "materiality": raw.get("materiality") or "UNCLASSIFIED",
    }


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def _symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").strip().upper()


def select_deep_enrichment_symbols(
    ranked_rows: Sequence[Mapping[str, Any]],
    *,
    top_limit: int = 15,
    watchlist: Iterable[str] = (),
) -> tuple[list[str], dict[str, list[str]]]:
    """Return a stable deduplicated post-ranking union and selection reasons.

    Recommendation and tier values are consumed exactly as already calculated;
    this function never derives or changes them.
    """
    watch = {str(item).strip().upper() for item in watchlist if str(item).strip()}
    ordered: list[str] = []
    reasons: dict[str, list[str]] = {}

    def add(symbol: str, reason: str) -> None:
        if not symbol:
            return
        if symbol not in reasons:
            reasons[symbol] = []
            ordered.append(symbol)
        if reason not in reasons[symbol]:
            reasons[symbol].append(reason)

    for row in ranked_rows[: max(0, int(top_limit))]:
        add(_symbol(row), "TOP_15")
    for row in ranked_rows:
        symbol = _symbol(row)
        recommendation = str(
            row.get("recommendation") or row.get("verdict") or row.get("Recommendation") or ""
        ).upper().replace(" ", "_")
        tier = str(row.get("v42_tier") or row.get("research_tier") or row.get("tier") or "").upper()
        if recommendation == "BUY_NOW":
            add(symbol, "BUY_NOW")
        if tier in {"TIER_1", "TIER1", "FULL", "DEEP"}:
            add(symbol, "TIER_1")
        if symbol in watch:
            add(symbol, "WATCHLIST")
    return ordered, reasons


def normalize_earnings_history(
    rows: Any,
    *,
    provider: str,
    captured_at: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Normalize provider earnings rows without replacing missing or zero values."""
    if not isinstance(rows, list):
        return []
    observed_at = captured_at or datetime.now(timezone.utc).isoformat()
    normalized: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        fiscal_period = str(raw.get("fiscalPeriod") or raw.get("period") or raw.get("fiscalDateEnding") or "").strip()
        report_date = str(raw.get("date") or raw.get("reportedDate") or raw.get("reportDate") or "").strip()
        actual_eps = _number(raw.get("epsActual") if raw.get("epsActual") is not None else raw.get("actualEarningResult"))
        estimate_eps = _number(raw.get("epsEstimated") if raw.get("epsEstimated") is not None else raw.get("estimatedEarning"))
        actual_revenue = _number(raw.get("revenueActual"))
        estimate_revenue = _number(raw.get("revenueEstimated"))
        eps_surprise = (
            ((actual_eps - estimate_eps) / abs(estimate_eps)) * 100
            if actual_eps is not None and estimate_eps not in (None, 0)
            else None
        )
        revenue_surprise = (
            ((actual_revenue - estimate_revenue) / abs(estimate_revenue)) * 100
            if actual_revenue is not None and estimate_revenue not in (None, 0)
            else None
        )
        if not fiscal_period and not report_date:
            continue
        item = {
            "fiscal_period": fiscal_period or None,
            "report_date": report_date or None,
            "eps_actual": actual_eps,
            "eps_estimate": estimate_eps,
            "eps_surprise_pct": round(eps_surprise, 4) if eps_surprise is not None else None,
            "revenue_actual": actual_revenue,
            "revenue_estimate": estimate_revenue,
            "revenue_surprise_pct": round(revenue_surprise, 4) if revenue_surprise is not None else None,
            "provider": provider,
            "evidence_timestamp": observed_at,
        }
        normalized[(fiscal_period, report_date)] = item
    return sorted(
        normalized.values(),
        key=lambda item: (str(item.get("report_date") or ""), str(item.get("fiscal_period") or "")),
        reverse=True,
    )[:limit]


def build_earnings_comparisons(history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministic latest-versus-prior evidence comparisons."""
    if len(history) < 2:
        return {}
    latest, prior = history[0], history[1]

    def direction(key: str) -> str | None:
        current, previous = _number(latest.get(key)), _number(prior.get(key))
        if current is None or previous is None:
            return None
        return "IMPROVING" if current > previous else "WORSENING" if current < previous else "UNCHANGED"

    result = {
        "eps_surprise_trend": direction("eps_surprise_pct"),
        "revenue_surprise_trend": direction("revenue_surprise_pct"),
        "comparison_basis": "LATEST_REPORTED_QUARTER_VS_PRIOR_REPORTED_QUARTER",
    }
    return {key: value for key, value in result.items() if value is not None}


def normalize_guidance_evidence(rows: Any) -> list[dict[str, Any]]:
    """Accept only explicitly sourced company/management guidance evidence."""
    if not isinstance(rows, list):
        return []
    allowed = {"revenue", "eps", "margin", "capex", "other"}
    output = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        source_type = str(raw.get("source_type") or "").upper()
        category = str(raw.get("category") or "").lower()
        if source_type not in {"COMPANY", "MANAGEMENT", "SEC_FILING", "EARNINGS_TRANSCRIPT"} or category not in allowed:
            continue
        if not raw.get("source") or not raw.get("date"):
            continue
        output.append({key: raw.get(key) for key in (
            "category", "fiscal_horizon", "low", "high", "value", "prior_low", "prior_high",
            "prior_value", "direction", "source", "source_url", "date", "source_type"
        ) if raw.get(key) is not None})
    return output


def normalize_transcript_evidence(rows: Any) -> list[dict[str, Any]]:
    """Retain bounded structured transcript evidence only with provenance."""
    if not isinstance(rows, list):
        return []
    output = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        if not raw.get("source") or not raw.get("date") or not raw.get("fiscal_period"):
            continue
        themes = raw.get("themes") if isinstance(raw.get("themes"), list) else []
        output.append({
            "fiscal_period": raw.get("fiscal_period"),
            "date": raw.get("date"),
            "source": raw.get("source"),
            "source_url": raw.get("source_url"),
            "themes": [str(item) for item in themes[:8] if str(item).strip()],
        })
    return output


def normalize_news_articles(
    rows: Any, *, symbol: str, transport_provider: str | None = None,
    captured_at: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    output = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        normalized = normalize_governed_news_article(
            raw, symbol=symbol, transport_provider=transport_provider, captured_at=captured_at,
        )
        if normalized:
            output.append(normalized)
    return output
