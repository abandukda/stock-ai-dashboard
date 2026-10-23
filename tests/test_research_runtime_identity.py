from copy import deepcopy
import asyncio
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import services.research_runtime_identity as identity


def graph(tmp_path, monkeypatch):
    sources = (
        'def build_customer_research_view(report): return build_customer_research_v2(report)\n',
        'def build_customer_research_v2(report): return load_research_market_context(report)\n',
        'def load_research_market_context(report): return MODE\n',
    )
    functions = []
    for (_, relative, name), source in zip(identity._TARGETS, sources):
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        # The helper may compile this file, but must never execute its module.
        path.write_text(source + '\nraise RuntimeError("MODULE_MUST_NOT_EXECUTE")\n')
        code = next(c for c in compile(source, relative, 'exec').co_consts
                    if isinstance(c, CodeType) and c.co_name == name)
        functions.append(FunctionType(code, {'MODE': 'CURRENT'}, name))
    view, projection, reader = functions
    view.__globals__['build_customer_research_v2'] = projection
    projection.__globals__['load_research_market_context'] = reader
    monkeypatch.setattr(identity, '_ROOT', tmp_path)
    return view, projection, reader


def test_current_actual_bindings_match_without_reload_or_financial_invocation(monkeypatch):
    from services.customer_research_view import build_customer_research_view
    import importlib
    reload = Mock(side_effect=AssertionError('No reload'))
    monkeypatch.setattr(importlib, 'reload', reload)
    result = identity.research_function_body_identity(build_customer_research_view)
    assert all(result[k]['status'] == 'BODY_MATCH' for k in ('view','projection','reader'))
    assert result['data_admission'] == result['globals_defaults_helpers'] == 'NOT_ATTESTED'
    reload.assert_not_called()


def test_actual_by_value_projection_and_reader_are_followed_not_current_module_names(tmp_path, monkeypatch):
    view, projection, reader = graph(tmp_path, monkeypatch)
    assert identity.research_function_body_identity(view)['reader']['status'] == 'BODY_MATCH'
    replacement = compile('def load_research_market_context(report): return "LEGACY"', '<old-worker>', 'exec')
    stale = FunctionType(next(c for c in replacement.co_consts if isinstance(c, CodeType)), {})
    projection.__globals__['load_research_market_context'] = stale
    result = identity.research_function_body_identity(view)
    assert result['view']['status'] == result['projection']['status'] == 'BODY_MATCH'
    assert result['reader']['status'] == 'BODY_MISMATCH'
    # A stale by-value projection is inspected even if sys.modules is current.
    stale_projection = FunctionType(compile('def build_customer_research_v2(report): return {}', '', 'exec').co_consts[0], {})
    view.__globals__['build_customer_research_v2'] = stale_projection
    result = identity.research_function_body_identity(view)
    assert result['projection']['status'] == 'BODY_MISMATCH'
    assert result['reader']['status'] == 'UNAVAILABLE'


def test_equal_bodies_do_not_claim_global_or_data_coherence(tmp_path, monkeypatch):
    view, _, reader = graph(tmp_path, monkeypatch)
    reader.__globals__['MODE'] = 'LEGACY'
    result = identity.research_function_body_identity(view)
    assert result['reader']['status'] == 'BODY_MATCH'
    assert reader(None) == 'LEGACY'  # Synthetic proof of the diagnostic's limit.
    assert result['globals_defaults_helpers'] == result['data_admission'] == 'NOT_ATTESTED'


@pytest.mark.parametrize('failure', ['missing','oversize','syntax','changing'])
def test_source_failures_are_sanitized_and_cannot_change_other_bindings(tmp_path, monkeypatch, failure):
    view, _, _ = graph(tmp_path, monkeypatch)
    path = tmp_path / identity._TARGETS[0][1]
    if failure == 'missing': path.unlink()
    if failure == 'oversize': monkeypatch.setattr(identity, '_MAX_SOURCE_BYTES', 2)
    if failure == 'syntax': path.write_text('PRIVATE_SECRET_PATH = !invalid')
    if failure == 'changing':
        original = identity._read_source
        calls = []
        def changing(self):
            value = original(self)
            if self == path:
                calls.append(1)
                if len(calls) > 1: return value + b'# changed'
            return value
        monkeypatch.setattr(identity, '_read_source', changing)
    result = identity.research_function_body_identity(view)
    assert result['view'] == {'status':'UNAVAILABLE','loaded_sha256':'','disk_sha256':''}
    assert str(tmp_path) not in str(result) and 'PRIVATE' not in str(result)


