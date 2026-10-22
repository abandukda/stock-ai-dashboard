from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from services.transcript_cache_reader import ReadOnlyTranscriptCache, TranscriptCacheReadError
from services.transcript_evidence_store import TranscriptEvidenceStore
from services.transcript_intelligence_runtime import clear_transcript_runtime_cache
from tests.test_transcript_evidence_store import provider, summary

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)
END = datetime(2026, 12, 31, tzinfo=timezone.utc)


def _store(root):
    return TranscriptEvidenceStore(root, retention_until=END, clock=lambda: NOW)


def _reader(root, **kwargs):
    return ReadOnlyTranscriptCache(root, retention_until=kwargs.pop('retention_until', END),
        provider=kwargs.pop('provider', provider([])), clock=kwargs.pop('clock', lambda: NOW), **kwargs)


def _snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def _cache(root, *, model=False):
    calls, models = [], []
    result = _store(root).run('NVDA', year=2026, quarter=2, provider=provider(calls),
        acquisition_authorized=True, summary_authorized=model, summarizer=summary(models) if model else None,
        summary_revision='approved-model-policy-v1')
    assert len(calls) == 1 and len(models) == int(model)
    clear_transcript_runtime_cache()
    return result


def test_reader_is_read_only_across_restart_and_separates_transcript_from_summary(tmp_path, monkeypatch):
    root = tmp_path / 'private'; _cache(root)
    before = _snapshot(root)
    def forbidden(*a, **k): raise AssertionError('No provider/model call or writer constructor')
    p = provider([]); p.transcript = p.available_periods = forbidden
    monkeypatch.setattr(TranscriptEvidenceStore, '__init__', forbidden)
    reader = _reader(root, provider=p, summary_revision='approved-model-policy-v1')
    index = reader.period_index('NVDA')
    assert index['data']['periods'][0]['fiscal_year'] == 2026
    result = reader.read('NVDA', year=2026, quarter=2)
    assert result['transcript_status'] == 'AVAILABLE'
    assert result['ai_summary_status'] == 'PENDING'
    assert result['customer_projection'] == {}
    assert result['provider_calls'] == result['model_calls'] == 0
    assert _snapshot(root) == before
    assert sorted(p.name for p in root.iterdir()) == ['transcript_cache.sqlite3']
    clear_transcript_runtime_cache()
    assert _reader(root, summary_revision='approved-model-policy-v1').read('NVDA', year=2026, quarter=2) == result


def test_later_approved_cached_summary_is_reused_without_raw_source_projection(tmp_path):
    root = tmp_path / 'private'; _cache(root)
    assert _reader(root, summary_revision='approved-model-policy-v1').read('NVDA', year=2026, quarter=2)['ai_summary_status'] == 'PENDING'
    models = []
    _store(root).run('NVDA', year=2026, quarter=2, provider=provider([]),
        summary_authorized=True, summarizer=summary(models), summary_revision='approved-model-policy-v1')
    assert len(models) == 1
    before = _snapshot(root)
    result = _reader(root, summary_revision='approved-model-policy-v1').read('NVDA', year=2026, quarter=2)
    assert result['transcript_status'] == result['ai_summary_status'] == 'AVAILABLE'
    assert result['customer_projection']['management_summary']['claim'] == 'Revenue grew 10%.'
    assert 'raw_content' not in str(result) and 'source_excerpt\'' not in str(result)
    assert 'Margin pressure remains a risk.' not in str(result)
    assert 'mock-key' not in str(result)
    clear_transcript_runtime_cache()
    assert _reader(root, summary_revision='approved-model-policy-v1').read('NVDA', year=2026, quarter=2) == result
    assert _snapshot(root) == before


def test_missing_storage_does_not_create_directory_database_or_sidecars(tmp_path):
    root = tmp_path / 'does-not-exist'; reader = _reader(root)
    assert not root.exists()
    with pytest.raises(TranscriptCacheReadError, match='STORAGE_UNAVAILABLE'):
        reader.period_index('NVDA')
    assert not root.exists()
    root.mkdir(mode=0o700)
    with pytest.raises(TranscriptCacheReadError, match='STORAGE_UNAVAILABLE'):
        reader.read('NVDA', year=2026, quarter=2)
    assert not list(root.iterdir())


