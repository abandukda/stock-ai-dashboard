import json
from datetime import datetime, timezone
import hashlib
from pathlib import Path

import pytest

import services.incremental_publication_bridge as bridge
from services.finnhub_incremental_post_close import (
    IncrementalCeiling, accept_receipt, build_incremental_plan, new_checkpoint,
)


def fixture():
    plan = build_incremental_plan(
        session="2026-10-14", customer_symbols=["AAA", "BBB"],
        ceiling=IncrementalCeiling(customer_symbols=2, changed_fundamental_symbols=0),
    )
    checkpoint = new_checkpoint(plan=plan)
    for key in plan["request_keys"]:
        session, symbol, family = key.split(":", 2)
        checkpoint = accept_receipt(plan=plan, checkpoint=checkpoint, receipt={
            "request_key": key, "session": session, "symbol": symbol,
            "family": family, "status": "AVAILABLE", "raw_path": f"{key}.json",
            "raw_sha256": "a" * 64,
        })
    readiness = bridge.publication_readiness(plan=plan, checkpoint=checkpoint)
    records = [{
        "ticker": symbol, "row": {"ticker": symbol},
        "bars": [{"close": 1}], "incremental_receipt_keys": [
            key for key in plan["request_keys"] if f":{symbol}:" in key
        ],
        "incremental_receipt_set_sha256": readiness["receipt_set_sha256"],
        "normalization_method": "EXISTING_FINNHUB_CANONICAL_NORMALIZER",
    } for symbol in ("AAA", "BBB")]
    return plan, checkpoint, records


def successful_aggregate(**kwargs):
    candidate = {
        "candidate_digest": "c" * 64, "supported_symbol_count": 2,
        "source_sha": "s" * 40,
    }
    manifest = {
        "publication_gate_status": "PASS", "run_id": "incremental-test",
        "source_commit_sha": "s" * 40, "artifact_hashes": {},
        "customer_publication_count": 1, "executor_candidate_digest_verified": True,
        "report_card_prospective_active": False,
        "executor_candidate_identity": {
            "candidate_digest": "c" * 64, "source_sha": "s" * 40,
            "universe_sha256": "u" * 64,
        },
    }
    return {
        "new_full_universe_candidate_certified": True,
        "immutable_candidate": candidate,
        "publication_bundle_digest": "p" * 64,
        "full_universe_completeness": {"state": "FULL_UNIVERSE_CERTIFIED", "customer_publishable": True},
        "determinism": {"status": "PASS", "first_digest": "c" * 64, "second_digest": "c" * 64,
                        "structural_diff": {"analytical_mismatch_count": 0}},
        "evidence_inspector_coverage": {"status": "PASS", "failures": []},
        "publication_bundle": {
            "artifacts": {"market_full_scan.json": []}, "manifest": manifest,
        },
    }


def test_complete_incremental_chain_stages_existing_publisher_handoff(monkeypatch, tmp_path):
    plan, checkpoint, records = fixture()
    monkeypatch.setattr(bridge, "aggregate_complete_run", successful_aggregate)
    report = bridge.certify_incremental_candidate(
        plan=plan, checkpoint=checkpoint, acquired_records=records,
        source_sha="s" * 40, candidate_dir=tmp_path, workflow_run_id="123",
    )
    assert report["status"] == "CERTIFIED_NOT_PUBLISHED"
    assert report["production_writes"] == 0
    assert (tmp_path / "publication_bundle" / "market_full_scan.json").is_file()
    assert (tmp_path / "publication_bundle" / "incremental_certification_handoff.json").is_file()
    manifest = tmp_path / "publication_bundle" / "publication_manifest.json"
    assert json.loads(manifest.read_text())["workflow_run_id"] == "123"
    from scripts.validate_full_universe_promotion_input import validate
    validated = validate(
        tmp_path, run_id="123", candidate="c" * 64, publication="",
        source_sha="s" * 40, require_authorization=False,
    )
    assert validated["status"] == "PASS"


@pytest.mark.parametrize("mutation, message", [
    (lambda rows: rows.pop(), "MEMBERSHIP_MISMATCH"),
    (lambda rows: rows.append(dict(rows[0])), "DUPLICATE_SYMBOL"),
    (lambda rows: rows[0].update(bars=[]), "CANONICAL_INPUT_MISSING"),
    (lambda rows: rows[0].update(incremental_receipt_keys=[]), "EVIDENCE_INCOMPLETE"),
    (lambda rows: rows[0].update(incremental_receipt_set_sha256="bad"), "RECEIPT_IDENTITY_MISMATCH"),
    (lambda rows: rows[0].update(normalization_method="NEW_SCORING_PATH"), "PARALLEL_NORMALIZATION_FORBIDDEN"),
])
def test_incomplete_or_conflicting_inputs_fail_before_scoring(monkeypatch, tmp_path, mutation, message):
    plan, checkpoint, records = fixture()
    mutation(records)
    monkeypatch.setattr(
        bridge, "aggregate_complete_run",
        lambda **kwargs: pytest.fail("canonical evaluator must not run"),
    )
    with pytest.raises(ValueError, match=message):
        bridge.certify_incremental_candidate(
            plan=plan, checkpoint=checkpoint, acquired_records=records,
            source_sha="s" * 40, candidate_dir=tmp_path, workflow_run_id="123",
        )


