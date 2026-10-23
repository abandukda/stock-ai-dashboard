"""Inert V2 signal-performance proposal; never a ledger append bundle.

Owner methodology approval is required before any writer can consume this
proposal. Reference prices remain original evidence, never executable entries.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

from services.prospective_report_card import _finite_observation_number, _utc, _digest
from services.report_card import HORIZONS
from services.report_card_observation_activation import ALLOWED_PRICE_SOURCES

METHODOLOGY = 'ATLAS_FIRST_FULL_SESSION_CLOSE_SIGNAL_PERFORMANCE_V2_PROPOSAL'


def rehearse_signal_performance(*, signals: Sequence[Mapping[str, Any]],
                                sessions: Sequence[Mapping[str, Any]],
                                prices: Mapping[str, Mapping[str, Mapping[str, Any]]],
                                horizon: int, now: datetime) -> dict[str, Any]:
    """Independently plan each signal using aligned stock/SPY entry/exit closes.

    Calendar sessions must be complete from before registration through now.
    The first session whose OPEN is after both actual registration and proven
    publication supplies entry CLOSE. Horizon N ends N sessions after entry.
    Missing prices never become zero returns or forward-filled observations.
    """
    if type(horizon) is not int or horizon not in HORIZONS:
        raise ValueError('UNREGISTERED_REPORT_CARD_HORIZON')
    current = _utc(now, 'REHEARSAL_NOW')
    finalized = []
    last_close = None
    for session in sessions:
        opened = _utc(session.get('open_at'), 'SESSION_OPEN')
        closed = _utc(session.get('close_at'), 'SESSION_CLOSE')
        if closed <= opened or (last_close is not None and opened <= last_close):
            raise ValueError('TRADING_SESSION_SEQUENCE_INVALID')
        last_close = closed
        if closed <= current:
            finalized.append((opened, closed))
    ids = [str(s.get('signal_id') or '') for s in signals]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError('SIGNAL_IDENTITY_INVALID')
    results = []
    for signal in signals:
        item = {'signal_id': signal['signal_id'], 'ticker': str(signal.get('ticker') or '').upper(),
                'status': 'PENDING', 'stock_return': None, 'benchmark_return': None,
                'excess_return': None, 'reference_price': signal.get('reference_price'),
                'reference_price_role': 'ORIGINAL_SIGNAL_EVIDENCE_NOT_ENTRY',
                'reference_price_timestamp': signal.get('reference_price_timestamp')}
        if signal.get('publication_verified') is not True:
            item.update(reason='ACTUAL_PUBLICATION_UNPROVEN')
            results.append(item)
            continue
        registered = _utc(signal.get('registered_at'), 'ACTUAL_REGISTRATION')
        published = _utc(signal.get('published_at'), 'ACTUAL_PUBLICATION')
        anchor = max(registered, published)
        eligible = [(opened, closed) for opened, closed in finalized if opened > anchor]
        if len(eligible) <= horizon:
            item.update(reason='ENTRY_OR_HORIZON_IMMATURE')
            results.append(item)
            continue
        entry, exit = eligible[0][1], eligible[horizon][1]
        item.update(entry_at=entry.isoformat(), observed_at=exit.isoformat())
        selected = []
        for ticker in (item['ticker'], 'SPY'):
            for at in (entry, exit):
                price = prices.get(ticker, {}).get(at.date().isoformat())
                if (not isinstance(price, Mapping) or price.get('instrument') != ticker
                        or price.get('price_source') not in ALLOWED_PRICE_SOURCES
                        or not price.get('source_id') or not price.get('currency')
                        or not price.get('adjustment_basis')
                        or _finite_observation_number(price.get('close'), positive=True) is None):
                    selected = []
                    break
                if _utc(price.get('as_of'), 'PRICE_AS_OF') != at:
                    raise ValueError('ENTRY_EXIT_TIMESTAMP_MISMATCH')
                selected.append(price)
            if not selected:
                break
        if len(selected) != 4:
            item.update(status='UNAVAILABLE', reason='ALIGNED_ENTRY_EXIT_EVIDENCE_MISSING')
        elif (len({p['currency'] for p in selected}) != 1
              or len({p['adjustment_basis'] for p in selected}) != 1
              or len({p['price_source'] for p in selected}) != 1):
            raise ValueError('STOCK_SPY_PRICE_CONVENTION_MISMATCH')
        else:
            stock_entry, stock_exit, spy_entry, spy_exit = [float(p['close']) for p in selected]
            stock_return = stock_exit / stock_entry - 1
            spy_return = spy_exit / spy_entry - 1
            if not all(math.isfinite(value) for value in (stock_return, spy_return, stock_return - spy_return)):
                raise ValueError('SIGNAL_PERFORMANCE_NONFINITE')
            item.update(status='AVAILABLE', stock_return=stock_return, benchmark_return=spy_return,
                        excess_return=stock_return - spy_return,
                        entry_price=stock_entry, benchmark_entry_price=spy_entry,
                        evidence_sha256=_digest(selected), reason='PROPOSAL_REHEARSAL_ONLY')
        results.append(item)
    return {'methodology': METHODOLOGY, 'horizon': horizon, 'records': results,
            'activation_authorized': False, 'append_compatible': False,
            'customer_visible': False, 'public_performance_claims_allowed': False,
            'provider_calls': 0, 'ledger_writes': 0,
            'performance_kind': 'SIGNAL_CLOSE_TO_CLOSE_NOT_BUY_RANGE_FILL_OR_PORTFOLIO',
            'calendar_completeness': 'REQUIRES_SEPARATE_CERTIFICATION'}
