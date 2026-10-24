"""Fail-closed presentation labels for retained ATLAS evidence.

This module does not acquire data or generate analysis.  It only translates
already-governed records into customer-facing availability disclosures.
"""

from __future__ import annotations

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
    if not text:
        return {"state": "UNAVAILABLE", "label": "Summary unavailable",
                "detail": "No grounded summary is available for this snapshot."}
    if source == "LLM_VALIDATED" and item.get("accepted") is True:
        return {"state": "GENERATED_VALIDATED", "label": "Validated generated explanation",
                "detail": "Generated wording passed the grounded-evidence checks."}
    if source == "DETERMINISTIC_FALLBACK":
        return {"state": "DETERMINISTIC", "label": "Deterministic explanation",
                "detail": "External AI was not used; this wording was assembled from governed fields."}
    return {"state": "UNAVAILABLE", "label": "Summary source unavailable",
            "detail": "The displayed text is not identified as validated generated or deterministic content."}


def market_view_disclosure(market: Mapping[str, Any] | None) -> dict[str, str]:
    """Describe a Home market view without upgrading last-known evidence."""
    item = dict(market or {})
    status = _status(item.get("status") or item.get("market_session"))
    source = str(item.get("source") or item.get("source_type") or "Unavailable")
    as_of = str(item.get("as_of") or "Timestamp unavailable")
    has_evidence = bool(item.get("instruments") or item.get("official_macro_evidence") or item.get("major_market_news"))
    if status in _STALE:
        state, label = "STALE", "Last-known market context"
    elif has_evidence and status in _AVAILABLE:
        state, label = "AVAILABLE", "Verified market context"
    elif has_evidence:
        state, label = "PARTIAL", "Partial market context"
    else:
        state, label = "UNAVAILABLE", "Market context unavailable"
    return {"state": state, "label": label, "source": source, "as_of": as_of}


def research_field_disclosure(section: Mapping[str, Any] | None) -> dict[str, str]:
    """Return source/freshness/availability for one canonical Research section."""
    item = dict(section or {})
    provenance = dict(item.get("provenance") or {})
    status = _status(item.get("semantic_status") or item.get("status"))
    freshness = _status(item.get("freshness") or provenance.get("freshness") or provenance.get("status"))
    source = str(provenance.get("source") or provenance.get("provider") or item.get("source") or "Unavailable")
    as_of = str(provenance.get("as_of") or provenance.get("capture_timestamp") or item.get("as_of") or "Timestamp unavailable")
    if freshness in _STALE or status in _STALE:
        availability, label = "STALE", "Stale evidence"
    elif status in _AVAILABLE:
        availability, label = status if status == "PARTIAL" else "AVAILABLE", "Partial evidence" if status == "PARTIAL" else "Available evidence"
    else:
        availability, label = "UNAVAILABLE", "Evidence unavailable"
    return {"availability": availability, "label": label, "source": source, "as_of": as_of}


__all__ = ["market_view_disclosure", "research_field_disclosure", "summary_disclosure"]
