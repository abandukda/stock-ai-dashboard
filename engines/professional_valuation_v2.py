"""Evidence-gated professional valuation models and deterministic reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping

from engines.institutional_formulas import dcf_equity_value
from engines.methodology_registry import assert_registered


VERSION = "ATLAS_PROFESSIONAL_VALUATION_V2"
PUBLISHED = "PUBLISHED"
INSUFFICIENT_INPUTS = "INSUFFICIENT_INPUTS"
NOT_APPLICABLE = "NOT_APPLICABLE"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool): return None
    try:
        result = float(str(value).replace(",", "").replace("$", "").replace("%", ""))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError): return None


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    return next((row.get(key) for key in keys if row.get(key) not in (None, "", "Unavailable")), None)


def classify_company(row: Mapping[str, Any]) -> str:
    security = str(_first(row, "security_type", "asset_type") or "").upper()
    sector = str(row.get("sector") or "").lower(); industry = str(row.get("industry") or "").lower()
    profitable = (_number(_first(row, "forward_eps", "net_income", "latest_eps")) or 0) > 0
    if security == "ETF" or "exchange traded fund" in industry: return "ETF"
    if "reit" in industry or "real estate investment trust" in industry: return "REIT"
    if "bank" in industry: return "BANK"
    if "insurance" in industry: return "INSURER"
    if "biotech" in industry and not profitable: return "PRE_PROFIT_BIOTECH"
    if "pharma" in industry or "drug manufacturer" in industry: return "PROFITABLE_PHARMA" if profitable else "PRE_PROFIT_BIOTECH"
    if "software" in industry and (_number(row.get("revenue_growth")) or 0) > .15: return "HIGH_GROWTH_SOFTWARE"
    if any(word in industry for word in ("gold", "copper", "oil & gas", "mining")): return "COMMODITY_PRODUCER"
    if "conglomerate" in industry: return "CONGLOMERATE"
    return "PROFITABLE_OPERATING_COMPANY" if profitable else "UNCLASSIFIED_OPERATING_COMPANY"


def _model(methodology_id: str, *, status: str, value: float | None = None, confidence: float = 0,
           coverage: float = 0, fiscal_period: str | None = None, assumptions: Mapping[str, Any] | None = None,
           reason: str | None = None) -> dict[str, Any]:
    method = assert_registered(methodology_id, standard_name=True)
    return {"methodology_id": method.methodology_id, "name": method.name, "status": status,
            "value": round(value, 4) if value is not None else None, "confidence": confidence,
            "evidence_coverage": coverage, "fiscal_period": fiscal_period,
            "key_assumptions": dict(assumptions or {}), "reason": reason}


def _forward_pe(row: Mapping[str, Any], company_type: str) -> dict[str, Any]:
    allowed = {"PROFITABLE_OPERATING_COMPANY", "PROFITABLE_PHARMA", "HIGH_GROWTH_SOFTWARE", "BANK", "INSURER"}
    if company_type not in allowed: return _model("VAL_FORWARD_PE_V1", status=NOT_APPLICABLE, reason="COMPANY_TYPE_NOT_ELIGIBLE")
    eps = _number(_first(row, "normalized_forward_eps", "forward_eps")); period = _first(row, "forward_eps_period")
    multiple = _number(_first(row, "justified_forward_pe", "atlas_valuation_justified_pe"))
    basis = _first(row, "justified_forward_pe_basis", "atlas_valuation_multiple_basis")
    # Legacy ATLAS multiples are not professional evidence merely because they
    # were persisted. They require an explicit peer/history/fundamental basis.
    if eps is None or eps <= 0 or multiple is None or multiple <= 0 or not period or not basis:
        return _model("VAL_FORWARD_PE_V1", status=INSUFFICIENT_INPUTS, reason="EPS_PERIOD_OR_JUSTIFIED_MULTIPLE_EVIDENCE_MISSING")
    if multiple > 100: return _model("VAL_FORWARD_PE_V1", status=INSUFFICIENT_INPUTS, reason="UNSUPPORTED_EXTREME_MULTIPLE")
    return _model("VAL_FORWARD_PE_V1", status=PUBLISHED, value=eps*multiple, confidence=80, coverage=1,
                  fiscal_period=str(period), assumptions={"forward_eps": eps, "justified_forward_pe": multiple, "multiple_basis": basis})


def _dcf(row: Mapping[str, Any], company_type: str) -> dict[str, Any]:
    if company_type not in {"PROFITABLE_OPERATING_COMPANY", "PROFITABLE_PHARMA", "HIGH_GROWTH_SOFTWARE", "COMMODITY_PRODUCER"}:
        return _model("VAL_FCFF_DCF_V1", status=NOT_APPLICABLE, reason="COMPANY_TYPE_NOT_ELIGIBLE")
    fcffs = row.get("forecast_fcff") if isinstance(row.get("forecast_fcff"), (list, tuple)) else None
    values = {key: _number(row.get(key)) for key in ("wacc", "terminal_growth", "total_debt", "cash_and_equivalents", "diluted_shares")}
    if not fcffs or any(values[key] is None for key in values):
        return _model("VAL_FCFF_DCF_V1", status=INSUFFICIENT_INPUTS, reason="EXPLICIT_FCFF_FORECAST_OR_CAPITAL_INPUTS_MISSING")
    try:
        result = dcf_equity_value(fcffs, values["wacc"], values["terminal_growth"], values["total_debt"], values["cash_and_equivalents"], values["diluted_shares"])
    except ValueError as exc:
        return _model("VAL_FCFF_DCF_V1", status=INSUFFICIENT_INPUTS, reason=str(exc))
    terminal_share = result["terminal_value_pct_of_enterprise_value"]
    confidence = 75 if terminal_share <= .75 else 55
    return _model("VAL_FCFF_DCF_V1", status=PUBLISHED, value=result["per_share_value"], confidence=confidence, coverage=1,
                  assumptions={**values, "forecast_fcff": tuple(fcffs), "terminal_value_pct_of_enterprise_value": terminal_share})


def _ev_ebitda(row: Mapping[str, Any], company_type: str) -> dict[str, Any]:
    if company_type in {"BANK", "INSURER", "REIT", "PRE_PROFIT_BIOTECH", "ETF"}:
        return _model("VAL_EV_EBITDA_V1", status=NOT_APPLICABLE, reason="COMPANY_TYPE_NOT_ELIGIBLE")
    ebitda = _number(row.get("forward_ebitda")); multiple = _number(row.get("justified_ev_ebitda")); shares = _number(row.get("diluted_shares"))
    debt = _number(row.get("total_debt")); cash = _number(row.get("cash_and_equivalents")); basis = row.get("justified_ev_ebitda_basis")
    if None in (ebitda,multiple,shares,debt,cash) or not basis or shares <= 0 or multiple <= 0:
        return _model("VAL_EV_EBITDA_V1", status=INSUFFICIENT_INPUTS, reason="FORWARD_EBITDA_MULTIPLE_OR_CAPITAL_INPUTS_MISSING")
    return _model("VAL_EV_EBITDA_V1", status=PUBLISHED, value=(ebitda*multiple-debt+cash)/shares, confidence=75, coverage=1,
                  assumptions={"forward_ebitda":ebitda,"multiple":multiple,"multiple_basis":basis,"net_debt":debt-cash})


def _p_fcf(row: Mapping[str, Any], company_type: str) -> dict[str, Any]:
    if company_type in {"BANK", "INSURER", "PRE_PROFIT_BIOTECH", "ETF"}:
        return _model("VAL_P_FCF_V1", status=NOT_APPLICABLE, reason="COMPANY_TYPE_NOT_ELIGIBLE")
    fcf = _number(_first(row,"normalized_fcf","free_cash_flow")); multiple = _number(row.get("justified_p_fcf")); shares = _number(row.get("diluted_shares")); basis=row.get("justified_p_fcf_basis")
    if None in (fcf,multiple,shares) or not basis or fcf <= 0 or multiple <= 0 or shares <= 0:
        return _model("VAL_P_FCF_V1", status=INSUFFICIENT_INPUTS, reason="NORMALIZED_FCF_MULTIPLE_OR_SHARES_MISSING")
    return _model("VAL_P_FCF_V1", status=PUBLISHED, value=fcf*multiple/shares, confidence=70, coverage=1,
                  assumptions={"normalized_fcf":fcf,"multiple":multiple,"multiple_basis":basis,"diluted_shares":shares})


def value_company(row: Mapping[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    company_type = classify_company(row); price = _number(_first(row,"current_price","price","Price"))
    models = [_dcf(row,company_type),_forward_pe(row,company_type),_ev_ebitda(row,company_type),_p_fcf(row,company_type)]
    valid = [model for model in models if model["status"] == PUBLISHED and model["value"] is not None and model["value"] > 0]
    if company_type == "ETF": status, reason = NOT_APPLICABLE, "CORPORATE_FAIR_VALUE_NOT_APPLICABLE_TO_ETF"
    elif not valid: status, reason = INSUFFICIENT_INPUTS, "NO_ELIGIBLE_MODEL_HAS_COMPLETE_PROFESSIONAL_INPUTS"
    else: status, reason = PUBLISHED, None
    if valid:
        total = sum(model["confidence"] for model in valid)
        for model in valid: model["weight"] = round(model["confidence"]/total,4)
        base = sum(model["value"]*model["weight"] for model in valid)
        low, high = min(model["value"] for model in valid), max(model["value"] for model in valid)
        # Scenarios alter model inputs upstream. Until scenario inputs exist,
        # bear/bull are deliberately unavailable rather than ±% decorations.
        confidence = sum(model["confidence"]*model["weight"] for model in valid)
    else: base=low=high=confidence=None
    lineage = dict(row.get("valuation_lineage") or {}) if isinstance(row.get("valuation_lineage"), Mapping) else {}
    for metric, source_key, period_key in (
        ("forward_eps", "forward_eps_source", "forward_eps_period"),
        ("forward_revenue", "forward_revenue_source", "forward_revenue_period"),
        ("free_cash_flow", "free_cash_flow_source", "free_cash_flow_period"),
    ):
        if row.get(metric) is not None:
            lineage.setdefault(metric, {"source": row.get(source_key), "raw_field": metric,
                                        "period": row.get(period_key), "unit": "PER_SHARE" if metric == "forward_eps" else "CURRENCY",
                                        "normalization": "NONE", "methodology": None})
    return {"version":VERSION,"status":status,"company_type":company_type,
            "atlas_base_fair_value":round(base,2) if base else None,"atlas_fair_value_low":round(low,2) if low else None,
            "atlas_fair_value_high":round(high,2) if high else None,"atlas_bear_case":None,"atlas_bull_case":None,
            "atlas_expected_return":round((base/price-1)*100,1) if base and price and price>0 else None,
            "valuation_confidence":round(confidence,1) if confidence is not None else None,
            "valuation_as_of":as_of or datetime.now(timezone.utc).isoformat(),"valuation_methodology_version":VERSION,
            "models":models,"reason":reason,"wall_street_used":False,
            "lineage":lineage,
            "scenario_status":"INSUFFICIENT_ECONOMIC_SCENARIO_INPUTS" if valid else "NOT_AVAILABLE"}


__all__ = ["INSUFFICIENT_INPUTS", "NOT_APPLICABLE", "PUBLISHED", "VERSION", "classify_company", "value_company"]
