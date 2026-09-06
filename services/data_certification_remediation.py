"""Deterministic remediation classification and provider-quality reporting."""
from __future__ import annotations

from collections import Counter
import math
from typing import Any, Mapping, Sequence

VERSION = "ATLAS_DATA_CERTIFICATION_REMEDIATION_V1"

CLASSIFICATIONS = {
    "PERIOD_MISMATCH": "ATLAS_PERIOD_DEFECT",
    "MARKET_CAP_BRIDGE_FAILURE": "ATLAS_SHARE_BRIDGE_DEFECT",
    "EV_BRIDGE_FAILURE": "ATLAS_NORMALIZATION_DEFECT",
    "FCF_RECONCILIATION_FAILURE": "PROVIDER_FIELD_MISSING",
    "SECTOR_MODEL_APPLICABILITY_WARNING": "ATLAS_MODEL_ROUTING_DEFECT",
    "EXTREME_MODEL_DISPERSION": "LEGITIMATE_HIGH_UNCERTAINTY",
    "INPUT_SOURCE_DIVERGENCE": "PROVIDER_SCHEMA_LIMITATION",
    "PROFESSIONAL_V2_MISSING": "PROVIDER_FIELD_MISSING",
}


def classify_blockers(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks = record.get("checks") or {}
    output = []
    for warning in record.get("warnings") or ():
        category = CLASSIFICATIONS.get(str(warning), "PROVIDER_SCHEMA_LIMITATION")
        detail: Any = None
        if warning == "FCF_RECONCILIATION_FAILURE":
            detail = checks.get("fcf_reconciliation")
            if (detail or {}).get("difference_classification") == "PERIOD_MISMATCH": category = "ATLAS_PERIOD_DEFECT"
        elif warning == "MARKET_CAP_BRIDGE_FAILURE":
            detail = checks.get("market_cap_bridge")
            if (detail or {}).get("failure_classification") == "CURRENT_SHARES_FIELD_MISSING": category = "PROVIDER_FIELD_MISSING"
        elif warning == "INPUT_SOURCE_DIVERGENCE": detail = checks.get("input_reconciliation")
        elif warning == "SECTOR_MODEL_APPLICABILITY_WARNING": detail = record.get("model_applicability")
        elif warning == "EXTREME_MODEL_DISPERSION": detail = checks.get("dispersion")
        output.append({"blocker": warning, "classification": category, "detail": detail})
    if not output and record.get("certification_state") == "INSUFFICIENT_INPUTS":
        output.append({"blocker": "REQUIRED_PROVIDER_FIELDS_MISSING", "classification": "PROVIDER_FIELD_MISSING"})
    return output


def continuity_check(series: Sequence[Mapping[str, Any]], *, field: str,
                     threshold: float = .50) -> list[dict[str, Any]]:
    """Flag material adjacent-period changes lacking an attributable event."""
    ordered = sorted((dict(item) for item in series), key=lambda x: str(x.get("period") or ""))
    findings = []
    for prior, current in zip(ordered, ordered[1:]):
        try:
            old, new = float(prior[field]), float(current[field])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(old) or not math.isfinite(new) or old == 0: continue
        change = abs(new-old)/abs(old)
        if change > threshold and not current.get("attributable_event_evidence_id"):
            findings.append({"field":field,"prior_period":prior.get("period"),"current_period":current.get("period"),
                             "change_pct":round(change*100,2),"status":"REVIEW_REQUIRED"})
    return findings


def provider_quality(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metrics = ("revenue","net_income","eps","ebitda","operating_cash_flow","capex","free_cash_flow","cash","debt","current_shares_outstanding","diluted_shares","forward_eps","forward_revenue")
    output = {}
    for metric in metrics:
        checked=agreed=diverged=missing=0; primary=Counter(); secondary=Counter()
        for record in records:
            lineage=(record.get("input_lineage") or {}).get(metric) or {}
            reconciliation=(record.get("checks") or {}).get("input_reconciliation") or {}
            primary[str(lineage.get("source") or "NOT_AVAILABLE")]+=1
            agreement=next((x for x in reconciliation.get("agreements") or () if x.get("metric")==metric),None)
            divergence=next((x for x in reconciliation.get("divergences") or () if x.get("metric")==metric),None)
            if agreement:
                checked+=1;agreed+=1;secondary[str(agreement.get("secondary_source"))]+=1
            elif divergence:
                checked+=1;diverged+=1;secondary[str(divergence.get("secondary_source"))]+=1
            else: missing+=1
        total=len(records)
        output[metric]={"primary_providers":dict(primary),"secondary_validators":dict(secondary),"records_checked":checked,
                        "agreement_rate":round(agreed/checked*100,2) if checked else None,
                        "divergence_rate":round(diverged/checked*100,2) if checked else None,
                        "missing_rate":round(missing/total*100,2) if total else None,
                        "unresolved_rate":round((diverged+missing)/total*100,2) if total else None}
    return {"version":VERSION,"families":output}


__all__ = ["CLASSIFICATIONS","VERSION","classify_blockers","continuity_check","provider_quality"]
