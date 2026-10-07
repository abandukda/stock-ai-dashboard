import hashlib
import json
from types import SimpleNamespace

import pytest

import services.finnhub_full_universe_executor as executor
import scripts.run_finnhub_full_universe as runner


def _universe(symbols=("A",)):
    return {
        "source_sha256": "universe-sha", "supported_equity_count": len(symbols),
        "supported_symbols": list(symbols), "universe_methodology_version": "U1",
    }


def _identity(symbols=("A",)):
    return executor.build_run_identity(
        universe=_universe(symbols), evidence_snapshot_at="2026-10-06T20:00:00+00:00",
        source_sha="a" * 40,
    )


def _success(symbol, capability):
    return {
        "payload": {},
        "provenance": {
            "provider": "FINNHUB", "certification_status": "CERTIFIED",
            "derived_use_permission": "CERTIFIED_CALCULATION",
            "raw_evidence_id": f"{symbol}:{capability}",
        },
    }


class _Governor:
    class Contract:
        def as_dict(self):
            return {"global_requests_per_minute": 500, "global_requests_per_second_ceiling": 20}

    contract = Contract()
    wait_seconds = 0.0
    peak_requests_per_second = 1

    def __init__(self):
        self.starts = 0
        self.delays = []

    def before_request(self):
        self.starts += 1

    def retry_delay(self, seconds):
        self.delays.append(seconds)
        self.wait_seconds += seconds


def _acquire(monkeypatch, responses):
    calls = []

    def fetch(_adapter, capability, symbol, _pace, **_params):
        calls.append((symbol, capability))
        if capability == "company_profile" and responses:
            return responses.pop(0)
        return _success(symbol, capability)

    monkeypatch.setattr(executor, "_fetch", fetch)
    monkeypatch.setattr(executor, "_normalized_row", lambda symbol, *_args: ({"ticker": symbol}, [], []))
    governor = _Governor()
    payload = executor.acquire_shard(
        adapter=object(), estimate_adapter=object(),
        shard=executor.deterministic_shards(["A"], shard_size=1)[0],
        identity=_identity(), catalog={}, rate_governor=governor,
        strict_provider_health=True,
    )
    return payload, governor, calls


def test_readtimeout_then_success_consumes_one_governed_retry(monkeypatch):
    payload, governor, calls = _acquire(monkeypatch, [
        {"payload": {"reason": "READTIMEOUT"}}, _success("A", "company_profile"),
    ])
    telemetry = payload["provider_telemetry"]
    assert telemetry["provider_calls"] == 7
    assert telemetry["fresh_provider_calls"] == 6
    assert telemetry["retry_provider_calls"] == 1
    assert telemetry["duplicate_or_reacquired_requests"] == 0
    assert governor.starts == 7 and len(governor.delays) == 1
    assert len(calls) == 7


def test_readtimeout_exhausting_budget_stops(monkeypatch):
    with pytest.raises(RuntimeError, match="READTIMEOUT:RETRY_BUDGET_EXHAUSTED"):
        _acquire(monkeypatch, [{"payload": {"reason": "READTIMEOUT"}} for _ in range(3)])


def test_approved_transient_503_retries_then_succeeds(monkeypatch):
    payload, governor, _calls = _acquire(monkeypatch, [
        {"payload": {"reason": "HTTP_503"}}, _success("A", "company_profile"),
    ])
    assert payload["provider_telemetry"]["http_5xx_count"] == 1
    assert payload["provider_telemetry"]["retry_count"] == 1
    assert len(governor.delays) == 1


@pytest.mark.parametrize("reason", ["HTTP_429", "HTTP_400"])
def test_governance_and_deterministic_4xx_stop_without_retry(monkeypatch, reason):
    calls = []
    monkeypatch.setattr(executor, "_fetch", lambda *_args, **_kwargs: (
        calls.append(1) or {"payload": {"reason": reason}}
    ))
    shard = executor.deterministic_shards(["A"], shard_size=1)[0]
    with pytest.raises(RuntimeError, match=reason):
        executor.acquire_shard(
            adapter=object(), shard=shard, identity=_identity(), catalog={},
            rate_governor=_Governor(), strict_provider_health=True,
        )
    assert len(calls) == 1


