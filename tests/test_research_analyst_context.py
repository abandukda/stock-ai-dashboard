"""Generated financial context verifies meaning, not merely valid self hashes."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from services.research_analyst_context import COUNT_MAX_EXACT_INTEGER, analyst_context_rejection
from services.research_market_read_model import load_research_market_context, seal_research_market_bundle
from services.customer_research_v2 import build_customer_research_v2
from tests.test_customer_research_v2 import report
from tests.test_research_market_read_model import _document, _family

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
COUNTS = {"strong_buy": 10, "buy": 8, "hold": 3, "sell": 1, "strong_sell": 0}
RECOMMENDATIONS = {"periods": [{"period": "2026-10-01", **COUNTS}]}
TARGETS = {"target_low": 180, "target_mean": 240, "target_high": 300, "last_updated": "2026-10-08"}


@pytest.mark.parametrize('value', [True, False, -1, 1.5, 1.0, '10', 'unknown', None, float('nan'), float('inf'), {}, [],
                                 COUNT_MAX_EXACT_INTEGER + 1, 10**400])
def test_counts_reject_coercion_missing_and_non_integer_values(value):
    payload = deepcopy(RECOMMENDATIONS)
    payload['periods'][0]['strong_buy'] = value
    assert analyst_context_rejection('recommendations', payload, ticker='NVDA', now=NOW) == 'RECOMMENDATIONS_COUNTS_INVALID'


@pytest.mark.parametrize('mutation,reason', [
    (lambda p: p['periods'][0].pop('hold'), 'RECOMMENDATIONS_COUNTS_INVALID'),
    (lambda p: p['periods'][0].update(period='2026-10-18'), 'RECOMMENDATIONS_PERIOD_INVALID'),
    (lambda p: p['periods'][0].update(period='2026-99-01'), 'RECOMMENDATIONS_PERIOD_INVALID'),
    (lambda p: p['periods'][0].update(symbol='MSFT'), 'ANALYST_CONTEXT_IDENTITY_OR_SCHEMA_INVALID'),
    (lambda p: p.update(ticker='MSFT'), 'ANALYST_CONTEXT_IDENTITY_OR_SCHEMA_INVALID'),
    (lambda p: p['periods'].append(deepcopy(p['periods'][0])), 'RECOMMENDATIONS_PERIOD_INVALID'),
    (lambda p: p['periods'].append({**COUNTS, 'period':'2026-10-02'}), 'RECOMMENDATIONS_PERIOD_INVALID'),
])
def test_recommendation_identity_period_order_and_completeness(mutation, reason):
    payload = deepcopy(RECOMMENDATIONS); mutation(payload)
    assert analyst_context_rejection('recommendations', payload, ticker='NVDA', now=NOW) == reason


def test_valid_analyst_payload_is_unchanged_and_partial_targets_stay_partial():
    recommendations = {'periods': [RECOMMENDATIONS['periods'][0], {**COUNTS, 'period':'2026-09-01'}]}
    for capability, payload in [('recommendations', recommendations), ('price_targets', TARGETS),
                                ('price_targets', {'target_mean':240, 'last_updated':'2026-10-08T21:00:00Z'}),
                                ('recommendations', {'periods': []})]:
        before = deepcopy(payload)
        assert analyst_context_rejection(capability, payload, ticker='NVDA', now=NOW) is None
        assert payload == before
    assert 'target_median' not in TARGETS


@pytest.mark.parametrize('key,value,reason', [
    ('target_mean', True, 'PRICE_TARGET_VALUE_INVALID'),
    ('target_mean', '240', 'PRICE_TARGET_VALUE_INVALID'),
    ('target_mean', 0, 'PRICE_TARGET_VALUE_INVALID'),
    ('target_mean', -1, 'PRICE_TARGET_VALUE_INVALID'),
    ('target_mean', float('nan'), 'PRICE_TARGET_VALUE_INVALID'),
    ('target_mean', float('inf'), 'PRICE_TARGET_VALUE_INVALID'),
    ('target_mean', 10**400, 'PRICE_TARGET_VALUE_INVALID'),
    ('target_mean', 301, 'PRICE_TARGET_RANGE_INVALID'),
    ('target_median', 179, 'PRICE_TARGET_RANGE_INVALID'),
    ('target_low', 301, 'PRICE_TARGET_RANGE_INVALID'),
    ('last_updated', '2026-10-18', 'PRICE_TARGET_DATE_INVALID'),
    ('last_updated', '2026-10-08T21:00:00', 'PRICE_TARGET_DATE_INVALID'),
    ('last_updated', None, 'PRICE_TARGET_DATE_INVALID'),
    ('symbol', 'MSFT', 'ANALYST_CONTEXT_IDENTITY_OR_SCHEMA_INVALID'),
])
def test_targets_reject_invalid_financial_values_ranges_dates_and_identity(key, value, reason):
    payload = {**TARGETS, key:value}
    assert analyst_context_rejection('price_targets', payload, ticker='NVDA', now=NOW) == reason


def _write_analyst_document(root, recommendations=RECOMMENDATIONS, targets=TARGETS):
    document = _document()
    document['families']['recommendations'] = _family('recommendations', '/stock/recommendation', recommendations)
    document['families']['price_targets'] = _family('price_targets', '/stock/price-target', targets)
    document = seal_research_market_bundle(document)
    path = root/'NVDA.json'; path.write_text(json.dumps(document))
    return path


@pytest.mark.parametrize('value', ['unknown', True, -1, 0.5, None])
@pytest.mark.parametrize('enabled', [False, True])
def test_actual_customer_projection_withholds_bad_admitted_counts_without_crash_or_rating_change(tmp_path, monkeypatch, value, enabled):
    recommendations = deepcopy(RECOMMENDATIONS); recommendations['periods'][0]['strong_buy'] = value
    path = _write_analyst_document(tmp_path, recommendations)
    before_bytes = path.read_bytes()
    monkeypatch.delenv('ATLAS_QA_MODE', raising=False)
    monkeypatch.delenv('ATLAS_RESEARCH_V2_QA_ENRICHMENT', raising=False)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', str(enabled).lower())
    source = report(); before = deepcopy(source)
    result = build_customer_research_v2(source)
    assert result['status'] == 'AVAILABLE'
    assert result['header']['fair_value'] == 346.05
    assert source == before and path.read_bytes() == before_bytes
    receipt = result['market_context']['admission_receipt']
    assert receipt['family_rejections'] == [{'capability':'recommendations', 'reason':'RECOMMENDATIONS_COUNTS_INVALID'}]
    if enabled:
        assert result['wall_street']['status'] == 'PARTIAL'
        assert result['wall_street']['analyst_count'] is None
        assert result['wall_street']['consensus'] is None
        assert result['wall_street']['target_average'] == 240
    else:
        assert result['wall_street'] == {'status':'DISABLED', 'classification':'CONTEXTUAL_NON_SCORING',
                                       'reason':'CONTEXT_DISPLAY_NOT_ENABLED'}


@pytest.mark.parametrize('enabled', [False, True])
def test_projection_defends_explicit_qa_enrichment_too(monkeypatch, enabled):
    import services.customer_research_v2 as projection
    payload = deepcopy(RECOMMENDATIONS); payload['periods'][0]['buy'] = 'unknown'
    enrichment = {'recommendations': {'payload':payload, 'provenance':{'raw_evidence_id':'GENERATED:INVALID'}}}
    monkeypatch.setattr(projection, '_qa_enrichment', lambda _:enrichment)
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', str(enabled).lower())
    result = projection.build_customer_research_v2(report())
    assert result['status'] == 'AVAILABLE'
    assert result['wall_street']['status'] == ('UNAVAILABLE' if enabled else 'DISABLED')
    if enabled:
        assert result['wall_street']['analyst_count'] is None and result['wall_street']['consensus'] is None


def test_zero_analysts_never_creates_strong_buy_consensus(tmp_path, monkeypatch):
    recommendations = {'periods':[{'period':'2026-10-01', **dict.fromkeys(COUNTS, 0)}]}
    _write_analyst_document(tmp_path, recommendations)
    monkeypatch.delenv('ATLAS_QA_MODE', raising=False)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', 'true')
    result = build_customer_research_v2(report())['wall_street']
    assert result['analyst_count'] == 0
    assert result['buy_count'] == result['hold_count'] == result['sell_count'] == 0
    assert result['consensus'] is None
    assert result['reason'] == 'NO_ANALYST_COVERAGE'
    assert result['status'] == 'PARTIAL' and result['target_average'] == 240


def test_resealed_target_evidence_cannot_postdate_its_recorded_capture(tmp_path):
    path = _write_analyst_document(tmp_path, targets={**TARGETS, 'last_updated':'2026-10-17'})
    receipt = {}
    result = load_research_market_context('NVDA', tmp_path, now=NOW, admission_receipt=receipt)
    assert 'price_targets' not in result and 'recommendations' in result
    assert receipt['family_rejections'] == [{'capability':'price_targets', 'reason':'PRICE_TARGET_DATE_INVALID'}]


def test_valid_retained_analyst_context_reaches_projection_without_mutation(tmp_path, monkeypatch):
    path = _write_analyst_document(tmp_path)
    before = path.read_bytes()
    monkeypatch.delenv('ATLAS_QA_MODE', raising=False)
    monkeypatch.delenv('ATLAS_RESEARCH_V2_QA_ENRICHMENT', raising=False)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', 'true')
    result = build_customer_research_v2(report())
    assert result['wall_street']['status'] == 'AVAILABLE'
    assert result['wall_street']['analyst_count'] == 22
    assert result['wall_street']['consensus'] == 'Strong Buy'
    assert result['wall_street']['target_average'] == 240
    assert result['wall_street']['target_low'] == 180 and result['wall_street']['target_high'] == 300
    assert result['wall_street']['as_of'] == '2026-10-08'
    assert result['market_context']['admission_receipt']['family_rejections'] == []
    assert result['header']['fair_value'] == 346.05 and path.read_bytes() == before


def test_invalid_target_is_withheld_without_hiding_valid_analyst_counts(tmp_path, monkeypatch):
    _write_analyst_document(tmp_path, targets={**TARGETS, 'target_mean':float('nan')})
    monkeypatch.delenv('ATLAS_QA_MODE', raising=False)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', 'true')
    result = build_customer_research_v2(report())
    assert result['wall_street']['analyst_count'] == 22
    assert result['wall_street']['consensus'] == 'Strong Buy'
    assert result['wall_street']['target_average'] is None
    assert result['wall_street']['status'] == 'PARTIAL'
    assert result['market_context']['admission_receipt']['family_rejections'] == [
        {'capability':'price_targets', 'reason':'PRICE_TARGET_VALUE_INVALID'}]


def test_missing_periods_and_untrusted_values_never_leak_into_rejection_receipt(tmp_path):
    sensitive = '/private/provider-source?token=DO_NOT_ECHO'
    _write_analyst_document(tmp_path, recommendations={'periods':[{'period':sensitive, **COUNTS}]})
    receipt = {}
    result = load_research_market_context('NVDA', tmp_path, now=NOW, admission_receipt=receipt)
    assert 'recommendations' not in result and 'price_targets' in result
    assert receipt['family_rejections'] == [{'capability':'recommendations', 'reason':'RECOMMENDATIONS_PERIOD_INVALID'}]
    assert sensitive not in json.dumps(receipt)


@pytest.mark.parametrize('counts', [
    {**dict.fromkeys(COUNTS, 0), 'strong_buy':10**400},
    {**dict.fromkeys(COUNTS, 0), 'strong_buy':COUNT_MAX_EXACT_INTEGER, 'hold':1},
])
def test_oversize_or_aggregate_inexact_counts_are_withheld_by_actual_projection(tmp_path, monkeypatch, counts):
    path = _write_analyst_document(tmp_path, recommendations={'periods':[{'period':'2026-10-01', **counts}]})
    before = path.read_bytes()
    monkeypatch.delenv('ATLAS_QA_MODE', raising=False)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', 'true')
    result = build_customer_research_v2(report())
    assert result['wall_street']['analyst_count'] is None and result['wall_street']['consensus'] is None
    assert result['wall_street']['status'] == 'PARTIAL' and result['wall_street']['target_average'] == 240
    assert result['market_context']['admission_receipt']['family_rejections'] == [
        {'capability':'recommendations', 'reason':'RECOMMENDATIONS_COUNTS_INVALID'}]
    assert path.read_bytes() == before


def test_exact_integer_boundary_is_projected_without_rounding_or_clipping(tmp_path, monkeypatch):
    counts = {'strong_buy':COUNT_MAX_EXACT_INTEGER - 4, 'buy':1, 'hold':1, 'sell':1, 'strong_sell':1}
    path = _write_analyst_document(tmp_path, recommendations={'periods':[{'period':'2026-10-01', **counts}]})
    before = path.read_bytes()
    monkeypatch.delenv('ATLAS_QA_MODE', raising=False)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', 'true')
    result = build_customer_research_v2(report())
    assert result['wall_street']['status'] == 'AVAILABLE'
    assert result['wall_street']['analyst_count'] == COUNT_MAX_EXACT_INTEGER
    assert result['wall_street']['buy_count'] == COUNT_MAX_EXACT_INTEGER - 3
    assert result['wall_street']['sell_count'] == 2
    assert result['wall_street']['consensus'] == 'Strong Buy'
    assert result['market_context']['admission_receipt']['family_rejections'] == []
    assert path.read_bytes() == before


@pytest.mark.parametrize('updated', [
    '2023-04-06 00:00:00',  # Finnhub's documented provider-native shape.
    '2026-10-16 23:59:59',  # Later wall time is not claimed as UTC or compared as such.
    '2026-10-16',
    '2026-10-16T20:59:59Z',
])
def test_native_target_clock_retains_its_source_value_and_only_calendar_authority(tmp_path, monkeypatch, updated):
    path = _write_analyst_document(tmp_path, targets={**TARGETS, 'last_updated':updated})
    before = path.read_bytes()
    receipt = {}
    context = load_research_market_context('NVDA', tmp_path, now=NOW, admission_receipt=receipt)
    assert context['price_targets']['payload']['last_updated'] == updated
    assert receipt['family_rejections'] == []
    monkeypatch.delenv('ATLAS_QA_MODE', raising=False)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', 'true')
    result = build_customer_research_v2(report())
    assert result['wall_street']['target_average'] == 240
    assert result['wall_street']['as_of'] == updated
    assert path.read_bytes() == before


@pytest.mark.parametrize('updated', [
    '2026-10-17 00:00:00',  # Source day follows its individual response capture day.
    '2026-10-16 24:00:00', '2026-10-16 23:60:00', '2026-10-16 23:59:60',
    '2026-02-30 00:00:00', '2026-1-16 00:00:00',
    '2026-10-16T21:00:01Z',  # Offset-aware source instant follows recorded response completion.
    '2026-10-16T23:00:01+02:00',
])
def test_invalid_native_clock_or_future_aware_instant_remains_withheld(tmp_path, updated):
    path = _write_analyst_document(tmp_path, targets={**TARGETS, 'last_updated':updated})
    before = path.read_bytes()
    receipt = {}
    context = load_research_market_context('NVDA', tmp_path, now=NOW, admission_receipt=receipt)
    assert 'price_targets' not in context and 'recommendations' in context
    assert receipt['family_rejections'] == [{'capability':'price_targets', 'reason':'PRICE_TARGET_DATE_INVALID'}]
    assert path.read_bytes() == before
