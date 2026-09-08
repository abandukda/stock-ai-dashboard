from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validate_candidate_artifact_provenance import validate_candidate
from services.evidence_lineage_governance import PROVIDER_ARCHITECTURE_VERSION
from services.publication_governance import stage_candidate_artifacts


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def _stage(tmp_path: Path, *, rows=None, source_sha: str = SHA) -> Path:
    candidate = tmp_path / "candidate"
    scanner_sha = hashlib.sha256((ROOT / "overnight_market_scan.py").read_bytes()).hexdigest()
    rows = [] if rows is None else rows
    payloads = {
        tmp_path / "market_full_scan.json": rows,
        tmp_path / "governed_market_acquisition_diagnostics.json": {
            "schema_version": "GOVERNED_MARKET_ACQUISITION_DIAGNOSTICS_V1",
            "records": [],
        },
    }
    manifest = {
        "publication_gate_status": "PASS",
        "published_yahoo_lineage_count": 0,
        "source_commit_sha": source_sha,
        "source_ref": "refs/heads/codex/discovery-engine-v2",
        "source_branch": "codex/discovery-engine-v2",
        "scanner_file_sha256": scanner_sha,
        "provider_architecture_version": PROVIDER_ARCHITECTURE_VERSION,
        "generated_at": "2026-09-08T00:00:00Z",
        "run_id": "overnight-test",
        "workflow_run_id": "123",
    }
    stage_candidate_artifacts(payloads, manifest=manifest, candidate_dir=candidate)
    return candidate


def test_valid_candidate_binds_every_file_to_source_and_scanner(tmp_path):
    candidate = _stage(tmp_path)
    result = validate_candidate(candidate, expected_sha=SHA, root=ROOT)
    assert result["status"] == "PASS", result
    provenance = json.loads((candidate / "artifact_provenance.json").read_text())
    assert set(provenance["artifacts"]) == {
        "market_full_scan.json", "governed_market_acquisition_diagnostics.json",
        "publication_manifest.json",
    }


def test_stale_candidate_file_is_rejected(tmp_path):
    candidate = _stage(tmp_path)
    (candidate / "stale.json").write_text("{}\n", encoding="utf-8")
    result = validate_candidate(candidate, expected_sha=SHA, root=ROOT)
    assert "CANDIDATE_ARTIFACT_INVENTORY_MISMATCH" in result["errors"]


def test_missing_diagnostics_is_rejected(tmp_path):
    candidate = _stage(tmp_path)
    (candidate / "governed_market_acquisition_diagnostics.json").unlink()
    result = validate_candidate(candidate, expected_sha=SHA, root=ROOT)
    assert "GOVERNED_MARKET_DIAGNOSTICS_MISSING" in result["errors"]


def test_yahoo_lineage_cannot_hide_behind_passing_manifest(tmp_path):
    candidate = _stage(tmp_path, rows=[{"ticker": "BAD", "forward_eps_source": "YAHOO_INFO"}])
    result = validate_candidate(candidate, expected_sha=SHA, root=ROOT)
    assert "PUBLISHED_YAHOO_LINEAGE_PRESENT" in result["errors"]
    assert "YAHOO_LINEAGE_MANIFEST_FALSE_PASS" in result["errors"]


def test_source_sha_mismatch_is_rejected(tmp_path):
    candidate = _stage(tmp_path, source_sha="b" * 40)
    result = validate_candidate(candidate, expected_sha=SHA, root=ROOT)
    assert "MANIFEST_SOURCE_SHA_MISMATCH" in result["errors"]
    assert "PROVENANCE_SOURCE_SHA_MISMATCH" in result["errors"]
