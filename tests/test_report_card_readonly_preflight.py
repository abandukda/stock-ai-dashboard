"""Exercise missing audit configuration without credentials or durable storage."""
import os
from pathlib import Path
import subprocess

import pytest
import yaml


def steps():
    source = Path('.github/workflows/atlas_report_card_durable_readonly_certification.yml').read_text()
    return yaml.safe_load(source)['jobs']['certify']['steps']


@pytest.mark.parametrize('missing', [
    'ATLAS_REPORT_CARD_DURABLE_ROOT', 'ATLAS_REPORT_CARD_BACKUP_ROOT',
    'ATLAS_INTERNAL_QA_PASSWORD', 'ATLAS_VIEWER_QA_PASSWORD',
])
def test_missing_input_is_named_without_disclosing_credential_values(tmp_path, missing):
    configured = {
        'ATLAS_REPORT_CARD_DURABLE_ROOT': '/mnt/atlas_report_card_primary',
        'ATLAS_REPORT_CARD_BACKUP_ROOT': '/mnt/atlas_report_card_backup',
        'ATLAS_INTERNAL_QA_PASSWORD': 'offline-admin-sentinel',
        'ATLAS_VIEWER_QA_PASSWORD': 'offline-viewer-sentinel',
    }
    del configured[missing]
    diagnostic = tmp_path / 'audit_results/report_card_durable_readonly'
    diagnostic.mkdir(parents=True)
    command = next(s['run'] for s in steps() if s.get('name') == 'Enforce exact runner and immutable inputs')
    command = command.replace('${{ runner.name }}', 'atlas-worker-1')
    result = subprocess.run(['bash', '-euo', 'pipefail', '-c', command],
                            cwd=tmp_path, env={'PATH': os.environ['PATH'], **configured},
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert missing in result.stdout
    assert (diagnostic / 'missing_configuration.txt').read_text().strip() == missing
    assert 'offline-admin-sentinel' not in result.stdout + result.stderr
    assert 'offline-viewer-sentinel' not in result.stdout + result.stderr


def test_incomplete_before_capture_cannot_run_after_or_certify():
    by_name = {s.get('name'): s for s in steps()}
    after = by_name['Capture after state and prove no mutation']
    summary = by_name['Build certification summary']
    assert "steps.before.outcome == 'success'" in after['if']
    for name in ('before', 'audit', 'after'):
        assert f"steps.{name}.outcome == 'success'" in summary['if']
    assert by_name['Upload complete certification artifact']['if'] == '${{ always() }}'
