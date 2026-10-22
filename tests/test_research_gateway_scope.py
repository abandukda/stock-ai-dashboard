from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json

import pytest

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.operations_gateway import GatewayApproval, canonical_bytes, verify_scope
from services.research_gateway_scope import build_research_gateway_scope
from services.research_refresh_execution import compile_execution_plan
from services.research_refresh_readiness import ResearchRefreshLimits, SUPPORTED_CAPABILITIES, plan_research_refresh


SOURCE = 'a' * 40
NOW = datetime(2026, 10, 22, 22, 5, tzinfo=timezone.utc)
COMPATIBLE = ('historical_ohlcv', 'financial_statements', 'stock_earnings', 'earnings_calendar',
              'recommendations', 'price_targets', 'company_news', 'company_profile')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def _plan(capabilities=COMPATIBLE, *, tickers=('NVDA',), ceiling=40):
    upstream = plan_research_refresh(tickers, {}, {'status': 'APPROVED', 'contract_id': CONTRACT_ID,
        'capabilities': list(capabilities)}, source_sha=SOURCE, now=NOW, capabilities=capabilities,
        limits=ResearchRefreshLimits(max_tickers=4, max_requests=ceiling))
    return compile_execution_plan(upstream, as_of=NOW.date())


def _reseal(plan):
    for row in plan['requests']:
        row.pop('request_sha256', None)
        row['request_sha256'] = _digest(row)
    plan['scope_sha256'] = _digest({key: plan[key] for key in ('source_sha', 'as_of', 'requests', 'limits')})
    plan.pop('package_sha256', None)
    plan['package_sha256'] = _digest(plan)
    return plan


def test_exact_compatible_four_ticker_plan_is_gateway_verifiable_without_authorizing_acquisition(tmp_path):
    plan = _plan(tickers=('NVDA', 'MSFT', 'META', 'ANET'))
    before = deepcopy(plan)
    result = build_research_gateway_scope(plan, expected_source_sha=SOURCE, rate_limit_rpm=60)
    assert plan == before
    assert result['request_count'] == 40
    assert result['max_provider_calls'] == 40
    assert result['authorization_issued'] is False
    assert result['provider_calls'] == result['publication_writes'] == result['report_card_writes'] == 0
    scope = result['scope']
    assert scope['limits'] == plan['limits']
    assert scope['execution_policy'] == {'rate_limit_rpm': 60, 'concurrency': 1, 'retry_count': 0}
    assert scope['source_sha'] == SOURCE
    assert scope['refresh_package_sha256'] == plan['package_sha256']
    assert scope['refresh_scope_sha256'] == plan['scope_sha256']
    assert 'authorization_token' not in json.dumps(result)
    for old, new in zip(plan['requests'], scope['requests']):
        assert new['method'] == 'GET'
        assert new['source_request_sha256'] == old['request_sha256']
        assert new['ordinal'] == old['ordinal']
        assert new['parameters'] == old['parameters']
        assert new['endpoint'] == old['endpoint']
    # Plan-mode approval exists only in this mock fixture; no acquire token or request.
    digest = result['scope_sha256']
    approved = GatewayApproval.parse({'operation': 'plan', 'source_sha': SOURCE,
        'scope_sha256': digest, 'max_provider_calls': result['max_provider_calls'],
        'authorization_token': f'ATLAS_PLAN:{digest}'})
    target = tmp_path / 'scope.json'
    target.write_bytes(canonical_bytes(scope))
    assert verify_scope(target, approved) == scope
    target.write_bytes(canonical_bytes(result))  # Never submit the wrapper as scope.
    with pytest.raises(PermissionError, match='DIGEST_MISMATCH'):
        verify_scope(target, approved)


def test_scope_is_deterministic_and_preserves_pending_families():
    plan = _plan()
    plan['deferred'].append({'ticker': 'NVDA', 'capability': 'live_quote', 'reason': 'NOT_IN_UPSTREAM_PLAN'})
    _reseal(plan)
    first = build_research_gateway_scope(plan, expected_source_sha=SOURCE)
    assert first == build_research_gateway_scope(deepcopy(plan), expected_source_sha=SOURCE)
    assert first['scope']['deferred'] == plan['deferred']
    first['scope']['deferred'][0]['reason'] = 'changed'
    assert plan['deferred'][0]['reason'] == 'NOT_IN_UPSTREAM_PLAN'


@pytest.mark.parametrize('capability', ['live_quote', 'basic_financials', 'analyst_actions', 'revenue_estimates', 'eps_estimates'])
def test_unsupported_endpoint_is_rejected_without_silent_filtering(capability):
    plan = _plan((capability,))
    with pytest.raises(PermissionError, match='ENDPOINT_UNSUPPORTED'):
        build_research_gateway_scope(plan, expected_source_sha=SOURCE)


