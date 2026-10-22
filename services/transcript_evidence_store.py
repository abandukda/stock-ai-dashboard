"""Opt-in private transcript/derived-summary cache. No production wiring or transport.

The caller selects a private storage directory explicitly. Successful committed
records are reusable across process restarts. SQLite serializes concurrent cache
misses; a crash before commit can require another separately authorized fetch.
No exactly-once external API guarantee is claimed.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Callable

from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, GovernedRecord, MarketCoverageClass,
    ProvenanceEnvelope, UsePermission,
)
from services.transcript_provider import ConfiguredTranscriptProvider, transcript_customer_projection
from services.transcript_intelligence_runtime import (
    TRANSCRIPT_SUMMARY_PROMPT_VERSION, TRANSCRIPT_SUMMARY_SCHEMA_VERSION,
    TranscriptRuntimeResult, retrieve_and_summarize_transcript,
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _record(value: dict) -> GovernedRecord:
    p = dict(value["provenance"])
    for field, enum in (("dataset_family", DatasetFamily), ("certification_status", CertificationStatus),
                        ("display_permission", UsePermission), ("derived_use_permission", UsePermission),
                        ("market_coverage_class", MarketCoverageClass)):
        p[field] = enum(p[field])
    p["covered_venues"] = tuple(p.get("covered_venues") or ())
    return GovernedRecord(ProvenanceEnvelope(**p), value["payload"], tuple(value.get("limitations") or ()))


class TranscriptEvidenceStore:
    """Private local cache; never use an original Report Card/source-ledger path."""

    def __init__(self, root: Path, *, retention_until: datetime, clock: Callable = lambda: datetime.now(timezone.utc)):
        if retention_until.tzinfo is None:
            raise ValueError("TRANSCRIPT_RETENTION_DEADLINE_MUST_BE_AWARE")
        self.retention_until, self.clock = retention_until, clock
        self._retention()
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / "transcript_cache.sqlite3"
        self._private(self.root, directory=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        self._private(self.path)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT, identity TEXT, body TEXT, digest TEXT, PRIMARY KEY(kind,identity))")

    def _retention(self):
        now = self.clock()
        if now.tzinfo is None or now >= self.retention_until:
            raise PermissionError("TRANSCRIPT_RETENTION_EXPIRED_OR_UNVERIFIED")

    @staticmethod
    def _private(path: Path, *, directory: bool = False) -> None:
        info = path.lstat()
        if (info.st_uid != os.getuid() or info.st_mode & 0o077
                or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
            raise PermissionError("TRANSCRIPT_CACHE_PRIVATE_STORAGE_REQUIRED")

    @contextmanager
    def _connect(self):
        self._retention()
        self._private(self.root, directory=True)
        self._private(self.path)
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16 * 1024 * 1024)
            db.execute("PRAGMA journal_mode=DELETE")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _get(db, kind, identity):
        row = db.execute("SELECT body,digest FROM records WHERE kind=? AND identity=?", (kind, identity)).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise ValueError("TRANSCRIPT_CACHE_HASH_MISMATCH")
        return json.loads(row[0])

    @staticmethod
    def _put(db, kind, identity, value):
        body = _json(value)
        db.execute("INSERT INTO records VALUES (?,?,?,?)", (kind, identity, body, hashlib.sha256(body.encode()).hexdigest()))

    def run(self, symbol: str, *, year: int, quarter: int, provider: ConfiguredTranscriptProvider,
            acquisition_authorized: bool = False, summary_authorized: bool = False,
            summarizer: Callable | None = None, summary_revision: str = "") -> TranscriptRuntimeResult:
        ticker = str(symbol).upper().strip()
        if (not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", ticker) or type(year) is not int
                or type(quarter) is not int or not 1990 <= year <= 2100 or quarter not in (1, 2, 3, 4)):
            raise ValueError("TRANSCRIPT_REQUEST_IDENTITY_INVALID")
        if summarizer is not None and not summary_revision.strip():
            raise ValueError("TRANSCRIPT_SUMMARY_REVISION_REQUIRED")
        partition = provider.durable_cache_partition()
        request = _hash([partition, ticker, year, quarter])
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            stored = self._get(db, "transcript", request)
            acquired = False
            if stored is None:
                if not acquisition_authorized:
                    raise PermissionError("TRANSCRIPT_ACQUISITION_NOT_AUTHORIZED")
                evidence = provider.transcript(ticker, year=year, quarter=quarter)
                acquired = True
            else:
                evidence = _record(stored)
            raw = evidence.payload.get("raw_content")
            if isinstance(raw, str) and raw.strip():
                digest = hashlib.sha256(raw.encode()).hexdigest()
                if (digest != evidence.payload.get("raw_content_hash") or digest != evidence.provenance.content_hash
                        or evidence.provenance.symbol != ticker or evidence.provenance.provider != provider._provider
                        or evidence.provenance.license_class != provider._license.value
                        or evidence.provenance.endpoint_or_source_family != "EARNINGS_TRANSCRIPT"):
                    raise ValueError("TRANSCRIPT_CACHE_SOURCE_IDENTITY_INVALID")
                # Do not alias a requested historical quarter to a different call.
                if (evidence.payload.get("year"), evidence.payload.get("quarter")) != (year, quarter):
                    raise ValueError("TRANSCRIPT_EXACT_PERIOD_REQUIRED")
                if stored is None:
                    self._put(db, "transcript", request, evidence.as_dict())
            summary_key = _hash([request, evidence.payload.get("raw_content_hash"), summary_revision,
                                 TRANSCRIPT_SUMMARY_PROMPT_VERSION, TRANSCRIPT_SUMMARY_SCHEMA_VERSION])
            saved = self._get(db, "summary", summary_key) if summary_revision else None
            if saved:
                insight = _record(saved["insight"])
                if (insight.payload.get("source_transcript_evidence_id") != evidence.provenance.raw_evidence_id
                        or insight.provenance.license_class != evidence.provenance.license_class):
                    raise ValueError("TRANSCRIPT_SUMMARY_SOURCE_IDENTITY_INVALID")
                result = TranscriptRuntimeResult(evidence, insight, transcript_customer_projection(insight), saved["operation"])
            else:
                class RetainedProvider:
                    _provider = evidence.provenance.provider
                    def cache_partition(self): return "durable:" + request + ":" + str(evidence.payload.get("raw_content_hash"))
                    def transcript(self, *_args, **_kwargs): return evidence
                def guarded_summary(payload):
                    try:
                        generated = summarizer(payload)
                        if (not isinstance(generated, (tuple, list)) or len(generated) != 3
                                or not isinstance(generated[1], str) or not generated[1].strip()
                                or not isinstance(generated[2], str) or not generated[2].strip()):
                            raise ValueError("INVALID_SUMMARIZER_RESULT")
                        return generated
                    except Exception:
                        # Preserve committed source reuse without serializing model
                        # exception text or treating failed generation as a summary.
                        return None, "APPROVED_SUMMARIZER_ERROR", summary_revision
                result = retrieve_and_summarize_transcript(
                    ticker, year=year, quarter=quarter, provider=RetainedProvider(),
                    allow_external_ai=False,
                    summarizer=guarded_summary if summary_authorized and summarizer is not None else None,
                )
                if result.insight is not None:
                    self._put(db, "summary", summary_key, {"insight": result.insight.as_dict(), "operation": dict(result.operation_metadata)})
            metadata = {**dict(result.operation_metadata),
                        "cache_status": "DURABLE_HIT" if stored else "DURABLE_MISS",
                        "summary_cache_status": "DURABLE_HIT" if saved else "DURABLE_MISS",
                        "provider_call_count": int(acquired),
                        "provider_invocation_count": int(acquired),
                        "network_calls_instrumented": False,
                        "summary_revision": summary_revision or None,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                        "freshness_scope": "RETAINED_EXACT_QUARTER_NOT_LATEST_RELEASE_PROOF"}
            return replace(result, operation_metadata=metadata)
