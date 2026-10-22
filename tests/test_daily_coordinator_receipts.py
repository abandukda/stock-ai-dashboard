"""Exercise the actual CLI with disposable outputs and read-only repository inputs."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def invoke(tmp_path, *args):
    receipt = tmp_path / 'coordinator.json'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_daily_buy_now_post_close.py'),
                             '--now', '2026-10-21T22:05:00Z', '--root', str(ROOT),
                             '--output', str(receipt), *args], capture_output=True, text=True,
                            env=os.environ.copy())
    return result, json.loads(receipt.read_text())


def test_missing_boundary_saves_receipt_and_does_not_admit_downstream(tmp_path):
    result, value = invoke(tmp_path)
    assert result.returncode == 1
    assert value['error'] == 'DAILY_BUY_NOW_CONTIGUOUS_BOUNDARY_REQUIRED'
    assert value['schedule']['eligible'] is False
    assert value['provider_calls'] == value['production_writes'] == 0
    assert not (tmp_path / 'provider_free_publication_validation.json').exists()


def test_bad_boundary_saves_sanitized_fail_closed_receipt(tmp_path):
    result, value = invoke(tmp_path, '--last-contiguous-session', 'sensitive-invalid-path')
    assert result.returncode == 1
    assert value['status'] == 'FAILED'
    assert value['schedule']['eligible'] is False
    assert 'sensitive-invalid-path' not in json.dumps(value)


def test_certified_boundary_can_plan_without_changing_published_inputs(tmp_path):
    import hashlib
    names = ['market_full_scan.json', 'market_scan_state.json', 'publication_manifest.json']
    before = {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in names}
    result, value = invoke(tmp_path, '--last-contiguous-session', '2026-10-02')
    assert result.returncode == 0, result.stderr
    assert value['status'] == 'PASS'
    assert value['continuity']['missing_session_count'] == 13
    assert value['continuity']['mode'] == 'BOUNDED_BACKFILL'
    assert before == {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in names}
