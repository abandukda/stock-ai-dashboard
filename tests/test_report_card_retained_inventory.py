import copy
from datetime import datetime, timezone
import pytest
from services.report_card_retained_inventory import inventory
from tests.test_buy_now_backfill_certification import _plan, _write


def fixture(tmp_path):
    plan = _plan()
    plan['missing_sessions'] = ['2026-10-09', '2026-10-15']
    for r in plan['requests']:
        r['parameters'] = {'symbol': r['ticker']}
    original, recovery = tmp_path / 'original', tmp_path / 'recovery'
    original.mkdir(); recovery.mkdir()
    for r in plan['requests']:
        body = [] if r['endpoint'] != '/stock/candle' else {
            's': 'ok', 't': [int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
                             for s in plan['missing_sessions']],
            'o': [2, 2], 'h': [3, 3], 'l': [1, 1], 'c': [2, 2], 'v': [10, 10]}
        _write(original, r, body)
    return dict(plan=plan, signals=[{'signal_id': 'immutable-id', 'ticker': 'AAA'}],
                original=original, recovery=recovery)


def test_raw_available_never_certifies_or_manufactures_missing_benchmark(tmp_path):
    report = inventory(**fixture(tmp_path))
    assert report['signals'][0]['signal_id'] == 'immutable-id'
    assert report['signals'][0]['evidence']['raw_status'] == 'VALIDATED_NOT_GOVERNED_CERTIFIED'
    assert report['benchmark']['status'] == 'MISSING_DATA'
    assert report['observation_ready_count'] == report['provider_calls'] == report['ledger_writes'] == 0
    assert report['public_activation'] is False


@pytest.mark.parametrize('defect', ['body_hash', 'duplicate', 'missing_action', 'symlink'])
def test_rejects_corrupt_or_ambiguous_sources(tmp_path, defect):
    args = fixture(tmp_path)
    source = args['original'] / '00001.json'
    if defect == 'body_hash':
        import json
        e = json.loads(source.read_text()); e['body_sha256'] = '0' * 64
        source.write_text(json.dumps(e))
    elif defect == 'duplicate':
        (args['recovery'] / source.name).write_bytes(source.read_bytes())
    elif defect == 'missing_action':
        (args['original'] / '00002.json').unlink()
    else:
        target = tmp_path / 'outside.json'; source.rename(target); source.symlink_to(target)
        with pytest.raises(ValueError, match='SOURCE_PATH'):
            inventory(**args)
        return
    report = inventory(**args)
    assert report['signals'][0]['evidence']['raw_status'] == 'INVALID'
    assert report['observation_ready_count'] == 0


def test_rejects_mutated_request_symbol_and_duplicate_ordinal(tmp_path):
    args = fixture(tmp_path)
    args['plan']['requests'][0]['parameters']['symbol'] = 'OTHER'
    with pytest.raises(ValueError, match='SYMBOL_INVALID'):
        inventory(**args)
    args['plan']['requests'][0]['ordinal'] = args['plan']['requests'][1]['ordinal']
    with pytest.raises(ValueError, match='ORDINAL_DUPLICATE'):
        inventory(**args)


def test_inventory_workflow_has_no_acquisition_credentials_or_writer():
    from pathlib import Path
    import yaml
    text = Path('.github/workflows/atlas_report_card_retained_inventory.yml').read_text()
    workflow = yaml.safe_load(text)
    job = workflow['jobs']['inventory']
    assert job['environment'] == 'atlas-internal-report-card'
    assert job['runs-on'][-1] == 'atlas-worker-1'
    assert 'secrets.' not in text
    assert '12069093114/zip' in text
    assert 'sha256sum --check' in text
    assert '--ledger /mnt/atlas_report_card_primary/report-card.sqlite3' in text
    assert 'acquire_report_card_market_evidence.py' not in text
    assert 'observation_producer.py' not in text
