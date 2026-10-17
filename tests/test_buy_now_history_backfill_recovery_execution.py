import json
from pathlib import Path

import pytest

from services.buy_now_history_backfill_execution import (
    RecoveryBackfillExecutor, Response, digest, recovery_authorization_token,
    validate_recovery_scope,
)


def _bound(tmp_path: Path, transport, *, execution="run-1"):
    endpoints = ("/stock/candle", "/stock/split", "/stock/dividend")
    requests = []
    for ordinal in range(2849, 3895):
        endpoint = endpoints[(ordinal - 2849) % 3]
        requests.append({"ordinal": ordinal, "ticker": f"S{ordinal:04d}",
                         "capability": "historical_ohlcv" if endpoint.endswith("candle") else endpoint.rsplit("/", 1)[-1] + "s",
                         "endpoint": endpoint, "method": "GET",
                         "parameters": {"symbol": f"S{ordinal:04d}", "from": "2026-10-05", "to": "2026-10-15"}})
    plan = {"schema_version": "ATLAS_BUY_NOW_HISTORY_BACKFILL_RECOVERY_V1",
            "registered_source_sha": "a" * 40, "original_claim_id": "original",
            "original_claim_scope_sha256": "b" * 64, "request_count": 1046,
            "absolute_request_ceiling": 1046,
            "execution_policy": {"concurrency": 1, "rate_limit_rpm": 60,
                                 "automatic_retries": 0}, "requests": requests}
    plan["plan_sha256"] = digest(plan)
    ordinals = [row["ordinal"] for row in requests]
    import hashlib
    from services.buy_now_history_backfill_execution import canonical
    scope = {"schema": "ATLAS_BUY_NOW_HISTORY_BACKFILL_RECOVERY_CLAIM_V1",
             "claim_id": "recovery-01", "registered_source_sha": "a" * 40,
             "recovery_plan_sha256": plan["plan_sha256"],
             "original_claim_id": "original", "original_claim_scope_sha256": "b" * 64,
             "request_count": 1046,
             "request_ordinals_sha256": hashlib.sha256(canonical(ordinals)).hexdigest(),
             "maximum_requests": 1046, "concurrency": 1, "initial_rpm": 60,
             "automatic_retries": 0}
    scope["claim_scope_sha256"] = digest(scope)
    executor = RecoveryBackfillExecutor(
        state_root=tmp_path / "state", raw_root=tmp_path / "raw", scope=scope,
        plan=plan, token=recovery_authorization_token(scope), execution_id=execution,
        transport=transport)
    return executor, scope, plan


def _transport(calls):
    def call(request):
        calls.append(request["ordinal"])
        body = {"s": "no_data"} if request["endpoint"] == "/stock/candle" else []
        return Response(200, json.dumps(body).encode())
    return call


def test_recovery_executes_only_exact_suffix_and_never_publishes(tmp_path):
    calls = []
    executor, scope, _ = _bound(tmp_path, _transport(calls))
    result = executor.run()
    assert result["status"] == "COMPLETE"
    assert calls == list(range(2849, 3895))
    assert result["authorized_requests"] == result["provider_calls"] == 1046
    assert result["publication_writes"] == result["report_card_mutations"] == 0
    assert result["dispositions"] == {"AVAILABLE": 697, "FINNHUB_NO_DATA": 349}
    claim = json.loads((tmp_path / "state/history_backfill_recovery_claims" /
                        scope["claim_id"] / "claim.json").read_text())
    assert claim["state"] == "COMPLETE"


def test_recovery_duplicate_execution_and_indeterminate_intent_fail_closed(tmp_path):
    calls = []
    executor, scope, plan = _bound(tmp_path, _transport(calls))
    executor.claim_dir.joinpath("intents").mkdir(parents=True)
    executor.claim_dir.joinpath("intents/02849.json").write_text("{}")
    with pytest.raises(RuntimeError, match="ATTEMPT_INDETERMINATE:2849"):
        executor.run()
    assert calls == []
    second = RecoveryBackfillExecutor(
        state_root=tmp_path / "state", raw_root=tmp_path / "raw", scope=scope,
        plan=plan, token=recovery_authorization_token(scope), execution_id="run-2",
        transport=_transport(calls))
    with pytest.raises(PermissionError, match="ALREADY_CONSUMED"):
        second.run()
    assert calls == []


def test_recovery_scope_rejects_any_expansion_or_wrong_token(tmp_path):
    executor, scope, plan = _bound(tmp_path, _transport([]))
    expanded = dict(plan)
    expanded["requests"] = [*plan["requests"], dict(plan["requests"][-1], ordinal=3895)]
    with pytest.raises(PermissionError, match="SCOPE_BINDING_INVALID"):
        validate_recovery_scope(scope, expanded)
    with pytest.raises(PermissionError, match="AUTHORIZATION_INVALID"):
        RecoveryBackfillExecutor(
            state_root=tmp_path / "other", raw_root=tmp_path / "other-raw",
            scope=scope, plan=plan, token="wrong", execution_id="run",
            transport=_transport([]))


def test_registered_recovery_job_is_exactly_bounded_and_never_publishes():
    workflow = Path(".github/workflows/atlas_daily_incremental_buy_now.yml").read_text()
    script = Path("scripts/run_buy_now_history_backfill_recovery.py").read_text()
    assert "protected-history-backfill-recovery-acquisition:" in workflow
    assert "execute_consumed_backfill_recovery_acquisition == true" in workflow
    assert "--request-ceiling 1046" in workflow
    assert "--require-credential" in workflow
    assert "RECOVERY_ARTIFACT_ID: \"12083244989\"" in workflow
    assert "RECOVERY_CLAIM_SCOPE_SHA256: 4d2edddf" in workflow
    assert "ATLAS_BACKFILL_RECOVERY_MANUAL_ACQUIRE_ENABLED" in workflow
    assert "publication_result" not in workflow.split(
        "protected-history-backfill-recovery-acquisition:", 1)[1]
    assert "publication_authorized\": False" in script
    assert "history_backfill_recovery_claims" in Path(
        "services/buy_now_history_backfill_execution.py").read_text()
