from __future__ import annotations

import json
from pathlib import Path

from scripts.build_major_release_visual_review import build


def test_visual_review_bundle_labels_fixture_evidence_and_requires_all_viewports(tmp_path: Path):
    source = tmp_path / "qa-fixture"
    source.mkdir()
    for name in ("home-desktop.png", "home-tablet.png", "home-mobile.png", "home-mobile-360.png"):
        (source / name).write_bytes(b"png-evidence")
    output = tmp_path / "bundle"
    build(output, [source], "a" * 40)
    manifest = json.loads((output / "screenshot_manifest.json").read_text())
    assert manifest["status"] == "PASS"
    assert manifest["production_mutation"] == "NONE"
    assert manifest["licensed_provider_calls"] == 0
    assert {item["viewport"] for item in manifest["screenshots"]} == {
        "desktop_1440", "tablet_1024", "mobile_390", "mobile_360",
    }
    assert all(item["evidence_classification"] == "ISOLATED_QA_FIXTURE_NOT_LIVE_MARKET_DATA"
               for item in manifest["screenshots"])
    for required in (
        "README.md", "SCREENSHOT_INDEX.md", "IMPLEMENTATION_SUMMARY.md", "DATA_TRUTH.md",
        "KNOWN_LIMITATIONS.md", "PRIORITIZED_REMAINING_GAPS.md", "QA_RESULTS.md", "CLAUDE_REVIEW_PROMPT.md",
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
