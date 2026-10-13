from pathlib import Path


def test_release_smoke_requires_distinct_admin_and_viewer_secrets():
    source = Path(".github/workflows/atlas_release_smoke_bounded.yml").read_text(encoding="utf-8")
    assert "ATLAS_AUDIT_PASSWORD: ${{ secrets.ATLAS_INTERNAL_QA_PASSWORD }}" in source
    assert "APP_PASSWORD: ${{ secrets.ATLAS_INTERNAL_QA_PASSWORD }}" in source
    assert "ATLAS_VIEWER_QA_PASSWORD: ${{ secrets.ATLAS_AUDIT_PASSWORD }}" in source
    assert 'test "$ATLAS_AUDIT_PASSWORD" != "$ATLAS_VIEWER_QA_PASSWORD"' in source
    assert "Admin and viewer QA credentials must be independent" in source
