import hashlib
import json
from argparse import Namespace
from pathlib import Path

from agents.visual_qa_certification_v2 import candidate_identity
from scripts.run_bounded_release_smoke import (
    PUBLICATION_FILES,
    _canonical_digest,
    _stream_customer_rows,
    _stream_top_level_scalars,
    run,
)


SOURCE_SHA = "d5526664b1b4450e67b63a67b01d936f6da5a2a4"


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

    selected, published = _stream_customer_rows(pool)

    assert published == ["NVDA"]
    assert {row["ticker"] for row in selected} == {"NVDA", "REGN"}


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


def test_browser_startup_is_explicit_and_fails_with_streamlit_diagnostics():
    workflow = Path(".github/workflows/atlas_release_smoke_bounded.yml").read_text()
    assert "python -m playwright install chromium" in workflow
    assert "--server.address 127.0.0.1" in workflow
    assert 'kill -0 "$app_pid"' in workflow
    assert "Streamlit exited before readiness" in workflow
    assert 'cat "$log"' in workflow
    assert "app_memory.txt" in workflow
    assert "browser_memory.txt" in workflow
