from pathlib import Path


WORKFLOW = Path(".github/workflows/atlas_internal_prospective_report_card.yml")


def test_workflow_is_manual_internal_only_and_has_no_provider_credentials():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "schedule:" not in source
    assert "environment: atlas-internal-report-card" in source
    assert "FINNHUB_API_KEY" not in source
    assert "customer_report_card_visible'] is False" in source
    assert "validate_storage" in source
    assert "atlas-worker-1" in source
    assert "environment: atlas-internal-report-card" in source


def test_workflow_requires_durable_primary_and_backup_outside_runner_storage():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "ATLAS_REPORT_CARD_DURABLE_ROOT" in source
    assert "ATLAS_REPORT_CARD_BACKUP_ROOT" in source
    assert "MUST_NOT_USE_EPHEMERAL" not in source  # enforced by the Python command, not weakened in YAML
    assert '"$GITHUB_WORKSPACE"*|"$RUNNER_TEMP"*' in source


def test_workflow_consumes_certified_artifact_without_acquisition():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "actions/download-artifact@v4" in source
    assert "expected_candidate_digest" in source
    assert "expected_publication_digest" in source
    assert "expected_source_sha" in source
    assert "run_finnhub" not in source
    assert "provider_calls'] == 0" in source
    assert "closure_run_id" in source
    assert "closure_artifact_name" in source
    assert "historical_run_identity" in source
    assert "scripts/build_report_card_capture_handoff.py" in source
    assert "--capture-handoff audit_results/report_card_capture_handoff.json" in source


def test_validation_mode_cannot_activate_or_download_publication():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "inputs.operation == 'validate_storage'" in source
    assert "scripts/validate_report_card_storage.py" in source
    assert "operational_activation_created" not in source  # asserted by the validator report itself


def test_self_hosted_paths_require_and_use_python3():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "command -v python3" in source
    assert "python3 --version" in source
    assert "python3 scripts/validate_report_card_storage.py" in source
    assert "python3 scripts/run_internal_prospective_report_card.py" in source
    assert "\n          python " not in source
