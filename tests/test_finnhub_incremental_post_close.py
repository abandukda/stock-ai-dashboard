import pytest
import json
import subprocess
import sys

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
