"""Zero-provider binding of acquisition evidence to certified closure authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


CLASSIFICATION = "FINNHUB_FULL_UNIVERSE_CERTIFICATION_CLOSED_GREEN"
SCHEMA = "ATLAS_REPORT_CARD_CAPTURE_HANDOFF_V1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_capture_handoff(*, manifest_path: Path, publication_path: Path, closure_path: Path,
                          expected_acquisition_run_id: str, expected_closure_run_id: str,
                          expected_run_identity: str, expected_source_sha: str,
                          expected_candidate_digest: str, expected_publication_digest: str) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = json.loads(publication_path.read_text(encoding="utf-8"))
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    identity = dict(manifest.get("executor_candidate_identity") or {})
    checks = dict(closure.get("checks") or {})
    checkpoint = dict(closure.get("checkpoint_validation") or {})
    required_checks = {
        "candidate_digest", "publication_digest", "determinism", "analytical_mismatches",
        "manifests", "payloads", "symbols", "repository_integrity", "publication_gate",
    }
    if manifest.get("publication_gate_status") != "PASS" or manifest.get("artifact_lineage_status") != "COHERENT":
        raise ValueError("SOURCE_PUBLICATION_NOT_CERTIFIED")
    if not isinstance(rows, list) or not rows:
        raise ValueError("SOURCE_PUBLICATION_ROWS_MISSING")
    expected = {
        "evidence_source_run_id": str(expected_acquisition_run_id),
        "evidence_source_run_identity": expected_run_identity,
        "evidence_source_sha": expected_source_sha,
        "candidate_digest": expected_candidate_digest,
        "publication_digest": expected_publication_digest,
    }
    for field, value in expected.items():
        if str(closure.get(field) or "") != str(value):
            raise ValueError(f"CLOSURE_IDENTITY_MISMATCH:{field}")
    if str(identity.get("candidate_digest") or "") != expected_candidate_digest:
        raise ValueError("SOURCE_CANDIDATE_DIGEST_MISMATCH")
    if str(identity.get("source_sha") or "") != expected_source_sha:
        raise ValueError("SOURCE_SHA_MISMATCH")
    if closure.get("classification") != CLASSIFICATION or closure.get("workflow_conclusion") != "GREEN":
        raise ValueError("CLOSURE_NOT_GREEN")
    if closure.get("determinism") != "PASS" or int(closure.get("analytical_mismatches", -1)) != 0:
        raise ValueError("CLOSURE_DETERMINISM_OR_ANALYTICS_FAILED")
    if int(closure.get("closure_provider_calls", -1)) != 0:
        raise ValueError("CLOSURE_PROVIDER_CALLS_NONZERO")
    if checkpoint.get("status") != "PASS" or checkpoint.get("manifests") != 41 or checkpoint.get("payloads") != 41:
        raise ValueError("CLOSURE_CHECKPOINT_INCOMPLETE")
    completeness = dict(closure.get("symbol_completeness") or {})
    if completeness != {"actual": 6033, "expected": 6033, "status": "PASS"}:
        raise ValueError("CLOSURE_SYMBOL_COMPLETENESS_FAILED")
    if not required_checks.issubset({key for key, value in checks.items() if value is True}):
        raise ValueError("CLOSURE_REQUIRED_CHECKS_MISSING")
    artifact_hashes = manifest.get("artifact_hashes")
    if not isinstance(artifact_hashes, Mapping) or not artifact_hashes:
        raise ValueError("SOURCE_GOVERNED_ARTIFACT_HASHES_MISSING")
    for row in rows:
        if row.get("candidate_digest") != expected_candidate_digest or row.get("source_sha") != expected_source_sha:
            raise ValueError("PUBLICATION_ROW_IDENTITY_MISMATCH")
    return {
        "schema": SCHEMA, "status": "PASS", "classification": CLASSIFICATION,
        "acquisition_run_id": str(expected_acquisition_run_id), "closure_run_id": str(expected_closure_run_id),
        "historical_run_identity": expected_run_identity, "source_sha": expected_source_sha,
        "candidate_digest": expected_candidate_digest, "publication_digest": expected_publication_digest,
        "manifest_sha256": _sha256(manifest_path), "publication_rows_sha256": _sha256(publication_path),
        "closure_report_sha256": _sha256(closure_path), "governed_artifact_hashes": dict(artifact_hashes),
        "certified_manifests": 41, "certified_payloads": 41, "certified_symbols": 6033,
        "determinism": "PASS", "analytical_mismatches": 0, "provider_calls": 0,
        "row_count": len(rows), "customer_production_promotion": False,
    }


def validate_capture_handoff(envelope: Mapping[str, Any], *, manifest_path: Path,
                             publication_path: Path, closure_path: Path) -> dict[str, str]:
    if envelope.get("schema") != SCHEMA or envelope.get("status") != "PASS":
        raise ValueError("CAPTURE_HANDOFF_INVALID")
    hashes = {
        "manifest_sha256": _sha256(manifest_path), "publication_rows_sha256": _sha256(publication_path),
        "closure_report_sha256": _sha256(closure_path),
    }
    for field, actual in hashes.items():
        if envelope.get(field) != actual:
            raise ValueError(f"CAPTURE_HANDOFF_HASH_MISMATCH:{field}")
    if envelope.get("classification") != CLASSIFICATION or envelope.get("determinism") != "PASS":
        raise ValueError("CAPTURE_HANDOFF_AUTHORITY_INVALID")
    if (envelope.get("certified_manifests"), envelope.get("certified_payloads"), envelope.get("certified_symbols")) != (41, 41, 6033):
        raise ValueError("CAPTURE_HANDOFF_COMPLETENESS_INVALID")
    if envelope.get("analytical_mismatches") != 0 or envelope.get("provider_calls") != 0:
        raise ValueError("CAPTURE_HANDOFF_GOVERNANCE_INVALID")
    return {key: str(envelope[key]) for key in ("candidate_digest", "publication_digest", "source_sha")}
