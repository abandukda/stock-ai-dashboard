import copy
from services.customer_statement_history_projection import project_customer_statement_history
from services.customer_research_v2 import build_customer_research_v2
from tests.test_customer_annual_statement_projection import fixture as annual_fixture
from tests.test_customer_research_v2 import report

def quarterly_fixture():
    fact={'fact_id':'q1','statement':'INCOME_STATEMENT','concept':'Revenue','label':'Revenue','status':'AVAILABLE','value':25,'unavailable_reason':None,'unit':{'canonical':'USD','original':'usd'},'duration_semantics':'DISCRETE_AND_YTD','provenance':{'raw_sha256':'a'*64}}
    normalized={'contract':'ATLAS_G6_QUARTERLY_STATEMENT_NORMALIZATION_V1','ticker':'ABC','normalized_sha256':'q'*64,'ratings_changed':False,'publications_changed':False}
    period={'fiscal_year':2026,'fiscal_quarter':1,'fiscal_period_start':'2026-01-01','fiscal_period_end':'2026-03-31','filed_date':'2026-05-01','accepted_date':'2026-05-01','accession':'q1','restatement_candidates':1,'facts':[fact],'discrete_flow_facts':[{'concept':'Revenue','status':'AVAILABLE','value':25}]}
    series={'contract':'ATLAS_G6_QUARTERLY_FINANCIAL_SERIES_V1','ticker':'ABC','sha256':'s'*64,'periods':[period]}
    return normalized,series

def test_combined_projection_is_read_only_source_bound_and_never_zero_fills():
    annual=annual_fixture();q,s=quarterly_fixture();projection=project_customer_statement_history(annual,q,s)
    assert projection['ticker']=='ABC' and projection['read_only'] is True and projection['provider_calls']==0
    assert projection['annual']['retained_period_count']==6 and projection['quarterly']['retained_period_count']==1
    assert projection['quarterly']['statements']['INCOME_STATEMENT'][0]['cells'][0]['value']==25
    assert projection['rating_authority']==projection['publication_authority']=='UNCHANGED'

def test_research_accepts_only_exact_ticker_read_only_projection_without_changing_authority():
    annual=annual_fixture();annual['ticker']='NVDA';q,s=quarterly_fixture();q['ticker']=s['ticker']='NVDA'
    projection=project_customer_statement_history(annual,q,s);source=report();source['certified_statement_history']=projection;before=copy.deepcopy(source['certified_customer_evaluation'])
    page=build_customer_research_v2(source);assert page['statement_history']['contract']=='ATLAS_CUSTOMER_STATEMENT_HISTORY_PROJECTION_V1'
    assert source['certified_customer_evaluation']==before
    bad=copy.deepcopy(source);bad['certified_statement_history']['ticker']='MSFT'
    assert build_customer_research_v2(bad)['statement_history']=={'status':'UNAVAILABLE','reason':'STATEMENT_HISTORY_AUTHORITY_MISMATCH'}
