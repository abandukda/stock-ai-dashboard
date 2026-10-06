#!/usr/bin/env python3
"""Fail-closed validation and materialization of a certified full-universe artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def _read(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"FULL_UNIVERSE_EVIDENCE_MISSING:{path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"FULL_UNIVERSE_EVIDENCE_INVALID:{path.name}")
    return value


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def validate(root: Path, *, run_id: str, candidate: str, publication: str,
             source_sha: str, require_authorization: bool) -> dict:
    manifests = list(root.rglob("publication_bundle/publication_manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError(f"FULL_UNIVERSE_PUBLICATION_BUNDLE_COUNT:{len(manifests)}")
    report_root = manifests[0].parent.parent
    bundle = manifests[0].parent
    manifest = _read(manifests[0])
    checkpoint = _read(report_root / "checkpoint_summary.json")
    determinism = _read(report_root / "determinism_report.json")
    inspector = _read(report_root / "evidence_inspector_coverage.json")

    identity = dict(manifest.get("executor_candidate_identity") or {})
    actual_candidate = str(identity.get("candidate_digest") or "")
    actual_source = str(identity.get("source_sha") or "")
    actual_publication = _digest({
        "artifact_hashes": manifest.get("artifact_hashes") or {},
        "candidate_digest": actual_candidate,
    })
    if require_authorization and not all((candidate, publication, source_sha)):
        raise RuntimeError("FULL_UNIVERSE_PROMOTION_AUTHORIZATION_INCOMPLETE")
    if candidate and actual_candidate != candidate:
        raise RuntimeError("FULL_UNIVERSE_CANDIDATE_DIGEST_MISMATCH")
    if publication and actual_publication != publication:
        raise RuntimeError("FULL_UNIVERSE_PUBLICATION_DIGEST_MISMATCH")
    if source_sha and actual_source != source_sha:
        raise RuntimeError("FULL_UNIVERSE_SOURCE_SHA_MISMATCH")
    if str(manifest.get("workflow_run_id") or "") != run_id:
        raise RuntimeError("FULL_UNIVERSE_RUN_ID_MISMATCH")
    if manifest.get("source_commit_sha") != actual_source:
        raise RuntimeError("FULL_UNIVERSE_MANIFEST_SOURCE_SHA_MISMATCH")
    if manifest.get("publication_gate_status") != "PASS":
        raise RuntimeError("FULL_UNIVERSE_PUBLICATION_GATE_FAILED")
    if manifest.get("executor_candidate_digest_verified") is not True:
        raise RuntimeError("FULL_UNIVERSE_CANDIDATE_NOT_VERIFIED")
    if manifest.get("report_card_prospective_active") is not False:
        raise RuntimeError("FULL_UNIVERSE_REPORT_CARD_NOT_OFF")
    if checkpoint.get("state") != "FULL_UNIVERSE_CERTIFIED" or checkpoint.get("customer_publishable") is not True:
        raise RuntimeError("FULL_UNIVERSE_FINAL_CERTIFICATION_FAILED")
    if checkpoint.get("terminal_record_count") != checkpoint.get("expected_supported_symbol_count"):
        raise RuntimeError("FULL_UNIVERSE_ACCOUNTING_MISMATCH")
    if checkpoint.get("missing_symbols") or checkpoint.get("duplicate_symbols") or checkpoint.get("unexpected_symbols"):
        raise RuntimeError("FULL_UNIVERSE_SYMBOL_INTEGRITY_FAILED")
    if determinism.get("status") != "PASS":
        raise RuntimeError("FULL_UNIVERSE_DETERMINISM_FAILED")
    if determinism.get("first_digest") != actual_candidate or determinism.get("second_digest") != actual_candidate:
        raise RuntimeError("FULL_UNIVERSE_DETERMINISM_DIGEST_MISMATCH")
    if (determinism.get("structural_diff") or {}).get("analytical_mismatch_count") != 0:
        raise RuntimeError("FULL_UNIVERSE_ANALYTICAL_MISMATCH")
    if inspector.get("status") != "PASS" or inspector.get("failures"):
        raise RuntimeError("FULL_UNIVERSE_EVIDENCE_INSPECTOR_FAILED")
    if manifest.get("customer_publication_count", 0) < 1:
        raise RuntimeError("FULL_UNIVERSE_CUSTOMER_PUBLICATION_EMPTY")

    return {
        "status": "PASS", "source_run_id": run_id, "report_root": str(report_root),
        "bundle": str(bundle), "candidate_digest": actual_candidate,
        "publication_digest": actual_publication, "source_sha": actual_source,
        "evidence_snapshot_at": manifest.get("generated_at"),
        "universe_sha256": identity.get("universe_sha256"),
        "universe_count": checkpoint.get("terminal_record_count"),
        "publication_gate": manifest.get("publication_gate_status"),
        "determinism": determinism.get("status"), "evidence_inspector": inspector.get("status"),
        "report_card_prospective_active": manifest.get("report_card_prospective_active"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-candidate-digest", default="")
    parser.add_argument("--expected-publication-digest", default="")
    parser.add_argument("--expected-source-sha", default="")
    parser.add_argument("--require-authorization", default="CERTIFY_ONLY")
    parser.add_argument("--materialize", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate(
        args.root, run_id=args.expected_run_id,
        candidate=args.expected_candidate_digest, publication=args.expected_publication_digest,
        source_sha=args.expected_source_sha,
        require_authorization=args.require_authorization == "CERTIFY_AND_PROMOTE",
    )
    if args.materialize:
        if args.materialize.exists():
            raise RuntimeError("FULL_UNIVERSE_MATERIALIZATION_TARGET_EXISTS")
        shutil.move(result["bundle"], args.materialize)
        result["materialized_bundle"] = str(args.materialize)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
