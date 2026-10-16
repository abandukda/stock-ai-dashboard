import json
from datetime import datetime, timezone
from datetime import timedelta
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


def retained_history(*symbols, session="2026-10-14"):
    end = datetime.fromisoformat(session).replace(tzinfo=timezone.utc) - timedelta(days=1)
    return {symbol: [{
        "symbol": symbol, "timestamp": (end - timedelta(days=220-index)).isoformat(),
        "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100,
        "completed": True,
    } for index in range(221)] for symbol in symbols}


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
            "artifacts": {
                "market_full_scan.json": [],
                "full_evaluation_pool.json": [
                    {"ticker": "AAA", "publication_certification": {
                        "customer_publication_allowed": True,
                        "certification_state": "CERTIFIED", "components": {},
                    }},
                    {"ticker": "BBB", "publication_certification": {
                        "customer_publication_allowed": False,
                        "certification_state": "INSUFFICIENT_INPUTS",
                        "components": {"market": {"blockers": ["MARKET_EVIDENCE_STALE"]}},
                    }},
                ],
            }, "manifest": manifest,
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
    assert report["unaccounted_publication_records"] == 0
    assert report["publishable_count"] == 1
    assert report["withheld_count"] == 1
    reconciliation = json.loads((tmp_path / "publication_population_reconciliation.json").read_text())
    assert reconciliation["status"] == "RECONCILED"
    assert reconciliation["observed_count"] == 2
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


def test_provider_free_replay_is_certified_but_never_publication_authorized(monkeypatch, tmp_path):
    plan, checkpoint, records = fixture()
    monkeypatch.setattr(bridge, "aggregate_complete_run", successful_aggregate)
    report = bridge.certify_incremental_candidate(
        plan=plan, checkpoint=checkpoint, acquired_records=records,
        source_sha="s" * 40, candidate_dir=tmp_path, workflow_run_id="replay",
        evidence_classification="PROVIDER_FREE_SIMULATED_REPLAY",
    )
    assert report["status"] == "PROVIDER_FREE_REPLAY_CERTIFIED_NOT_PUBLISHABLE"
    assert report["publication_authorized"] is False
    manifest = json.loads((tmp_path / "publication_bundle" / "publication_manifest.json").read_text())
    assert manifest["incremental_evidence_classification"] == "PROVIDER_FREE_SIMULATED_REPLAY"
    assert manifest["incremental_publication_authorized"] is False


def test_daily_promoter_rejects_provider_free_replay_before_writes(monkeypatch, tmp_path):
    import scripts.promote_daily_buy_now_snapshot as promoter
    bundle = tmp_path / "candidate" / "publication_bundle"
    bundle.mkdir(parents=True)
    (bundle / "publication_manifest.json").write_text(json.dumps({
        "incremental_evidence_classification": "PROVIDER_FREE_SIMULATED_REPLAY",
        "incremental_publication_authorized": False,
    }))
    monkeypatch.setattr(promoter, "validate", lambda *_args, **_kwargs: {"bundle": str(bundle)})
    with pytest.raises(RuntimeError, match="PROVIDER_FREE_REPLAY_PUBLICATION_FORBIDDEN"):
        promoter.promote(
            artifact_root=tmp_path / "candidate", production_root=tmp_path / "production",
            run_id="replay", source_sha="s" * 40, finalized_session="2026-10-15",
        )
    assert not (tmp_path / "production").exists()


def test_retained_technical_history_is_source_bound_complete_and_prior(tmp_path):
    plan, _, _ = fixture()
    plan["governed_membership"] = {
        "source_run_id": "retained-run", "source_commit_sha": "a" * 40,
    }
    payload = {
        "run_identity": {"source_sha": "a" * 40, "run_identity_sha256": "r" * 64},
        "records": [
            {"ticker": symbol, "bars": retained_history(symbol)[symbol]}
            for symbol in ("AAA", "BBB")
        ],
    }
    payload["shard_digest"] = bridge._digest(payload)
    (tmp_path / "shard-000.json").write_text(json.dumps(payload))
    (tmp_path / "shard_manifest.json").write_text(json.dumps({"not": "a payload"}))
    histories, report = bridge.load_retained_technical_history(root=tmp_path, plan=plan)
    assert sorted(histories) == ["AAA", "BBB"]
    assert report["symbol_count"] == 2 and report["minimum_bar_count"] == 221
    assert report["source_commit_sha"] == "a" * 40


def test_short_retained_history_is_explicitly_bound_for_governed_withholding(tmp_path):
    plan, _, _ = fixture()
    plan["governed_membership"] = {
        "source_run_id": "retained-run", "source_commit_sha": "a" * 40,
    }
    short = retained_history("AAA")["AAA"][:25]
    complete = retained_history("BBB")["BBB"]
    payload = {
        "run_identity": {"source_sha": "a" * 40, "run_identity_sha256": "r" * 64},
        "records": [
            {"ticker": "AAA", "bars": short},
            {"ticker": "BBB", "bars": complete},
        ],
    }
    payload["shard_digest"] = bridge._digest(payload)
    (tmp_path / "shard-000.json").write_text(json.dumps(payload))

    histories, report = bridge.load_retained_technical_history(root=tmp_path, plan=plan)

    assert len(histories["AAA"]) == 25
    assert report["minimum_bar_count"] == 25
    assert report["insufficient_history_count"] == 1
    assert report["insufficient_history_symbols"] == {"AAA": 25}


