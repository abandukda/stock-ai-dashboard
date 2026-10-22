import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.runner_readonly_diagnostic import Probe, command, diagnostic, registration, MAX_CAPTURE


class RunnerReadonlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.value = {"agentId": 23, "agentName": "atlas-contabo-1", "gitHubUrl": "https://github.com/abandukda/stock-ai-dashboard", "ephemeral": False}
        (self.root / ".runner").write_text(json.dumps(self.value))

    def tearDown(self):
        self.temp.cleanup()

    def test_plain_and_bom_registration_and_identity(self):
        for encoding in ("utf-8", "utf-8-sig"):
            (self.root / ".runner").write_text(json.dumps(self.value), encoding=encoding)
            self.assertEqual(registration(self.root, "23"), {"state": "MATCH", "ephemeral": False})
        self.assertEqual(registration(self.root, "21")["state"], "IDENTITY_MISMATCH")

    def test_diagnostic_cannot_emit_credentials_or_raw_logs_and_has_no_mutating_command(self):
        secret = "DO_NOT_OUTPUT_CREDENTIAL_3e6919"
        (self.root / ".credentials").write_text(secret)
        logs = self.root / "_diag"
        logs.mkdir()
        (logs / "Runner_20261022.log").write_text(f"Listening for Jobs\n{secret}\nConnection refused\n")
        invoked = []
        def mock(argv):
            invoked.append(argv)
            if "list-units" in argv:
                return Probe("OK", "actions.runner.abandukda-stock-ai-dashboard.atlas-contabo-1.service loaded inactive dead\n")
            if "show" in argv:
                return Probe("OK", "ActiveState=inactive\nSubState=dead\nExecMainStatus=0\nEnvironment=" + secret + "\nRestart=" + secret + "\n")
            if "_TRANSPORT=kernel" in argv:
                return Probe("INACCESSIBLE_OR_FAILED", "")
            return Probe("OK", f"{secret}\nThe runner has received a shutdown signal\n")
        opened = []
        real_open = Path.open
        def observed_open(path, *args, **kwargs):
            opened.append(path.name)
            self.assertFalse(path.name.startswith(".credentials"))
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", observed_open):
            result = diagnostic(self.root, "23", "2026-10-21T04:20:00Z", "2026-10-21T05:10:00Z", mock)
        self.assertIn(".runner", opened)
        self.assertIn("Runner_20261022.log", opened)
        serialized = json.dumps(result)
        self.assertNotIn(secret, serialized)
        self.assertNotIn(str(self.root), serialized)
        self.assertFalse(result["credentials_read"])
        self.assertEqual(result["services"][0]["properties"], {"ActiveState": "inactive", "SubState": "dead", "ExecMainStatus": "0"})
        self.assertEqual(result["services"][0]["historical_events"]["shutdown_signal"], 1)
        self.assertEqual(result["recent_runner_diagnostics"]["events"]["listening"], 1)
        self.assertEqual(result["kernel"]["probe"], "INACCESSIBLE_OR_FAILED")
        self.assertEqual(result["conclusion"], "EVIDENCE_ONLY_CAUSE_REQUIRES_CORRELATION")
        self.assertTrue(all(call[0] in {"systemctl", "journalctl", "ps"} for call in invoked))
        self.assertTrue(all(not set(call) & {"start", "stop", "restart", "enable", "disable", "daemon-reload", "--vacuum-time"} for call in invoked))

    def test_no_service_is_not_expired_registration_proof(self):
        result = diagnostic(self.root, "23", "2026-10-21T04:20:00Z", "2026-10-21T05:10:00Z", lambda argv: Probe("OK"))
        self.assertEqual(result["services"], [])
        self.assertEqual(result["registration"]["state"], "MATCH")
        self.assertNotIn("expired", json.dumps(result))

    def test_rejects_symlink_metadata_and_diagnostic_directory(self):
        (self.root / ".runner").unlink()
        (self.root / "other").write_text(json.dumps(self.value))
        (self.root / ".runner").symlink_to(self.root / "other")
        self.assertEqual(registration(self.root, "23")["state"], "INVALID_METADATA_FILE")
        (self.root / "_diag").symlink_to(self.root, target_is_directory=True)
        result = diagnostic(self.root, "23", "2026-10-21T04:20:00Z", "2026-10-21T05:10:00Z", lambda argv: Probe("OK"))
        self.assertEqual(result["recent_runner_diagnostics"]["files_read"], 0)
        self.assertEqual(result["recent_runner_diagnostics"]["unreadable_or_rejected"], 1)

    def test_windows_are_timezone_aware_ordered_and_explicit(self):
        for since, until in (("2026-10-21", "2026-10-22"), ("2026-10-22T00:00:00Z", "2026-10-21T00:00:00Z")):
            with self.assertRaises(ValueError):
                diagnostic(self.root, "23", since, until, lambda argv: Probe("OK"))

    def test_command_capture_and_timeout_are_bounded(self):
        result = command([sys.executable, "-c", f"import sys;sys.stdout.write('x'*{MAX_CAPTURE + 10000})"], timeout=5)
        self.assertEqual(result.state, "TRUNCATED")
        self.assertEqual(len(result.output), MAX_CAPTURE)
        self.assertTrue(result.truncated)
        result = command([sys.executable, "-c", "import time;time.sleep(2)"], timeout=0.1)
        self.assertEqual(result.state, "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
