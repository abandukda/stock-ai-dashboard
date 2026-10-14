"""Read-only customer projection of source-bound annual and quarterly facts."""
from __future__ import annotations
from collections import defaultdict
from typing import Any,Mapping

from services.customer_annual_statement_projection import project_customer_annual_statements

CONTRACT="ATLAS_CUSTOMER_STATEMENT_HISTORY_PROJECTION_V1"

def _field_id(fact:Mapping[str,Any])->str:
    unit=fact.get('unit') or {}
    return '|'.join((str(fact.get('statement')),str(fact.get('concept')),str(unit.get('canonical')),str(unit.get('original'))))

def _quarterly_projection(normalized:Mapping[str,Any],series:Mapping[str,Any],max_visible_periods:int)->dict[str,Any]:
    if normalized.get('contract')!='ATLAS_G6_QUARTERLY_STATEMENT_NORMALIZATION_V1':raise ValueError('QUARTERLY_NORMALIZED_CONTRACT_MISMATCH')
    if series.get('contract')!='ATLAS_G6_QUARTERLY_FINANCIAL_SERIES_V1' or series.get('ticker')!=normalized.get('ticker'):raise ValueError('QUARTERLY_SERIES_CONTRACT_MISMATCH')
    if normalized.get('ratings_changed') is not False or normalized.get('publications_changed') is not False:raise ValueError('PROTECTED_OUTPUT_INVARIANCE_UNPROVEN')
    periods=list(series.get('periods') or [])[-max_visible_periods:]
    grouped=defaultdict(lambda:defaultdict(list)); metadata={}
    for period in periods:
        accession=period['accession']
        for fact in period.get('facts') or []:
            fid=_field_id(fact);grouped[fid][accession].append(fact)
            metadata.setdefault(fid,{'field_id':fid,'statement':fact['statement'],'concept':fact['concept'],'unit':fact['unit'],'labels':set()})
            if fact.get('label'):metadata[fid]['labels'].add(fact['label'])
    tables={key:[] for key in ('INCOME_STATEMENT','BALANCE_SHEET','CASH_FLOW')};counts={'available':0,'unavailable':0,'ambiguous':0}
    for fid,meta in sorted(metadata.items(),key=lambda x:(x[1]['statement'],x[1]['concept'],x[0])):
        cells=[]
        for period in periods:
            matches=grouped[fid].get(period['accession'],[])
            if not matches:cell={'status':'UNAVAILABLE','value':None,'reason':'FIELD_NOT_REPORTED_FOR_PERIOD'}
            elif len(matches)>1:cell={'status':'AMBIGUOUS','value':None,'reason':'MULTIPLE_FACTS_FOR_FIELD_PERIOD','fact_ids':[x['fact_id'] for x in matches]}
            elif matches[0]['status']!='AVAILABLE':cell={'status':'UNAVAILABLE','value':None,'reason':matches[0]['unavailable_reason'],'fact_id':matches[0]['fact_id']}
            else:cell={'status':'AVAILABLE','value':matches[0]['value'],'fact_id':matches[0]['fact_id'],'provenance':matches[0]['provenance'],'duration_semantics':matches[0]['duration_semantics']}
            counts[cell['status'].lower()]+=1;cells.append({'accession':period['accession'],**cell})
        if any(c['status'] in {'AVAILABLE','AMBIGUOUS'} for c in cells):
            tables[meta['statement']].append({**meta,'labels':sorted(meta['labels']),'cells':cells})
    discrete={f"FY{p['fiscal_year']}Q{p['fiscal_quarter']}":p.get('discrete_flow_facts') or [] for p in periods}
    return {'status':'AVAILABLE' if periods else 'UNAVAILABLE','source_normalized_sha256':normalized['normalized_sha256'],
            'source_series_sha256':series['sha256'],'visible_periods':[{k:p[k] for k in ('fiscal_year','fiscal_quarter','fiscal_period_start','fiscal_period_end','filed_date','accepted_date','accession','restatement_candidates')} for p in periods],
            'retained_period_count':len(series.get('periods') or []),'visible_period_count':len(periods),'statements':tables,
            'cell_coverage':counts,'discrete_flow_facts':discrete,
            'disclosure':{'reported_flow_values':'CUMULATIVE_YTD_EXCEPT_Q1','discrete_flow_values':'DERIVED_ONLY_FROM_EXACT_PRIOR_YTD_MATCH','balance_sheet':'INSTANTANEOUS_AT_PERIOD_END','missing_values':'NEVER_RENDER_AS_ZERO'}}

def project_customer_statement_history(annual_presentation:Mapping[str,Any],quarterly_normalized:Mapping[str,Any],quarterly_series:Mapping[str,Any],*,max_annual_periods:int=5,max_quarterly_periods:int=8)->dict[str,Any]:
    annual=project_customer_annual_statements(annual_presentation,max_visible_periods=max_annual_periods)
    quarterly=_quarterly_projection(quarterly_normalized,quarterly_series,max_quarterly_periods)
    tickers={annual.get('ticker'),quarterly_normalized.get('ticker'),quarterly_series.get('ticker')}
    if len(tickers)!=1:raise ValueError('ANNUAL_QUARTERLY_TICKER_MISMATCH')
    return {'contract':CONTRACT,'status':'AVAILABLE' if annual['status']=='AVAILABLE' or quarterly['status']=='AVAILABLE' else 'UNAVAILABLE',
            'ticker':annual.get('ticker'),'annual':annual,'quarterly':quarterly,'read_only':True,
            'rating_authority':'UNCHANGED','publication_authority':'UNCHANGED','provider_calls':0}

__all__=['CONTRACT','project_customer_statement_history']
