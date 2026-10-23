"""Generated retained bytes only: no acquisitions or production evidence."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest

from services.retained_earnings_context import build_retained_earnings_context
from services.research_market_read_model import seal_research_market_bundle, load_research_market_context
from tests.test_research_context_ingestion import review, NOW, BASE


@pytest.fixture
def admitted(tmp_path):
    generated = review('stock_earnings')
    bundle = seal_research_market_bundle(generated['bundle'])
    (tmp_path / 'NVDA.json').write_text(json.dumps(bundle))
    return load_research_market_context('NVDA', tmp_path, now=NOW,
        expected_source_sha=BASE['source_sha'], expected_bundle_id=BASE['bundle_id'])


def project(context, **kwargs):
    return build_retained_earnings_context(context, ticker='NVDA', now=NOW, **kwargs)


@pytest.mark.parametrize('capture', ['0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00'])
def test_capture_utc_conversion_overflow_is_withheld(admitted, capture):
    admitted['stock_earnings']['provenance']['capture_timestamp'] = capture
    result = project(admitted)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'RETAINED_EARNINGS_CAPTURE_INVALID'
    assert result['records'] == []


@pytest.mark.parametrize('capture', ['0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00'])
def test_malformed_capture_is_withheld_by_actual_reader_and_customer_projection(tmp_path, monkeypatch, capture):
    from services.customer_research_v2 import build_customer_research_v2, _instant
    from tests.test_customer_research_v2 import report

    candidate = review('stock_earnings')['bundle']
    candidate['families']['stock_earnings']['provenance']['capture_timestamp'] = capture
    path = tmp_path / 'NVDA.json'
    path.write_text(json.dumps(seal_research_market_bundle(candidate)))
    before = path.read_bytes()
    assert load_research_market_context('NVDA', tmp_path, now=NOW) == {}
    assert _instant(capture) is None
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_QA_MODE', '0')
    monkeypatch.delenv('ATLAS_RESEARCH_V2_QA_ENRICHMENT', raising=False)
    source = report(); original = deepcopy(source)
    page = build_customer_research_v2(source)
    assert page['retained_reported_earnings']['records'] == []
    assert page['header']['fair_value'] == 346.05
    assert source == original and path.read_bytes() == before


def test_converter_reader_context_retains_actual_values_and_lineage_without_mutation(admitted):
    before = deepcopy(admitted)
    page = project(admitted)
    assert page['status'] == 'AVAILABLE'
    assert page['records'] == [dict(period_end='2026-07-31', eps_actual=1.2, eps_estimate=1,
        eps_currency=None, eps_basis='UNVERIFIED', periodicity='UNVERIFIED', comparison_allowed=False)]
    assert page['source']['raw_response_sha256'] == admitted['stock_earnings']['provenance']['raw_response_sha256']
    assert page['source']['record_sha256'] == admitted['__read_model__']['record_sha256']
    assert page['source']['captured_at'] == admitted['stock_earnings']['provenance']['capture_timestamp']
    assert page['provider_calls'] == 0 and page['rating_authority'] == page['publication_authority'] == 'UNCHANGED'
    assert admitted == before
    assert 'surprise' not in json.dumps(page).lower()
    assert 'Period end is not' in ' '.join(page['disclosures'])


@pytest.mark.parametrize('actual,estimate,status', [(0, -1, 'AVAILABLE'), (-3.25, 0, 'AVAILABLE'), (None, 0, 'PARTIAL'), (0,None,'PARTIAL')])
def test_zero_losses_and_missing_stay_distinct(admitted, actual, estimate, status):
    admitted['stock_earnings']['payload']['records'][0].update(actual=actual, estimate=estimate,
        year=2026, quarter=3, surprise=999, surprisePercent=999, currency='USD')
    page = project(admitted)
    assert page['status'] == status
    assert page['records'][0]['eps_actual'] == actual
    assert page['records'][0]['eps_estimate'] == estimate
    assert page['records'][0]['periodicity'] == 'UNVERIFIED'
    assert page['records'][0]['eps_currency'] is None
    assert page['comparison_allowed'] is False


@pytest.mark.parametrize('value', [True, False, '1.2', float('nan'), float('inf'), -float('inf'), pytest.param(10**10000, id='overflow-integer')])
def test_bad_numeric_withholds_entire_family(admitted, value):
    admitted['stock_earnings']['payload']['records'][0]['actual'] = value
    assert project(admitted)['records'] == []


@pytest.mark.parametrize('mutation', [
    lambda c: c.pop('__read_model__'),
    lambda c: c.update(__atlas_ticker__='MSFT'),
    lambda c: c['__read_model__'].update(record_sha256='wrong'),
    lambda c: c['__read_model__'].update(publication_authority='AUTHORIZED'),
    lambda c: c['stock_earnings']['provenance'].update(raw_capture_binding='UNVERIFIED'),
    lambda c: c['stock_earnings']['provenance'].update(raw_response_sha256='wrong'),
    lambda c: c['stock_earnings']['provenance'].update(contract_id='other'),
    lambda c: c['stock_earnings']['provenance'].update(raw_machine_readable_redistribution_allowed=True),
    lambda c: c['stock_earnings']['provenance'].update(capture_timestamp='2026-10-23'),
    lambda c: c['stock_earnings']['provenance'].update(capture_timestamp='2026-10-24T00:00:00Z'),
])
def test_no_unverified_lineage_or_future_capture(admitted, mutation):
    mutation(admitted)
    assert project(admitted)['status'] == 'UNAVAILABLE'
    assert project(admitted)['source'] is None


@pytest.mark.parametrize('row', [
    {'symbol':'MSFT','period':'2026-07-31','actual':1},
    {'symbol':'NVDA','period':'2026-07-31','actual':1}, # duplicate
    {'symbol':'NVDA','period':'2026-02-30','actual':1},
    {'symbol':'NVDA','period':'2026-10-24','actual':1},
    {'symbol':'NVDA','period':'2026-07-30','actual':None,'estimate':None},
    {'symbol':'NVDA','period':'2026-07-30','actual':True},
])
def test_invalid_later_row_does_not_get_silently_dropped(admitted, row):
    admitted['stock_earnings']['payload']['records'].append(row)
    assert project(admitted)['records'] == []


def test_later_serving_cannot_launder_future_period_vs_family_capture(admitted):
    admitted['stock_earnings']['payload']['records'][0]['period'] = '2026-10-24'
    page = build_retained_earnings_context(admitted, ticker='NVDA', now=NOW+timedelta(days=2))
    assert page['status'] == 'UNAVAILABLE'


def test_all_rows_validated_before_display_limit_and_sorted_without_fiscal_inference(admitted):
    rows = [dict(symbol='NVDA', period=f'2026-{month:02d}-01', actual=-month, estimate=None) for month in range(1,10)]
    admitted['stock_earnings']['payload']['records'] = rows
    page = project(admitted)
    assert len(page['records']) == 8 and page['latest_retained_period'] == '2026-09-01'
    rows.append(dict(symbol='MSFT', period='2026-01-02', actual=1))
    assert project(admitted)['records'] == []
