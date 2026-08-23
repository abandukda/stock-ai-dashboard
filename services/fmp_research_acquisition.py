"""Explicit-ticker FMP acquisition for canonical Research context.

This service is deliberately isolated from the scanner.  It refreshes independent
evidence families, uses family-level caches, and never calculates or mutates an
ATLAS production decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from engines.earnings_intelligence import build_earnings_intelligence
from engines.fmp_normalization import (
    normalize_analyst_action, normalize_analyst_consensus,
    normalize_analyst_estimate, normalize_earnings_record,
    normalize_financial_growth, normalize_financial_statement,
    normalize_fmp_news, normalize_fund_disclosure,
    normalize_institutional_ownership_summary, normalize_key_metrics,
    normalize_peers, normalize_price_target, normalize_profile, normalize_ratios,
)
from engines.research_context import (
    build_research_context, evidence_envelope, security_type_of,
    stable_evidence_id,
)
from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE
from services.fmp_stable_client import FMPResponse, FMPStableClient
from services.research_family_cache import (
    DEFAULT_CACHE_ROOT, load_family_envelope, save_family_envelope,
)


FMP_RESEARCH_ACQUISITION_VERSION = "FMP_RESEARCH_ACQUISITION_V1"
MAX_EXPLICIT_RESEARCH_REQUESTS = 24
MAX_ANALYST_ACTIONS = 25
MAX_INSTITUTIONAL_HOLDERS = 50

_CORPORATE_FAMILIES = (
    "financial_statements", "ratios_key_metrics", "growth_segments",
    "earnings_history", "analyst_estimates", "analyst_consensus_targets",
    "analyst_actions", "institutional_ownership", "company_news",
    "press_releases",
)


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "historical"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        return [payload] if payload else []
    return []


def _available(record: Mapping[str, Any]) -> bool:
    provenance = record.get("provenance")
    return isinstance(provenance, Mapping) and provenance.get("semantic_status") == AVAILABLE


def _date(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if record.get(key) not in (None, ""):
            return record.get(key)
    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        for key in keys:
            if provenance.get(key) not in (None, ""):
                return provenance.get(key)
    return None


def _evidence_ids(ticker: str, family: str, records: Sequence[Mapping[str, Any]]) -> list[str]:
    ids = []
    for index, record in enumerate(records):
        provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
        endpoint = str(provenance.get("endpoint_family") or family)
        semantic = ":".join(str(record.get(key) or "") for key in (
            "symbol", "fiscal_date", "report_date", "date", "firm", "url",
            "investor", "security_cusip",
        )) or str(index)
        ids.append(stable_evidence_id(
            ticker=ticker, family=family, provider="FMP",
            semantic_identity=f"{endpoint}:{semantic}",
            observation_date=_date(record, "observation_date", "report_date", "published_at"),
            reporting_date=_date(record, "reporting_date", "fiscal_date"),
            filing_date=_date(record, "filing_date"), provenance=endpoint,
        ))
    return ids


def _envelope(
    ticker: str, family: str, endpoint: str, fetched_at: str,
    data: Any, records: Sequence[Mapping[str, Any]], *,
    limitations: Sequence[str] = (), available: bool | None = None,
) -> dict[str, Any]:
    good = [record for record in records if _available(record)]
    is_available = bool(good) if available is None else bool(available)
    first = good[0] if good else {}
    return evidence_envelope(
        ticker=ticker, family=family,
        semantic_status=AVAILABLE if is_available else DATA_UNAVAILABLE,
        cache_status="FETCHED" if is_available else "TEMPORARILY_UNAVAILABLE",
        provider="FMP", endpoint_family=endpoint, fetched_at=fetched_at,
        observation_date=_date(first, "observation_date", "report_date", "published_at"),
        reporting_date=_date(first, "reporting_date", "fiscal_date"),
        filing_date=_date(first, "filing_date"), data=data if is_available else None,
        evidence_ids=_evidence_ids(ticker, family, good),
        limitations=limitations if is_available else tuple(limitations) + ("No normalized FMP evidence was available.",),
    )


class _Session:
    def __init__(self, client: FMPStableClient) -> None:
        self.client = client
        self.calls = 0
        self.provider_attempts = 0
        self.outcomes: dict[str, int] = {}
        self.endpoint_seconds: dict[str, float] = {}

    def get(self, endpoint: str, params: Mapping[str, Any]) -> FMPResponse:
        if self.calls >= MAX_EXPLICIT_RESEARCH_REQUESTS:
            raise RuntimeError("explicit FMP Research request ceiling exceeded")
        started = time.monotonic()
        response = self.client.get(endpoint, params)
        elapsed = max(0.0, time.monotonic() - started)
        self.calls += 1
        self.provider_attempts += response.attempts
        self.outcomes[response.outcome] = self.outcomes.get(response.outcome, 0) + 1
        self.endpoint_seconds[endpoint] = self.endpoint_seconds.get(endpoint, 0.0) + elapsed
        return response


def _strip_cache_metadata(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in envelope.items() if key != "cache_version"}


def _refresh_family(
    ticker: str, family: str, fetcher: Callable[[], tuple[dict[str, Any], bool]],
    *, cache_root: str | Path, diagnostics: dict[str, Any], force_refresh: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    cached = load_family_envelope(ticker, family, root=cache_root, allow_stale=True)
    if cached and cached.get("cache_status") == "FRESH_CACHE" and not force_refresh:
        diagnostics["fresh_cache_hits"] += 1
        diagnostics["family_seconds"][family] = round(max(0.0, time.monotonic() - started), 6)
        return _strip_cache_metadata(cached)
    stale = cached if cached and cached.get("cache_status") == "STALE_FALLBACK" else None
    try:
        envelope, refresh_succeeded = fetcher()
    except Exception:
        envelope, refresh_succeeded = evidence_envelope(ticker=ticker, family=family), False
    if refresh_succeeded:
        diagnostics["live_family_refreshes"] += 1
        save_family_envelope(ticker, family, envelope, root=cache_root)
        diagnostics["family_seconds"][family] = round(max(0.0, time.monotonic() - started), 6)
        return envelope
    if stale:
        diagnostics["stale_fallbacks"] += 1
        diagnostics["family_seconds"][family] = round(max(0.0, time.monotonic() - started), 6)
        return _strip_cache_metadata(stale)
    diagnostics["temporarily_unavailable"] += 1
    diagnostics["family_seconds"][family] = round(max(0.0, time.monotonic() - started), 6)
    return envelope


def _request_records(session: _Session, endpoint: str, symbol: str, **params: Any) -> tuple[FMPResponse, list[Mapping[str, Any]]]:
    response = session.get(endpoint, {"symbol": symbol, **params})
    return response, _rows(response.payload) if response.successful else []


def _relevant_news(row: Mapping[str, Any], symbol: str, company_name: str | None) -> bool:
    text = " ".join(str(row.get(key) or "") for key in ("title", "headline", "symbol", "tickers"))
    if re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", text.upper()):
        return True
    company_token = next((part for part in re.split(r"\W+", company_name or "") if len(part) >= 4), "")
    return bool(company_token and re.search(rf"(?i)(?<!\w){re.escape(company_token)}(?!\w)", text))


def acquire_explicit_fmp_research(
    ticker: str, *, production_row: Mapping[str, Any] | None,
    api_key: str = "", client: FMPStableClient | None = None,
    cache_root: str | Path = DEFAULT_CACHE_ROOT, force_refresh: bool = False,
) -> dict[str, Any]:
    """Acquire bounded FMP evidence for one explicitly researched ticker."""
    acquisition_started = time.monotonic()
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        raise ValueError("explicit Research ticker is required")
    diagnostics = {
        "version": FMP_RESEARCH_ACQUISITION_VERSION, "symbol": symbol,
        "request_ceiling": MAX_EXPLICIT_RESEARCH_REQUESTS,
        "requests": 0, "provider_attempts": 0, "fresh_cache_hits": 0,
        "live_family_refreshes": 0, "stale_fallbacks": 0,
        "temporarily_unavailable": 0, "outcomes": {}, "endpoint_seconds": {},
        "family_seconds": {},
    }
    if client is None and not str(api_key or "").strip():
        context = build_research_context(symbol, production_row=production_row)
        diagnostics["temporarily_unavailable"] = len(_CORPORATE_FAMILIES) + 1
        diagnostics["total_acquisition_seconds"] = round(max(0.0, time.monotonic() - acquisition_started), 6)
        return {"research_context": context, "diagnostics": diagnostics}

    session = _Session(client or FMPStableClient(api_key, timeout_seconds=12, retries=1))
    families: dict[str, dict[str, Any]] = {}
    profile_name: str | None = None

    def profile_fetch() -> tuple[dict[str, Any], bool]:
        nonlocal profile_name
        response, rows = _request_records(session, "profile", symbol)
        profiles = [normalize_profile(row, fetched_at=response.fetched_at) for row in rows]
        peer_response, peer_rows = _request_records(session, "stock-peers", symbol)
        peers = [normalize_peers(row, fetched_at=peer_response.fetched_at) for row in peer_rows]
        good_profiles = [row for row in profiles if _available(row)]
        profile_name = good_profiles[0].get("company_name") if good_profiles else None
        data = {"profile": good_profiles[0] if good_profiles else None, "peers": peers[0].get("peers", []) if peers else []}
        env = _envelope(symbol, "profile", "profile+stock-peers", response.fetched_at, data, good_profiles + [p for p in peers if _available(p)])
        return env, response.successful and peer_response.successful

    families["profile"] = _refresh_family(symbol, "profile", profile_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)
    cached_profile = (families["profile"].get("data") or {}).get("profile") if isinstance(families["profile"].get("data"), Mapping) else None
    if isinstance(cached_profile, Mapping):
        profile_name = cached_profile.get("company_name")
    security = security_type_of(production_row or cached_profile)

    if security != "ETF":
        def statements_fetch() -> tuple[dict[str, Any], bool]:
            normalized: dict[str, list[dict[str, Any]]] = {}
            responses = []
            for endpoint, kind in (("income-statement", "income_statement"), ("balance-sheet-statement", "balance_sheet"), ("cash-flow-statement", "cash_flow")):
                response, rows = _request_records(session, endpoint, symbol, period="quarter", limit=8)
                responses.append(response)
                normalized[kind] = [normalize_financial_statement(row, statement_type=kind, fetched_at=response.fetched_at) for row in rows]
            records = [row for values in normalized.values() for row in values]
            env = _envelope(symbol, "financial_statements", "income+balance+cash-flow", responses[0].fetched_at, normalized, records)
            return env, all(response.successful for response in responses)
        families["financial_statements"] = _refresh_family(symbol, "financial_statements", statements_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)

        def ratios_fetch() -> tuple[dict[str, Any], bool]:
            metrics_response, metrics_rows = _request_records(session, "key-metrics", symbol, period="quarter", limit=8)
            ratios_response, ratio_rows = _request_records(session, "ratios", symbol, period="quarter", limit=8)
            metrics = [normalize_key_metrics(row, fetched_at=metrics_response.fetched_at) for row in metrics_rows]
            ratios = [normalize_ratios(row, fetched_at=ratios_response.fetched_at) for row in ratio_rows]
            return _envelope(symbol, "ratios_key_metrics", "key-metrics+ratios", metrics_response.fetched_at, {"key_metrics": metrics, "ratios": ratios}, metrics + ratios), metrics_response.successful and ratios_response.successful
        families["ratios_key_metrics"] = _refresh_family(symbol, "ratios_key_metrics", ratios_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)

        def growth_fetch() -> tuple[dict[str, Any], bool]:
            response, rows = _request_records(session, "financial-growth", symbol, period="quarter", limit=8)
            records = [normalize_financial_growth(row, fetched_at=response.fetched_at) for row in rows]
            return _envelope(symbol, "growth_segments", "financial-growth", response.fetched_at, {"growth_history": records, "segment_data": None}, records, limitations=("Revenue segment acquisition is not activated in FIRST.3.",)), response.successful
        families["growth_segments"] = _refresh_family(symbol, "growth_segments", growth_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)

        def earnings_fetch() -> tuple[dict[str, Any], bool]:
            response, rows = _request_records(session, "earnings", symbol, limit=12)
            records = [normalize_earnings_record(row, fetched_at=response.fetched_at) for row in rows]
            intelligence = build_earnings_intelligence(records)
            as_of = str(response.fetched_at or "")[:10]
            future_events = [record for record in records if not record.get("reported_period") and str(record.get("report_date") or "") >= as_of]
            future_events.sort(key=lambda record: str(record.get("report_date") or ""))
            next_event = future_events[0] if future_events else None
            return _envelope(symbol, "earnings_history", "earnings", response.fetched_at, {"records": records, "earnings_intelligence": intelligence, "next_earnings_event": next_event}, records, available=intelligence.get("semantic_status") == AVAILABLE or next_event is not None), response.successful
        families["earnings_history"] = _refresh_family(symbol, "earnings_history", earnings_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)

        def estimates_fetch() -> tuple[dict[str, Any], bool]:
            response, rows = _request_records(session, "analyst-estimates", symbol, period="annual", limit=12)
            records = [normalize_analyst_estimate(row, fetched_at=response.fetched_at) for row in rows]
            return _envelope(symbol, "analyst_estimates", "analyst-estimates", response.fetched_at, {"estimates": records, "estimate_vintage_status": "NOT_POINT_IN_TIME_VINTAGE"}, records), response.successful
        families["analyst_estimates"] = _refresh_family(symbol, "analyst_estimates", estimates_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)

        def consensus_fetch() -> tuple[dict[str, Any], bool]:
            normalized: dict[str, Any] = {}
            records: list[dict[str, Any]] = []
            responses = []
            for endpoint in ("grades-consensus", "price-target-consensus", "price-target-summary"):
                response, rows = _request_records(session, endpoint, symbol)
                responses.append(response)
                if endpoint == "grades-consensus":
                    values = [normalize_analyst_consensus(row, fetched_at=response.fetched_at) for row in rows]
                else:
                    values = [normalize_price_target(row, endpoint_family=endpoint, fetched_at=response.fetched_at) for row in rows]
                normalized[endpoint.replace("-", "_")] = values
                records.extend(values)
            return _envelope(symbol, "analyst_consensus_targets", "+".join(("grades-consensus", "price-target-consensus", "price-target-summary")), responses[0].fetched_at, normalized, records, limitations=("Wall Street consensus is separate from canonical Atlas Fair Value.",)), all(response.successful for response in responses)
        families["analyst_consensus_targets"] = _refresh_family(symbol, "analyst_consensus_targets", consensus_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)

        def actions_fetch() -> tuple[dict[str, Any], bool]:
            response, rows = _request_records(session, "grades", symbol, limit=1000)
            records = [normalize_analyst_action(row, fetched_at=response.fetched_at) for row in rows]
            records = [row for row in records if _available(row)]
            for record in records:
                record.update({
                    "current_rating": record.get("to_grade"),
                    "previous_rating": record.get("from_grade"),
                    "provider": "FMP", "source_family": "grades",
                })
            records.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("firm") or ""), str(row.get("action") or "")), reverse=True)
            records = records[:MAX_ANALYST_ACTIONS]
            return _envelope(symbol, "analyst_actions", "grades", response.fetched_at, {"actions": records, "retained_cap": MAX_ANALYST_ACTIONS}, records), response.successful
        families["analyst_actions"] = _refresh_family(symbol, "analyst_actions", actions_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)

        def ownership_summary_fetch() -> tuple[dict[str, Any], bool]:
            summary_response, summary_rows = _request_records(session, "institutional-ownership/symbol-positions-summary", symbol)
            summaries = [normalize_institutional_ownership_summary(row, fetched_at=summary_response.fetched_at) for row in summary_rows]
            return _envelope(symbol, "institutional_ownership", "institutional-ownership/symbol-positions-summary", summary_response.fetched_at, {"summary": summaries}, summaries, limitations=("Evidence is available only from its filing date; missing filing dates fail closed.",)), summary_response.successful

        def holders_fetch() -> tuple[dict[str, Any], bool]:
            holder_response, holder_rows = _request_records(session, "funds/disclosure-holders-latest", symbol, limit=1000)
            holders = [normalize_fund_disclosure(row, fetched_at=holder_response.fetched_at) for row in holder_rows]
            holders = [row for row in holders if _available(row)]
            holders.sort(key=lambda row: (
                row.get("weight") is not None, row.get("weight") or float("-inf"),
                row.get("market_value") is not None, row.get("market_value") or float("-inf"),
                row.get("shares") is not None, row.get("shares") or float("-inf"),
                str(row.get("investor_name") or ""),
            ), reverse=True)
            holders = holders[:MAX_INSTITUTIONAL_HOLDERS]
            return _envelope(symbol, "institutional_ownership", "funds/disclosure-holders-latest", holder_response.fetched_at, {"holders": holders, "holder_cap": MAX_INSTITUTIONAL_HOLDERS}, holders, limitations=("Holdings are available only from their filing date; missing filing dates fail closed.",)), holder_response.successful

        summary_env = _refresh_family(symbol, "institutional_ownership", ownership_summary_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)
        holder_env = _refresh_family(symbol, "holders_13f", holders_fetch, cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)
        ownership_available = summary_env.get("semantic_status") == AVAILABLE or holder_env.get("semantic_status") == AVAILABLE
        ownership_data = {
            "summary": ((summary_env.get("data") or {}).get("summary") if isinstance(summary_env.get("data"), Mapping) else []) or [],
            "holders": ((holder_env.get("data") or {}).get("holders") if isinstance(holder_env.get("data"), Mapping) else []) or [],
            "holder_cap": MAX_INSTITUTIONAL_HOLDERS,
        }
        families["institutional_ownership"] = evidence_envelope(
            ticker=symbol, family="institutional_ownership",
            semantic_status=AVAILABLE if ownership_available else DATA_UNAVAILABLE,
            cache_status=("FRESH_CACHE" if {summary_env.get("cache_status"), holder_env.get("cache_status")} == {"FRESH_CACHE"} else "STALE_FALLBACK" if "STALE_FALLBACK" in {summary_env.get("cache_status"), holder_env.get("cache_status")} else "FETCHED" if ownership_available else "TEMPORARILY_UNAVAILABLE"),
            provider="FMP", endpoint_family="institutional-summary+fund-disclosures",
            fetched_at=max(filter(None, (summary_env.get("fetched_at"), holder_env.get("fetched_at"))), default=None),
            reporting_date=summary_env.get("reporting_date") or holder_env.get("reporting_date"),
            filing_date=summary_env.get("filing_date") or holder_env.get("filing_date"),
            data=ownership_data if ownership_available else None,
            evidence_ids=list(summary_env.get("evidence_ids") or []) + list(holder_env.get("evidence_ids") or []),
            limitations=tuple(summary_env.get("limitations") or ()) + tuple(holder_env.get("limitations") or ()),
        )

        def news_fetch(endpoint: str, family: str) -> tuple[dict[str, Any], bool]:
            response = session.get(endpoint, {"symbols": symbol, "limit": 50})
            rows = _rows(response.payload) if response.successful else []
            relevant = [row for row in rows if _relevant_news(row, symbol, profile_name)]
            records = [normalize_fmp_news(row, symbol=symbol, endpoint_family=endpoint, fetched_at=response.fetched_at) for row in relevant]
            records = [row for row in records if _available(row)]
            records.sort(key=lambda row: str(row.get("published_at") or ""), reverse=True)
            return _envelope(symbol, family, endpoint, response.fetched_at, {"articles": records[:20], "provider_rows": len(rows), "relevance_rejected": len(rows) - len(relevant)}, records[:20]), response.successful
        families["company_news"] = _refresh_family(symbol, "company_news", lambda: news_fetch("news/stock", "company_news"), cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)
        families["press_releases"] = _refresh_family(symbol, "press_releases", lambda: news_fetch("news/press-releases", "press_releases"), cache_root=cache_root, diagnostics=diagnostics, force_refresh=force_refresh)

    # SEC evidence is never acquired from FMP in FIRST.3.
    sec_available = bool((production_row or {}).get("v42_sec_available") or (production_row or {}).get("sec_filings"))
    families["sec_filings"] = evidence_envelope(
        ticker=symbol, family="sec_filings",
        semantic_status=AVAILABLE if sec_available else DATA_UNAVAILABLE,
        cache_status="PERSISTED_PRODUCTION" if sec_available else "TEMPORARILY_UNAVAILABLE",
        provider="SEC", endpoint_family="SEC_EDGAR_EXISTING",
        fetched_at=(production_row or {}).get("generated_at"),
        data={"filings": (production_row or {}).get("sec_filings")} if sec_available else None,
        limitations=() if sec_available else ("No verified SEC filing evidence is available in the production row.",),
    )
    context = build_research_context(symbol, production_row=production_row, evidence_families=families, security_type=security)
    diagnostics.update({
        "requests": session.calls, "provider_attempts": session.provider_attempts,
        "outcomes": dict(session.outcomes),
        "endpoint_seconds": {key: round(value, 6) for key, value in session.endpoint_seconds.items()},
        "total_provider_seconds": round(sum(session.endpoint_seconds.values()), 6),
        "total_acquisition_seconds": round(max(0.0, time.monotonic() - acquisition_started), 6),
    })
    return {"research_context": context, "diagnostics": diagnostics}


__all__ = [
    "FMP_RESEARCH_ACQUISITION_VERSION", "MAX_ANALYST_ACTIONS",
    "MAX_EXPLICIT_RESEARCH_REQUESTS", "MAX_INSTITUTIONAL_HOLDERS",
    "acquire_explicit_fmp_research",
]
