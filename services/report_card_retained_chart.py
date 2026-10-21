"""Join frozen signal authority to its certified acquisition bars, without providers."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from services.report_card_chart import build_chart_projection
from services.report_card_signal_detail import _matching_authority


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _verified_json(path: Path, expected: str) -> Any:
    if file_sha(path) != expected:
        raise ValueError(f'RETAINED_CHART_FILE_HASH_MISMATCH:{path.name}')
    return json.loads(path.read_text())


def recover_chart_authority(*, signals: Sequence[Mapping[str, Any]], source: Path,
                            shards: Path, config: Mapping[str, Any]) -> tuple[list[dict], dict]:
    """Produce an ephemeral display projection; never replaces certified decisions."""
    if config.get('schema') != 'ATLAS_REPORT_CARD_RETAINED_CHART_SOURCE_V1' or not signals:
        raise ValueError('RETAINED_CHART_SOURCE_CONFIG_INVALID')
    publication = _verified_json(source / 'market_full_scan.json', config['publication_sha256'])
    manifest = _verified_json(source / 'publication_manifest.json', config['manifest_sha256'])
    identity = manifest.get('executor_candidate_identity') or {}
    if (identity.get('candidate_digest') != config['candidate_digest'] or
            identity.get('source_sha') != config['source_sha'] or
            manifest.get('publication_gate_status') != 'PASS'):
        raise ValueError('RETAINED_CHART_PUBLICATION_IDENTITY_MISMATCH')

    acquisitions = {}
    wanted = {str(signal['ticker']) for signal in signals}
    for name, hashes in config['shards'].items():
        payload = _verified_json(shards / f'{name}.json', hashes['payload_sha256'])
        checkpoint = _verified_json(shards / 'certification' / f'{name}.checkpoint.json',
                                    hashes['checkpoint_sha256'])
        if (payload.get('run_identity', {}).get('run_identity_sha256') != config['run_identity_sha256'] or
                checkpoint.get('run_identity_sha256') != config['run_identity_sha256'] or
                checkpoint.get('completion_status') != 'CERTIFIED_COMPLETE' or
                checkpoint.get('acquisition_digest') != payload.get('shard_digest')):
            raise ValueError(f'RETAINED_CHART_SHARD_IDENTITY_MISMATCH:{name}')
        for item in payload['records']:
            ticker = item.get('ticker')
            if ticker not in wanted:
                continue
            if ticker in acquisitions:
                raise ValueError(f'RETAINED_CHART_DUPLICATE_TICKER:{ticker}')
            acquisitions[ticker] = (item, hashes['payload_sha256'])

    result, facts = [], []
    for signal in signals:
        if (signal.get('candidate_digest') != config['candidate_digest'] or
                signal.get('publication_digest') != config['publication_digest']):
            raise ValueError('RETAINED_CHART_SIGNAL_COHORT_MISMATCH')
        matches = [row for row in publication if _matching_authority(signal, [row]) is not None]
        if len(matches) != 1:
            raise ValueError(f'RETAINED_CHART_EXACT_SNAPSHOT_MISSING:{signal.get("ticker")}')
        authority = matches[0]
        ticker = str(signal['ticker'])
        if authority.get('source_sha') != config['source_sha'] or ticker not in acquisitions:
            raise ValueError(f'RETAINED_CHART_ACQUISITION_MISSING:{ticker}')
        item, shard_hash = acquisitions[ticker]
        evidence_id = authority.get('historical_ohlcv_evidence_id')
        if (not evidence_id or evidence_id != (item.get('row') or {}).get('historical_ohlcv_evidence_id') or
                evidence_id not in item.get('evidence_ids', []) or
                item.get('shadow_evidence_leakage') or item.get('authority_violations')):
            raise ValueError(f'RETAINED_CHART_PRICE_LINEAGE_MISMATCH:{ticker}')
        canonical = authority.get('canonical_investment_evaluation') or {}
        technical = canonical.get('technical_confirmation') or {}
        adjustment = (technical.get('evidence') or {}).get('adjustment_mode')
        if adjustment != 'PROVIDER_ADJUSTED_COMPLETED_DAILY':
            raise ValueError(f'RETAINED_CHART_ADJUSTMENT_UNPROVEN:{ticker}')
        bars = item.get('bars') or []
        if any(bar.get('symbol') != ticker or bar.get('completed') is not True for bar in bars):
            raise ValueError(f'RETAINED_CHART_BAR_IDENTITY_MISMATCH:{ticker}')
        provenance = {
            'source': 'FINNHUB_CERTIFIED_RETAINED_ACQUISITION', 'evidence_ids': [evidence_id],
            'adjustment': 'ADJUSTED', 'original_adjustment_mode': adjustment,
            'source_run_id': config['source_run_id'], 'source_sha': config['source_sha'],
            'run_identity_sha256': config['run_identity_sha256'], 'shard_sha256': shard_hash,
            'publication_sha256': config['publication_sha256'],
        }
        chart = build_chart_projection(bars, provenance)
        certified_as_of = str(technical.get('as_of') or '')[:10]
        if chart.get('status') != 'AVAILABLE' or not certified_as_of or chart['as_of'] > certified_as_of:
            raise ValueError(f'RETAINED_CHART_VERIFIED_HISTORY_INCOMPLETE:{ticker}')
        projected = deepcopy(authority)
        projected.update(bars=deepcopy(bars), history_provenance=provenance)
        result.append(projected)
        facts.append({'ticker': ticker, 'bar_count': chart['bar_count'], 'as_of': chart['as_of'],
                      'evaluation_snapshot_id': signal['evaluation_snapshot_id'], 'evidence_id': evidence_id})
    return result, {'status': 'EXACT_RETAINED_CHART_AUTHORITY_RECOVERED', 'signals': facts,
                    'signal_count': len(result), 'provider_calls': 0, 'ledger_mutations': 0,
                    'observations_manufactured': 0, 'customer_visible': False}
