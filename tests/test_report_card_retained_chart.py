from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing

import pytest

from scripts.prepare_report_card_retained_chart import prepare
from services.prospective_report_card import ProspectiveLedger
from services.report_card_retained_chart import file_sha, recover_chart_authority
from services.report_card_signal_detail import build_signal_detail


def fixture(tmp_path):
    source, shards = tmp_path / 'source', tmp_path / 'shards'
    source.mkdir(); shards.mkdir(); (shards / 'certification').mkdir()
    signal = {'ticker': 'NVDA', 'candidate_digest': 'candidate', 'publication_digest': 'publication',
              'evaluation_snapshot_id': 'snapshot', 'first_seen_at': '2026-10-08T03:20:17Z',
              'canonical_recommendation': 'BUY_NOW', 'reference_price': 102,
              'withholding_status': 'CUSTOMER_PUBLISHABLE'}
    row = {'ticker': 'NVDA', 'candidate_digest': 'candidate', 'source_sha': 'source',
           'historical_ohlcv_evidence_id': 'ohlcv:NVDA:1',
           'certified_customer_evaluation': {'digests': {'evaluation_snapshot_id': 'snapshot'}},
           'canonical_investment_evaluation': {'technical_confirmation': {
               'as_of': '2026-09-30T00:00:00Z',
               'evidence': {'adjustment_mode': 'PROVIDER_ADJUSTED_COMPLETED_DAILY'}}}}
    bars = [{'symbol': 'NVDA', 'timestamp': f'2026-09-{day:02d}T00:00:00Z',
             'close': 100 + day, 'open': 100 + day, 'high': 101 + day, 'low': 99 + day,
             'volume': 1000, 'completed': True} for day in range(1, 26)]
    payload = {'run_identity': {'run_identity_sha256': 'run'}, 'shard_digest': 'shard',
               'records': [{'ticker': 'NVDA', 'row': row, 'bars': bars,
                            'evidence_ids': ['ohlcv:NVDA:1'], 'authority_violations': 0,
                            'shadow_evidence_leakage': False}]}
    checkpoint = {'run_identity_sha256': 'run', 'completion_status': 'CERTIFIED_COMPLETE',
                  'acquisition_digest': 'shard'}
    (source / 'market_full_scan.json').write_text(json.dumps([row]))
    (source / 'publication_manifest.json').write_text(json.dumps({
        'executor_candidate_identity': {'candidate_digest': 'candidate', 'source_sha': 'source'},
        'publication_gate_status': 'PASS'}))
    (shards / 'shard-000.json').write_text(json.dumps(payload))
    (shards / 'certification/shard-000.checkpoint.json').write_text(json.dumps(checkpoint))
    config = {'schema': 'ATLAS_REPORT_CARD_RETAINED_CHART_SOURCE_V1', 'candidate_digest': 'candidate',
              'publication_digest': 'publication', 'source_sha': 'source', 'source_run_id': 1,
              'run_identity_sha256': 'run', 'publication_sha256': file_sha(source / 'market_full_scan.json'),
              'manifest_sha256': file_sha(source / 'publication_manifest.json'),
              'shards': {'shard-000': {'payload_sha256': file_sha(shards / 'shard-000.json'),
                         'checkpoint_sha256': file_sha(shards / 'certification/shard-000.checkpoint.json')}}}
    return signal, row, payload, source, shards, config


def test_exact_recovery_restores_chart_without_changing_original_decision(tmp_path):
    signal, original, payload, source, shards, config = fixture(tmp_path)
    before = deepcopy((signal, original, payload))
    rows, report = recover_chart_authority(signals=[signal], source=source, shards=shards, config=config)
    detail = build_signal_detail(signal, [], authority_rows=rows)
    assert detail['price_chart']['status'] == 'AVAILABLE'
    assert detail['price_chart']['bar_count'] == 25
    assert detail['authority_status'] == 'EXACT_CERTIFIED_MATCH'
    assert rows[0]['canonical_investment_evaluation'] == original['canonical_investment_evaluation']
    assert rows[0]['certified_customer_evaluation'] == original['certified_customer_evaluation']
    assert (signal, original, payload) == before
    assert all(x['status'] == 'PENDING' and x['stock_return'] is None for x in detail['performance'])
    assert report['provider_calls'] == report['ledger_mutations'] == report['observations_manufactured'] == 0