def test_incomplete_retained_tail_is_removed_and_explicitly_blocked(tmp_path):
    plan, _, _ = fixture()
    plan["governed_membership"] = {
        "source_run_id": "retained-run", "source_commit_sha": "a" * 40,
    }
    bars = retained_history("AAA")["AAA"]
    bars[-1]["completed"] = False
    payload = {
        "run_identity": {"source_sha": "a" * 40, "run_identity_sha256": "r" * 64},
        "records": [
            {"ticker": "AAA", "bars": bars},
            {"ticker": "BBB", "bars": retained_history("BBB")["BBB"]},
        ],
    }
    payload["shard_digest"] = bridge._digest(payload)
    (tmp_path / "shard-000.json").write_text(json.dumps(payload))

    histories, report = bridge.load_retained_technical_history(root=tmp_path, plan=plan)

    assert len(histories["AAA"]) == 220
    assert all(item["completed"] for item in histories["AAA"])
    assert report["history_blockers"] == {
        "AAA": ["INCREMENTAL_RETAINED_TECHNICAL_HISTORY_INCOMPLETE"]
    }


def test_empty_retained_history_is_kept_as_explicit_missing_history_blocker(tmp_path):
    plan, _, _ = fixture()
    plan["governed_membership"] = {
        "source_run_id": "retained-run", "source_commit_sha": "a" * 40,
    }
    payload = {
        "run_identity": {"source_sha": "a" * 40, "run_identity_sha256": "r" * 64},
        "records": [
            {"ticker": "AAA", "bars": []},
            {"ticker": "BBB", "bars": retained_history("BBB")["BBB"]},
        ],
    }
    payload["shard_digest"] = bridge._digest(payload)
    (tmp_path / "shard-000.json").write_text(json.dumps(payload))

    histories, report = bridge.load_retained_technical_history(root=tmp_path, plan=plan)

    assert histories["AAA"] == []
    assert report["insufficient_history_symbols"]["AAA"] == 0
    assert report["history_blockers"] == {
        "AAA": ["INCREMENTAL_RETAINED_TECHNICAL_HISTORY_MISSING"]
    }


def test_short_retained_history_becomes_explicit_terminal_blocker(monkeypatch, tmp_path):
    plan, checkpoint, _ = fixture()
    histories = retained_history("AAA", "BBB")
    histories["AAA"] = histories["AAA"][:25]
    retained = [{"ticker": symbol, "professional_evidence_as_of": "2026-10-13"}
                for symbol in ("AAA", "BBB")]
    session_end = datetime(2026, 10, 14, 23, 59, 59, tzinfo=timezone.utc)
    fresh = bridge.deserialize_bars([{
        "symbol": "AAA", "timestamp": session_end.isoformat(),
        "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1,
        "completed": True,
    }])
    monkeypatch.setattr(bridge, "_bars", lambda *_args: fresh)
    monkeypatch.setattr(bridge, "_new_filing", lambda **_kwargs: False)
    monkeypatch.setattr(bridge, "_provider_record", lambda **kwargs: {
        "payload": {"filings": []},
        "provenance": {"raw_evidence_id": kwargs["receipt"]["request_key"]},
    })

    records = bridge.materialize_acquired_records(
        plan=plan, checkpoint=checkpoint, raw_root=tmp_path,
        retained_rows=retained, retained_technical_history=histories,
    )

    by_symbol = {record["ticker"]: record for record in records}
    assert by_symbol["AAA"]["blockers"] == ["INCREMENTAL_TECHNICAL_HISTORY_INSUFFICIENT"]
    assert by_symbol["BBB"]["blockers"] == []


def test_retained_technical_history_rejects_wrong_source(tmp_path):
    plan, _, _ = fixture()
    plan["governed_membership"] = {"source_commit_sha": "a" * 40}
    payload = {
        "run_identity": {"source_sha": "b" * 40, "run_identity_sha256": "r" * 64},
        "records": [{"ticker": "AAA", "bars": retained_history("AAA")["AAA"]}],
    }
    payload["shard_digest"] = bridge._digest(payload)
    (tmp_path / "shard-000.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="SOURCE_MISMATCH"):
        bridge.load_retained_technical_history(root=tmp_path, plan=plan)


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


def test_publication_population_omission_or_unexplained_withholding_fails_closed():
    with pytest.raises(ValueError, match="POPULATION_MISMATCH"):
        bridge.reconcile_publication_population(
            symbols=["AAA", "BBB"], artifacts={"full_evaluation_pool.json": [{
                "ticker": "AAA", "publication_certification": {
                    "customer_publication_allowed": True, "certification_state": "CERTIFIED",
                },
            }]}, source_sha="s" * 40, candidate_digest="c" * 64,
        )
    with pytest.raises(ValueError, match="WITHHOLDING_UNEXPLAINED"):
        bridge.reconcile_publication_population(
            symbols=["AAA"], artifacts={"full_evaluation_pool.json": [{
                "ticker": "AAA", "publication_certification": {
                    "customer_publication_allowed": False,
                    "certification_state": "INSUFFICIENT_INPUTS", "components": {},
                },
            }]}, source_sha="s" * 40, candidate_digest="c" * 64,
        )


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
        retained_technical_history=retained_history("AAA", "BBB"),
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
            retained_technical_history=retained_history("AAA", "BBB"),
            retained_rows=[
                {"ticker": "AAA", "professional_evidence_as_of": "2026-10-01T00:00:00Z"},
                {"ticker": "BBB", "professional_evidence_as_of": "2026-10-01T00:00:00Z"},
            ],
        )
