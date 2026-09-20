from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shadow_workflow_is_manual_non_production_and_precommercial():
    path = ROOT / ".github" / "workflows" / "atlas_provider_shadow_validation.yml"
    rendered = path.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in rendered
    assert "provider-shadow:" in rendered
    assert "ATLAS_TRANSCRIPT_LICENSE_STATE: DEVELOPMENT_PRECOMMERCIAL" in rendered
    assert "CERTIFY_AND_PROMOTE" not in rendered
    assert "overnight_market_scan.py" not in rendered
    assert "FMP_API_KEY" not in rendered


def test_shadow_script_does_not_import_canonical_decision_or_publication_engines():
    source = (ROOT / "scripts" / "provider_migration_readiness.py").read_text(encoding="utf-8")
    for forbidden in (
        "canonical_investment_evaluation", "full_universe_decision_publication",
        "publication_governance", "overnight_market_scan",
    ):
        assert forbidden not in source
