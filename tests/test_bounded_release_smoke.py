import hashlib
import json
from argparse import Namespace
from pathlib import Path

from agents.visual_qa_certification_v2 import candidate_identity
from scripts.run_bounded_release_smoke import (
    PUBLICATION_FILES,
    _action,
    _canonical_digest,
    _materialize_runtime_expectations,
    _materialize_runtime_projection_contract,
    _semantic_json_sha256,
    _verify_publication_artifact_hashes,
    _verify_fresh_artifact_contract,
    _verify_fresh_backend_handoff,
    _verify_fresh_inventory,
    _stream_customer_rows,
    _stream_top_level_scalars,
    run,
)


SOURCE_SHA = "d5526664b1b4450e67b63a67b01d936f6da5a2a4"


def _expectations(candidate="c" * 64, publication="p" * 64, source=SOURCE_SHA):
    return {
        "identity": {
            "candidate_digest": candidate,
            "publication_digest": publication,
            "source_sha": source,
        },
        "expected_facts": {
            "NVDA": {"action": "BUY_NOW", "atlas_fair_value": 346.05},
            "MSFT": {"action": "BUY_NOW", "atlas_fair_value": 704.48},
            "AVT": {"action": "BUY_NOW", "atlas_fair_value": 130.97},
        },
        "source_inventory": {
            "canonical_buy_now": ["NVDA"], "publishable_buy_now": ["NVDA"],
            "withheld_buy_now": [],
        },
    }


def _materialize(source_dir, runtime, **overrides):
    return _materialize_runtime_expectations(
        source_dir=source_dir,
        runtime=runtime,
        candidate_digest=overrides.get("candidate", "c" * 64),
        publication_digest=overrides.get("publication", "p" * 64),
        source_sha=overrides.get("source", SOURCE_SHA),
        research_tickers=overrides.get("tickers", ("NVDA", "MSFT", "AVT")),
    )


def test_fresh_runtime_expectations_are_materialized_exactly(tmp_path):
    source_dir, runtime = tmp_path / "source", tmp_path / "runtime"
    expected = _expectations()
    _write(source_dir / "runtime_projection_expectations_candidate.json", expected)
    target = _materialize(source_dir, runtime)
    assert target.parent == runtime / "certification"
    assert json.loads(target.read_text()) == expected
    assert len(list(target.parent.glob("runtime_projection_expectations_*.json"))) == 1
    assert json.loads(target.read_text())["expected_facts"] == expected["expected_facts"]


def test_fresh_runtime_expectations_fail_closed_on_zero_or_duplicate_files(tmp_path):
    source_dir, runtime = tmp_path / "source", tmp_path / "runtime"
    source_dir.mkdir()
    try:
        _materialize(source_dir, runtime)
    except ValueError as error:
        assert str(error) == "RUNTIME_EXPECTATIONS_SOURCE_MISSING"
    else:
        raise AssertionError("zero expectations files must fail closed")

    _write(source_dir / "runtime_projection_expectations_one.json", _expectations())
    _write(source_dir / "runtime_projection_expectations_two.json", _expectations())
    try:
        _materialize(source_dir, runtime)
    except ValueError as error:
        assert str(error) == "RUNTIME_EXPECTATIONS_SOURCE_AMBIGUOUS:2"
    else:
        raise AssertionError("duplicate candidate expectations must fail closed")


def test_fresh_runtime_expectations_fail_closed_on_identity_or_ticker_mismatch(tmp_path):
    cases = (
        (_expectations(candidate="x" * 64), {}, "RUNTIME_EXPECTATIONS_CANDIDATE_MISMATCH"),
        (_expectations(publication="x" * 64), {}, "RUNTIME_EXPECTATIONS_PUBLICATION_MISMATCH"),
        (_expectations(source="x" * 40), {}, "RUNTIME_EXPECTATIONS_SOURCE_SHA_MISMATCH"),
        (_expectations(), {"tickers": ("NVDA", "MSFT")}, "RUNTIME_EXPECTATIONS_TICKER_SET_MISMATCH"),
    )
    for index, (payload, overrides, expected_error) in enumerate(cases):
        source_dir, runtime = tmp_path / f"source-{index}", tmp_path / f"runtime-{index}"
        _write(source_dir / "runtime_projection_expectations_candidate.json", payload)
        try:
            _materialize(source_dir, runtime, **overrides)
        except ValueError as error:
            assert str(error) == expected_error
        else:
            raise AssertionError(f"{expected_error} must fail closed")


