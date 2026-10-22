"""Public reason receipts observe admission without changing its authority."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pandas as pd
import pytest

from services.research_market_read_model import (
    ADMISSION_REASON_CODES, load_research_market_context, public_admission_marker_values,
    seal_research_market_bundle,
)
from tests.test_research_market_read_model import _document
from tests.test_customer_research_v2 import report

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def write_document(root, document):
    root.mkdir(exist_ok=True)
    (root / 'NVDA.json').write_text(json.dumps(document))


def test_empty_roots_and_invalid_ticker_return_empty_without_filesystem_access(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('unexpected file access')
    monkeypatch.setattr(Path, 'read_text', forbidden)
    receipt = {'old_secret': '/private/key'}
    assert load_research_market_context('NVDA', '', admission_receipt=receipt) == {}
    assert receipt['reason'] == 'ROOTS_NOT_CONFIGURED'
    assert not receipt['primary_configured'] and not receipt['backup_configured']
    assert 'old_secret' not in receipt
    assert load_research_market_context('???', '/private', admission_receipt=receipt) == {}
    assert receipt['reason'] == 'INVALID_TICKER'


def test_missing_and_unreadable_files_are_distinct_without_path_or_exception_leaks(tmp_path, monkeypatch):
    root = tmp_path / 'PRIVATE_OWNER_STORAGE'
    receipt = {}
    assert load_research_market_context('NVDA', root, admission_receipt=receipt) == {}
    assert receipt['reason'] == 'FILE_NOT_FOUND'
    def unreadable(*args, **kwargs): raise PermissionError('SECRET_CREDENTIAL_AND_PATH')
    monkeypatch.setattr(Path, 'read_text', unreadable)
    assert load_research_market_context('NVDA', root, admission_receipt=receipt) == {}
    assert receipt['reason'] == 'FILE_UNREADABLE'
    encoded = json.dumps(receipt)
    assert str(root) not in encoded and 'SECRET_CREDENTIAL' not in encoded


@pytest.mark.parametrize('mutation,source_pin,bundle_pin,reason', [
    (lambda d: d.update(schema='PRIVATE_INVALID_SCHEMA'), None, None, 'SCHEMA_OR_LINEAGE_REJECTED'),
    (lambda d: d.update(lineage_sha256='PRIVATE_LINEAGE'), None, None, 'SCHEMA_OR_LINEAGE_REJECTED'),
    (lambda d: None, 'PRIVATE_SOURCE_PIN', None, 'SOURCE_PIN_MISMATCH'),
    (lambda d: None, None, 'PRIVATE_BUNDLE_PIN', 'BUNDLE_PIN_MISMATCH'),
    (lambda d: d.update(record_sha256='PRIVATE_CORRUPT_HASH'), None, None, 'RECORD_HASH_MISMATCH'),
])
def test_individual_admission_gates_keep_empty_failure_and_public_codes(tmp_path, mutation, source_pin, bundle_pin, reason):
    document = _document()
    mutation(document)
    write_document(tmp_path, document)
    receipt = {}
    result = load_research_market_context('NVDA', tmp_path, now=NOW, expected_source_sha=source_pin,
                                         expected_bundle_id=bundle_pin, admission_receipt=receipt)
    assert result == {}
    assert receipt['status'] == 'UNAVAILABLE' and receipt['reason'] == reason
    assert 'PRIVATE_' not in json.dumps(receipt)
    assert str(tmp_path) not in json.dumps(receipt)


def test_backup_authority_rejection_does_not_bypass_any_admission_gate(tmp_path):
    write_document(tmp_path, _document())
    receipt = {}
    assert load_research_market_context('NVDA', None, backup_root=tmp_path, now=NOW, admission_receipt=receipt) == {}
    assert receipt['reason'] == 'BACKUP_AUTHORITY_REJECTED'
    assert receipt['attempts'] == [{'source': 'BACKUP', 'reason': 'BACKUP_AUTHORITY_REJECTED'}]


def test_valid_context_is_identical_with_or_without_receipt(tmp_path):
    write_document(tmp_path, _document())
    expected = load_research_market_context('NVDA', tmp_path, now=NOW)
    receipt = {}
    actual = load_research_market_context('NVDA', tmp_path, now=NOW, admission_receipt=receipt)
    assert actual == expected and actual['__read_model__']['cache_source'] == 'PRIMARY'
    assert receipt['status'] == 'AVAILABLE' and receipt['reason'] == 'CONTEXT_ADMITTED'
    assert receipt['accepted_family_count'] == 3 and receipt['rejected_family_count'] == 0
    assert receipt['history_status'] == 'ADMITTED'
    assert '__read_model__' not in receipt and 'payload' not in receipt


def test_valid_backup_fallback_preserves_primary_failure_receipt(tmp_path):
    primary, backup = tmp_path / 'PRIVATE_PRIMARY', tmp_path / 'PRIVATE_BACKUP'
    primary.mkdir(); (primary / 'NVDA.json').write_text('{corrupt')
    document = _document()
    document['backup_provenance'] = {'independent_copy': True, 'lineage_sha256': document['lineage_sha256']}
    write_document(backup, seal_research_market_bundle(document))
    receipt = {}
    actual = load_research_market_context('NVDA', primary, backup_root=backup, now=NOW, admission_receipt=receipt)
    expected = load_research_market_context('NVDA', primary, backup_root=backup, now=NOW)
    assert actual == expected and actual['__read_model__']['cache_source'] == 'BACKUP'
    assert receipt['status'] == 'AVAILABLE'
    assert receipt['attempts'] == [{'source': 'PRIMARY', 'reason': 'FILE_UNREADABLE'},
                                   {'source': 'BACKUP', 'reason': 'BUNDLE_ACCEPTED'}]
    assert 'PRIVATE_' not in json.dumps(receipt)


def test_primary_pin_rejection_is_not_hidden_by_optional_missing_backup(tmp_path):
    write_document(tmp_path, _document())
    receipt = {}
    assert load_research_market_context('NVDA', tmp_path, backup_root=tmp_path / 'missing',
        expected_source_sha='wrong', now=NOW, admission_receipt=receipt) == {}
    assert receipt['reason'] == 'SOURCE_PIN_MISMATCH'
    assert receipt['attempts'][-1]['reason'] == 'FILE_NOT_FOUND'


@pytest.mark.parametrize('case,reason,accepted,rejected', [
    ('rejected_history', 'HISTORY_FAMILY_REJECTED', 2, 1),
    ('missing_history', 'HISTORY_FAMILY_MISSING', 2, 0),
    ('all_rejected', 'NO_VERIFIED_FAMILIES', 0, 1),
])
def test_family_failure_is_distinct_from_bundle_admission(tmp_path, case, reason, accepted, rejected):
    document = _document()
    if case == 'missing_history':
        document['families'].pop('historical_ohlcv')
    else:
        document['families']['historical_ohlcv']['provenance']['commercial_display_allowed'] = False
        if case == 'all_rejected':
            document['families'] = {'historical_ohlcv': document['families']['historical_ohlcv']}
    write_document(tmp_path, seal_research_market_bundle(document))
    receipt = {}
    result = load_research_market_context('NVDA', tmp_path, now=NOW, admission_receipt=receipt)
    assert receipt['reason'] == reason
    assert receipt['accepted_family_count'] == accepted and receipt['rejected_family_count'] == rejected
    assert bool(result) is bool(accepted)
    assert 'historical_ohlcv' not in result


def test_stale_history_remains_admitted_not_rejected_by_diagnostics(tmp_path):
    write_document(tmp_path, _document())
    receipt = {}
    result = load_research_market_context('NVDA', tmp_path, now=datetime(2026, 11, 20, tzinfo=timezone.utc), admission_receipt=receipt)
    assert result['historical_ohlcv']['cache_status'] == 'STALE_RETAINED'
    assert receipt['status'] == 'AVAILABLE' and receipt['history_status'] == 'ADMITTED'


def test_customer_view_retains_safe_receipt_without_changing_financial_authority(monkeypatch):
    from services.customer_research_view import build_customer_research_view
    monkeypatch.setattr('services.customer_research_v2._qa_enrichment', lambda ticker: {})
    for name in ('ATLAS_RESEARCH_MARKET_DATA_ROOT', 'ATLAS_RESEARCH_MARKET_DATA_BACKUP_ROOT'):
        monkeypatch.delenv(name, raising=False)
    source = report(); before = deepcopy(source)
    result = build_customer_research_view(source).as_mapping()
    assert result['market_context']['status'] == 'UNAVAILABLE'
    assert result['market_context']['admission_receipt']['reason'] == 'ROOTS_NOT_CONFIGURED'
    assert result['header']['price'] == 186.09 and result['header']['fair_value'] == 346.05
    assert source == before


def test_qa_enrichment_receipt_does_not_claim_production_admission(monkeypatch):
    from services.customer_research_v2 import build_customer_research_v2
    monkeypatch.setattr('services.customer_research_v2._qa_enrichment', lambda ticker: {'__atlas_ticker__': ticker})
    result = build_customer_research_v2(report())
    assert result['market_context']['status'] == 'QA_ONLY'
    assert result['market_context']['admission_receipt']['reason'] == 'QA_ENRICHMENT_USED'


def test_rendered_marker_only_admits_whitelisted_public_codes():
    source = Path('ui/customer_research_v2.py').read_text()
    tree = ast.parse(source)
    marker = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_marker')
    ui = SimpleNamespace(markdown=Mock())
    ns = {'st': ui, 'Any': Any, 'escape': escape}
    exec(compile(ast.Module(body=[marker], type_ignores=[]), '<actual_ui_marker>', 'exec'), ns)
    ns['_marker']('market-admission', 'NVDA', **public_admission_marker_values({
        'status': '/private/root', 'reason': {'secret': 'PRIVATE_KEY'}, 'payload': 'PRIVATE_BAR',
        'primary_configured': '/private/root', 'source_pin_configured': True,
        'accepted_family_count': 'PRIVATE_COUNT', 'rejected_family_count': -10,
        'history_status': 'PRIVATE_HISTORY',
    }))
    html = ui.markdown.call_args.args[0]
    assert 'NOT_RECORDED' in html and 'ADMISSION_RECEIPT_UNAVAILABLE' in html
    assert '/private' not in html and 'PRIVATE_' not in html
    assert 'data-atlas-source-pin-configured="True"' in html
    assert 'data-atlas-primary-configured="False"' in html
    assert 'data-atlas-accepted-family-count="0"' in html
    assert 'data-atlas-history-reason="HISTORY_NOT_EVALUATED"' in html
    render = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render_customer_research_v2')
    call = next(n for n in ast.walk(render) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == '_marker' and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'market-admission')
    assert any(k.arg is None and isinstance(k.value, ast.Call) and k.value.func.id == 'public_admission_marker_values' for k in call.keywords)


def test_actual_annotated_outlook_caption_escapes_currency_without_changing_evidence(monkeypatch):
    from services import annotated_research_chart
    evidence = {'outlook': 'Last close $12.34; support $10.00.', 'evidence_digest': 'mock',
                'candles': False, 'volume_available': False, 'pending_lookbacks': [], 'methodology': 'Mock methodology'}
    before = deepcopy(evidence)
    monkeypatch.setattr(annotated_research_chart, 'build_annotated_research_chart', lambda *args, **kwargs: (object(), evidence))
    tree = ast.parse(Path('ui/customer_research_v2.py').read_text())
    names = {'_escape_markdown_currency', '_annotated_customer_price_chart'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ui = SimpleNamespace(caption=Mock(), plotly_chart=Mock(), warning=Mock())
    ns = {'Any': Any, 'st': ui, '_marker': lambda *args, **kwargs: None, 'datetime': datetime, '_friendly_time': str}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual_chart_caption>', 'exec'), ns)
    dates = pd.to_datetime(['2026-10-15', '2026-10-16'], utc=True)
    rows = pd.DataFrame({'date': dates, 'close': [12.00, 12.34]})
    ns['_annotated_customer_price_chart'](pd.DataFrame(index=dates), rows=rows, date_key='date', close_key='close',
                                          ticker='NVDA', chart={}, report={}, key='mock')
    assert ui.caption.call_args_list[0].args[0] == r'Last close \$12.34; support \$10.00.'
    assert evidence == before


def test_crawler_public_code_domain_matches_producer_without_financial_dependency():
    from agents import atlas_visual_crawler_v1 as crawler
    from services.research_market_read_model import ADMISSION_STATUS_CODES
    assert crawler._MARKET_ADMISSION_STATUS_CODES == ADMISSION_STATUS_CODES
    assert crawler._MARKET_ADMISSION_REASON_CODES == ADMISSION_REASON_CODES
    attributes = public_admission_marker_values({
        'status': 'PARTIAL', 'reason': 'HISTORY_FAMILY_REJECTED', 'history_status': 'REJECTED',
        'primary_configured': True, 'backup_configured': False,
        'accepted_family_count': 2, 'rejected_family_count': 1,
    })
    assert crawler._sanitize_market_admission_attributes({key: str(value) for key, value in attributes.items()}) == attributes


@pytest.mark.parametrize('chart_passed', [False, True])
@pytest.mark.parametrize('hostile_marker', [False, True])
def test_actual_crawler_records_sanitized_receipt_on_chart_pass_and_failure(monkeypatch, chart_passed, hostile_marker):
    import asyncio
    from unittest.mock import AsyncMock
    from agents import atlas_visual_crawler_v1 as module
    attributes = {
        'status': 'PARTIAL', 'reason': 'HISTORY_FAMILY_REJECTED', 'history_status': 'REJECTED',
        'primary_configured': 'True', 'backup_configured': 'False',
        'source_pin_configured': 'True', 'bundle_pin_configured': 'True',
        'accepted_family_count': '2', 'rejected_family_count': '1',
        'root': '/PRIVATE_STORAGE', 'payload': 'PRIVATE_BARS',
    }
    if hostile_marker:
        attributes.update(status='PRIVATE_STATUS', reason='PRIVATE_PATH', history_status='PRIVATE_HISTORY',
                          accepted_family_count='PRIVATE_COUNT', rejected_family_count='-1')
    requested = []
    class Locator:
        def __init__(self, kind): self.kind = kind
        @property
        def last(self): return self
        async def count(self):
            return 1 if self.kind == 'admission' or chart_passed else 0
        async def get_attribute(self, name):
            requested.append(name)
            if self.kind == 'admission': return attributes.get(name.removeprefix('data-atlas-').replace('-', '_'))
            if name == 'data-atlas-status': return 'AVAILABLE'
            if name == 'data-atlas-panels': return '4'
        def nth(self, index): return self
        def locator(self, selector): return Locator('nested')
        async def all_text_contents(self): return ['NVDA OHLC']
        async def scroll_into_view_if_needed(self, **kwargs): pass
        async def is_visible(self): return chart_passed
    class Scope:
        def locator(self, selector):
            return Locator('admission' if 'market-admission' in selector else 'chart')
    monkeypatch.setattr(module, '_scopes', lambda page: [Scope()])
    crawler = module.AtlasVisualCrawler.__new__(module.AtlasVisualCrawler)
    crawler._record = AsyncMock()
    crawler._shot_locator = AsyncMock(return_value='GENERATED_CHART.png')
    assert asyncio.run(crawler._annotated_chart_evidence(object(), 'NVDA', 'desktop')) is chart_passed
    record = crawler._record.call_args.kwargs
    assert record['passed'] is chart_passed and record['required'] is True
    receipt = json.loads(record['observed'].split('; market_admission=', 1)[1])
    assert receipt['marker_present'] is True
    if hostile_marker:
        assert receipt['status'] == 'NOT_RECORDED'
        assert receipt['reason'] == 'ADMISSION_RECEIPT_UNAVAILABLE'
        assert receipt['accepted_family_count'] == 0
    else:
        assert receipt['reason'] == 'HISTORY_FAMILY_REJECTED'
        assert receipt['history_reason'] == 'HISTORY_FAMILY_REJECTED'
        assert receipt['accepted_family_count'] == 2
    assert 'PRIVATE_' not in record['observed']
    assert 'data-atlas-root' not in requested and 'data-atlas-payload' not in requested
