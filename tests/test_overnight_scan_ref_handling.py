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
        "audit_script_exists=true", "ATLAS_SOURCE_COMMIT_SHA=${checked_out_sha}",
        "ATLAS_SCANNER_SHA256=${scanner_sha}",
    ):
        assert marker in WORKFLOW
    assert WORKFLOW.index("Record checkout diagnostics") < WORKFLOW.index("Enforce governed-provider boundary")
    assert WORKFLOW.index("Enforce governed-provider boundary") < WORKFLOW.index("Run overnight scan")


def test_failed_scan_still_uploads_governed_market_diagnostics():
    upload = WORKFLOW[WORKFLOW.index("- name: Upload exact scan candidate"):]
    assert "if: always()" in upload
    assert "path: audit_results/candidate_artifacts" in upload
    assert "GOVERNED_MARKET_DIAGNOSTICS_MISSING" in Path(
        "scripts/validate_candidate_artifact_provenance.py"
    ).read_text(encoding="utf-8")
    assert "if-no-files-found: warn" in upload


def test_candidate_directory_is_cleaned_and_validated_before_upload():
    clean = WORKFLOW.index("Prepare clean candidate output directory")
    scan = WORKFLOW.index("Run overnight scan")
    validate = WORKFLOW.index("Validate candidate provenance and governed-provider gates")
    upload = WORKFLOW.index("Upload exact scan candidate")
    assert clean < scan < validate < upload
    assert "rm -rf audit_results/candidate_artifacts" in WORKFLOW
    assert "path: audit_results/candidate_artifacts" in WORKFLOW
    assert '--expected-sha "$ATLAS_SOURCE_COMMIT_SHA"' in WORKFLOW


def test_wrong_ref_checkout_is_rejected():
    assert 'if [ "${checked_out_sha}" != "${{ github.sha }}" ]; then' in WORKFLOW
    assert "does not match triggering SHA" in WORKFLOW
