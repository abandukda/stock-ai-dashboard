import pytest
import json
import subprocess
import sys
from datetime import datetime, timezone

from services.finnhub_incremental_post_close import (
    FUNDAMENTAL_FAMILIES,
    IncrementalCeiling,
    build_incremental_plan,
    accept_receipt,
    classify_retry,
    load_checkpoint,
    new_checkpoint,
    publication_readiness,
    resume_request_keys,
    validate_incremental_receipts,
    write_checkpoint_atomic,
    execute_incremental_plan,
    load_governed_membership,
    prepare_certification_handoff,
    canonical_transport_parameters,
)
from services.incremental_provider_free_replay import ProviderFreeReplayAdapter
from services.incremental_provider_free_replay import (
    resolve_replay_retained_records, validate_replay_retained_scope,
)


def symbols(count=1298):
    return [f"S{index:04d}" for index in range(count)]


def test_first_live_plan_has_exact_bounded_ceiling_and_zero_provider_calls():
    plan = build_incremental_plan(
        session="2026-10-14", customer_symbols=symbols(),
        changed_fundamental_symbols=symbols(50),
    )
    assert plan["provider_calls"] == 0
    assert plan["request_count"] == plan["exact_max_requests"] == 2746
    assert plan["request_ceiling"] == {
        "completed_session_price": 1298,
        "filing_change_probe": 1298,
        "changed_fundamentals": 150,
    }
    assert len(plan["request_keys"]) == len(set(plan["request_keys"]))
    assert plan["methodology_mutation"] == "NONE"
    assert plan["publication_mode"] == "EXISTING_ATOMIC_PROMOTER"


def test_changed_fundamentals_are_the_only_deep_fundamental_requests():
    changed = ["S0002", "S0001"]
    plan = build_incremental_plan(
        session="2026-10-14", customer_symbols=symbols(),
        changed_fundamental_symbols=changed,
    )
    assert plan["request_count"] == 1298 * 2 + len(changed) * len(FUNDAMENTAL_FAMILIES)
    for family in FUNDAMENTAL_FAMILIES:
        assert plan["family_counts"][family] == 2


def test_scope_and_change_ceiling_fail_closed():
    with pytest.raises(ValueError, match="CUSTOMER_SCOPE_MISMATCH"):
        build_incremental_plan(session="2026-10-14", customer_symbols=symbols(1297))
    with pytest.raises(ValueError, match="CHANGE_CEILING_EXCEEDED"):
        build_incremental_plan(
            session="2026-10-14", customer_symbols=symbols(),
            changed_fundamental_symbols=symbols(51),
        )
    with pytest.raises(ValueError, match="OUTSIDE_SCOPE"):
        build_incremental_plan(
            session="2026-10-14", customer_symbols=symbols(),
            changed_fundamental_symbols=["OTHER"],
        )


def test_receipts_require_exact_fresh_complete_deduplicated_plan_ownership():
    ceiling = IncrementalCeiling(customer_symbols=2, changed_fundamental_symbols=0)
    plan = build_incremental_plan(
        session="2026-10-14", customer_symbols=["A", "B"], ceiling=ceiling,
    )
    receipts = [
        {"request_key": key, "session": "2026-10-14", "status": "AVAILABLE"}
        for key in plan["request_keys"]
    ]
    assert validate_incremental_receipts(plan=plan, receipts=receipts)["status"] == "PASS"
    with pytest.raises(ValueError, match="INCOMPLETE"):
        validate_incremental_receipts(plan=plan, receipts=receipts[:-1])
    with pytest.raises(ValueError, match="DUPLICATE"):
        validate_incremental_receipts(plan=plan, receipts=[*receipts, receipts[0]])
    stale = [dict(item) for item in receipts]
    stale[0]["session"] = "2026-10-13"
    with pytest.raises(ValueError, match="STALE_SESSION"):
        validate_incremental_receipts(plan=plan, receipts=stale)