def _write_certified(root, shard, identity, *, source_override=None):
    payload = {
        "run_identity": identity, "shard": dict(shard),
        "records": [{"ticker": symbol} for symbol in shard["symbols"]],
        "provider_telemetry": {"provider_calls": 6 * len(shard["symbols"]),
                               "fresh_provider_calls": 6 * len(shard["symbols"]), "retry_count": 0},
    }
    payload["shard_digest"] = executor._digest(payload)
    payload_path = root / f"{shard['shard_id']}.json"
    runner._write(payload_path, payload)
    contract = runner._shard_contract(
        identity=identity, shard=shard, configured_rpm=500, parallel_workers=5,
    )
    if source_override is not None:
        contract["source_sha"] = source_override
    checkpoint = executor.build_certified_shard_checkpoint(
        payload=payload, artifact_digest=hashlib.sha256(payload_path.read_bytes()).hexdigest(),
        contract=contract,
    )
    runner._write(root / "certification" / f"{shard['shard_id']}.checkpoint.json", checkpoint)
    return payload, contract


def test_successful_checkpoint_reuses_without_provider_calls(tmp_path):
    shard = executor.deterministic_shards(["A"], shard_size=1)[0]
    identity = _identity()
    payload, contract = _write_certified(tmp_path, shard, identity)
    reused = runner._reuse_certified_shard(
        resume_root=tmp_path, shard=shard, expected_contract=contract,
    )
    assert reused is not None and reused[0] == payload


def test_partial_shard_cannot_create_certified_checkpoint(tmp_path):
    shard = executor.deterministic_shards(["A", "B"], shard_size=2)[0]
    contract = runner._shard_contract(
        identity=_identity(("A", "B")), shard=shard, configured_rpm=500, parallel_workers=5,
    )
    payload = {
        "shard": dict(shard), "records": [{"ticker": "A"}], "shard_digest": "partial",
        "provider_telemetry": {"provider_calls": 6, "retry_count": 0},
    }
    with pytest.raises(ValueError, match="partial shard"):
        executor.build_certified_shard_checkpoint(
            payload=payload, artifact_digest="artifact", contract=contract,
        )


def test_failed_shard_writes_no_certified_checkpoint(monkeypatch, tmp_path):
    scope = _universe()
    monkeypatch.setattr(runner, "load_frozen_universe", lambda _path: scope)
    monkeypatch.setattr(runner, "load_governed_classifications", lambda: ({}, {}))
    monkeypatch.setattr(runner, "FinnhubCanonicalAdapter", lambda: object())
    monkeypatch.setattr(runner, "FinnhubShadowAdapter", lambda **_kwargs: object())
    monkeypatch.setattr(runner, "build_parallel_rate_governor", lambda **_kwargs: _Governor())
    monkeypatch.setattr(runner, "acquire_shard", lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("STRICT_PROVIDER_HEALTH_STOP:A:company_profile:READTIMEOUT:RETRY_BUDGET_EXHAUSTED")
    ))
    args = SimpleNamespace(
        universe=tmp_path / "universe.json", canary_size=0,
        evidence_snapshot="2026-10-06T20:00:00+00:00", source_sha="a" * 40,
        shard_size=1, shard_index=0, global_requests_per_minute=500,
        certify_shard_checkpoint=True, parallel_workers=5, resume_shards=None,
        pace_seconds=0, checkpoint_dir=tmp_path / "symbol-checkpoints",
        strict_provider_health=True, output=tmp_path / "output",
    )
    with pytest.raises(RuntimeError, match="RETRY_BUDGET_EXHAUSTED"):
        runner.run_shard(args)
    assert not list((tmp_path / "output").rglob("*.checkpoint.json"))


