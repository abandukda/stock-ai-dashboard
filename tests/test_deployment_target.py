import pytest

from agents.deployment_target import (
    DeploymentTargetValidationError,
    PRODUCTION_ATLAS_URL,
    canonical_production_url,
)


def test_valid_production_url_requires_no_playwright_import():
    assert canonical_production_url(PRODUCTION_ATLAS_URL) == PRODUCTION_ATLAS_URL


def test_harmless_production_url_variations_normalize_to_governed_origin():
    assert canonical_production_url("STOCK-AI-DASHBOARD.STREAMLIT.APP") == PRODUCTION_ATLAS_URL
    assert canonical_production_url("https://stock-ai-dashboard.streamlit.app") == PRODUCTION_ATLAS_URL
    assert canonical_production_url("https://stock-ai-dashboard.streamlit.app/?ignored=1") == PRODUCTION_ATLAS_URL


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("", "ATLAS_PRODUCTION_URL_MISSING"),
        ("not a url", "NON_STREAMLIT_APP_ORIGIN"),
        ("http://localhost:8501", "LOCALHOST_NOT_ALLOWED_IN_PRODUCTION"),
        ("http://stock-ai-dashboard.streamlit.app", "PRODUCTION_URL_REQUIRES_HTTPS"),
        ("https://atlas-production-7f3.streamlit.app", "RETIRED_ATLAS_DEPLOYMENT_TARGET"),
        ("https://wrong-atlas.streamlit.app", "UNAUTHORIZED_STREAMLIT_APP_TARGET"),
        ("https://stock-ai-dashboard.streamlit.app/research", "UNEXPECTED_PRODUCTION_URL_PATH"),
        ("https://user@stock-ai-dashboard.streamlit.app", "MALFORMED_PRODUCTION_URL"),
        ("https://stock-ai-dashboard.streamlit.app:not-a-port", "MALFORMED_PRODUCTION_URL"),
    ],
)
def test_invalid_production_targets_fail_closed(url, reason):
    with pytest.raises(DeploymentTargetValidationError) as exc:
        canonical_production_url(url)
    assert exc.value.reason == reason


def test_runtime_module_uses_dependency_light_validator():
    source = open("agents/atlas_runtime_qa_v3.py", encoding="utf-8").read()
    assert "from agents.deployment_target import" in source
