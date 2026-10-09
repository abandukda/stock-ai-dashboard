from pathlib import Path

import pytest

from agents import atlas_runtime_qa_v3 as qa


@pytest.mark.parametrize("target", ["http://127.0.0.1:8501", "http://localhost:8501"])
def test_governed_exact_candidate_mode_accepts_only_supported_loopback(target):
    assert qa._canonical_streamlit_url(target, allow_local_exact_candidate=True) == target + "/"


@pytest.mark.parametrize("target", ["http://127.0.0.1:8501", "http://localhost:8501"])
def test_localhost_is_rejected_by_default(target):
    with pytest.raises(qa.DeploymentTargetError):
        qa._canonical_streamlit_url(target)


@pytest.mark.parametrize("target", [
    "http://example.com:8501",
    "http://192.0.2.10:8501",
    "http://localhost:9999",
    "ftp://localhost:8501",
    "http://user:secret@localhost:8501",
])
def test_exact_candidate_mode_rejects_remote_unsupported_or_malformed_targets(target):
    with pytest.raises(qa.DeploymentTargetError):
        qa._canonical_streamlit_url(target, allow_local_exact_candidate=True)


@pytest.mark.parametrize("target", [
    "https://wrong-atlas.streamlit.app",
    "https://atlas-production-7f3.streamlit.app",
])
def test_wrong_streamlit_production_slug_remains_rejected_in_all_modes(target):
    with pytest.raises(qa.DeploymentTargetError):
        qa._canonical_streamlit_url(target, allow_local_exact_candidate=True)


def test_cli_and_complete_call_path_propagate_explicit_mode():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert 'parser.add_argument(\n        "--exact-candidate-localhost"' in source
    assert "exact_candidate_localhost=args.exact_candidate_localhost" in source
    assert "allow_local_exact_candidate=exact_candidate_localhost" in source
    assert "allow_local_exact_candidate=allow_local_exact_candidate" in source


def test_only_exact_candidate_workflow_enables_localhost_mode():
    autonomous = Path(".github/workflows/atlas_customer_experience_autonomous_qa.yml").read_text(encoding="utf-8")
    production = Path(".github/workflows/atlas-runtime-qa-v3.yml").read_text(encoding="utf-8")
    assert autonomous.count("--exact-candidate-localhost") == 2
    assert "--exact-candidate-localhost" not in production


def test_production_target_remains_strict_even_when_local_mode_code_exists():
    assert qa._canonical_streamlit_url("https://stock-ai-dashboard.streamlit.app/") == (
        "https://stock-ai-dashboard.streamlit.app/"
    )
    with pytest.raises(qa.DeploymentTargetError):
        qa._canonical_streamlit_url("http://stock-ai-dashboard.streamlit.app/")
