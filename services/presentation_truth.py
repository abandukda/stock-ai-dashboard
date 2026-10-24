"""Fail-closed presentation labels for retained ATLAS evidence.

This module does not acquire data or generate analysis.  It only translates
already-governed records into customer-facing availability disclosures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


_STALE = {"STALE", "STALE_FALLBACK", "LAST_KNOWN", "EXPIRED"}
_AVAILABLE = {"AVAILABLE", "PARTIAL", "PUBLISHED", "CERTIFIED", "LIVE", "CURRENT"}


def _status(value: Any) -> str:
    return str(value or "UNAVAILABLE").strip().upper().replace(" ", "_")


def summary_disclosure(summary: Mapping[str, Any] | None) -> dict[str, str]:
    """Identify generated, deterministic, stale, and unavailable summaries."""
    item = dict(summary or {})
    text = str(item.get("text") or "").strip()
    source = _status(item.get("source"))
    mode = _status(item.get("mode"))
    if mode == "DETERMINISTIC_GROUNDED_FALLBACK" and item.get("external_model_active") is False:
        return {"state": "DETERMINISTIC", "label": "Deterministic explanation",
                "detail": "External AI was not used; this wording was assembled from governed fields."}
    if not text:
        return {"state": "UNAVAILABLE", "label": "Summary unavailable",
                "detail": "No grounded summary is available for this snapshot."}
    if source == "LLM_VALIDATED" and item.get("accepted") is True:
        return {"state": "GENERATED_VALIDATED", "label": "Validated generated explanation",
                "detail": "Generated wording passed the grounded-evidence checks."}
    if source == "DETERMINISTIC_FALLBACK":
        return {"state": "DETERMINISTIC", "label": "Deterministic explanation",
                "detail": "The displayed wording is the deterministic governed fallback; model-attempt status is not implied."}
    # Older canonical projections predate the explicit source/accepted pair.
    # Their authority and consistency receipts establish governed prose, but
    # do not establish that an external model ran.
    if item.get("version") and item.get("authority") and item.get("consistency"):
        return {"state": "DETERMINISTIC", "label": "Governed deterministic explanation",
                "detail": "No validated external-generation receipt is attached to this explanation."}
    return {"state": "UNAVAILABLE", "label": "Summary source unavailable",
            "detail": "The displayed text is not identified as validated generated or deterministic content."}


def market_view_disclosure(market: Mapping[str, Any] | None) -> dict[str, str]:
    """Describe a Home market view without upgrading last-known evidence."""
    item = dict(market or {})
    status = _status(item.get("status") or item.get("market_session"))
    evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
    declared_freshness = [_status(item.get("freshness_status") or evidence.get("freshness_status"))]
    declared_freshness.extend(
        _status(row.get("freshness_status")) for row in item.get("instruments") or () if isinstance(row, Mapping)
    )
    source = str(item.get("source") or item.get("source_type") or "Unavailable")
    as_of = str(item.get("as_of") or "Timestamp unavailable")
    valid_instruments = [row for row in item.get("instruments") or () if isinstance(row, Mapping)
                         and row.get("symbol") and row.get("price") is not None
                         and row.get("source") and row.get("evidence_id")]
    valid_macro = [row for row in item.get("official_macro_evidence") or () if isinstance(row, Mapping)
                   and row.get("agency_label") and row.get("source_url") and row.get("observation_period")]
    valid_news = [row for row in item.get("major_market_news") or () if isinstance(row, Mapping)
                  and row.get("headline") and row.get("source") and row.get("published_at")]
    has_evidence = bool(valid_instruments or valid_macro or valid_news)
    try:
        parsed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        timestamp_valid = parsed.tzinfo is not None and parsed <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        timestamp_valid = False
    if status in _STALE or any(value in _STALE for value in declared_freshness):
        state, label = "STALE", "Last-known market context"
    elif has_evidence and (status == "PARTIAL" or not timestamp_valid):
        state, label = "PARTIAL", "Partial market context"
    elif has_evidence and status in _AVAILABLE and any(value in {"CURRENT", "CAPTURED", "LIVE"} for value in declared_freshness):
        state, label = "AVAILABLE", "Verified market context"
    elif has_evidence:
        state, label = "PARTIAL", "Dated market context"
    else:
        state, label = "UNAVAILABLE", "Market context unavailable"
    return {"state": state, "label": label, "source": source, "as_of": as_of}


def research_field_disclosure(section: Mapping[str, Any] | None) -> dict[str, str]:
    """Return source/freshness/availability for one canonical Research section."""
    item = dict(section or {})
    provenance = dict(item.get("provenance") or {})
    semantic_status = _status(item.get("semantic_status"))
    status = _status(item.get("status"))
    freshness = _status(item.get("freshness") or provenance.get("freshness") or provenance.get("status"))
    source = str(provenance.get("source") or provenance.get("provider") or item.get("source") or "Unavailable")
    as_of = str(provenance.get("as_of") or provenance.get("capture_timestamp") or item.get("as_of") or "Timestamp unavailable")
    if freshness in _STALE or status in _STALE or semantic_status in _STALE:
        availability, label = "STALE", "Stale evidence"
    elif "PARTIAL" in {status, semantic_status}:
        availability, label = "PARTIAL", "Partial evidence"
    elif status in _AVAILABLE or semantic_status in _AVAILABLE:
        availability, label = "AVAILABLE", "Available evidence"
    else:
        availability, label = "UNAVAILABLE", "Evidence unavailable"
    return {"availability": availability, "label": label, "source": source, "as_of": as_of}


__all__ = ["market_view_disclosure", "research_field_disclosure", "summary_disclosure"]
