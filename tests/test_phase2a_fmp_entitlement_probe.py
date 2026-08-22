from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from analysis.phase2a import fmp_entitlement_probe as probe


WORKFLOW = Path(".github/workflows/phase2a-fmp-entitlement-probe.yml")


def test_workflow_is_manual_read_only_and_isolated():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "contents: read" in source
    assert "python -m analysis.phase2a.fmp_entitlement_probe" in source
    for forbidden in (
        "schedule:", "push:", "pull_request:", "workflow_call:",
        "overnight_market_scan.py", "git push", "git commit",
        "market_full_scan.json", "market_scan_state.json",
    ):
        assert forbidden not in source


def test_secret_is_environment_only_and_masked():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "FMP_API_KEY: ${{ secrets.FMP_API_KEY }}" in source
    assert '::add-mask::${FMP_API_KEY}' in source
    assert "contents: write" not in source


def test_fixed_scope_and_hard_budget():
    assert probe.SYMBOLS == ("NVDA", "AAPL", "SPY")
    assert probe.REQUEST_CAP == 25
    assert len(probe.FIXED_PROBES) == 24
    assert {item[1] for item in probe.FIXED_PROBES} == set(probe.SYMBOLS)
    budget = probe.RequestBudget(999)
    for _ in range(25):
        budget.consume()
    with pytest.raises(RuntimeError, match="REQUEST_CAP_REACHED"):
        budget.consume()


def test_documented_transcript_and_etf_paths_are_exact():
    paths = {item[2] for item in probe.FIXED_PROBES}
    assert "earning-call-transcript-dates" in paths
    source = inspect.getsource(probe.run)
    assert '"earning-call-transcript"' in source
    assert {"etf/info", "etf/holdings", "etf/sector-weightings", "etf/country-weightings"} <= paths


def test_sanitized_summary_excludes_values_text_and_secrets():
    payload = [{
        "symbol": "NVDA", "publishedDate": "2026-08-20",
        "title": "sensitive article title", "text": "article body",
        "url": "https://example.test/article", "apiKey": "secret-value",
    }]
    value = probe.summarize("stock_news", "NVDA", 200, payload, None)
    rendered = json.dumps(value)
    assert "sensitive article title" not in rendered
    assert "article body" not in rendered
    assert "secret-value" not in rendered
    assert "https://example.test" not in rendered
    assert value["row_count"] == 1
    assert value["semantic_field_presence"]["title"] is True


def test_transcript_content_is_never_serialized():
    payload = [{"symbol": "NVDA", "year": 2026, "quarter": 2, "content": "raw transcript words"}]
    value = probe.summarize("transcript_content", "NVDA", 200, payload, None)
    assert "raw transcript words" not in json.dumps(value)
    assert value["existing_normalizer_success"] is True


def test_http_helper_never_logs_url_payload_or_exception_text():
    source = inspect.getsource(probe._request)
    assert "print(" not in source
    assert "str(exc)" not in source
    assert "response.text" not in source
    assert "write_text" not in source


def test_missing_credential_makes_zero_network_calls(monkeypatch, tmp_path):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(probe, "_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")))
    output = tmp_path / "summary.json"
    assert probe.run(output) == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["requests_used"] == 0
    assert saved["results"] == []


def test_only_allowlisted_summary_shape_is_persisted(monkeypatch, tmp_path):
    monkeypatch.setenv("FMP_API_KEY", "masked-test-key")
    calls = []

    def fake_request(path, params, key, budget):
        calls.append((path, dict(params)))
        budget.consume()
        if path == "earning-call-transcript-dates":
            return 200, [{"symbol": "NVDA", "year": 2026, "quarter": 2, "date": "2026-08-01"}], None
        return 200, [{"symbol": params.get("symbol") or params.get("symbols"), "date": "2026-01-01"}], None

    monkeypatch.setattr(probe, "_request", fake_request)
    output = tmp_path / "summary.json"
    assert probe.run(output) == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["requests_used"] == 25
    assert len(calls) == 25
    rendered = output.read_text(encoding="utf-8")
    assert "masked-test-key" not in rendered
    assert "financialmodelingprep.com" not in rendered
    assert "earning-call-transcript" not in rendered or "transcript_content" in rendered


def test_production_workflow_and_scanner_are_not_part_of_patch():
    production = Path(".github/workflows/overnight_scan.yml").read_text(encoding="utf-8")
    assert "phase2a" not in production.lower()
    assert Path("overnight_market_scan.py").exists()
