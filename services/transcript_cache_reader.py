"""Read approved private transcript-cache evidence without acquisition or writes.

An explicit trusted backend supplies storage, retention and account configuration.
The customer surface receives metadata and permitted derived summaries only.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Mapping

from services.transcript_evidence_store import TranscriptEvidenceStore, _authenticate, _hash, _record
from services.transcript_intelligence_runtime import (
    SUMMARY_FIELDS, TRANSCRIPT_SUMMARY_PROMPT_VERSION, TRANSCRIPT_SUMMARY_SCHEMA_VERSION,
)
from services.transcript_provider import (
    ConfiguredTranscriptProvider, TRANSCRIPT_DERIVATION_VERSION,
    transcript_customer_projection, transcript_license_permissions,
)
from services.provider_domain_contracts import UsePermission


MAX_RECORD_BYTES = 16 * 1024 * 1024


class TranscriptCacheReadError(ValueError):
    """Sanitized failure code; never include paths, credentials or source text."""


def _instant(value: Any) -> datetime:
    try:
        instant = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if instant.tzinfo is None:
            raise ValueError
        return instant.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise TranscriptCacheReadError('TRANSCRIPT_CACHE_TIMESTAMP_INVALID') from None


class ReadOnlyTranscriptCache:
    """Existing DELETE-journal cache reader; no default storage or transport.

    Standard SQLite mode=ro and a read transaction provide a consistent read;
    immutable=1 is deliberately not used with a separately approved writer.
    Existing sidecars and WAL-mode headers fail closed before SQLite opens.
    """

    def __init__(self, root: Path, *, retention_until: datetime,
                 provider: ConfiguredTranscriptProvider, summary_revision: str = '',
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._root = Path(root)
        self._path = self._root / 'transcript_cache.sqlite3'
        self._deadline = _instant(retention_until)
        self._clock = clock
        self._revision = str(summary_revision).strip()
        self._now()
        try:
            self._partition = provider.durable_cache_partition()
            self._provider = provider._provider
            self._license = provider._license.value
            self._permissions = transcript_license_permissions(self._license)
        except (ValueError, PermissionError):
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_ACCOUNT_NOT_CONFIGURED') from None

    def _now(self):
        now = _instant(self._clock())
        if now >= self._deadline:
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_RETENTION_EXPIRED')
        return now

    @staticmethod
    def _identity(ticker, year, quarter):
        ticker = str(ticker).upper().strip()
        if (not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}', ticker)
                or type(year) is not int or not 1990 <= year <= 2100
                or type(quarter) is not int or quarter not in (1, 2, 3, 4)):
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_REQUEST_IDENTITY_INVALID')
        return ticker

    @contextmanager
    def _connect(self):
        self._now()
        try:
            TranscriptEvidenceStore._private(self._root, directory=True)
            TranscriptEvidenceStore._private(self._path)
            for suffix in ('-wal', '-shm', '-journal'):
                sidecar = Path(str(self._path) + suffix)
                if sidecar.exists() or sidecar.is_symlink():
                    raise TranscriptCacheReadError('TRANSCRIPT_CACHE_WRITER_OR_SIDECAR_PRESENT')
            with self._path.open('rb') as source:
                header = source.read(100)
            if len(header) != 100 or header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
                raise TranscriptCacheReadError('TRANSCRIPT_CACHE_STORAGE_FORMAT_INVALID')
            db = sqlite3.connect(self._path.absolute().as_uri() + '?mode=ro', uri=True, timeout=2)
        except TranscriptCacheReadError:
            raise
        except (OSError, sqlite3.Error, PermissionError):
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_STORAGE_UNAVAILABLE') from None
        try:
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_RECORD_BYTES)
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            table = db.execute("SELECT type FROM sqlite_master WHERE name='records'").fetchone()
            columns = {row[1] for row in db.execute('PRAGMA table_info(records)')}
            if table != ('table',) or columns != {'kind', 'identity', 'body', 'digest'}:
                raise TranscriptCacheReadError('TRANSCRIPT_CACHE_SCHEMA_INVALID')
            yield db
            self._now()
        except sqlite3.Error:
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_READ_UNAVAILABLE') from None
        finally:
            db.close()

    def _get(self, db, kind, identity):
        row = db.execute('SELECT body,digest FROM records WHERE kind=? AND identity=?', (kind, identity)).fetchone()
        if row is None:
            return None
        body, digest = row
        if (not isinstance(body, str) or len(body.encode()) > MAX_RECORD_BYTES
                or hashlib.sha256(body.encode()).hexdigest() != digest):
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_HASH_MISMATCH')
        try:
            value = json.loads(body)
        except (ValueError, TypeError):
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_RECORD_SCHEMA_INVALID') from None
        if not isinstance(value, dict):
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_RECORD_SCHEMA_INVALID')
        try:
            return _authenticate(value, partition=self._partition, kind=kind, identity=identity)
        except ValueError:
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_ACCOUNT_BINDING_REVALIDATION_REQUIRED') from None

    def _evidence(self, db, ticker, year, quarter):
        request = _hash([self._partition, ticker, year, quarter])
        stored = self._get(db, 'transcript', request)
        if stored is None:
            return request, None
        try:
            evidence = _record(stored)
            raw = evidence.payload.get('raw_content')
            digest = hashlib.sha256(raw.encode()).hexdigest() if isinstance(raw, str) and raw.strip() else ''
            p = evidence.provenance
            period = f'{year}-Q{quarter}'
            if (not digest or digest != evidence.payload.get('raw_content_hash') or digest != p.content_hash
                    or p.symbol != ticker or p.canonical_security_id != ticker
                    or p.provider != self._provider or p.license_class != self._license
                    or p.endpoint_or_source_family != 'EARNINGS_TRANSCRIPT'
                    or p.effective_period != period or p.fiscal_period != f'Q{quarter} {year}'
                    or (evidence.payload.get('year'), evidence.payload.get('quarter')) != (year, quarter)
                    or evidence.payload.get('requested_period') != period or evidence.payload.get('resolved_period') != period
                    or p.display_permission != UsePermission.PROHIBITED
                    or p.derived_use_permission != self._permissions['derived_summary_display']
                    or _instant(p.capture_timestamp) > self._now()):
                raise TranscriptCacheReadError('TRANSCRIPT_CACHE_SOURCE_IDENTITY_INVALID')
            call = evidence.payload.get('call_date')
            if call and datetime.fromisoformat(str(call).replace('Z', '+00:00')).date() > self._now().date():
                raise TranscriptCacheReadError('TRANSCRIPT_CACHE_SOURCE_IDENTITY_INVALID')
            return request, evidence
        except TranscriptCacheReadError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError):
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_SOURCE_IDENTITY_INVALID') from None

    def period_index(self, ticker: str) -> dict[str, Any]:
        ticker = self._identity(ticker, 2000, 1)
        periods = []
        with self._connect() as db:
            # Existing V1 keys include the private namespace but do not store it
            # in a separate column. Probe the bounded444 exact keys; never scan
            # another account's source bodies or expose partition identities.
            for year in range(2100, 1989, -1):
                for quarter in (4, 3, 2, 1):
                    _, evidence = self._evidence(db, ticker, year, quarter)
                    if evidence is not None:
                        periods.append({'fiscal_year': year, 'fiscal_quarter': quarter,
                                        'call_date': evidence.payload.get('call_date'),
                                        'transcript_status': 'AVAILABLE'})
        return {'semantic_status': 'AVAILABLE' if periods else 'DATA_UNAVAILABLE',
                'data': {'periods': periods}, 'provider_calls': 0, 'model_calls': 0,
                'freshness_scope': 'RETAINED_EXACT_QUARTERS_NOT_LATEST_RELEASE_PROOF'}

    def read(self, ticker: str, *, year: int, quarter: int) -> dict[str, Any]:
        ticker = self._identity(ticker, year, quarter)
        result = {'ticker': ticker, 'year': year, 'quarter': quarter,
                  'requested_period': f'{year}-Q{quarter}', 'transcript_status': 'NOT_CACHED',
                  'ai_summary_status': 'PENDING', 'customer_projection': {},
                  'provider_calls': 0, 'model_calls': 0, 'cache_status': 'READ_ONLY_MISS',
                  'non_scoring': True, 'freshness_scope': 'RETAINED_EXACT_QUARTER_NOT_LATEST_RELEASE_PROOF'}
        with self._connect() as db:
            request, evidence = self._evidence(db, ticker, year, quarter)
            if evidence is None:
                return result
            p = evidence.provenance
            result.update(transcript_status='AVAILABLE', cache_status='READ_ONLY_HIT',
                          call_date=evidence.payload.get('call_date'), capture_timestamp=p.capture_timestamp,
                          transcript_evidence_id=p.raw_evidence_id, provider=p.provider)
            key = _hash([request, evidence.payload['raw_content_hash'], self._revision,
                         TRANSCRIPT_SUMMARY_PROMPT_VERSION, TRANSCRIPT_SUMMARY_SCHEMA_VERSION])
            saved = self._get(db, 'summary', key) if self._revision else None
            if saved is None:
                return result
            try:
                insight = _record(saved['insight'])
                payload, ip = insight.payload, insight.provenance
                derived = {key: value for key, value in payload.items() if key not in {
                    'source_transcript_evidence_id', 'model_provider', 'model_version',
                    'prompt_template_version', 'generation_timestamp', 'output_schema_version'}}
                expected = hashlib.sha256(json.dumps({'source': p.raw_evidence_id, 'output': derived,
                    'model': payload.get('model_version'), 'prompt': payload.get('prompt_template_version')},
                    sort_keys=True, default=str).encode()).hexdigest()
                operation = saved['operation']
                if (ip.provider != 'ATLAS_AI' or ip.symbol != ticker or ip.canonical_security_id != ticker
                        or ip.endpoint_or_source_family != 'TRANSCRIPT_DERIVED_INSIGHT'
                        or ip.license_class != self._license or ip.effective_period != p.effective_period
                        or ip.fiscal_period != p.fiscal_period or ip.source_timestamp != p.source_timestamp
                        or payload.get('source_transcript_evidence_id') != p.raw_evidence_id
                        or payload.get('prompt_template_version') != TRANSCRIPT_SUMMARY_PROMPT_VERSION
                        or payload.get('output_schema_version') != TRANSCRIPT_DERIVATION_VERSION
                        or payload.get('grounding_status') != 'PASS' or not payload.get('model_provider')
                        or not payload.get('model_version') or ip.content_hash != expected
                        or ip.raw_evidence_id != f'TRANSCRIPT_DERIVED:{expected[:24]}'
                        or payload.get('generation_timestamp') != ip.capture_timestamp
                        or not _instant(p.capture_timestamp) <= _instant(ip.capture_timestamp) <= self._now()
                        or operation.get('grounding_status') != 'PASS' or operation.get('ai_summary_status') != 'PASS'
                        or operation.get('transcript_evidence_id') != p.raw_evidence_id
                        or operation.get('non_scoring') is not True
                        or ip.display_permission != self._permissions['derived_summary_display']):
                    raise TranscriptCacheReadError('TRANSCRIPT_CACHE_SUMMARY_IDENTITY_INVALID')
                projection = transcript_customer_projection(insight)
                allowed = {'management_summary', *SUMMARY_FIELDS, 'grounding_status', 'model_provider',
                           'model_version', 'prompt_template_version', 'generation_timestamp',
                           'output_schema_version', 'semantic_status', 'source_evidence_ids',
                           'source_transcript_evidence_id'}
                public = {key: value for key, value in projection.items() if key in allowed}
                claim_keys = {'claim', 'claim_type', 'source_section', 'source_excerpt_hash', 'source_span_id'}
                def claim(value):
                    return {key: item for key, item in value.items()
                            if key in claim_keys and (item is None or isinstance(item, str))} if isinstance(value, Mapping) else None
                public['management_summary'] = claim(public.get('management_summary'))
                for field in SUMMARY_FIELDS:
                    public[field] = [clean for item in public.get(field, [])
                                     if (clean := claim(item)) is not None]
                result['customer_projection'] = public
                result['ai_summary_status'] = 'AVAILABLE' if projection.get('semantic_status') == 'AVAILABLE' else 'DISPLAY_NOT_PERMITTED'
            except TranscriptCacheReadError:
                raise
            except (KeyError, TypeError, ValueError, AttributeError):
                raise TranscriptCacheReadError('TRANSCRIPT_CACHE_SUMMARY_IDENTITY_INVALID') from None
        return result


__all__ = ['ReadOnlyTranscriptCache', 'TranscriptCacheReadError']