def test_cli_reads_only_customer_publication_scope_and_writes_plan_atomically(tmp_path):
    rows = [
        {"ticker": ticker, "publication_certification": {"customer_publication_allowed": True}}
        for ticker in symbols()
    ]
    rows.append({"ticker": "INTERNAL", "publication_certification": {"customer_publication_allowed": False}})
    publication = tmp_path / "market_full_scan.json"
    output = tmp_path / "plan.json"
    publication.write_text(json.dumps(rows))
    subprocess.run([
        sys.executable, "scripts/plan_finnhub_incremental_post_close.py",
        "--session", "2026-10-14", "--publication", str(publication),
        "--output", str(output),
    ], check=True)
    plan = json.loads(output.read_text())
    assert plan["customer_symbol_count"] == 1298
    assert plan["request_count"] == 2596
    assert plan["provider_calls"] == 0


def small_plan():
    return build_incremental_plan(
        session="2026-10-14", customer_symbols=["A", "B"],
        ceiling=IncrementalCeiling(customer_symbols=2, changed_fundamental_symbols=0),
    )


def receipt(plan, key):
    return {"request_key": key, "session": plan["session"], "status": "AVAILABLE"}


def test_partial_acquisition_checkpoint_resumes_only_missing_requests(tmp_path):
    plan = small_plan()
    checkpoint = new_checkpoint(plan=plan)
    checkpoint = accept_receipt(plan=plan, checkpoint=checkpoint,
                                receipt=receipt(plan, plan["request_keys"][0]))
    path = tmp_path / "durable/checkpoint.json"
    write_checkpoint_atomic(path=path, checkpoint=checkpoint)
    restored = load_checkpoint(path=path, plan=plan)
    assert resume_request_keys(plan=plan, checkpoint=restored) == plan["request_keys"][1:]
    assert restored["telemetry"] == {
        "attempted_requests": 1, "accepted_receipts": 1, "automatic_retries": 0,
    }


def test_interruption_before_checkpoint_write_replays_only_uncommitted_receipt(tmp_path):
    plan = small_plan()
    durable = new_checkpoint(plan=plan)
    path = tmp_path / "checkpoint.json"
    write_checkpoint_atomic(path=path, checkpoint=durable)
    _interrupted_in_memory = accept_receipt(
        plan=plan, checkpoint=durable, receipt=receipt(plan, plan["request_keys"][0])
    )
    restored = load_checkpoint(path=path, plan=plan)
    assert resume_request_keys(plan=plan, checkpoint=restored) == plan["request_keys"]


def test_corrupt_checkpoint_fails_closed(tmp_path):
    plan = small_plan()
    path = tmp_path / "checkpoint.json"
    path.write_text('{"checkpoint_version":"tampered"}')
    with pytest.raises(ValueError, match="CORRUPT"):
        load_checkpoint(path=path, plan=plan)


def test_duplicate_execution_is_idempotent_but_conflict_fails():
    plan = small_plan()
    item = receipt(plan, plan["request_keys"][0])
    once = accept_receipt(plan=plan, checkpoint=new_checkpoint(plan=plan), receipt=item)
    twice = accept_receipt(plan=plan, checkpoint=once, receipt=item)
    assert twice == once
    with pytest.raises(ValueError, match="CONFLICTING_DUPLICATE"):
        accept_receipt(plan=plan, checkpoint=once, receipt={**item, "value": 2})


def test_storage_failure_does_not_leave_partial_checkpoint(monkeypatch, tmp_path):
    plan = small_plan()
    path = tmp_path / "checkpoint.json"
    def fail_replace(self, target):
        raise OSError("injected storage failure")
    monkeypatch.setattr(type(path), "replace", fail_replace)
    with pytest.raises(OSError, match="storage failure"):
        write_checkpoint_atomic(path=path, checkpoint=new_checkpoint(plan=plan))
    assert not path.exists()
    assert not path.with_suffix(".json.tmp").exists()


