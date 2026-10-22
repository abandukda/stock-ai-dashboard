import json
from datetime import date, datetime, time, timezone

import pytest

from services.buy_now_history_backfill_execution import (
    BackfillExecutor, Response, authorization_token, build_claim_scope, scope_digest,
)
from tests.test_buy_now_history_continuity import _plan
from scripts.inspect_buy_now_history_backfill_claim import inspect


def _bound(tmp_path, transport, execution="run-1"):
    plan = _plan()
    scope = build_claim_scope(
        claim_id="provider-free-backfill-test-0001", source_sha=plan["source_sha"],
        workflow_source_sha="e" * 40,
        artifact_id=12069093114, artifact_zip_sha256="c" * 64,
        package_sha256="d" * 64, plan_sha256=plan["plan_sha256"],
        scope_sha256=scope_digest(plan), plan=plan,
    )
    return BackfillExecutor(state_root=tmp_path / "state", raw_root=tmp_path / "raw",
                            scope=scope, plan=plan, token=authorization_token(scope),
                            execution_id=execution, transport=transport, provider_free=True), scope


def _transport(counter):
    ts = [int(datetime.combine(date.fromisoformat(v), time(21), tzinfo=timezone.utc).timestamp())
          for v in ("2026-10-05", "2026-10-06")]
    def call(request):
        counter.append(request["ordinal"])
        body = ({"s":"ok", "t":ts, "o":[1,1], "h":[2,2], "l":[.5,.5],
                 "c":[1.5,1.5], "v":[100,100]}
                if request["endpoint"] == "/stock/candle" else [])
        return Response(200, json.dumps(body).encode())
    return call


def test_atomic_response_is_resumed_without_repeating_call(tmp_path):
    calls=[]
    executor, _ = _bound(tmp_path, _transport(calls))
    with pytest.raises(RuntimeError, match="SIMULATED_CRASH_AFTER_RESPONSE"):
        executor.run(stop_after_response_ordinal=1)
    assert calls == [1]
    result = executor.run()
    assert result["status"] == "COMPLETE"
    assert result["provider_calls"] == 0
    assert calls.count(1) == 1
    assert result["requests"] == 3894


def test_intent_without_response_is_indeterminate_and_never_retried(tmp_path):
    calls=[]
    executor, _ = _bound(tmp_path, _transport(calls))
    with pytest.raises(RuntimeError, match="SIMULATED_CRASH_AFTER_INTENT"):
        executor.run(stop_after_intent_ordinal=1)
    assert calls == []
    with pytest.raises(RuntimeError, match="BACKFILL_ATTEMPT_INDETERMINATE:1"):
        executor.run()
    assert calls == []


def test_consumed_claim_rejects_different_execution_and_scope(tmp_path):
    calls=[]
    first, scope = _bound(tmp_path, _transport(calls))
    with pytest.raises(RuntimeError, match="SIMULATED_CRASH_AFTER_INTENT"):
        first.run(stop_after_intent_ordinal=1)
    second = BackfillExecutor(state_root=tmp_path/"state", raw_root=tmp_path/"raw",
        scope=scope, plan=_plan(), token=authorization_token(scope), execution_id="run-2",
        transport=_transport(calls), provider_free=True)
    with pytest.raises(PermissionError, match="ALREADY_CONSUMED"):
        second.run()


@pytest.mark.parametrize("status,error", [(429,"HTTP_429"),(401,"ENTITLEMENT"),(500,"HTTP_ERROR")])
def test_http_failures_stop_without_retry(tmp_path, status, error):
    calls=[]
    def bad(request):
        calls.append(request["ordinal"]); return Response(status, b'{}')
    executor, _ = _bound(tmp_path, bad)
    with pytest.raises(RuntimeError, match=error): executor.run()
    assert calls == [1]


def test_corporate_action_schema_and_range_fail_closed():
    request = {"endpoint":"/stock/split", "parameters":{"from":"2026-10-05", "to":"2026-10-15"}}
    body = [{"date":"2026-10-16", "fromFactor":1, "toFactor":2}]
    envelope = {"status_code":200, "body_base64":__import__('base64').b64encode(json.dumps(body).encode()).decode()}
    with pytest.raises(RuntimeError, match="DATE_OUT_OF_RANGE"):
        BackfillExecutor._validate_response(request, envelope)


def test_no_data_is_terminal_unavailable_evidence_not_a_valid_candle(tmp_path):
    calls=[]
    def no_data(request):
        calls.append(request["ordinal"])
        if request["endpoint"] == "/stock/candle" and request["ticker"] == "S0000":
            return Response(200, b'{"s":"no_data"}', {"content-type":"application/json"})
        return _transport([])(request)
    executor, scope = _bound(tmp_path, no_data)
    result = executor.run()
    assert result["status"] == "COMPLETE"
    validation = result["observation_validation"]
    assert validation["ticker_count"] == 1298
    assert validation["available_ticker_count"] == 1297
    assert validation["unavailable_ticker_count"] == 1
    assert validation["unavailable_inventory"][0]["ticker"] == "S0000"
    assert validation["unavailable_inventory"][0]["reason"] == "FINNHUB_NO_DATA"
    receipt = json.loads((tmp_path/"state"/"history_backfill_claims"/
                          scope["claim_id"] / "receipts" / "00001.json").read_text())
    assert receipt["evidence_disposition"] == "FINNHUB_NO_DATA"


def test_consumed_claim_forensics_sanitizes_no_data_and_reconciles(tmp_path):
    calls=[]
    def no_data(request):
        calls.append(request["ordinal"])
        return Response(200, b'{"s":"no_data","unexpected":true}',
                        {"content-type":"application/json"})
    executor, scope = _bound(tmp_path, no_data)
    with pytest.raises(RuntimeError, match="CANDLE_SCHEMA_INVALID"):
        executor.run()
    package=tmp_path/"package.json"
    package.write_text(json.dumps({"backfill_plan":_plan()}))
    result=inspect(package=package,state_root=tmp_path/"state",raw_root=tmp_path/"raw",
                   claim_id=scope["claim_id"],expected_claim_scope=scope["claim_scope_sha256"])
    assert calls == [1]
    assert result["durable_intents"] == result["raw_envelopes"] == 1
    assert result["completed_receipts"] == result["indeterminate_requests"] == 0
    assert result["not_attempted"] == 3893
    assert result["remaining_authorized_budget"] == 0
    assert result["failure"]["ordinal"] == 1
    assert result["failure"]["response_shape"]["classification"] == "FINNHUB_NO_DATA"
    assert "body_base64" not in json.dumps(result)


def test_invalid_prices_stop_at_first_preserved_response_without_retry(tmp_path):
    calls = []
    def malformed(request):
        response = _transport(calls)(request)
        body = json.loads(response.body)
        body["c"][0] = float("nan")
        return Response(200, json.dumps(body).encode())
    executor, scope = _bound(tmp_path, malformed)
    for _ in range(2):
        with pytest.raises(ValueError, match="OHLCV_NOT_FINITE_NUMERIC"):
            executor.run()
    assert calls == [1]
    claim_dir = tmp_path / "state" / "history_backfill_claims" / scope["claim_id"]
    assert len(list((claim_dir / "intents").glob("*.json"))) == 1
    assert not list((claim_dir / "receipts").glob("*.json"))
    assert json.loads((claim_dir / "claim.json").read_text())["state"] != "COMPLETE"