def test_invalid_certification_cannot_stage_or_publish(monkeypatch, tmp_path):
    plan, checkpoint, records = fixture()
    monkeypatch.setattr(bridge, "aggregate_complete_run", lambda **kwargs: {
        "new_full_universe_candidate_certified": False,
    })
    with pytest.raises(ValueError, match="CERTIFIED_CANDIDATE_REJECTED"):
        bridge.certify_incremental_candidate(
            plan=plan, checkpoint=checkpoint, acquired_records=records,
            source_sha="s" * 40, candidate_dir=tmp_path, workflow_run_id="123",
        )
    assert list(tmp_path.iterdir()) == []


def test_raw_receipts_materialize_retained_fundamentals_and_new_completed_bars(tmp_path):
    plan, checkpoint, _ = fixture()
    timestamp = datetime(2026, 10, 14, 20, tzinfo=timezone.utc).timestamp()
    next_checkpoint = dict(checkpoint)
    receipts = {}
    for key, receipt in checkpoint["receipts"].items():
        _, symbol, family = key.split(":", 2)
        provider_record = {
            "provenance": {"certification_status": "CERTIFIED", "raw_evidence_id": key},
            "payload": ({
                "timestamps": [timestamp], "open": [1], "high": [2], "low": [1],
                "close": [1.5], "volume": [100], "completed_session_flags": [True],
            } if family == "completed_session_price" else {"filings": []}),
        }
        body = json.dumps({"request_key": key, "provider_record": provider_record}, sort_keys=True)
        path = tmp_path / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
        path.write_text(body)
        receipts[key] = {**receipt, "raw_path": path.name,
                         "raw_sha256": hashlib.sha256(body.encode()).hexdigest()}
    value = {key: item for key, item in next_checkpoint.items() if key != "checkpoint_sha256"}
    value["receipts"] = receipts
    value["checkpoint_sha256"] = bridge._digest(value)
    rows = bridge.materialize_acquired_records(
        plan=plan, checkpoint=value, raw_root=tmp_path,
        retained_rows=[
            {"ticker": "AAA", "professional_evidence_as_of": "2026-10-01T00:00:00Z"},
            {"ticker": "BBB", "professional_evidence_as_of": "2026-10-01T00:00:00Z"},
        ],
    )
    assert [item["ticker"] for item in rows] == ["AAA", "BBB"]
    assert all(item["row"]["price"] == 1.5 for item in rows)


def test_new_filing_without_bounded_fundamental_expansion_fails_closed(tmp_path):
    plan, checkpoint, _ = fixture()
    timestamp = datetime(2026, 10, 14, 20, tzinfo=timezone.utc).timestamp()
    receipts = {}
    for key, receipt in checkpoint["receipts"].items():
        family = key.split(":", 2)[2]
        provider_record = {"provenance": {"certification_status": "CERTIFIED"}, "payload": (
            {"timestamps": [timestamp], "open": [1], "high": [2], "low": [1],
             "close": [1.5], "volume": [100], "completed_session_flags": [True]}
            if family == "completed_session_price" else
            {"filings": [{"filing_date": "2026-10-10"}]}
        )}
        body = json.dumps({"request_key": key, "provider_record": provider_record}, sort_keys=True)
        path = tmp_path / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
        path.write_text(body)
        receipts[key] = {**receipt, "raw_path": path.name,
                         "raw_sha256": hashlib.sha256(body.encode()).hexdigest()}
    value = {key: item for key, item in checkpoint.items() if key != "checkpoint_sha256"}
    value["receipts"] = receipts
    value["checkpoint_sha256"] = bridge._digest(value)
    with pytest.raises(ValueError, match="CHANGED_FUNDAMENTALS_NOT_ACQUIRED"):
        bridge.materialize_acquired_records(
            plan=plan, checkpoint=value, raw_root=tmp_path,
            retained_rows=[
                {"ticker": "AAA", "professional_evidence_as_of": "2026-10-01T00:00:00Z"},
                {"ticker": "BBB", "professional_evidence_as_of": "2026-10-01T00:00:00Z"},
            ],
        )
