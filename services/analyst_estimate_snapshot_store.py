"""Append-only daily FMP analyst-estimate snapshots for bounded finalists.

GitHub cache/artifact persistence is the Phase 1 foundation. Ninety-day
revision history requires durable object/database storage in a later phase.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Final, Mapping

from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE
from services.fmp_stable_client import FMPStableClient


SNAPSHOT_SCHEMA_VERSION: Final = "FMP_ANALYST_ESTIMATE_SNAPSHOT_V1"
DEFAULT_SNAPSHOT_ROOT: Final = Path(".atlas_research_cache/analyst_estimate_snapshots_v1")
ACCUMULATION_MESSAGE: Final = "Estimate revision history is still being accumulated."


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or isinstance(value, (Mapping, list, tuple, set)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in {float("inf"), float("-inf")} else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _evidence_id(snapshot: Mapping[str, Any]) -> str:
    identity = {key: snapshot.get(key) for key in (
        "ticker", "estimate_period", "period_type", "metric", "observed_at",
        "provider", "endpoint_schema_version",
    )}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"ev_{digest[:24]}"


def normalize_estimate_snapshots(
    ticker: str, rows: Any, *, observed_at: str, period_type: str = "annual",
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    symbol = str(ticker or "").strip().upper()
    date_key = observed_at[:10]
    output = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        estimate_period = str(row.get("date") or "").strip()
        if not estimate_period:
            continue
        for metric, low_key, high_key, avg_key, count_key in (
            ("EPS", "epsLow", "epsHigh", "epsAvg", "numAnalystsEps"),
            ("REVENUE", "revenueLow", "revenueHigh", "revenueAvg", "numAnalystsRevenue"),
        ):
            snapshot = {
                "ticker": symbol, "estimate_period": estimate_period,
                "period_type": period_type, "metric": metric,
                "low": _number(row.get(low_key)), "high": _number(row.get(high_key)),
                "average": _number(row.get(avg_key)), "analyst_count": _integer(row.get(count_key)),
                "observed_at": date_key, "provider": "FMP",
                "endpoint_schema_version": SNAPSHOT_SCHEMA_VERSION,
                "semantic_status": AVAILABLE if _number(row.get(avg_key)) is not None else DATA_UNAVAILABLE,
            }
            snapshot["evidence_id"] = _evidence_id(snapshot)
            output.append(snapshot)
    return output


def _path(ticker: str, root: str | Path) -> Path:
    symbol = "".join(ch for ch in str(ticker).upper() if ch.isalnum() or ch in {"-", "_"})
    return Path(root) / f"{symbol}.jsonl"


def load_snapshots(ticker: str, *, root: str | Path = DEFAULT_SNAPSHOT_ROOT) -> list[dict[str, Any]]:
    path = _path(ticker, root)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    output = []
    for line in lines:
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get("endpoint_schema_version") == SNAPSHOT_SCHEMA_VERSION:
            output.append(value)
    return output


def append_daily_snapshots(
    ticker: str, snapshots: list[Mapping[str, Any]], *, root: str | Path = DEFAULT_SNAPSHOT_ROOT,
) -> dict[str, int]:
    existing = load_snapshots(ticker, root=root)
    identities = {
        (item.get("ticker"), item.get("estimate_period"), item.get("period_type"), item.get("metric"), item.get("observed_at"))
        for item in existing
    }
    additions = []
    for item in snapshots:
        identity = (item.get("ticker"), item.get("estimate_period"), item.get("period_type"), item.get("metric"), item.get("observed_at"))
        if identity not in identities:
            identities.add(identity)
            additions.append(dict(item))
    if additions:
        path = _path(ticker, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for item in additions:
                handle.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
    return {"added": len(additions), "duplicates": len(snapshots) - len(additions), "total": len(existing) + len(additions)}


def revision_summary(ticker: str, *, root: str | Path = DEFAULT_SNAPSHOT_ROOT) -> dict[str, Any]:
    snapshots = load_snapshots(ticker, root=root)
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for item in snapshots:
        key = tuple(str(item.get(name) or "") for name in ("ticker", "estimate_period", "period_type", "metric"))
        groups.setdefault(key, []).append(item)
    comparisons = []
    for key, values in groups.items():
        distinct = sorted({str(item.get("observed_at")) for item in values})
        if len(distinct) < 2:
            continue
        ordered = sorted(values, key=lambda item: str(item.get("observed_at") or ""))
        current, prior = ordered[-1], ordered[-2]
        comparisons.append({
            "ticker": key[0], "estimate_period": key[1], "period_type": key[2], "metric": key[3],
            "prior_observed_at": prior.get("observed_at"), "current_observed_at": current.get("observed_at"),
            "prior_average": prior.get("average"), "current_average": current.get("average"),
            "source_evidence_ids": [prior.get("evidence_id"), current.get("evidence_id")],
        })
    return {
        "semantic_status": AVAILABLE if comparisons else DATA_UNAVAILABLE,
        "status_detail": None if comparisons else ACCUMULATION_MESSAGE,
        "comparisons": comparisons,
        "snapshot_count": len(snapshots),
    }


def capture_daily_estimates(
    tickers: list[str], *, api_key: str, root: str | Path = DEFAULT_SNAPSHOT_ROOT,
    observed_at: str | None = None, client: FMPStableClient | None = None,
) -> dict[str, Any]:
    now = observed_at or datetime.now(timezone.utc).isoformat()
    day = now[:10]
    transport = client or FMPStableClient(api_key, timeout_seconds=8, retries=0)
    calls = added = skipped = unavailable = 0
    for ticker in dict.fromkeys(str(item).upper().strip() for item in tickers if str(item).strip()):
        if any(item.get("observed_at") == day for item in load_snapshots(ticker, root=root)):
            skipped += 1
            continue
        response = transport.get("analyst-estimates", {"symbol": ticker, "period": "annual", "limit": 12})
        calls += int(response.attempts > 0)
        rows = response.payload if response.successful and isinstance(response.payload, list) else []
        snapshots = normalize_estimate_snapshots(ticker, rows, observed_at=now)
        if snapshots:
            added += append_daily_snapshots(ticker, snapshots, root=root)["added"]
        else:
            unavailable += 1
    return {"provider_calls": calls, "snapshots_added": added, "daily_skips": skipped, "unavailable": unavailable}


__all__ = [
    "ACCUMULATION_MESSAGE", "DEFAULT_SNAPSHOT_ROOT", "SNAPSHOT_SCHEMA_VERSION",
    "append_daily_snapshots", "capture_daily_estimates", "load_snapshots",
    "normalize_estimate_snapshots", "revision_summary",
]
