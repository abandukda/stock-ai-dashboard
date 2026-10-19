from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_preview_checklist_is_separate_exact_branch_and_provider_free():
    text = (ROOT / "docs/operations/ATLAS_PREVIEW_ACTIVATION_CHECKLIST.md").read_text()
    assert "codex/preview-milestone3-0758fac" in text
    assert "0758fac72209ab0642e9f1a431db092d1a699119" in text
    assert "new private preview app" in text
    assert "GUEST_PASSWORD` or `VIEWER_PASSWORD" in text
    assert "auto-authenticates as admin" in text
    assert "ATLAS_REQUIRE_AUTH=true" in text
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
    assert "visual_baseline_sha:" in workflow
    assert "VISUAL_BASELINE_ARTIFACT_NOT_EXACTLY_ONE" in workflow
    assert '--before-screenshot-root "$ATLAS_QA_OUTPUT/visual-baseline/browser/required"' in workflow
    assert '--before-screenshot-root "$ATLAS_QA_OUTPUT/visual-baseline/browser/report-card"' in workflow
    assert '--before-source-sha "$VISUAL_BASELINE_SHA"' in workflow
    assert 'git fetch --no-tags --depth=1 origin "$BASELINE_SHA"' in workflow
    for name in (
        "README.md", "QA_RESULTS.md", "FEATURE_COMPLETION.md", "DATA_TRUTH.md",
        "KNOWN_LIMITATIONS.md", "SOURCE_IDENTITY.md", "CLAUDE_REVIEW_PROMPT.md",
    ):
        assert name in builder


def test_milestone3_contabo_runbook_preserves_source_and_requires_transfer_approval():
    text = (ROOT / "docs/operations/ATLAS_CONTABO_MIGRATION_READINESS.md").read_text()
    assert "Never delete or alter the DigitalOcean source" in text
    assert "explicit owner approval" in text
    assert "fresh GitHub runner registration token" in text
    assert "sha256sum" in text
    assert "licensed evidence transfer is not authorized" in text


def test_48gb_certification_runbook_is_bounded_and_provider_free():
    text = (ROOT / "docs/operations/ATLAS_48GB_CERTIFICATION_READINESS.md").read_text()
    assert "No Finnhub calls" in text
    assert "5 GiB" in text
    assert "8 GiB" in text
    assert "64-security" in text
    assert "separate owner authorization" in text
    assert "production publication" in text


def test_hosted_preview_authentication_can_fail_closed():
    source = (ROOT / "app.py").read_text()
    assert 'ATLAS_REQUIRE_AUTH = ' in source
    assert 'if ATLAS_REQUIRE_AUTH:' in source
    assert 'Authentication is required, but no admin or viewer password is configured.' in source


def test_ask_suggestions_use_callback_safe_widget_state_updates():
    source = (ROOT / "app.py").read_text()
    assert 'def _apply_ask_suggestion(value):' in source
    assert 'on_click=_apply_ask_suggestion' in source
    assert 'args=(_suggestion,)' in source
    assert 'if _suggestion_cols[_index % 2].button' not in source


def test_home_preserves_required_strongest_opportunities_contract():
    source = (ROOT / "app.py").read_text()
    assert "Strongest Opportunities · Today's Highest-Conviction" in source