def test_legacy_bounded_runtime_does_not_require_expectations_contract(tmp_path):
    # The legacy run fixture exercises the existing path without supplying a
    # runtime expectations directory; its successful run below is the contract.
    assert not (tmp_path / "certification").exists()


def test_bounded_runtime_materializes_current_projection_contract(tmp_path):
    runtime = tmp_path / "runtime"
    expectations = tmp_path / "expectations.json"
    _write(expectations, _expectations())
    artifacts = {
        name: ([{"ticker": "NVDA", "certified_customer_evaluation": {
            "customer_publication_allowed": True, "decision": {"action": "BUY_NOW"},
        }}] if name in {"market_full_scan.json", "full_evaluation_pool.json"} else [])
        for name in PUBLICATION_FILES
    }
    for name, payload in artifacts.items():
        _write(runtime / name, payload)
    _write(runtime / "publication_manifest.json", {
        "executor_candidate_identity": {"candidate_digest": "c" * 64, "source_sha": SOURCE_SHA},
        "source_commit_sha": SOURCE_SHA,
    })
    _materialize_runtime_projection_contract(
        runtime=runtime, expectations_path=expectations,
        candidate_digest="c" * 64, publication_digest="p" * 64,
        source_sha=SOURCE_SHA, evidence_snapshot_at="2026-09-11T20:00:00Z",
    )
    contract = json.loads((runtime / "publication_manifest.json").read_text())["runtime_projection_contract"]
    assert contract["source_certification"]["candidate_digest"] == "c" * 64
    assert contract["source_certification"]["publication_digest"] == "p" * 64
    assert contract["source_certification"]["analytical_source_sha"] == SOURCE_SHA
    assert contract["runtime_projection"]["withheld_customer_leakage"] == []
    assert contract["runtime_projection"]["record_counts"]["full_evaluation_pool.json"] == 1


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def test_bounded_smoke_verifies_exact_identity_and_materializes_only_slice(tmp_path):
    bundle, reports = tmp_path / "bundle", tmp_path / "reports"
    allowed = {"publication_certification": {"customer_publication_allowed": True}}
    denied = {"publication_certification": {"customer_publication_allowed": False}}
    rows = []
    for index in range(6033):
        action = "BUY_NOW" if index < 28 else "WAIT_FOR_CONFIRMATION"
        ticker = {0: "NVDA", 1: "REGN"}.get(index, f"T{index}")
        row = {"ticker": ticker, "canonical_investment_evaluation": {"guidance": {"state": action}}}
        row.update(allowed if index < 22 else denied)
        rows.append(row)
    customer = rows[:22]
    payloads = {
        "market_full_scan.json": customer,
        "market_prescreen.json": rows,
        "recovery_scan.json": [], "etf_scan.json": [],
        "total_market_universe.json": {"count": 6033},
        "market_scan_state.json": {"report_card_prospective_active": False},
        "discovery_candidate_pool.json": rows, "full_evaluation_pool.json": rows,
    }
    hashes = {}
    for name, payload in payloads.items():
        _write(bundle / name, payload)
        hashes[name] = hashlib.sha256((bundle / name).read_bytes()).hexdigest()
    candidate = "c" * 64
    publication = _canonical_digest({"artifact_hashes": hashes, "candidate_digest": candidate})
    _write(bundle / "publication_manifest.json", {
        "artifact_hashes": hashes, "source_commit_sha": SOURCE_SHA, "run_id": "certified-run",
        "executor_candidate_identity": {"candidate_digest": candidate, "source_sha": SOURCE_SHA},
        "provider_status": {"provider_calls": 0},
    })
    _write(reports / "full_universe_gate_report.json", {
        "provider_calls_during_aggregation": 0, "same_snapshot_parity": "PASS",
        "report_card_prospective_active": False,
    })
    _write(reports / "determinism_report.json", {
        "status": "PASS", "structural_diff": {"analytical_mismatch_count": 0},
    })
    _write(reports / "evidence_inspector_coverage.json", {"status": "PASS"})
    result = run(Namespace(
        bundle=bundle, report_root=reports, runtime_dir=tmp_path / "runtime", output=tmp_path / "result.json",
        expected_candidate_digest=candidate, expected_publication_digest=publication,
        expected_source_sha=SOURCE_SHA,
    ))
    assert result["status"] == "PASS"
    assert result["canonical_buy_now_count"] == 28
    assert result["customer_publishable_buy_now_count"] == 22
    assert result["withheld_buy_now_count"] == 6
    assert result["candidate_source_sha"] == SOURCE_SHA
    runtime_manifest = json.loads((tmp_path / "runtime" / "publication_manifest.json").read_text())
    assert runtime_manifest["source_commit_sha"] == SOURCE_SHA
    assert runtime_manifest["executor_candidate_identity"]["source_sha"] == SOURCE_SHA
    runtime_identity = candidate_identity(tmp_path / "runtime", code_sha="f" * 40)
    assert runtime_identity["valid"] is True
    assert runtime_identity["candidate_source_sha"] == SOURCE_SHA
    assert runtime_identity["code_sha"] != runtime_identity["candidate_source_sha"]
    assert (tmp_path / "runtime" / "full_evaluation_pool.json").stat().st_size < (bundle / "full_evaluation_pool.json").stat().st_size
    runtime_rows = json.loads((tmp_path / "runtime" / "market_full_scan.json").read_text())
    assert len(runtime_rows) < len(rows)
    assert {row["ticker"] for row in runtime_rows} >= {"NVDA", "REGN"}
    assert json.loads((tmp_path / "runtime" / "market_prescreen.json").read_text()) == []
    assert json.loads((tmp_path / "runtime" / "discovery_candidate_pool.json").read_text()) == []
    projection = runtime_manifest["runtime_projection"]
    assert projection["mode"] == "RELEASE_SMOKE_BOUNDED_UI"
    assert projection["provider_calls"] == 0
    assert projection["analytical_recomputation"] is False


