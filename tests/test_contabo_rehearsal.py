import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/contabo_certification_rehearsal.py'
spec = importlib.util.spec_from_file_location('rehearsal', SCRIPT)
rehearsal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearsal)
FLAGS = dict(ATLAS_QA_PROVIDER_CALLS_ALLOWED='0', ATLAS_ALLOW_EXTERNAL_AI='false',
             ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')


class RehearsalTests(unittest.TestCase):
    def test_source_backup_verifier_rejects_same_file_device_and_changed_bytes(self):
        spec = importlib.util.spec_from_file_location('verify', ROOT/'scripts/verify_source_backup_readonly.py')
        verify = importlib.util.module_from_spec(spec); spec.loader.exec_module(verify)
        with tempfile.TemporaryDirectory() as work:
            a=Path(work)/'source'; b=Path(work)/'backup'
            a.write_bytes(b'fixture'); b.write_bytes(b'fixture')
            expected=hashlib.sha256(b'fixture').hexdigest()
            with self.assertRaisesRegex(ValueError,'SAME_FILE'):
                verify.verify(a,a,expected)
            with self.assertRaisesRegex(ValueError,'INDEPENDENT_STORAGE'):
                verify.verify(a,b,expected)
            b.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'DIGEST_MISMATCH'):
                verify.verify(a,b,expected)
            self.assertEqual(a.read_bytes(),b'fixture')
            link=Path(work)/'link'; link.symlink_to(a)
            with self.assertRaises(OSError):
                verify.identity(link)

    def test_actual_restart_corruption_and_source_integrity(self):
        with tempfile.TemporaryDirectory() as work, patch.dict(os.environ, dict(FLAGS, RUNNER_TEMP=work)):
            receipt = rehearsal.run('a'*40, source_rows=137, selected=129, padding=1024)
        self.assertEqual(receipt['status'], 'PASS')
        self.assertTrue(receipt['restarted_processes'])
        self.assertTrue(receipt['checkpoint_corruption_rejected'])
        self.assertFalse(receipt['retained_data_certified'])
        self.assertFalse(receipt['ledger_access'])
        self.assertLess(receipt['peak_rss_kib'], rehearsal.TARGET_KIB)

    def test_corrupted_and_wrong_source_checkpoints_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/'checkpoint.json'
            rehearsal.checkpoint(path, 'a'*40, 'b'*64, 64, ['fixture'])
            with self.assertRaisesRegex(ValueError, 'IDENTITY'):
                rehearsal.load_checkpoint(path, 'c'*40, 'b'*64)
            value = json.loads(path.read_text()); value['completed'] = 128
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'CORRUPT'):
                rehearsal.load_checkpoint(path, 'a'*40, 'b'*64)

    def test_resource_target_stops_after_valid_checkpoint(self):
        with tempfile.TemporaryDirectory() as work, patch.object(rehearsal, 'TARGET_KIB', 0):
            path = Path(work)/'checkpoint.json'
            with self.assertRaisesRegex(ValueError, 'RSS_TARGET'):
                rehearsal.checkpoint(path, 'a'*40, 'b'*64, 64, [])
            self.assertEqual(rehearsal.load_checkpoint(path, 'a'*40, 'b'*64)['completed'], 64)

    def test_provider_flags_and_network_fail_closed(self):
        code = 'import runpy,socket; m=runpy.run_path('+repr(str(SCRIPT))+'); m["safety"](); socket.socket()'
        env = dict(PATH=os.defpath, **FLAGS)
        result = subprocess.run([sys.executable, '-c', code], env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('NETWORK_DISABLED', result.stderr)
        for key in FLAGS:
            changed = dict(env); changed.pop(key)
            result = subprocess.run([sys.executable, '-c', code], env=changed, text=True, capture_output=True)
            self.assertIn('SAFETY_FLAG_MISMATCH', result.stderr)
        result = subprocess.run([sys.executable, '-c', code], env=dict(env, FINNHUB_API_KEY='DO_NOT_PRINT'), text=True, capture_output=True)
        self.assertIn('PROTECTED_VARIABLE_PRESENT', result.stderr)
        self.assertNotIn('DO_NOT_PRINT', result.stderr)

    def test_manual_owner_main_staging_zero_permission_workflow(self):
        path = ROOT/'.github/workflows/atlas_contabo_certification_rehearsal.yml'
        source = path.read_text(); doc = yaml.load(source, Loader=yaml.BaseLoader)
        self.assertEqual(set(doc['on']), {'workflow_dispatch'})
        self.assertFalse(doc['on']['workflow_dispatch'])
        job = doc['jobs']['rehearsal']
        self.assertEqual(job['runs-on'], ['self-hosted','Linux','X64','atlas-contabo-staging'])
        self.assertEqual(doc['permissions'], {}); self.assertEqual(job['permissions'], {})
        self.assertNotIn('environment', job)
        for clause in ("github.actor == 'abandukda'", "github.triggering_actor == 'abandukda'", "github.ref == 'refs/heads/main'"):
            self.assertIn(clause, job['if'])
        self.assertIn(hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), source)
        for forbidden in ('secrets.', 'actions/checkout', 'pip install', 'download-artifact'):
            self.assertNotIn(forbidden, source)

    def test_launcher_exact_rehearsal_id_and_workflow_only(self):
        source = (ROOT/'scripts/contabo_rehearsal_once.sh').read_text()
        self.assertIn("data.get('agentId') != 23", source)
        guard = re.search(r"<<'GUARD'\n(.*?)\nGUARD", source, re.S).group(1).split('\nATLAS_SMOKE_GUARD_PY')[0]
        code = 'APPROVED_SHA = "'+'a'*40+'"\n'+guard
        env = dict(PATH=os.defpath, GITHUB_REPOSITORY='abandukda/stock-ai-dashboard',
                   GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main',
                   GITHUB_WORKFLOW_REF='abandukda/stock-ai-dashboard/.github/workflows/atlas_contabo_certification_rehearsal.yml@refs/heads/main',
                   GITHUB_WORKFLOW_SHA='a'*40, GITHUB_SHA='a'*40, GITHUB_ACTOR='abandukda',
                   GITHUB_TRIGGERING_ACTOR='abandukda', GITHUB_JOB='rehearsal', RUNNER_NAME='atlas-contabo-1')
        def invoke(environment):
            return subprocess.run([sys.executable,'-c',code], env=environment, capture_output=True)
        self.assertEqual(invoke(env).returncode, 0)
        for key in env.keys()-{'PATH'}:
            self.assertNotEqual(invoke(dict(env, **{key:'wrong'})).returncode, 0)
        self.assertNotEqual(invoke(dict(env,GITHUB_JOB='smoke')).returncode, 0)
        for forbidden in ('config.sh','svc.sh install','sudo '):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