def test_corrupt_checkpoint_is_rejected(tmp_path):
    shard = executor.deterministic_shards(["A"], shard_size=1)[0]
    identity = _identity(); _, contract = _write_certified(tmp_path, shard, identity)
    path = tmp_path / "certification" / "shard-000.checkpoint.json"
    data = json.loads(path.read_text()); data["completed_symbol_count"] = 0
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="manifest digest"):
        runner._reuse_certified_shard(resume_root=tmp_path, shard=shard, expected_contract=contract)


def test_source_sha_and_symbol_set_mismatch_are_rejected(tmp_path):
    shard = executor.deterministic_shards(["A"], shard_size=1)[0]
    identity = _identity(); _, contract = _write_certified(tmp_path, shard, identity)
    wrong_source = {**contract, "source_sha": "b" * 40}
    with pytest.raises(ValueError, match="source_sha mismatch"):
        runner._reuse_certified_shard(resume_root=tmp_path, shard=shard, expected_contract=wrong_source)
    wrong_symbols = {**contract, "expected_symbols": ["B"]}
    with pytest.raises(ValueError, match="expected_symbols mismatch"):
        runner._reuse_certified_shard(resume_root=tmp_path, shard=shard, expected_contract=wrong_symbols)


def test_provider_contract_and_retry_policy_mismatch_are_rejected(tmp_path):
    shard = executor.deterministic_shards(["A"], shard_size=1)[0]
    identity = _identity(); _, contract = _write_certified(tmp_path, shard, identity)
    wrong_provider = {**contract, "provider_configuration_identity": "wrong"}
    with pytest.raises(ValueError, match="provider_configuration_identity mismatch"):
        runner._reuse_certified_shard(resume_root=tmp_path, shard=shard, expected_contract=wrong_provider)
    wrong_retry = {**contract, "retry_policy_version": "wrong"}
    with pytest.raises(ValueError, match="retry_policy_version mismatch"):
        runner._reuse_certified_shard(resume_root=tmp_path, shard=shard, expected_contract=wrong_retry)


def test_missing_or_failed_shard_is_reacquired_not_reused(tmp_path):
    shard = executor.deterministic_shards(["A"], shard_size=1)[0]
    contract = runner._shard_contract(
        identity=_identity(), shard=shard, configured_rpm=500, parallel_workers=5,
    )
    assert runner._reuse_certified_shard(
        resume_root=tmp_path, shard=shard, expected_contract=contract,
    ) is None


def test_aggregation_requires_all_41_certified_shards(tmp_path):
    symbols = tuple(f"S{index:03d}" for index in range(41))
    identity = _identity(symbols)
    shards = executor.deterministic_shards(symbols, shard_size=1)
    for shard in shards[:-1]:
        _write_certified(tmp_path, shard, identity)
    with pytest.raises(ValueError, match="41/41"):
        runner._validate_certified_shard_set(
            root=tmp_path, identity=identity, shards=shards,
            configured_rpm=500, parallel_workers=5,
        )
    _write_certified(tmp_path, shards[-1], identity)
    runner._validate_certified_shard_set(
        root=tmp_path, identity=identity, shards=shards,
        configured_rpm=500, parallel_workers=5,
    )


def test_retry_telemetry_does_not_change_deterministic_analytical_replay():
    record = {
        "ticker": "A", "canonical_action": "WAIT_FOR_CONFIRMATION",
        "terminal_data_state": "CERTIFIED_EVALUATION",
        "evaluation": {"opportunity": 70, "decision_confidence": 80},
    }
    first = {"evaluations": [record], "provider_telemetry": {"retry_count": 0}}
    second = {"evaluations": [record], "provider_telemetry": {"retry_count": 2}}
    comparison = executor.compare_replay_candidates(first, second)
    assert comparison["analytical_mismatch_count"] == 0
    assert comparison["classifications"]["ACTION_DIFFERENCE"] == 0
