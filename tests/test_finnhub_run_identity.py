from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.resolve_finnhub_run_identity import resolve_identity


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), check=True, capture_output=True, text=True).stdout.strip()


def test_dispatch_and_schedule_resolve_same_commit_identity():
    sha = _git("rev-parse", "HEAD")
    expected_timestamp = _git("show", "-s", "--format=%cI", sha)
    dispatch_identity = resolve_identity(sha)
    schedule_identity = resolve_identity(sha)
    assert dispatch_identity == schedule_identity == {
        "source_sha": sha,
        "evidence_snapshot_at": expected_timestamp,
    }


def test_mismatched_checkout_fails_closed():
    with pytest.raises(ValueError, match="does not equal expected SHA"):
        resolve_identity("0" * 40)


def test_missing_commit_timestamp_fails_closed(monkeypatch):
    sha = _git("rev-parse", "HEAD")

    def fake_git(*args: str) -> str:
        return sha if args[:2] == ("rev-parse", "HEAD") else ""

    monkeypatch.setattr("scripts.resolve_finnhub_run_identity._git", fake_git)
    with pytest.raises(ValueError, match="commit timestamp is required"):
        resolve_identity(sha)


def test_every_full_universe_job_resolves_checkout_identity():
    workflow = Path(
        ".github/workflows/atlas_finnhub_full_universe_certification.yml"
    ).read_text(encoding="utf-8")
    assert "github.event.head_commit.timestamp" not in workflow
    assert workflow.count("uses: actions/checkout@v4") == 6
    assert workflow.count("name: Resolve immutable run identity from checkout") == 6
