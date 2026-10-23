"""Retained daily planning must share customer admission and preserve inputs."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from services.daily_buy_now_post_close import validate_retained_publication
from services.runtime_projection_contract import build_runtime_projection_contract, semantic_digest
from services.runtime_projection_loader import (
    load_exact_customer_inventory_with_status, validate_customer_inventory_payload,
)

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('market_full_scan.json', 'market_scan_state.json', 'publication_manifest.json')
PILLARS = ('valuation_quality', 'fundamental_quality', 'technical_quality',
           'risk_quality', 'entry_quality', 'volume_quality')


def fixture(root, *, runtime=False, mutation=None):
    evaluation = {'ticker': 'NVDA', 'guidance': {'state': 'BUY_NOW'},
                  'methodology_version': 'generated-method', 'decision_digest': 'generated-decision',
                  **{name: {'score': 50.0} for name in PILLARS}}
    rows = [{'ticker': 'NVDA', 'canonical_investment_evaluation': evaluation,
             'publication_certification': {'customer_publication_allowed': True}}]
    if mutation:
        mutation(rows)
    manifest = {'publication_gate_status': 'PASS', 'report_card_prospective_active': False,
                'executor_candidate_digest_verified': True, 'source_commit_sha': 'a' * 40,
                'executor_candidate_identity': {'candidate_digest': 'b' * 64},
                'artifact_hashes': {'market_full_scan.json': semantic_digest(rows)}}
    if runtime:
        manifest['runtime_projection_contract'] = build_runtime_projection_contract(
            manifest=manifest, artifacts={'market_full_scan.json': rows},
            candidate_digest='b' * 64, publication_digest='c' * 64, source_sha='a' * 40,
            evidence_snapshot_at='2026-10-02T20:30:00Z', source_counts={}, expected_facts={},
            required_tickers=['NVDA'], source_inventory={},
        )
    root.mkdir(parents=True, exist_ok=True)
    (root / NAMES[0]).write_text(json.dumps(rows))
    (root / NAMES[1]).write_text(json.dumps({'status': 'COMPLETE'}))
    (root / NAMES[2]).write_text(json.dumps(manifest))
    return rows, manifest


def hashes(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in NAMES}


@pytest.mark.parametrize('runtime', [False, True])
def test_valid_customer_contract_and_daily_receipt_agree_without_source_mutation(tmp_path, runtime):
    rows, manifest = fixture(tmp_path, runtime=runtime)
    before = hashes(tmp_path)
    assert validate_customer_inventory_payload(rows, manifest, artifact_name=NAMES[0]) == (True, ())
    assert load_exact_customer_inventory_with_status(tmp_path / NAMES[0], manifest) == (rows, True, ())
    output = tmp_path / 'audit_results/daily/result.json'
    value = validate_retained_publication(root=tmp_path, output=output)
    assert value['publication_gate_status'] == 'PASS'
    assert value['provider_calls'] == value['production_writes'] == 0
    assert value['retained_customer_allowed_count'] == 1
    assert hashes(tmp_path) == before
    assert json.loads(output.read_text()) == value


@pytest.mark.parametrize('runtime', [False, True])
@pytest.mark.parametrize('damage', ['tampered_rows', 'missing_hash', 'wrong_hash'])
def test_daily_rejects_same_unbound_inventory_as_customer_loader(tmp_path, runtime, damage):
    rows, manifest = fixture(tmp_path, runtime=runtime)
    if damage == 'tampered_rows':
        rows[0]['canonical_investment_evaluation']['valuation_quality']['score'] = 99.0
        (tmp_path / NAMES[0]).write_text(json.dumps(rows))
    else:
        target = manifest['runtime_projection_contract']['runtime_projection']['files'][NAMES[0]] if runtime else manifest['artifact_hashes']
        key = 'semantic_sha256' if runtime else NAMES[0]
        if damage == 'missing_hash':
            target.pop(key)
        else:
            target[key] = '0' * 64
        (tmp_path / NAMES[2]).write_text(json.dumps(manifest))
    before = hashes(tmp_path)
    assert load_exact_customer_inventory_with_status(tmp_path / NAMES[0], manifest)[1] is False
    with pytest.raises(RuntimeError, match='DAILY_BUY_NOW_RETAINED_PROJECTION_NOT_VERIFIED'):
        validate_retained_publication(root=tmp_path, output=tmp_path / 'out.json')
    assert hashes(tmp_path) == before
    assert not (tmp_path / 'out.json').exists()


@pytest.mark.parametrize('field', PILLARS)
@pytest.mark.parametrize('bad', [True, False, float('nan'), float('inf'), -float('inf'), 10 ** 400])
@pytest.mark.parametrize('nested', [False, True])
def test_all_six_pillars_reject_nonfinite_and_boolean_scores_even_when_hash_bound(tmp_path, field, bad, nested):
    def mutate(rows):
        rows[0]['canonical_investment_evaluation'][field] = {'score': bad} if nested else bad
    fixture(tmp_path, mutation=mutate)
    before = hashes(tmp_path)
    with pytest.raises(RuntimeError, match='DAILY_BUY_NOW_SIX_PILLAR_REPLAY_INCOMPLETE'):
        validate_retained_publication(root=tmp_path, output=tmp_path / 'out.json')
    assert hashes(tmp_path) == before
    assert not (tmp_path / 'out.json').exists()


def alias(root, name, kind):
    source = root / name
    if kind == 'direct':
        return source
    output = root / ('alias-' + name)
    if kind == 'symlink':
        output.symlink_to(source)
    else:
        os.link(source, output)
    return output


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('kind', ['direct', 'symlink', 'hardlink'])
def test_daily_output_cannot_overwrite_any_source_alias(tmp_path, name, kind):
    fixture(tmp_path)
    output = alias(tmp_path, name, kind)
    before = hashes(tmp_path)
    with pytest.raises(RuntimeError, match='DAILY_BUY_NOW_RECEIPT_OUTPUT_CONFLICT'):
        validate_retained_publication(root=tmp_path, output=output)
    assert hashes(tmp_path) == before


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('kind', ['direct', 'symlink', 'hardlink'])
@pytest.mark.parametrize('now', ['invalid-sensitive-clock', '2026-10-21T22:05:00Z'])
def test_cli_success_and_error_receipts_never_overwrite_source_aliases(tmp_path, name, kind, now):
    fixture(tmp_path)
    output = alias(tmp_path, name, kind)
    before = hashes(tmp_path)
    result = subprocess.run([
        sys.executable, str(ROOT / 'scripts/run_daily_buy_now_post_close.py'),
        '--now', now, '--last-contiguous-session', '2026-10-02',
        '--root', str(tmp_path), '--output', str(output),
    ], capture_output=True, text=True)
    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt['error'] == 'DAILY_BUY_NOW_RECEIPT_OUTPUT_CONFLICT'
    assert receipt['provider_calls'] == receipt['production_writes'] == 0
    assert now not in result.stdout
    assert not result.stderr
    assert hashes(tmp_path) == before
    assert not (tmp_path / 'provider_free_publication_validation.json').exists()


def test_source_change_between_read_and_final_verification_is_rejected(tmp_path, monkeypatch):
    rows, _ = fixture(tmp_path)
    before = hashes(tmp_path)
    original = Path.read_bytes
    changed = False
    def intercepted(path):
        nonlocal changed
        raw = original(path)
        if path == tmp_path / NAMES[0] and not changed:
            changed = True
            altered = deepcopy(rows)
            altered[0]['ticker'] = 'CHANGED_AFTER_READ'
            path.write_text(json.dumps(altered))
        return raw
    monkeypatch.setattr(Path, 'read_bytes', intercepted)
    with pytest.raises(RuntimeError, match='DAILY_BUY_NOW_DRY_RUN_MUTATED_PRODUCTION'):
        validate_retained_publication(root=tmp_path, output=tmp_path / 'out.json')
    assert not (tmp_path / 'out.json').exists()
    assert hashes(tmp_path)[NAMES[1]] == before[NAMES[1]]
    assert hashes(tmp_path)[NAMES[2]] == before[NAMES[2]]


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_cli_checks_derived_validation_receipt_before_any_output(tmp_path, kind):
    fixture(tmp_path)
    target = tmp_path / 'audit_results'
    target.mkdir()
    validation = target / 'provider_free_publication_validation.json'
    if kind == 'symlink':
        validation.symlink_to(tmp_path / NAMES[0])
    else:
        os.link(tmp_path / NAMES[0], validation)
    before = hashes(tmp_path)
    output = target / 'coordinator.json'
    result = subprocess.run([
        sys.executable, str(ROOT / 'scripts/run_daily_buy_now_post_close.py'),
        '--now', '2026-10-21T22:05:00Z', '--last-contiguous-session', '2026-10-02',
        '--root', str(tmp_path), '--output', str(output),
    ], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['error'] == 'DAILY_BUY_NOW_RECEIPT_OUTPUT_CONFLICT'
    assert not output.exists()
    assert hashes(tmp_path) == before


def test_output_alias_through_symlink_directory_is_rejected(tmp_path):
    root = tmp_path / 'source'
    fixture(root)
    linked = tmp_path / 'linked'
    linked.symlink_to(root, target_is_directory=True)
    before = hashes(root)
    with pytest.raises(RuntimeError, match='DAILY_BUY_NOW_RECEIPT_OUTPUT_CONFLICT'):
        validate_retained_publication(root=root, output=linked / NAMES[0])
    assert hashes(root) == before


def test_daily_does_not_admit_encoding_the_customer_cannot_read(tmp_path):
    rows, manifest = fixture(tmp_path)
    (tmp_path / NAMES[0]).write_bytes(json.dumps(rows).encode('utf-16'))
    before = hashes(tmp_path)
    assert load_exact_customer_inventory_with_status(tmp_path / NAMES[0], manifest)[1] is False
    with pytest.raises(UnicodeError):
        validate_retained_publication(root=tmp_path, output=tmp_path / 'out.json')
    assert hashes(tmp_path) == before
    assert not (tmp_path / 'out.json').exists()


@pytest.mark.parametrize('now', ['invalid-sensitive-clock', '2026-10-21T22:05:00Z'])
def test_cli_existing_directory_receipt_failure_remains_sanitized(tmp_path, now):
    fixture(tmp_path)
    output = tmp_path / 'private-sensitive-directory'
    output.mkdir()
    before = hashes(tmp_path)
    result = subprocess.run([
        sys.executable, str(ROOT / 'scripts/run_daily_buy_now_post_close.py'),
        '--now', now, '--last-contiguous-session', '2026-10-02',
        '--root', str(tmp_path), '--output', str(output),
    ], capture_output=True, text=True)
    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt['status'] == 'FAILED'
    assert receipt['error'] == 'DAILY_BUY_NOW_RECEIPT_WRITE_FAILED'
    assert receipt['schedule']['eligible'] is False
    assert 'private-sensitive' not in result.stdout
    assert not result.stderr
    assert hashes(tmp_path) == before
    assert list(output.iterdir()) == []


@pytest.mark.parametrize('now', ['invalid-sensitive-clock', '2026-10-21T22:05:00Z'])
def test_cli_replace_error_after_success_or_validation_failure_is_sanitized(tmp_path, monkeypatch, capsys, now):
    from scripts import run_daily_buy_now_post_close as cli
    fixture(tmp_path)
    before = hashes(tmp_path)
    output = tmp_path / 'audit_results/coordinator.json'
    original = os.replace
    def fail_receipt(source, destination):
        if Path(destination) == output:
            raise PermissionError('private-sensitive-path-or-credential')
        return original(source, destination)
    monkeypatch.setattr(os, 'replace', fail_receipt)
    monkeypatch.setattr(sys, 'argv', [
        'daily-coordinator', '--now', now, '--last-contiguous-session', '2026-10-02',
        '--root', str(tmp_path), '--output', str(output),
    ])
    assert cli.main() == 1
    captured = capsys.readouterr()
    receipt = json.loads(captured.out)
    assert receipt['error'] == 'DAILY_BUY_NOW_RECEIPT_WRITE_FAILED'
    assert receipt['status'] == 'FAILED' and receipt['schedule']['eligible'] is False
    assert 'private-sensitive' not in captured.out and now not in captured.out
    assert not captured.err
    assert hashes(tmp_path) == before
    assert not output.exists()
    assert not list(output.parent.glob('tmp*'))


@pytest.mark.parametrize('name', [
    'full_evaluation_pool.json', 'market_prescreen.json', 'discovery_candidate_pool.json',
    'recovery_scan.json', 'etf_scan.json', 'total_market_universe.json',
])
@pytest.mark.parametrize('kind', ['direct', 'symlink', 'hardlink'])
def test_unread_projection_sentinels_are_protected_on_success_and_cli_error(tmp_path, name, kind):
    fixture(tmp_path)
    extra = ['full_evaluation_pool.json', 'market_prescreen.json', 'discovery_candidate_pool.json',
             'recovery_scan.json', 'etf_scan.json', 'total_market_universe.json']
    for item in extra:
        (tmp_path / item).write_text(json.dumps({'generated-sentinel': item}))
    before = {item: (tmp_path / item).read_bytes() for item in (*NAMES, *extra)}
    output = alias(tmp_path, name, kind)
    with pytest.raises(RuntimeError, match='DAILY_BUY_NOW_RECEIPT_OUTPUT_CONFLICT'):
        validate_retained_publication(root=tmp_path, output=output)
    result = subprocess.run([
        sys.executable, str(ROOT / 'scripts/run_daily_buy_now_post_close.py'),
        '--now', 'invalid-sensitive-clock', '--root', str(tmp_path), '--output', str(output),
    ], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['error'] == 'DAILY_BUY_NOW_RECEIPT_OUTPUT_CONFLICT'
    assert not result.stderr
    assert {item: (tmp_path / item).read_bytes() for item in before} == before
