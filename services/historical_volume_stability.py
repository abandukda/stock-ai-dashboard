"""Append-only, non-production stability ledger for disputed historical volume."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


VERSION = "ATLAS_HISTORICAL_VOLUME_STABILITY_V1"
DISPUTED_SESSIONS = {
    "AAPL": ("2026-06-12", "2026-06-25", "2026-09-18"),
    "MSFT": ("2026-06-12", "2026-06-25", "2026-07-02", "2026-09-18"),
    "NVDA": ("2026-06-12", "2026-06-25", "2026-07-02", "2026-09-18"),
}


def append_stability_observation(path: str | Path, *, forensic_rows: Sequence[Mapping[str, Any]],
                                 provider_records: Mapping[str, Any], observed_at: str | None = None) -> dict[str, Any]:
    target = Path(path)
    existing = _load(target)
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    observations = list(existing.get("observations") or [])
    current = []
    by_key = {(row.get("ticker"), row.get("session_date")): row for row in forensic_rows}
    for ticker, dates in DISPUTED_SESSIONS.items():
        for session in dates:
            row = by_key.get((ticker, session)) or {}
            current.append(_observation(ticker, session, row, provider_records.get(ticker) or {}, timestamp))
    observations.extend(current)
    history = _history(observations)
    report = {
        "version": VERSION, "updated_at": timestamp, "append_only": True,
        "production_authority_changed": False, "observations": observations,
        "per_session_history": history,
        "independent_calendar_days": sorted({str(item["retrieval_timestamp"])[:10] for item in observations}),
        "readiness": "SHADOW_READY",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(target)
    return report


def _observation(ticker: str, session: str, row: Mapping[str, Any], records: Mapping[str, Any], timestamp: str) -> dict[str, Any]:
    historical = records.get("historical_ohlcv") or {}
    provenance = historical.get("provenance") or {}
    twelve = row.get("twelve_volume")
    finnhub = row.get("finnhub_volume")
    return {
        "ticker": ticker, "session_date": session, "retrieval_timestamp": timestamp,
        "twelve": _provider_observation("TWELVE_DATA", ticker, session, twelve, timestamp,
                                        "splits", "FULL_CONSOLIDATED", "TWELVE_DATA_PHASE1_ADAPTER"),
        "finnhub": _provider_observation("FINNHUB", ticker, session, finnhub, timestamp,
                                         "SPLIT_ADJUSTED_ONLY;VOLUME_CONSOLIDATED_AFTER_4PM",
                                         provenance.get("market_coverage_class"),
                                         provenance.get("adapter_version"), provenance.get("raw_evidence_id")),
        "absolute_difference": row.get("absolute_difference"),
        "percentage_difference": row.get("percentage_difference"),
        "mechanism_evidence": row.get("root_cause_evidence"),
    }


def _provider_observation(provider: str, ticker: str, session: str, volume: Any, retrieval: str,
                          adjustment: Any, coverage: Any, adapter: Any, evidence_id: Any = None) -> dict[str, Any]:
    digest = hashlib.sha256(f"{provider}|{ticker}|{session}|{volume}|{retrieval}".encode()).hexdigest()
    return {
        "provider": provider, "observed_volume": volume, "retrieval_timestamp": retrieval,
        "source_timestamp": session if volume is not None else None, "adjustment_metadata": adjustment,
        "market_coverage_metadata": coverage, "evidence_id": evidence_id or f"VOLUME_FORENSIC:{digest[:24]}",
        "content_hash": digest, "adapter_version": adapter, "schema_version": VERSION,
    }


def _history(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for item in observations:
        grouped.setdefault((str(item["ticker"]), str(item["session_date"])), []).append(item)
    output = []
    for (ticker, session), rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda item: str(item["retrieval_timestamp"]))
        current, prior = rows[-1], rows[-2] if len(rows) > 1 else None
        days = {str(row["retrieval_timestamp"])[:10] for row in rows}
        comparison = _classify(prior, current, len(days))
        output.append({
            "ticker": ticker, "session_date": session, "observation_count": len(rows),
            "independent_calendar_day_count": len(days), "current_twelve_value": current["twelve"]["observed_volume"],
            "current_finnhub_value": current["finnhub"]["observed_volume"],
            "current_difference_pct": current.get("percentage_difference"), **comparison,
            "difference_type": "CROSS_PROVIDER_DIFFERENCE",
            "finnhub_internal_consistency": (
                "NO_INTERNAL_FINNHUB_INCONSISTENCY_OBSERVED"
                if comparison.get("finnhub_changed") is False else
                "ADDITIONAL_OBSERVATION_REQUIRED"
            ),
            "mechanism_confidence": "INSUFFICIENT" if len(days) < 3 else "OBSERVATIONAL",
            "evidence_note": "No final mechanism is inferred before three independent calendar-day observations.",
        })
    return output


def _classify(prior: Mapping[str, Any] | None, current: Mapping[str, Any], independent_days: int) -> dict[str, Any]:
    if prior is None:
        return {"twelve_changed": None, "finnhub_changed": None, "moved_toward": None, "moved_farther": None,
                "identical_to_prior": None, "classification": "INSUFFICIENT_OBSERVATIONS"}
    pt, pf = prior["twelve"]["observed_volume"], prior["finnhub"]["observed_volume"]
    ct, cf = current["twelve"]["observed_volume"], current["finnhub"]["observed_volume"]
    tc, fc = ct != pt, cf != pf
    prior_gap = abs(float(pt) - float(pf)) if pt is not None and pf is not None else None
    current_gap = abs(float(ct) - float(cf)) if ct is not None and cf is not None else None
    identical = not tc and not fc
    if ct is not None and cf is not None and ct == cf: classification = "RESOLVED_EQUAL"
    elif independent_days < 3: classification = "INSUFFICIENT_OBSERVATIONS"
    elif identical: classification = "STABLE_PROVIDER_DIVERGENCE"
    elif tc and fc: classification = "BOTH_CHANGED"
    elif current_gap is not None and prior_gap is not None and current_gap < prior_gap: classification = "CONVERGING_LATE_PRINT"
    elif current_gap is not None and prior_gap is not None and current_gap > prior_gap: classification = "DIVERGING_REVISION"
    else: classification = "ONE_PROVIDER_CHANGED"
    return {"twelve_changed": tc, "finnhub_changed": fc,
            "moved_toward": current_gap < prior_gap if current_gap is not None and prior_gap is not None else None,
            "moved_farther": current_gap > prior_gap if current_gap is not None and prior_gap is not None else None,
            "identical_to_prior": identical, "classification": classification}


def _load(path: Path) -> dict[str, Any]:
    if not path.exists(): return {"version": VERSION, "observations": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if payload.get("version") == VERSION else {"version": VERSION, "observations": []}
    except (OSError, ValueError):
        return {"version": VERSION, "observations": []}


__all__ = ["DISPUTED_SESSIONS", "VERSION", "append_stability_observation"]
