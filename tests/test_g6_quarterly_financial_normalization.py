import copy,hashlib,json
from pathlib import Path
import pytest
from services.g6_annual_financial_normalization import canonical_bytes
from services.g6_quarterly_financial_normalization import QuarterlyNormalizationError,build_quarterly_series,normalize_files,normalize_response

def fixture(quarter=2,value=30.0,*,accession='a2',accepted='2026-08-01T00:00:00Z'):
    payload={'symbol':'AVT','cik':'8858','data':[{'accessNumber':accession,'symbol':'AVT','cik':'8858','year':2026,'quarter':quarter,'form':'10-Q','startDate':'2026-01-01','endDate':f'2026-0{quarter*3}-30','filedDate':'2026-08-01','acceptedDate':accepted,
        'report':{'ic':[{'concept':'Revenue','label':'Revenue','unit':'usd','value':value},{'concept':'Bad','unit':'usd','value':None}], 'bs':[{'concept':'Cash','label':'Cash','unit':'usd','value':5}], 'cf':[]}}]}
    raw=canonical_bytes(payload);meta={'ticker':'AVT','endpoint':'/stock/financials-reported','parameters':{'symbol':'AVT','freq':'quarterly'},'status_code':200,'attempt_count':1,'retry_count':0,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)}
    return payload,meta

def test_normalization_retains_every_fact_and_types_unavailable_values():
    payload,meta=fixture();result=normalize_response(payload,meta,raw_file='raw.json')
    assert result['coverage']=={'filing_count':1,'source_fact_count':3,'available_fact_count':2,'unavailable_fact_count':1,'currencies':['USD']}
    bad=result['filings'][0]['facts'][1];assert bad['status']=='UNAVAILABLE' and bad['value'] is None
    assert result['filings'][0]['facts'][0]['duration_semantics']=='REPORTED_CUMULATIVE_YTD'
    assert result['filings'][0]['facts'][2]['duration_semantics']=='INSTANTANEOUS_AT_PERIOD_END'

def test_raw_digest_and_zero_retry_metadata_fail_closed(tmp_path):
    payload,meta=fixture();raw=canonical_bytes(payload);rp=tmp_path/'r.json';mp=tmp_path/'m.json';rp.write_bytes(raw);mp.write_text(json.dumps(meta))
    assert normalize_files(rp,mp)['ticker']=='AVT'
    rp.write_bytes(raw+b' ')
    with pytest.raises(QuarterlyNormalizationError,match='INTEGRITY'):normalize_files(rp,mp)
    changed=copy.deepcopy(meta);changed['retry_count']=1
    with pytest.raises(QuarterlyNormalizationError,match='HEALTH'):normalize_response(payload,changed,raw_file='r.json')

def test_discrete_flows_require_exact_prior_ytd_and_restatements_choose_latest():
    q1,m1=fixture(1,10,accession='a1',accepted='2026-05-01T00:00:00Z');q2,m2=fixture(2,30,accession='a2-old',accepted='2026-08-01T00:00:00Z');q2b,m2b=fixture(2,34,accession='a2-new',accepted='2026-08-02T00:00:00Z')
    records=[normalize_response(x,m,raw_file=f'{i}.json')['filings'][0] for i,(x,m) in enumerate(((q1,m1),(q2,m2),(q2b,m2b)))]
    base=normalize_response(q1,m1,raw_file='base.json');base['filings']=records;base['coverage']['filing_count']=3;base['normalized_sha256']='n'*64
    series=build_quarterly_series(base);assert len(series['periods'])==2 and series['periods'][-1]['accession']=='a2-new' and series['periods'][-1]['restatement_candidates']==2
    revenue=next(x for x in series['periods'][-1]['discrete_flow_facts'] if x['concept']=='Revenue')
    assert revenue['status']=='AVAILABLE' and revenue['value']==24 and revenue['method']=='CURRENT_YTD_MINUS_PRIOR_YTD'
