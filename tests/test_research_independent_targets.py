"""Independent admitted analyst families retain independent display readiness."""
from copy import deepcopy

import pytest

from services.customer_research_v2 import build_customer_research_v2
from services.research_analyst_readiness import analyst_display_fact
from tests.test_customer_research_v2 import report
from tests.test_research_analyst_context import _write_analyst_document, RECOMMENDATIONS, TARGETS


@pytest.mark.parametrize('state', ['valid', 'zero', 'malformed', 'missing', 'invalid_target', 'missing_target', 'range_only', 'off'])
def test_real_admission_projection_and_downstream_views_keep_independent_authority(tmp_path, monkeypatch, state):
    recs = deepcopy(RECOMMENDATIONS)
    targets = deepcopy(TARGETS)
    if state == 'zero':
        recs['periods'][0].update({key: 0 for key in ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell')})
    if state == 'malformed':
        recs['periods'][0]['buy'] = 'unknown'
    if state == 'missing':
        recs = {'periods': []}
    if state == 'invalid_target':
        targets['target_mean'] = True
    if state == 'missing_target':
        targets = {}
    if state == 'range_only':
        targets.pop('target_mean')
    path = _write_analyst_document(tmp_path, recs, targets)
    before_bytes = path.read_bytes()
    monkeypatch.delenv('ATLAS_QA_MODE', raising=False)
    monkeypatch.delenv('ATLAS_RESEARCH_V2_QA_ENRICHMENT', raising=False)
    monkeypatch.setenv('ATLAS_RESEARCH_MARKET_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('ATLAS_WALL_STREET_CONTEXT_ENABLED', str(state != 'off').lower())
    source = report(); before = deepcopy(source)
    page = build_customer_research_v2(source)
    admitted = state not in {'invalid_target', 'missing_target', 'range_only', 'off'}
    assert page['valuation_chart']['values'].get('Wall St. Average') == (240 if admitted else None)
    valuation = page['institutional_report']['valuation']
    assert valuation['wall_street_target_average'] == (240 if admitted else None)
    fact = analyst_display_fact(page['analyst_context_readiness'], 'average_target')
    assert fact['status'] == ('AVAILABLE' if admitted else 'DISABLED' if state == 'off' else 'UNAVAILABLE')
    if admitted:
        assert valuation['wall_street_as_of'] == TARGETS['last_updated']
        assert '240' in str(page['investment_digest'])
    if state in {'zero', 'malformed', 'missing'}:
        assert page['wall_street']['status'] == 'PARTIAL'
        assert valuation['wall_street_consensus'] is None
    if state == 'zero':
        assert page['wall_street']['analyst_count'] == 0
        assert page['wall_street']['reason'] == 'NO_ANALYST_COVERAGE'
        assert valuation['wall_street_recommendations_status'] == 'NO_COVERAGE'
    assert page['header']['fair_value'] == 346.05
    assert source == before and path.read_bytes() == before_bytes


def test_downstream_readiness_does_not_infer_authority_from_combined_status():
    from services.institutional_research_report import build_institutional_research_report
    from services.research_investment_digest import build_investment_digest
    page = build_customer_research_v2(report())
    page.pop('analyst_context_readiness', None)
    page['wall_street'] = {'status': 'AVAILABLE', 'target_average': 999999, 'consensus': 'Invented'}
    assert build_institutional_research_report(page)['valuation']['wall_street_target_average'] is None
    assert '999999' not in str(build_investment_digest(page))
    assert analyst_display_fact({}, 'average_target') == {'status': 'UNAVAILABLE'}