def test_bounded_smoke_fails_closed_on_candidate_identity_mismatch(tmp_path):
    bundle = tmp_path / "bundle"; reports = tmp_path / "reports"
    bundle.mkdir(); reports.mkdir()
    _write(bundle / "publication_manifest.json", {
        "source_commit_sha": SOURCE_SHA,
        "executor_candidate_identity": {"candidate_digest": "wrong", "source_sha": SOURCE_SHA},
    })
    try:
        run(Namespace(bundle=bundle, report_root=reports, runtime_dir=tmp_path / "runtime",
                      output=tmp_path / "out.json", expected_candidate_digest="expected",
                      expected_publication_digest="publication", expected_source_sha=SOURCE_SHA))
    except ValueError as error:
        assert str(error) == "CERTIFIED_CANDIDATE_DIGEST_MISMATCH"
    else:
        raise AssertionError("identity mismatch must fail closed")


def test_bounded_smoke_rejects_missing_or_mismatched_analytical_source_sha(tmp_path):
    bundle = tmp_path / "bundle"
    reports = tmp_path / "reports"
    bundle.mkdir(); reports.mkdir()
    candidate = "c" * 64
    base = {
        "executor_candidate_identity": {"candidate_digest": candidate},
    }
    for manifest, expected_error in (
        (base, "CERTIFIED_CANDIDATE_SOURCE_SHA_MISSING"),
        ({"source_commit_sha": SOURCE_SHA,
          "executor_candidate_identity": {"candidate_digest": candidate, "source_sha": "a" * 40}},
         "CERTIFIED_CANDIDATE_SOURCE_SHA_MISMATCH"),
    ):
        _write(bundle / "publication_manifest.json", manifest)
        try:
            run(Namespace(
                bundle=bundle, report_root=reports, runtime_dir=tmp_path / "runtime",
                output=tmp_path / "out.json", expected_candidate_digest=candidate,
                expected_publication_digest="publication", expected_source_sha=SOURCE_SHA,
            ))
        except ValueError as error:
            assert str(error) == expected_error
        else:
            raise AssertionError("source identity defect must fail closed")

    _write(bundle / "publication_manifest.json", {
        "source_commit_sha": SOURCE_SHA,
        "executor_candidate_identity": {"candidate_digest": candidate, "source_sha": SOURCE_SHA},
    })
    try:
        run(Namespace(
            bundle=bundle, report_root=reports, runtime_dir=tmp_path / "runtime",
            output=tmp_path / "out.json", expected_candidate_digest=candidate,
            expected_publication_digest="publication",
            expected_source_sha="abd23cb98b3e083eb2aa065fe9bf3bf1fd453d9",
        ))
    except ValueError as error:
        assert str(error) == "CERTIFIED_CANDIDATE_SOURCE_SHA_MISMATCH"
    else:
        raise AssertionError("workflow SHA must not satisfy analytical source identity")