@pytest.mark.parametrize('name', ['publication', 'shard', 'checkpoint'])
def test_changed_retained_files_fail_hash_binding(tmp_path, name):
    signal, _, _, source, shards, config = fixture(tmp_path)
    paths = {'publication': source / 'market_full_scan.json', 'shard': shards / 'shard-000.json',
             'checkpoint': shards / 'certification/shard-000.checkpoint.json'}
    with paths[name].open('a') as stream: stream.write(' ')
    with pytest.raises(ValueError, match='FILE_HASH_MISMATCH'):
        recover_chart_authority(signals=[signal], source=source, shards=shards, config=config)


@pytest.mark.parametrize('field', ['candidate_digest', 'publication_digest', 'evaluation_snapshot_id'])
def test_another_candidate_or_snapshot_cannot_supply_chart(tmp_path, field):
    signal, _, _, source, shards, config = fixture(tmp_path)
    signal[field] = 'another'
    with pytest.raises(ValueError):
        recover_chart_authority(signals=[signal], source=source, shards=shards, config=config)


@pytest.mark.parametrize('mutation', ['price_id', 'ticker', 'completion', 'future', 'run_identity'])
def test_even_hash_bound_shards_require_matching_price_lineage(tmp_path, mutation):
    signal, _, payload, source, shards, config = fixture(tmp_path)
    item = payload['records'][0]
    if mutation == 'price_id': item['evidence_ids'] = ['another-price']
    elif mutation == 'ticker': item['bars'][0]['symbol'] = 'MSFT'
    elif mutation == 'completion': item['bars'][0]['completed'] = False
    elif mutation == 'future': item['bars'][-1]['timestamp'] = '2026-10-10T00:00:00Z'
    else: payload['run_identity']['run_identity_sha256'] = 'another-run'
    path = shards / 'shard-000.json'; path.write_text(json.dumps(payload))
    config['shards']['shard-000']['payload_sha256'] = file_sha(path)
    with pytest.raises(ValueError):
        recover_chart_authority(signals=[signal], source=source, shards=shards, config=config)


def test_materialization_reads_ledger_without_appending_any_observations(tmp_path):
    signal, _, _, source, shards, config = fixture(tmp_path)
    ledger_path = tmp_path / 'ledger.sqlite3'; ledger = ProspectiveLedger(ledger_path)
    now = datetime(2026, 10, 8, 3, 20, 17, tzinfo=timezone.utc)
    ledger.activate(activation_timestamp=now.isoformat(), now=now)
    ledger.append('SIGNAL', 'signal-1', signal, created_at=now)
    # Settle this temporary writer's WAL before measuring read-only byte identity.
    with closing(sqlite3.connect(ledger_path)) as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before = (file_sha(ledger_path), ledger_path.stat().st_mtime_ns)
    config_path = tmp_path / 'config.json'; config_path.write_text(json.dumps(config))
    report = prepare(ledger=ledger_path, source=source, shards=shards, config=config_path,
                     output=tmp_path / 'display', report_path=tmp_path / 'recovery.json')
    assert before == (file_sha(ledger_path), ledger_path.stat().st_mtime_ns)
    assert ledger.rows('OBSERVATION') == []
    assert report['ledger_before_sha256'] == report['ledger_after_sha256']
    assert json.loads((tmp_path / 'display/full_evaluation_pool.json').read_text())[0]['bars']


def test_workflow_binds_retained_source_and_keeps_chart_assertions():
    workflow = Path('.github/workflows/atlas_report_card_durable_readonly_certification.yml').read_text()
    assert 'run-id: 37553164176' in workflow
    assert 'ATLAS_REPORT_CARD_CHART_EVIDENCE_ROOT:' in workflow
    assert 'prepare_report_card_retained_chart.py' in workflow
    crawler = Path('scripts/crawl_report_card_durable_ui.py').read_text()
    assert 'await chart.wait_for(state="attached", timeout=30000)' in crawler
    for assertion in ('REPORT_CARD_CHART_NOT_AVAILABLE', 'REPORT_CARD_CHART_SCORING_ISOLATION_MISSING',
                      'REPORT_CARD_CHART_FRESHNESS_MISSING', 'REPORT_CARD_CHART_PROVENANCE_MISSING'):
        assert assertion in crawler