def test_complete_60_request_scope_cannot_be_silently_narrowed():
    plan = _plan(SUPPORTED_CAPABILITIES, tickers=('NVDA', 'MSFT', 'META', 'ANET'), ceiling=60)
    assert len(plan['requests']) == 60
    before = deepcopy(plan)
    with pytest.raises(PermissionError, match='ENDPOINT_UNSUPPORTED'):
        build_research_gateway_scope(plan, expected_source_sha=SOURCE)
    assert plan == before


@pytest.mark.parametrize('mutation', ['package', 'scope', 'request', 'source', 'budget', 'retry', 'concurrency',
                                     'endpoint_alias', 'parameters', 'secret', 'schema', 'duplicate',
                                     'published', 'empty', 'ticker', 'upstream'])
def test_invalid_source_hash_budget_policy_or_request_fails_closed(mutation):
    plan = _plan(('company_profile',))
    expected = SOURCE
    if mutation == 'package':
        plan['package_sha256'] = '0' * 64
    elif mutation == 'scope':
        plan['scope_sha256'] = '0' * 64
        plan.pop('package_sha256'); plan['package_sha256'] = _digest(plan)
    elif mutation == 'request':
        plan['requests'][0]['parameters']['symbol'] = 'MSFT'
    elif mutation == 'source':
        expected = 'b' * 40
    else:
        if mutation == 'budget': plan['limits']['max_requests'] = 0
        elif mutation == 'retry': plan['limits']['retries'] = 1
        elif mutation == 'concurrency': plan['limits']['concurrency'] = 2
        elif mutation == 'endpoint_alias': plan['requests'][0]['endpoint'] = '/stock/candle'
        elif mutation == 'parameters': plan['requests'][0]['parameters']['symbol'] = 'MSFT'
        elif mutation == 'secret': plan['requests'][0]['parameters']['token'] = 'MOCK_SECRET_NEVER_TRANSMITTED'
        elif mutation == 'schema': plan['requests'][0]['headers'] = {'Authorization': 'MOCK_ONLY'}
        elif mutation == 'duplicate': plan['requests'].append({**deepcopy(plan['requests'][0]), 'ordinal': 2})
        elif mutation == 'published': plan['publication_writes'] = 1
        elif mutation == 'empty': plan['requests'] = []
        elif mutation == 'ticker': plan['requests'][0]['ticker'] = '../bad'
        elif mutation == 'upstream': plan['upstream_plan_sha256'] = 'unbound'
        _reseal(plan)
    with pytest.raises((ValueError, PermissionError)):
        build_research_gateway_scope(plan, expected_source_sha=expected)


@pytest.mark.parametrize('rpm', [0, 501, True, '60'])
def test_rate_limit_is_explicit_and_bounded(rpm):
    with pytest.raises(ValueError, match='RATE_INVALID'):
        build_research_gateway_scope(_plan(), expected_source_sha=SOURCE, rate_limit_rpm=rpm)


def test_mock_gateway_approval_cannot_expand_source_or_budget(tmp_path):
    result = build_research_gateway_scope(_plan(), expected_source_sha=SOURCE)
    scope = result['scope']; target = tmp_path / 'scope.json'; target.write_bytes(canonical_bytes(scope))
    digest = result['scope_sha256']
    for source, budget, error in [('b' * 40, result['max_provider_calls'], 'SOURCE_MISMATCH'),
                                  (SOURCE, 0, 'BUDGET_EXCEEDED')]:
        approved = GatewayApproval.parse({'operation': 'plan', 'source_sha': source,
            'scope_sha256': digest, 'max_provider_calls': budget,
            'authorization_token': f'ATLAS_PLAN:{digest}'})
        with pytest.raises(PermissionError, match=error):
            verify_scope(target, approved)


@pytest.mark.parametrize('key', ['retained_fresh', 'unavailable', 'deferred'])
def test_pending_metadata_cannot_copy_unexpected_credential_fields(key):
    plan = _plan()
    row = {'ticker': 'NVDA', 'capability': 'live_quote', 'token': 'MOCK_SECRET'}
    if key != 'retained_fresh': row['reason'] = 'NOT_IN_UPSTREAM_PLAN'
    plan[key] = [row]
    _reseal(plan)
    with pytest.raises(ValueError, match='PENDING_SCHEMA_INVALID'):
        build_research_gateway_scope(plan, expected_source_sha=SOURCE)


def test_execution_limits_cannot_copy_unexpected_credential_fields():
    plan = _plan(); plan['limits']['token'] = 'MOCK_SECRET'; _reseal(plan)
    with pytest.raises(ValueError, match='LIMITS_INVALID'):
        build_research_gateway_scope(plan, expected_source_sha=SOURCE)
