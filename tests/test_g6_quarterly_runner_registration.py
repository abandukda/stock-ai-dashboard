import json
from pathlib import Path

import pytest

from scripts.run_g6_quarterly_research import (
    EXPECTED_APPROVAL_SHA,
    EXPECTED_EVIDENCE_SOURCE_SHA,
    EXPECTED_MANIFEST_SHA,
    EXPECTED_TICKERS,
    EXPECTED_TOKEN,
    execute,
    verify,
)


APPROVAL = Path("output/joint/r2_reconciliation/g6_quarterly_acquisition_approval.json")
MANIFEST = Path("output/joint/r2_reconciliation/g6_quarterly_immutable_batches.json")
WORKFLOW = Path(".github/workflows/atlas_g6_quarterly_research.yml")


def inputs():
    return json.loads(APPROVAL.read_text()), json.loads(MANIFEST.read_text())


def test_frozen_quarterly_package_is_exactly_11_tickers_and_zero_retry():
    approval, manifest = inputs()
    assert verify(approval, manifest, evidence_source_sha=EXPECTED_EVIDENCE_SOURCE_SHA, token=EXPECTED_TOKEN) == EXPECTED_TICKERS
    assert manifest["sha256"] == EXPECTED_MANIFEST_SHA
    assert approval["sha256"] == EXPECTED_APPROVAL_SHA
    assert approval["rate_contract"]["automatic_retry_ceiling_per_request"] == 0
    assert approval["rate_contract"]["absolute_provider_attempt_ceiling"] == 11


@pytest.mark.parametrize("mutation", ["source", "token", "symbol", "retry", "attempts", "manifest"])
def test_quarterly_package_mutations_fail_closed(mutation):
    approval, manifest = inputs()
    source, token = EXPECTED_EVIDENCE_SOURCE_SHA, EXPECTED_TOKEN
    if mutation == "source":
        source = "wrong"
    elif mutation == "token":
        token = "wrong"
    elif mutation == "symbol":
        approval["request_contract"]["symbol_order"][0] = "BAD"
    elif mutation == "retry":
        approval["rate_contract"]["automatic_retry_ceiling_per_request"] = 1
    elif mutation == "attempts":
        approval["rate_contract"]["absolute_provider_attempt_ceiling"] = 12
    else:
        manifest["batches"][0]["symbols"][0] = "BAD"
    with pytest.raises(PermissionError):
        verify(approval, manifest, evidence_source_sha=source, token=token)


def test_workflow_is_manual_protected_credential_bearing_and_serial():
    source = WORKFLOW.read_text()
    assert "workflow_dispatch:" in source and "schedule:" not in source and "push:" not in source
    assert "environment: atlas-premium-g6-quarterly" in source
    assert "secrets.FINNHUB_API_KEY" in source
    assert EXPECTED_EVIDENCE_SOURCE_SHA in source and EXPECTED_MANIFEST_SHA in source and EXPECTED_TOKEN in source
    assert "ref: ${{ github.sha }}" in source and 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in source
    assert "matrix:" not in source and "max_retries=0" not in source
    assert "scripts/run_g6_quarterly_research.py" in source


def test_runner_writes_exact_raw_lineage_without_retry_or_secret(monkeypatch, tmp_path):
    calls = []

    class Response:
        status_code = 200
        content = b'{"data": []}'
        headers = {"Content-Type": "application/json", "Authorization": "secret", "X-RateLimit-Remaining": "499"}

    class Session:
        def mount(self, *_args):
            pass

        def get(self, url, *, params, timeout):
            calls.append((url, params, timeout))
            return Response()

    monkeypatch.setattr("scripts.run_g6_quarterly_research.requests.Session", Session)
    monkeypatch.setattr("scripts.run_g6_quarterly_research.time.sleep", lambda _seconds: None)
    monkeypatch.setenv("G6_QUARTERLY_EXECUTE", "1")
    summary = execute(
        APPROVAL,
        MANIFEST,
        tmp_path / "run",
        evidence_source_sha=EXPECTED_EVIDENCE_SOURCE_SHA,
        execution_sha="a" * 40,
        token=EXPECTED_TOKEN,
        api_key="hidden",
    )
    assert summary["provider_calls"] == 11 and summary["retry_count"] == 0 and len(calls) == 11
    assert [call[1]["symbol"] for call in calls] == list(EXPECTED_TICKERS)
    metadata = json.loads(next((tmp_path / "run" / "raw").glob("*.metadata.json")).read_text())
    assert metadata["attempt_count"] == 1 and metadata["retry_count"] == 0
    assert metadata["response_headers"] == {"Content-Type": "application/json", "X-RateLimit-Remaining": "499"}
    assert "hidden" not in json.dumps(summary)


def test_runner_stops_on_first_provider_failure_without_retry(monkeypatch, tmp_path):
    calls = []

    class Response:
        status_code = 429
        content = b'{"error": "rate limit"}'
        headers = {"Content-Type": "application/json"}

    class Session:
        def mount(self, *_args):
            pass

        def get(self, url, *, params, timeout):
            calls.append((url, params, timeout))
            return Response()

    monkeypatch.setattr("scripts.run_g6_quarterly_research.requests.Session", Session)
    monkeypatch.setenv("G6_QUARTERLY_EXECUTE", "1")
    with pytest.raises(RuntimeError, match="G6_QUARTERLY_HTTP_FAILURE:AVT:429"):
        execute(
            APPROVAL,
            MANIFEST,
            tmp_path / "run",
            evidence_source_sha=EXPECTED_EVIDENCE_SOURCE_SHA,
            execution_sha="a" * 40,
            token=EXPECTED_TOKEN,
            api_key="hidden",
        )
    assert len(calls) == 1


def test_quarterly_acquisition_remains_separate_from_customer_projection():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "customer_annual_statement_projection" not in workflow
    assert "publication" not in workflow.lower()
    assert "rating" not in workflow.lower()
    assert "normalize_g6_annual_statements.py" not in workflow
    assert "build_g6_annual_financial_series.py" not in workflow
