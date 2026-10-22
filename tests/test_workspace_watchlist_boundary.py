"""Exercise the real app file helpers without importing app/provider startup."""
import ast
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Callable

import pandas as pd
import pytest

from services.watchlist_access import workspace_watchlist_allowed


APP = Path(__file__).parents[1] / 'app.py'
FUNCTIONS = {
    '_workspace_watchlist_access_allowed', 'read_watchlist_symbols',
    'write_watchlist_symbols', 'add_symbol_to_watchlist',
    'remove_symbol_from_watchlist', 'latest_watchlist_scan', 'safe_text', 'v8055_saved_ticker_record',
}


class UI:
    def __init__(self, state):
        self.session_state = state
        self.messages = []
    def markdown(self, text, **kwargs): self.messages.append(text)
    def info(self, text): self.messages.append(text)
    def error(self, text): self.messages.append(text)


def extracted_helpers(tmp_path, state):
    tree = ast.parse(APP.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
    assert {node.name for node in nodes} == FUNCTIONS
    ui = UI(state)
    calls = []
    def read_json(path):
        calls.append('read')
        return json.loads(path.read_text())
    def load_file(path):
        calls.append('scan')
        return pd.DataFrame([{'Ticker': 'PRIVATE_WORKSPACE_TICKER'}])
    namespace = {
        'st': ui, 're': re, 'json': json, 'pd': pd,
        'WATCHLIST_FILE': tmp_path / 'watchlist.json',
        'WATCHLIST_SCAN_FILE': tmp_path / 'watchlist_scan.json',
        'read_json_file': read_json, 'load_file': load_file,
        'load_full_scan': lambda: (_ for _ in ()).throw(AssertionError('unexpected fallback')),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP), 'exec'), namespace)
    return namespace, calls, ui


@pytest.mark.parametrize('state', [
    {}, {'authenticated': False, 'role': 'admin', 'user_role': 'admin'},
    {'authenticated': 'true', 'role': 'admin'},
    {'authenticated': True},
    {'authenticated': True, 'role': 'viewer', 'user_role': 'viewer'},
    {'authenticated': True, 'role': 'beta', 'user_id': 'another-owner'},
    {'authenticated': True, 'role': 'admin', 'user_role': 'viewer'},
    {'authenticated': True, 'role': 'admin', 'authentication_credential_role': 'viewer'},
])
def test_unverified_or_nonadmin_session_cannot_read_or_mutate_shared_storage(tmp_path, state):
    ns, calls, _ = extracted_helpers(tmp_path, state)
    path = ns['WATCHLIST_FILE']
    path.write_text('{"symbols": ["NVDA"]}')
    before = path.read_bytes()
    assert ns['read_watchlist_symbols']() == []
    assert ns['latest_watchlist_scan']().empty
    assert ns['write_watchlist_symbols'](['MSFT']) is False
    assert ns['add_symbol_to_watchlist']('MSFT') is False
    assert ns['remove_symbol_from_watchlist']('NVDA') is False
    assert calls == []
    assert path.read_bytes() == before


def test_two_shared_password_sessions_cannot_observe_or_remove_admin_watchlist(tmp_path):
    admin, _, _ = extracted_helpers(tmp_path, {'authenticated': True, 'role': 'admin', 'user_role': 'admin'})
    assert admin['write_watchlist_symbols'](['NVDA']) is True
    assert admin['add_symbol_to_watchlist']('MSFT') is True
    assert admin['read_watchlist_symbols']() == ['NVDA', 'MSFT']
    for subject in ('alice', 'bob'):
        viewer, calls, _ = extracted_helpers(tmp_path, {
            'authenticated': True, 'role': 'viewer', 'user_role': 'viewer',
            'user_id': subject, 'auth_subject': subject,
        })
        assert viewer['read_watchlist_symbols']() == []
        assert viewer['remove_symbol_from_watchlist']('NVDA') is False
        assert viewer['add_symbol_to_watchlist']('AMZN') is False
        assert calls == []
    assert admin['read_watchlist_symbols']() == ['NVDA', 'MSFT']
    assert admin['remove_symbol_from_watchlist']('NVDA') is True
    assert admin['read_watchlist_symbols']() == ['MSFT']


def test_denial_never_creates_a_shared_file(tmp_path):
    ns, calls, _ = extracted_helpers(tmp_path, {'authenticated': True, 'role': 'beta'})
    assert ns['write_watchlist_symbols'](['NVDA']) is False
    assert not ns['WATCHLIST_FILE'].exists()
    assert calls == []


def test_renderer_hides_received_private_tickers_and_edit_controls_for_viewer():
    tree = ast.parse((APP.parent / 'ui/watchlist_vnext.py').read_text())
    renderer = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'render_watchlist_vnext')
    ui = UI({'authenticated': True, 'role': 'viewer', 'user_role': 'viewer'})
    ns = {'st': ui, 'Any': Any, 'Callable': Callable, 'emit_page_interactive': lambda *args: None}
    exec(compile(ast.Module(body=[renderer], type_ignores=[]), 'watchlist_vnext.py', 'exec'), ns)
    def forbidden(*args): raise AssertionError('private callback invoked')
    ns['render_watchlist_vnext'](None, ['PRIVATE_WORKSPACE_TICKER'], open_research=forbidden,
                                add_symbol=forbidden, remove_symbol=forbidden)
    rendered = '\n'.join(ui.messages)
    assert 'watchlist-access-pending' in rendered
    assert 'PRIVATE_WORKSPACE_TICKER' not in rendered
    assert 'Shared-password sessions cannot read or edit' in rendered


def test_active_home_and_watchlist_route_bind_the_protected_helpers():
    tree = ast.parse(APP.read_text())
    homes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'v810_render_dynamic_home']
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == 'read_watchlist_symbols' for node in ast.walk(homes[-1]))
    renderers = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'render_watchlist_vnext']
    assert len(renderers) == 1
    assert isinstance(renderers[0].args[1], ast.Call)
    assert renderers[0].args[1].func.id == 'read_watchlist_symbols'
    callbacks = {item.arg: item.value.id for item in renderers[0].keywords if item.arg in {'add_symbol', 'remove_symbol'}}
    assert callbacks == {'add_symbol': 'add_symbol_to_watchlist', 'remove_symbol': 'remove_symbol_from_watchlist'}


def test_legacy_research_merge_cannot_bypass_private_scan_guard(tmp_path, monkeypatch):
    from services import exact_candidate_research
    monkeypatch.setattr(exact_candidate_research, 'exact_candidate_qa_enabled', lambda: False)
    for role in ('viewer', 'beta', 'admin'):
        ns, _, _ = extracted_helpers(tmp_path, {'authenticated': True, 'role': role, 'user_role': role})
        for name in ('TOP_IDEAS_FILE', 'FULL_SCAN_FILE', 'RECOVERY_SCAN_FILE', 'PRESCREEN_FILE', 'ETF_SCAN_FILE'):
            ns[name] = tmp_path / name
        opened = []
        def load_file(path):
            opened.append(path)
            return pd.DataFrame([{'Ticker': 'PRIVATE', 'owner_note': 'private'}]) if path == ns['WATCHLIST_SCAN_FILE'] else pd.DataFrame()
        ns['load_file'] = load_file
        ns['v8055_merge_best'] = lambda base, row: {**base, **row}
        result = ns['v8055_saved_ticker_record']('PRIVATE')
        if role == 'admin':
            assert ns['WATCHLIST_SCAN_FILE'] in opened
            assert result['owner_note'] == 'private'
        else:
            assert ns['WATCHLIST_SCAN_FILE'] not in opened
            assert result == {}
