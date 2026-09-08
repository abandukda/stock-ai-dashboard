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
    assert 'data-atlas-login-ready="true"' in marker_source


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"fatal_exception": True}, ("BOOTSTRAP_EXCEPTION", "DEPLOYMENT_DEFECT")),
        ({"unavailable": True}, ("UNAVAILABLE", "APP_AVAILABILITY_DEFECT")),
        ({"marker_sha": "a" * 40}, ("DEPLOYMENT_UPDATING", "DEPLOYMENT_NOT_READY")),
        ({"password_ready": True, "login_heading_ready": True}, ("LOGIN_READY", "PASS")),
        ({"login_heading_ready": True, "login_button_ready": True}, ("LOGIN_READY", "PASS")),
        ({"dashboard_ready": True}, ("APP_READY", "PASS")),
        ({"updating": True, "marker_sha": ""}, ("DEPLOYMENT_UPDATING", "DEPLOYMENT_NOT_READY")),
        ({}, ("SETTLING", "IN_PROGRESS")),
    ],
)
def test_bootstrap_health_contract(kwargs, expected):
    values = {
        "marker_sha": EXPECTED_SHA,
        "expected_sha": EXPECTED_SHA,
        "password_ready": False,
        "login_marker_ready": False,
        "login_heading_ready": False,
        "login_button_ready": False,
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


def test_first_probe_miss_then_stable_login_passes(monkeypatch, tmp_path):
    sequence = [
        {
            "state": "SETTLING", "classification": "IN_PROGRESS",
            "deployed_source_sha": EXPECTED_SHA, "expected_source_sha": EXPECTED_SHA,
            "password_ready": False, "login_marker_ready": False,
            "login_heading_ready": False, "login_button_ready": False,
            "dashboard_ready": False, "fatal_exception": False,
            "sha_mismatch": False, "login_signal_contradiction": False,
        },
        {
            "state": "LOGIN_READY", "classification": "PASS",
            "deployed_source_sha": EXPECTED_SHA, "expected_source_sha": EXPECTED_SHA,
            "password_ready": False, "login_marker_ready": True,
            "login_heading_ready": True, "login_button_ready": True,
            "dashboard_ready": False, "fatal_exception": False,
            "sha_mismatch": False, "login_signal_contradiction": False,
        },
        {
            "state": "LOGIN_READY", "classification": "PASS",
            "deployed_source_sha": EXPECTED_SHA, "expected_source_sha": EXPECTED_SHA,
            "password_ready": True, "login_marker_ready": True,
            "login_heading_ready": True, "login_button_ready": True,
            "dashboard_ready": False, "fatal_exception": False,
            "sha_mismatch": False, "login_signal_contradiction": False,
        },
    ]

    async def capture(_page, _expected_sha):
        return sequence.pop(0)

    class Page:
        async def wait_for_timeout(self, _milliseconds):
            return None

    monkeypatch.setattr(qa, "_capture_deployed_readiness", capture)
    result = asyncio.run(qa._deployed_readiness_gate(
        Page(), expected_sha=EXPECTED_SHA, output_dir=tmp_path,
    ))
    assert result["state"] == "LOGIN_READY"
    assert result["stable_checks"] == 2
    assert [item["state"] for item in result["observations"]] == [
        "SETTLING", "LOGIN_READY", "LOGIN_READY",
    ]


def test_stable_authenticated_dashboard_passes(monkeypatch, tmp_path):
    async def capture(_page, _expected_sha):
        return {
            "state": "APP_READY", "classification": "PASS",
            "deployed_source_sha": EXPECTED_SHA, "expected_source_sha": EXPECTED_SHA,
            "password_ready": False, "dashboard_ready": True,
            "fatal_exception": False, "sha_mismatch": False,
        }

    class Page:
        async def wait_for_timeout(self, _milliseconds):
            return None

    monkeypatch.setattr(qa, "_capture_deployed_readiness", capture)
    result = asyncio.run(qa._deployed_readiness_gate(
        Page(), expected_sha=EXPECTED_SHA, output_dir=tmp_path,
    ))
    assert result["state"] == "APP_READY"
    assert result["stable_checks"] == 2


def test_timeout_distinguishes_qa_contradiction_update_and_unavailable():
    contradiction = qa._timeout_readiness_result({
        "state": "SETTLING", "deployed_source_sha": EXPECTED_SHA,
        "login_signal_contradiction": True,
    })
    assert (contradiction["state"], contradiction["classification"]) == ("SETTLING", "QA_DEFECT")

    updating = qa._timeout_readiness_result({
        "state": "DEPLOYMENT_UPDATING", "deployed_source_sha": "UNKNOWN",
    })
    assert updating["classification"] == "DEPLOYMENT_NOT_READY"

    unavailable = qa._timeout_readiness_result({
        "state": "UNAVAILABLE", "deployed_source_sha": "UNKNOWN",
    })
    assert (unavailable["state"], unavailable["classification"]) == (
        "UNAVAILABLE", "APP_AVAILABILITY_DEFECT",
    )


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
    assert 'DEPLOYED_READINESS_TIMEOUT_SECONDS = int(os.getenv("ATLAS_QA_READINESS_TIMEOUT_SECONDS", "180"))' in source
    assert 'except DeploymentReadinessError as exc:' in source
    assert 'base["status"] = exc.classification' in source
    auth_source = source[source.index("async def _authenticate_and_confirm"):source.index("async def _open_and_authenticate")]
    assert "_rendered_streamlit_exception(page)" in auth_source
    assert 'DeploymentReadinessError("DEPLOYMENT_DEFECT"' in auth_source
    assert "traceback.format_exc" not in auth_source


def test_public_streamlit_url_is_normalized_without_inventing_host_route():
    assert qa._canonical_streamlit_url("atlas-production-7f3.streamlit.app?x=secret") == (
        "https://atlas-production-7f3.streamlit.app/"
    )
    assert qa._canonical_streamlit_url("http://atlas-production-7f3.streamlit.app/research") == (
        "https://atlas-production-7f3.streamlit.app/research"
    )


@pytest.mark.parametrize("target,reason", [
    ("https://share.streamlit.io/app/stock-ai-dashboard/", "GENERIC_STREAMLIT_SHARE_SHELL"),
    ("https://stock-ai-dashboard.streamlit.app", "RETIRED_ATLAS_DEPLOYMENT_TARGET"),
    ("https://example.com/atlas", "NON_STREAMLIT_APP_ORIGIN"),
    ("", "ATLAS_PRODUCTION_URL_MISSING"),
])
def test_generic_stale_or_missing_deployment_target_fails_fast(target, reason, monkeypatch):
    monkeypatch.setattr(qa, "DEFAULT_URL", "")
    with pytest.raises(qa.DeploymentTargetError) as captured:
        qa._canonical_streamlit_url(target)
    assert captured.value.diagnostics["reason"] == reason


def test_open_records_resolved_host_transition_and_wake(monkeypatch):
    class Response:
        status = 200

    class Page:
        url = "https://atlas-production-7f3.streamlit.app/"
        async def goto(self, url, **_kwargs):
            self.url = url
            return Response()

    async def shell(_page): return None
    async def wake(_page): return True
    monkeypatch.setattr(qa, "_wait_for_streamlit_shell", shell)
    monkeypatch.setattr(qa, "_wake_if_needed", wake)
    result = asyncio.run(qa._open_streamlit_origin(Page(), "atlas-production-7f3.streamlit.app"))
    assert result == {
        "requested_url": "https://atlas-production-7f3.streamlit.app/",
        "resolved_url": "https://atlas-production-7f3.streamlit.app/",
        "document_status": 200,
        "streamlit_public_host": True,
        "wake_control_used": True,
        "navigation_attempts": 1,
        "navigation_error_categories": [],
    }


def test_open_retries_transient_navigation_failure_without_skipping_login(monkeypatch):
    class Response: status = 200
    class Page:
        url = ""
        calls = 0
        async def goto(self, url, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("transient hosting shell")
            self.url = url
            return Response()
        async def wait_for_timeout(self, _milliseconds): return None
    async def shell(_page): return None
    async def wake(_page): return False
    monkeypatch.setattr(qa, "_wait_for_streamlit_shell", shell)
    monkeypatch.setattr(qa, "_wake_if_needed", wake)
    result = asyncio.run(qa._open_streamlit_origin(Page(), "https://atlas-production-7f3.streamlit.app"))
    assert result["navigation_attempts"] == 2
    assert result["navigation_error_categories"] == ["TimeoutError"]


def test_redirect_to_generic_share_shell_is_recorded_and_rejected(tmp_path):
    class Response: status = 200
    class Page:
        url = ""
        async def goto(self, _url, **_kwargs):
            self.url = "https://share.streamlit.io/app/stock-ai-dashboard/"
            return Response()
    with pytest.raises(qa.DeploymentTargetError) as captured:
        asyncio.run(qa._open_streamlit_origin(
            Page(), "https://atlas-production-7f3.streamlit.app", tmp_path,
        ))
    recorded = json.loads((tmp_path / "deployment_target.json").read_text())
    assert recorded["reason"] == "GENERIC_STREAMLIT_SHARE_SHELL"
    assert recorded["resolved_target_url"] == "https://share.streamlit.io/app/stock-ai-dashboard/"
    assert captured.value.classification == "DEPLOYMENT_TARGET_INVALID"


@pytest.mark.parametrize("path,status", [
    ("/api/v2/user/details", 401),
    ("/api/v1/app/event/open", 404),
    ("/_stcore/health", 404),
    ("/_stcore/stream", 401),
])
def test_hosting_bootstrap_responses_are_not_product_defects(path, status):
    result = qa._classify_failed_request(
        f"https://atlas-production-7f3.streamlit.app{path}?redacted=yes", status,
    )
    assert result["relevance"] in {"NOT_ATLAS_FUNCTIONALITY", "HOSTING_READINESS_ONLY"}
    assert "redacted" not in str(result)