def test_unsupported_callable_is_never_unwrapped_or_invoked():
    value = Mock(side_effect=AssertionError('No invocation'))
    result = identity.research_function_body_identity(value)
    assert all(result[k]['status'] == 'UNAVAILABLE' for k in ('view','projection','reader'))
    value.assert_not_called()


def test_custom_global_mapping_methods_are_never_executed(tmp_path, monkeypatch):
    view, _, _ = graph(tmp_path, monkeypatch)
    class HostileGlobals(dict):
        def get(self, *args): raise AssertionError('Custom mapping must not run')
    unexpected = FunctionType(view.__code__, HostileGlobals())
    result = identity.research_function_body_identity(unexpected)
    assert result['view']['status'] == 'BODY_MATCH'
    assert result['projection']['status'] == result['reader']['status'] == 'UNAVAILABLE'


def test_nested_code_behavior_changes_but_line_shifts_do_not_change_body_identity():
    def body(source):
        return next(c for c in compile(source, '/PRIVATE/PATH', 'exec').co_consts if isinstance(c, CodeType))
    source = 'def test():\n def inner(): return 1\n return inner()\n'
    assert identity._fingerprint(body(source)) == identity._fingerprint(body('\n# moved\n' + source))
    assert identity._fingerprint(body(source)) != identity._fingerprint(body(source.replace('return 1','return 2')))


def test_crawler_decoder_cannot_leak_arbitrary_dom_attributes(monkeypatch):
    import agents.atlas_visual_crawler_v1 as crawler
    attributes = {'data-atlas-view-status':'BODY_MISMATCH',
                  'data-atlas-view-loaded-sha256':'a'*64,
                  'data-atlas-view-disk-sha256':'/PRIVATE/CREDENTIAL',
                  'data-atlas-reader-status':'SECRET_BODY'}
    marker = SimpleNamespace(count=AsyncMock(return_value=1),
        get_attribute=AsyncMock(side_effect=lambda key: attributes.get(key)))
    marker.last = marker
    scope = SimpleNamespace(locator=lambda _: marker)
    monkeypatch.setattr(crawler, '_scopes', lambda _: [scope])
    result = asyncio.run(crawler._runtime_code_evidence(object(), 'NVDA'))
    assert result['view']['status'] == 'BODY_MISMATCH'
    assert result['view']['loaded_sha256'] == 'a'*64 and result['view']['disk_sha256'] == ''
    assert result['reader']['status'] == 'UNAVAILABLE'
    assert 'PRIVATE' not in str(result) and 'SECRET' not in str(result)


def _render_runtime_fixture(source):
    from ui.customer_research_v2 import render_customer_research_v2
    render_customer_research_v2(source, ask_cta=lambda _: None)


def test_actual_renderer_identifies_retained_reader_that_never_records_admission(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from tests.test_customer_research_v2 import report
    import ui.customer_research_v2 as renderer
    original_view = renderer.build_customer_research_view
    original_projection = original_view.__globals__['build_customer_research_v2']
    # Synthetic old reader ignores the receipt argument, reproducing the
    # observed NOT_RECORDED state without changing any real retained evidence.
    stale_code = next(c for c in compile(
        'def load_research_market_context(*args, **kwargs): return {}', '', 'exec').co_consts
        if isinstance(c, CodeType))
    projection_globals = dict(original_projection.__globals__)
    projection_globals['load_research_market_context'] = FunctionType(stale_code, {})
    projection = FunctionType(original_projection.__code__, projection_globals,
                              argdefs=original_projection.__defaults__)
    projection.__kwdefaults__ = deepcopy(original_projection.__kwdefaults__)
    view_globals = dict(original_view.__globals__)
    view_globals['build_customer_research_v2'] = projection
    view = FunctionType(original_view.__code__, view_globals, argdefs=original_view.__defaults__)
    view.__kwdefaults__ = deepcopy(original_view.__kwdefaults__)
    monkeypatch.setattr(renderer, 'build_customer_research_view', view)
    source = report()
    before = deepcopy(source)
    app = AppTest.from_function(_render_runtime_fixture, kwargs={'source':source}, default_timeout=30).run()
    assert not app.exception
    markup = '\n'.join(str(item.value) for item in app.markdown)
    assert 'data-atlas-view-status="BODY_MATCH"' in markup
    assert 'data-atlas-projection-status="BODY_MATCH"' in markup
    assert 'data-atlas-reader-status="BODY_MISMATCH"' in markup
    assert 'ADMISSION_RECEIPT_UNAVAILABLE' in markup
    assert 'data-atlas-scope="FUNCTION_BODIES_ONLY"' in markup
    assert source == before
