"""Synthetic contract tests only: no original records or production acceptance."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import socket

import pytest
from streamlit.testing.v1 import AppTest

from services import report_card_snapshot_binding as binding
from services.prospective_report_card import ProspectiveLedger
from tests.test_internal_report_card_dashboard import NOW
from tests.test_report_card_retained_chart import fixture


def synthetic_binding(tmp_path):
    signal, row, payload, *_ = fixture(tmp_path)
    signal['signal_id'] = 'SYNTHETIC-ONLY'
    item = ProspectiveLedger(tmp_path / 'primary' / 'synthetic.sqlite3')
    item.activate(activation_timestamp=NOW.isoformat(), now=NOW)
    item.append('SIGNAL', 'SYNTHETIC-ONLY', signal, created_at=NOW)
    path = item.backup(tmp_path / 'snapshot', now=NOW)
    row['source_sha'] = 'a' * 40
    row['bars'] = payload['records'][0]['bars']
    row['history_provenance'] = {
        'source': 'FINNHUB_CERTIFIED_RETAINED_ACQUISITION',
        'original_adjustment_mode': 'PROVIDER_ADJUSTED_COMPLETED_DAILY',
        'adjustment': 'ADJUSTED', 'evidence_ids': ['ohlcv:NVDA:1'],
        'source_run_id': 1, 'source_sha': 'a' * 40,
        'run_identity_sha256': 'b' * 64, 'shard_sha256': 'c' * 64,
        'publication_sha256': 'd' * 64,
    }
    chart = tmp_path / 'snapshot' / 'synthetic-chart.json'
    chart.write_text(json.dumps([row]))
    return binding.SnapshotBinding(path, hashlib.sha256(path.read_bytes()).hexdigest(),
        item.verify(), chart, hashlib.sha256(chart.read_bytes()).hexdigest())


def environment(value):
    return {binding.PREFIX + key: str(item) for key, item in {
        'ENABLED': 'true', 'PATH': value.ledger_path, 'SHA256': value.ledger_sha256,
        'TIP': value.ledger_tip, 'CHART_PATH': value.chart_path,
        'CHART_SHA256': value.chart_sha256}.items()}


@pytest.mark.parametrize('flag', ['', 'false', '0', 'off', 'no'])
def test_default_off_ignores_unbound_pins(flag):
    assert binding.snapshot_binding_from_environment({binding.PREFIX+'ENABLED': flag,
        binding.PREFIX+'PATH': '/not/a/source'}) is None


@pytest.mark.parametrize('key', ['PATH', 'SHA256', 'TIP', 'CHART_PATH', 'CHART_SHA256'])
def test_enabled_requires_every_pin(tmp_path, key):
    env = environment(synthetic_binding(tmp_path))
    del env[binding.PREFIX + key]
    with pytest.raises(binding.SnapshotBindingError):
        binding.snapshot_binding_from_environment(env)


@pytest.mark.parametrize('key,value', [('ENABLED','maybe'), ('SHA256','bad'), ('TIP','bad'),
    ('CHART_SHA256','bad'), ('PATH','relative'), ('CHART_PATH','relative')])
def test_invalid_binding_rejected(tmp_path, key, value):
    env = environment(synthetic_binding(tmp_path)); env[binding.PREFIX+key] = value
    with pytest.raises(binding.SnapshotBindingError):
        binding.snapshot_binding_from_environment(env)


def test_pinned_chart_and_ledger_read_without_network_or_mutation(tmp_path, monkeypatch):
    value = synthetic_binding(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('Network, writer or legacy authority fallback invoked')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(ProspectiveLedger, 'append', forbidden)
    monkeypatch.setattr(ProspectiveLedger, 'activate', forbidden)
    monkeypatch.setattr('services.report_card_dashboard.load_certified_authority', forbidden)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in value.ledger_path.parent.iterdir()}
    result = binding.build_bound_snapshot_report(value, authorized=True)
    assert result['signal_count'] == 1
    assert result['signals'][0]['signal_id'] == 'SYNTHETIC-ONLY'
    assert result['signal_details'][0]['price_chart']['bar_count'] == 25
    assert result['performance_policy'] == 'VISIBILITY_ONLY_NO_RETURN_AUTHORITY'
    assert result['home_performance_value'] is None
    assert result['customer_visible'] is False
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in value.ledger_path.parent.iterdir()}


@pytest.mark.parametrize('field', ['ledger_sha256', 'ledger_tip', 'chart_sha256'])
def test_wrong_pins_rejected(tmp_path, field):
    value = replace(synthetic_binding(tmp_path), **{field:'0'*64})
    with pytest.raises(binding.SnapshotBindingError):
        binding.build_bound_snapshot_report(value, authorized=True)


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_even_empty_sidecars_rejected(tmp_path, suffix):
    value = synthetic_binding(tmp_path)
    Path(str(value.ledger_path)+suffix).touch()
    with pytest.raises(binding.SnapshotBindingError):
        binding.build_bound_snapshot_report(value, authorized=True)


@pytest.mark.parametrize('mutation', ['ticker','candidate','snapshot','duplicate','provenance','bar',
    'nested_override','spy','future','empty','json'])
def test_repinned_unverified_chart_rejected(tmp_path, mutation):
    value = synthetic_binding(tmp_path)
    rows = json.loads(value.chart_path.read_text()); row = rows[0]
    if mutation == 'ticker': row['ticker'] = 'OTHER'
    elif mutation == 'candidate': row['candidate_digest'] = 'OTHER'
    elif mutation == 'snapshot': row['certified_customer_evaluation']['digests']['evaluation_snapshot_id'] = 'OTHER'
    elif mutation == 'duplicate': rows.append(deepcopy(row))
    elif mutation == 'provenance': del row['history_provenance']['shard_sha256']
    elif mutation == 'bar': row['bars'][0]['completed'] = False
    elif mutation == 'nested_override':
        row['canonical_investment_evaluation']['technical'] = {'history':deepcopy(row['bars'])}
        row['canonical_investment_evaluation']['technical']['history'][0]['close'] += .5
    elif mutation == 'spy': row['spy_history'] = deepcopy(row['bars'])
    elif mutation == 'future': row['bars'][-1]['timestamp'] = '2026-10-20'
    elif mutation == 'empty': rows = []
    value.chart_path.write_text('not json' if mutation == 'json' else json.dumps(rows))
    value = replace(value, chart_sha256=hashlib.sha256(value.chart_path.read_bytes()).hexdigest())
    with pytest.raises(binding.SnapshotBindingError):
        binding.build_bound_snapshot_report(value, authorized=True)


@pytest.mark.parametrize('field', ['ledger_path', 'chart_path'])
def test_symlinks_rejected(tmp_path, field):
    value = synthetic_binding(tmp_path); link = tmp_path / 'link'
    link.symlink_to(getattr(value, field))
    with pytest.raises(binding.SnapshotBindingError):
        binding.build_bound_snapshot_report(replace(value, **{field:link}), authorized=True)


def route(authorized=True):
    from ui.internal_report_card import render_internal_report_card_route
    render_internal_report_card_route('/must-not-fallback', authorized=authorized)


def test_admin_route_renders_verified_snapshot(tmp_path, monkeypatch):
    for key, value in environment(synthetic_binding(tmp_path)).items(): monkeypatch.setenv(key, value)
    app = AppTest.from_function(route, default_timeout=30).run()
    assert not app.exception and not app.error
    assert 'Performance is pending' in '\n'.join(str(x.value) for x in app.markdown)


def test_invalid_enabled_route_does_not_fallback_or_leak(tmp_path, monkeypatch):
    from ui import internal_report_card as ui
    value = synthetic_binding(tmp_path)
    for key, item in environment(replace(value, ledger_sha256='0'*64)).items(): monkeypatch.setenv(key, item)
    monkeypatch.setattr(ui, 'render_internal_report_card', lambda *a, **k: pytest.fail('legacy fallback'))
    app = AppTest.from_function(route, default_timeout=30).run()
    assert not app.exception and len(app.error) == 1
    assert str(tmp_path) not in app.error[0].value
    assert 'SYNTHETIC-ONLY' not in '\n'.join(str(x.value) for x in app.markdown)


def test_viewer_and_public_guard_precede_any_file_read(tmp_path, monkeypatch):
    from ui.internal_report_card import render_internal_report_card_route
    value = synthetic_binding(tmp_path)
    monkeypatch.setattr(binding, '_read_chart_bytes', lambda *a: pytest.fail('unauthorized read'))
    with pytest.raises(PermissionError): binding.build_bound_snapshot_report(value, authorized=False)
    with pytest.raises(PermissionError): render_internal_report_card_route(None, authorized=False)
    monkeypatch.setattr(binding, 'public_report_allowed', lambda: True)
    monkeypatch.setattr('services.report_card_governance.public_report_allowed', lambda: True)
    with pytest.raises(PermissionError): binding.build_bound_snapshot_report(value, authorized=True)
    with pytest.raises(PermissionError): render_internal_report_card_route(None, authorized=True)


def test_chart_fifo_rejected_without_blocking(tmp_path):
    import os
    value = synthetic_binding(tmp_path)
    fifo = tmp_path / 'fifo'
    os.mkfifo(fifo)
    with pytest.raises(binding.SnapshotBindingError):
        binding.build_bound_snapshot_report(replace(value, chart_path=fifo), authorized=True)


def test_dangling_sidecar_rejected(tmp_path):
    value = synthetic_binding(tmp_path)
    Path(str(value.ledger_path) + '-wal').symlink_to(tmp_path / 'absent')
    with pytest.raises(binding.SnapshotBindingError):
        binding.build_bound_snapshot_report(value, authorized=True)
