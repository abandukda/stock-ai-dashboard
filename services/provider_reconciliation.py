"""Deterministic shadow reconciliation; never selects canonical authority."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from services.provider_domain_contracts import GovernedRecord


RECONCILIATION_VERSION = "ATLAS_PROVIDER_RECONCILIATION_V1"


@dataclass(frozen=True)
class ReconciliationTolerance:
    absolute: float = 1e-6
    relative_pct: float = 1.0


def compare_scalar(left: Any, right: Any, *, tolerance: ReconciliationTolerance = ReconciliationTolerance()) -> dict[str, Any]:
    if left is None or right is None:
        return {"status": "UNAVAILABLE", "left": left, "right": right}
    try:
        a, b = float(left), float(right)
    except (TypeError, ValueError):
        return {"status": "MATCH" if left == right else "MATERIAL_MISMATCH", "left": left, "right": right}
    delta = abs(a - b)
    scale = max(abs(a), abs(b), tolerance.absolute)
    pct = delta / scale * 100.0
    status = "MATCH" if delta <= tolerance.absolute else "WITHIN_TOLERANCE" if pct <= tolerance.relative_pct else "MATERIAL_MISMATCH"
    return {"status": status, "left": a, "right": b, "absolute_delta": delta, "relative_delta_pct": pct}


def reconcile_fields(
    current: GovernedRecord, shadow: GovernedRecord, field_pairs: Mapping[str, tuple[str, str]],
    *, tolerance: ReconciliationTolerance = ReconciliationTolerance(),
) -> dict[str, Any]:
    fields = {
        name: compare_scalar(current.payload.get(pair[0]), shadow.payload.get(pair[1]), tolerance=tolerance)
        for name, pair in field_pairs.items()
    }
    counts: dict[str, int] = {}
    for result in fields.values():
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {
        "version": RECONCILIATION_VERSION,
        "symbol": current.provenance.symbol,
        "current_provider": current.provenance.provider,
        "shadow_provider": shadow.provenance.provider,
        "fields": fields,
        "status_counts": counts,
        "authority_changed": False,
    }


def reconcile_ohlcv(current_bars: Sequence[Mapping[str, Any]], shadow_bars: Sequence[Mapping[str, Any]],
                    *, tolerance: ReconciliationTolerance = ReconciliationTolerance(relative_pct=0.1)) -> dict[str, Any]:
    def index(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
        return {str(row.get("date") or row.get("timestamp")): row for row in rows if row.get("date") or row.get("timestamp")}
    left, right = index(current_bars), index(shadow_bars)
    common = sorted(set(left) & set(right))
    comparisons = []
    for date in common:
        comparisons.append({
            "date": date,
            **{field: compare_scalar(left[date].get(field), right[date].get(field), tolerance=tolerance)
               for field in ("open", "high", "low", "close", "volume")},
        })
    material = sum(
        result.get("status") == "MATERIAL_MISMATCH"
        for row in comparisons for field, result in row.items() if field != "date"
    )
    price_statistics = {}
    for field in ("open", "high", "low", "close"):
        deltas = [row[field].get("relative_delta_pct") for row in comparisons if row[field].get("relative_delta_pct") is not None]
        price_statistics[field] = {
            "compared": len(deltas),
            "exact_match_rate": sum(value == 0 for value in deltas) / len(deltas) if deltas else None,
            "within_1bp_rate": sum(value <= 0.01 for value in deltas) / len(deltas) if deltas else None,
            "within_5bp_rate": sum(value <= 0.05 for value in deltas) / len(deltas) if deltas else None,
            "max_deviation_pct": max(deltas) if deltas else None,
            "beyond_5bp_count": sum(value > 0.05 for value in deltas),
        }
    return {
        "version": RECONCILIATION_VERSION, "common_sessions": len(common),
        "current_only_sessions": len(set(left) - set(right)),
        "shadow_only_sessions": len(set(right) - set(left)),
        "material_mismatch_count": material, "comparisons": comparisons,
        "price_accuracy": price_statistics,
        "authority_changed": False,
    }


__all__ = ["RECONCILIATION_VERSION", "ReconciliationTolerance", "compare_scalar", "reconcile_fields", "reconcile_ohlcv"]
