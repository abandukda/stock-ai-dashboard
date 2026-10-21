#!/usr/bin/env python3
"""Generated-fixture infrastructure rehearsal. Never a market-data verdict."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

CLASS = 'GENERATED_FIXTURE_NOT_MARKET_EVIDENCE'
TARGET_KIB = 5 * 1024**2
HARD_BYTES = 8 * 1024**3
MAX_LINE = 256 * 1024


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def atomic(path, value):
    payload = dict(value, checksum=hashlib.sha256(canonical(value)).hexdigest())
    temp = path.with_suffix('.tmp')
    with temp.open('xb') as stream:
        stream.write(canonical(payload))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    descriptor = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def checkpoint(path, source_sha, source_hash, completed, results):
    atomic(path, dict(classification=CLASS, source_sha=source_sha, input_sha256=source_hash,
                     completed=completed, results=results))
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss >= TARGET_KIB:
        raise ValueError('RSS_TARGET_EXCEEDED_AFTER_CHECKPOINT')


def load_checkpoint(path, source_sha, source_hash):
    value = json.loads(path.read_text())
    seal = value.pop('checksum')
    if hashlib.sha256(canonical(value)).hexdigest() != seal:
        raise ValueError('CHECKPOINT_CORRUPT')
    if (value['classification'], value['source_sha'], value['input_sha256']) != (CLASS, source_sha, source_hash):
        raise ValueError('CHECKPOINT_IDENTITY_MISMATCH')
    return value


def worker(root, source_sha, selected, stop):
    source = root / 'generated.jsonl'
    source_hash = digest(source)
    cp = root / 'checkpoint.json'
    previous = load_checkpoint(cp, source_sha, source_hash) if cp.exists() else None
    results = []
    rows = 0
    with source.open('rb') as stream:
        while True:
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                raise ValueError('ROW_SIZE_LIMIT')
            row = json.loads(line)
            if row['classification'] != CLASS or row['index'] != rows:
                raise ValueError('FIXTURE_IDENTITY_INVALID')
            rows += 1
            if rows <= selected:
                # Determinism exercise only; no financial scoring is invoked.
                forward = sum(row['bars'])
                if forward != sum(reversed(row['bars'])) or len(row['bars']) != 200:
                    raise ValueError('FIXTURE_REVERSE_MISMATCH')
                results.append(hashlib.sha256(canonical([row['index'], forward])).hexdigest())
                if previous and rows == previous['completed']:
                    if results != previous['results']:
                        raise ValueError('CHECKPOINT_REPLAY_MISMATCH')
                if rows % 64 == 0 or rows == selected:
                    checkpoint(cp, source_sha, source_hash, rows, results)
                    if stop and rows == 64:
                        return dict(status='CHECKPOINTED', completed=rows)
    if rows < selected or previous and previous['completed'] > selected:
        raise ValueError('INCOMPLETE_FIXTURE')
    if digest(source) != source_hash:
        raise ValueError('SOURCE_CHANGED')
    return dict(status='PASS', source_rows=rows, selected=selected,
                result_sha256=hashlib.sha256(canonical(results)).hexdigest(),
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def safety():
    for key in ('FINNHUB_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'APP_PASSWORD',
                'ATLAS_AUDIT_PASSWORD', 'GUEST_PASSWORD', 'VIEWER_PASSWORD',
                'ATLAS_REPORT_CARD_LEDGER_PATH', 'DATA_DIR'):
        if os.environ.get(key):
            raise ValueError('PROTECTED_VARIABLE_PRESENT:' + key)
    for key, value in dict(ATLAS_QA_PROVIDER_CALLS_ALLOWED='0', ATLAS_ALLOW_EXTERNAL_AI='false',
                           ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false').items():
        if os.environ.get(key) != value:
            raise ValueError('SAFETY_FLAG_MISMATCH:' + key)
    resource.setrlimit(resource.RLIMIT_AS, (HARD_BYTES, HARD_BYTES))
    def deny_network(event, args):
        if event.startswith('socket.'):
            raise RuntimeError('NETWORK_DISABLED_IN_REHEARSAL')
    sys.addaudithook(deny_network)


def run(source_sha, source_rows=6033, selected=1298, padding=196608):
    if not (64 <= selected <= 1298 and selected <= source_rows <= 6033 and 0 <= padding <= 196608):
        raise ValueError('SCOPE_OUT_OF_BOUNDS')
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='atlas-fixture-rehearsal-', dir=os.environ['RUNNER_TEMP']) as directory:
        root = Path(directory)
        source = root / 'generated.jsonl'
        with source.open('wb') as stream:
            for index in range(source_rows):
                stream.write(canonical(dict(classification=CLASS, index=index, bars=list(range(200)),
                                            padding='x' * padding)) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        source.chmod(0o400)
        before = digest(source)
        def child(stop=False):
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', str(root),
                       '--source-sha', source_sha, '--selected', str(selected)]
            if stop:
                command.append('--stop-after-checkpoint')
            return json.loads(subprocess.check_output(command, text=True, timeout=300))
        first = child(True)
        if first != dict(status='CHECKPOINTED', completed=64):
            raise ValueError('CHECKPOINT_BOUNDARY_INVALID')
        cp = root / 'checkpoint.json'
        backup = root / 'checkpoint.fixture-backup.json'
        backup.write_bytes(cp.read_bytes())
        with backup.open('rb') as stream:
            os.fsync(stream.fileno())
        if digest(cp) != digest(backup):
            raise ValueError('BACKUP_MISMATCH')
        # Explicit corruption rejection, followed by recovery from fixture backup.
        saved = cp.read_bytes()
        cp.write_text('{}')
        try:
            load_checkpoint(cp, source_sha, before)
        except (KeyError, ValueError):
            pass
        else:
            raise ValueError('CORRUPTION_ACCEPTED')
        cp.write_bytes(saved)
        resumed = child()
        cp.unlink()
        clean = child()
        if resumed['result_sha256'] != clean['result_sha256'] or digest(source) != before:
            raise ValueError('RESTART_OR_SOURCE_INTEGRITY_FAILURE')
        receipt = dict(status='PASS', classification=CLASS, source_sha=source_sha,
                       source_sha256=before, source_bytes=source.stat().st_size,
                       source_rows=source_rows, selected_rows=selected, batch_size=64,
                       bars_per_fixture=200, restarted_processes=True,
                       checkpoint_corruption_rejected=True, fixture_backup_verified=True,
                       independent_backup_certified=False, retained_data_certified=False,
                       ledger_access=False, provider_calls=0, paid_ai_calls=0, publication=False,
                       rss_target_kib=TARGET_KIB, address_space_hard_limit_bytes=HARD_BYTES,
                       peak_rss_kib=max(resumed['peak_rss_kib'], clean['peak_rss_kib'],
                                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
                       elapsed_seconds=round(time.monotonic()-started, 3))
        if receipt['peak_rss_kib'] >= TARGET_KIB:
            raise ValueError('RSS_TARGET_EXCEEDED')
        return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--selected', type=int, default=1298)
    parser.add_argument('--stop-after-checkpoint', action='store_true')
    args = parser.parse_args()
    if len(args.source_sha) != 40 or any(c not in '0123456789abcdef' for c in args.source_sha):
        raise SystemExit('INVALID_SOURCE_SHA')
    safety()
    result = worker(args.worker, args.source_sha, args.selected, args.stop_after_checkpoint) if args.worker else run(args.source_sha)
    print(json.dumps(result, sort_keys=True))
    if not args.worker and os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write('## Generated fixture infrastructure rehearsal\n```json\n'+json.dumps(result, indent=2)+'\n```\n')
