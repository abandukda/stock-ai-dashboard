from pathlib import Path


WORKFLOW = Path(".github/workflows/overnight_scan.yml").read_text(encoding="utf-8")


def test_manual_dispatch_preserves_selected_branch_instead_of_forcing_main():
    assert "github.event_name == 'workflow_dispatch' && github.ref_name || 'main'" in WORKFLOW
    assert "Force main branch checkout" not in WORKFLOW
    assert "git checkout -B main" not in WORKFLOW
    assert "git fetch origin main" not in WORKFLOW


def test_checkout_diagnostics_bind_audit_and_scan_to_same_commit():
    for marker in (
        "github.ref=", "github.ref_name=", "checked_out_sha=", "branch=",
        "audit_script_exists=true", "ATLAS_SOURCE_COMMIT_SHA=$(git rev-parse HEAD)",
    ):
        assert marker in WORKFLOW
    assert WORKFLOW.index("Record checkout diagnostics") < WORKFLOW.index("Enforce governed-provider boundary")
    assert WORKFLOW.index("Enforce governed-provider boundary") < WORKFLOW.index("Run overnight scan")


def test_failed_scan_still_uploads_governed_market_diagnostics():
    upload = WORKFLOW[WORKFLOW.index("- name: Upload exact scan candidate"):]
    assert "if: always()" in upload
    assert "governed_market_acquisition_diagnostics.json" in upload
    assert "if-no-files-found: warn" in upload
