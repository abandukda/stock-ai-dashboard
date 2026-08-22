from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from analysis.phase2b import fmp_schema_transcript_probe as probe


WORKFLOW = Path(".github/workflows/phase2b-fmp-schema-transcript-probe.yml")


def test_workflow_is_manual_read_only_and_isolated():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "contents: read" in source
    assert "python -m analysis.phase2b.fmp_schema_transcript_probe" in source
    for forbidden in (
        "schedule:", "push:", "pull_request:", "workflow_call:",
        "overnight_market_scan.py", "git push", "git commit",
        "market_full_scan.json", ".atlas_research_cache",
    ):
        assert forbidden not in source


def test_secret_is_environment_only_masked_and_single_artifact_is_allowed():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "FMP_API_KEY: ${{ secrets.FMP_API_KEY }}" in source
    assert '::add-mask::${FMP_API_KEY}' in source
    assert source.count("actions/upload-artifact@v4") == 1
    assert "fmp_phase2b_schema_probe_summary.json" in source
    assert "retention-days: 7" in source
    assert "contents: write" not in source


def test_scope_is_nvda_and_hard_cap_is_five():
    assert probe.SYMBOL == "NVDA"
    assert probe.REQUEST_CAP == 5
    assert len(probe.FIXED_REQUESTS) == 4
    assert {params["symbol"] for _, _, params in probe.FIXED_REQUESTS} == {"NVDA"}
    budget = probe.RequestBudget(999)
    for _ in range(5):
        budget.consume()
    with pytest.raises(RuntimeError, match="REQUEST_CAP_REACHED"):
        budget.consume()


def test_transcript_request_depends_on_valid_date_result(monkeypatch, tmp_path):
    monkeypatch.setenv("FMP_API_KEY", "masked-test-key")
    calls = []

    def fake_request(path, params, key, budget):
        calls.append((path, dict(params)))
        budget.consume()
        return 200, [{"symbol": "NVDA", "date": "2026-01-01"}], None

    monkeypatch.setattr(probe, "_request", fake_request)
    output = tmp_path / "summary.json"
    assert probe.run(output) == 0
    assert len(calls) == 4
    assert not any(path == "earning-call-transcript" for path, _ in calls)
    saved = json.loads(output.read_text())
    assert saved["transcript_result"]["period_mapping_source"] == "NO_VALID_YEAR_QUARTER_NO_REQUEST"


def test_valid_latest_period_drives_exact_fifth_request(monkeypatch, tmp_path):
    monkeypatch.setenv("FMP_API_KEY", "masked-test-key")
    calls = []

    def fake_request(path, params, key, budget):
        calls.append((path, dict(params)))
        budget.consume()
        if path == "earning-call-transcript-dates":
            return 200, [
                {"symbol": "NVDA", "year": 2025, "quarter": 4, "date": "2026-02-01"},
                {"symbol": "NVDA", "year": 2026, "quarter": 2, "date": "2026-08-01"},
            ], None
        if path == "earning-call-transcript":
            return 200, [{"symbol": "NVDA", "year": 2026, "quarter": 2, "content": "private transcript"}], None
        return 200, [{"symbol": "NVDA", "date": "2026-01-01"}], None

    monkeypatch.setattr(probe, "_request", fake_request)
    output = tmp_path / "summary.json"
    assert probe.run(output) == 0
    assert len(calls) == 5
    assert calls[-1] == ("earning-call-transcript", {"symbol": "NVDA", "year": 2026, "quarter": 2})
    saved = json.loads(output.read_text())
    assert saved["requests_used"] == 5
    assert saved["transcript_date_conclusion"]["multiple_historical_quarters_appear_addressable"] is True
    assert "private transcript" not in output.read_text()


def test_schema_inventory_contains_names_and_types_not_values():
    payload = [{
        "date": "2026-01-31", "estimatedEpsAvg": 9.99,
        "estimatedRevenueAvg": 123456789, "apiKey": "secret-value",
    }]
    result = probe.summarize_schema("analyst_estimates", 200, payload, None)
    rendered = json.dumps(result)
    assert "9.99" not in rendered
    assert "123456789" not in rendered
    assert "secret-value" not in rendered
    assert result["primitive_types_by_field"]["estimatedEpsAvg"] == ["number"]
    assert result["primitive_types_by_field"]["date"] == ["string"]


def test_transcript_summary_never_contains_text_or_values():
    payload = [{
        "symbol": "NVDA", "year": 2026, "quarter": 2,
        "speaker": "Private Name", "content": "Never serialize these transcript words",
    }]
    result = probe.summarize_transcript(200, payload, None)
    rendered = json.dumps(result)
    assert "Private Name" not in rendered
    assert "Never serialize" not in rendered
    assert result["content_present"] is True
    assert result["speaker_information_present"] is True
    assert result["approximate_total_character_count"] > 0


def test_http_helper_never_logs_sensitive_material():
    source = inspect.getsource(probe._request)
    assert "print(" not in source
    assert "str(exc)" not in source
    assert "response.text" not in source
    assert "write_text" not in source


def test_missing_credentials_make_zero_requests(monkeypatch, tmp_path):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(probe, "_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")))
    output = tmp_path / "summary.json"
    assert probe.run(output) == 2
    saved = json.loads(output.read_text())
    assert saved["requests_used"] == 0
    assert saved["schema_results"] == []


def test_no_production_or_scanner_dependency():
    source = inspect.getsource(probe)
    for forbidden in (
        "overnight_market_scan", "market_full_scan.json", "market_scan_state.json",
        "deep_research_cache", ".atlas_research_cache",
    ):
        assert forbidden not in source
