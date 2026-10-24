"""Opt-in private F1 binding. Pins require independent review; no provisioning or writers."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Mapping

from services.report_card_dashboard import build_immutable_internal_report_card
from services.report_card_chart import normalize_price_history
from services.report_card_governance import public_report_allowed
from services.report_card_signal_detail import _matching_authority


PREFIX = 'ATLAS_REPORT_CARD_SNAPSHOT_'
MAX_CHART_BYTES = 64 * 1024 * 1024


class SnapshotBindingError(ValueError):
    """A sanitized binding failure; never includes paths, records or credentials."""


@dataclass(frozen=True)
class SnapshotBinding:
    ledger_path: Path
    ledger_sha256: str
    ledger_tip: str
    chart_path: Path
    chart_sha256: str


def snapshot_binding_from_environment(environment: Mapping[str, str]) -> SnapshotBinding | None:
    enabled = environment.get(PREFIX + 'ENABLED', '').strip().lower()
    if enabled in ('', 'false', '0', 'off', 'no'):
        return None
    if enabled not in ('true', '1', 'on', 'yes'):
        raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_ENABLE_VALUE_INVALID')
    values = {key: environment.get(PREFIX + key, '').strip()
              for key in ('PATH', 'SHA256', 'TIP', 'CHART_PATH', 'CHART_SHA256')}
    if not all(values.values()):
        raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_BINDING_INCOMPLETE')
    if any(re.fullmatch('[0-9a-f]{64}', values[key]) is None
           for key in ('SHA256', 'TIP', 'CHART_SHA256')):
        raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_PIN_FORMAT_INVALID')
    ledger, chart = Path(values['PATH']), Path(values['CHART_PATH'])
    if not ledger.is_absolute() or not chart.is_absolute() or ledger == chart:
        raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_PATHS_INVALID')
    return SnapshotBinding(ledger, values['SHA256'], values['TIP'], chart, values['CHART_SHA256'])


def _read_chart_bytes(path: Path, expected: str) -> bytes:
    # Read one bounded regular file and render those verified bytes, not a second
    # filesystem read through a legacy root or a current-working-directory fallback.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_CHART_BYTES:
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_FILE_INVALID')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_CHART_BYTES + 1)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_CHANGED')
        if len(raw) > MAX_CHART_BYTES or hashlib.sha256(raw).hexdigest() != expected:
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_HASH_MISMATCH')
        return raw
    finally:
        os.close(descriptor)


def _validate_chart_cohort(report: dict, rows: list[dict]) -> None:
    if not report['signals'] or len(rows) != len(report['signals']):
        raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_COHORT_MISMATCH')
    for signal, detail in zip(report['signals'], report['signal_details'], strict=True):
        matches = [row for row in rows if _matching_authority(signal, [row]) is not None]
        if len(matches) != 1:
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_IDENTITY_MISMATCH')
        row = matches[0]
        provenance = row.get('history_provenance') or {}
        technical = (row.get('canonical_investment_evaluation') or {}).get('technical_confirmation') or {}
        evidence_id = row.get('historical_ohlcv_evidence_id')
        if (provenance.get('source') != 'FINNHUB_CERTIFIED_RETAINED_ACQUISITION'
                or provenance.get('original_adjustment_mode') != 'PROVIDER_ADJUSTED_COMPLETED_DAILY'
                or (technical.get('evidence') or {}).get('adjustment_mode') != 'PROVIDER_ADJUSTED_COMPLETED_DAILY'
                or not isinstance(evidence_id, str) or not evidence_id
                or evidence_id not in (provenance.get('evidence_ids') or [])
                or type(provenance.get('source_run_id')) is not int or provenance['source_run_id'] <= 0
                or re.fullmatch('[0-9a-f]{40}', str(provenance.get('source_sha', ''))) is None
                or provenance.get('source_sha') != row.get('source_sha')
                or any(re.fullmatch('[0-9a-f]{64}', str(provenance.get(key, ''))) is None
                       for key in ('run_identity_sha256', 'shard_sha256', 'publication_sha256'))):
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_PROVENANCE_INVALID')
        chart = detail['price_chart']
        bars = row.get('bars') or []
        # Validate the effective rendered payload too: nested technical fields
        # must not override the independently pinned retained evidence.
        if (not isinstance(bars, list)
                or any(not isinstance(bar, dict) or bar.get('symbol') != signal['ticker']
                       or bar.get('completed') is not True for bar in bars)
                or chart.get('provenance') != provenance
                or chart.get('bars') != normalize_price_history(bars)
                or chart.get('bar_count') != len(bars)
                or row.get('spy_history')):
            # This contract carries stock-chart evidence only. A separate SPY
            # series needs its own reviewed provenance contract before binding.
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_PAYLOAD_INVALID')
        if (detail['authority_status'] != 'EXACT_CERTIFIED_MATCH'
                or chart['status'] != 'AVAILABLE'
                or chart['classification'] != 'EDUCATIONAL_NON_SCORING'
                or not technical.get('as_of')
                or chart['as_of'] > str(technical['as_of'])[:10]):
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_UNAVAILABLE')


def build_bound_snapshot_report(binding: SnapshotBinding, *, authorized: bool) -> dict:
    if not authorized:
        raise PermissionError('INTERNAL_REPORT_CARD_ACCESS_REQUIRED')
    if public_report_allowed():
        raise PermissionError('PUBLIC_REPORT_CARD_MUST_REMAIN_OFF')
    try:
        if any(os.path.lexists(str(binding.ledger_path) + suffix)
               for suffix in ('-wal', '-shm', '-journal')):
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_SIDECARS_PRESENT')
        raw = _read_chart_bytes(binding.chart_path, binding.chart_sha256)
        rows = json.loads(raw)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_FORMAT_INVALID')
        report = build_immutable_internal_report_card(
            binding.ledger_path, expected_sha256=binding.ledger_sha256,
            expected_tip=binding.ledger_tip, authorized=True, authority_rows=rows)
        _validate_chart_cohort(report, rows)
        if _read_chart_bytes(binding.chart_path, binding.chart_sha256) != raw:
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_CHART_CHANGED')
        if any(os.path.lexists(str(binding.ledger_path) + suffix)
               for suffix in ('-wal', '-shm', '-journal')):
            raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_SIDECARS_PRESENT')
        report['chart_source_sha256'] = binding.chart_sha256
        return report
    except SnapshotBindingError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
        raise SnapshotBindingError('REPORT_CARD_SNAPSHOT_EVIDENCE_REJECTED') from None
