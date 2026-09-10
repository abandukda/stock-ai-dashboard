"""Non-scoring evidence-strength certification for Professional Valuation V2."""
from __future__ import annotations

import math
import statistics
from typing import Any, Mapping

VERSION = "ATLAS_VALUATION_EVIDENCE_STRENGTH_V1"
MULTI_METHOD_CORROBORATED = "MULTI_METHOD_CORROBORATED"
SINGLE_METHOD_HIGH_SUPPORT = "SINGLE_METHOD_HIGH_SUPPORT"
SINGLE_METHOD_LIMITED_SUPPORT = "SINGLE_METHOD_LIMITED_SUPPORT"

# This registry describes the methods already implemented by Professional V2;
# it does not add models or alter their calculations.  An empty sole-method set
# means the current route has not established any one method as sufficient by
# itself for the strongest customer Action.
PROFESSIONAL_METHOD_POLICY = {
    "PROFITABLE_OPERATING_COMPANY":{"applicable":{"VAL_FCFF_DCF_V1","VAL_FORWARD_PE_V1","VAL_EV_EBITDA_V1","VAL_P_FCF_V1","VAL_DDM_GORDON_V1"},"sole_primary_sufficient":set()},
    "PROFITABLE_PHARMA":{"applicable":{"VAL_FCFF_DCF_V1","VAL_FORWARD_PE_V1","VAL_EV_EBITDA_V1","VAL_P_FCF_V1","VAL_DDM_GORDON_V1"},"sole_primary_sufficient":set()},
    "HIGH_GROWTH_SOFTWARE":{"applicable":{"VAL_FCFF_DCF_V1","VAL_FORWARD_PE_V1","VAL_EV_EBITDA_V1","VAL_P_FCF_V1"},"sole_primary_sufficient":{"VAL_FCFF_DCF_V1"}},
    "COMMODITY_PRODUCER":{"applicable":{"VAL_FCFF_DCF_V1","VAL_EV_EBITDA_V1","VAL_P_FCF_V1"},"sole_primary_sufficient":{"VAL_FCFF_DCF_V1"}},
    "BANK":{"applicable":{"VAL_FORWARD_PE_V1","VAL_DDM_GORDON_V1"},"sole_primary_sufficient":set()},
    "INSURER":{"applicable":{"VAL_FORWARD_PE_V1","VAL_DDM_GORDON_V1"},"sole_primary_sufficient":set()},
    "REIT":{"applicable":{"VAL_P_FCF_V1"},"sole_primary_sufficient":set()},
}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def certify_peer_multiple(model: Mapping[str, Any]) -> dict[str, Any]:
    assumptions = dict(model.get("key_assumptions") or {})
    evidence = dict(assumptions.get("peer_evidence") or {})
    peers = [dict(item) for item in evidence.get("included_peers") or () if isinstance(item, Mapping)]
    values = [_num(item.get("multiple")) for item in peers]
    values = [value for value in values if value is not None]
    used = _num(assumptions.get("multiple") or assumptions.get("justified_forward_pe"))
    reproduced = statistics.median(sorted(values)) if len(values) >= int(evidence.get("minimum_peer_count") or 3) else None
    required = ("peer_ticker", "peer_company_name", "peer_sector", "peer_industry", "basis", "evidence_as_of", "provider", "evidence_ids", "comparability_status")
    missing = sorted({field for peer in peers for field in required if not peer.get(field)})
    if model.get("methodology_id") == "VAL_EV_EBITDA_V1":
        missing.extend(field for field in ("peer_enterprise_value", "peer_ebitda", "peer_ev_ebitda") if any(_num(peer.get(field)) is None for peer in peers))
    ratio_mismatches=[]
    if model.get("methodology_id") == "VAL_EV_EBITDA_V1":
        for peer in peers:
            enterprise,ebitda,reported=(_num(peer.get(key)) for key in ("peer_enterprise_value","peer_ebitda","peer_ev_ebitda"))
            # Twelve's provider EV/EBITDA is a current/TTM statistic.  Do not
            # compare it with an annual or forward EBITDA denominator.  That
            # is a period mismatch, not a failed numerical reconciliation.
            same_basis = str(peer.get("peer_ebitda_basis") or "").upper() == str(peer.get("peer_ev_ebitda_basis") or "").upper() != ""
            if same_basis and enterprise is not None and ebitda not in (None,0) and reported is not None and not math.isclose(enterprise/ebitda,reported,rel_tol=.01):
                ratio_mismatches.append(peer.get("peer_ticker"))
    flags = sorted({flag for peer in peers for flag in peer.get("comparability_flags") or ()})
    reasons=[]
    if "evidence_as_of" in missing: reasons.append("PEER_VALUATION_AS_OF_UNAVAILABLE")
    if missing: reasons.append("PEER_VALUATION_LINEAGE_INCOMPLETE")
    if flags: reasons.append("PEER_COMPARABILITY_UNCERTIFIED")
    if ratio_mismatches: reasons.append("PEER_EV_EBITDA_RECONCILIATION_FAILED")
    if reproduced is None or used is None or not math.isclose(reproduced or 0,used or 0,rel_tol=1e-9,abs_tol=1e-9): reasons.append("PEER_MEDIAN_RECONCILIATION_FAILED")
    status = "CERTIFIED" if not reasons else "INSUFFICIENT"
    return {"version":VERSION,"status":status,"used_multiple":used,"reproduced_median":reproduced,
            "included_peer_count":len(peers),"missing_fields":sorted(set(missing)),"comparability_flags":flags,"ratio_mismatch_peers":ratio_mismatches,
            "reason_codes":list(dict.fromkeys(reasons)),"final_peer_set":[peer.get("peer_ticker") for peer in peers]}


