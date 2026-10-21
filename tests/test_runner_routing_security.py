"""Routing is checked before allocation; Contabo smoke never runs repository code."""
import copy
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SMOKE = 'atlas_contabo_provider_free_smoke.yml'
LEGACY = ['self-hosted', 'Linux', 'X64', 'atlas-worker-1']
STAGING = ['self-hosted', 'Linux', 'X64', 'atlas-contabo-staging']
SHA = 'a' * 40


def workflows(root=ROOT):
    return {p.name: yaml.load(p.read_text(), Loader=yaml.BaseLoader)
            for p in (root / '.github/workflows').glob('*.yml')}


def routing_errors(definitions):
    errors = []
    for name, doc in definitions.items():
        for job_id, job in doc.get('jobs', {}).items():
            route = job.get('runs-on', [])
            if 'self-hosted' not in str(route):
                continue
            wanted = STAGING if name == SMOKE and job_id == 'smoke' else LEGACY
            if route != wanted:
                errors.append(f'{name}:{job_id}:unapproved-runner-route')
    return errors


class RoutingSecurity(unittest.TestCase):
    def test_all_self_hosted_jobs_have_explicit_preallocation_routes(self):
        self.assertEqual(routing_errors(workflows()), [])

    def test_generic_route_is_rejected_even_with_post_allocation_guard(self):
        docs = {SMOKE: workflows()[SMOKE]}
        docs = copy.deepcopy(docs)
        docs[SMOKE]['jobs']['smoke']['runs-on'] = ['self-hosted', 'Linux', 'X64']
        self.assertEqual(len(routing_errors(docs)), 1)

    def test_protected_workloads_cannot_be_moved_to_contabo(self):
        docs = copy.deepcopy(workflows())
        docs['atlas_report_card_durable_readonly_certification.yml']['jobs']['certify']['runs-on'] = STAGING
        self.assertEqual(len(routing_errors(docs)), 1)

    def test_all_seven_previously_generic_jobs_guard_before_checkout(self):
        expected = {
            'atlas_finnhub_full_universe_aggregation_recovery.yml': ['build-immutable-candidate-checkpoint', 'build-publication-candidate'],
            'atlas_finnhub_publication_only_recovery.yml': ['build-publication-candidate-only'],
            'atlas_full_qa_certification.yml': ['visual-certification'],
            'atlas_release_smoke_bounded.yml': ['verify-publication', 'browser-smoke'],
            'atlas_research_context_diagnostic.yml': ['research-context-ab'],
        }
        docs = workflows()
        for name, jobs in expected.items():
            for job_id in jobs:
                with self.subTest(workflow=name, job=job_id):
                    job = docs[name]['jobs'][job_id]
                    self.assertEqual(job['runs-on'], LEGACY)
                    first = job['steps'][0]
                    self.assertNotIn('uses', first)
                    self.assertEqual(first['env']['ATLAS_ACTUAL_RUNNER'], '${{ runner.name }}')
                    self.assertEqual(first['run'], 'test "$ATLAS_ACTUAL_RUNNER" = "atlas-worker-1"')

    def test_full_visual_job_does_not_inherit_repository_write(self):
        job = workflows()['atlas_full_qa_certification.yml']['jobs']['visual-certification']
        self.assertEqual(job['permissions'], {'actions': 'read', 'contents': 'read'})

    def test_smoke_is_manual_main_owner_only_and_has_no_inputs(self):
        doc = workflows()[SMOKE]
        self.assertEqual(set(doc['on']), {'workflow_dispatch'})
        self.assertFalse(doc['on']['workflow_dispatch'])
        job = doc['jobs']['smoke']
        for clause in ["github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'",
                       "github.repository == 'abandukda/stock-ai-dashboard'", "github.actor == 'abandukda'",
                       "github.triggering_actor == 'abandukda'"]:
            self.assertIn(clause, job['if'])
        self.assertEqual(doc['permissions'], {})
        self.assertEqual(job['permissions'], {})
        self.assertEqual(job['timeout-minutes'], '5')
        self.assertFalse(any('uses' in step for step in job['steps']))
        source = (ROOT / '.github/workflows' / SMOKE).read_text()
        for forbidden in ('secrets.', 'actions/checkout', 'pip install', 'curl ', 'wget ', 'import requests', 'import socket', 'import urllib'):
            self.assertNotIn(forbidden, source)

    def test_smoke_boundaries_and_temp_only_io_are_explicit(self):
        source = (ROOT / '.github/workflows' / SMOKE).read_text()
        self.assertIn("dir=os.environ['RUNNER_TEMP']", source)
        self.assertIn("'ATLAS_QA_PROVIDER_CALLS_ALLOWED'] == '0'", source)
        self.assertIn("'ATLAS_CUSTOMER_REPORT_CARD_ENABLED'] == 'false'", source)
        self.assertIn('production_ledger_access=False', source)

    def test_runner_identity_context_is_scoped_to_first_step(self):
        # GitHub rejects runner context in jobs.<job>.env before allocation.
        job = workflows()[SMOKE]['jobs']['smoke']
        self.assertFalse(any('runner.' in value for value in job['env'].values()))
        first = job['steps'][0]
        self.assertEqual(first['env']['ATLAS_ACTUAL_RUNNER'], '${{ runner.name }}')
        self.assertIn('test "$ATLAS_ACTUAL_RUNNER" = atlas-contabo-1', first['run'])

    def test_ci_checks_workflow_semantics_with_checksum_pinned_linter(self):
        steps = workflows()['atlas_runner_routing_ci.yml']['jobs']['offline-routing-contract']['steps']
        lint = next(step['run'] for step in steps if 'pinned actionlint' in step.get('name', ''))
        self.assertIn('actionlint_1.7.12_linux_amd64.tar.gz', lint)
        self.assertIn('8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8', lint)
        self.assertIn('sha256sum -c -', lint)
        self.assertIn('.github/workflows/' + SMOKE, lint)
        self.assertNotIn('-ignore', lint)

    def test_launcher_preserves_registration_and_has_bounded_foreground_mode(self):
        source = (ROOT / 'scripts/contabo_smoke_once.sh').read_text()
        for forbidden in ('config.sh', 'svc.sh install', 'svc.sh start', 'sudo ', 'pkill ', 'killall '):
            self.assertNotIn(forbidden, source)
        self.assertIn('--preflight', source)
        self.assertIn('timeout --signal=INT --kill-after=30s 12m ./run.sh --once', source)
        self.assertIn('ACTIONS_RUNNER_HOOK_JOB_STARTED="$guard"', source)
        self.assertIn('2.337.0', source)

    def test_ci_stays_github_hosted_and_read_only(self):
        doc = workflows()['atlas_runner_routing_ci.yml']
        self.assertEqual(doc['permissions'], {'contents': 'read'})
        self.assertEqual(doc['jobs']['offline-routing-contract']['runs-on'], 'ubuntu-24.04')
        self.assertNotIn('secrets.', (ROOT / '.github/workflows/atlas_runner_routing_ci.yml').read_text())


