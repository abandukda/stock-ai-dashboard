from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from analysis.phase7b2 import provider_entitlement_probe as probe


WORKFLOW = Path(".github/workflows/phase7b2-provider-entitlement-probe.yml")


def test_workflow_is_manual_only_and_read_only():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    for forbidden in ("schedule:", "push:", "pull_request:", "overnight_market_scan.py", "git push", "git commit", "upload-artifact"):
        assert forbidden not in source
    assert "contents: read" in source
    assert "timeout-minutes: 8" in source


def test_workflow_uses_secrets_only_as_environment_and_masks_them():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "FMP_API_KEY: ${{ secrets.FMP_API_KEY }}" in source
    assert "FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}" in source
    assert "::add-mask::${FMP_API_KEY}" in source
    assert "::add-mask::${FINNHUB_API_KEY}" in source
    assert "python analysis/phase7b2/provider_entitlement_probe.py" in source


def test_scope_and_request_cap_are_fixed():
    assert probe.TICKERS == ("NVDA", "AVGO")
    assert len(probe.FMP_ENDPOINTS) == 9
    assert len(probe.OBSERVATION_DATES) == 6
    assert probe.DEFAULT_REQUEST_CAP == 48
    budget = probe.RequestBudget(999)
    assert budget.cap == 48
    for _ in range(48):
        budget.consume()
    with pytest.raises(RuntimeError, match="REQUEST_CAP_REACHED"):
        budget.consume()


def test_sanitized_summary_contains_metadata_not_values_or_secrets():
    payload = [{
        "symbol": "NVDA", "date": "2026-01-31", "fiscalYear": 2026,
        "estimatedEpsAvg": 9.99, "numberAnalysts": 42,
        "filingDate": "2026-02-20", "apiKey": "must-not-appear",
    }]
    summary = probe.summarize("FMP", "analyst_estimates", "NVDA", 200, payload, None)
    rendered = json.dumps(summary)
    assert "must-not-appear" not in rendered
    assert "apiKey" not in rendered
    assert "9.99" not in rendered
    assert summary["row_count"] == 1
    assert "date" in summary["date_field_names"]
    assert "numberAnalysts" in summary["analyst_count_field_names"]


def test_http_error_path_never_formats_exception_or_url():
    source = inspect.getsource(probe._http_json)
    assert "str(exc)" not in source
    assert "response.text" not in source
    assert "print(" not in source


def test_missing_credentials_make_zero_requests(monkeypatch, capsys):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setattr(probe, "_http_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")))
    assert probe.run() == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[-1] == {"hard_request_cap": 48, "kind": "probe_complete", "requests_used": 0}


def test_production_workflow_is_not_modified_by_probe_design():
    production = Path(".github/workflows/overnight_scan.yml").read_text(encoding="utf-8")
    assert "python overnight_market_scan.py" in production
    assert "phase7b2" not in production.lower()
