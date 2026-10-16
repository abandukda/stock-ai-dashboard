import json
from datetime import date, datetime, time, timezone

import pytest

from services.buy_now_history_backfill_execution import (
    BackfillExecutor, Response, authorization_token, build_claim_scope, scope_digest,
)
from tests.test_buy_now_history_continuity import _plan


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
