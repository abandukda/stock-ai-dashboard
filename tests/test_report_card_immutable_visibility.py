import hashlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services.report_card_dashboard import build_immutable_internal_report_card
from tests.test_internal_report_card_dashboard import ledger, NOW


def snapshot(tmp_path):
    item = ledger(tmp_path / 'synthetic-primary' / 'ledger.sqlite3')
    path = item.backup(tmp_path / 'synthetic-consolidated', now=NOW)
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), item.verify()


def test_zero_observation_immutable_source_is_visible_read_only_without_activation(tmp_path):
    path, digest, tip = snapshot(tmp_path)
    before = {p.name: p.read_bytes() for p in path.parent.iterdir()}
    result = build_immutable_internal_report_card(path, expected_sha256=digest,
                                                expected_tip=tip, authorized=True)
    assert result['signal_count'] == 2 and result['observation_count'] == 0
    assert result['source_mode'] == 'HASH_PINNED_IMMUTABLE_SNAPSHOT'
    assert result['home_performance_value'] is None
    assert result['public_performance_claims_allowed'] is result['customer_visible'] is False
    assert before == {p.name: p.read_bytes() for p in path.parent.iterdir()}
    assert not list(path.parent.glob('*-wal')) and not list(path.parent.glob('*-shm'))


def render_snapshot(path, digest, tip):
    from pathlib import Path
    from ui.internal_report_card import render_internal_report_card
    render_internal_report_card(Path(path), authorized=True, snapshot_sha256=digest, snapshot_tip=tip)


def test_actual_renderer_shows_registered_signals_and_pending_without_observations(tmp_path):
    path, digest, tip = snapshot(tmp_path)
    app = AppTest.from_function(render_snapshot, kwargs={'path':str(path), 'digest':digest, 'tip':tip}, default_timeout=30).run()
    assert not app.exception
    html = '\n'.join(str(x.value) for x in app.markdown)
    assert 'Performance is pending' in html
    assert 'Original registered signals' in html
    assert 'Public activation OFF' in html
    assert 'Reference price is not an executable entry' in html or 'reference price is not an executable entry' in html
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_unauthorized_access_does_not_touch_source(tmp_path):
    with pytest.raises(PermissionError, match='ACCESS_REQUIRED'):
        build_immutable_internal_report_card(tmp_path / 'does-not-exist', expected_sha256='',
                                            expected_tip='', authorized=False)


@pytest.mark.parametrize('mutation,error', [('digest','DIGEST_MISMATCH'), ('tip','TIP_MISMATCH'),
                                           ('wal','CONSOLIDATED_SNAPSHOT_REQUIRED')])
def test_snapshot_pins_and_consolidation_fail_closed(tmp_path, mutation, error):
    path, digest, tip = snapshot(tmp_path)
    if mutation == 'digest': digest = '0' * 64
    elif mutation == 'tip': tip = 'wrong'
    else: Path(str(path) + '-wal').write_bytes(b'synthetic-unmerged-WAL')
    with pytest.raises(ValueError, match=error):
        build_immutable_internal_report_card(path, expected_sha256=digest, expected_tip=tip, authorized=True)


def test_completed_synthetic_ledger_operations_are_final_before_delayed_gc(tmp_path):
    """A transaction context commits but does not close SQLite connections."""
    import gc
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        item = ledger(tmp_path / 'synthetic-finalized' / 'ledger.sqlite3')
        tip = item.verify()
        before = item.path.read_bytes()
        gc.collect()
        assert item.path.read_bytes() == before
        assert item.verify() == tip
        assert not Path(str(item.path)+'-wal').exists()
        assert not Path(str(item.path)+'-shm').exists()
    finally:
        if was_enabled: gc.enable()


def test_hash_valid_existing_observation_does_not_authorize_performance_visibility(tmp_path):
    from services.prospective_report_card import append_observation
    from ui.report_card_overview import overview_html
    item = ledger(tmp_path / 'synthetic-with-observation' / 'ledger.sqlite3')
    append_observation(item, signal_id='AAA', horizon=1, now=NOW, observation={
        'observed_price':110, 'observed_at':'2026-10-08T20:00:00+00:00',
        'price_source':'GOVERNED_OFFICIAL_DAILY_CLOSE', 'corporate_action_status':'NONE',
        'data_status':'AVAILABLE', 'benchmark_ticker':'SPY', 'benchmark_return':.01,
        'benchmark_observed_at':'2026-10-08T20:00:00+00:00', 'stock_return':.1,
        'excess_return':.09, 'trading_sessions':['2026-10-08']})
    path=item.backup(tmp_path / 'synthetic-observed-snapshot', now=NOW)
    before=path.read_bytes()
    report=build_immutable_internal_report_card(path,expected_sha256=hashlib.sha256(before).hexdigest(),
                                               expected_tip=item.verify(),authorized=True)
    assert report['observation_count']==1 and report['spy_comparison_count']==0
    assert report['home_performance_value'] is report['mean_return'] is report['median_return'] is None
    assert all(row['stock_return'] is row['spy_return'] is row['excess_return'] is None for row in report['rows'])
    for detail in report['signal_details']:
        assert all(row['stock_return'] is row['spy_return'] is row['excess_return'] is None for row in detail['performance'])
    assert 'performance withheld' in overview_html(report)
    assert '10.00%' not in str(report['signal_details'])
    assert path.read_bytes()==before
