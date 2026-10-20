"""Exercise the actual workflow checksum commands without providers or secrets."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/atlas_codex_autopilot.yml'


class CandidateChecksumTests(unittest.TestCase):
    def commands(self):
        source = WORKFLOW.read_text()
        blocks = []
        for section in source.split('expected_digest=$(awk ')[1:]:
            block = 'expected_digest=$(awk ' + section.split('          expected=$(cat atlas-autopilot-base-sha)')[0]
            blocks.append('\n'.join(line.strip() for line in block.strip().splitlines()))
        self.assertEqual(len(blocks), 2, 'Both validate and draft_pr must verify the candidate')
        return blocks

    def verify(self, content, manifest):
        for command in self.commands():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'atlas-autopilot.patch').write_bytes(content)
                (root / 'atlas-autopilot.patch.sha256').write_text(manifest)
                result = subprocess.run(['bash', '-euo', 'pipefail', '-c', command], cwd=root, capture_output=True)
                yield result.returncode

    def test_relocated_artifact_accepts_absolute_packaging_path(self):
        patch = b'preserved candidate\n'
        digest = hashlib.sha256(patch).hexdigest()
        self.assertEqual(list(self.verify(patch, f'{digest}  /tmp/atlas-autopilot.patch\n')), [0, 0])

    def test_tampered_artifact_fails_closed(self):
        digest = hashlib.sha256(b'original').hexdigest()
        self.assertTrue(all(self.verify(b'tampered', f'{digest}  /tmp/atlas-autopilot.patch\n')))

    def test_empty_short_and_non_hex_digests_fail_closed(self):
        for manifest in ('', 'abc  atlas-autopilot.patch\n', 'z' * 64 + '  atlas-autopilot.patch\n'):
            with self.subTest(manifest=manifest):
                self.assertTrue(all(self.verify(b'candidate', manifest)))

    def test_exact_base_and_patch_guards_remain_in_both_stages(self):
        source = WORKFLOW.read_text()
        for stage in ('  validate:', '  draft_pr:'):
            section = source.split(stage, 1)[1].split('\n  draft_pr:')[0]
            self.assertIn('test "$(git rev-parse HEAD)" = "$expected"', section)
            self.assertIn('git apply --check /tmp/atlas-candidate/atlas-autopilot.patch', section)
            self.assertIn("services/customer_research_v2\\.py$", section)


if __name__ == '__main__':
    unittest.main()
