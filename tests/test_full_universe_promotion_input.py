import json
from pathlib import Path

import pytest

from scripts.validate_full_universe_promotion_input import _digest, validate


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(root: Path) -> tuple[str, str, str]:
    candidate, source = "c" * 64, "a" * 40
    hashes = {"market_full_scan.json": "h" * 64}
    publication = _digest({"artifact_hashes": hashes, "candidate_digest": candidate})
    _write(root / "publication_bundle/publication_manifest.json", {
        "workflow_run_id": "123", "source_commit_sha": source,
        "generated_at": "2026-10-04T12:21:38-04:00", "publication_gate_status": "PASS",
        "executor_candidate_digest_verified": True, "report_card_prospective_active": False,
        "customer_publication_count": 11, "artifact_hashes": hashes,
        "executor_candidate_identity": {"candidate_digest": candidate, "source_sha": source,
                                          "universe_sha256": "u" * 64},
    })
    _write(root / "checkpoint_summary.json", {
        "state": "FULL_UNIVERSE_CERTIFIED", "customer_publishable": True,
        "terminal_record_count": 6033, "expected_supported_symbol_count": 6033,
        "missing_symbols": [], "duplicate_symbols": [], "unexpected_symbols": [],
    })
    _write(root / "determinism_report.json", {
        "status": "PASS", "first_digest": candidate, "second_digest": candidate,
        "structural_diff": {"analytical_mismatch_count": 0},
    })
    _write(root / "evidence_inspector_coverage.json", {"status": "PASS", "failures": []})
    return candidate, publication, source


def test_certified_full_universe_input_passes_exact_authorization(tmp_path):
    candidate, publication, source = _fixture(tmp_path)
    result = validate(tmp_path, run_id="123", candidate=candidate, publication=publication,
                      source_sha=source, require_authorization=True)
    assert result["status"] == "PASS"
    assert result["universe_count"] == 6033
    assert result["report_card_prospective_active"] is False


@pytest.mark.parametrize("field", ["candidate", "publication", "source"])
def test_certified_full_universe_input_fails_closed_on_identity_mismatch(tmp_path, field):
    candidate, publication, source = _fixture(tmp_path)
    values = {"candidate": candidate, "publication": publication, "source": source}
    values[field] = "wrong"
    with pytest.raises(RuntimeError, match="MISMATCH"):
        validate(tmp_path, run_id="123", candidate=values["candidate"],
                 publication=values["publication"], source_sha=values["source"],
                 require_authorization=True)


def test_promotion_requires_all_explicit_authorization_assertions(tmp_path):
    _fixture(tmp_path)
    with pytest.raises(RuntimeError, match="AUTHORIZATION_INCOMPLETE"):
        validate(tmp_path, run_id="123", candidate="", publication="", source_sha="",
                 require_authorization=True)
