"""Fail-closed Finnhub forward-input bridge for existing Professional V2 models.

No valuation is calculated here.  The bridge certifies provider semantics and
maps eligible inputs into the already-approved Professional V2 field contract.
"""
from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any, Mapping

from engines.professional_valuation_v2 import classify_company
from services.finnhub_contract_gap_governance import estimate_bridge


VERSION = "FINNHUB_FORWARD_VALUATION_BRIDGE_V1"
METHOD_STATES = frozenset({
    "CERTIFIED_APPLICABLE", "CERTIFIED_BUT_NOT_APPLICABLE", "INPUT_INCOMPLETE",
    "ACCOUNTING_BRIDGE_INCOMPLETE", "SCENARIO_EVIDENCE_INCOMPLETE",
    "CURRENCY_MISMATCH", "PROVIDER_DATA_UNAVAILABLE",
})


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _period(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def select_forward_estimate(*, profile: Mapping[str, Any], estimate: Mapping[str, Any],
                            capability: str, snapshot_timestamp: str,
                            price_currency: str | None) -> dict[str, Any]:
    """Select the earliest annual fiscal period after the immutable snapshot."""
    bridge = estimate_bridge(profile, estimate, capability=capability, price_currency=price_currency)
    if bridge["status"] != "CERTIFIED_PROVIDER_CONTRACT":
        state = "CURRENCY_MISMATCH" if "PRICE_ESTIMATE_CURRENCY_MISMATCH" in bridge["blockers"] else (
            "PROVIDER_DATA_UNAVAILABLE" if "PROVIDER_DATA_UNAVAILABLE" in bridge["blockers"] else "INPUT_INCOMPLETE"
        )
        return {"status": state, "bridge": bridge, "selected": None}
    snapshot = datetime.fromisoformat(snapshot_timestamp.replace("Z", "+00:00")).date()
    eligible = []
    for row in estimate.get("estimates") or ():
        period = _period(row.get("period"))
        value = _number(row.get("average"))
        analysts = _number(row.get("analyst_count"))
        if row.get("frequency") == "annual" and period and period > snapshot and value is not None and analysts and analysts > 0:
            eligible.append((period, str(row.get("year") or ""), dict(row)))
    if not eligible:
        return {"status": "INPUT_INCOMPLETE", "bridge": bridge, "selected": None,
                "blockers": ["NO_POSITIVE_ANALYST_SUPPORTED_ANNUAL_FORWARD_PERIOD"]}
    selected = min(eligible, key=lambda item: (item[0], item[1]))[2]
    return {
        "status": "CERTIFIED_PROVIDER_CONTRACT", "bridge": bridge, "selected": selected,
        "selection_rule": "EARLIEST_ANNUAL_FISCAL_PERIOD_STRICTLY_AFTER_SNAPSHOT",
        "period": selected["period"], "value": float(selected["average"]),
        "analyst_count": int(float(selected["analyst_count"])),
        "currency": bridge["currency"], "basis": bridge["basis"], "scale": bridge["value_scale"],
    }


def accounting_bridge(row: Mapping[str, Any]) -> dict[str, Any]:
    fields = (row.get("professional_evidence_lineage") or {}).get("fields") or {}
    required = ("market_cap", "total_debt", "cash_and_equivalents", "diluted_shares")
    missing_values = [field for field in required if _number(row.get(field)) is None]
    missing_lineage = [field for field in required if not (fields.get(field) or {}).get("evidence_id")]
    currencies = {
        str((fields.get(field) or {}).get("currency")).upper()
        for field in required[:-1] if (fields.get(field) or {}).get("currency")
    }
    blockers = []
    if missing_values: blockers.append("MISSING_VALUES:" + ",".join(missing_values))
    if missing_lineage: blockers.append("MISSING_LINEAGE:" + ",".join(missing_lineage))
    if len(currencies) > 1: blockers.append("CURRENCY_MISMATCH")
    shares = _number(row.get("diluted_shares"))
    if shares is not None and shares <= 0: blockers.append("NONPOSITIVE_DILUTED_SHARES")
    if blockers:
        state = "CURRENCY_MISMATCH" if "CURRENCY_MISMATCH" in blockers else "ACCOUNTING_BRIDGE_INCOMPLETE"
        return {"version": VERSION, "status": state, "blockers": blockers}
    market_cap, debt, cash = (_number(row.get(name)) for name in required[:3])
    return {
        "version": VERSION, "status": "CERTIFIED", "blockers": [],
        "enterprise_value": market_cap + debt - cash,
        "formula": "MARKET_CAP_PLUS_GOVERNED_DEBT_MINUS_GOVERNED_CASH",
        "currency": next(iter(currencies), None), "diluted_shares": shares,
    }


def apply_forward_inputs(row: Mapping[str, Any], *, profile: Mapping[str, Any],
                         estimates: Mapping[str, Mapping[str, Any]], snapshot_timestamp: str,
                         evidence_ids: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    output = dict(row)
    currency = str(profile.get("currency") or "").upper() or None
    mapping = {
        "eps_estimates": ("forward_eps", "forward_eps_period"),
        "revenue_estimates": ("forward_revenue", "forward_revenue_period"),
        "ebitda_estimates": ("forward_ebitda", "forward_ebitda_period"),
        "dps_estimates": ("dividend_next", "dividend_next_period"),
        "fcf_estimates": ("forward_fcf", "forward_fcf_period"),
    }
    results = {}
    fields = dict((output.get("professional_evidence_lineage") or {}).get("fields") or {})
    for capability, (value_field, period_field) in mapping.items():
        result = select_forward_estimate(
            profile=profile, estimate=estimates.get(capability) or {}, capability=capability,
            snapshot_timestamp=snapshot_timestamp, price_currency=currency,
        )
        results[capability] = result
        if result["status"] != "CERTIFIED_PROVIDER_CONTRACT":
            continue
        output[value_field] = result["value"]
        output[period_field] = result["period"]
        if capability == "eps_estimates":
            output["normalized_forward_eps"] = result["value"]
        fields[value_field] = {
            "evidence_id": evidence_ids.get(capability), "provider": "FINNHUB",
            "unit": "PER_SHARE" if result["basis"] == "PER_SHARE" else "CURRENCY_ABSOLUTE",
            "currency": result["currency"], "period": result["period"],
            "analyst_count": result["analyst_count"], "frequency": "annual",
            "scale": "IDENTITY", "selection_rule": result["selection_rule"],
        }
    lineage = dict(output.get("professional_evidence_lineage") or {})
    lineage["fields"] = fields
    lineage["evidence_ids"] = sorted(set(filter(None, (*lineage.get("evidence_ids", ()), *evidence_ids.values()))))
    output["professional_evidence_lineage"] = lineage
    output["forward_estimate_evidence"] = {
        "revenue": {
            "avg_estimate": output.get("forward_revenue"),
            "period": output.get("forward_revenue_period"),
        }
    }
    output["forward_contract_status"] = "CERTIFIED" if all(
        results[name]["status"] == "CERTIFIED_PROVIDER_CONTRACT"
        for name in ("eps_estimates", "revenue_estimates", "ebitda_estimates")
    ) else "PARTIAL"
    return output, results


def classify_method(*, row: Mapping[str, Any], model: Mapping[str, Any],
                    forward_results: Mapping[str, Mapping[str, Any]]) -> str:
    method = str(model.get("methodology_id") or "")
    if model.get("status") == "NOT_APPLICABLE":
        return "CERTIFIED_BUT_NOT_APPLICABLE"
    capabilities = {
        "VAL_FORWARD_PE_V1": ("eps_estimates",),
        "VAL_EV_EBITDA_V1": ("ebitda_estimates",),
        "VAL_FCFF_DCF_V1": ("revenue_estimates", "fcf_estimates"),
        "VAL_DDM_GORDON_V1": ("dps_estimates",),
    }.get(method, ())
    states = [str((forward_results.get(name) or {}).get("status")) for name in capabilities]
    if "CURRENCY_MISMATCH" in states: return "CURRENCY_MISMATCH"
    if "PROVIDER_DATA_UNAVAILABLE" in states: return "PROVIDER_DATA_UNAVAILABLE"
    if any(state != "CERTIFIED_PROVIDER_CONTRACT" for state in states): return "INPUT_INCOMPLETE"
    if method in {"VAL_EV_EBITDA_V1", "VAL_FCFF_DCF_V1"}:
        account = accounting_bridge(row)
        if account["status"] != "CERTIFIED": return account["status"]
    if method == "VAL_FCFF_DCF_V1" and not row.get("valuation_scenarios"):
        return "SCENARIO_EVIDENCE_INCOMPLETE"
    if model.get("status") == "PUBLISHED": return "CERTIFIED_APPLICABLE"
    return "INPUT_INCOMPLETE"


def method_matrix(row: Mapping[str, Any], valuation: Mapping[str, Any],
                  forward_results: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    models = {model.get("methodology_id"): model for model in valuation.get("models") or ()}
    return {method: classify_method(row=row, model=models.get(method) or {"methodology_id": method},
                                    forward_results=forward_results)
            for method in ("VAL_FORWARD_PE_V1", "VAL_EV_EBITDA_V1", "VAL_FCFF_DCF_V1", "VAL_DDM_GORDON_V1")}


__all__ = ["METHOD_STATES", "VERSION", "accounting_bridge", "apply_forward_inputs",
           "classify_method", "method_matrix", "select_forward_estimate"]
