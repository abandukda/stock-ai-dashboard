from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

import overnight_market_scan as scanner


class _Response:
    def __init__(self, status_code=200, payload=None, json_error=None):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


@pytest.fixture(autouse=True)
def reset_diagnostics(monkeypatch):
    scanner._NEWSAPI_DIAGNOSTICS.clear()
    monkeypatch.setattr(scanner, "NEWSAPI_KEY", "secret-value-that-must-not-appear")
    for key in list(scanner._SCAN_TIMINGS):
        scanner._SCAN_TIMINGS[key] = 0 if isinstance(scanner._SCAN_TIMINGS[key], int) else 0.0
    scanner._YAHOO_METADATA_LATENCIES.clear()


@pytest.mark.parametrize(
    ("response", "error", "expected"),
    [
        (_Response(401, {}), None, scanner.NEWSAPI_AUTH_FAILURE),
        (_Response(403, {}), None, scanner.NEWSAPI_AUTH_FAILURE),
        (_Response(429, {}), None, scanner.NEWSAPI_RATE_LIMIT),
        (_Response(500, {}), None, scanner.NEWSAPI_HTTP_FAILURE),
        (None, requests.Timeout("secret raw timeout"), scanner.NEWSAPI_NETWORK_FAILURE),
        (_Response(200, json_error=ValueError("secret raw payload")), None, scanner.NEWSAPI_SCHEMA_FAILURE),
        (_Response(200, {"articles": "wrong"}), None, scanner.NEWSAPI_SCHEMA_FAILURE),
        (_Response(200, {"articles": []}), None, scanner.NEWSAPI_ZERO_ARTICLES),
    ],
)
def test_newsapi_sanitized_failure_categories(monkeypatch, capsys, response, error, expected):
    def request(*args, **kwargs):
        if error:
            raise error
        return response

    monkeypatch.setattr(scanner.requests, "get", request)
    assert scanner.get_news_research("SAFE", "Safe Company") == {}
    diagnostic = scanner._NEWSAPI_DIAGNOSTICS[-1]
    assert diagnostic == {
        "ticker": "SAFE",
        "status": expected,
        "article_count": 0,
        "accepted_count": 0,
        "relevance_rejected_count": 0,
    }
    output = capsys.readouterr().out
    assert "secret-value-that-must-not-appear" not in output
    assert "secret raw" not in output
    assert "newsapi.org" not in output


def test_newsapi_success_and_relevance_rejection_counts_are_sanitized(monkeypatch, capsys):
    payload = {
        "articles": [
            {
                "title": "Safe Company raises guidance",
                "description": "sensitive article body",
                "source": {"name": "Wire"},
                "publishedAt": "2026-08-18T00:00:00Z",
                "url": "https://example.test/safe",
            },
            {
                "title": "Unrelated market story",
                "description": "another sensitive body",
                "source": {"name": "Wire"},
                "publishedAt": "2026-08-18T00:00:00Z",
                "url": "https://example.test/unrelated",
            },
        ]
    }
    monkeypatch.setattr(scanner.requests, "get", lambda *args, **kwargs: _Response(200, payload))
    result = scanner.get_news_research("SAFE", "Safe Company")
    assert len(result["news_evidence"]) == 1
    assert scanner._NEWSAPI_DIAGNOSTICS[-1] == {
        "ticker": "SAFE",
        "status": scanner.NEWSAPI_SUCCESS,
        "article_count": 2,
        "accepted_count": 1,
        "relevance_rejected_count": 1,
    }
    output = capsys.readouterr().out
    assert "sensitive article body" not in output
    assert "Unrelated market story" not in output


def test_newsapi_all_rejected_is_distinct_from_zero_articles(monkeypatch):
    payload = {"articles": [{"title": "Unrelated market story", "description": "none"}]}
    monkeypatch.setattr(scanner.requests, "get", lambda *args, **kwargs: _Response(200, payload))
    assert scanner.get_news_research("SAFE", "Safe Company") == {}
    assert scanner._NEWSAPI_DIAGNOSTICS[-1]["status"] == scanner.NEWSAPI_RELEVANCE_REJECTED
    assert scanner._NEWSAPI_DIAGNOSTICS[-1]["relevance_rejected_count"] == 1


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (RuntimeError("Too Many Requests"), "rate_limited"),
        (RuntimeError("Quote not found for symbol"), "invalid_or_delisted"),
        (requests.Timeout("timed out"), "timeout_or_network"),
        (TypeError("schema mismatch"), "parsing_or_schema"),
        (RuntimeError("provider unavailable"), "other_exceptions"),
    ],
)
def test_yahoo_metadata_exception_categories(monkeypatch, error, category):
    class Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        def get_info(self):
            raise error

    monkeypatch.setattr(scanner.yf, "Ticker", Ticker)
    result = scanner.get_metadata("TEST")
    assert result["company_name"] == "TEST"
    assert scanner._SCAN_TIMINGS["yahoo_metadata_calls"] == 1
    assert scanner._SCAN_TIMINGS["yahoo_metadata_failures"] == 1
    assert scanner._SCAN_TIMINGS[f"yahoo_metadata_{category}"] == 1
    categories = (
        "rate_limited", "invalid_or_delisted", "timeout_or_network",
        "parsing_or_schema", "other_exceptions",
    )
    assert sum(scanner._SCAN_TIMINGS[f"yahoo_metadata_{item}"] for item in categories) == 1


def test_yahoo_metadata_dependency_map_prevents_unsafe_deferral():
    dependencies = scanner.yahoo_metadata_dependency_map()
    assert {"market_cap", "revenue_growth", "earnings_growth", "forward_pe"}.issubset(
        dependencies["scoring_and_ranking"]
    )
    assert {"sector", "industry", "quote_type"}.issubset(dependencies["before_prescreen"])
    assert "website" in dependencies["post_prescreen_presentation_only"]


def test_github_actions_never_invokes_scanner_git_persistence(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(scanner, "run_cmd", lambda command: pytest.fail(f"unexpected git command: {command}"))
    assert scanner.persist_to_github() is False


def test_workflow_is_only_commit_push_owner_and_stages_six_outputs():
    workflow = Path(".github/workflows/overnight_scan.yml").read_text(encoding="utf-8")
    expected = [path.name for path in scanner.PRODUCTION_OUTPUT_FILES]
    add_line = next(line.strip() for line in workflow.splitlines() if line.strip().startswith("git add --"))
    assert add_line.split()[3:] == expected
    assert "git push origin main" in workflow
    assert "GITHUB_REPO_URL" not in add_line


def test_production_output_contract_is_exactly_six_json_files():
    assert [path.name for path in scanner.PRODUCTION_OUTPUT_FILES] == [
        "etf_scan.json",
        "market_full_scan.json",
        "market_prescreen.json",
        "market_scan_state.json",
        "recovery_scan.json",
        "total_market_universe.json",
    ]
    assert all(path.suffix == ".json" for path in scanner.PRODUCTION_OUTPUT_FILES)


def test_news_diagnostic_summary_contains_no_raw_payload_fields():
    scanner._record_newsapi_diagnostic(
        "SAFE", scanner.NEWSAPI_SUCCESS,
        article_count=2, accepted_count=1, relevance_rejected_count=1,
    )
    summary = scanner._newsapi_diagnostic_summary()
    assert summary["requests"] == 1
    assert summary["by_status"] == {scanner.NEWSAPI_SUCCESS: 1}
    serialized = json.dumps(summary)
    for forbidden in ("apiKey", "description", "body", "authenticated_url", "secret"):
        assert forbidden not in serialized
