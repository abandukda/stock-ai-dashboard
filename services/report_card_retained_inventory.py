"""Read-only, bounded inventory of previously acquired evidence; never certification."""
from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Mapping, Sequence

from services.buy_now_backfill_certification import combine_backfill_observations
from services.buy_now_history_backfill_execution import digest, file_sha256

CAPABILITIES = {'historical_ohlcv', 'splits', 'dividends'}
DUE_SESSIONS = ['2026-10-09', '2026-10-15']


def inventory(*, plan: Mapping, signals: Sequence[Mapping], original: Path, recovery: Path) -> dict:
    """Keep original request identities; scope only the local read-only projection.

    An available raw response remains BLOCKED pending governed certification,
    benchmark evidence, calendar/adjustment reconciliation and write approval.
    """
    requests = list(plan['requests'])
    ordinals = [r['ordinal'] for r in requests]
    if len(ordinals) != len(set(ordinals)):
        raise ValueError('RETAINED_REQUEST_ORDINAL_DUPLICATE')
    if not signals or len({s['signal_id'] for s in signals}) != len(signals):
        raise ValueError('RETAINED_SIGNAL_IDENTITY_INVALID')
    roots = (original.resolve(), recovery.resolve())
    results = {}
    for ticker in sorted({s['ticker'] for s in signals} | {'SPY'}):
        selected = [r for r in requests if r['ticker'] == ticker]
        item = {'ticker': ticker, 'status': 'MISSING_DATA', 'raw_status': 'NOT_IN_RETAINED_PLAN',
                'due_sessions': DUE_SESSIONS, 'source_files': []}
        results[ticker] = item
        if not selected:
            continue
        if len(selected) != 3 or {r['capability'] for r in selected} != CAPABILITIES:
            raise ValueError(f'RETAINED_CAPABILITY_SCOPE_INVALID:{ticker}')
        for request in selected:
            if request.get('parameters', {}).get('symbol') != ticker:
                raise ValueError(f'RETAINED_REQUEST_SYMBOL_INVALID:{ticker}')
            for root in roots:
                path = root / f"{int(request['ordinal']):05d}.json"
                if path.exists():
                    if path.is_symlink() or path.resolve().parent != root:
                        raise ValueError('RETAINED_SOURCE_PATH_INVALID')
                    item['source_files'].append({'ordinal': request['ordinal'],
                                                'sha256': file_sha256(path),
                                                'namespace': 'original' if root == roots[0] else 'recovery'})
        projection = copy.deepcopy(dict(plan))
        projection['requests'] = selected
        projection['request_keys'] = [f"{ticker}:{r['capability']}:inventory" for r in selected]
        # This projected validation is NOT the authorized full-universe plan.
        projection['plan_sha256'] = None
        try:
            rows, missing, validation = combine_backfill_observations(
                plan=projection, original_raw_dir=original, recovery_raw_dir=recovery)
            for row in rows.get(ticker, []):
                if any(not isinstance(row[k], (int, float)) or isinstance(row[k], bool)
                       or not math.isfinite(row[k]) or row[k] <= 0 for k in ('open', 'high', 'low', 'close')):
                    raise ValueError('RETAINED_PRICE_INVALID')
                if row['high'] < max(row['open'], row['close'], row['low']) or row['low'] > min(row['open'], row['close']):
                    raise ValueError('RETAINED_OHLC_INVALID')
                if not isinstance(row['volume'], (int, float)) or not math.isfinite(row['volume']) or row['volume'] < 0:
                    raise ValueError('RETAINED_VOLUME_INVALID')
            sessions = [row['session'] for row in rows.get(ticker, [])]
            available = all(s in sessions for s in DUE_SESSIONS)
            item.update(status='BLOCKED' if available else 'MISSING_DATA',
                        raw_status='VALIDATED_NOT_GOVERNED_CERTIFIED' if available else 'INCOMPLETE',
                        available_sessions=sessions, unavailable=missing.get(ticker),
                        raw_lineage_sha256=rows.get(ticker, [{}])[0].get('raw_response_sha256'),
                        validation_sha256=digest(validation))
        except (ValueError, RuntimeError, KeyError) as exc:
            item.update(status='BLOCKED', raw_status='INVALID', error=str(exc))
        for source in item['source_files']:
            root = roots[0] if source['namespace'] == 'original' else roots[1]
            if file_sha256(root / f"{source['ordinal']:05d}.json") != source['sha256']:
                raise ValueError('RETAINED_SOURCE_CHANGED')
    return {'schema': 'ATLAS_REPORT_CARD_RETAINED_INVENTORY_V1',
            'source_plan_sha256': plan.get('plan_sha256'), 'source_plan_file_digest': digest(plan),
            'signals': [{**dict(s), 'evidence': results[s['ticker']]} for s in signals],
            'benchmark': results['SPY'], 'provider_calls': 0, 'ledger_writes': 0,
            'public_activation': False, 'governed_certification': False,
            'observation_ready_count': 0, 'publication_authority': 'UNPROVEN'}
