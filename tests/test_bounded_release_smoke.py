import hashlib
import json
from argparse import Namespace
from pathlib import Path

from scripts.run_bounded_release_smoke import PUBLICATION_FILES, _canonical_digest, run


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
        row = {"ticker": f"T{index}", "canonical_investment_evaluation": {"guidance": {"state": action}}}
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
        "artifact_hashes": hashes, "executor_candidate_identity": {"candidate_digest": candidate},
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
    ))
    assert result["status"] == "PASS"
    assert result["canonical_buy_now_count"] == 28
    assert result["customer_publishable_buy_now_count"] == 22
    assert result["withheld_buy_now_count"] == 6
    assert (tmp_path / "runtime" / "full_evaluation_pool.json").stat().st_size < (bundle / "full_evaluation_pool.json").stat().st_size


def test_bounded_smoke_fails_closed_on_candidate_identity_mismatch(tmp_path):
    bundle = tmp_path / "bundle"; reports = tmp_path / "reports"
    bundle.mkdir(); reports.mkdir()
    _write(bundle / "publication_manifest.json", {"executor_candidate_identity": {"candidate_digest": "wrong"}})
    try:
        run(Namespace(bundle=bundle, report_root=reports, runtime_dir=tmp_path / "runtime",
                      output=tmp_path / "out.json", expected_candidate_digest="expected",
                      expected_publication_digest="publication"))
    except ValueError as error:
        assert str(error) == "CERTIFIED_CANDIDATE_DIGEST_MISMATCH"
    else:
        raise AssertionError("identity mismatch must fail closed")


def test_publication_file_contract_is_exact():
    assert set(PUBLICATION_FILES) == {
        "market_full_scan.json", "market_prescreen.json", "recovery_scan.json", "etf_scan.json",
        "total_market_universe.json", "market_scan_state.json", "discovery_candidate_pool.json",
        "full_evaluation_pool.json",
    }


def test_browser_startup_is_explicit_and_fails_with_streamlit_diagnostics():
    workflow = Path(".github/workflows/atlas_release_smoke_bounded.yml").read_text()
    assert "python -m playwright install --with-deps chromium" in workflow
    assert "--server.address 127.0.0.1" in workflow
    assert 'kill -0 "$app_pid"' in workflow
    assert "Streamlit exited before readiness" in workflow
    assert 'cat "$log"' in workflow
    assert "app_memory.txt" in workflow
    assert "browser_memory.txt" in workflow
