from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "atlas-runtime-qa-v3.yml"
SOURCE = WORKFLOW.read_text(encoding="utf-8")


def test_dispatch_exposes_three_isolated_modes_and_schedule_stays_full():
    options = SOURCE.split("options:", 1)[1].split("schedule:", 1)[0]
    assert options.count("- full") == 1
    assert options.count("- targeted_preflight") == 1
    assert options.count("- visual_crawl") == 1
    assert "github.event_name == 'workflow_dispatch' && inputs.mode == 'visual_crawl'" in SOURCE
    assert "github.event_name != 'workflow_dispatch' || inputs.mode != 'visual_crawl'" in SOURCE
    assert "github.event_name == 'workflow_dispatch' && inputs.mode || 'full'" in SOURCE


def test_visual_mode_reuses_existing_secret_and_has_no_new_credential_path():
    visual = SOURCE.split("Run non-blocking Atlas Visual Crawler", 1)[1].split(
        "Summarize Visual Crawler certification", 1
    )[0]
    assert "ATLAS_AUDIT_PASSWORD: ${{ secrets.ATLAS_AUDIT_PASSWORD }}" in visual
    assert "secrets." in visual
    assert visual.count("secrets.") == 1
    assert "password=" not in visual.lower()


def test_visual_mode_invokes_only_standalone_crawler_and_cannot_fall_through():
    visual = SOURCE.split("Run non-blocking Atlas Visual Crawler", 1)[1].split(
        "Summarize Visual Crawler certification", 1
    )[0]
    assert "python -u -m agents.atlas_visual_crawler_v1" in visual
    assert "agents.atlas_runtime_qa_v3" not in visual
    assert "scanner" not in visual.lower()
    assert "continue-on-error: true" in visual


def test_artifact_upload_precedes_final_certification_failure():
    upload = SOURCE.index("- name: Upload QA Report")
    final = SOURCE.index("- name: Set Visual Crawler certification result")
    assert upload < final
    assert "if: always()" in SOURCE[upload:final]
    assert "retention-days: 14" in SOURCE[upload:final]
    assert "path: audit_results" in SOURCE[upload:final]


def test_console_summary_contains_all_required_counts_and_severities():
    summary = SOURCE.split("Summarize Visual Crawler certification", 1)[1].split(
        "- name: Upload QA Report", 1
    )[0]
    for term in (
        "VISUAL_CERTIFICATION_FAIL", "VISUAL_CERTIFICATION_PASS", "pages:",
        "interactions:", "Research tickers:", "tabs:", "screenshots:",
        "P1", "P2", "P3", "audit_results/visual_crawl",
    ):
        assert term in summary


def test_final_status_is_decided_only_from_completed_summary_after_upload():
    final = SOURCE.split("Set Visual Crawler certification result", 1)[1]
    assert "atlas_visual_qa_summary.json" in final
    assert "report.get(\"finished\")" in final
    assert "VISUAL_CERTIFICATION_FAIL" in final
    assert "VISUAL_CERTIFICATION_PASS" in final
    assert "raise SystemExit(1)" in final
