from pathlib import Path


def test_authenticated_v31_has_invalid_audit_guard():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert '"AUDIT_INVALID"' in source
    assert "authenticated_dashboard_detected" in source
    assert "len(page_results) >= 3" in source


def test_authenticated_v31_captures_request_urls():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert '"url": response.url' in source
    assert '"status": response.status' in source
    assert '"resource_type": response.request.resource_type' in source


def test_workflow_executes_v3_unbuffered():
    source = Path(".github/workflows/atlas-runtime-qa-v3.yml").read_text(
        encoding="utf-8"
    )
    assert "python -u -m agents.atlas_runtime_qa_v3" in source
    assert "ATLAS_AUDIT_PASSWORD" in source
    assert "PYTHONUNBUFFERED" in source


def test_workflow_uses_pinned_chromium_without_apt_dependency_install():
    source = Path(".github/workflows/atlas-runtime-qa-v3.yml").read_text(
        encoding="utf-8"
    )

    assert "cache: pip" in source
    assert "cache-dependency-path: requirements-runtime-qa.txt" in source
    assert "python -m playwright install chromium" in source
    assert "playwright.chromium.launch(headless=True)" in source
    assert "playwright install --with-deps" not in source
    assert "apt-get" not in source
    assert "~/.cache/ms-playwright" not in source
    assert "timeout-minutes: 20" in source
