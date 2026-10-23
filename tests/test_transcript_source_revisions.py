"""Generated mock calls only: explicit corrections never silently reuse old analysis."""
from dataclasses import replace
import hashlib
import json
import sqlite3

import pytest

from services.transcript_cache_reader import TranscriptCacheReadError
from services.transcript_intelligence_runtime import clear_transcript_runtime_cache
from tests.test_transcript_cache_reader import NOW, _reader, _snapshot, _store
from tests.test_transcript_evidence_store import provider, summary


@pytest.fixture(autouse=True)
def capture_clock(monkeypatch):
    monkeypatch.setattr('services.transcript_provider._now', lambda: NOW.isoformat())
    clear_transcript_runtime_cache()


def corrected_provider(calls, text):
    p = provider(calls)
    original = p.transcript
    def transcript(*args, **kwargs):
        evidence = original(*args, **kwargs)
        digest = hashlib.sha256(text.encode()).hexdigest()
        return replace(evidence, payload={**evidence.payload, 'raw_content': text,
            'raw_content_hash': digest}, provenance=replace(evidence.provenance,
            content_hash=digest, raw_evidence_id='GENERATED_MOCK_REVISION:' + digest[:24]))
    p.transcript = transcript
    return p


def exact_summary(calls, text):
    def summarize(_):
        calls.append('GENERATED_MOCK_MODEL')
        return {'management_summary': {'claim': text, 'source_excerpt': text,
            'source_excerpt_hash': hashlib.sha256(text.encode()).hexdigest(),
            'claim_type': 'PERFORMANCE'}}, 'GENERATED_MOCK_MODEL', 'review-v1'
    return summarize


def test_corrected_margin_call_invalidates_old_summary_and_preserves_all_evidence(tmp_path):
    root = tmp_path/'private'; calls, models = [], []
    store = _store(root)
    first = store.run('NVDA', year=2026, quarter=2, provider=provider(calls),
        acquisition_authorized=True, summary_authorized=True, summarizer=summary(models), summary_revision='v1')
    with sqlite3.connect(store.path) as db:
        original = db.execute("SELECT body,digest FROM records WHERE kind='transcript'").fetchone()
        original_summary = db.execute("SELECT body,digest FROM records WHERE kind='summary'").fetchone()
    corrected = 'Revenue grew 10%. Operating margin fell 2 percentage points. Earnings exceeded estimates. The share price fell 5%.'
    revised = store.run('NVDA', year=2026, quarter=2, provider=corrected_provider(calls, corrected),
        refresh_authorized=True, acquisition_authorized=True, summary_revision='v1')
    assert revised.operation_metadata['source_revision_status'] == 'UPDATED'
    assert revised.insight is None and len(models) == 1
    assert revised.transcript.provenance.raw_evidence_id != first.transcript.provenance.raw_evidence_id
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT body,digest FROM records WHERE kind='transcript'").fetchone() == original
        assert db.execute("SELECT body,digest FROM records WHERE kind='summary'").fetchone() == original_summary
        assert db.execute("SELECT count(*) FROM records WHERE kind='transcript_revision'").fetchone()[0] == 1
    before = _snapshot(root)
    result = _reader(root, summary_revision='v1').read('NVDA', year=2026, quarter=2)
    assert result['transcript_status'] == 'AVAILABLE' and result['ai_summary_status'] == 'PENDING'
    assert result['customer_projection'] == {} and _snapshot(root) == before
    # Explicitly approved new analysis must preserve the deteriorating margin
    # and the observed falling price despite an earnings beat, not infer upside.
    store.run('NVDA', year=2026, quarter=2, provider=provider(calls),
        summary_authorized=True, summarizer=exact_summary(models, corrected), summary_revision='v1')
    read = _reader(root, summary_revision='v1').read('NVDA', year=2026, quarter=2)
    assert read['customer_projection']['management_summary']['claim'] == corrected
    assert len(calls) == len(models) == 2
    assert read['provider_calls'] == read['model_calls'] == 0
    assert 'raw_content' not in str(read) and 'source_excerpt\'' not in str(read)