def certify_method_bridges(professional: Mapping[str,Any], validation: Mapping[str,Any]) -> dict[str,Any]:
    """Certify only bridge inputs consumed by each published method."""
    checks=dict(validation.get("checks") or {}); lineage=dict(validation.get("input_lineage") or {})
    output={}
    def requirement(name,value,*,check=None,source=None):
        present=value is not None and value!="" and value!=[]
        check_ok=check is None or (checks.get(check) or {}).get("status") in {"PASS","NOT_TESTABLE"}
        item={"required":True,"certified":bool(present and check_ok),"value_present":present,
              "evidence_id":(lineage.get(source or name) or {}).get("evidence_id") or (lineage.get(source or name) or {}).get("endpoint"),
              "certification_check":check,"reason":None}
        if not present:item["reason"]="VALUATION_BRIDGE_INPUT_UNCERTIFIED"
        elif not check_ok:item["reason"]="VALUATION_BRIDGE_BASIS_MISMATCH"
        return item
    for model in professional.get("models") or ():
        if model.get("status")!="PUBLISHED":continue
        method=model.get("methodology_id"); a=dict(model.get("key_assumptions") or {})
        if method=="VAL_FCFF_DCF_V1":
            inputs={"forecast_fcff":requirement("forecast_fcff",a.get("forecast_fcff"),check="period_basis"),"wacc":requirement("wacc",a.get("wacc")),"terminal_growth":requirement("terminal_growth",a.get("terminal_growth")),"total_debt":requirement("total_debt",a.get("total_debt"),source="debt"),"cash_and_equivalents":requirement("cash_and_equivalents",a.get("cash_and_equivalents"),source="cash"),"diluted_shares":requirement("diluted_shares",a.get("diluted_shares"),source="diluted_shares")}
        elif method=="VAL_FORWARD_PE_V1":
            inputs={"forward_eps":requirement("forward_eps",a.get("forward_eps"),check="period_basis"),"forward_eps_period":requirement("forward_eps_period",model.get("fiscal_period"),check="period_basis",source="forward_eps"),"justified_forward_pe":requirement("justified_forward_pe",a.get("justified_forward_pe")),"multiple_basis":requirement("multiple_basis",a.get("multiple_basis"))}
        elif method=="VAL_EV_EBITDA_V1":
            inputs={"forward_ebitda":requirement("forward_ebitda",a.get("forward_ebitda"),check="ev_bridge",source="ebitda"),"multiple":requirement("multiple",a.get("multiple")),"net_debt":requirement("net_debt",a.get("net_debt"),check="ev_bridge"),"diluted_shares":requirement("diluted_shares",a.get("diluted_shares"),check="ev_bridge",source="diluted_shares")}
        elif method=="VAL_P_FCF_V1":
            inputs={"normalized_fcf":requirement("normalized_fcf",a.get("normalized_fcf"),check="fcf_reconciliation",source="free_cash_flow"),"multiple":requirement("multiple",a.get("multiple")),"diluted_shares":requirement("diluted_shares",a.get("diluted_shares"),source="diluted_shares")}
        elif method=="VAL_DDM_GORDON_V1":
            inputs={"dividend_next":requirement("dividend_next",a.get("dividend_next")),"cost_of_equity":requirement("cost_of_equity",a.get("cost_of_equity")),"dividend_growth":requirement("dividend_growth",a.get("dividend_growth"))}
        else: inputs={}
        passed=bool(inputs) and all(item["certified"] for item in inputs.values())
        output[method]={"status":"CERTIFIED" if passed else "INSUFFICIENT","inputs":inputs,
                        "reason_codes":[] if passed else sorted({item["reason"] for item in inputs.values() if item["reason"]})}
    return {"status":"CERTIFIED" if output and all(item["status"]=="CERTIFIED" for item in output.values()) else "INSUFFICIENT",
            "methods":output,"aggregation":"PUBLISHED_METHODS_ONLY"}


