from copy import deepcopy
from datetime import datetime, timezone

import pytest

from services.report_card_methodology_rehearsal import rehearse_signal_performance

NOW = datetime(2026, 10, 14, 21, tzinfo=timezone.utc)
SESSIONS = [{'open_at': f'2026-10-{day:02}T13:30:00Z', 'close_at': f'2026-10-{day:02}T20:00:00Z'}
            for day in (8, 9, 12, 13, 14)]


def signal(identity='early', registered='2026-10-08T12:00:00Z'):
    return {'signal_id': identity, 'ticker': 'NVDA', 'registered_at': registered,
            'published_at': registered, 'publication_verified': True,
            'reference_price': 50, 'reference_price_timestamp': '2026-10-02T20:00:00Z'}


def prices():
    out = {}
    for ticker, values in [('NVDA', [100, 110, 121, 133.1, 146.41]),
                           ('SPY', [500, 550, 605, 665.5, 732.05])]:
        out[ticker] = {f'2026-10-{day:02}': {'instrument': ticker, 'close': value,
                       'as_of': f'2026-10-{day:02}T20:00:00Z', 'currency': 'USD',
                       'price_source': 'GOVERNED_ADJUSTED_DAILY_CLOSE',
                       'adjustment_basis': 'SPLIT_DIVIDEND_ADJUSTED', 'source_id': 'synthetic-only'}
                       for day, value in zip((8, 9, 12, 13, 14), values)}
    return out


def run(signals, market=None):
    return rehearse_signal_performance(signals=signals, sessions=SESSIONS,
        prices=prices() if market is None else market, horizon=1, now=NOW)


def test_same_entry_same_exit_both_legs_gain_ten_percent_excess_is_zero():
    source = [signal()]; market = prices(); before = deepcopy((source, market))
    proposal = run(source, market); row = proposal['records'][0]
    assert row['entry_at'] == '2026-10-08T20:00:00+00:00'
    assert row['observed_at'] == '2026-10-09T20:00:00+00:00'
    assert row['stock_return'] == pytest.approx(.10)
    assert row['benchmark_return'] == pytest.approx(.10)
    assert row['excess_return'] == pytest.approx(0)
    assert row['entry_price'] == 100 and row['reference_price'] == 50
    assert proposal['append_compatible'] is proposal['activation_authorized'] is False
    assert proposal['provider_calls'] == proposal['ledger_writes'] == 0
    assert (source, market) == before


def test_independently_maturing_signals_do_not_block_each_other():
    result = run([signal(), signal('later', '2026-10-12T14:00:00Z'),
                  signal('immature', '2026-10-14T12:00:00Z')])['records']
    assert [x['status'] for x in result] == ['AVAILABLE', 'AVAILABLE', 'PENDING']
    assert result[1]['entry_at'] == '2026-10-13T20:00:00+00:00'
    assert result[1]['observed_at'] == '2026-10-14T20:00:00+00:00'
    assert result[2]['stock_return'] is result[2]['excess_return'] is None


def test_later_publication_governs_entry_and_unproven_publication_stays_pending():
    proven = signal(); proven['published_at'] = '2026-10-09T14:00:00Z'
    unknown = signal('unknown'); unknown['publication_verified'] = False
    result = run([proven, unknown])['records']
    assert result[0]['entry_at'] == '2026-10-12T20:00:00+00:00'
    assert result[1]['reason'] == 'ACTUAL_PUBLICATION_UNPROVEN'
    assert result[1]['stock_return'] is None


@pytest.mark.parametrize('value', [None, 0, -1, True, float('nan'), float('inf')])
def test_missing_or_invalid_prices_never_become_zero_returns(value):
    market = prices(); market['NVDA']['2026-10-08']['close'] = value
    row = run([signal()], market)['records'][0]
    assert row['status'] == 'UNAVAILABLE'
    assert row['stock_return'] is row['benchmark_return'] is row['excess_return'] is None


@pytest.mark.parametrize('field,value', [('currency', 'EUR'), ('adjustment_basis', 'SPLIT_ONLY'),
                                        ('price_source', 'GOVERNED_OFFICIAL_DAILY_CLOSE')])
def test_mixed_price_conventions_are_rejected(field, value):
    market = prices(); market['SPY']['2026-10-08'][field] = value
    with pytest.raises(ValueError, match='STOCK_SPY_PRICE_CONVENTION_MISMATCH'):
        run([signal()], market)


def test_wrong_timestamp_rejected_and_missing_benchmark_is_unavailable():
    market = prices(); market['NVDA']['2026-10-08']['as_of'] = '2026-10-08T19:59:00Z'
    with pytest.raises(ValueError, match='ENTRY_EXIT_TIMESTAMP_MISMATCH'):
        run([signal()], market)
    market = prices(); market.pop('SPY')
    assert run([signal()], market)['records'][0]['status'] == 'UNAVAILABLE'


def test_registered_signals_and_repeated_horizons_cannot_clear_sample_warning():
    from dataclasses import replace
    from services.report_card import internal_report, ObservationRecord
    from tests.test_beta_product_foundation import signal_payload
    from services.report_card import build_signal_record
    base = build_signal_record(signal_payload(), activation_authorized=True)
    cohort = [replace(base, signal_id=f's-{i}') for i in range(20)]
    assert internal_report([], cohort)['sample_size_warning'] == 'INSUFFICIENT_SAMPLE_FOR_CONCLUSIONS'
    observed = [ObservationRecord(cohort[0].signal_id, horizon, '2026-10-14T20:00:00Z',
                                 .1, .1, 0, 110, None, None, None, None, 'BUY_NOW', {})
                for horizon in (1,5,21,63,126,252)]
    report = internal_report(observed, cohort)
    assert report['matured_signal_count'] == 1
    assert report['matured_sample_by_horizon'] == {str(h):1 for h in (1,5,21,63,126,252)}
    assert report['sample_size_warning'] == 'INSUFFICIENT_SAMPLE_FOR_CONCLUSIONS'
    assert report['cohort_concentration_warning'] == 'SINGLE_PUBLICATION_DATE_COHORT'


def test_finite_endpoint_prices_cannot_overflow_to_available_infinite_return():
    market = prices()
    market['NVDA']['2026-10-08']['close'] = 5e-324
    market['NVDA']['2026-10-09']['close'] = 1e308
    with pytest.raises(ValueError, match='SIGNAL_PERFORMANCE_NONFINITE'):
        run([signal()], market)


def test_boolean_horizon_and_timezone_free_clock_are_not_admitted():
    with pytest.raises(ValueError, match='UNREGISTERED_REPORT_CARD_HORIZON'):
        rehearse_signal_performance(signals=[signal()], sessions=SESSIONS, prices=prices(), horizon=True, now=NOW)
    with pytest.raises(ValueError, match='REHEARSAL_NOW_TIMEZONE_REQUIRED'):
        rehearse_signal_performance(signals=[signal()], sessions=SESSIONS, prices=prices(), horizon=1,
                                    now=datetime(2026,10,14,21))


def test_proposal_is_rejected_before_any_legacy_ledger_access(tmp_path):
    from services.report_card_observation_activation import apply_observation_bundle
    class ForbiddenLedger:
        def __getattr__(self, name): raise AssertionError('No proposal may access an operational ledger')
    with pytest.raises(ValueError, match='OBSERVATION_BUNDLE_SCHEMA_INVALID'):
        apply_observation_bundle(ledger=ForbiddenLedger(), backup_root=tmp_path/'never-created',
                                 bundle=run([signal()]), now=NOW)
    assert not (tmp_path/'never-created').exists()
