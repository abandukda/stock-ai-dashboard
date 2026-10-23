"""Offline fixtures only: never run APT or change host source configuration."""
from pathlib import Path
import os
import stat
import subprocess
import sys
import shlex
from unittest.mock import patch

import pytest

from scripts.normalize_ci_ubuntu_mirror import normalize_file, normalize_sources


UBUNTU = 'ID=ubuntu\nVERSION_ID="24.04"\n'
SOURCE = """# Ubuntu archive for disposable hosted CI
Types: deb deb-src
URIs: mirror+file:/etc/apt/apt-mirrors.txt
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
Architectures: amd64

Types: deb
URIs: mirror+file:/etc/apt/apt-security-mirrors.txt
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""


def test_recognized_runner_mirror_lists_use_official_https_without_losing_authority():
    output = normalize_sources(SOURCE)
    assert "URIs: https://archive.ubuntu.com/ubuntu" in output
    assert "URIs: https://security.ubuntu.com/ubuntu" in output
    assert "Suites: noble noble-updates noble-backports" in output
    assert "Suites: noble-security" in output
    assert "Types: deb deb-src" in output
    assert "Architectures: amd64" in output
    assert output.count("Components: main restricted universe multiverse") == 2
    assert output.count("Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg") == 2
    assert "# Ubuntu archive for disposable hosted CI" in output
    assert normalize_sources(output) == output


@pytest.mark.parametrize("uri", ["http://azure.archive.ubuntu.com/ubuntu/",
    "https://azure.archive.ubuntu.com/ubuntu", "http://archive.ubuntu.com/ubuntu",
    "https://archive.ubuntu.com/ubuntu", "http://security.ubuntu.com/ubuntu",
    "https://security.ubuntu.com/ubuntu"])
def test_recognized_direct_ubuntu_uris_are_normalized(uri):
    assert "URIs: https://archive.ubuntu.com/ubuntu" in normalize_sources(
        SOURCE.replace("mirror+file:/etc/apt/apt-mirrors.txt", uri))


def test_combined_security_stanza_preserves_all_suites_and_signing_fields():
    original = SOURCE.split("\n\n", 1)[0].replace(
        "noble noble-updates noble-backports", "noble-security noble noble-updates noble-backports")
    output = normalize_sources(original)
    assert output.count("Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg") == 2
    assert "Suites: noble noble-updates noble-backports" in output
    assert "Suites: noble-security" in output
    assert "https://security.ubuntu.com/ubuntu" in output
    assert normalize_sources(output) == output


@pytest.mark.parametrize("before,after", [
    ("mirror+file:/etc/apt/apt-mirrors.txt", "https://unknown.invalid/ubuntu"),
    ("mirror+file:/etc/apt/apt-mirrors.txt", "mirror+file:/tmp/unreviewed-mirrors.txt"),
    ("ubuntu-archive-keyring.gpg", "unreviewed-keyring.gpg"),
    ("Suites: noble noble-updates noble-backports", "Suites: jammy"),
    ("Suites: noble noble-updates noble-backports", "Suites: noble noble"),
    ("Components: main restricted universe multiverse", "Components: main unreviewed"),
    ("Types: deb deb-src", "Types: arbitrary"),
    ("Architectures: amd64", "Architectures: arm64"),
    ("Architectures: amd64", "Enabled: no"),
    ("Architectures: amd64", "Trusted: yes"),
    ("Architectures: amd64", "URIs: https://archive.ubuntu.com/ubuntu"),
    ("Types: deb deb-src", " Types: deb deb-src"),
])
def test_unknown_layout_rejected_before_file_mutation(tmp_path, before, after):
    path = tmp_path / "ubuntu.sources"
    original = SOURCE.replace(before, after).encode()
    path.write_bytes(original)
    with pytest.raises(ValueError):
        normalize_file(path, os_release=UBUNTU)
    assert path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ubuntu.sources"]


def test_atomic_replacement_preserves_mode_owner_and_supports_idempotency(tmp_path):
    path = tmp_path / "ubuntu.sources"
    path.write_text(SOURCE)
    path.chmod(0o640)
    original = path.stat()
    receipt = normalize_file(path, os_release=UBUNTU)
    assert receipt["changed"] is True
    assert receipt["before_sha256"] != receipt["after_sha256"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert (path.stat().st_uid, path.stat().st_gid) == (original.st_uid, original.st_gid)
    assert normalize_file(path, os_release=UBUNTU)["changed"] is False


def test_replace_failure_leaves_original_complete_and_cleans_temporary_file(tmp_path):
    path = tmp_path / "ubuntu.sources"
    path.write_text(SOURCE)
    with patch("scripts.normalize_ci_ubuntu_mirror.os.replace", side_effect=OSError("fixture")):
        with pytest.raises(OSError):
            normalize_file(path, os_release=UBUNTU)
    assert path.read_text() == SOURCE
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ubuntu.sources"]


def test_source_change_during_prepare_is_not_overwritten(tmp_path):
    path = tmp_path / "ubuntu.sources"
    path.write_text(SOURCE)
    real_fsync = os.fsync
    def changed(descriptor):
        real_fsync(descriptor)
        path.write_text("EXTERNAL CHANGE")
    with patch("scripts.normalize_ci_ubuntu_mirror.os.fsync", side_effect=changed):
        with pytest.raises(ValueError, match="CHANGED_DURING_REVIEW"):
            normalize_file(path, os_release=UBUNTU)
    assert path.read_text() == "EXTERNAL CHANGE"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ubuntu.sources"]


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_source_aliases_rejected(tmp_path, kind):
    original = tmp_path / "original"
    original.write_text(SOURCE)
    path = tmp_path / "ubuntu.sources"
    if kind == "symlink":
        path.symlink_to(original)
    else:
        os.link(original, path)
    with pytest.raises(ValueError, match="REGULAR_UNALIASED"):
        normalize_file(path, os_release=UBUNTU)
    assert original.read_text() == SOURCE


@pytest.mark.parametrize("release", ['ID=debian\nVERSION_ID="24.04"',
                                     'ID=ubuntu\nVERSION_ID="22.04"'])
def test_other_operating_systems_rejected_without_writes(tmp_path, release):
    path = tmp_path / "ubuntu.sources"
    path.write_text(SOURCE)
    with pytest.raises(ValueError, match="RELEASE_UNRECOGNIZED"):
        normalize_file(path, os_release=release)
    assert path.read_text() == SOURCE


def test_comments_and_missing_stanzas_do_not_discard_active_sources():
    with pytest.raises(ValueError):
        normalize_sources("# Only a comment\n")
    output = normalize_sources("# Preamble\n\n" + SOURCE)
    assert output.startswith("# Preamble\n\n")
    assert "Suites: noble-security" in output


@pytest.mark.parametrize("filename,render_gate", [
    ("atlas_premium_home_review.yml", "python -m unittest discover -s tests -p 'test_premium_*render.py' -v"),
    ("atlas_customer_experience_autonomous_qa.yml", "python -m unittest discover -s tests -p test_chart_failure_diagnostic_browser.py -v"),
])
def test_workflow_keeps_complete_playwright_install_and_all_render_gates(filename, render_gate):
    workflow = (Path(__file__).parents[1] / ".github/workflows" / filename).read_text()
    # Inspect only the affected hosted 15-minute job. The separate manually
    # dispatched governed certification job and its policy are unchanged.
    affected_job = workflow.split("  governed-browser-certification:", 1)[0]
    assert "timeout-minutes: 15" in affected_job
    assert "sudo python3 scripts/normalize_ci_ubuntu_mirror.py\n          python -m playwright install --with-deps chromium" in workflow
    assert "playwright==1.52.0" in workflow
    assert render_gate in affected_job
    if filename == "atlas_premium_home_review.yml":
        assert "if-no-files-found: error" in affected_job
    else:
        # Preserve the existing Customer evidence policy; do not change it as
        # part of dependency installation recovery.
        assert affected_job.count("if-no-files-found: warn") == 3
        assert "test_research_section_navigation_browser.py" in affected_job
        assert "test_workspace_watchlist_boundary_browser.py" in affected_job
    assert "runs-on: ubuntu-24.04" in affected_job
    assert "self-hosted" not in affected_job
    assert "scripts/normalize_ci_ubuntu_mirror.py" in affected_job
    assert "python -m pytest -q tests/test_ci_ubuntu_mirror.py" in affected_job


def test_routing_geometry_normalizes_mirror_without_extending_or_bypassing_gates():
    import yaml
    workflow = (Path(__file__).parents[1] / ".github/workflows" / "atlas_runner_routing_ci.yml").read_text()
    parsed = yaml.safe_load(workflow)
    job = parsed["jobs"]["customer-navigation-geometry"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 8
    assert parsed["permissions"] == {"contents": "read"}
    runs = [step.get("run", "") for step in job["steps"]]
    install = next(run for run in runs if "playwright install" in run)
    assert install == ("sudo python3 scripts/normalize_ci_ubuntu_mirror.py\n"
                       "python -m playwright install --with-deps chromium\n")
    assert all(step.get("continue-on-error") is not True for step in job["steps"])
    assert "python -m unittest discover -s tests -p test_customer_nav_geometry.py -v" in runs
    assert "python -m unittest discover -s tests -p test_annotated_chart_render.py -v" in runs
    assert any(step.get("with", {}).get("if-no-files-found") == "error" for step in job["steps"])
    offline = parsed["jobs"]["offline-routing-contract"]
    assert "python3 -m pytest -q tests/test_ci_ubuntu_mirror.py" in [step.get("run") for step in offline["steps"]]
    assert "self-hosted" not in str(job) and "secrets." not in str(job)
    assert "scripts/normalize_ci_ubuntu_mirror.py" in workflow


def test_pinned_playwright_dry_run_still_requests_all_chromium_libraries_and_fonts():
    # This CLI mode prints commands only. It does not invoke APT or networking.
    result = subprocess.run([sys.executable, "-m", "playwright", "install-deps",
                             "--dry-run", "chromium"], check=True,
                            capture_output=True, text=True, timeout=15)
    shell = shlex.split(result.stdout.strip())
    assert shell[:2] == ["sh", "-c"] or shell[:4] == ["sudo", "--", "sh", "-c"]
    command = shell[-1]
    update, install = command.split("&&")
    assert shlex.split(update) == ["apt-get", "update"]
    tokens = shlex.split(install)
    assert tokens[:4] == ["apt-get", "install", "-y", "--no-install-recommends"]
    assert set(tokens[4:]) == {
        "libasound2t64", "libatk-bridge2.0-0t64", "libatk1.0-0t64", "libatspi2.0-0t64",
        "libcairo2", "libcups2t64", "libdbus-1-3", "libdrm2", "libgbm1", "libglib2.0-0t64",
        "libnspr4", "libnss3", "libpango-1.0-0", "libx11-6", "libxcb1", "libxcomposite1",
        "libxdamage1", "libxext6", "libxfixes3", "libxkbcommon0", "libxrandr2", "xvfb",
        "fonts-noto-color-emoji", "fonts-unifont", "libfontconfig1", "libfreetype6",
        "xfonts-cyrillic", "xfonts-scalable", "fonts-liberation", "fonts-ipafont-gothic",
        "fonts-wqy-zenhei", "fonts-tlwg-loma-otf", "fonts-freefont-ttf",
    }


@pytest.mark.parametrize("normalization_exit,install_exit,expected", [(17, 0, 17), (0, 19, 19), (0, 0, 0)])
def test_workflow_shell_propagates_failures_without_real_commands(tmp_path, normalization_exit, install_exit, expected):
    sentinel = tmp_path / "install-attempted"
    # These are shell functions, not package-manager or host commands.
    command = f'''sudo() {{ return {normalization_exit}; }}
python() {{ touch "$SENTINEL"; return {install_exit}; }}
sudo python3 scripts/normalize_ci_ubuntu_mirror.py
python -m playwright install --with-deps chromium
'''
    result = subprocess.run(["bash", "-e", "-c", command],
                            env={**os.environ, "SENTINEL": str(sentinel)}, timeout=5)
    assert result.returncode == expected
    assert sentinel.exists() is (normalization_exit == 0)
