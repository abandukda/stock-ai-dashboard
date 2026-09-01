"""Canonical research context with an immutable production-decision boundary.

FIRST.2 is an architecture layer only.  It reads an already-produced scan row,
normalizes refreshable research evidence, and never invokes investment logic or
chooses a provider.  Provider ownership remains descriptive governance metadata.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Iterable, Mapping

from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE, NOT_APPLICABLE


RESEARCH_CONTEXT_VERSION: Final = "RESEARCH_CONTEXT_V1"
TOP_ANALYST_ACTIONS_VERSION: Final = "TOP_ANALYST_ACTIONS_V1"
RESEARCH_SYNTHESIS_VERSION: Final = "ATLAS_RESEARCH_SYNTHESIS_V2"

EVIDENCE_FAMILIES: Final[tuple[str, ...]] = (
    "profile",
    "financial_statements",
    "ratios_key_metrics",
    "growth_segments",
    "earnings_history",
    "analyst_estimates",
    "analyst_consensus_targets",
    "analyst_actions",
    "institutional_ownership",
    "company_news",
    "press_releases",
    "sec_filings",
    "transcript_index",
    "transcript_intelligence",
    "analyst_price_target_actions",
    "insider_transactions",
    "analyst_estimate_snapshots",
    "management_guidance",
    "technicals",
    "etf_research",
)

CORPORATE_ONLY_FAMILIES: Final = frozenset({
    "financial_statements",
    "ratios_key_metrics",
    "growth_segments",
    "earnings_history",
    "analyst_estimates",
    "analyst_consensus_targets",
    "analyst_actions",
    "institutional_ownership",
    "company_news",
    "press_releases",
    "transcript_index",
    "transcript_intelligence",
    "analyst_price_target_actions",
    "insider_transactions",
    "analyst_estimate_snapshots",
    "management_guidance",
})

SYNTHESIS_SECTIONS: Final[tuple[str, ...]] = (
    "atlas_view",
    "why_atlas_likes_it",
    "what_changed_recently",
    "earnings_trend",
    "management_guidance",
    "analyst_view",
    "top_5_analyst_actions",
    "valuation",
    "technical_setup",
    "institutional_insider_context",
    "major_catalysts",
    "key_risks",
    "what_to_watch_next",
)

_RAW_KEYS: Final = frozenset({
    "raw", "raw_payload", "provider_payload", "response_body",
    "authenticated_url", "api_key", "credentials", "headers",
})


class FrozenDict(dict[str, Any]):
    """JSON-serializable dict that rejects mutation after construction."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("production_decision is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __copy__(self) -> "FrozenDict":
        return self

    def __deepcopy__(self, _memo: dict[int, Any]) -> "FrozenDict":
        return self


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            value = row.get(key)
            if value is not None and not (isinstance(value, str) and not value.strip()):
                return value
    return None


