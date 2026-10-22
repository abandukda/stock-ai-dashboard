"""Generated candles only: exact raw bytes are not financial certification."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from services.research_history_ingestion import build_history_bundle, build_history_review_from_gateway_capture
from services.research_market_read_model import load_research_market_context
from tests.test_research_history_ingestion import fixture

NOW = datetime(2026, 10, 22, 22, 10, tzinfo=timezone.utc)
IDENTITY = dict(ticker='NVDA', source_sha='a'*40, bundle_id='MOCK_ONLY_NOT_CERTIFIED',
    captured_at=NOW, checked_at=NOW, raw_evidence_id='MOCK:CANDLES',
    adjustment_basis='SPLIT_ADJUSTED', adjustment_evidence_id='MOCK:VERIFIED_ADJUSTMENT')


def capture():
    body = json.dumps(fixture(), indent=2).encode() + b'\n'
    record = dict(ordinal=1, ticker='NVDA', endpoint='/stock/candle', parameters={'symbol':'NVDA'},
        status='PASS', status_code=200, attempt_count=1, retry_count=0, raw_complete=True,
        raw_capture='COMPLETE', raw_bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest())
    summary = dict(contract='ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1', source_sha='a'*40,
        scope_sha256='b'*64, status='PASS', failure_code=None, automatic_redirects=False, retry_count=0,
        provider_calls=1, max_provider_calls=1, attempted_transport_calls=1, responses_received=1,
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
