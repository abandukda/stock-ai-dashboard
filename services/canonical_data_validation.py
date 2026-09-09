"""Pre-publication validation for Professional V2 evidence and outputs.

This module validates provider mappings and accounting relationships. It never
recalculates or tunes an ATLAS decision score.
"""
from __future__ import annotations
import math
from collections import Counter
from typing import Any,Mapping,Sequence
from engines.professional_valuation_v2 import classify_company
from services.valuation_evidence_strength import classify_valuation_evidence

VERSION="ATLAS_CANONICAL_DATA_VALIDATION_V1"
ATLAS_STANDARD_FCF="ATLAS_STANDARD_FCF = OCF - abs(Capex)"
CERTIFIED="CERTIFIED";CERTIFIED_HIGH_UNCERTAINTY="CERTIFIED_HIGH_UNCERTAINTY";REVIEW_REQUIRED="REVIEW_REQUIRED";INSUFFICIENT_INPUTS="INSUFFICIENT_INPUTS";NOT_APPLICABLE="NOT_APPLICABLE"
TOLERANCES={"revenue":.03,"net_income":.05,"eps":.08,"ebitda":.08,"operating_cash_flow":.05,"capex":.08,"cash":.05,"debt":.05,"current_shares_outstanding":.03,"diluted_shares":.05,"free_cash_flow":.10,"forward_eps":.08,"forward_revenue":.05}

def _num(value):
    try:
        result=float(value);return result if math.isfinite(result) else None
    except (TypeError,ValueError):return None

def _first(data:Mapping[str,Any],*keys):
    for key in keys:
        if data.get(key) is not None:return data.get(key)
    return None

def _relative_gap(left,right):
    a,b=_num(left),_num(right)
    if a is None or b is None:return None
    return abs(a-b)/max(abs(a),abs(b),1e-12)

