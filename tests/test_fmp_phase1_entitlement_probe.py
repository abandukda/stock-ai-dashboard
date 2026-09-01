from __future__ import annotations

import inspect
import json
from pathlib import Path
import socket

import pytest

from analysis.phase1 import fmp_intelligence_entitlement_probe as probe


WORKFLOW = Path(".github/workflows/fmp_phase1_entitlement_probe.yml")


@pytest.mark.parametrize(("status", "payload", "error", "expected"), [
    (200, [{"symbol": "MSFT"}], None, "AUTHORIZED_NONEMPTY"),
    (200, [], None, "AUTHORIZED_EMPTY"),
    (401, None, None, "UNAUTHORIZED"),
    (402, None, None, "PLAN_RESTRICTED"),
    (403, None, None, "PLAN_RESTRICTED"),
    (404, None, None, "ENDPOINT_NOT_FOUND"),
    (None, None, "TIMEOUT", "TIMEOUT"),
    (200, None, "MALFORMED_RESPONSE", "MALFORMED_RESPONSE"),
    (500, None, None, "PROBE_ERROR"),
])
def test_exact_classifications(status, payload, error, expected):
    assert probe._classification(status, payload, error) == expected
    assert expected in probe.CLASSIFICATIONS


def test_list_and_nested_dict_containers_are_schema_only():
    for payload, container in (([{"symbol": "MSFT", "priceTarget": 450}], "LIST"), ({"data": [{"symbol": "MSFT"}]}, "OBJECT")):
        result = probe.summarize("price_target_actions", 200, payload, None, 12.5)
        assert result["container_type"] == container
        assert result["row_count"] == 1
        assert "symbol" in result["field_names"]
        assert "450" not in json.dumps(result)


def test_transcript_text_names_values_urls_and_key_never_leak(monkeypatch, tmp_path):
    secret = "credential-that-must-never-appear"
    sensitive = {
        "transcript_index": [{"symbol": "MSFT", "year": 2026, "quarter": 2, "date": "2026-07-30"}],
        "transcript_content": [{"symbol": "MSFT", "year": 2026, "quarter": 2, "content": "sensitive transcript words", "speaker": "Private Person"}],
        "price_target_actions": [{"symbol": "MSFT", "analystName": "Private Analyst", "priceTarget": 999.99, "url": "https://private.test"}],
        "insider_transactions": [{"symbol": "MSFT", "reportingName": "Private Insider", "transactionDate": "2026-01-01", "filingId": "secret-filing", "shares": -25, "value": 1000}],
        "analyst_estimates": [{"date": "2027-06-30", "estimatedEpsAvg": 10.25}],
    }

    def fake_request(path, params, api_key):
        family = next(name for name, endpoint in probe.ENDPOINTS.items() if endpoint == path)
        return 200, sensitive[family], None, 1.0

    monkeypatch.setenv("FMP_API_KEY", secret)
    monkeypatch.setattr(probe, "_request", fake_request)
    json_path, md_path = tmp_path / "matrix.json", tmp_path / "report.md"
    assert probe.run(json_path, md_path) == 0
    rendered = json_path.read_text() + md_path.read_text()
    for forbidden in (secret, "sensitive transcript words", "Private Person", "Private Analyst", "Private Insider", "999.99", "https://private.test", "secret-filing", "1000"):
        assert forbidden not in rendered
    assert "approximate_content_characters" in rendered


def test_prior_target_is_never_inferred():
    current_only = probe.summarize("price_target_actions", 200, [{"symbol": "MSFT", "priceTarget": 500}], None, 1)
    assert current_only["prior_target_status"] == "PRIOR_TARGET_NOT_PROVEN"
    explicit = probe.summarize("price_target_actions", 200, [{"symbol": "MSFT", "priceTarget": 500, "previousPriceTarget": 480}], None, 1)
    assert explicit["prior_target_status"] == "PRIOR_TARGET_PROVEN"


def test_fiscal_period_is_not_observation_date():
    result = probe.summarize("analyst_estimates", 200, [{"date": "2027-06-30", "estimatedEpsAvg": 10}], None, 1)
    assert result["semantic_field_presence"]["estimate_period"]["present"] is True
    assert result["semantic_field_presence"]["observation_timestamp"]["present"] is False
    assert result["estimate_vintage_status"] == "POINT_IN_TIME_ESTIMATE_VINTAGES_NOT_PRESENT"


def test_transcript_uses_exact_returned_period(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("FMP_API_KEY", "masked")

    def fake_request(path, params, api_key):
        calls.append((path, dict(params)))
        if path == "earning-call-transcript-dates":
            return 200, [{"symbol": "MSFT", "year": 2025, "quarter": 4}], None, 1
        if path == "earning-call-transcript":
            return 200, [{"symbol": "MSFT", "year": 2025, "quarter": 4, "content": "words"}], None, 1
        return 200, [], None, 1

    monkeypatch.setattr(probe, "_request", fake_request)
    assert probe.run(tmp_path / "x.json", tmp_path / "x.md") == 0
    transcript_call = next(params for path, params in calls if path == "earning-call-transcript")
    assert transcript_call == {"symbol": "MSFT", "year": 2025, "quarter": 4}


def test_missing_credential_makes_no_network_call(monkeypatch, tmp_path):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(probe, "_request", lambda *args: (_ for _ in ()).throw(AssertionError("network called")))
    assert probe.run(tmp_path / "x.json", tmp_path / "x.md") == 2


def test_timeout_transport_never_logs_or_serializes_exception_details():
    source = inspect.getsource(probe._request)
    assert "print(" not in source
    assert "str(exc)" not in source
    assert "response.text" not in source


def test_workflow_is_manual_read_only_and_uploads_before_failure_enforcement():
    source = WORKFLOW.read_text()
    assert "workflow_dispatch:" in source
    assert "contents: read" in source
    assert "FMP_API_KEY: ${{ secrets.FMP_API_KEY }}" in source
    assert 'echo "::add-mask::${FMP_API_KEY}"' in source
    assert "retention-days: 14" in source
    assert source.index("Run sanitized entitlement probe") < source.index("Upload sanitized probe artifacts") < source.index("Enforce probe infrastructure status")
    for forbidden in ("schedule:", "push:", "pull_request:", "overnight_market_scan.py", "git commit", "git push", "market_full_scan.json"):
        assert forbidden not in source


def test_probe_scope_is_exact_and_production_paths_untouched():
    assert set(probe.ENDPOINTS.values()) == {
        "earning-call-transcript-dates", "earning-call-transcript", "price-target-news",
        "insider-trading/search", "analyst-estimates",
    }
    assert probe.REQUEST_CAP == 5
    assert Path("services/fmp_research_acquisition.py").exists()
    assert Path("overnight_market_scan.py").exists()
