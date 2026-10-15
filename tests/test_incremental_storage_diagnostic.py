from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gateway_registers_provider_free_storage_diagnostic():
    source = (ROOT / ".github/workflows/atlas_stable_report_card_gateway.yml").read_text()
    assert "storage_diagnostic" in source
    assert "ATLAS_STORAGE_DIAGNOSTIC_ONCE:$SOURCE_SHA" in source
    assert "test -z \"${FINNHUB_API_KEY:-}\"" in source
    assert "atlas-worker-1" in source


def test_diagnostic_excludes_protected_and_temporary_storage():
    source = (ROOT / "scripts/diagnose_incremental_storage.py").read_text()
    for path in (
        "/tmp",
        "/var/tmp",
        "/mnt/atlas_report_card_primary",
        "/mnt/atlas_report_card_backup",
    ):
        assert path in source
    assert '"provider_calls": 0' in source
    assert '"report_card_ledger_access": 0' in source
    assert '"sentinel_transitions": 0' in source
