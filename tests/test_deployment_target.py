import pytest

from agents.deployment_target import (
    DeploymentTargetValidationError,
    PRODUCTION_ATLAS_URL,
    canonical_production_url,
)


def test_valid_production_url_requires_no_playwright_import():
    assert canonical_production_url(PRODUCTION_ATLAS_URL) == PRODUCTION_ATLAS_URL


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("", "ATLAS_PRODUCTION_URL_MISSING"),
        ("not a url", "NON_STREAMLIT_APP_ORIGIN"),
        ("http://localhost:8501", "LOCALHOST_NOT_ALLOWED_IN_PRODUCTION"),
        ("http://stock-ai-dashboard.streamlit.app", "PRODUCTION_URL_REQUIRES_HTTPS"),
    ],
)
def test_invalid_production_targets_fail_closed(url, reason):
    with pytest.raises(DeploymentTargetValidationError) as exc:
        canonical_production_url(url)
    assert exc.value.reason == reason


def test_https_streamlit_production_url_passes():
    assert canonical_production_url("https://atlas-example.streamlit.app") == "https://atlas-example.streamlit.app/"


def test_runtime_module_uses_dependency_light_validator():
    source = open("agents/atlas_runtime_qa_v3.py", encoding="utf-8").read()
    assert "from agents.deployment_target import" in source
