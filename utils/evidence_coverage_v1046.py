
from __future__ import annotations
from typing import Any, Mapping
import math

_MISSING = {"", "none", "nan", "null", "n/a", "na", "unknown", "under review", "unavailable", "not available"}

def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in _MISSING
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True

def calculate_evidence_coverage(row: Mapping[str, Any]) -> dict[str, Any]:
    components = row.get("components") or {}
    raw = row.get("raw") or row.get("Raw") or {}
    if not isinstance(raw, Mapping):
        raw = {}

    checks = {
        "Fundamentals": _present(components.get("fundamentals")),
        "Valuation": _present(components.get("valuation")),
        "Technicals": _present(components.get("technical")),
        "Analyst": _present(components.get("analyst")),
        "Institutional": _present(components.get("institutional")),
        "Political": _present(components.get("political")),
        "Insider": _present(components.get("insider")),
        "Risk": _present(components.get("risk")),
        "Macro": _present(components.get("macro")),
        "Fair Value": _present(row.get("validated_fair_value") or row.get("atlas_fair_value")),
        "Thesis": _present(row.get("investment_thesis")),
        "Earnings": _present(
            row.get("next_earnings_date")
            or row.get("guidance")
            or raw.get("next_earnings_date")
            or raw.get("Next Earnings")
            or raw.get("Earnings Date")
            or raw.get("earnings_date")
            or raw.get("earnings_summary")
            or raw.get("transcript_summary")
        ),
        "News / Catalyst": _present(
            raw.get("latest_news_headline")
            or raw.get("top_news_headline")
            or raw.get("Top News")
            or raw.get("catalysts")
        ),
    }

    available = sum(1 for value in checks.values() if value)
    total = len(checks)
    return {
        "coverage_pct": round(100.0 * available / total, 1) if total else 0.0,
        "available_count": available,
        "total_count": total,
        "checks": checks,
        "missing": [name for name, value in checks.items() if not value],
    }

__all__ = ["calculate_evidence_coverage"]