def test_wrong_account_license_endpoint_or_summary_revision_cannot_reuse_cache(tmp_path):
    root = tmp_path / 'private'; _cache(root, model=True)
    changed = provider([], key='other-private-account')
    changed_license = provider([], state='DEVELOPMENT_PRECOMMERCIAL')
    changed_endpoint = provider([]); changed_endpoint._base = 'https://different.example'
    for configured in (changed, changed_license, changed_endpoint):
        reader = _reader(root, provider=configured, summary_revision='approved-model-policy-v1')
        assert reader.period_index('NVDA')['data']['periods'] == []
        assert reader.read('NVDA', year=2026, quarter=2)['transcript_status'] == 'NOT_CACHED'
    result = _reader(root, summary_revision='other-model-policy').read('NVDA', year=2026, quarter=2)
    assert result['transcript_status'] == 'AVAILABLE' and result['ai_summary_status'] == 'PENDING'


def test_retention_and_private_storage_fail_before_serving(tmp_path):
    root = tmp_path / 'missing'
    with pytest.raises(TranscriptCacheReadError, match='RETENTION_EXPIRED'):
        _reader(root, retention_until=NOW)
    assert not root.exists()
    root = tmp_path / 'private'; _cache(root)
    before = _snapshot(root)
    with pytest.raises(TranscriptCacheReadError, match='RETENTION_EXPIRED'):
        _reader(root, clock=lambda: END)
    os.chmod(root, 0o755)
    with pytest.raises(TranscriptCacheReadError, match='STORAGE_UNAVAILABLE'):
        _reader(root).read('NVDA', year=2026, quarter=2)
    os.chmod(root, 0o700)
    link = tmp_path / 'linked'; link.symlink_to(root, target_is_directory=True)
    with pytest.raises(TranscriptCacheReadError, match='STORAGE_UNAVAILABLE'):
        _reader(link).period_index('NVDA')
    assert _snapshot(root) == before


def _rewrite(root, kind, transform, *, resign=False):
    from services.transcript_evidence_store import _json
    import hmac
    path = root / 'transcript_cache.sqlite3'
    with sqlite3.connect(path) as db:
        identity, body = db.execute('SELECT identity,body FROM records WHERE kind=?', (kind,)).fetchone()
        value = json.loads(body); transform(value)
        if resign:
            value.pop('_cache_auth', None)
            value['_cache_auth'] = hmac.new(provider([]).durable_cache_partition().encode(),
                _json([kind, identity, value]).encode(), hashlib.sha256).hexdigest()
        body = _json(value)
        db.execute('UPDATE records SET body=?,digest=? WHERE kind=? AND identity=?',
            (body, hashlib.sha256(body.encode()).hexdigest(), kind, identity))


@pytest.mark.parametrize('kind', ['transcript', 'summary'])
def test_unsigned_or_tampered_records_require_revalidation(tmp_path, kind):
    root = tmp_path / 'private'; _cache(root, model=True)
    _rewrite(root, kind, lambda value: value.pop('_cache_auth'))
    before = _snapshot(root)
    with pytest.raises(TranscriptCacheReadError, match='ACCOUNT_BINDING_REVALIDATION_REQUIRED'):
        _reader(root, summary_revision='approved-model-policy-v1').read('NVDA', year=2026, quarter=2)
    assert _snapshot(root) == before


@pytest.mark.parametrize('changed', ['account', 'license'])
def test_copied_rekeyed_source_cannot_cross_account_or_license(tmp_path, changed):
    from services.transcript_evidence_store import _hash
    root = tmp_path / 'private'; _cache(root)
    other = provider([], key='different-account') if changed == 'account' else provider([], state='DEVELOPMENT_PRECOMMERCIAL')
    with sqlite3.connect(root / 'transcript_cache.sqlite3') as db:
        body, digest = db.execute("SELECT body,digest FROM records WHERE kind='transcript'").fetchone()
        key = _hash([other.durable_cache_partition(), 'NVDA', 2026, 2])
        db.execute('INSERT INTO records VALUES (?,?,?,?)', ('transcript', key, body, digest))
    with pytest.raises(TranscriptCacheReadError, match='ACCOUNT_BINDING_REVALIDATION_REQUIRED'):
        _reader(root, provider=other).read('NVDA', year=2026, quarter=2)


@pytest.mark.parametrize('field,value', [('year',2025), ('quarter',1), ('resolved_period','2026-Q1')])
def test_authentic_but_wrong_period_is_rejected(tmp_path, field, value):
    root = tmp_path / 'private'; _cache(root)
    _rewrite(root, 'transcript', lambda record: record['payload'].__setitem__(field,value), resign=True)
    with pytest.raises(TranscriptCacheReadError, match='SOURCE_IDENTITY_INVALID'):
        _reader(root).read('NVDA',year=2026,quarter=2)


def test_corrupt_digest_is_rejected_without_write(tmp_path):
    root = tmp_path / 'private'; _cache(root)
    with sqlite3.connect(root / 'transcript_cache.sqlite3') as db:
        db.execute("UPDATE records SET digest='bad'")
    before = _snapshot(root)
    with pytest.raises(TranscriptCacheReadError, match='HASH_MISMATCH'):
        _reader(root).period_index('NVDA')
    assert _snapshot(root) == before