def test_refresh_requires_separate_explicit_acquisition_and_unchanged_check_reuses_summary(tmp_path):
    root = tmp_path/'private'; calls, models = [], []
    store = _store(root)
    first = store.run('NVDA', year=2026, quarter=2, provider=provider(calls),
        acquisition_authorized=True, summary_authorized=True, summarizer=summary(models), summary_revision='v1')
    before = _snapshot(root)
    with pytest.raises(PermissionError, match='REVISION_ACQUISITION_NOT_AUTHORIZED'):
        store.run('NVDA', year=2026, quarter=2, provider=provider(calls), refresh_authorized=True)
    assert _snapshot(root) == before and len(calls) == len(models) == 1
    checked = store.run('NVDA', year=2026, quarter=2, provider=provider(calls),
        acquisition_authorized=True, refresh_authorized=True, summary_authorized=True,
        summarizer=summary(models), summary_revision='v1')
    assert checked.operation_metadata['source_revision_status'] == 'CHECKED_UNCHANGED'
    assert checked.insight.as_dict() == first.insight.as_dict()
    assert len(calls) == 2 and len(models) == 1 and _snapshot(root) == before


def test_unavailable_check_preserves_last_verified_exact_call(tmp_path):
    root = tmp_path/'private'; calls = []; store = _store(root)
    first = store.run('NVDA', year=2026, quarter=2, provider=provider(calls), acquisition_authorized=True)
    before = _snapshot(root)
    p = provider(calls); denied = provider([], key='')
    p.transcript = denied.transcript
    checked = store.run('NVDA', year=2026, quarter=2, provider=p,
        acquisition_authorized=True, refresh_authorized=True)
    assert checked.operation_metadata['source_revision_status'] == 'CHECKED_UNAVAILABLE'
    assert checked.transcript.as_dict() == first.transcript.as_dict()
    assert _snapshot(root) == before


def test_wrong_quarter_correction_rolls_back_without_losing_prior_source(tmp_path):
    root = tmp_path/'private'; calls = []; store = _store(root)
    store.run('NVDA', year=2026, quarter=2, provider=provider(calls), acquisition_authorized=True)
    before = _snapshot(root)
    p = corrected_provider(calls, 'A corrected call.'); original = p.transcript
    def wrong(*args, **kwargs):
        e = original(*args, **kwargs)
        return replace(e, payload={**e.payload, 'quarter': 3})
    p.transcript = wrong
    with pytest.raises(ValueError, match='EXACT_PERIOD_REQUIRED'):
        store.run('NVDA', year=2026, quarter=2, provider=p,
            acquisition_authorized=True, refresh_authorized=True)
    assert _snapshot(root) == before


def test_revision_head_tampering_fails_closed_without_calls_or_writes(tmp_path):
    root = tmp_path/'private'; calls = []; store = _store(root)
    store.run('NVDA', year=2026, quarter=2, provider=provider(calls), acquisition_authorized=True)
    store.run('NVDA', year=2026, quarter=2, provider=corrected_provider(calls, 'Margin fell 2%.'),
        acquisition_authorized=True, refresh_authorized=True)
    with sqlite3.connect(store.path) as db:
        identity, body = db.execute("SELECT identity,body FROM records WHERE kind='transcript_head'").fetchone()
        body = json.loads(body); body['revision_identity'] = 'other-quarter'
        body = json.dumps(body, sort_keys=True, separators=(',', ':'))
        db.execute("UPDATE records SET body=?,digest=? WHERE kind='transcript_head' AND identity=?",
                   (body, hashlib.sha256(body.encode()).hexdigest(), identity))
    before = _snapshot(root)
    with pytest.raises(TranscriptCacheReadError, match='ACCOUNT_BINDING_REVALIDATION_REQUIRED'):
        _reader(root).read('NVDA', year=2026, quarter=2)
    with pytest.raises(ValueError, match='ACCOUNT_BINDING_REVALIDATION_REQUIRED'):
        store.run('NVDA', year=2026, quarter=2, provider=provider(calls))
    assert _snapshot(root) == before and len(calls) == 2
