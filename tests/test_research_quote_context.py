"""Synthetic quote bytes only: no provider, live transport or promotion."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.operations_gateway import CAPTURE_TIME_CONTRACT, RESEARCH_ENDPOINTS, GatewayApproval, canonical_bytes, verify_scope
from services.research_context_ingestion import CAPABILITIES
from services.research_market_read_model import load_research_market_context
from services.research_quote_context import QUOTE_CAPTURE_SCHEMA, build_quote_review_from_capture, project_quote_context
from services.research_refresh_execution import compile_execution_plan
from services.research_refresh_readiness import plan_research_refresh

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SOURCE = 'a' * 40
BUNDLE = 'GENERATED_QUOTE_REVIEW_NOT_CERTIFIED'


def fixture(*, age=20):
    plan = compile_execution_plan(plan_research_refresh(['NVDA'], {}, {
        'status': 'APPROVED', 'contract_id': CONTRACT_ID, 'capabilities': ['live_quote'],
    }, source_sha=SOURCE, now=NOW, capabilities=['live_quote']), as_of=NOW.date())
    body = json.dumps(dict(c=100, o=99, h=101, l=98, pc=97,
                           t=int((NOW-timedelta(seconds=age)).timestamp()))).encode()
    request = plan['requests'][0]
    metadata = dict(ordinal=1, ticker='NVDA', endpoint='/quote', parameters={'symbol':'NVDA'},
        request_sha256=request['request_sha256'], status='PASS', status_code=200, attempt_count=1,
        retry_count=0, raw_complete=True, raw_capture='COMPLETE', raw_bytes=len(body),
        raw_sha256=hashlib.sha256(body).hexdigest(), capture_time_contract=CAPTURE_TIME_CONTRACT,
        capture_time_status='BOUND', attempt_started_at=(NOW-timedelta(seconds=1)).isoformat(),
        response_completed_at=NOW.isoformat())
    summary = dict(contract=QUOTE_CAPTURE_SCHEMA, source_sha=SOURCE,
        scope_sha256=plan['scope_sha256'], package_sha256=plan['package_sha256'], status='PASS',
        failure_code=None, automatic_redirects=False, retry_count=0, provider_calls=1,
        max_provider_calls=1, attempted_transport_calls=1, responses_received=1,
        capture_time_contract=CAPTURE_TIME_CONTRACT, capture_time_status='BOUND',
        capture_started_at=metadata['attempt_started_at'], capture_completed_at=metadata['response_completed_at'],
        telemetry=[deepcopy(metadata)])
    return plan, body, metadata, summary


def review(values=None, **kwargs):
    plan, body, metadata, summary = fixture() if values is None else values
    return build_quote_review_from_capture(body, plan=plan, expected_source_sha=SOURCE,
        expected_package_sha256=plan['package_sha256'], ticker='NVDA', metadata=metadata,
        run_summary=summary, bundle_id=BUNDLE, captured_at=NOW, checked_at=NOW,
        raw_evidence_id='GENERATED:quote:1', **kwargs)


def admit(tmp_path, wrapper, *, expected_source=SOURCE, expected_bundle=BUNDLE, now=NOW):
    root = tmp_path/'primary'; root.mkdir(exist_ok=True)
    (root/'NVDA.json').write_text(json.dumps(wrapper['bundle']))
    return load_research_market_context('NVDA', root, now=now,
        expected_source_sha=expected_source, expected_bundle_id=expected_bundle)


def test_compiled_quote_to_pinned_read_model_to_customer_context_without_clients(tmp_path, monkeypatch):
    import socket
    from services.finnhub_shadow_provider import FinnhubShadowAdapter
    monkeypatch.setattr(socket.socket, 'connect', lambda *a,**k:pytest.fail('network attempted'))
    monkeypatch.setattr(FinnhubShadowAdapter, '__init__', lambda *a,**k:pytest.fail('client constructed'))
    original = fixture(); before = deepcopy(original)
    wrapper = review(original)
    assert original == before
    assert wrapper['status'] == 'OWNER_REVIEW_ONLY_NOT_PUBLISHED'
    assert wrapper['provider_calls'] == wrapper['publication_writes'] == wrapper['report_card_writes'] == 0
    assert wrapper['live_transport'] == 'NOT_REGISTERED'
    loaded = admit(tmp_path, wrapper)
    projected = project_quote_context(loaded['live_quote'], ticker='NVDA', checked_at=NOW)
    assert projected['status'] == 'AVAILABLE' and projected['price'] == 100
    assert projected['as_of'] == (NOW-timedelta(seconds=20)).isoformat()
    assert projected['market_coverage'] == 'PARTIAL_REALTIME'
    assert projected['classification'] == 'CONTEXTUAL_NON_SCORING'
    assert projected['currency'] is None  # /quote does not state a currency.
    assert projected['identity_binding'] == 'REQUEST_BOUND_PROVIDER_RESPONSE_HAS_NO_REQUIRED_TICKER'
    assert projected['evidence_id'] == 'GENERATED:quote:1'


def test_review_wrapper_cannot_be_served_directly_or_without_external_pins(tmp_path):
    wrapper = review()
    root = tmp_path/'raw-wrapper'; root.mkdir()
    (root/'NVDA.json').write_text(json.dumps(wrapper))
    assert load_research_market_context('NVDA', root, now=NOW) == {}
    assert admit(tmp_path, wrapper, expected_source=None) == {}
    assert admit(tmp_path, wrapper, expected_bundle=None) == {}
    assert admit(tmp_path, wrapper, expected_source='b'*40) == {}
    assert admit(tmp_path, wrapper, expected_bundle='different') == {}


def test_fresh_capture_cannot_refresh_old_provider_time(tmp_path):
    wrapper = review(fixture(age=86400))
    loaded = admit(tmp_path, wrapper)
    assert loaded['live_quote']['cache_status'] == 'STALE_RETAINED'
    view = project_quote_context(loaded['live_quote'], ticker='NVDA', checked_at=NOW)
    assert view['status'] == 'DATED' and view['source_age_seconds'] == 86400
    assert view['captured_at'] == NOW.isoformat()
    assert view['as_of'] == (NOW-timedelta(days=1)).isoformat()
    recent = admit(tmp_path, review())
    assert project_quote_context(recent['live_quote'], ticker='NVDA', checked_at=NOW+timedelta(seconds=61))['status'] == 'DATED'


@pytest.mark.parametrize('mutation', [
    lambda p,m,s:m.update(ticker='MSFT'), lambda p,m,s:m.update(endpoint='/quote/us'),
    lambda p,m,s:m.update(parameters={'symbol':'MSFT'}), lambda p,m,s:m.update(request_sha256='b'*64),
    lambda p,m,s:m.update(raw_sha256='0'*64), lambda p,m,s:m.update(raw_complete=False),
    lambda p,m,s:m.update(status_code=302), lambda p,m,s:m.update(ordinal=True),
    lambda p,m,s:s.update(source_sha='b'*40), lambda p,m,s:s.update(scope_sha256='b'*64),
    lambda p,m,s:s.update(package_sha256='b'*64), lambda p,m,s:s.update(provider_calls=True),
    lambda p,m,s:s.update(automatic_redirects=True), lambda p,m,s:s.update(retry_count=1),
    lambda p,m,s:m.update(response_completed_at=(NOW+timedelta(seconds=1)).isoformat()),
])
def test_request_capture_scope_and_clock_mutations_fail_closed(mutation):
    plan,body,meta,summary = fixture(); mutation(plan,meta,summary)
    summary['telemetry'] = [deepcopy(meta)]
    with pytest.raises(ValueError): review((plan,body,meta,summary))


@pytest.mark.parametrize('change', [
    {'c':True}, {'c':'100'}, {'c':None}, {'c':0}, {'c':float('inf')}, {'c':float('nan')},
    {'h':90}, {'l':102}, {'pc':-1}, {'t':True}, {'t':0},
    {'t':int((NOW+timedelta(seconds=1)).timestamp())}, {'symbol':'MSFT'}, {'ticker':'MSFT'}, {'error':'denied'},
])
def test_malformed_partial_or_future_quote_is_not_normalized_to_authority(change):
    plan,body,meta,summary = fixture()
    raw = json.loads(body); raw.update(change); body = json.dumps(raw).encode()
    meta.update(raw_bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest())
    summary['telemetry'] = [deepcopy(meta)]
    with pytest.raises(ValueError):review((plan,body,meta,summary))


def test_generic_gateway_converter_and_live_execution_remain_closed(tmp_path, monkeypatch):
    from services.research_refresh_execution import execute_live
    assert '/quote' not in RESEARCH_ENDPOINTS and 'live_quote' not in CAPABILITIES
    scope={'source_sha':SOURCE,'requests':[{'ordinal':1,'method':'GET','endpoint':'/quote','parameters':{'symbol':'NVDA'}}]}
    digest=hashlib.sha256(canonical_bytes(scope)).hexdigest()
    path=tmp_path/'scope.json';path.write_text(json.dumps(scope))
    approval=GatewayApproval.parse(dict(operation='plan',source_sha=SOURCE,scope_sha256=digest,
        max_provider_calls=1,authorization_token='ATLAS_PLAN:'+digest))
    with pytest.raises(PermissionError,match='ENDPOINT_NOT_ALLOWED'):verify_scope(path,approval)
    monkeypatch.setenv('ATLAS_RESEARCH_REFRESH_LIVE_ENABLED','true')
    with pytest.raises(PermissionError,match='WORKFLOW_NOT_REGISTERED'):execute_live()


def test_quote_cannot_replace_certified_customer_authority(tmp_path, monkeypatch):
    import services.customer_research_v2 as customer
    from tests.test_customer_research_v2 import report
    source = report(); before=deepcopy(source)
    monkeypatch.setattr(customer, '_qa_enrichment', lambda _: {})
    monkeypatch.setattr(customer, 'load_research_market_context', lambda *a,**k:{})
    baseline=customer.build_customer_research_v2(source)
    enrichment=admit(tmp_path,review())
    monkeypatch.setattr(customer, 'load_research_market_context', lambda *a,**k:enrichment)
    actual=customer.build_customer_research_v2(source)
    assert actual['quote_context']['price'] == 100
    for field in ('header','authority','signal','six_pillars'):
        assert actual[field] == baseline[field]
    assert source == before


def test_actual_ui_keeps_quote_separate_and_missing_currency_explicit(tmp_path):
    from streamlit.testing.v1 import AppTest
    view=project_quote_context(admit(tmp_path,review())['live_quote'],ticker='NVDA',checked_at=NOW)
    code='''
from ui.customer_research_v2 import _render_provider_quote_context
_render_provider_quote_context(PAGE)
'''.replace('PAGE',repr(dict(ticker='NVDA',quote_context=view)))
    app=AppTest.from_string(code).run()
    assert not app.exception
    rendered=' '.join(str(v.value) for v in app.markdown)+ ' '.join(str(v.value) for v in app.caption)
    assert '100.00' in rendered and 'currency not supplied' in rendered
    assert 'Partial market coverage' in rendered and 'Non-scoring context' in rendered
    assert 'not a certified close' in rendered and '$100' not in rendered


def test_currency_requires_separate_same_ticker_profile_lineage(tmp_path):
    quote = admit(tmp_path, review())['live_quote']
    own = dict(ticker='NVDA', raw_evidence_id='GENERATED:profile:1', contract_id=CONTRACT_ID,
               contracted_endpoint='/stock/profile2', commercial_display_allowed=True,
               raw_machine_readable_redistribution_allowed=False)
    profile = dict(payload=dict(currency='USD'), provenance=own)
    view = project_quote_context(quote, ticker='NVDA', checked_at=NOW, profile=profile)
    assert view['currency'] == 'USD' and view['currency_evidence_id'] == 'GENERATED:profile:1'
    for field, value in [('ticker','MSFT'), ('contract_id','unlicensed'),
                         ('contracted_endpoint','/quote'), ('commercial_display_allowed',False),
                         ('raw_machine_readable_redistribution_allowed',True),
                         ('raw_evidence_id',True), ('raw_evidence_id',42),
                         ('raw_evidence_id','   ')]:
        bad = deepcopy(profile); bad['provenance'][field] = value
        assert project_quote_context(quote, ticker='NVDA', checked_at=NOW, profile=bad)['currency'] is None


@pytest.mark.parametrize('missing', ['o', 'h', 'l', 'pc', 't'])
def test_missing_quote_fields_are_not_filled_from_other_authorities(missing):
    plan, body, meta, summary = fixture()
    raw = json.loads(body); raw.pop(missing); body = json.dumps(raw).encode()
    meta.update(raw_bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest())
    summary['telemetry'] = [deepcopy(meta)]
    with pytest.raises(ValueError): review((plan,body,meta,summary))


def test_retained_profile_producer_admission_quote_and_ui_currency_lineage(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from services.research_context_ingestion import build_context_review_from_gateway_capture
    from services.research_market_read_model import seal_research_market_bundle
    from tests.test_research_context_ingestion import capture, NOW as PROFILE_NOW
    from services.finnhub_shadow_provider import FinnhubShadowAdapter
    monkeypatch.setattr(FinnhubShadowAdapter, '__init__', lambda *a,**k:pytest.fail('client constructed'))
    raw, metadata, summary = capture('company_profile')
    evidence = 'GENERATED:profile:<img src=x onerror=alert(1)>'
    profile = build_context_review_from_gateway_capture(raw, metadata=metadata,
        run_summary=summary, capability='company_profile', ticker='NVDA', source_sha=SOURCE,
        scope_sha256='b'*64, bundle_id=BUNDLE, captured_at=PROFILE_NOW, checked_at=NOW,
        raw_evidence_id=evidence)
    quote = review()
    combined = deepcopy(quote['bundle'])
    combined['families']['company_profile'] = profile['bundle']['families']['company_profile']
    combined = seal_research_market_bundle(combined)
    loaded = admit(tmp_path, dict(bundle=combined))
    assert loaded['company_profile']['payload']['currency'] == 'USD'
    assert loaded['company_profile']['provenance']['raw_response_sha256'] == hashlib.sha256(raw).hexdigest()
    view = project_quote_context(loaded['live_quote'], ticker='NVDA', checked_at=NOW,
                                 profile=loaded['company_profile'])
    assert view['currency'] == 'USD' and view['currency_evidence_id'] == evidence
    code = ('from ui.customer_research_v2 import _render_provider_quote_context\n'
            '_render_provider_quote_context(' + repr(dict(ticker='NVDA',quote_context=view)) + ')')
    app = AppTest.from_string(code).run()
    assert not app.exception
    rendered = ' '.join(str(value.value) for value in app.markdown)
    assert '100.00 USD' in rendered and 'Currency profile evidence:' in rendered
    assert '&lt;img src=x onerror=alert(1)&gt;' in rendered
    assert '<img src=x' not in rendered
