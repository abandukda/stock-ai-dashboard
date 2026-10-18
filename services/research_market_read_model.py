"""Read-only, cache-first market evidence for customer Research.

This module deliberately has no provider adapter. It can only project a
content-addressed retained bundle whose display rights and provenance have
already been recorded. The resulting context is educational/non-scoring and
cannot replace certified recommendation or publication authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from services.finnhub_enterprise_display_contract import display_authority


SCHEMA = "ATLAS_RESEARCH_MARKET_READ_MODEL_V1"
CLASSIFICATION = "CONTEXTUAL_NON_SCORING"
FAMILY_MAX_AGE_SECONDS = {
    "historical_ohlcv": 7 * 86400,
    "financial_statements": 32 * 86400,
    "basic_financials": 8 * 3600,
    "stock_earnings": 8 * 3600,
    "earnings_calendar": 8 * 3600,
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _safe_ticker(value: str) -> str:
    return "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {"-", "."})


def _family(envelope: Any, *, ticker: str, now: datetime) -> dict[str, Any] | None:
    if not isinstance(envelope, Mapping):
        return None
    item = dict(envelope)
    capability = str(item.get("capability") or "")
    authority = display_authority(capability)
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    payload = item.get("payload")
    captured = _instant(provenance.get("capture_timestamp"))
    evidence_id = str(provenance.get("raw_evidence_id") or "").strip()
    payload_sha = str(item.get("payload_sha256") or "").strip()
    if (
        authority is None
        or not isinstance(payload, (Mapping, list))
        or not captured
        or not evidence_id
        or str(provenance.get("ticker") or "").upper() != ticker
        or provenance.get("commercial_display_allowed") is not True
        or provenance.get("raw_machine_readable_redistribution_allowed") is not False
        or str(provenance.get("contract_id") or "") != authority.contract_id
        or str(provenance.get("contracted_endpoint") or "") != authority.endpoint
        or payload_sha != hashlib.sha256(_canonical(payload)).hexdigest()
    ):
        return None
    age = max(0.0, (now - captured).total_seconds())
    max_age = FAMILY_MAX_AGE_SECONDS.get(capability)
    status = "FRESH_CACHE" if max_age is None or age <= max_age else "STALE_RETAINED"
    return {
        "payload": payload,
        "provenance": {**dict(provenance), "source": provenance.get("source") or "FINNHUB_RETAINED_EVIDENCE"},
        "cache_status": status,
        "age_seconds": age,
        "classification": CLASSIFICATION,
    }


def load_research_market_context(
    ticker: str, root: str | Path | None, *, now: datetime | None = None,
) -> dict[str, Any]:
    """Load a verified retained bundle without network access or mutation."""
    symbol = _safe_ticker(ticker)
    if not symbol or root in (None, ""):
        return {}
    path = Path(root) / f"{symbol}.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    supplied = str(document.pop("record_sha256", ""))
    if (
        document.get("schema") != SCHEMA
        or str(document.get("ticker") or "").upper() != symbol
        or not document.get("source_sha")
        or supplied != hashlib.sha256(_canonical(document)).hexdigest()
    ):
        return {}
    checked = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    modules: dict[str, Any] = {}
    for key, envelope in (document.get("families") or {}).items():
        verified = _family(envelope, ticker=symbol, now=checked)
        if verified:
            modules[str(key)] = verified
    if not modules:
        return {}
    modules["__atlas_ticker__"] = symbol
    modules["__read_model__"] = {
        "schema": SCHEMA,
        "source_sha": document["source_sha"],
        "bundle_id": document.get("bundle_id"),
        "record_sha256": supplied,
        "classification": CLASSIFICATION,
        "provider_calls": 0,
        "rating_authority": "UNCHANGED",
        "publication_authority": "UNCHANGED",
    }
    return modules


def seal_research_market_bundle(document: Mapping[str, Any]) -> dict[str, Any]:
    """Test/producer helper: attach the deterministic top-level self hash."""
    payload = dict(document)
    payload.pop("record_sha256", None)
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return payload


__all__ = [
    "CLASSIFICATION", "FAMILY_MAX_AGE_SECONDS", "SCHEMA",
    "load_research_market_context", "seal_research_market_bundle",
]
