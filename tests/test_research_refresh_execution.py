from datetime import date, datetime, timezone
from collections import Counter
import json

import pytest

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.research_refresh_execution import (
    MAX_REQUESTS, compile_execution_plan, execute_live, rehearse,
)
from services.research_refresh_readiness import ALLOWED_CAPABILITIES, plan_research_refresh


NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def _plan(tickers, cache=None):
    return plan_research_refresh(
        tickers, cache or {}, {"status": "APPROVED", "contract_id": CONTRACT_ID,
                               "capabilities": list(ALLOWED_CAPABILITIES)},
        source_sha="a" * 40, now=NOW,
    )


def test_cold_cache_25_tickers_is_exactly_bounded_and_parameter_complete():
    compiled = compile_execution_plan(_plan([f"T{i:02d}" for i in range(25)]),
                                      as_of=date(2026, 10, 16))
    assert len(compiled["requests"]) == MAX_REQUESTS == 225
    counts = Counter(row["capability"] for row in compiled["requests"])
    assert counts == {
        "historical_ohlcv": 25, "splits": 25, "dividends": 25,
        "financial_statements": 25, "basic_financials": 25,
        "stock_earnings": 25, "recommendations": 25,
        "price_targets": 25, "company_news": 25,
    }
    assert {row["capability"] for row in compiled["deferred"]
            if row["reason"] == "DEFERRED_REQUEST_BUDGET"} == {
                "analyst_actions", "earnings_calendar",
            }
    assert compiled["limits"] == {"max_tickers": 25, "max_requests": 225,
                                   "concurrency": 1, "retries": 0}
    assert all(row["request_sha256"] for row in compiled["requests"])
    candle = next(row for row in compiled["requests"] if row["capability"] == "historical_ohlcv")
    assert candle["parameters"]["resolution"] == "D"
    assert isinstance(candle["parameters"]["from"], int)
    assert compiled["provider_calls"] == compiled["publication_writes"] == 0
    assert compiled["recommendation_authority"] == "UNCHANGED"


def test_cache_hits_release_budget_but_never_reacquire_fresh_family():
    cache = {"NVDA": {"historical_ohlcv": {
        "capture_timestamp": "2026-10-18T00:00:00Z", "integrity_verified": True,
    }}}
    compiled = compile_execution_plan(_plan(["NVDA"], cache), as_of=date(2026, 10, 18))
    capabilities = {row["capability"] for row in compiled["requests"]}
    assert "historical_ohlcv" not in capabilities
    assert {"financial_statements", "stock_earnings", "company_news"} <= capabilities


def test_rehearsal_is_raw_first_restart_safe_and_rejects_corrupt_receipt(tmp_path):
    compiled = compile_execution_plan(_plan(["NVDA"]), as_of=date(2026, 10, 18))
    first = rehearse(compiled, durable_root=tmp_path)
    second = rehearse(compiled, durable_root=tmp_path)
    assert first.completed == len(compiled["requests"])
    assert first.resumed == 0
    assert second.resumed == first.completed
    run = tmp_path / compiled["package_sha256"]
    assert len(list((run / "intents").glob("*.json"))) == first.completed
    assert len(list((run / "envelopes").glob("*.json"))) == first.completed
    receipt = sorted((run / "receipts").glob("*.json"))[0]
    value = json.loads(receipt.read_text())
    value["request_sha256"] = "bad"
    receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="RECEIPT_MISMATCH"):
        rehearse(compiled, durable_root=tmp_path)


def test_live_is_fail_closed_even_when_flag_is_set(monkeypatch):
    monkeypatch.delenv("ATLAS_RESEARCH_REFRESH_LIVE_ENABLED", raising=False)
    with pytest.raises(PermissionError, match="LIVE_DISABLED"):
        execute_live()
    monkeypatch.setenv("ATLAS_RESEARCH_REFRESH_LIVE_ENABLED", "true")
    with pytest.raises(PermissionError, match="WORKFLOW_NOT_REGISTERED"):
        execute_live()


def test_scope_and_package_are_deterministic():
    first = compile_execution_plan(_plan(["MSFT", "NVDA"]), as_of=date(2026, 10, 18))
    second = compile_execution_plan(_plan(["NVDA", "MSFT"]), as_of=date(2026, 10, 18))
    assert first == second


def test_tampered_or_non_commit_upstream_identity_fails_closed():
    bad = _plan(["NVDA"])
    bad["requests"][0]["ticker"] = "MSFT"
    with pytest.raises(ValueError, match="PLAN_DIGEST"):
        compile_execution_plan(bad, as_of=date(2026, 10, 18))
    weak = _plan(["NVDA"])
    weak["source_sha"] = "branch-name"
    with pytest.raises(ValueError, match="SOURCE_SHA"):
        compile_execution_plan(weak, as_of=date(2026, 10, 18))
