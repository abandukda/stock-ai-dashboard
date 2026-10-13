"""Read-only Premium R2 financial-period sufficiency report."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


STANDARD = {"annual": 3, "quarterly": 4}
METRICS = {
    "revenue": "latest_revenue",
    "operating_margin": "operating_margin_pct",
    "free_cash_flow": "free_cash_flow",
    "net_debt": "net_debt",
}


def period_coverage(
    records: list[Mapping[str, Any]], tickers: set[str],
    recovered_lineage: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in records}
    matrix: list[dict[str, Any]] = []
    totals = {"STANDARD_MET": 0, "BELOW_STANDARD": 0, "NOT_AVAILABLE": 0}
    for ticker in sorted(tickers):
        row = by_ticker.get(ticker, {})
        original = ((row.get("professional_evidence_lineage") or {}).get("fields") or {})
        recovered = recovered_lineage.get(ticker) or {}
        for metric, field in METRICS.items():
            evidence = {**dict(recovered.get(field) or {}), **dict(original.get(field) or {})}
            period = str(evidence.get("period") or "").strip()
            evidence_id = str(evidence.get("evidence_id") or "").strip()
            frequency = str(evidence.get("frequency") or evidence.get("period_type") or "").upper()
            annual = {period} if period and evidence_id and frequency in {"ANNUAL", "FY"} else set()
            quarterly = {period} if period and evidence_id and frequency in {"QUARTERLY", "FQ", "Q"} else set()
            if len(annual) >= STANDARD["annual"] and len(quarterly) >= STANDARD["quarterly"]:
                status = "STANDARD_MET"
            elif annual or quarterly:
                status = "BELOW_STANDARD"
            else:
                status = "NOT_AVAILABLE"
            totals[status] += 1
            matrix.append({
                "ticker": ticker, "metric": metric, "source_field": field,
                "annual_periods": sorted(annual), "annual_count": len(annual),
                "quarterly_periods": sorted(quarterly), "quarterly_count": len(quarterly),
                "required_annual": STANDARD["annual"], "required_quarterly": STANDARD["quarterly"],
                "status": status, "evidence_id": evidence_id or None,
                "provider": evidence.get("provider"), "unit": evidence.get("unit"),
                "limitation": None if status == "STANDARD_MET" else
                    "Retained evidence does not prove at least 3 annual and 4 quarterly periods.",
            })
    return {
        "contract": "ATLAS_R2_PREMIUM_PERIOD_STANDARD_V1",
        "provider_calls": 0,
        "standard": {
            "annual_periods": 3, "quarterly_periods": 4,
            "metrics": list(METRICS), "where_reported": True,
        },
        "ticker_count": len(tickers), "cell_count": len(matrix),
        "conservation": {**totals, "total": sum(totals.values())},
        "matrix": matrix,
        "authority_preserved": True,
        "g6_changed": False,
    }


def write_report(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["METRICS", "STANDARD", "period_coverage", "write_report"]
