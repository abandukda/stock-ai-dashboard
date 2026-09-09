"""Deterministic professional valuation inputs from approved evidence.

The module forecasts operating inputs from aligned annual statements and
consensus revenue. It never uses an LLM, legacy ATLAS value, or Street target.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence

from engines.institutional_formulas import capm_cost_of_equity, fcff, wacc

VERSION = "ATLAS_PROFESSIONAL_EVIDENCE_V1"
ASSUMPTIONS_PATH = Path(__file__).resolve().parents[1] / "config" / "professional_market_assumptions.json"


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _get(source: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(source, Mapping): return None
        source = source.get(key)
    return source


def _payload(row: Mapping[str, Any], family: str) -> Mapping[str, Any]:
    dossier = row.get("twelve_trial_dossier") or {}
    return _get(dossier, "families", family, "payload") or {}


def _records(row: Mapping[str, Any], family: str) -> list[Mapping[str, Any]]:
    values = _payload(row, family).get(family)
    return [item for item in values or () if isinstance(item, Mapping)] if isinstance(values, list) else []


def load_market_assumptions(path: Path = ASSUMPTIONS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _median_ratio(records: Sequence[Mapping[str, Any]], numerator, denominator) -> float | None:
    ratios = []
    for record in records[:3]:
        top, bottom = _num(numerator(record)), _num(denominator(record))
        if top is not None and bottom and bottom > 0: ratios.append(top / bottom)
    return statistics.median(ratios) if ratios else None


def build_operating_forecast(row: Mapping[str, Any], *, years: int = 5) -> dict[str, Any]:
    income, cash = _records(row, "income_statement"), _records(row, "cash_flow")
    revenue = _num(row.get("forward_revenue"))
    if revenue is None or not income or not cash:
        return {"status":"ELIGIBLE_INCOMPLETE","reason":"FCFF_INPUTS_INCOMPLETE"}
    margin = _median_ratio(income, lambda x:x.get("ebit") or x.get("operating_income"), lambda x:x.get("sales"))
    da_ratio = _median_ratio(cash, lambda x:_get(x,"operating_activities","depreciation"), lambda x:next((i.get("sales") for i in income if i.get("fiscal_date")==x.get("fiscal_date")), None))
    capex_ratio = _median_ratio(cash, lambda x:abs(_num(_get(x,"investing_activities","capital_expenditures"))) if _num(_get(x,"investing_activities","capital_expenditures")) is not None else None, lambda x:next((i.get("sales") for i in income if i.get("fiscal_date")==x.get("fiscal_date")), None))
    nwc_ratio = _median_ratio(cash, lambda x:-sum(_num(_get(x,"operating_activities",key)) or 0 for key in ("accounts_receivable","accounts_payable","other_assets_liabilities")), lambda x:next((i.get("sales") for i in income if i.get("fiscal_date")==x.get("fiscal_date")), None))
    tax_rates = [max(0.0,min(.35,float(i["income_tax"])/float(i["pretax_income"]))) for i in income[:3] if _num(i.get("income_tax")) is not None and (_num(i.get("pretax_income")) or 0)>0]
    if None in (margin, da_ratio, capex_ratio) or not tax_rates:
        return {"status":"ELIGIBLE_INCOMPLETE","reason":"FCFF_INPUTS_INCOMPLETE"}
    tax_rate = statistics.median(tax_rates)
    estimate = row.get("forward_estimate_evidence") or {}; rev = estimate.get("revenue") or {}
    growth = _num(rev.get("sales_growth"))
    if growth is None:
        prior = _num(income[0].get("sales")); growth = revenue/prior-1 if prior and prior>0 else None
    if growth is None: return {"status":"ELIGIBLE_INCOMPLETE","reason":"FORWARD_PERIOD_MISSING"}
    assumptions = load_market_assumptions(); terminal = float(assumptions["terminal_growth"])
    forecast, details = [], []
    for year in range(1,years+1):
        if year > 1:
            faded = growth + (terminal-growth)*(year-1)/(years-1)
            revenue *= 1+faded
        else: faded = growth
        ebit = revenue*margin; da=revenue*da_ratio; capex=revenue*capex_ratio
        change_nwc=revenue*(nwc_ratio or 0.0)
        value=fcff(ebit,tax_rate,da,capex,change_nwc)
        forecast.append(value); details.append({"year":year,"revenue":revenue,"growth":faded,"ebit_margin":margin,"tax_rate":tax_rate,"da_ratio":da_ratio,"capex_ratio":capex_ratio,"nwc_ratio":nwc_ratio,"change_nwc":change_nwc,"fcff":value})
    return {"status":"ELIGIBLE_COMPLETE","forecast_fcff":forecast,"forecast_detail":details,
            "methodology_id":"FIN_FCFF_V1","source_periods":[r.get("fiscal_date") for r in income[:3]],
            "assumption_lineage":{"revenue":"annual consensus","ratios":"median of up to three aligned annual statements","change_nwc":"median historical cash-flow-statement working-capital adjustment ratio; zero only when the provider has no usable series"}}


def enrich_professional_inputs(row: Mapping[str, Any]) -> dict[str, Any]:
    output=dict(row); assumptions=load_market_assumptions(); forecast=build_operating_forecast(output)
    if forecast.get("status")=="ELIGIBLE_COMPLETE": output.update(forecast)
    debt=_num(output.get("total_debt")); cash=_num(output.get("cash_and_equivalents")); equity=_num(output.get("market_cap")); beta=_num(output.get("beta"))
    cash_rows=_records(output,"cash_flow"); interest=next((_num(r.get("interest_paid")) for r in cash_rows if _num(r.get("interest_paid")) is not None),None)
    tax_rate=_num((forecast.get("forecast_detail") or [{}])[0].get("tax_rate"))
    if None not in (debt,cash,equity,beta,interest,tax_rate) and debt and debt>0 and equity and equity>0:
        cost_equity=capm_cost_of_equity(assumptions["risk_free_rate"],beta,assumptions["equity_risk_premium"])
        accounting_cost_debt=max(0.0,interest/debt)
        # A historical accounting coupon proxy is not a current borrowing
        # yield. In the absence of observable spread evidence it may not sit
        # below the maturity-matched Treasury benchmark.
        cost_debt=max(accounting_cost_debt, assumptions["risk_free_rate"])
        capital_wacc=wacc(equity,debt,cost_equity,cost_debt,tax_rate)
        output.update({"risk_free_rate":assumptions["risk_free_rate"],"equity_risk_premium":assumptions["equity_risk_premium"],"cost_of_equity":cost_equity,"cost_of_debt":cost_debt,"accounting_cost_of_debt_proxy":accounting_cost_debt,"cost_of_debt_method":"interest paid / current interest-bearing debt accounting proxy, floored at maturity-matched Treasury when no credit-spread evidence is available","after_tax_cost_of_debt":cost_debt*(1-tax_rate),"tax_rate":tax_rate,"wacc":capital_wacc,"wacc_minus_g":capital_wacc-assumptions["terminal_growth"],"equity_weight":equity/(equity+debt),"debt_weight":debt/(equity+debt),"market_equity_value":equity,"debt_value":debt,"terminal_growth":assumptions["terminal_growth"],"market_assumption_lineage":assumptions})
        base=output["wacc"]; output["sensitivity_wacc"]=[base-.01,base,base+.01]; output["sensitivity_terminal_growth"]=[max(0,assumptions["terminal_growth"]-.005),assumptions["terminal_growth"],assumptions["terminal_growth"]+.005]
        rev=(output.get("forward_estimate_evidence") or {}).get("revenue") or {}
        consensus=_num(rev.get("avg_estimate")); low=_num(rev.get("low_estimate")); high=_num(rev.get("high_estimate"))
        if output.get("forecast_fcff") and consensus and low and high and consensus>0:
            output["valuation_scenarios"]={
                "bear":{"forecast_fcff":[value*low/consensus for value in output["forecast_fcff"]],"wacc":base,"terminal_growth":max(0,assumptions["terminal_growth"]-.005)},
                "bull":{"forecast_fcff":[value*high/consensus for value in output["forecast_fcff"]],"wacc":base,"terminal_growth":assumptions["terminal_growth"]+.005},
            }
    output["professional_input_version"]=VERSION
    return output


def apply_peer_multiple_evidence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prepared=[enrich_professional_inputs(row) for row in rows]
    for row in prepared:
        industry_peers=[p for p in prepared if p is not row and p.get("industry") and str(p.get("industry")).lower()==str(row.get("industry") or "").lower()]
        used_sector_fallback=len(industry_peers)<3
        peers=industry_peers if not used_sector_fallback else [p for p in prepared if p is not row and p.get("sector") and str(p.get("sector")).lower()==str(row.get("sector") or "").lower()]
        selection_rule="same sector fallback" if used_sector_fallback else "same industry"
        subject_cap=_num(row.get("market_cap"))

        def peer_record(peer: Mapping[str, Any], metric: str, value: float | None, included: bool, reason: str) -> dict[str, Any]:
            peer_cap=_num(peer.get("market_cap")); scale_ratio=max(subject_cap,peer_cap)/min(subject_cap,peer_cap) if subject_cap and peer_cap and min(subject_cap,peer_cap)>0 else None
            peer_debt=_num(peer.get("total_debt")); peer_cash=_num(peer.get("cash_and_equivalents"))
            peer_ev=peer_cap+peer_debt-peer_cash if None not in (peer_cap,peer_debt,peer_cash) else None
            lineage=(peer.get("professional_evidence_lineage") or {}).get("fields") or {}
            comparability_flags=[flag for flag,condition in (("SECTOR_FALLBACK",used_sector_fallback),("SCALE_GAP_OVER_10X",bool(scale_ratio and scale_ratio>10)),("SECURITY_TYPE_MISMATCH",bool(row.get("security_type") and peer.get("security_type") and row.get("security_type")!=peer.get("security_type")))) if condition]
            return {
                "subject_ticker":str(row.get("ticker") or row.get("symbol") or ""),
                "peer_ticker":str(peer.get("ticker") or peer.get("Ticker") or peer.get("symbol") or ""),
                "peer_company_name":peer.get("company") or peer.get("company_name") or peer.get("name"),
                "peer_sector":peer.get("sector"),"peer_industry":peer.get("industry"),
                "peer_security_type":peer.get("security_type"),"peer_market_cap":peer_cap,
                "peer_enterprise_value":peer_ev,"peer_enterprise_value_basis":"MARKET_CAP_PLUS_DEBT_MINUS_CASH",
                "peer_ebitda":_num(peer.get("forward_ebitda")),
                "peer_ev_ebitda":_num(peer.get("provider_ev_ebitda")),
                "multiple":value,"multiple_metric":metric,"basis":"TTM" if metric!="FORWARD_PE" else "FORWARD",
                "provider_fetched_at":peer.get("professional_evidence_fetched_at"),
                "evidence_as_of":peer.get("professional_evidence_as_of"),
                "fiscal_period_end":peer.get("financial_reporting_period"),
                "as_of":peer.get("professional_evidence_as_of"),"provider":"TWELVE_DATA",
                "evidence_ids":list((peer.get("professional_evidence_lineage") or {}).get("evidence_ids") or ()),
                "inclusion_reason":f"{selection_rule}; valid positive {metric}" if included else None,
                "exclusion_reason":None if included else reason,
                "comparability_status":"CERTIFIED" if not comparability_flags else "LIMITED",
                "comparability_flags":comparability_flags,
                "source_lineage":dict(lineage.get({"FORWARD_PE":"provider_forward_pe","EV_EBITDA":"provider_ev_ebitda","P_FCF":"provider_p_fcf"}[metric]) or {}),
            }

        metric_specs=(
            ("FORWARD_PE","provider_forward_pe","justified_forward_pe","median current forward P/E of deterministic peers"),
            ("EV_EBITDA","provider_ev_ebitda","justified_ev_ebitda","median current EV/EBITDA of deterministic peers"),
            ("P_FCF","provider_p_fcf","justified_p_fcf","median current P/FCF of deterministic peers"),
        )
        evidence={}
        for metric,source_field,target_field,basis in metric_specs:
            records=[]
            for peer in peers:
                value=_num(peer.get(source_field)); included=value is not None and 0<value<100
                reason="MULTIPLE_MISSING" if value is None else "MULTIPLE_NONPOSITIVE" if value<=0 else "MULTIPLE_OUTSIDE_GOVERNED_RANGE"
                records.append(peer_record(peer,metric,value,True,reason) if included else {
                    "subject_ticker":str(row.get("ticker") or row.get("symbol") or ""),
                    "peer_ticker":str(peer.get("ticker") or peer.get("Ticker") or peer.get("symbol") or ""),
                    "peer_company_name":peer.get("company") or peer.get("company_name") or peer.get("name"),
                    "multiple_metric":metric,"exclusion_reason":reason,
                })
            included_records=[record for record in records if record.get("inclusion_reason")]
            values=sorted(float(record["multiple"]) for record in included_records)
            median=statistics.median(values) if len(values)>=3 else None
            evidence[metric]={"subject_ticker":str(row.get("ticker") or row.get("symbol") or ""),"selection_rule":selection_rule,
                "included_peers":included_records,"excluded_peers":[record for record in records if record["exclusion_reason"]],
                "final_peer_set":[record["peer_ticker"] for record in included_records],"published_median":median,
                "median_calculation":{"ordered_values":values,"function":"statistics.median"},"minimum_peer_count":3,
                "provider_fetched_at":row.get("professional_evidence_fetched_at"),
                "evidence_as_of":row.get("professional_evidence_as_of"),
                "as_of":row.get("professional_evidence_as_of"),"provider":"TWELVE_DATA"}
            if median is not None:
                row.update({target_field:median,f"{target_field}_basis":basis,f"{target_field}_range":[values[0],values[-1]],f"{target_field}_peer_evidence":evidence[metric]})
        peer_ids=[str(p.get("ticker") or p.get("Ticker") or p.get("symbol")) for p in peers]
        row["deterministic_peer_set"]={"peers":peer_ids,"rule":f"{selection_rule}; current universe; valid positive comparable multiple","as_of":row.get("professional_evidence_as_of"),"multiple_evidence":evidence}
    return prepared

__all__=["VERSION","apply_peer_multiple_evidence","build_operating_forecast","enrich_professional_inputs","load_market_assumptions"]
