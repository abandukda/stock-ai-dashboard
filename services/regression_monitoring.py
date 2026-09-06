"""Non-mutating run-over-run diagnostics for canonical ATLAS artifacts."""
from __future__ import annotations
from typing import Any,Mapping,Sequence
def compare_runs(previous:Sequence[Mapping[str,Any]],current:Sequence[Mapping[str,Any]])->list[dict[str,Any]]:
    old={str(x.get('ticker')):x for x in previous};alerts=[]
    for row in current:
        ticker=str(row.get('ticker'));prior=old.get(ticker)
        if not prior:continue
        pe=dict(prior.get('canonical_investment_evaluation') or {});ce=dict(row.get('canonical_investment_evaluation') or {})
        pv=dict((pe.get('atlas_valuation') or {}).get('professional_valuation_v2') or {});cv=dict((ce.get('atlas_valuation') or {}).get('professional_valuation_v2') or {})
        def add(kind,before,after): alerts.append({'ticker':ticker,'type':kind,'before':before,'after':after,'action':'REVIEW_ONLY'})
        if pv.get('company_type')!=cv.get('company_type'):add('COMPANY_TYPE_CHANGED',pv.get('company_type'),cv.get('company_type'))
        if len([x for x in pv.get('models') or [] if x.get('status')=='PUBLISHED'])>len([x for x in cv.get('models') or [] if x.get('status')=='PUBLISHED']):add('MODEL_COUNT_DROPPED',None,None)
        same_inputs=pe.get('input_digest')==ce.get('input_digest')
        for kind,key in (('WACC_CHANGED_WITHOUT_INPUT_CHANGE','wacc'),('FAIR_VALUE_CHANGED_WITHOUT_INPUT_CHANGE','atlas_base_fair_value'),('VALUATION_CONFIDENCE_CHANGED_WITHOUT_INPUT_CHANGE','valuation_confidence')):
            if same_inputs and pv.get(key)!=cv.get(key): add(kind,pv.get(key),cv.get(key))
        old_periods=[(x.get('metric'),x.get('fiscal_period')) for x in pe.get('forward_estimates') or []]
        new_periods=[(x.get('metric'),x.get('fiscal_period')) for x in ce.get('forward_estimates') or []]
        if same_inputs and old_periods!=new_periods:add('FORWARD_PERIOD_CHANGED_WITHOUT_INPUT_CHANGE',old_periods,new_periods)
        if (pe.get('guidance') or {}).get('state')!=(ce.get('guidance') or {}).get('state') and pe.get('input_digest')==ce.get('input_digest'):add('ACTION_CHANGED_WITHOUT_INPUT_CHANGE',(pe.get('guidance') or {}).get('state'),(ce.get('guidance') or {}).get('state'))
        if pe.get('methodology_registry_version')!=ce.get('methodology_registry_version'):add('METHODOLOGY_VERSION_CHANGED',pe.get('methodology_registry_version'),ce.get('methodology_registry_version'))
        if row.get('home_action') and row.get('research_action') and row.get('home_action')!=row.get('research_action'):add('HOME_RESEARCH_MISMATCH',row.get('home_action'),row.get('research_action'))
    return alerts
__all__=['compare_runs']
