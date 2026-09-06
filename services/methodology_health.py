"""Admin-only production health for governed ATLAS methodology artifacts."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from engines.methodology_registry import REGISTRY_VERSION
from engines.professional_valuation_v2 import VERSION as VALUATION_VERSION

VERSION = "ATLAS_METHODOLOGY_HEALTH_V1"


def methodology_health(rows: Sequence[Mapping[str, Any]], *, now: datetime | None = None, performance_snapshot_count: int = 0, matured_performance_count: int = 0) -> dict[str, Any]:
    observed = now or datetime.now(timezone.utc); counts=Counter(); stale=0; mismatches=0
    for row in rows:
        evaluation=dict(row.get("canonical_investment_evaluation") or {})
        valuation=dict((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
        status=valuation.get("status") or "MISSING"; counts[status]+=1
        diagnostics=dict(valuation.get("valuation_diagnostics") or {}); flags=set(diagnostics.get("flags") or ())
        counts["HIGH_DISPERSION"] += "MODEL_DISPERSION_HIGH" in flags
        counts["HIGH_TERMINAL"] += "TERMINAL_VALUE_DEPENDENCE_HIGH" in flags
        counts["WACC_BELOW_RF"] += "WACC_BELOW_RISK_FREE" in flags
        counts["SINGLE_MODEL"] += "MODEL_CONCENTRATION_SINGLE_METHOD" in flags
        if valuation and valuation.get("valuation_methodology_version") != VALUATION_VERSION: mismatches+=1
        stamp=valuation.get("valuation_as_of")
        try:
            parsed=datetime.fromisoformat(str(stamp).replace("Z","+00:00")); stale += (observed-parsed).total_seconds()>86400*180
        except Exception: stale += bool(valuation)
    return {"version":VERSION,"methodology_registry_version":REGISTRY_VERSION,"valuation_methodology_version":VALUATION_VERSION,
            "published_count":counts["PUBLISHED"],"insufficient_count":counts["INSUFFICIENT_INPUTS"],
            "not_applicable_count":counts["NOT_APPLICABLE"],"stale_evidence_count":stale,
            "high_model_dispersion_count":counts["HIGH_DISPERSION"],"high_terminal_dependence_count":counts["HIGH_TERMINAL"],
            "wacc_below_risk_free_count":counts["WACC_BELOW_RF"],"single_model_count":counts["SINGLE_MODEL"],
            "methodology_mismatch_count":mismatches,"home_research_mismatch_count":0,"thesis_validation_failure_count":0,
            "performance_snapshot_count":performance_snapshot_count,"matured_performance_count":matured_performance_count,
            "status":"DEGRADED" if mismatches else "HEALTHY","observed_at":observed.isoformat()}

__all__=["VERSION","methodology_health"]
