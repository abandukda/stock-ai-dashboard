"""Optional post-shell FMP intelligence acquisition for Phase 1.

This module is intentionally absent from the synchronous explicit-Research
acquisition graph. Ordinary callers only read its independent caches.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Final, Mapping

from engines.fmp_normalization import (
    latest_valid_transcript_period,
    normalize_insider_transaction,
    normalize_price_target_action,
    normalize_transcript_content,
    normalize_transcript_period,
)
from engines.research_context import evidence_envelope, stable_evidence_id
from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE, NOT_APPLICABLE
from engines.transcript_intelligence import TRANSCRIPT_SYNTHESIS_VERSION, derive_transcript_intelligence
from services.analyst_estimate_snapshot_store import revision_summary
from services.fmp_stable_client import FMPStableClient
from services.research_family_cache import DEFAULT_CACHE_ROOT, load_family_envelope, save_family_envelope


PHASE1_INTELLIGENCE_VERSION: Final = "FMP_PHASE1_INTELLIGENCE_V1"
POST_SHELL_REQUEST_CEILING: Final = 2
MAX_TARGET_ACTIONS: Final = 25
MAX_INSIDER_TRANSACTIONS: Final = 50


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        return [payload] if payload else []
    return []


def _unavailable(ticker: str, family: str, limitation: str, *, status: str = DATA_UNAVAILABLE) -> dict[str, Any]:
    return evidence_envelope(
        ticker=ticker, family=family, semantic_status=status,
        cache_status="NOT_APPLICABLE" if status == NOT_APPLICABLE else "TEMPORARILY_UNAVAILABLE",
        limitations=(limitation,),
    )


def _load_bounded(ticker: str, family: str, *, cache_root: str | Path, max_age: int | None = None) -> dict[str, Any] | None:
    if family == "transcript_intelligence":
        try:
            value = json.loads((Path(cache_root) / family / f"{ticker}.latest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            value = None
    else:
        value = load_family_envelope(ticker, family, root=cache_root, allow_stale=True)
    if value and max_age is not None and float(value.get("age_seconds") or 0) > max_age:
        return None
    return value


def load_cached_phase1_families(
    ticker: str, *, security_type: str = "EQUITY", cache_root: str | Path = DEFAULT_CACHE_ROOT,
) -> dict[str, dict[str, Any]]:
    symbol = str(ticker or "").strip().upper()
    families = ("transcript_index", "transcript_intelligence", "analyst_price_target_actions", "insider_transactions")
    if str(security_type).upper() in {"ETF", "FUND", "MUTUALFUND"}:
        result = {family: _unavailable(symbol, family, "Corporate evidence does not apply to ETFs.", status=NOT_APPLICABLE) for family in families}
    else:
        result = {}
        for family in families:
            max_age = 24 * 3600 if family in {"analyst_price_target_actions", "insider_transactions"} else None
            result[family] = _load_bounded(symbol, family, cache_root=cache_root, max_age=max_age) or _unavailable(
                symbol, family, "Optional Phase 1 evidence has not been acquired or its cache expired."
            )
    revisions = revision_summary(symbol)
    result["analyst_estimate_snapshots"] = evidence_envelope(
        ticker=symbol, family="analyst_estimate_snapshots",
        semantic_status=revisions["semantic_status"], cache_status="SCHEDULED_SNAPSHOT_STORE",
        provider="FMP", endpoint_family="analyst-estimates", data=revisions,
        evidence_ids=[
            evidence_id for item in revisions.get("comparisons", [])
            for evidence_id in item.get("source_evidence_ids", []) if evidence_id
        ],
        limitations=((revisions.get("status_detail"),) if revisions.get("status_detail") else ()),
    )
    return result


def refresh_post_shell_evidence(
    ticker: str, *, api_key: str, security_type: str = "EQUITY",
    cache_root: str | Path = DEFAULT_CACHE_ROOT, client: FMPStableClient | None = None,
) -> dict[str, Any]:
    """Refresh target/insider evidence only after explicit post-shell action."""
    symbol = str(ticker or "").strip().upper()
    if str(security_type).upper() in {"ETF", "FUND", "MUTUALFUND"}:
        return {"provider_calls": 0, "families": load_cached_phase1_families(symbol, security_type="ETF", cache_root=cache_root)}
    transport = client or FMPStableClient(api_key, timeout_seconds=8, retries=0)
    calls = 0

    target_response = transport.get("price-target-news", {"symbol": symbol, "limit": 25})
    calls += int(target_response.attempts > 0)
    targets = [normalize_price_target_action(row, fetched_at=target_response.fetched_at) for row in _rows(target_response.payload)] if target_response.successful else []
    targets = [row for row in targets if row.get("semantic_status") == AVAILABLE][:MAX_TARGET_ACTIONS]
    target_ids = [stable_evidence_id(
        ticker=symbol, family="analyst_price_target_actions", provider="FMP",
        semantic_identity=f"{row.get('analyst_name')}:{row.get('firm_or_publisher')}:{row.get('action_date')}:{row.get('price_target')}",
        observation_date=row.get("action_date"), provenance="price-target-news",
    ) for row in targets]
    for row, evidence_id in zip(targets, target_ids):
        row["evidence_id"] = evidence_id
    target_env = evidence_envelope(
        ticker=symbol, family="analyst_price_target_actions",
        semantic_status=AVAILABLE if targets else DATA_UNAVAILABLE,
        cache_status="FETCHED", provider="FMP", endpoint_family="price-target-news",
        fetched_at=target_response.fetched_at, data={"actions": targets, "prior_target_status": "PRIOR_TARGET_NOT_PROVEN"} if targets else None,
        evidence_ids=target_ids, limitations=("Prior target and currency are not proven by this endpoint schema.",),
    )
    if target_response.successful:
        save_family_envelope(symbol, "analyst_price_target_actions", target_env, root=cache_root)

    insider_response = transport.get("insider-trading/search", {"symbol": symbol, "limit": 50})
    calls += int(insider_response.attempts > 0)
    insiders = [normalize_insider_transaction(row, fetched_at=insider_response.fetched_at) for row in _rows(insider_response.payload)] if insider_response.successful else []
    insiders = [row for row in insiders if row.get("semantic_status") == AVAILABLE][:MAX_INSIDER_TRANSACTIONS]
    insider_ids = [stable_evidence_id(
        ticker=symbol, family="insider_transactions", provider="FMP",
        semantic_identity=f"{row.get('reporting_cik')}:{row.get('transaction_date')}:{row.get('filing_identity')}:{row.get('transaction_type')}",
        observation_date=row.get("transaction_date"), filing_date=row.get("filing_date"), provenance="insider-trading/search",
    ) for row in insiders]
    for row, evidence_id in zip(insiders, insider_ids):
        row["evidence_id"] = evidence_id
    insider_env = evidence_envelope(
        ticker=symbol, family="insider_transactions",
        semantic_status=AVAILABLE if insiders else DATA_UNAVAILABLE,
        cache_status="FETCHED", provider="FMP", endpoint_family="insider-trading/search",
        fetched_at=insider_response.fetched_at, data={"transactions": insiders, "context_authority": "CONTEXT_ONLY"} if insiders else None,
        evidence_ids=insider_ids, limitations=("Context only; no transaction value or scoring effect is calculated.",),
    )
    if insider_response.successful:
        save_family_envelope(symbol, "insider_transactions", insider_env, root=cache_root)
    if calls > POST_SHELL_REQUEST_CEILING:
        raise RuntimeError("Phase 1 post-shell request ceiling exceeded")
    return {"provider_calls": calls, "families": {"analyst_price_target_actions": target_env, "insider_transactions": insider_env}}


def acquire_latest_transcript_intelligence(
    ticker: str, *, api_key: str, cache_root: str | Path = DEFAULT_CACHE_ROOT,
    client: FMPStableClient | None = None,
) -> dict[str, Any]:
    """Explicitly acquire the latest transcript; never called by ordinary Research."""
    index = acquire_transcript_index(ticker, api_key=api_key, cache_root=cache_root, client=client)
    periods = ((index.get("family") or {}).get("data") or {}).get("periods", [])
    latest = latest_valid_transcript_period(periods)
    if not latest:
        return {
            "provider_calls": index["provider_calls"],
            "family": _unavailable(str(ticker).upper(), "transcript_intelligence", "No valid transcript period was returned."),
            "operation_metadata": _transcript_operation_metadata(
                ticker, None, None, index["provider_calls"], "UNAVAILABLE", None
            ),
        }
    return acquire_transcript_intelligence(
        ticker,
        year=int(latest["fiscal_year"]),
        quarter=int(latest["fiscal_quarter"]),
        api_key=api_key,
        cache_root=cache_root,
        client=client,
        _index_result=index,
    )


def _transcript_operation_metadata(
    ticker: str, year: int | None, quarter: int | None, provider_calls: int,
    cache_status: str, evidence_id: str | None,
) -> dict[str, Any]:
    """Sanitized operation evidence; never includes transcript/provider payloads."""
    return {
        "ticker": str(ticker or "").strip().upper(),
        "selected_year": year,
        "selected_quarter": quarter,
        "transcript_evidence_id": evidence_id,
        "cache_status": cache_status,
        "provider_call_count": provider_calls,
        "synthesis_version": TRANSCRIPT_SYNTHESIS_VERSION,
    }


def acquire_transcript_index(
    ticker: str, *, api_key: str, cache_root: str | Path = DEFAULT_CACHE_ROOT,
    client: FMPStableClient | None = None,
) -> dict[str, Any]:
    """Explicitly fetch/cache the transcript index without loading transcript bodies."""
    symbol = str(ticker or "").strip().upper()
    transport = client or FMPStableClient(api_key, timeout_seconds=12, retries=0)
    calls = 0
    index_env = load_family_envelope(symbol, "transcript_index", root=cache_root, allow_stale=False)
    if index_env:
        periods = (index_env.get("data") or {}).get("periods", []) if isinstance(index_env.get("data"), Mapping) else []
    else:
        response = transport.get("earning-call-transcript-dates", {"symbol": symbol})
        calls += int(response.attempts > 0)
        periods = [normalize_transcript_period(row, fetched_at=response.fetched_at) for row in _rows(response.payload)] if response.successful else []
        periods = [row for row in periods if row.get("fiscal_year") and row.get("fiscal_quarter")]
        ids = [stable_evidence_id(
            ticker=symbol, family="transcript_index", provider="FMP",
            semantic_identity=f"{row.get('fiscal_year')}:Q{row.get('fiscal_quarter')}",
            observation_date=row.get("transcript_date"), provenance="earning-call-transcript-dates",
        ) for row in periods]
        index_env = evidence_envelope(
            ticker=symbol, family="transcript_index", semantic_status=AVAILABLE if periods else DATA_UNAVAILABLE,
            cache_status="FETCHED", provider="FMP", endpoint_family="earning-call-transcript-dates",
            fetched_at=response.fetched_at, data={"periods": periods} if periods else None,
            evidence_ids=ids, limitations=(),
        )
        if response.successful:
            save_family_envelope(symbol, "transcript_index", index_env, root=cache_root)
    return {"provider_calls": calls, "family": index_env}


def acquire_transcript_intelligence(
    ticker: str, *, year: int, quarter: int, api_key: str,
    cache_root: str | Path = DEFAULT_CACHE_ROOT, client: FMPStableClient | None = None,
    _index_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Explicitly load one provider-indexed period and derive safe intelligence."""
    symbol = str(ticker or "").strip().upper()
    if quarter not in {1, 2, 3, 4}:
        raise ValueError("quarter must be one of 1, 2, 3, 4")
    transport = client or FMPStableClient(api_key, timeout_seconds=12, retries=0)
    index_result = dict(_index_result or acquire_transcript_index(
        symbol, api_key=api_key, cache_root=cache_root, client=transport
    ))
    calls = int(index_result.get("provider_calls") or 0)
    periods = ((index_result.get("family") or {}).get("data") or {}).get("periods", [])
    indexed = any(
        int(item.get("fiscal_year") or 0) == int(year)
        and int(item.get("fiscal_quarter") or 0) == int(quarter)
        for item in periods if isinstance(item, Mapping)
    )
    if not indexed:
        family = _unavailable(symbol, "transcript_intelligence", "Transcript commentary unavailable for this quarter.")
        metadata = _transcript_operation_metadata(symbol, year, quarter, calls, "UNAVAILABLE", None)
        return {"provider_calls": calls, "family": family, "period": f"{year}-Q{quarter}", "operation_metadata": metadata}
    period_key = f"{year}-Q{quarter}"
    content_cache = load_family_envelope(symbol, "transcript_content", root=cache_root, period_key=period_key)
    content_cache_hit = bool(content_cache)
    if content_cache:
        transcript = content_cache.get("transcript") if isinstance(content_cache.get("transcript"), Mapping) else {}
    else:
        response = transport.get("earning-call-transcript", {"symbol": symbol, "year": year, "quarter": quarter})
        calls += int(response.attempts > 0)
        normalized = [normalize_transcript_content(row, requested_year=year, requested_quarter=quarter, fetched_at=response.fetched_at) for row in _rows(response.payload)] if response.successful else []
        transcript = next((row for row in normalized if row.get("semantic_status") == AVAILABLE), {})
        if transcript:
            save_family_envelope(symbol, "transcript_content", {"fetched_at": response.fetched_at, "transcript": transcript}, root=cache_root, period_key=period_key)
    if not transcript:
        family = _unavailable(symbol, "transcript_intelligence", "Transcript commentary unavailable for this quarter.")
        metadata = _transcript_operation_metadata(symbol, year, quarter, calls, "UNAVAILABLE", None)
        return {"provider_calls": calls, "family": family, "period": period_key, "operation_metadata": metadata}
    evidence_id = stable_evidence_id(
        ticker=symbol, family="transcript_intelligence", provider="FMP",
        semantic_identity=f"{year}:Q{quarter}:{transcript.get('call_date')}",
        observation_date=transcript.get("call_date"), reporting_date=f"{year}-Q{quarter}", provenance="earning-call-transcript",
    )
    synthesis_key = f"{period_key}-{evidence_id}-{TRANSCRIPT_SYNTHESIS_VERSION}"
    intelligence_env = load_family_envelope(symbol, "transcript_intelligence", root=cache_root, period_key=synthesis_key)
    if not intelligence_env:
        intelligence = derive_transcript_intelligence(transcript, evidence_id=evidence_id)
        intelligence_env = evidence_envelope(
            ticker=symbol, family="transcript_intelligence", semantic_status=intelligence.get("semantic_status", DATA_UNAVAILABLE),
            cache_status="FETCHED", provider="FMP", endpoint_family="earning-call-transcript",
            fetched_at=datetime.now(timezone.utc).isoformat(), observation_date=transcript.get("call_date"),
            reporting_date=f"{year}-Q{quarter}", data=intelligence, evidence_ids=(evidence_id,),
            limitations=intelligence.get("limitations", ()),
        )
        save_family_envelope(symbol, "transcript_intelligence", intelligence_env, root=cache_root, period_key=synthesis_key)
    if calls > POST_SHELL_REQUEST_CEILING:
        raise RuntimeError("Phase 1 transcript request ceiling exceeded")
    if calls == 0:
        cache_status = "CACHE_HIT"
    elif calls >= 2:
        cache_status = "COLD_INDEX_AND_CONTENT"
    elif content_cache_hit:
        cache_status = "COLD_INDEX"
    else:
        cache_status = "COLD_CONTENT"
    metadata = _transcript_operation_metadata(symbol, year, quarter, calls, cache_status, evidence_id)
    intelligence_env = dict(intelligence_env)
    intelligence_env["operation_metadata"] = metadata
    # The replaceable selected-period pointer contains derived evidence and
    # sanitized operation metadata only, never raw transcript text.
    latest_pointer = dict(intelligence_env)
    latest_pointer["fetched_at"] = datetime.now(timezone.utc).isoformat()
    path = Path(cache_root) / "transcript_intelligence" / f"{symbol}.latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(latest_pointer, sort_keys=True, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)
    return {"provider_calls": calls, "family": intelligence_env, "period": period_key, "operation_metadata": metadata}


__all__ = [
    "MAX_INSIDER_TRANSACTIONS", "MAX_TARGET_ACTIONS", "PHASE1_INTELLIGENCE_VERSION",
    "POST_SHELL_REQUEST_CEILING", "acquire_latest_transcript_intelligence",
    "acquire_transcript_index", "acquire_transcript_intelligence",
    "load_cached_phase1_families", "refresh_post_shell_evidence",
]
