import json
from argparse import Namespace
from pathlib import Path

import pytest
from scripts.full_qa_split_handoff import build_backend, build_visual, finalize


IDENTITY = {
    "candidate_digest": "candidate",
    "publication_digest": "publication",
    "source_sha": "source",
    "release_sha": "release",
}


def _write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_workflow_splits_backend_visual_and_finalization():
    path = Path(".github/workflows/atlas_full_qa_certification.yml")
    source = path.read_text()
    assert "  backend-certification:\n" in source
    assert "  visual-certification:\n    needs: backend-certification\n    runs-on: [self-hosted, Linux, X64]" in source
    assert "  finalization:\n    needs: [backend-certification, visual-certification]\n    runs-on: ubuntu-latest" in source
    assert source.index("Build governed backend certification handoff") < source.index("visual-certification:")
    assert "--mode RELEASE_FULL" in source
    assert "atlas-worker-1" in source
    assert "if: always()" in source and "Clean up Streamlit and Chromium" in source


def test_backend_fail_prevents_handoff(tmp_path):
    verification = _write(tmp_path / "verification.json", {"status": "PASS", **IDENTITY})
    qa = tmp_path / "qa"
    _write(qa / "ATLAS_MASTER_QA_x.json", {
        "gate": "FAIL", "summary": {"dataset_certification_status": "FAIL"}
    })
    with pytest.raises(RuntimeError, match="BACKEND_DATASET_GATE_FAILED"):
        build_backend(Namespace(verification=verification, qa_dir=qa, candidate_run_id="1",
                                release_sha="release", output=tmp_path / "backend.json"))


def test_visual_mismatch_and_missing_manifest_fail_closed(tmp_path):
    backend = _write(tmp_path / "backend.json", {"status": "PASS", "candidate_run_id": "1", **IDENTITY})
    verification = _write(tmp_path / "verification.json", {
        "status": "PASS", "candidate_digest": "wrong", "publication_bundle_digest": "publication",
        "candidate_source_sha": "source", "provider_calls": 0, "reacquisition": "none",
        "same_snapshot_parity": "PASS",
    })
    summary = _write(tmp_path / "summary.json", {
        "status": "PASS", "completion_contract": {"passed": True}, "candidate_identity": {"valid": True}
    })
    manifest = _write(tmp_path / "manifest.json", [])
    with pytest.raises(RuntimeError, match="VISUAL_SCREENSHOT_MANIFEST_EMPTY"):
        build_visual(Namespace(backend=backend, verification=verification, visual_summary=summary,
                               screenshot_manifest=manifest, output=tmp_path / "visual.json"))


def test_fresh_visual_consumes_evidence_backed_parity_object(tmp_path):
    backend = _write(tmp_path / "backend.json", {"status": "PASS", "candidate_run_id": "1", **IDENTITY})
    verification = _write(tmp_path / "verification.json", {
        "status": "PASS", "candidate_digest": "candidate", "publication_bundle_digest": "publication",
        "candidate_source_sha": "source", "provider_calls": 0, "reacquisition": "none",
        "same_snapshot_parity": None,
    })
    parity = {
        "status": "PASS", "candidate_digest": "candidate", "publication_digest": "publication",
        "source_sha": "source", "candidate_run_id": "1", "tickers_checked": ["NVDA", "MSFT", "AVT"],
        "action_parity": "PASS", "fair_value_parity": "PASS", "opportunity_parity": "PASS",
        "confidence_parity": "PASS", "evaluation_snapshot_identity_parity": "PASS",
        "withheld_publication_leakage": 0,
    }
    summary = _write(tmp_path / "summary.json", {
        "status": "PASS", "completion_contract": {"passed": True},
        "candidate_identity": {"valid": True}, "same_snapshot_parity": parity,
    })
    manifest = _write(tmp_path / "manifest.json", [
        {"viewport": "desktop"}, {"viewport": "mobile"},
    ])
    result = build_visual(Namespace(backend=backend, verification=verification, visual_summary=summary,
                                    screenshot_manifest=manifest, output=tmp_path / "visual.json"))
    assert result["same_snapshot_parity"] == parity


@pytest.mark.parametrize("mutation,error", [
    (lambda p: p.update(status="FAIL"), "VISUAL_SNAPSHOT_PARITY_FAILED"),
    (lambda p: p.update(candidate_digest="wrong"), "VISUAL_SNAPSHOT_PARITY_IDENTITY_MISMATCH"),
    (lambda p: p.update(action_parity="FAIL"), "VISUAL_SNAPSHOT_PARITY_FIELD_FAILED"),
    (lambda p: p.update(withheld_publication_leakage=1), "VISUAL_WITHHELD_PUBLICATION_LEAKAGE"),
])
def test_fresh_visual_parity_fails_closed(tmp_path, mutation, error):
    backend = _write(tmp_path / "backend.json", {"status": "PASS", "candidate_run_id": "1", **IDENTITY})
    verification = _write(tmp_path / "verification.json", {
        "status": "PASS", "candidate_digest": "candidate", "publication_bundle_digest": "publication",
        "candidate_source_sha": "source", "provider_calls": 0, "reacquisition": "none",
        "same_snapshot_parity": None,
    })
    parity = {"status": "PASS", "candidate_digest": "candidate", "publication_digest": "publication",
              "source_sha": "source", "candidate_run_id": "1", "action_parity": "PASS",
              "fair_value_parity": "PASS", "opportunity_parity": "PASS", "confidence_parity": "PASS",
              "evaluation_snapshot_identity_parity": "PASS", "withheld_publication_leakage": 0}
    mutation(parity)
    summary = _write(tmp_path / "summary.json", {"status": "PASS", "completion_contract": {"passed": True},
                    "candidate_identity": {"valid": True}, "same_snapshot_parity": parity})
    manifest = _write(tmp_path / "manifest.json", [{"viewport": "desktop"}, {"viewport": "mobile"}])
    with pytest.raises(RuntimeError, match=error):
        build_visual(Namespace(backend=backend, verification=verification, visual_summary=summary,
                               screenshot_manifest=manifest, output=tmp_path / "visual.json"))


def test_finalization_requires_matching_passed_constituents(tmp_path):
    backend = _write(tmp_path / "backend.json", {"status": "PASS", "candidate_run_id": "1", **IDENTITY})
    visual = _write(tmp_path / "visual.json", {"status": "PASS", "candidate_run_id": "2", **IDENTITY})
    with pytest.raises(RuntimeError, match="RELEASE_FULL_FINAL_RUN_ID_MISMATCH"):
        finalize(Namespace(backend=backend, visual=visual, output=tmp_path / "final.json"))
    visual = _write(tmp_path / "visual.json", {"status": "PASS", "candidate_run_id": "1", **IDENTITY})
    result = finalize(Namespace(backend=backend, visual=visual, output=tmp_path / "final.json"))
    assert result["release_state"] == "RELEASE_FULL_PASS_READY_FOR_CONTROLLED_PROMOTION"
    assert result["report_card_prospective_active"] is False
