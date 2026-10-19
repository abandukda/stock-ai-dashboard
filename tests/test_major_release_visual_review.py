from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_major_release_visual_review import build


def test_visual_review_bundle_labels_fixture_evidence_and_requires_all_viewports(tmp_path: Path):
    source = tmp_path / "qa-fixture"
    source.mkdir()
    for name in ("home-desktop.png", "home-tablet.png", "home-tablet-768.png", "home-mobile.png", "home-mobile-360.png"):
        (source / name).write_bytes(b"png-evidence")
    output = tmp_path / "bundle"
    build(output, [source], "a" * 40)
    manifest = json.loads((output / "screenshot_manifest.json").read_text())
    assert manifest["status"] == "PASS"
    assert manifest["production_mutation"] == "NONE"
    assert manifest["licensed_provider_calls"] == 0
    assert {item["viewport"] for item in manifest["screenshots"]} == {
        "desktop_1440", "tablet_1024", "tablet_768", "mobile_390", "mobile_360",
    }
    assert all(item["evidence_classification"] == "ISOLATED_QA_FIXTURE_NOT_LIVE_MARKET_DATA"
               for item in manifest["screenshots"])
    for required in (
        "README.md", "SCREENSHOT_INDEX.md", "IMPLEMENTATION_SUMMARY.md", "FEATURE_COMPLETION.md", "DATA_TRUTH.md",
        "KNOWN_LIMITATIONS.md", "PRIORITIZED_REMAINING_GAPS.md", "CLAUDE_ISSUE_INVENTORY.md",
        "QA_RESULTS.md", "CLAUDE_REVIEW_PROMPT.md",
    ):
        assert (output / required).is_file()


def test_visual_review_bundle_fails_closed_when_tablet_is_missing(tmp_path: Path):
    source = tmp_path / "retained"
    source.mkdir()
    for name in ("research-desktop.png", "research-mobile.png", "research-mobile-360.png"):
        (source / name).write_bytes(b"png-evidence")
    output = tmp_path / "bundle"
    build(output, [source], "b" * 40)
    manifest = json.loads((output / "screenshot_manifest.json").read_text())
    assert manifest["status"] == "INCOMPLETE"
    assert "tablet_1024" not in manifest["observed_viewports"]


def test_visual_review_cli_accepts_relative_zip_output(tmp_path: Path):
    source = tmp_path / "qa-fixture"
    source.mkdir()
    for name in ("home-desktop.png", "home-tablet.png", "home-tablet-768.png", "home-mobile.png", "home-mobile-360.png"):
        (source / name).write_bytes(b"png-evidence")
    output = tmp_path / "bundle"
    relative_zip = Path("artifacts") / "review.zip"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "build_major_release_visual_review.py"),
            "--source-sha", "c" * 40,
            "--screenshot-root", str(source),
            "--output", str(output),
            "--zip-output", str(relative_zip),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / relative_zip).is_file()


def test_visual_review_bundle_separates_before_and_after_evidence(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir(); after.mkdir()
    names = ("report-card-desktop.png", "report-card-tablet.png", "report-card-tablet-768.png",
             "report-card-mobile.png", "report-card-mobile-360.png")
    for name in names:
        (before / name).write_bytes(b"before")
        (after / name).write_bytes(b"after")
    output = tmp_path / "bundle"
    build(output, [after], "d" * 40, [before], "c" * 40)
    manifest = json.loads((output / "screenshot_manifest.json").read_text())
    assert manifest["status"] == "PASS"
    assert manifest["before_evidence_status"] == "INCLUDED"
    assert manifest["before_source_sha"] == "c" * 40
    assert len(manifest["before_screenshots"]) == len(manifest["screenshots"]) == 5
    assert all(item["file"].startswith("screenshots/before/") for item in manifest["before_screenshots"])
    assert all(item["source_sha"] == "c" * 40 for item in manifest["before_screenshots"])
    assert all(item["file"].startswith("screenshots/after/") for item in manifest["screenshots"])
