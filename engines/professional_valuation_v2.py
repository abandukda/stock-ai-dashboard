"""Evidence-gated professional valuation models and deterministic reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping

from engines.institutional_formulas import dcf_equity_value, dividend_discount_model
from engines.methodology_registry import assert_registered


VERSION = "ATLAS_PROFESSIONAL_VALUATION_V2"
PUBLISHED = "PUBLISHED"
INSUFFICIENT_INPUTS = "INSUFFICIENT_INPUTS"
NOT_APPLICABLE = "NOT_APPLICABLE"
VALIDATION_FAILED = "VALIDATION_FAILED"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool): return None
    try:
        result = float(str(value).replace(",", "").replace("$", "").replace("%", ""))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError): return None


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    return next((row.get(key) for key in keys if row.get(key) not in (None, "", "Unavailable")), None)


def classify_company(row: Mapping[str, Any]) -> str:
    security = str(_first(row, "security_type", "asset_type", "provider_security_type") or "").upper()
    sector = str(row.get("sector") or "").lower(); industry = str(row.get("industry") or "").lower()
    profitable = (_number(_first(row, "forward_eps", "net_income", "latest_eps")) or 0) > 0
    if security == "ETF" or "exchange traded fund" in industry: return "ETF"
    if "reit" in industry or "real estate investment trust" in industry: return "REIT"
    if "bank" in industry: return "BANK"
    if "insurance" in industry: return "INSURER"
    if "biotech" in industry and ((_number(row.get("net_income")) or 0) <= 0): return "PRE_PROFIT_BIOTECH"
    if "pharma" in industry or "drug manufacturer" in industry: return "PROFITABLE_PHARMA" if profitable else "PRE_PROFIT_BIOTECH"
    if "software" in industry and (_number(row.get("revenue_growth")) or 0) > .15: return "HIGH_GROWTH_SOFTWARE"
    if any(word in industry for word in ("gold", "copper", "oil & gas", "mining")): return "COMMODITY_PRODUCER"
    if "conglomerate" in industry: return "CONGLOMERATE"
    return "PROFITABLE_OPERATING_COMPANY" if profitable else "UNCLASSIFIED_OPERATING_COMPANY"


def _model(methodology_id: str, *, status: str, value: float | None = None, confidence: float = 0,
           coverage: float = 0, fiscal_period: str | None = None, assumptions: Mapping[str, Any] | None = None,
           reason: str | None = None) -> dict[str, Any]:
    method = assert_registered(methodology_id, standard_name=True)
    eligibility = {PUBLISHED:"ELIGIBLE_COMPLETE", INSUFFICIENT_INPUTS:"ELIGIBLE_INCOMPLETE", NOT_APPLICABLE:"NOT_APPLICABLE", VALIDATION_FAILED:"FAILED_VALIDATION"}.get(status,"FAILED_VALIDATION")
    return {"methodology_id": method.methodology_id, "name": method.name, "status": status, "eligibility_state": eligibility,
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
    if result["per_share_value"] <= 0:
        return _model("VAL_FCFF_DCF_V1", status=VALIDATION_FAILED, reason="NONPOSITIVE_EQUITY_VALUE")
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
    value=(ebitda*multiple-debt+cash)/shares
    if value <= 0: return _model("VAL_EV_EBITDA_V1", status=VALIDATION_FAILED, reason="NONPOSITIVE_EQUITY_VALUE")
    return _model("VAL_EV_EBITDA_V1", status=PUBLISHED, value=value, confidence=75, coverage=1,
                  assumptions={"forward_ebitda":ebitda,"multiple":multiple,"multiple_basis":basis,"net_debt":debt-cash})


def _p_fcf(row: Mapping[str, Any], company_type: str) -> dict[str, Any]:
    if company_type in {"BANK", "INSURER", "PRE_PROFIT_BIOTECH", "ETF"}:
        return _model("VAL_P_FCF_V1", status=NOT_APPLICABLE, reason="COMPANY_TYPE_NOT_ELIGIBLE")
    fcf = _number(_first(row,"normalized_fcf","free_cash_flow")); multiple = _number(row.get("justified_p_fcf")); shares = _number(row.get("diluted_shares")); basis=row.get("justified_p_fcf_basis")
    if None in (fcf,multiple,shares) or not basis or fcf <= 0 or multiple <= 0 or shares <= 0:
        return _model("VAL_P_FCF_V1", status=INSUFFICIENT_INPUTS, reason="NORMALIZED_FCF_MULTIPLE_OR_SHARES_MISSING")
    return _model("VAL_P_FCF_V1", status=PUBLISHED, value=fcf*multiple/shares, confidence=70, coverage=1,
                  assumptions={"normalized_fcf":fcf,"multiple":multiple,"multiple_basis":basis,"diluted_shares":shares})


def _ddm(row: Mapping[str, Any], company_type: str) -> dict[str, Any]:
    if company_type not in {"BANK", "INSURER", "PROFITABLE_OPERATING_COMPANY", "PROFITABLE_PHARMA"}:
        return _model("VAL_DDM_GORDON_V1", status=NOT_APPLICABLE, reason="COMPANY_TYPE_NOT_ELIGIBLE")
    dividend = _number(row.get("dividend_next")); cost = _number(row.get("cost_of_equity")); growth = _number(row.get("dividend_growth"))
    if None in (dividend, cost, growth):
        return _model("VAL_DDM_GORDON_V1", status=INSUFFICIENT_INPUTS, reason="DIVIDEND_COST_OF_EQUITY_OR_GROWTH_MISSING")
    try:
        value = dividend_discount_model(dividend, cost, growth)
    except ValueError as exc:
        return _model("VAL_DDM_GORDON_V1", status=VALIDATION_FAILED, reason=str(exc))
    return _model("VAL_DDM_GORDON_V1", status=PUBLISHED, value=value, confidence=70, coverage=1,
                  assumptions={"dividend_next": dividend, "cost_of_equity": cost, "dividend_growth": growth})


def _model_weight(company_type: str, methodology_id: str, confidence: float) -> float:
    preferences = {
        "BANK": {"VAL_FORWARD_PE_V1": 1.0, "VAL_DDM_GORDON_V1": 1.1},
        "INSURER": {"VAL_FORWARD_PE_V1": 1.0, "VAL_DDM_GORDON_V1": 1.1},
        "HIGH_GROWTH_SOFTWARE": {"VAL_FCFF_DCF_V1": 1.2, "VAL_FORWARD_PE_V1": .9},
        "PROFITABLE_PHARMA": {"VAL_FCFF_DCF_V1": 1.1, "VAL_FORWARD_PE_V1": 1.0},
        "COMMODITY_PRODUCER": {"VAL_FCFF_DCF_V1": 1.2, "VAL_EV_EBITDA_V1": 1.0},
    }
    return confidence * preferences.get(company_type, {}).get(methodology_id, 1.0)


def _scenario_value(row: Mapping[str, Any], name: str, company_type: str) -> float | None:
    scenarios = row.get("valuation_scenarios")
    inputs = scenarios.get(name.lower()) if isinstance(scenarios, Mapping) else None
    if not isinstance(inputs, Mapping):
        return None
    result = value_company({**dict(row), **dict(inputs), "valuation_scenarios": None}, _scenario_run=True)
    return result.get("atlas_base_fair_value") if result.get("status") == PUBLISHED else None


def _dcf_sensitivity(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    fcffs = row.get("forecast_fcff")
    debt, cash, shares = (_number(row.get(key)) for key in ("total_debt", "cash_and_equivalents", "diluted_shares"))
    wacc_values = row.get("sensitivity_wacc") or ()
    growth_values = row.get("sensitivity_terminal_growth") or ()
    if not isinstance(fcffs, (list, tuple)) or None in (debt, cash, shares): return []
    cells = []
    for discount in wacc_values if isinstance(wacc_values, (list, tuple)) else ():
        for growth in growth_values if isinstance(growth_values, (list, tuple)) else ():
            try:
                value = dcf_equity_value(fcffs, float(discount), float(growth), debt, cash, shares)["per_share_value"]
                cells.append({"wacc": float(discount), "terminal_growth": float(growth), "fair_value": round(value, 2)})
            except (TypeError, ValueError):
                continue
    return cells


def _valuation_diagnostics(
    row: Mapping[str, Any], valid: list[dict[str, Any]], *, base: float,
    low: float, high: float, bear: float | None, bull: float | None,
    sensitivity: list[dict[str, Any]], confidence: float,
) -> tuple[float, dict[str, Any], dict[str, Any]]:
    """Return deterministic risk diagnostics, calibrated confidence, and client explanation."""
    values = [float(model["value"]) for model in valid]
    dispersion = ((max(values) - min(values)) / base * 100) if base > 0 and len(values) > 1 else 0.0
    range_width = ((high - low) / base * 100) if base > 0 else 0.0
    sensitivity_values = [float(cell["fair_value"]) for cell in sensitivity if _number(cell.get("fair_value")) is not None]
    sensitivity_width = ((max(sensitivity_values) - min(sensitivity_values)) / base * 100) if base > 0 and sensitivity_values else None
    terminal_shares = [
        float((model.get("key_assumptions") or {}).get("terminal_value_pct_of_enterprise_value"))
        for model in valid
        if _number((model.get("key_assumptions") or {}).get("terminal_value_pct_of_enterprise_value")) is not None
    ]
    terminal_share = max(terminal_shares) if terminal_shares else None
    flags: list[str] = []
    if dispersion >= 50: flags.append("MODEL_DISPERSION_HIGH")
    if range_width >= 75: flags.append("FAIR_VALUE_RANGE_WIDE")
    if terminal_share is not None and terminal_share >= .85: flags.append("TERMINAL_VALUE_DEPENDENCE_HIGH")
    if bull is not None and bull >= base * 2: flags.append("BULL_CASE_EXTREME")
    if bear is not None and (base - bear) / base >= .35: flags.append("BEAR_BASE_GAP_HIGH")
    if len(valid) == 1: flags.append("MODEL_CONCENTRATION_SINGLE_METHOD")
    if sensitivity_width is not None and sensitivity_width >= 100: flags.append("SENSITIVITY_WIDE")
    dcf_assumptions = next((model.get("key_assumptions") or {} for model in valid if model.get("methodology_id") == "VAL_FCFF_DCF_V1"), {})
    wacc_value = _number(dcf_assumptions.get("wacc")); growth_value = _number(dcf_assumptions.get("terminal_growth")); risk_free = _number(row.get("risk_free_rate"))
    spread = wacc_value - growth_value if wacc_value is not None and growth_value is not None else None
    if wacc_value is not None and risk_free is not None and wacc_value < risk_free: flags.append("WACC_BELOW_RISK_FREE")
    if spread is not None and spread < .01: flags.append("WACC_G_SPREAD_BELOW_1PCT")
    elif spread is not None and spread < .015: flags.append("WACC_G_SPREAD_BELOW_1_5PCT")
    elif spread is not None and spread < .02: flags.append("WACC_G_SPREAD_BELOW_2PCT")

    # Confidence remains descriptive and non-authoritative. Penalize only
    # observable valuation uncertainty; never change model values or weights.
    calibrated = confidence
    calibrated -= min(20.0, dispersion * .15)
    if terminal_share is not None and terminal_share > .75:
        calibrated -= min(12.0, (terminal_share - .75) * 60)
    if sensitivity_width is not None and sensitivity_width > 50:
        calibrated -= min(12.0, (sensitivity_width - 50) * .06)
    if len(valid) == 1: calibrated = min(calibrated, 55.0)
    if "WACC_BELOW_RISK_FREE" in flags: calibrated -= 5
    if spread is not None and spread < .02: calibrated -= min(15.0, (.02-spread)*750)
    calibrated = max(20.0, min(90.0, calibrated))

    primary = max(valid, key=lambda model: float(model.get("weight") or 0))
    secondary = sorted(valid, key=lambda model: float(model.get("weight") or 0), reverse=True)[1] if len(valid) > 1 else None
    def driver(model: Mapping[str, Any]) -> str:
        assumptions = model.get("key_assumptions") or {}
        if model.get("methodology_id") == "VAL_FCFF_DCF_V1":
            return f"forecast free cash flow discounted at {float(assumptions['wacc'])*100:.1f}% with {float(assumptions['terminal_growth'])*100:.1f}% terminal growth"
        if model.get("methodology_id") == "VAL_EV_EBITDA_V1":
            return f"forward EBITDA of ${float(assumptions['forward_ebitda']):,.0f} valued at {float(assumptions['multiple']):.1f}× before the net-debt bridge"
        if model.get("methodology_id") == "VAL_FORWARD_PE_V1":
            return f"forward EPS of ${float(assumptions['forward_eps']):.2f} valued at {float(assumptions['justified_forward_pe']):.1f}×"
        if model.get("methodology_id") == "VAL_P_FCF_V1":
            return f"normalized free cash flow valued at {float(assumptions['multiple']):.1f}×"
        if model.get("methodology_id") == "VAL_DDM_GORDON_V1":
            return f"next dividend discounted at {float(assumptions['cost_of_equity'])*100:.1f}% with {float(assumptions['dividend_growth'])*100:.1f}% growth"
        return model["name"]
    street = _number(_first(row, "analyst_target_mean", "wall_street_target", "street_target"))
    if street is None:
        street_reason = "A commercially usable Street target is not available for comparison."
    elif abs(base / street - 1) <= .10:
        street_reason = "ATLAS and Street are broadly aligned; model assumptions differ but not materially at the headline-value level."
    elif base > street:
        street_reason = f"ATLAS is above Street because its highest-weighted {primary['name']} evidence supports more value than the consensus target."
    else:
        street_reason = f"ATLAS is below Street because its highest-weighted {primary['name']} evidence is more conservative than the consensus target."
    uncertainty = (
        "Long-duration cash flows are highly sensitive to discount-rate and terminal-growth assumptions."
        if "TERMINAL_VALUE_DEPENDENCE_HIGH" in flags else
        "Independent valuation methods produce materially different estimates."
        if "MODEL_DISPERSION_HIGH" in flags else
        "The published methods are reasonably aligned, but forecast and market-multiple assumptions can still change."
    )
    explanation = {
        "primary_valuation_driver": f"{primary['name']} contributes {float(primary.get('weight') or 0)*100:.1f}% of the reconciled value, driven by {driver(primary)}.",
        "secondary_valuation_driver": f"{secondary['name']} provides the secondary cross-check through {driver(secondary)}." if secondary else "No second complete professional method is currently available.",
        "biggest_valuation_uncertainty": uncertainty,
        "highest_weight_method": primary["methodology_id"],
        "atlas_vs_street": street_reason,
        "scenario_risk": "The bull case is especially sensitive to optimistic discount-rate, growth, or revenue assumptions." if "BULL_CASE_EXTREME" in flags else "Bear and bull outcomes depend on the explicitly published scenario assumptions.",
    }
    diagnostics = {
        "flags": flags, "model_dispersion_pct": round(dispersion, 1),
        "fair_value_range_width_pct": round(range_width, 1),
        "terminal_value_pct_of_ev": round(terminal_share * 100, 1) if terminal_share is not None else None,
        "sensitivity_width_pct": round(sensitivity_width, 1) if sensitivity_width is not None else None,
        "street_target_context": street,
        "wacc_minus_g_pct": round(spread*100, 2) if spread is not None else None,
        "wacc_below_risk_free_attribution": {
            "equity_weight": _number(row.get("equity_weight")), "cost_of_equity": _number(row.get("cost_of_equity")),
            "debt_weight": _number(row.get("debt_weight")), "after_tax_cost_of_debt": _number(row.get("after_tax_cost_of_debt")),
        } if "WACC_BELOW_RISK_FREE" in flags else None,
    }
    return calibrated, diagnostics, explanation


def value_company(row: Mapping[str, Any], *, as_of: str | None = None, _scenario_run: bool = False) -> dict[str, Any]:
    company_type = classify_company(row); price = _number(_first(row,"current_price","price","Price"))
    models = [_dcf(row,company_type),_forward_pe(row,company_type),_ev_ebitda(row,company_type),_p_fcf(row,company_type),_ddm(row, company_type)]
    valid = [model for model in models if model["status"] == PUBLISHED and model["value"] is not None and model["value"] > 0]
    if company_type == "ETF": status, reason = NOT_APPLICABLE, "CORPORATE_FAIR_VALUE_NOT_APPLICABLE_TO_ETF"
    elif not valid: status, reason = INSUFFICIENT_INPUTS, "NO_ELIGIBLE_MODEL_HAS_COMPLETE_PROFESSIONAL_INPUTS"
    else: status, reason = PUBLISHED, None
    if valid:
        raw_weights = [_model_weight(company_type, model["methodology_id"], model["confidence"]) for model in valid]
        total = sum(raw_weights)
        for model, raw_weight in zip(valid, raw_weights):
            model["weight"] = round(raw_weight/total,4)
            model["weighting_justification"] = f"Deterministic {company_type} model preference adjusted by input confidence"
        base = sum(model["value"]*model["weight"] for model in valid)
        low, high = min(model["value"] for model in valid), max(model["value"] for model in valid)
        # Scenarios alter model inputs upstream. Until scenario inputs exist,
        # bear/bull are deliberately unavailable rather than ±% decorations.
        confidence = sum(model["confidence"]*model["weight"] for model in valid)
        concentration = "SINGLE METHOD" if len(valid) == 1 else "MULTI METHOD"
        if len(valid) == 1: confidence = min(confidence, 65)
    else: base=low=high=confidence=None; concentration=None
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
    bear = bull = None
    if valid and not _scenario_run:
        bear = _scenario_value(row, "bear", company_type)
        bull = _scenario_value(row, "bull", company_type)
        if bear is not None and bear >= base: bear = None
        if bull is not None and bull <= base: bull = None
    sensitivity = _dcf_sensitivity(row) if valid else []
    diagnostics = explanation = {}
    if valid:
        confidence, diagnostics, explanation = _valuation_diagnostics(
            row, valid, base=base, low=low, high=high, bear=bear, bull=bull,
            sensitivity=sensitivity, confidence=confidence,
        )
    blockers = tuple(dict.fromkeys(model.get("reason") for model in models if model.get("status") in {INSUFFICIENT_INPUTS, VALIDATION_FAILED} and model.get("reason")))
    return {"version":VERSION,"status":status,"company_type":company_type,
            "atlas_base_fair_value":round(base,2) if base else None,"atlas_fair_value_low":round(low,2) if low else None,
            "atlas_fair_value_high":round(high,2) if high else None,"atlas_bear_case":bear,"atlas_bull_case":bull,
            "atlas_expected_return":round((base/price-1)*100,1) if base and price and price>0 else None,
            "valuation_confidence":round(confidence,1) if confidence is not None else None,
            "valuation_as_of":as_of or datetime.now(timezone.utc).isoformat(),"valuation_methodology_version":VERSION,
            "models":models,"model_weights": {model["methodology_id"]: model.get("weight") for model in valid},
            "model_concentration": concentration,
            "weighting_basis": f"Deterministic company-type reconciliation for {company_type}",
            "reason":reason,"blockers":blockers,"wall_street_used":False,
            "lineage":lineage,
            "valuation_diagnostics": diagnostics,
            "valuation_explanation": explanation,
            "scenario_status":"PUBLISHED" if bear is not None and bull is not None else "INSUFFICIENT_ECONOMIC_SCENARIO_INPUTS" if valid else "NOT_AVAILABLE",
            "sensitivity": sensitivity}


__all__ = ["INSUFFICIENT_INPUTS", "NOT_APPLICABLE", "PUBLISHED", "VERSION", "classify_company", "value_company"]
