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
        cost_debt=max(0.0,interest/debt)
        output.update({"risk_free_rate":assumptions["risk_free_rate"],"equity_risk_premium":assumptions["equity_risk_premium"],"cost_of_equity":cost_equity,"cost_of_debt":cost_debt,"tax_rate":tax_rate,"wacc":wacc(equity,debt,cost_equity,cost_debt,tax_rate),"terminal_growth":assumptions["terminal_growth"],"market_assumption_lineage":assumptions})
        base=output["wacc"]; output["sensitivity_wacc"]=[base-.01,base,base+.01]; output["sensitivity_terminal_growth"]=[max(0,assumptions["terminal_growth"]-.005),assumptions["terminal_growth"],assumptions["terminal_growth"]+.005]
        rev=(output.get("forward_estimate_evidence") or {}).get("revenue") or {}
        consensus=_num(rev.get("avg_estimate")); low=_num(rev.get("low_estimate")); high=_num(rev.get("high_estimate"))
        if output.get("forecast_fcff") and consensus and low and high and consensus>0:
            output["valuation_scenarios"]={
                "bear":{"forecast_fcff":[value*low/consensus for value in output["forecast_fcff"]],"wacc":base+.01,"terminal_growth":max(0,assumptions["terminal_growth"]-.005)},
                "bull":{"forecast_fcff":[value*high/consensus for value in output["forecast_fcff"]],"wacc":base-.01,"terminal_growth":assumptions["terminal_growth"]+.005},
            }
    output["professional_input_version"]=VERSION
    return output


def apply_peer_multiple_evidence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prepared=[enrich_professional_inputs(row) for row in rows]
    for row in prepared:
        peers=[p for p in prepared if p is not row and p.get("industry") and str(p.get("industry")).lower()==str(row.get("industry") or "").lower()]
        if len(peers)<3: peers=[p for p in prepared if p is not row and p.get("sector") and str(p.get("sector")).lower()==str(row.get("sector") or "").lower()]
        pe=sorted(v for p in peers if (v:=_num(p.get("provider_forward_pe"))) is not None and 0<v<100)
        ev=sorted(v for p in peers if (v:=_num(p.get("provider_ev_ebitda"))) is not None and 0<v<100)
        pfcf=sorted(v for p in peers if (v:=_num(p.get("provider_p_fcf"))) is not None and 0<v<100)
        peer_ids=[str(p.get("ticker") or p.get("Ticker") or p.get("symbol")) for p in peers]
        row["deterministic_peer_set"]={"peers":peer_ids,"rule":"same industry; same sector fallback; current universe; valid positive comparable multiple","as_of":row.get("professional_evidence_as_of")}
        if len(pe)>=3:
            row.update({"justified_forward_pe":statistics.median(pe),"justified_forward_pe_basis":"median current forward P/E of deterministic peers","justified_forward_pe_range":[pe[0],pe[-1]]})
        if len(ev)>=3:
            row.update({"justified_ev_ebitda":statistics.median(ev),"justified_ev_ebitda_basis":"median current EV/EBITDA of deterministic peers","justified_ev_ebitda_range":[ev[0],ev[-1]]})
        if len(pfcf)>=3:
            row.update({"justified_p_fcf":statistics.median(pfcf),"justified_p_fcf_basis":"median current P/FCF of deterministic peers","justified_p_fcf_range":[pfcf[0],pfcf[-1]]})
    return prepared

__all__=["VERSION","apply_peer_multiple_evidence","build_operating_forecast","enrich_professional_inputs","load_market_assumptions"]