def classify_valuation_evidence(professional: Mapping[str, Any], validation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    models = [dict(model) for model in professional.get("models") or () if model.get("status") == "PUBLISHED"]
    company_type=str(professional.get("company_type") or "")
    policy=PROFESSIONAL_METHOD_POLICY.get(company_type,{"applicable":set(),"sole_primary_sufficient":set()})
    validation=dict(validation or {})
    bridge_certification=certify_method_bridges(professional,validation)
    bridges_ok=bridge_certification.get("status")=="CERTIFIED"
    applicability={item.get("methodology_id"):item.get("applicability") for item in validation.get("model_applicability") or ()}
    methods_appropriate=bool(models) and all(model.get("methodology_id") in policy["applicable"] and applicability.get(model.get("methodology_id"),"PRIMARY_APPROPRIATE")!="WEAK_FOR_COMPANY_TYPE" for model in models)
    peer_checks=[certify_peer_multiple(model) for model in models if model.get("methodology_id") in {"VAL_EV_EBITDA_V1","VAL_FORWARD_PE_V1","VAL_P_FCF_V1"}]
    peer_supported=all(check.get("status")=="CERTIFIED" for check in peer_checks) if peer_checks else True
    if len(models) >= 2:
        requirements={"company_type_route_registered":company_type in PROFESSIONAL_METHOD_POLICY,
                      "published_methods_professionally_appropriate":methods_appropriate,
                      "peer_evidence_certified_where_used":peer_supported,
                      "all_bridge_inputs_certified":bridges_ok,
                      "valuation_certification_publishable":validation.get("customer_publication_allowed") is not False}
        eligible=all(requirements.values())
        return {"version":VERSION,"classification":MULTI_METHOD_CORROBORATED,"strong_action_eligible":eligible,
                "published_method_count":len(models),"sole_method":None,"company_type":company_type,
                "professionally_applicable_methods":sorted(policy["applicable"]),"requirements":requirements,
                "unmet_requirements":[key for key,value in requirements.items() if not value],"peer_certifications":peer_checks,
                "method_bridge_certification":bridge_certification}
    if not models:
        return {"version":VERSION,"classification":SINGLE_METHOD_LIMITED_SUPPORT,"strong_action_eligible":False,
                "published_method_count":0,"sole_method":None,"requirements":{"valuation_published":False}}
    model=models[0]; methodology=str(model.get("methodology_id") or "")
    peer_check=certify_peer_multiple(model) if methodology in {"VAL_EV_EBITDA_V1","VAL_FORWARD_PE_V1","VAL_P_FCF_V1"} else {"status":"NOT_REQUIRED"}
    approval=dict(professional.get("single_method_sufficiency") or {})
    flags=set((professional.get("valuation_diagnostics") or {}).get("flags") or ())-{"MODEL_CONCENTRATION_SINGLE_METHOD"}
    explanation=dict(professional.get("valuation_explanation") or {})
    requirements={
        "company_type_route_registered":company_type in PROFESSIONAL_METHOD_POLICY,
        "method_professionally_appropriate":methods_appropriate,
        "explicit_method_sufficiency":methodology in policy["sole_primary_sufficient"] and approval.get("status")=="APPROVED" and approval.get("methodology_id")==methodology and approval.get("company_type")==company_type,
        "peer_evidence_certified":peer_check.get("status") in {"CERTIFIED","NOT_REQUIRED"},
        "valuation_confidence_high_support":(_num(professional.get("valuation_confidence")) or 0)>=70,
        "no_material_qa_flags":not flags,
        "all_bridge_inputs_certified":bridges_ok,
        "scenario_evidence_published":professional.get("scenario_status")=="PUBLISHED" and professional.get("atlas_bear_case") is not None and professional.get("atlas_bull_case") is not None,
        "economic_explanation_complete":all(explanation.get(key) for key in ("primary_valuation_driver","secondary_valuation_driver","biggest_valuation_uncertainty")),
    }
    high=all(requirements.values())
    return {"version":VERSION,"classification":SINGLE_METHOD_HIGH_SUPPORT if high else SINGLE_METHOD_LIMITED_SUPPORT,
            "strong_action_eligible":high,"published_method_count":1,"sole_method":methodology,
            "sole_method_weight":model.get("weight"),"company_type":company_type,
            "professionally_applicable_methods":sorted(policy["applicable"]),"requirements":requirements,"peer_certification":peer_check,
            "method_bridge_certification":bridge_certification,
            "unmet_requirements":[key for key,value in requirements.items() if not value]}


__all__=["MULTI_METHOD_CORROBORATED","PROFESSIONAL_METHOD_POLICY","SINGLE_METHOD_HIGH_SUPPORT","SINGLE_METHOD_LIMITED_SUPPORT","VERSION","certify_method_bridges","certify_peer_multiple","classify_valuation_evidence"]