@pytest.mark.parametrize('suffix',['-journal','-wal','-shm'])
def test_existing_sidecars_are_refused_and_untouched(tmp_path,suffix):
    root = tmp_path / 'private'; _cache(root)
    (root / ('transcript_cache.sqlite3'+suffix)).write_bytes(b'owner-evidence')
    before = _snapshot(root)
    with pytest.raises(TranscriptCacheReadError,match='SIDECAR_PRESENT'):
        _reader(root).read('NVDA',year=2026,quarter=2)
    assert _snapshot(root) == before


def test_query_only_connection_refuses_writes(tmp_path):
    root = tmp_path / 'private'; _cache(root)
    before = _snapshot(root)
    with _reader(root)._connect() as db:
        with pytest.raises(sqlite3.OperationalError,match='readonly'):
            db.execute('DELETE FROM records')
    assert _snapshot(root) == before


@pytest.mark.parametrize('kind', ['transcript','summary'])
def test_modified_body_with_recomputed_digest_still_requires_private_mac(tmp_path,kind):
    root=tmp_path/'private'; _cache(root,model=True)
    def modify(value):
        record=value if kind=='transcript' else value['insight']
        record['provenance']['license_class']='DEVELOPMENT_PRECOMMERCIAL'
    _rewrite(root,kind,modify)
    with pytest.raises(TranscriptCacheReadError,match='ACCOUNT_BINDING_REVALIDATION_REQUIRED'):
        _reader(root,summary_revision='approved-model-policy-v1').read('NVDA',year=2026,quarter=2)


@pytest.mark.parametrize('field,value',[('license_class','DEVELOPMENT_PRECOMMERCIAL'),('provider','OTHER')])
def test_correctly_bound_but_inconsistent_source_is_rejected(tmp_path,field,value):
    root=tmp_path/'private'; _cache(root)
    _rewrite(root,'transcript',lambda record:record['provenance'].__setitem__(field,value),resign=True)
    with pytest.raises(TranscriptCacheReadError,match='SOURCE_IDENTITY_INVALID'):
        _reader(root).read('NVDA',year=2026,quarter=2)


def test_bound_summary_cannot_change_source_or_grounding(tmp_path):
    root=tmp_path/'private'; _cache(root,model=True)
    _rewrite(root,'summary',lambda value:value['operation'].__setitem__('grounding_status','FAIL'),resign=True)
    with pytest.raises(TranscriptCacheReadError,match='SUMMARY_IDENTITY_INVALID'):
        _reader(root,summary_revision='approved-model-policy-v1').read('NVDA',year=2026,quarter=2)


def test_retention_expiring_during_read_rejects_result(tmp_path):
    root=tmp_path/'private'; _cache(root)
    calls=[0]
    def clock():
        calls[0]+=1
        return NOW if calls[0]<5 else END
    with pytest.raises(TranscriptCacheReadError,match='RETENTION_EXPIRED'):
        _reader(root,clock=clock).read('NVDA',year=2026,quarter=2)


def test_summary_copied_to_another_account_identity_is_rejected(tmp_path):
    from services.transcript_evidence_store import _hash
    from services.transcript_intelligence_runtime import TRANSCRIPT_SUMMARY_PROMPT_VERSION, TRANSCRIPT_SUMMARY_SCHEMA_VERSION
    root=tmp_path/'private'; _cache(root,model=True)
    other=provider([],key='other-approved-account')
    _store(root).run('NVDA',year=2026,quarter=2,provider=other,acquisition_authorized=True,
                    summary_revision='approved-model-policy-v1')
    with sqlite3.connect(root/'transcript_cache.sqlite3') as db:
        body,digest=db.execute("SELECT body,digest FROM records WHERE kind='summary'").fetchone()
        source=json.loads(db.execute("SELECT body FROM records WHERE kind='transcript' LIMIT 1").fetchone()[0])
        request=_hash([other.durable_cache_partition(),'NVDA',2026,2])
        key=_hash([request,source['payload']['raw_content_hash'],'approved-model-policy-v1',
                   TRANSCRIPT_SUMMARY_PROMPT_VERSION,TRANSCRIPT_SUMMARY_SCHEMA_VERSION])
        db.execute('INSERT INTO records VALUES (?,?,?,?)',('summary',key,body,digest))
    with pytest.raises(TranscriptCacheReadError,match='ACCOUNT_BINDING_REVALIDATION_REQUIRED'):
        _reader(root,provider=other,summary_revision='approved-model-policy-v1').read('NVDA',year=2026,quarter=2)