def _finite(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None
    return value


def security_type_of(row: Mapping[str, Any] | None) -> str:
    source = row or {}
    value = str(_first(source, "security_type", "quote_type", "quoteType") or "EQUITY").upper()
    return "ETF" if value in {"ETF", "FUND", "MUTUALFUND"} else "EQUITY"


def build_production_decision(production_row: Mapping[str, Any] | None) -> FrozenDict:
    """Extract decision outputs without calculating, defaulting, or substituting."""
    if not production_row:
        return FrozenDict({"semantic_status": DATA_UNAVAILABLE})

    recommendation = _first(
        production_row, "Recommendation", "recommendation", "committee_verdict",
        "action_code",
    )
    buy_now = _first(production_row, "buy_now", "is_buy_now", "BUY NOW")
    if buy_now is None and recommendation is not None:
        buy_now = str(recommendation).upper().replace(" ", "_") == "BUY_NOW"

    decision = {
        "semantic_status": AVAILABLE,
        "recommendation": recommendation,
        # Generic ``score`` is the legacy confidence/conviction value in the
        # persisted scan. It is not canonical Opportunity authority.
        "opportunity": _first(production_row, "Opportunity", "opportunity_score", "Opportunity Score"),
        "confidence": _first(production_row, "Confidence", "confidence", "confidence_pct"),
        "buy_now": buy_now,
        "ranking": _first(production_row, "ranking", "rank", "relative_rank_score"),
        "atlas_fair_value": _first(production_row, "atlas_fair_value", "Atlas Fair Value"),
        "decision_expected_return": _first(
            production_row, "decision_expected_return_pct", "expected_return_pct",
            "expected_upside_pct", "Expected Return",
        ),
        "entry_low": _first(production_row, "preferred_entry_low", "entry_low", "Entry Low"),
        "entry_high": _first(production_row, "preferred_entry_high", "entry_high", "Entry High"),
        "decision_target": _first(production_row, "decision_target", "target", "Target"),
        "trade_target_1": _first(production_row, "trade_target_1", "target_1", "Target 1"),
        "trade_target_2": _first(production_row, "trade_target_2", "target_2", "Target 2"),
        "stop": _first(production_row, "stop_loss", "stop", "Stop"),
        "position_sizing": _first(production_row, "position_size_range", "position_sizing", "Position Size"),
        "production_scan_timestamp": _first(
            production_row, "scan_time", "generated_at", "production_scan_timestamp",
        ),
    }
    return FrozenDict({key: _finite(value) for key, value in decision.items()})


def load_production_row(ticker: str, scan_path: str | Path = "market_full_scan.json") -> dict[str, Any] | None:
    """Read the latest persisted scan row; never fetch or calculate a decision."""
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return None
    try:
        payload = json.loads(Path(scan_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    rows = payload if isinstance(payload, list) else payload.get("rows", []) if isinstance(payload, dict) else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("ticker") or row.get("Ticker") or "").upper() == symbol:
            return row
    return None


def stable_evidence_id(
    *, ticker: str, family: str, provider: str, semantic_identity: str,
    observation_date: Any = None, reporting_date: Any = None,
    filing_date: Any = None, provenance: Any = None,
) -> str:
    identity = {
        "ticker": str(ticker).upper().strip(),
        "family": family,
        "provider": provider,
        "semantic_identity": semantic_identity,
        "observation_date": observation_date,
        "reporting_date": reporting_date,
        "filing_date": filing_date,
        "provenance": provenance,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return f"ev_{digest[:24]}"


def _assert_normalized(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _RAW_KEYS:
                raise ValueError(f"raw provider field is prohibited: {key}")
            _assert_normalized(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_normalized(nested)


def evidence_envelope(
    *, ticker: str, family: str, semantic_status: str = DATA_UNAVAILABLE,
    cache_status: str = "TEMPORARILY_UNAVAILABLE", provider: str | None = None,
    endpoint_family: str | None = None, fetched_at: str | None = None,
    observation_date: Any = None, reporting_date: Any = None,
    filing_date: Any = None, age_seconds: float | None = None,
    data: Any = None, evidence_ids: Iterable[str] = (),
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    if family not in EVIDENCE_FAMILIES:
        raise ValueError(f"unknown evidence family: {family}")
    _assert_normalized(data)
    return {
        "semantic_status": semantic_status,
        "cache_status": cache_status,
        "provider": provider,
        "endpoint_family": endpoint_family,
        "fetched_at": fetched_at,
        "observation_date": observation_date,
        "reporting_date": reporting_date,
        "filing_date": filing_date,
        "age_seconds": age_seconds,
        "data": data,
        "evidence_ids": list(evidence_ids),
        "limitations": list(limitations),
    }


def customer_freshness_label(envelope: Mapping[str, Any], *, production: bool = False) -> str:
    if production:
        return "Latest Production Scan"
    if envelope.get("semantic_status") == DATA_UNAVAILABLE:
        return "Data Unavailable"
    if envelope.get("semantic_status") == NOT_APPLICABLE:
        return "Evidence Limited"
    cache_status = str(envelope.get("cache_status") or "")
    if cache_status in {"FETCHED", "REFRESHED"}:
        return "Fresh"
    if cache_status in {"FRESH_CACHE", "STALE_FALLBACK"}:
        return "Cached"
    return "Evidence Limited"


def top_analyst_actions_contract(actions: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    normalized = []
    for action in list(actions)[:5]:
        normalized.append({
            key: action.get(key)
            for key in ("firm", "action", "current_rating", "previous_rating", "date", "provider", "source_family", "evidence_id")
        })
    return {
        "version": TOP_ANALYST_ACTIONS_VERSION,
        "semantic_status": AVAILABLE if normalized else DATA_UNAVAILABLE,
        "actions": normalized,
    }


def research_synthesis_contract() -> dict[str, Any]:
    return {
        "version": RESEARCH_SYNTHESIS_VERSION,
        "semantic_status": DATA_UNAVAILABLE,
        "sections": {section: [] for section in SYNTHESIS_SECTIONS},
        "assertion_schema": {
            "text": None,
            "evidence_ids": [],
            "as_of": None,
            "confidence": None,
        },
    }


def build_research_context(
    ticker: str,
    *,
    production_row: Mapping[str, Any] | None,
    market_snapshot: Mapping[str, Any] | None = None,
    evidence_families: Mapping[str, Mapping[str, Any]] | None = None,
    generated_at: str | None = None,
    security_type: str | None = None,
) -> dict[str, Any]:
    symbol = str(ticker or "").strip().upper()
    security = security_type or security_type_of(production_row or market_snapshot)
    supplied = evidence_families or {}
    families: dict[str, dict[str, Any]] = {}
    registry: dict[str, list[str]] = {}
    for family in EVIDENCE_FAMILIES:
        if security == "ETF" and family in CORPORATE_ONLY_FAMILIES:
            envelope = evidence_envelope(
                ticker=symbol, family=family, semantic_status=NOT_APPLICABLE,
                cache_status="NOT_APPLICABLE", limitations=("Corporate evidence does not apply to ETFs.",),
            )
        elif family in supplied:
            envelope = dict(supplied[family])
            required = {
                "semantic_status", "cache_status", "provider", "endpoint_family",
                "fetched_at", "observation_date", "reporting_date", "filing_date",
                "age_seconds", "data", "evidence_ids", "limitations",
            }
            if set(envelope) != required:
                raise ValueError(f"invalid evidence envelope for {family}")
            _assert_normalized(envelope.get("data"))
        else:
            envelope = evidence_envelope(ticker=symbol, family=family)
        families[family] = envelope
        registry[family] = list(envelope.get("evidence_ids") or [])

    decision = build_production_decision(production_row)
    return {
        "version": RESEARCH_CONTEXT_VERSION,
        "ticker": symbol,
        "security_type": security,
        "generated_at": generated_at or _now_iso(),
        "production_decision": decision,
        "market_snapshot": dict(market_snapshot or {}),
        "evidence_families": families,
        "evidence_registry": registry,
        "synthesis": research_synthesis_contract(),
        "limitations": [] if production_row else ["No authoritative production decision is available for this ticker."],
    }


__all__ = [
    "CORPORATE_ONLY_FAMILIES", "EVIDENCE_FAMILIES", "FrozenDict",
    "RESEARCH_CONTEXT_VERSION", "RESEARCH_SYNTHESIS_VERSION", "SYNTHESIS_SECTIONS",
    "TOP_ANALYST_ACTIONS_VERSION", "build_production_decision", "build_research_context",
    "customer_freshness_label", "evidence_envelope", "load_production_row",
    "research_synthesis_contract", "security_type_of", "stable_evidence_id",
    "top_analyst_actions_contract",
]