def _professional(row):
    evaluation=dict(row.get("canonical_investment_evaluation") or {})
    return evaluation,dict((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {})

def _inputs(row,evaluation,valuation):
    trial=dict(evaluation.get("trial_presentation_fields") or {});lineage=dict(valuation.get("lineage") or {});provider_lineage=dict(trial.get("professional_evidence_lineage") or {})
    values={
        "current_price":_first(row,"current_price","price","Price"),"revenue":_first(trial,"latest_revenue","revenue"),"eps":_first(row,"latest_eps","reported_eps","eps"),
        "net_income":_first(trial,"net_income", "latest_net_income",),"ebitda":_first(trial,"forward_ebitda","ebitda"),"ebit":_first(trial,"ebit","latest_operating_income"),"operating_cash_flow":_first(trial,"operating_cash_flow") if _first(trial,"operating_cash_flow") is not None else _first(row,"operating_cash_flow"),"free_cash_flow":_first(trial,"normalized_fcf","free_cash_flow") if _first(trial,"normalized_fcf","free_cash_flow") is not None else _first(row,"normalized_fcf","free_cash_flow"),
        "cash":_first(trial,"cash_and_equivalents") if _first(trial,"cash_and_equivalents") is not None else _first(row,"cash_and_equivalents"),"debt":_first(trial,"total_debt") if _first(trial,"total_debt") is not None else _first(row,"total_debt"),"current_shares_outstanding":_first(trial,"current_shares_outstanding") if _first(trial,"current_shares_outstanding") is not None else _first(row,"current_shares_outstanding","shares_outstanding"),"diluted_shares":_first(trial,"diluted_shares") if _first(trial,"diluted_shares") is not None else _first(row,"diluted_shares","weighted_average_shares_diluted"),"market_cap":_first(trial,"market_cap",) if _first(trial,"market_cap") is not None else _first(row,"market_cap"),
        "forward_eps":_first(trial,"forward_eps") if _first(trial,"forward_eps") is not None else _first(row,"forward_eps"),"forward_revenue":_first(trial,"forward_revenue") if _first(trial,"forward_revenue") is not None else _first(row,"forward_revenue"),"capex":_first(trial,"capital_expenditures","capex") if _first(trial,"capital_expenditures","capex") is not None else _first(row,"capital_expenditures","capex"),
    }
    output={}
    for key,value in values.items():
        lineage_key="capital_expenditures" if key=="capex" else key
        mapped=dict((provider_lineage.get("fields") or {}).get(lineage_key) or provider_lineage.get(lineage_key) or {})
        specific={**mapped,**dict(lineage.get(key) or {})}
        share_unit="SHARES" if "shares" in key else "PER_SHARE" if "eps" in key else "CURRENCY"
        canonical=_num(value)
        output[key]={"value":canonical,"canonical_value":canonical,"period":specific.get("period") or trial.get(f"{key}_period") or trial.get("financial_reporting_period"),"period_type":specific.get("period_type") or trial.get(f"{key}_period_type"),"basis":specific.get("basis") or trial.get(f"{key}_basis"),"unit":specific.get("unit") or share_unit,"currency":specific.get("currency") or (trial.get("market_assumption_lineage") or {}).get("currency") or "USD","source":specific.get("source") or specific.get("provider") or trial.get(f"{key}_source") or provider_lineage.get("provider"),"endpoint":specific.get("endpoint"),"raw_field":specific.get("raw_field"),"raw_value":specific.get("raw_value"),"canonical_field":specific.get("canonical_field") or key,"normalized_value":canonical,"transformation":specific.get("transformation"),"consuming_methodology":specific.get("consuming_methodology"),"as_of":specific.get("as_of") or provider_lineage.get("observed_at") or valuation.get("valuation_as_of")}
    return output,trial

def _company_domain(row,trial,valuation):
    classified=classify_company({**dict(row),**dict(trial)})
    return {"PRE_PROFIT_BIOTECH":"BIOTECH","HIGH_GROWTH_SOFTWARE":"SOFTWARE"}.get(classified,classified)

def _applicability(method,domain):
    method_id=str(method.get("methodology_id") or "")
    if method.get("status")!="PUBLISHED":return "NOT_APPLICABLE" if method.get("status")=="NOT_APPLICABLE" else "WEAK_FOR_COMPANY_TYPE"
    if domain=="COMMODITY_PRODUCER":
        return "PRIMARY_APPROPRIATE" if method_id=="VAL_FCFF_DCF_V1" else "SECONDARY_CROSSCHECK" if method_id=="VAL_EV_EBITDA_V1" else "WEAK_FOR_COMPANY_TYPE"
    if domain=="BANK":return "PRIMARY_APPROPRIATE" if method_id in {"VAL_P_TBV_V1","VAL_RESIDUAL_INCOME_V1"} else "SECONDARY_CROSSCHECK" if method_id in {"VAL_FORWARD_PE_V1","VAL_DDM_GORDON_V1"} else "WEAK_FOR_COMPANY_TYPE"
    if domain=="REIT":return "PRIMARY_APPROPRIATE" if method_id in {"VAL_P_AFFO_V1","VAL_NAV_V1"} else "WEAK_FOR_COMPANY_TYPE"
    if domain=="BIOTECH":return "PRIMARY_APPROPRIATE" if method_id=="VAL_RNPV_V1" else "SECONDARY_CROSSCHECK"
    return "PRIMARY_APPROPRIATE" if method_id in {"VAL_FCFF_DCF_V1","VAL_FORWARD_PE_V1","VAL_EV_EBITDA_V1","VAL_P_FCF_V1"} else "SECONDARY_CROSSCHECK"

def validate_valuation(row:Mapping[str,Any])->dict[str,Any]:
    evaluation,valuation=_professional(row);ticker=str(row.get("ticker") or row.get("symbol") or "")
    if not valuation:return {"version":VERSION,"ticker":ticker,"certification_state":INSUFFICIENT_INPUTS,"warnings":["PROFESSIONAL_V2_MISSING"]}
    if valuation.get("status")=="NOT_APPLICABLE":return {"version":VERSION,"ticker":ticker,"certification_state":NOT_APPLICABLE,"warnings":[]}
    if valuation.get("status")!="PUBLISHED":return {"version":VERSION,"ticker":ticker,"certification_state":INSUFFICIENT_INPUTS,"warnings":list(valuation.get("blockers") or ())}
    inputs,trial=_inputs(row,evaluation,valuation);warnings=[];checks={}
    # Explicit secondary-source values are compared only when source identity differs.
    secondary=dict(row.get("approved_secondary_valuation_inputs") or {})
    divergences=[];agreements=[];secondary_missing=[]
    for metric,tolerance in TOLERANCES.items():
        primary=inputs.get(metric,{});other=secondary.get(metric) if isinstance(secondary.get(metric),Mapping) else None
        if not other:
            secondary_missing.append(metric);continue
        period_match=not primary.get("period") or not other.get("period") or str(primary.get("period"))==str(other.get("period"))
        basis_match=not primary.get("basis") or not other.get("basis") or str(primary.get("basis")).upper()==str(other.get("basis")).upper()
        gap=_relative_gap(primary.get("value"),(other or {}).get("value"))
        detail={"metric":metric,"gap_pct":round(gap*100,2) if gap is not None else None,"tolerance_pct":tolerance*100,"primary_source":primary.get("source"),"secondary_source":other.get("source"),"primary_period":primary.get("period"),"secondary_period":other.get("period"),"period_match":period_match,"basis_match":basis_match}
        if (other or {}).get("source")!=primary.get("source") and gap is not None and gap<=tolerance and period_match and basis_match:agreements.append(detail)
        elif gap is not None and (other or {}).get("source")!=primary.get("source"):divergences.append(detail)
    if divergences:warnings.append("INPUT_SOURCE_DIVERGENCE")
    checks["input_reconciliation"]={"status":"DIVERGENCE" if divergences else "SECONDARY_VALIDATION_UNAVAILABLE" if not secondary else "RECONCILED","agreements":agreements,"divergences":divergences,"secondary_missing":secondary_missing}
    price=inputs["current_price"]["value"];current_shares=inputs["current_shares_outstanding"]["value"];shares=inputs["diluted_shares"]["value"];market_cap=inputs["market_cap"]["value"]
    structure=dict(trial.get("share_structure") or {}); bridge_shares=_num(structure.get("market_cap_reconciliation_shares")) or current_shares
    implied_market_cap=price*bridge_shares if price is not None and bridge_shares is not None else None;market_gap=_relative_gap(implied_market_cap,market_cap)
    market_failure_classification = None
    if market_gap is not None and market_gap>.15:
        security=str(_first(row,"security_type","asset_type") or "").upper()
        market_failure_classification=str(structure.get("classification") or ("ADR_RATIO" if security in {"ADR","ADS"} else "STALE_SHARES"))
    checks["market_cap_bridge"]={"status":"PASS" if market_gap is not None and market_gap<=.15 else "FAIL" if market_gap is not None else "NOT_TESTABLE","reported":market_cap,"price_times_current_shares":implied_market_cap,"current_shares_outstanding":current_shares,"economic_reconciliation_shares":bridge_shares,"diluted_valuation_shares":shares,"discrepancy_pct":round(market_gap*100,2) if market_gap is not None else None,"failure_classification":market_failure_classification or ("CURRENT_SHARES_FIELD_MISSING" if current_shares is None else None)}
    if checks["market_cap_bridge"]["status"] in {"FAIL","NOT_TESTABLE"}:warnings.append("MARKET_CAP_BRIDGE_FAILURE")
    debt=inputs["debt"]["value"];cash=inputs["cash"]["value"];net_debt=debt-cash if debt is not None and cash is not None else None
    ev_checks=[]
    models=[dict(x) for x in valuation.get("models") or ()]
    for model in models:
        assumptions=dict(model.get("key_assumptions") or {})
        if model.get("status")=="PUBLISHED" and model.get("methodology_id")=="VAL_EV_EBITDA_V1":
            enterprise=_num(assumptions.get("forward_ebitda"))*_num(assumptions.get("multiple")) if _num(assumptions.get("forward_ebitda")) is not None and _num(assumptions.get("multiple")) is not None else None
            reconstructed=(enterprise-net_debt)/shares if enterprise is not None and net_debt is not None and shares else None;gap=_relative_gap(reconstructed,model.get("value"))
            ev_checks.append({"enterprise_value":enterprise,"market_cap":market_cap,"total_debt":debt,"preferred_equity":None,"minority_interest":None,"cash_and_equivalents":cash,"net_debt":net_debt,"equity_value":enterprise-net_debt if enterprise is not None and net_debt is not None else None,"diluted_shares":shares,"reconstructed_per_share":reconstructed,"published_per_share":model.get("value"),"discrepancy_pct":round(gap*100,4) if gap is not None else None,"period":inputs["debt"].get("period"),"currency":inputs["debt"].get("currency"),"unit":"CURRENCY","sources":{"debt":inputs["debt"].get("source"),"cash":inputs["cash"].get("source"),"shares":inputs["diluted_shares"].get("source")},"status":"PASS" if gap is not None and gap<=.01 else "FAIL"})
    checks["ev_bridge"]={"status":"PASS" if ev_checks and all(x["status"]=="PASS" for x in ev_checks) else "FAIL" if ev_checks else "NOT_TESTABLE","models":ev_checks}
    if checks["ev_bridge"]["status"]=="FAIL":warnings.append("EV_BRIDGE_FAILURE")
    ocf=inputs["operating_cash_flow"]["value"];fcf=inputs["free_cash_flow"]["value"];capex=inputs["capex"]["value"]
    provider_fcf=_num(_first(trial,"provider_defined_fcf"))
    comparable_keys=("period","period_type","basis","currency","unit","as_of")
    ocf_meta=inputs["operating_cash_flow"];capex_meta=inputs["capex"]
    metadata_mismatches=[key for key in comparable_keys if not ocf_meta.get(key) or not capex_meta.get(key) or str(ocf_meta.get(key)).upper()!=str(capex_meta.get(key)).upper()]
    expected_fcf=ocf-abs(capex) if ocf is not None and capex is not None and not metadata_mismatches else None
    canonical_gap=_relative_gap(expected_fcf,fcf);provider_gap=_relative_gap(expected_fcf,provider_fcf)
    reconciliation_pass=expected_fcf is not None and fcf is not None and canonical_gap is not None and canonical_gap<=1e-9
    classification="MATCHED" if reconciliation_pass else "EVIDENCE_METADATA_MISMATCH" if metadata_mismatches else "MISSING_PROVIDER_EVIDENCE" if expected_fcf is None or fcf is None else "CANONICAL_VALUE_MISMATCH"
    checks["fcf_reconciliation"]={"status":"PASS" if reconciliation_pass else "FAIL","ocf":ocf,"capex":capex,"canonical_calculated_fcf":expected_fcf,"canonical_published_fcf":fcf,"provider_defined_fcf":provider_fcf,"atlas_standard_fcf":expected_fcf,"canonical_difference":fcf-expected_fcf if fcf is not None and expected_fcf is not None else None,"provider_difference":provider_fcf-expected_fcf if provider_fcf is not None and expected_fcf is not None else None,"provider_difference_pct":round(provider_gap*100,2) if provider_gap is not None else None,"difference_classification":classification,"metadata_mismatches":metadata_mismatches,"period":ocf_meta.get("period"),"statement_type":ocf_meta.get("period_type"),"basis":"OCF_MINUS_ABS_CAPEX","currency":ocf_meta.get("currency"),"unit":ocf_meta.get("unit"),"provider":ocf_meta.get("source"),"evidence_ids":[x for x in (ocf_meta.get("endpoint"),capex_meta.get("endpoint")) if x],"standard":ATLAS_STANDARD_FCF,"canonical_authority":"ATLAS_STANDARD_FCF"}
    if not reconciliation_pass:warnings.append("FCF_CANONICAL_RECONCILIATION_FAILURE")
    period_issues=[]
    for model in models:
        if model.get("status")=="PUBLISHED" and model.get("methodology_id")=="VAL_FORWARD_PE_V1":
            expected=inputs["forward_eps"].get("period");actual=model.get("fiscal_period")
            if not expected or not actual or str(expected)!=str(actual):period_issues.append({"model":model.get("methodology_id"),"input_period":expected,"model_period":actual})
    checks["period_basis"]={"status":"PASS" if not period_issues else "FAIL","issues":period_issues}
    if period_issues:warnings.append("PERIOD_MISMATCH")
    domain=_company_domain(row,trial,valuation);applicability=[{"methodology_id":m.get("methodology_id"),"status":m.get("status"),"applicability":_applicability(m,domain),"weight":m.get("weight")} for m in models]
    primary=max((x for x in applicability if x.get("status")=="PUBLISHED"),key=lambda x:x.get("weight") or 0,default={})
    routing_mismatch=domain!=valuation.get("company_type") and domain in {"COMMODITY_PRODUCER","BANK","REIT","BIOTECH"}
    weak_weighted=any(x.get("applicability")=="WEAK_FOR_COMPANY_TYPE" and (_num(x.get("weight")) or 0)>0 for x in applicability)
    if routing_mismatch or primary.get("applicability")=="WEAK_FOR_COMPANY_TYPE" or weak_weighted:warnings.append("SECTOR_MODEL_APPLICABILITY_WARNING")
    values=[_num(m.get("value")) for m in models if m.get("status")=="PUBLISHED" and _num(m.get("value")) not in (None,0)]
    ratio=max(values)/min(values) if values else None;checks["dispersion"]={"max_min_ratio":round(ratio,2) if ratio is not None else None,"over_2x":bool(ratio and ratio>2),"over_3x":bool(ratio and ratio>3),"over_5x":bool(ratio and ratio>5),"absolute_spread":max(values)-min(values) if values else None}
    if ratio and ratio>5:warnings.append("EXTREME_MODEL_DISPERSION")
    diagnostics=dict(valuation.get("valuation_diagnostics") or {});high_uncertainty=bool(diagnostics.get("flags")) or bool(ratio and ratio>2)
    # A fully reconciled but widely dispersed set of valid models is legitimate
    # high uncertainty, not an unresolved data defect. Dispersion never changes
    # model values or weights and remains visible in the explanation object.
    hard_review=any(code in warnings for code in ("INPUT_SOURCE_DIVERGENCE","MARKET_CAP_BRIDGE_FAILURE","EV_BRIDGE_FAILURE","FCF_CANONICAL_RECONCILIATION_FAILURE","PERIOD_MISMATCH","SECTOR_MODEL_APPLICABILITY_WARNING"))
    state=REVIEW_REQUIRED if hard_review else CERTIFIED_HIGH_UNCERTAINTY if high_uncertainty else CERTIFIED
    result={"version":VERSION,"ticker":ticker,"company_type":valuation.get("company_type"),"validated_company_domain":domain,"certification_state":state,"customer_publication_allowed":state in {CERTIFIED,CERTIFIED_HIGH_UNCERTAINTY},"base_fair_value":valuation.get("atlas_base_fair_value"),"model_values":{m.get("methodology_id"):m.get("value") for m in models if m.get("status")=="PUBLISHED"},"model_weights":dict(valuation.get("model_weights") or {}),"input_lineage":inputs,"checks":checks,"model_applicability":applicability,"warnings":list(dict.fromkeys(warnings)),"primary_warning":next(iter(warnings),None),"valuation_as_of":valuation.get("valuation_as_of")}
    result["valuation_evidence_strength"]=classify_valuation_evidence(valuation,result)
    return result

def validation_health(rows:Sequence[Mapping[str,Any]])->dict[str,Any]:
    records=[validate_valuation(row) for row in rows];counts=Counter(r["certification_state"] for r in records)
    def warning(code):return sum(code in r.get("warnings",()) for r in records)
    return {"version":VERSION,"published_audited":sum(r["certification_state"] not in {INSUFFICIENT_INPUTS,NOT_APPLICABLE} for r in records),"certification_distribution":dict(counts),"input_source_divergence_count":warning("INPUT_SOURCE_DIVERGENCE"),"period_mismatch_count":warning("PERIOD_MISMATCH"),"market_cap_bridge_failure_count":warning("MARKET_CAP_BRIDGE_FAILURE"),"ev_bridge_failure_count":warning("EV_BRIDGE_FAILURE"),"fcf_reconciliation_failure_count":warning("FCF_CANONICAL_RECONCILIATION_FAILURE"),"sector_model_applicability_warning_count":warning("SECTOR_MODEL_APPLICABILITY_WARNING"),"extreme_model_dispersion_count":sum(bool((r.get("checks") or {}).get("dispersion",{}).get("over_5x")) for r in records),"records":records}

__all__=["ATLAS_STANDARD_FCF","CERTIFIED","CERTIFIED_HIGH_UNCERTAINTY","INSUFFICIENT_INPUTS","NOT_APPLICABLE","REVIEW_REQUIRED","TOLERANCES","VERSION","validate_valuation","validation_health"]