def test_partial_publication_boundary_and_completed_readiness_are_provider_free():
    plan = small_plan()
    checkpoint = new_checkpoint(plan=plan)
    with pytest.raises(ValueError, match="PARTIAL_PUBLICATION_FORBIDDEN"):
        publication_readiness(plan=plan, checkpoint=checkpoint)
    for key in plan["request_keys"]:
        checkpoint = accept_receipt(
            plan=plan, checkpoint=checkpoint, receipt=receipt(plan, key)
        )
    ready = publication_readiness(plan=plan, checkpoint=checkpoint)
    assert ready["status"] == "READY_FOR_EXISTING_ATOMIC_PROMOTER"
    assert ready["provider_calls"] == ready["production_writes"] == 0
    assert ready["methodology_mutation"] == "NONE"


@pytest.mark.parametrize("code,retryable", [
    ("TIMEOUT", True), ("HTTP_429", True), ("SCHEMA_INVALID", False),
])
def test_retry_classification_never_authorizes_automatic_retry(code, retryable):
    decision = classify_retry(failure_code=code)
    assert decision["retryable_class"] is retryable
    assert decision["automatic_retry_limit"] == 0
    assert decision["automatic_retry_authorized"] is False


def test_telemetry_ceiling_tampering_is_rejected():
    plan = small_plan()
    checkpoint = new_checkpoint(plan=plan)
    body = {key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"}
    body["telemetry"] = {"attempted_requests": 5, "accepted_receipts": 0, "automatic_retries": 0}
    from services.finnhub_incremental_post_close import _digest
    body["checkpoint_sha256"] = _digest(body)
    with pytest.raises(ValueError, match="TELEMETRY_CEILING"):
        resume_request_keys(plan=plan, checkpoint=body)


def test_governed_membership_is_source_bound_not_repository_subset(monkeypatch, tmp_path):
    tickers = symbols()
    records = [{
        "ticker": ticker, "source_sha": "source", "candidate_digest": "candidate",
        "publication_certification": {"ticker": ticker, "customer_publication_allowed": True},
    } for ticker in tickers]
    manifest = {
        "workflow_run_id": "37216506983", "customer_publication_count": 1298,
        "source_commit_sha": "source", "executor_candidate_identity": {"candidate_digest": "candidate"},
        "artifact_hashes": {"full_evaluation_pool.json": "semantic"},
        "artifact_lineage": {"full_evaluation_pool.json": {"semantic_sha256": "semantic"}},
    }
    records_path, manifest_path = tmp_path / "records.json", tmp_path / "manifest.json"
    records_path.write_text(json.dumps(records)); manifest_path.write_text(json.dumps(manifest))
    import scripts.plan_ws3_published_acquisition as ws3
    monkeypatch.setattr(ws3, "EXPECTED_MEMBERSHIP_SHA256", ws3.digest(tickers))
    membership = load_governed_membership(records_path=records_path, manifest_path=manifest_path)
    plan = build_incremental_plan(
        session="2026-10-14", customer_symbols=membership["tickers"],
        governed_membership=membership,
    )
    assert plan["customer_symbol_count"] == 1298
    assert plan["governed_membership"]["source_run_id"] == "37216506983"
    tampered = dict(membership); tampered["tickers"] = membership["tickers"][:-1] + ["ZZZ"]
    with pytest.raises(ValueError, match="TICKERS_MISMATCH"):
        build_incremental_plan(
            session="2026-10-14", customer_symbols=membership["tickers"],
            governed_membership=tampered,
        )


class FakeAdapter:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def fetch(self, capability, symbol, **parameters):
        self.calls.append((capability, symbol, parameters))
        if len(self.calls) == self.fail_at:
            raise TimeoutError("injected")
        return {"payload": {"symbol": symbol}, "provenance": {"capability": capability}}


def transport_parameters():
    return {
        "completed_session_price": {
            "resolution": "D", "from": "2026-10-14", "to": "2026-10-14",
        },
        "filing_change_probe": {"from": "2026-10-14", "to": "2026-10-14"},
        **{family: {"bounded_window": "fixture"} for family in FUNDAMENTAL_FAMILIES},
    }


def test_completed_session_price_uses_finnhub_unix_second_contract():
    result = canonical_transport_parameters(
        family="completed_session_price",
        parameters={"resolution": "D", "from": "2026-10-15", "to": "2026-10-15"},
        session="2026-10-15",
    )
    assert result == {
        "resolution": "D",
        "from": int(datetime(2026, 10, 15, tzinfo=timezone.utc).timestamp()),
        "to": int(datetime(2026, 10, 16, tzinfo=timezone.utc).timestamp()) - 1,
    }


def test_provider_free_replay_proves_timestamp_contract_and_fixture_identity():
    adapter = ProviderFreeReplayAdapter(
        retained_rows=[{"ticker": "A", "current_price": 42.0}], session="2026-10-15",
    )
    record = adapter.fetch(
        "historical_ohlcv", "A", resolution="D",
        **{"from": 1792022400, "to": 1792108799},
    )
    assert record["payload"]["close"] == [42.0]
    assert record["provenance"]["fixture_classification"] == "SIMULATED_NOT_PROVIDER_EVIDENCE"
    with pytest.raises(ValueError, match="TIMESTAMP_CONTRACT"):
        adapter.fetch("historical_ohlcv", "A", resolution="D", **{"from": "2026-10-15", "to": "2026-10-15"})


def test_retained_resolver_uses_plan_digest_not_filesystem_first_match(tmp_path):
    plan = small_plan()
    rows = [
        {"ticker": "A", "current_price": 1}, {"ticker": "B", "current_price": 2},
        {"ticker": "C", "publication_certification": {
            "customer_publication_allowed": False, "certification_state": "WITHHELD",
            "blockers": ["MISSING_EVIDENCE"],
        }},
        {"ticker": "D", "publication_certification": {
            "customer_publication_allowed": False, "certification_state": "UNSUPPORTED",
        }},
    ]
    raw = json.dumps(rows, sort_keys=True).encode()
    import hashlib
    plan["governed_membership"] = {"source_file_sha256": hashlib.sha256(raw).hexdigest()}
    wrong = tmp_path / "00-wrong" / "full_evaluation_pool.json"
    right = tmp_path / "99-right" / "full_evaluation_pool.json"
    duplicate = tmp_path / "zz-duplicate" / "full_evaluation_pool.json"
    wrong.parent.mkdir(); right.parent.mkdir(); duplicate.parent.mkdir()
    wrong.write_text(json.dumps({"rows": rows}))
    right.write_bytes(raw); duplicate.write_bytes(raw)
    selected, report = resolve_replay_retained_records(artifact_root=tmp_path, plan=plan)
    assert [row["ticker"] for row in selected] == ["A", "B"]
    assert report["selected_relative_path"] == "99-right/full_evaluation_pool.json"
    assert report["candidate_count"] == 3 and report["matching_source_count"] == 2
    assert report["candidates"][0]["schema"] == "DICT"
    assert report["source_row_count"] == 4
    assert report["selected_row_count"] == 2
    assert report["excluded_row_count"] == 2
    assert report["excluded_reason_counts"] == {"MISSING_EVIDENCE": 1, "UNSUPPORTED": 1}


def test_retained_scope_rejects_schema_duplicates_and_membership_drift():
    plan = small_plan()
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        validate_replay_retained_scope(retained_rows={"rows": []}, plan=plan)
    with pytest.raises(ValueError, match="DUPLICATE_SYMBOL"):
        validate_replay_retained_scope(retained_rows=[{"ticker": "A"}, {"ticker": "A"}], plan=plan)
    with pytest.raises(ValueError, match="MEMBERSHIP_MISMATCH:2:2"):
        validate_replay_retained_scope(retained_rows=[{"ticker": "A"}, {"ticker": "C"}], plan=plan)


@pytest.mark.parametrize("rows,message", [
    ([{"ticker": "A"}, {"ticker": "A"}, {"ticker": "B"}], "DUPLICATE_SYMBOL:A"),
    ([{"ticker": "A"}, {"ticker": "C"}], "PLAN_TICKER_MISSING:B"),
    ([{"ticker": "A"}, {"ticker": "B"}, {"ticker": ""}], "TICKER_INVALID"),
])
def test_retained_resolver_fails_before_projection_on_source_integrity_errors(tmp_path, rows, message):
    plan = small_plan()
    raw = json.dumps(rows, sort_keys=True).encode()
    import hashlib
    plan["governed_membership"] = {"source_file_sha256": hashlib.sha256(raw).hexdigest()}
    path = tmp_path / "full_evaluation_pool.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match=message):
        resolve_replay_retained_records(artifact_root=tmp_path, plan=plan)


@pytest.mark.parametrize("parameters", [
    {"resolution": "D", "from": "2026-10-14", "to": "2026-10-15"},
    {"resolution": "5", "from": "2026-10-15", "to": "2026-10-15"},
])
def test_completed_session_price_rejects_scope_or_resolution_drift(parameters):
    with pytest.raises(ValueError, match="INCREMENTAL_PRICE_"):
        canonical_transport_parameters(
            family="completed_session_price", parameters=parameters, session="2026-10-15",
        )


def test_raw_first_transport_checkpoint_and_certification_handoff_are_non_promoting(tmp_path):
    plan = small_plan(); adapter = FakeAdapter()
    result = execute_incremental_plan(
        plan=plan, adapter=adapter, raw_root=tmp_path / "raw",
        checkpoint_path=tmp_path / "checkpoint.json", parameters_by_family=transport_parameters(),
    )
    assert result["status"] == "ACQUISITION_COMPLETE_PUBLICATION_NOT_PERFORMED"
    assert result["attempts_this_run"] == 4 and len(adapter.calls) == 4
    price_call = next(item for item in adapter.calls if item[0] == "historical_ohlcv")
    assert isinstance(price_call[2]["from"], int) and isinstance(price_call[2]["to"], int)
    assert price_call[2]["from"] < price_call[2]["to"]
    checkpoint = load_checkpoint(path=tmp_path / "checkpoint.json", plan=plan)
    for value in checkpoint["receipts"].values():
        raw = tmp_path / "raw" / value["raw_path"]
        import hashlib
        assert raw.exists() and hashlib.sha256(raw.read_bytes()).hexdigest() == value["raw_sha256"]
    certification = {
        "methodology_mutation": "NONE", "publication_gate_status": "PASS",
        "input_receipt_set_sha256": result["readiness"]["receipt_set_sha256"],
        "certification_run_id": "provider-free-fixture",
    }
    handoff = prepare_certification_handoff(
        plan=plan, checkpoint=checkpoint, candidate_dir=tmp_path / "candidate",
        certification=certification,
    )
    assert handoff["production_writes"] == 0
    assert handoff["required_promoter"].endswith("promote_atomically")


def test_transport_failure_is_raw_persisted_zero_retry_and_no_handoff(tmp_path):
    plan = small_plan(); adapter = FakeAdapter(fail_at=2)
    with pytest.raises(RuntimeError, match="PROVIDER_ATTEMPT_FAILED"):
        execute_incremental_plan(
            plan=plan, adapter=adapter, raw_root=tmp_path / "raw",
            checkpoint_path=tmp_path / "checkpoint.json", parameters_by_family=transport_parameters(),
        )
    assert len(adapter.calls) == 2
    raws = list((tmp_path / "raw").glob("*.json"))
    assert len(raws) == 2
    assert any(json.loads(path.read_text()).get("status") == "FAILED" for path in raws)
    checkpoint = load_checkpoint(path=tmp_path / "checkpoint.json", plan=plan)
    assert checkpoint["telemetry"]["accepted_receipts"] == 1


def test_adapter_unavailable_record_fails_closed(tmp_path):
    class UnavailableAdapter:
        def fetch(self, *_args, **_kwargs):
            return {"payload": {}, "provenance": {"certification_status": "ENTITLEMENT_UNAVAILABLE"}}
    with pytest.raises(RuntimeError, match="PROVIDER_RECORD_UNAVAILABLE"):
        execute_incremental_plan(
            plan=small_plan(), adapter=UnavailableAdapter(), raw_root=tmp_path / "raw",
            checkpoint_path=tmp_path / "checkpoint.json", parameters_by_family=transport_parameters(),
        )
