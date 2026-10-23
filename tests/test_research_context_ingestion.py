"""Synthetic source bytes only; no acquisition, entitlement or certification."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from unittest.mock import Mock

import pytest

from services.operations_gateway import CAPTURE_TIME_CONTRACT
from services.research_context_ingestion import CAPABILITIES, build_context_review_from_gateway_capture
from services.finnhub_enterprise_display_contract import display_authority
from services.research_market_read_model import load_research_market_context

NOW = datetime(2026, 10, 23, 0, tzinfo=timezone.utc)
BASE = dict(ticker='NVDA', source_sha='a'*40, scope_sha256='b'*64,
    bundle_id='GENERATED_REVIEW_NOT_CERTIFIED', captured_at=NOW, checked_at=NOW,
    raw_evidence_id='GENERATED:CONTEXT')


def response(capability):
    return {
        'company_profile': {'ticker':'NVDA','name':'Generated company','currency':'USD',
            'marketCapitalization':1000,'shareOutstanding':10},
        'recommendations': [{'symbol':'NVDA','period':'2026-10-01','strongBuy':2,
            'buy':3,'hold':1,'sell':0,'strongSell':0}],
        'price_targets': {'symbol':'NVDA','targetMean':110,'targetMedian':105,
            'targetLow':90,'targetHigh':130,'lastUpdated':'2026-10-22'},
        'earnings_calendar': {'earningsCalendar':[{'symbol':'NVDA','date':'2026-11-20',
            'epsEstimate':1.2,'revenueEstimate':100}]},
        'company_news': [{'related':'NVDA','headline':'NVDA generated update',
            'summary':'Synthetic summary','source':'Generated publisher','url':'https://example.invalid/news',
            'datetime':int((NOW-timedelta(hours=1)).timestamp()),'id':1}],
        'stock_earnings': [{'symbol':'NVDA','period':'2026-07-31','actual':1.2,'estimate':1}],
        'financial_statements': {'symbol':'NVDA','data':[{'endDate':'2025-12-31','filedDate':'2026-02-01',
            'year':2025,'quarter':0,'form':'10-K','report':{
                'ic':[{'concept':'us-gaap_Revenues','label':'Revenue','unit':'usd','value':100}]
            }}]},
    }[capability]


def capture(capability='recommendations', value=None):
    body=json.dumps(response(capability) if value is None else value,indent=2).encode()+b'\n'
    meta=dict(ordinal=1,ticker='NVDA',endpoint=display_authority(capability).endpoint,
        parameters={'symbol':'NVDA'},status='PASS',status_code=200,attempt_count=1,retry_count=0,
        raw_complete=True,raw_capture='COMPLETE',raw_bytes=len(body),raw_sha256=hashlib.sha256(body).hexdigest(),
        capture_time_contract=CAPTURE_TIME_CONTRACT,capture_time_status='BOUND',
        attempt_started_at=(NOW-timedelta(seconds=1)).isoformat(),response_completed_at=NOW.isoformat())
    summary=dict(contract='ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1',source_sha='a'*40,scope_sha256='b'*64,
        status='PASS',failure_code=None,automatic_redirects=False,retry_count=0,provider_calls=1,
        max_provider_calls=1,attempted_transport_calls=1,responses_received=1,
        capture_time_contract=CAPTURE_TIME_CONTRACT,capture_time_status='BOUND',
        capture_started_at=meta['attempt_started_at'],capture_completed_at=meta['response_completed_at'],
        telemetry=[deepcopy(meta)])
    return body,meta,summary


def review(capability='recommendations', value=None, *, raw=None, meta=None, summary=None, **kwargs):
    body,m,s=capture(capability,value)
    return build_context_review_from_gateway_capture(body if raw is None else raw,
        metadata=m if meta is None else meta,run_summary=s if summary is None else summary,
        capability=capability,**(BASE|kwargs))


@pytest.mark.parametrize('capability',sorted(CAPABILITIES))
def test_all_existing_supported_families_convert_exact_bytes_without_client_or_mutation(capability,monkeypatch):
    from services.finnhub_shadow_provider import FinnhubShadowAdapter
    monkeypatch.setattr(FinnhubShadowAdapter,'__init__',lambda *a,**k:pytest.fail('client constructed'))
    monkeypatch.setattr(FinnhubShadowAdapter,'fetch',lambda *a,**k:pytest.fail('provider invoked'))
    raw,meta,summary=capture(capability); before=deepcopy((meta,summary))
    result=review(capability,raw=raw,meta=meta,summary=summary)
    family=result['bundle']['families'][capability]
    assert family['provenance']['raw_response_sha256']==hashlib.sha256(raw).hexdigest()
    assert family['provenance']['raw_response_sha256'] != family['provenance']['normalized_response_sha256']
    assert family['provenance']['capture_timestamp']==NOW.isoformat()
    assert result['status']=='OWNER_REVIEW_ONLY_NOT_PUBLISHED'
    assert result['provider_calls']==result['publication_writes']==result['report_card_writes']==0
    assert (meta,summary)==before


@pytest.mark.parametrize('capability',sorted(CAPABILITIES))
def test_cross_ticker_response_is_not_silently_normalized(capability):
    value=response(capability)
    if capability=='company_news':value[0]['related']='MSFT'
    elif isinstance(value,list):value[0]['symbol']='MSFT'
    elif capability=='earnings_calendar':value['earningsCalendar'][0]['symbol']='MSFT'
    else:value['ticker' if capability=='company_profile' else 'symbol']='MSFT'
    with pytest.raises(ValueError,match='TICKER_MISMATCH'):review(capability,value)


@pytest.mark.parametrize('capability,value',[
    ('recommendations',[{'symbol':'NVDA','period':'2026-10-01','strongBuy':2,'buy':'bad','hold':1,'sell':0,'strongSell':0}]),
    ('recommendations',[{'symbol':'NVDA','period':'2026-10-01','strongBuy':True,'buy':1,'hold':1,'sell':0,'strongSell':0}]),
    ('price_targets',{'symbol':'NVDA','targetMean':200,'targetLow':90,'targetHigh':130,'lastUpdated':'2026-10-22'}),
    ('company_profile',{'ticker':'NVDA','name':''}),
    ('stock_earnings',[{'symbol':'NVDA','period':'2026-10-24','actual':1}]),
    ('earnings_calendar',{'earningsCalendar':[{'symbol':'NVDA','date':'bad'}]}),
    ('company_news',[{'related':'NVDA','headline':'NVDA','source':'Publisher','url':'javascript:bad','datetime':1}]),
    ('financial_statements',{'symbol':'NVDA','data':[{'endDate':'2025-12-31','report':{'ic':[{'label':'Revenue','value':True}]}}]}),
])
def test_malformed_semantics_do_not_produce_review_bundle(capability,value):
    with pytest.raises(ValueError):review(capability,value)


@pytest.mark.parametrize('raw',[b'{"ticker":"NVDA","ticker":"NVDA"}',b'{"value":NaN}',b'{"value":1e999}',b'null',b'\xff',b'{"value":'+str(10**400).encode()+b'}'])
def test_invalid_or_nonfinite_raw_json_is_rejected_even_if_hash_matches(raw):
    _,meta,summary=capture('company_profile')
    meta.update(raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest());summary['telemetry']=[deepcopy(meta)]
    with pytest.raises(ValueError,match='RAW_JSON_INVALID'):
        review('company_profile',raw=raw,meta=meta,summary=summary)


@pytest.mark.parametrize('mutation',[
    lambda m,s:m.update(raw_sha256='c'*64),
    lambda m,s:m.update(ordinal=True),
    lambda m,s:m.update(ticker='MSFT'),
    lambda m,s:m.update(endpoint='/quote'),
    lambda m,s:s.update(scope_sha256='c'*64),
    lambda m,s:s.update(provider_calls=2),
    lambda m,s:s.update(source_sha='c'*40),
    lambda m,s:s.update(automatic_redirects=True),
    lambda m,s:s.update(capture_time_status='UNATTESTED'),
])
def test_receipt_identity_scope_ordinal_budget_raw_and_time_guards(mutation):
    raw,meta,summary=capture();mutation(meta,summary)
    # Metadata equality remains bound for adversarial internally consistent receipts.
    if meta!=summary['telemetry'][0]:summary['telemetry']=[deepcopy(meta)]
    with pytest.raises(ValueError):review(raw=raw,meta=meta,summary=summary)


def test_legacy_and_caller_substituted_capture_time_are_rejected():
    raw,meta,summary=capture()
    with pytest.raises(ValueError,match='CAPTURE_TIME_BINDING'):
        review(raw=raw,meta=meta,summary=summary,captured_at=NOW+timedelta(minutes=1),checked_at=NOW+timedelta(minutes=1))
    summary.pop('capture_time_contract')
    with pytest.raises(ValueError,match='CAPTURE_TIME_UNATTESTED'):review(raw=raw,meta=meta,summary=summary)


@pytest.mark.parametrize('capability',['live_quote','basic_financials','eps_estimates','revenue_estimates','historical_ohlcv','unknown'])
def test_converter_does_not_expand_gateway_or_history_scope(capability):
    raw,meta,summary=capture()
    with pytest.raises(ValueError,match='CAPABILITY_UNSUPPORTED'):
        build_context_review_from_gateway_capture(raw,metadata=meta,run_summary=summary,capability=capability,**BASE)


def test_wrapper_not_directly_admissible_and_normalized_news_can_reach_customer_projection(tmp_path,monkeypatch):
    from services.customer_research_v2 import build_customer_research_v2
    from tests.test_customer_research_v2 import report
    result=review('company_news');path=tmp_path/'NVDA.json';path.write_text(json.dumps(result))
    assert load_research_market_context('NVDA',tmp_path,now=NOW)=={}
    # Explicit test-only promotion of generated evidence, never production code.
    path.write_text(json.dumps(result['bundle']))
    context=load_research_market_context('NVDA',tmp_path,now=NOW,expected_source_sha='a'*40,
        expected_bundle_id=BASE['bundle_id'])
    assert context['company_news']['payload']['articles'][0]['article_timestamp'].startswith('2026-10-22T23:')
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT',str(tmp_path))
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_EXPECTED_SOURCE_SHA','a'*40)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_EXPECTED_BUNDLE_ID',BASE['bundle_id'])
    monkeypatch.setenv('ATLAS_QA_MODE','0')
    projected=build_customer_research_v2(report())
    assert projected['status']=='AVAILABLE'
    assert projected['recent_changes']['items'][0]['headline']=='NVDA generated update'


def test_mock_streamed_gateway_receipt_to_review_to_read_model_preserves_rating_authority(tmp_path,monkeypatch):
    from scripts.run_licensed_research_gateway import run
    from tests.test_licensed_research_gateway import package, StreamResponse
    from services.customer_research_v2 import build_customer_research_v2
    from tests.test_customer_research_v2 import report
    raw=json.dumps(response('recommendations'),indent=2).encode()
    session=Mock();session.get.return_value=StreamResponse(chunks=(raw[:20],raw[20:]))
    monkeypatch.setattr('scripts.run_licensed_research_gateway.requests.Session',lambda:session)
    monkeypatch.setenv('FINNHUB_API_KEY','GENERATED_ONLY_NEVER_A_REAL_CREDENTIAL')
    ap,sp=package(tmp_path,requests_rows=[{'ordinal':1,'method':'GET',
        'endpoint':'/stock/recommendation','ticker':'NVDA','parameters':{'symbol':'NVDA'}}])
    clock=iter((NOW-timedelta(seconds=1),NOW))
    summary=run(approval_path=ap,scope_path=sp,output=tmp_path/'raw_capture',
        run_id='GENERATED_ONLY',clock=lambda:next(clock))
    meta=json.loads((tmp_path/'raw_capture/raw/00001.metadata.json').read_text())
    recorded=(tmp_path/'raw_capture/raw/00001.json').read_bytes()
    before={p:p.read_bytes() for p in (tmp_path/'raw_capture').rglob('*') if p.is_file()}
    result=review(raw=recorded,meta=meta,summary=summary,scope_sha256=summary['scope_sha256'])
    assert summary['provider_calls']==1 and session.get.call_count==1  # Simulated transport only.
    assert result['provider_calls']==result['publication_writes']==result['report_card_writes']==0
    assert all(p.read_bytes()==b for p,b in before.items())
    review_root=tmp_path/'synthetic_review';review_root.mkdir()
    (review_root/'NVDA.json').write_text(json.dumps(result['bundle']))
    admitted=load_research_market_context('NVDA',review_root,now=NOW,expected_source_sha='a'*40,
        expected_bundle_id=BASE['bundle_id'])
    assert admitted['recommendations']['payload']['periods'][0]['buy']==3
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT',str(review_root))
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_EXPECTED_SOURCE_SHA','a'*40)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_EXPECTED_BUNDLE_ID',BASE['bundle_id'])
    monkeypatch.setenv('ATLAS_QA_MODE','0')
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED','true')
    original=report();before_report=deepcopy(original)
    projected=build_customer_research_v2(original)
    assert projected['header']['price']==186.09
    assert projected['header']['fair_value']==346.05
    assert original==before_report


def test_own_response_clock_not_later_run_completion_controls_freshness():
    raw,meta,summary=capture('company_profile')
    first_end=NOW-timedelta(hours=6)
    meta.update(attempt_started_at=(first_end-timedelta(seconds=1)).isoformat(),
                response_completed_at=first_end.isoformat())
    second=deepcopy(meta);second.update(ordinal=2,attempt_started_at=(NOW-timedelta(seconds=1)).isoformat(),
        response_completed_at=NOW.isoformat(),endpoint='/stock/earnings')
    summary.update(provider_calls=2,max_provider_calls=2,attempted_transport_calls=2,responses_received=2,
        capture_started_at=meta['attempt_started_at'],telemetry=[deepcopy(meta),second])
    result=review('company_profile',raw=raw,meta=meta,summary=summary)
    provenance=result['bundle']['families']['company_profile']['provenance']
    assert provenance['capture_timestamp']==first_end.isoformat()
    assert provenance['gateway_run_capture_completed_at']==NOW.isoformat()


def test_normalizer_created_nonfinite_value_is_rejected(monkeypatch):
    from services.finnhub_shadow_provider import FinnhubShadowAdapter
    monkeypatch.setattr(FinnhubShadowAdapter,'_normalize',lambda *a,**k:{'name':'Generated','value':float('inf')})
    with pytest.raises(ValueError,match='CONTEXT_RESPONSE_NORMALIZATION_INVALID'):review('company_profile')


def test_documented_financial_native_datetime_dates_retain_timezone_ambiguity():
    value=response('financial_statements')
    value['data'][0].update(endDate='2025-12-31 00:00:00',filedDate='2026-02-01 12:30:59')
    result=review('financial_statements',value)
    family=result['bundle']['families']['financial_statements']
    normalized=family['payload']['reports'][0]
    assert normalized['fiscal_date']=='2025-12-31 00:00:00'
    assert normalized['filed_date']=='2026-02-01 12:30:59'
    assert family['provenance']['source_date_semantics']=='PROVIDER_CALENDAR_DATES_TIMEZONE_UNATTESTED'
    assert family['provenance']['capture_timestamp']==NOW.isoformat()


@pytest.mark.parametrize('field,value',[
    ('endDate','2025-12-31 25:00:00'),('filedDate','2026-02-30 00:00:00'),
    ('endDate','2025-12-31 00:00:00Z'),('filedDate','2026-10-24 00:00:00'),
    ('endDate','2026-10-24'),('filedDate','2026-02-01 00:61:00'),
])
def test_financial_native_dates_reject_invalid_clock_calendar_and_future_day(field,value):
    source=response('financial_statements');source['data'][0][field]=value
    with pytest.raises(ValueError,match='CONTEXT_RESPONSE_SCHEMA_INVALID'):review('financial_statements',source)


@pytest.mark.parametrize('updated', ['2023-04-06 00:00:00','2026-10-23 23:59:59'])
def test_documented_native_target_update_retained_without_invented_timezone(updated):
    value=response('price_targets');value['lastUpdated']=updated
    result=review('price_targets',value)
    family=result['bundle']['families']['price_targets']
    assert family['payload']['last_updated']==updated
    assert family['provenance']['source_update_value']==updated
    assert family['provenance']['source_date_semantics']=='PROVIDER_CALENDAR_DATE_TIMEZONE_UNATTESTED'
    # The verified UTC clock is the capture, not a manufactured provider update.
    assert family['provenance']['capture_timestamp']==NOW.isoformat()
    assert 'source_timestamp' not in family['provenance']
    assert value['lastUpdated']==updated


@pytest.mark.parametrize('updated', ['2026-10-24 00:00:00','2026-02-30 00:00:00',
    '2026-10-22 24:00:00','2026-10-22 00:60:00','2026-10-22T23:00:00',
    '2026-10-23T00:00:01+00:00'])
def test_invalid_native_or_future_explicit_target_update_cannot_enter_review(updated):
    value=response('price_targets');value['lastUpdated']=updated
    with pytest.raises(ValueError,match='CONTEXT_ANALYST_PAYLOAD_INVALID'):review('price_targets',value)


def test_aware_target_update_keeps_instant_semantics_and_native_clock_preserves_day_only():
    value=response('price_targets');value['lastUpdated']='2026-10-22T20:00:00-04:00'
    family=review('price_targets',value)['bundle']['families']['price_targets']
    assert family['payload']['last_updated']=='2026-10-22T20:00:00-04:00'
    assert family['provenance']['source_date_semantics']=='PROVIDER_TIMESTAMP_EXPLICIT_TIMEZONE'
    assert family['provenance']['capture_timestamp']==NOW.isoformat()


def test_later_run_completion_cannot_launder_next_day_native_target_update():
    value=response('price_targets');value['lastUpdated']='2026-10-23 00:00:00'
    raw,meta,summary=capture('price_targets',value)
    response_end=NOW-timedelta(minutes=1)
    meta.update(attempt_started_at=(response_end-timedelta(seconds=1)).isoformat(),
        response_completed_at=response_end.isoformat())
    later=deepcopy(meta);later.update(ordinal=2,endpoint='/stock/earnings',
        attempt_started_at=(NOW-timedelta(seconds=1)).isoformat(),response_completed_at=NOW.isoformat())
    summary.update(provider_calls=2,max_provider_calls=2,attempted_transport_calls=2,responses_received=2,
        capture_started_at=meta['attempt_started_at'],telemetry=[deepcopy(meta),later])
    with pytest.raises(ValueError,match='CONTEXT_ANALYST_PAYLOAD_INVALID'):
        review('price_targets',raw=raw,meta=meta,summary=summary)