def test_publication_file_contract_is_exact():
    assert set(PUBLICATION_FILES) == {
        "market_full_scan.json", "market_prescreen.json", "recovery_scan.json", "etf_scan.json",
        "total_market_universe.json", "market_scan_state.json", "discovery_candidate_pool.json",
        "full_evaluation_pool.json",
    }


def test_pool_engine_actions_use_governed_executor_aliases():
    def row(state):
        return {"canonical_investment_evaluation": {"guidance": {"state": state}}}

    assert _action(row("ACCUMULATE")) == "BUILD_A_POSITION"
    assert _action(row("WAIT_FOR_ENTRY")) == "WAIT_FOR_BETTER_ENTRY"
    assert _action(row("DATA_LIMITED")) == "RATING_NOT_PUBLISHED"
    assert _action(row("BUY_NOW")) == "BUY_NOW"


def _semantic_manifest(bundle: Path, payloads: dict[str, object]) -> dict:
    hashes = {}
    lineage = {}
    for name in PUBLICATION_FILES:
        _write(bundle / name, payloads[name])
        digest = _canonical_digest(payloads[name])
        hashes[name] = digest
        lineage[name] = {"semantic_sha256": digest}
    return {"artifact_hashes": hashes, "artifact_lineage": lineage}


def test_fresh_semantic_manifest_accepts_representation_only_byte_differences(tmp_path):
    bundle = tmp_path / "bundle"
    rows = [{"ticker": "NVDA", "nested": {"value": 88.54}}]
    payloads = {name: [] for name in PUBLICATION_FILES}
    payloads.update({
        "market_full_scan.json": rows,
        "market_scan_state.json": {"status": "PASS", "count": 1},
        "total_market_universe.json": {"symbols": ["NVDA"]},
    })
    manifest = _semantic_manifest(bundle, payloads)
    # Change storage whitespace only; governed canonical meaning is unchanged.
    (bundle / "market_full_scan.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )

    verified, diagnostics = _verify_publication_artifact_hashes(
        bundle, manifest, semantic_contract=True,
    )

    assert verified["market_full_scan.json"] == manifest["artifact_hashes"]["market_full_scan.json"]
    detail = diagnostics["market_full_scan.json"]
    assert detail["digest_contract"] == "CANONICAL_JSON_SEMANTIC_SHA256"
    assert detail["semantic_digest_verified"] is True
    assert detail["raw_storage_digest"] != detail["manifest_semantic_digest"]


def test_fresh_semantic_manifest_rejects_lineage_digest_divergence(tmp_path):
    bundle = tmp_path / "bundle"
    payloads = {name: [] for name in PUBLICATION_FILES}
    manifest = _semantic_manifest(bundle, payloads)
    manifest["artifact_lineage"]["market_full_scan.json"]["semantic_sha256"] = "0" * 64

    try:
        _verify_publication_artifact_hashes(bundle, manifest, semantic_contract=True)
    except ValueError as error:
        assert str(error) == (
            "PUBLICATION_MANIFEST_LINEAGE_DIGEST_MISMATCH:market_full_scan.json"
        )
    else:
        raise AssertionError("fresh semantic lineage divergence must fail closed")


def test_legacy_publication_hash_contract_remains_raw_bytes(tmp_path):
    bundle = tmp_path / "bundle"
    payloads = {name: [] for name in PUBLICATION_FILES}
    manifest = _semantic_manifest(bundle, payloads)
    (bundle / "market_full_scan.json").write_text("[ ]\n", encoding="utf-8")
    try:
        _verify_publication_artifact_hashes(bundle, manifest, semantic_contract=False)
    except ValueError as error:
        assert str(error) == "PUBLICATION_ARTIFACT_DIGEST_MISMATCH:market_full_scan.json"
    else:
        raise AssertionError("legacy raw-byte verification must remain unchanged")


def test_fresh_semantic_hash_rejects_logical_corruption(tmp_path):
    original = [{"ticker": "NVDA", "nested": {"value": 88.54}}]
    corruptions = (
        [],
        original + [{"ticker": "MSFT", "nested": {"value": 80.0}}],
        [{"ticker": "MSFT", "nested": {"value": 88.54}}],
        [{"ticker": "NVDA", "nested": {"value": 1.0}}],
    )
    for index, corrupted in enumerate(corruptions):
        bundle = tmp_path / str(index)
        payloads = {name: [] for name in PUBLICATION_FILES}
        payloads["market_full_scan.json"] = original
        manifest = _semantic_manifest(bundle, payloads)
        _write(bundle / "market_full_scan.json", corrupted)
        try:
            _verify_publication_artifact_hashes(bundle, manifest, semantic_contract=True)
        except ValueError as error:
            assert str(error) == "PUBLICATION_ARTIFACT_DIGEST_MISMATCH:market_full_scan.json"
        else:
            raise AssertionError("logical publication corruption must fail closed")


def test_semantic_array_hash_streams_large_top_level_array(tmp_path):
    path = tmp_path / "large.json"
    rows = [{"ticker": f"T{index}", "value": index} for index in range(20_000)]
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    assert _semantic_json_sha256(path) == _canonical_digest(rows)


def test_customer_publication_pool_is_streamed_to_bounded_rows(tmp_path):
    allowed = {"publication_certification": {"customer_publication_allowed": True}}
    denied = {"publication_certification": {"customer_publication_allowed": False}}
    rows = [
        {"ticker": "NVDA", "canonical_investment_evaluation": {"guidance": {"state": "BUY_NOW"}}, **allowed},
        {"ticker": "REGN", "canonical_investment_evaluation": {"guidance": {"state": "WAIT_FOR_CONFIRMATION"}}, **allowed},
        {"ticker": "WITHHELD", "canonical_investment_evaluation": {"guidance": {"state": "BUY_NOW"}}, **denied},
        {"ticker": "OTHER", "canonical_investment_evaluation": {"guidance": {"state": "WAIT_FOR_BETTER_ENTRY"}}, **allowed},
    ]
    pool = tmp_path / "market_full_scan.json"
    _write(pool, rows)

    selected, published, duplicates = _stream_customer_rows(pool)

    assert published == ["NVDA"]
    assert {row["ticker"] for row in selected} == {"NVDA", "REGN"}
    assert duplicates == []


def _fresh_inventory_inputs(
    canonical=("A", "B", "C"), publishable=("A", "B"), withheld=("C",),
):
    distribution = {"BUY_NOW": len(canonical), "WAIT_FOR_CONFIRMATION": 2}
    records = [
        {
            "ticker": ticker,
            "publication_eligible": ticker in publishable,
            "universe_sha256": "universe",
        }
        for ticker in (*publishable, *withheld)
    ]
    return {
        "action_distribution": distribution,
        "checkpoint": {
            "action_counts": distribution,
            "buy_now_tickers": list(publishable),
            "withheld_buy_now_tickers": list(withheld),
        },
        "provenance": {
            "status": "PASS",
            "canonical_buy_now_count": len(canonical),
            "publishable_buy_now_count": len(publishable),
            "records": records,
        },
        "observed_actions": distribution,
        "pool_inventory": {
            "canonical_buy_now": list(canonical),
            "publishable_buy_now": list(publishable),
            "withheld_buy_now": list(withheld),
            "duplicate_tickers": [],
        },
        "market_publishable": list(publishable),
        "market_duplicates": [],
        "universe_sha256": "universe",
    }


def _inventory_error(inputs, expected):
    try:
        _verify_fresh_inventory(**inputs)
    except ValueError as error:
        assert str(error) == expected
    else:
        raise AssertionError(f"expected {expected}")


def test_fresh_inventory_validates_dynamic_and_future_counts():
    current = _verify_fresh_inventory(**_fresh_inventory_inputs(
        canonical=tuple(f"T{i}" for i in range(21)),
        publishable=tuple(f"T{i}" for i in range(11)),
        withheld=tuple(f"T{i}" for i in range(11, 21)),
    ))
    assert (current["canonical_buy_now_count"],
            current["customer_publishable_buy_now_count"],
            current["withheld_buy_now_count"]) == (21, 11, 10)
    future = _verify_fresh_inventory(**_fresh_inventory_inputs(
        canonical=("N1", "N2", "N3", "N4"),
        publishable=("N1",), withheld=("N2", "N3", "N4"),
    ))
    assert (future["canonical_buy_now_count"],
            future["customer_publishable_buy_now_count"],
            future["withheld_buy_now_count"]) == (4, 1, 3)


def test_fresh_inventory_rejects_count_mismatches():
    canonical = _fresh_inventory_inputs()
    canonical["provenance"]["canonical_buy_now_count"] = 4
    _inventory_error(canonical, "FRESH_INVENTORY_CANONICAL_COUNT_MISMATCH")

    publishable = _fresh_inventory_inputs()
    publishable["provenance"]["publishable_buy_now_count"] = 1
    _inventory_error(publishable, "FRESH_INVENTORY_PUBLISHABLE_COUNT_MISMATCH")

    withheld = _fresh_inventory_inputs()
    withheld["provenance"]["publishable_buy_now_count"] = 3
    _inventory_error(withheld, "FRESH_INVENTORY_PUBLISHABLE_COUNT_MISMATCH")


def test_fresh_inventory_rejects_partition_and_projection_defects():
    leaked = _fresh_inventory_inputs()
    leaked["market_publishable"].append("C")
    _inventory_error(leaked, "FRESH_INVENTORY_WITHHELD_PUBLICATION_LEAK")

    noncanonical = _fresh_inventory_inputs()
    noncanonical["provenance"]["records"][0]["ticker"] = "X"
    _inventory_error(noncanonical, "FRESH_INVENTORY_UNEXPECTED_BUY_NOW_TICKER")

    missing = _fresh_inventory_inputs()
    missing["provenance"]["records"] = missing["provenance"]["records"][:-1]
    _inventory_error(missing, "FRESH_INVENTORY_CANONICAL_PARTITION_INCOMPLETE")

    duplicate = _fresh_inventory_inputs()
    duplicate["market_duplicates"] = ["A"]
    _inventory_error(duplicate, "FRESH_INVENTORY_DUPLICATE_TICKER")


def test_fresh_inventory_rejects_authorization_mismatches():
    inputs = _fresh_inventory_inputs()
    inputs["authorization"] = {"canonical_buy_now_count": 99}
    _inventory_error(inputs, "FRESH_INVENTORY_AUTHORIZATION_COUNT_MISMATCH")
    inputs = _fresh_inventory_inputs()
    inputs["authorization"] = {"publishable_buy_now": ["A", "X"]}
    _inventory_error(inputs, "FRESH_INVENTORY_AUTHORIZATION_TICKER_MISMATCH")


def test_large_gate_reads_only_required_root_scalars(tmp_path):
    gate = tmp_path / "full_universe_gate_report.json"
    _write(gate, {
        "provider_calls_during_aggregation": 0,
        "embedded_records": [{"payload": "x" * 1000} for _ in range(50)],
        "same_snapshot_parity": "PASS",
        "report_card_prospective_active": False,
    })

    assert _stream_top_level_scalars(gate, (
        "provider_calls_during_aggregation", "same_snapshot_parity", "report_card_prospective_active",
    )) == {
        "provider_calls_during_aggregation": 0,
        "same_snapshot_parity": "PASS",
        "report_card_prospective_active": False,
    }


def test_fresh_backend_handoff_requires_exact_identity_and_governance(tmp_path):
    path = tmp_path / "backend_handoff.json"
    handoff = {
        "schema": "ATLAS_RELEASE_FULL_BACKEND_HANDOFF_V1", "status": "PASS",
        "candidate_digest": "candidate", "publication_digest": "publication",
        "source_sha": SOURCE_SHA, "evidence_snapshot_at": "2026-10-04T00:00:00Z",
        "universe_sha256": "universe", "provider_calls": 0, "reacquisition": "none",
        "dataset_gate": "PASS", "dataset_certification_status": "PASS",
        "publication_gate_status": "PASS",
    }
    _write(path, handoff)
    assert _verify_fresh_backend_handoff(
        path, candidate_digest="candidate", publication_digest="publication",
        source_sha=SOURCE_SHA, evidence_snapshot_at="2026-10-04T00:00:00Z",
        universe_sha256="universe",
    ) == handoff

    for key, bad in (
        ("candidate_digest", "wrong"), ("publication_digest", "wrong"),
        ("source_sha", "wrong"), ("evidence_snapshot_at", "wrong"),
        ("universe_sha256", "wrong"), ("provider_calls", 1),
        ("reacquisition", "performed"), ("dataset_gate", "FAIL"),
        ("publication_gate_status", "FAIL"),
    ):
        broken = {**handoff, key: bad}
        _write(path, broken)
        try:
            _verify_fresh_backend_handoff(
                path, candidate_digest="candidate", publication_digest="publication",
                source_sha=SOURCE_SHA, evidence_snapshot_at="2026-10-04T00:00:00Z",
                universe_sha256="universe",
            )
        except ValueError as error:
            assert key in str(error)
        else:
            raise AssertionError(f"{key} mismatch must fail closed")


def test_fresh_artifact_contract_requires_completeness_determinism_and_identity():
    manifest = {
        "publication_gate_status": "PASS", "executor_candidate_digest_verified": True,
        "customer_publication_count": 11, "report_card_prospective_active": False,
        "generated_at": "2026-10-04T00:00:00Z",
    }
    checkpoint = {
        "state": "FULL_UNIVERSE_CERTIFIED", "terminal_record_count": 6033,
        "expected_supported_symbol_count": 6033, "missing_symbols": [],
        "duplicate_symbols": [], "unexpected_symbols": [], "customer_publishable": True,
    }
    determinism = {
        "status": "PASS", "first_digest": "candidate", "second_digest": "candidate",
        "structural_diff": {"analytical_mismatch_count": 0},
    }
    _verify_fresh_artifact_contract(
        manifest=manifest, checkpoint=checkpoint, determinism=determinism,
        candidate_digest="candidate", evidence_snapshot_at="2026-10-04T00:00:00Z",
        universe_sha256="universe",
    )
    broken = {**determinism, "status": "FAIL"}
    try:
        _verify_fresh_artifact_contract(
            manifest=manifest, checkpoint=checkpoint, determinism=broken,
            candidate_digest="candidate", evidence_snapshot_at="2026-10-04T00:00:00Z",
            universe_sha256="universe",
        )
    except ValueError as error:
        assert "determinism" in str(error)
    else:
        raise AssertionError("determinism failure must fail closed")


def test_browser_startup_is_explicit_and_fails_with_streamlit_diagnostics():
    workflow = Path(".github/workflows/atlas_release_smoke_bounded.yml").read_text()
    assert "python -m playwright install chromium" in workflow
    assert "--server.address 127.0.0.1" in workflow
    assert 'kill -0 "$app_pid"' in workflow
    assert "Streamlit exited before readiness" in workflow
    assert 'cat "$log"' in workflow
    assert "app_memory.txt" in workflow
    assert "browser_memory.txt" in workflow
