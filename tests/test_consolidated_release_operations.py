from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_preview_checklist_is_separate_exact_branch_and_provider_free():
    text = (ROOT / "docs/operations/ATLAS_PREVIEW_ACTIVATION_CHECKLIST.md").read_text()
    assert "codex/consolidated-release" in text
    assert "new private preview app" in text
    assert "Do not install Finnhub or external-model credentials" in text
    assert "Never mount production raw or" in text
    assert "ATLAS_CUSTOMER_REPORT_CARD_ENABLED=false" in text


def test_daily_readiness_truthfully_describes_dst_gate_and_disabled_live_path():
    workflow = (ROOT / ".github/workflows/atlas_daily_incremental_buy_now.yml").read_text()
    documentation = (ROOT / "docs/operations/ATLAS_DAILY_OPERATION_READINESS.md").read_text()
    assert 'cron: "5 22 * * 1-5"' in workflow
    assert 'cron: "5 23 * * 1-5"' in workflow
    assert "cancel-in-progress: false" in workflow
    assert "live-operation-disabled" in workflow
    assert "not evidence of acquisition, certification, or publication" in documentation
    assert "ATLAS_DAILY_BUY_NOW_LIVE_ENABLED` must remain false" in documentation


def test_customer_qa_uploads_shareable_visual_zip_and_required_review_files():
    workflow = (ROOT / ".github/workflows/atlas_customer_experience_autonomous_qa.yml").read_text()
    builder = (ROOT / "scripts/build_major_release_visual_review.py").read_text()
    assert "--zip-output artifacts/atlas-major-release-visual-review-" in workflow
    assert "artifacts/atlas-major-release-visual-review-${{ steps.context.outputs.candidate_sha }}.zip" in workflow
    for name in (
        "README.md", "QA_RESULTS.md", "FEATURE_COMPLETION.md", "DATA_TRUTH.md",
        "KNOWN_LIMITATIONS.md", "CLAUDE_REVIEW_PROMPT.md",
    ):
        assert name in builder
