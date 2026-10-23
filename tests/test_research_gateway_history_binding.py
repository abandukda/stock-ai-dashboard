"""Generated candles only: exact raw bytes are not financial certification."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from services.research_history_ingestion import build_history_bundle, build_history_review_from_gateway_capture
from services.research_market_read_model import load_research_market_context
from services.operations_gateway import CAPTURE_TIME_CONTRACT
from tests.test_research_history_ingestion import fixture

NOW = datetime(2026, 10, 22, 22, 10, tzinfo=timezone.utc)
IDENTITY = dict(ticker='NVDA', source_sha='a'*40, bundle_id='MOCK_ONLY_NOT_CERTIFIED',
    captured_at=NOW, checked_at=NOW, raw_evidence_id='MOCK:CANDLES',
    adjustment_basis='SPLIT_ADJUSTED', adjustment_evidence_id='MOCK:VERIFIED_ADJUSTMENT')


def capture():
    body = json.dumps(fixture(), indent=2).encode() + b'\n'
    record = dict(ordinal=1, ticker='NVDA', endpoint='/stock/candle', parameters={'symbol':'NVDA'},
        status='PASS', status_code=200, attempt_count=1, retry_count=0, raw_complete=True,
        raw_capture='COMPLETE', raw_bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest(),
        capture_time_contract=CAPTURE_TIME_CONTRACT, capture_time_status='BOUND',
        attempt_started_at=(NOW-timedelta(seconds=1)).isoformat(), response_completed_at=NOW.isoformat())
    summary = dict(contract='ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1', source_sha='a'*40,
        scope_sha256='b'*64, status='PASS', failure_code=None, automatic_redirects=False, retry_count=0,
        provider_calls=1, max_provider_calls=1, attempted_transport_calls=1, responses_received=1,
        capture_time_contract=CAPTURE_TIME_CONTRACT, capture_time_status='BOUND',
        capture_started_at=record['attempt_started_at'], capture_completed_at=record['response_completed_at'],
        telemetry=[deepcopy(record)])
    return body, record, summary


def review(body=None, record=None, summary=None, **kwargs):
    raw, meta, run = capture()
    return build_history_review_from_gateway_capture(
        raw if body is None else body, metadata=meta if record is None else record,
        run_summary=run if summary is None else summary, scope_sha256='b'*64, **(IDENTITY|kwargs))


def test_exact_raw_hash_differs_from_normalized_hash_without_recalculating_candles():
    raw, meta, run = capture()
    before = deepcopy((meta, run, fixture()))
    result = review(raw, meta, run)
    provenance = result['bundle']['families']['historical_ohlcv']['provenance']
    assert provenance['raw_response_sha256'] == hashlib.sha256(raw).hexdigest()
    assert provenance['normalized_response_sha256'] != provenance['raw_response_sha256']
    assert provenance['raw_capture_binding'] == 'EXACT_BYTES_VERIFIED'
    assert result['bundle']['families']['historical_ohlcv']['payload']['close'] == fixture()['c']
    assert (meta, run, fixture()) == before
    assert result['status'] == 'OWNER_REVIEW_ONLY_NOT_PUBLISHED'
    assert result['provider_calls'] == result['publication_writes'] == result['report_card_writes'] == 0


def test_normalized_only_caller_never_claims_exact_raw_response_identity():
    provenance = build_history_bundle(fixture(), **IDENTITY)['families']['historical_ohlcv']['provenance']
    assert provenance['raw_response_sha256'] is None
    assert provenance['raw_capture_binding'] == 'NOT_SUPPLIED'
    assert len(provenance['normalized_response_sha256']) == 64


def test_review_wrapper_cannot_be_installed_as_admitted_read_model(tmp_path):
    result = review()
    (tmp_path/'NVDA.json').write_text(json.dumps(result))
    assert load_research_market_context('NVDA', tmp_path, now=NOW) == {}


@pytest.mark.parametrize('mutate', [
    lambda m,r: m.update(raw_complete=False, raw_capture='INCOMPLETE_SIZE_LIMIT', raw_sha256=None),
    lambda m,r: m.update(raw_sha256='c'*64),
    lambda m,r: m.update(raw_bytes=1),
    lambda m,r: m.update(ticker='MSFT'),
    lambda m,r: m.update(parameters={'symbol':'MSFT'}),
    lambda m,r: m.update(endpoint='/quote'),
    lambda m,r: m.update(status_code=302),
    lambda m,r: m.update(attempt_count=True),
    lambda m,r: r.update(source_sha='c'*40),
    lambda m,r: r.update(scope_sha256='c'*64),
    lambda m,r: r.update(status='FAIL'),
    lambda m,r: r.update(automatic_redirects=True),
    lambda m,r: r.update(retry_count=1),
    lambda m,r: r.update(max_provider_calls=0),
    lambda m,r: r.update(provider_calls=True),
    lambda m,r: r.update(attempted_transport_calls=2),
    lambda m,r: r.update(responses_received=True),
])
def test_invalid_raw_or_run_binding_fails_closed(mutate):
    raw, meta, run = capture()
    mutate(meta, run)
    # Test metadata's own gate as well as its exact run-receipt membership.
    run['telemetry'] = [deepcopy(meta)]
    with pytest.raises(ValueError):
        review(raw, meta, run)


def test_mismatched_run_telemetry_rejected_even_when_raw_hash_matches():
    raw, meta, run = capture()
    run['telemetry'][0]['ticker'] = 'MSFT'
    with pytest.raises(ValueError): review(raw, meta, run)


@pytest.mark.parametrize('raw', [b'[]', b'not JSON', b'{"s":"ok","s":"ok"}', b'{"x":NaN}'])
def test_ambiguous_or_invalid_raw_json_cannot_enter_review(raw):
    _, meta, run = capture()
    meta.update(raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
    run['telemetry'] = [deepcopy(meta)]
    with pytest.raises(ValueError): review(raw, meta, run)


def test_payload_mismatch_and_missing_adjustment_proof_remain_rejected():
    with pytest.raises(ValueError, match='RAW_CAPTURE_PAYLOAD_MISMATCH'):
        build_history_bundle(fixture(), **IDENTITY, raw_response_bytes=b'{"s":"ok"}')
    with pytest.raises(ValueError): review(adjustment_evidence_id='')


@pytest.mark.parametrize('delta', [-1, 1])
def test_same_raw_receipt_cannot_acquire_a_different_capture_time(delta):
    with pytest.raises(ValueError, match='CAPTURE_TIME_BINDING_INVALID'):
        review(captured_at=NOW+timedelta(seconds=delta), checked_at=NOW+timedelta(seconds=2))


def test_legacy_receipts_remain_unchanged_and_time_unattested():
    raw, meta, run = capture()
    for key in ('capture_time_contract', 'capture_time_status', 'attempt_started_at', 'response_completed_at'):
        meta.pop(key)
    for key in ('capture_time_contract', 'capture_time_status', 'capture_started_at', 'capture_completed_at'):
        run.pop(key)
    run['telemetry'] = [deepcopy(meta)]
    before = deepcopy((meta, run))
    with pytest.raises(ValueError, match='CAPTURE_TIME_UNATTESTED'):
        review(raw, meta, run)
    assert (meta, run) == before


@pytest.mark.parametrize('key,value', [
    ('attempt_started_at', None), ('response_completed_at', 'not-a-time'),
    ('attempt_started_at', '2026-10-22T22:09:59'),
    ('response_completed_at', '2026-10-22T23:10:00+01:00'),
    ('response_completed_at', '2026-13-22T22:10:00Z'),
    ('response_completed_at', True), ('capture_time_status', 'UNATTESTED'),
    ('capture_time_contract', 'unknown-version'),
])
def test_invalid_unbound_or_non_utc_record_times_fail_closed(key, value):
    raw, meta, run = capture()
    meta[key] = value
    run['telemetry'] = [deepcopy(meta)]
    with pytest.raises(ValueError, match='CAPTURE_TIME'):
        review(raw, meta, run)


def test_reversed_response_and_future_receipt_times_are_rejected():
    raw, meta, run = capture()
    meta['attempt_started_at'] = (NOW+timedelta(seconds=1)).isoformat()
    run['telemetry'] = [deepcopy(meta)]
    with pytest.raises(ValueError, match='CAPTURE_TIME_WINDOW_INVALID'):
        review(raw, meta, run)
    raw, meta, run = capture()
    with pytest.raises(ValueError, match='CAPTURE_TIME_WINDOW_INVALID'):
        review(raw, meta, run, checked_at=NOW-timedelta(seconds=1))


@pytest.mark.parametrize('field', ['capture_started_at', 'capture_completed_at'])
def test_summary_window_must_match_actual_request_windows(field):
    raw, meta, run = capture()
    run[field] = (NOW-timedelta(seconds=2)).isoformat()
    with pytest.raises(ValueError, match='CAPTURE_TIME_BINDING_INVALID'):
        review(raw, meta, run)


def test_sequential_transport_receipts_to_history_review_are_bound(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from scripts.run_licensed_research_gateway import run as execute
    from tests.test_licensed_research_gateway import package, StreamResponse
    raw = json.dumps(fixture()).encode()
    requests = [
        {'ordinal': 1, 'method': 'GET', 'endpoint': '/stock/candle', 'ticker': 'NVDA', 'parameters': {'symbol': 'NVDA'}},
        {'ordinal': 2, 'method': 'GET', 'endpoint': '/stock/earnings', 'ticker': 'NVDA', 'parameters': {'symbol': 'NVDA'}},
    ]
    approval, scope = package(tmp_path, requests_rows=requests)
    session = Mock()
    session.get.side_effect = [StreamResponse(chunks=(raw,)), StreamResponse(chunks=(b'[]',))]
    monkeypatch.setenv('FINNHUB_API_KEY', 'MOCK_NOT_A_CREDENTIAL')
    monkeypatch.setattr('scripts.run_licensed_research_gateway.requests.Session', lambda: session)
    monkeypatch.setattr('scripts.run_licensed_research_gateway.time.sleep', lambda _: None)
    clock = iter([NOW-timedelta(seconds=4), NOW-timedelta(seconds=3), NOW-timedelta(seconds=2), NOW])
    execute(approval_path=approval, scope_path=scope, output=tmp_path/'capture', run_id='MOCK_ONLY', clock=lambda: next(clock))
    run = json.loads((tmp_path/'capture/run_summary.json').read_text())
    meta = json.loads((tmp_path/'capture/raw/00001.metadata.json').read_text())
    result = build_history_review_from_gateway_capture(
        (tmp_path/'capture/raw/00001.json').read_bytes(), metadata=meta, run_summary=run,
        scope_sha256=run['scope_sha256'], **IDENTITY)
    provenance = result['bundle']['families']['historical_ohlcv']['provenance']
    assert result['status'] == 'OWNER_REVIEW_ONLY_NOT_PUBLISHED'
    assert result['capture_time_binding'] == 'GATEWAY_RECEIPT_BOUND_NOT_CLOCK_CERTIFICATION'
    assert provenance['capture_timestamp'] == NOW.isoformat()
    assert provenance['gateway_response_completed_at'] == (NOW-timedelta(seconds=3)).isoformat()
    assert provenance['raw_response_sha256'] == hashlib.sha256(raw).hexdigest()
    assert session.get.call_count == run['provider_calls'] == 2
    # A later ancillary response cannot hide a pre-close candle capture.
    meta['attempt_started_at'] = '2026-10-22T19:58:00+00:00'
    meta['response_completed_at'] = '2026-10-22T19:59:00+00:00'
    run['telemetry'][0] = deepcopy(meta)
    run['capture_started_at'] = meta['attempt_started_at']
    with pytest.raises(ValueError, match='CAPTURE_PRECEDES_FINALIZED_SESSION'):
        build_history_review_from_gateway_capture(raw, metadata=meta, run_summary=run,
            scope_sha256=run['scope_sha256'], **IDENTITY)


def test_overlapping_request_windows_are_not_sequential_clock_evidence():
    raw, meta, run = capture()
    extra = deepcopy(meta)
    extra.update(ordinal=2, endpoint='/stock/earnings')
    run.update(provider_calls=2, max_provider_calls=2, attempted_transport_calls=2, responses_received=2,
               telemetry=[deepcopy(meta), extra])
    with pytest.raises(ValueError, match='CAPTURE_TIME_WINDOW_INVALID'):
        review(raw, meta, run)
