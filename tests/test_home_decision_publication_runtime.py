from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_overnight_scan_supplies_controlled_twelve_publication_environment():
    workflow = (ROOT / ".github/workflows/overnight_scan.yml").read_text(encoding="utf-8")
    assert "TWELVE_DATA_API_KEY: ${{ secrets.TWELVE_DATA_API_KEY }}" in workflow
    assert 'TWELVE_DATA_ENABLED: "true"' in workflow
    assert 'ATLAS_DATA_MODE: "INTERNAL_TRIAL"' in workflow


def test_home_runtime_rejects_stale_policy_cache_and_consumes_published_evaluation():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    story = (ROOT / "engines/home_guidance_story_v1.py").read_text(encoding="utf-8")
    assert "GUIDANCE_POLICY_VERSION" in app
    assert 'current_evaluations = {}' in app
    assert 'row.get("canonical_investment_evaluation")' in story
    assert 'persisted_guidance.get("policy_version") != GUIDANCE_POLICY_VERSION' in story
