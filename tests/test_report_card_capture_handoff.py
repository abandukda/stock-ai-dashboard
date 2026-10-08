from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.report_card_capture_handoff import build_capture_handoff, validate_capture_handoff


CANDIDATE = "c" * 64
PUBLICATION = "p" * 64
SOURCE = "s" * 40
RUN_IDENTITY = "r" * 64


def _write_inputs(tmp_path: Path):
    manifest = {
        "publication_gate_status": "PASS",
        "artifact_lineage_status": "COHERENT",
        "executor_candidate_identity": {"candidate_digest": CANDIDATE, "source_sha": SOURCE},
        "artifact_hashes": {f"artifact-{index}.json": str(index) * 64 for index in range(1, 9)},
    }
    rows = [{"ticker": "NVDA", "candidate_digest": CANDIDATE, "source_sha": SOURCE}]
    required = {
        "candidate_digest", "publication_digest", "determinism", "analytical_mismatches",
        "manifests", "payloads", "symbols", "repository_integrity", "publication_gate",
    }
    closure = {
        "evidence_source_run_id": "37553164176", "evidence_source_run_identity": RUN_IDENTITY,
        "evidence_source_sha": SOURCE, "candidate_digest": CANDIDATE,
        "publication_digest": PUBLICATION,
        "classification": "FINNHUB_FULL_UNIVERSE_CERTIFICATION_CLOSED_GREEN",
        "workflow_conclusion": "GREEN", "determinism": "PASS", "analytical_mismatches": 0,
        "closure_provider_calls": 0,
        "checkpoint_validation": {"status": "PASS", "manifests": 41, "payloads": 41},
        "symbol_completeness": {"actual": 6033, "expected": 6033, "status": "PASS"},
        "checks": {key: True for key in required},
    }
    paths = tuple(tmp_path / name for name in ("manifest.json", "publication.json", "closure.json"))
    for path, value in zip(paths, (manifest, rows, closure)):
        path.write_text(json.dumps(value), encoding="utf-8")
    return paths


def _build(paths, **changes):
    arguments = {
        "manifest_path": paths[0], "publication_path": paths[1], "closure_path": paths[2],
        "expected_acquisition_run_id": "37553164176", "expected_closure_run_id": "37698025363",
        "expected_run_identity": RUN_IDENTITY, "expected_source_sha": SOURCE,
        "expected_candidate_digest": CANDIDATE, "expected_publication_digest": PUBLICATION,
    }
    arguments.update(changes)
    return build_capture_handoff(**arguments)


def test_exact_acquisition_and_closure_are_bound_without_provider_calls(tmp_path):
    paths = _write_inputs(tmp_path)
    envelope = _build(paths)
    assert envelope["provider_calls"] == 0
    assert envelope["certified_manifests"] == envelope["certified_payloads"] == 41
    assert envelope["certified_symbols"] == 6033
    assert envelope["governed_artifact_hashes"]
    assert validate_capture_handoff(
        envelope, manifest_path=paths[0], publication_path=paths[1], closure_path=paths[2]
    ) == {"candidate_digest": CANDIDATE, "publication_digest": PUBLICATION, "source_sha": SOURCE}


@pytest.mark.parametrize("argument,value,match", [
    ("expected_acquisition_run_id", "0", "evidence_source_run_id"),
    ("expected_run_identity", "x" * 64, "evidence_source_run_identity"),
    ("expected_source_sha", "x" * 40, "evidence_source_sha"),
    ("expected_candidate_digest", "x" * 64, "candidate_digest"),
    ("expected_publication_digest", "x" * 64, "publication_digest"),
])
def test_wrong_governed_identity_fails_closed(tmp_path, argument, value, match):
    with pytest.raises(ValueError, match=match):
        _build(_write_inputs(tmp_path), **{argument: value})


@pytest.mark.parametrize("mutation,match", [
    (lambda closure: closure["checkpoint_validation"].update(manifests=40), "CHECKPOINT_INCOMPLETE"),
    (lambda closure: closure["symbol_completeness"].update(actual=6032), "SYMBOL_COMPLETENESS"),
    (lambda closure: closure["checks"].update(determinism=False), "REQUIRED_CHECKS"),
])
def test_incomplete_closure_fails_closed(tmp_path, mutation, match):
    paths = _write_inputs(tmp_path)
    closure = json.loads(paths[2].read_text())
    mutation(closure)
    paths[2].write_text(json.dumps(closure))
    with pytest.raises(ValueError, match=match):
        _build(paths)


def test_missing_artifact_hashes_and_mismatched_rows_fail_closed(tmp_path):
    paths = _write_inputs(tmp_path)
    manifest = json.loads(paths[0].read_text())
    manifest["artifact_hashes"] = {}
    paths[0].write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="ARTIFACT_HASHES_MISSING"):
        _build(paths)

    paths = _write_inputs(tmp_path)
    rows = json.loads(paths[1].read_text())
    rows[0]["candidate_digest"] = "x" * 64
    paths[1].write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="ROW_IDENTITY_MISMATCH"):
        _build(paths)


def test_any_source_byte_change_invalidates_handoff(tmp_path):
    paths = _write_inputs(tmp_path)
    envelope = _build(paths)
    paths[1].write_text(paths[1].read_text() + "\n")
    with pytest.raises(ValueError, match="HASH_MISMATCH:publication_rows_sha256"):
        validate_capture_handoff(
            envelope, manifest_path=paths[0], publication_path=paths[1], closure_path=paths[2]
        )
