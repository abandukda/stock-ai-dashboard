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
