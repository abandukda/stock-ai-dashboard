"""Deployment source/health checks that run before authenticated product QA."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agents import atlas_runtime_qa_v3 as qa


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA = "e" * 40


def test_source_marker_precedes_diagnostic_import_and_login_gate():
    marker_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'data-atlas-qa="deployment-readiness"' in marker_source
    assert 'data-atlas-source-sha=' in marker_source
    assert marker_source.index("st.set_page_config(") < marker_source.index(
        'data-atlas-qa="deployment-readiness"'
    )
    assert marker_source.index('data-atlas-qa="deployment-readiness"') < marker_source.index(
        "from services.research_render_diagnostics import ("
    ) < marker_source.index("def dashboard_login_gate")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"fatal_exception": True}, ("BOOTSTRAP_EXCEPTION", "DEPLOYMENT_DEFECT")),
        ({"unavailable": True}, ("UNAVAILABLE", "APP_AVAILABILITY_DEFECT")),
        ({"marker_sha": "a" * 40}, ("DEPLOYMENT_UPDATING", "DEPLOYMENT_NOT_READY")),
        ({"password_ready": True}, ("LOGIN_READY", "PASS")),
        ({"dashboard_ready": True}, ("APP_READY", "PASS")),
        ({"updating": True, "marker_sha": ""}, ("DEPLOYMENT_UPDATING", "DEPLOYMENT_NOT_READY")),
    ],
)
def test_bootstrap_health_contract(kwargs, expected):
    values = {
        "marker_sha": EXPECTED_SHA,
        "expected_sha": EXPECTED_SHA,
        "password_ready": False,
        "dashboard_ready": False,
        "fatal_exception": False,
        "updating": False,
        "unavailable": False,
    }
    values.update(kwargs)
    assert qa.classify_deployed_health(**values) == expected
    assert expected[0] in qa.DEPLOYED_HEALTH_STATES


def test_bootstrap_exception_location_is_sanitized():
    visible = (
        "ImportError: provider-secret-like-message\nTraceback:\n"
        'File "/mount/src/stock-ai-dashboard/app.py", line 28, in <module>'
    )
    result = qa._sanitized_bootstrap_location(visible)
    assert result == {
        "exception_class": "ImportError",
        "filename": "app.py",
        "function": "<module>",
        "line": 28,
        "location_fingerprint": result["location_fingerprint"],
    }
    serialized = json.dumps(result)
    for forbidden in ("provider-secret", "message", "Traceback", "/mount/src"):
        assert forbidden not in serialized


def test_readiness_requires_two_stable_checks(monkeypatch, tmp_path):
    checks = []

    async def capture(_page, _expected_sha):
        checks.append(True)
        return {
            "state": "LOGIN_READY", "classification": "PASS",
            "deployed_source_sha": EXPECTED_SHA,
            "expected_source_sha": EXPECTED_SHA,
            "password_ready": True, "dashboard_ready": False,
            "fatal_exception": False,
        }

    class Page:
        async def wait_for_timeout(self, _milliseconds):
            return None

    monkeypatch.setattr(qa, "_capture_deployed_readiness", capture)
    result = asyncio.run(qa._deployed_readiness_gate(
        Page(), expected_sha=EXPECTED_SHA, output_dir=tmp_path,
    ))
    assert len(checks) == 2
    assert result["stable_checks"] == 2
    assert result["status"] == "PASS"


def test_fatal_exception_fails_before_stability_or_login_timeout(monkeypatch, tmp_path):
    checks = []

    async def capture(_page, _expected_sha):
        checks.append(True)
        return {
            "state": "BOOTSTRAP_EXCEPTION", "classification": "DEPLOYMENT_DEFECT",
            "deployed_source_sha": "UNKNOWN", "expected_source_sha": EXPECTED_SHA,
            "password_ready": False, "dashboard_ready": False,
            "fatal_exception": True,
            "exception": {"exception_class": "ImportError", "filename": "app.py", "function": "<module>", "line": 28, "location_fingerprint": "abc"},
        }

    class Page:
        async def screenshot(self, **_kwargs):
            return None

        async def wait_for_timeout(self, _milliseconds):
            raise AssertionError("fatal bootstrap exception must not poll")

    monkeypatch.setattr(qa, "_capture_deployed_readiness", capture)
    with pytest.raises(qa.DeploymentReadinessError) as captured:
        asyncio.run(qa._deployed_readiness_gate(
            Page(), expected_sha=EXPECTED_SHA, output_dir=tmp_path,
        ))
    assert captured.value.classification == "DEPLOYMENT_DEFECT"
    assert len(checks) == 1


def test_targeted_and_full_paths_supply_checkout_sha_and_preserve_login_timeout():
    source = (ROOT / "agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert source.count('expected_sha=versions["source_commit"]') == 2
    assert "LOGIN_TIMEOUT_SECONDS = 240" in source
    assert "DEPLOYED_READINESS_TIMEOUT_SECONDS = 60" in source
    assert 'except DeploymentReadinessError as exc:' in source
    assert 'base["status"] = exc.classification' in source
    auth_source = source[source.index("async def _authenticate_and_confirm"):source.index("async def _open_and_authenticate")]
    assert "_rendered_streamlit_exception(page)" in auth_source
    assert 'DeploymentReadinessError("DEPLOYMENT_DEFECT"' in auth_source
    assert "traceback.format_exc" not in auth_source