class HostJobAllowlist(unittest.TestCase):
    def setUp(self):
        launcher = (ROOT / 'scripts/contabo_smoke_once.sh').read_text()
        self.code = 'APPROVED_SHA = "' + SHA + '"\n' + re.search(r"<<'GUARD'\n(.*?)\nGUARD", launcher, re.S).group(1).split('\nATLAS_SMOKE_GUARD_PY')[0]
        self.env = dict(PATH=os.defpath, GITHUB_REPOSITORY='abandukda/stock-ai-dashboard',
                        GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main',
                        GITHUB_WORKFLOW_REF='abandukda/stock-ai-dashboard/.github/workflows/'+SMOKE+'@refs/heads/main',
                        GITHUB_WORKFLOW_SHA=SHA, GITHUB_SHA=SHA, GITHUB_ACTOR='abandukda',
                        GITHUB_TRIGGERING_ACTOR='abandukda', GITHUB_JOB='smoke', RUNNER_NAME='atlas-contabo-1')

    def invoke(self, env):
        with tempfile.TemporaryDirectory() as directory:
            hook = Path(directory) / 'allow-smoke.sh'
            hook.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexec python3 - <<'ATLAS_SMOKE_GUARD_PY'\n" + self.code + '\nATLAS_SMOKE_GUARD_PY\n')
            return subprocess.run(['bash', str(hook)], env=env, text=True, capture_output=True)

    def test_exact_owner_main_smoke_allowed(self):
        self.assertEqual(self.invoke(self.env).returncode, 0)

    def test_missing_or_changed_identity_fails_closed(self):
        for key in self.env.keys() - {'PATH'}:
            for mode in ('missing', 'changed'):
                with self.subTest(key=key, mode=mode):
                    env = dict(self.env)
                    if mode == 'missing': env.pop(key)
                    else: env[key] = 'untrusted'
                    self.assertNotEqual(self.invoke(env).returncode, 0)

    def test_fork_pr_and_protected_workflow_rejected(self):
        for patch in [dict(GITHUB_EVENT_NAME='pull_request'), dict(GITHUB_EVENT_NAME='pull_request_target'),
                      dict(GITHUB_REF='refs/pull/106/merge'),
                      dict(GITHUB_WORKFLOW_REF='abandukda/stock-ai-dashboard/.github/workflows/atlas_report_card_durable_readonly_certification.yml@refs/heads/main')]:
            with self.subTest(patch=patch):
                self.assertNotEqual(self.invoke(dict(self.env, **patch)).returncode, 0)

    def test_protected_values_never_leak_on_rejection(self):
        for key in ('FINNHUB_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','APP_PASSWORD','ATLAS_AUDIT_PASSWORD','GUEST_PASSWORD','VIEWER_PASSWORD','ATLAS_REPORT_CARD_LEDGER_PATH','DATA_DIR'):
            with self.subTest(key=key):
                value='sensitive-test-marker-DO-NOT-PRINT'
                result=self.invoke(dict(self.env, **{key:value}))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(value, result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
