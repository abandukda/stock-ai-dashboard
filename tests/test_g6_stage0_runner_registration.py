import json
from pathlib import Path

import pytest

from scripts.run_g6_stage0 import EXPECTED_MANIFEST_SHA, EXPECTED_SOURCE_SHA, EXPECTED_TOKEN, execute, verify


PACKAGE = Path("output/joint/r2_reconciliation/g6_stage0_approval.json")
WORKFLOW = Path(".github/workflows/atlas_g6_stage0_financial_history.yml")


def test_frozen_package_passes_runner_identity_gate():
    package = json.loads(PACKAGE.read_text())
    scope = verify(package, source_sha=EXPECTED_SOURCE_SHA, token=EXPECTED_TOKEN)
    assert len(scope) == 11
    assert {row["endpoint"] for row in scope} == {"/stock/financials-reported"}
    assert {row["parameters"]["freq"] for row in scope} == {"annual"}


def test_runner_rejects_wrong_source_manifest_or_token():
    package = json.loads(PACKAGE.read_text())
    with pytest.raises(PermissionError, match="SOURCE_SHA"):
        verify(package, source_sha="wrong", token=EXPECTED_TOKEN)
    changed = json.loads(json.dumps(package)); changed["manifest"]["request_cap"] = 13
    with pytest.raises(PermissionError, match="MANIFEST_SHA"):
        verify(changed, source_sha=EXPECTED_SOURCE_SHA, token=EXPECTED_TOKEN)
    with pytest.raises(PermissionError, match="TOKEN"):
        verify(package, source_sha=EXPECTED_SOURCE_SHA, token="wrong")


def test_workflow_is_manual_protected_and_does_not_register_retry_or_parallelism():
    source = WORKFLOW.read_text()
    assert "workflow_dispatch:" in source and "schedule:" not in source and "push:" not in source
    assert "environment: atlas-premium-g6-stage0" in source
    assert "secrets.FINNHUB_API_KEY" in source
    assert EXPECTED_SOURCE_SHA in source and EXPECTED_MANIFEST_SHA in source
    assert "cancel-in-progress: false" in source
    assert "scripts/run_g6_stage0.py" in source
    assert "matrix:" not in source


def test_runner_persists_each_raw_response_and_sanitizes_headers(monkeypatch, tmp_path):
    calls = []
    class Response:
        status_code = 200
        content = b'{"data": []}'
        headers = {"Content-Type": "application/json", "Authorization": "secret", "X-RateLimit-Remaining": "59"}
    class Session:
        def mount(self, *args): pass
        def get(self, url, *, params, timeout):
            calls.append((url, params, timeout)); return Response()
    monkeypatch.setattr("scripts.run_g6_stage0.requests.Session", Session)
    monkeypatch.setattr("scripts.run_g6_stage0.time.sleep", lambda _: None)
    monkeypatch.setenv("G6_EXECUTE", "1")
    summary = execute(PACKAGE, tmp_path / "run", source_sha=EXPECTED_SOURCE_SHA, token=EXPECTED_TOKEN, api_key="hidden")
    assert summary["provider_calls"] == 11 and len(calls) == 11
    assert len(list((tmp_path / "run" / "raw").glob("*.json"))) == 22
    metadata = json.loads(next((tmp_path / "run" / "raw").glob("*.metadata.json")).read_text())
    assert metadata["headers"] == {"Content-Type": "application/json", "X-RateLimit-Remaining": "59"}
    assert "hidden" not in json.dumps(summary)
