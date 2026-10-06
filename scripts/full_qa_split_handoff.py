#!/usr/bin/env python3
"""Fail-closed contracts for split RELEASE_FULL certification jobs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


IDENTITY_FIELDS = ("candidate_digest", "publication_digest", "source_sha", "release_sha")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"HANDOFF_OBJECT_REQUIRED:{path}")
    return value


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(payload: dict) -> dict[str, str]:
    identity = {field: str(payload.get(field) or "") for field in IDENTITY_FIELDS}
    missing = [field for field, value in identity.items() if not value]
    if missing:
        raise RuntimeError("HANDOFF_IDENTITY_MISSING:" + ",".join(missing))
    return identity


def build_backend(args: argparse.Namespace) -> dict:
    verification = _read(args.verification)
    if verification.get("status") != "PASS":
        raise RuntimeError("BACKEND_IDENTITY_GATE_FAILED")
    reports = sorted(args.qa_dir.glob("ATLAS_MASTER_QA_*.json"))
    if len(reports) != 1:
        raise RuntimeError(f"BACKEND_QA_REPORT_COUNT:{len(reports)}")
    report = _read(reports[0])
    summary = dict(report.get("summary") or {})
    if report.get("gate") != "PASS":
        raise RuntimeError("BACKEND_DATASET_GATE_FAILED")
    if summary.get("dataset_certification_status") != "PASS":
        raise RuntimeError("BACKEND_DATASET_CERTIFICATION_FAILED")
    if summary.get("publication_gate_status") != "PASS":
        raise RuntimeError("BACKEND_PUBLICATION_GATE_FAILED")
    payload = {
        "schema": "ATLAS_RELEASE_FULL_BACKEND_HANDOFF_V1",
        "status": "PASS",
        "candidate_run_id": str(args.candidate_run_id),
        "candidate_digest": verification.get("candidate_digest"),
        "publication_digest": verification.get("publication_digest"),
        "source_sha": verification.get("source_sha"),
        "evidence_snapshot_at": verification.get("evidence_snapshot_at"),
        "universe_sha256": verification.get("universe_sha256"),
        "release_sha": args.release_sha,
        "provider_calls": 0,
        "reacquisition": "none",
        "dataset_gate": report.get("gate"),
        "dataset_certification_status": summary.get("dataset_certification_status"),
        "publication_gate_status": summary.get("publication_gate_status"),
        "qa_report": reports[0].name,
        "qa_report_sha256": _digest(reports[0]),
    }
    _identity(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_visual(args: argparse.Namespace) -> dict:
    backend = _read(args.backend)
    verification = _read(args.verification)
    summary = _read(args.visual_summary)
    manifest_value = json.loads(args.screenshot_manifest.read_text(encoding="utf-8"))
    manifest = manifest_value.get("screenshots", []) if isinstance(manifest_value, dict) else manifest_value
    if backend.get("status") != "PASS" or verification.get("status") != "PASS":
        raise RuntimeError("VISUAL_UPSTREAM_GATE_FAILED")
    if summary.get("status") != "PASS":
        raise RuntimeError("VISUAL_CERTIFICATION_FAILED")
    completion = dict(summary.get("completion_contract") or {})
    if not completion.get("passed"):
        raise RuntimeError("VISUAL_COMPLETION_CONTRACT_FAILED")
    if not isinstance(manifest, list) or not manifest:
        raise RuntimeError("VISUAL_SCREENSHOT_MANIFEST_EMPTY")
    viewports = {str(row.get("viewport")) for row in manifest if isinstance(row, dict)}
    if not {"desktop", "mobile"}.issubset(viewports):
        raise RuntimeError("VISUAL_VIEWPORT_COVERAGE_INCOMPLETE")
    candidate_identity = dict(summary.get("candidate_identity") or {})
    if candidate_identity.get("valid") is not True:
        raise RuntimeError("VISUAL_CANDIDATE_BINDING_INVALID")
    visual_identity = {
        "candidate_digest": verification.get("candidate_digest"),
        "publication_digest": verification.get("publication_bundle_digest"),
        "source_sha": verification.get("candidate_source_sha"),
        "release_sha": backend.get("release_sha"),
    }
    if _identity(backend) != _identity(visual_identity):
        raise RuntimeError("VISUAL_BACKEND_IDENTITY_MISMATCH")
    payload = {
        "schema": "ATLAS_RELEASE_FULL_VISUAL_HANDOFF_V1",
        "status": "PASS",
        **visual_identity,
        "candidate_run_id": backend.get("candidate_run_id"),
        "provider_calls": verification.get("provider_calls"),
        "reacquisition": verification.get("reacquisition"),
        "same_snapshot_parity": verification.get("same_snapshot_parity"),
        "screenshot_count": len(manifest),
        "visual_summary_sha256": _digest(args.visual_summary),
        "screenshot_manifest_sha256": _digest(args.screenshot_manifest),
    }
    if payload["provider_calls"] != 0 or payload["reacquisition"] != "none":
        raise RuntimeError("VISUAL_PROVIDER_BOUNDARY_FAILED")
    # Legacy bundles carry an already-certified scalar. Fresh full-universe
    # bundles intentionally leave it null: browser QA must produce the proof.
    if payload["same_snapshot_parity"] is None:
        parity = dict(summary.get("same_snapshot_parity") or {})
        expected = {
            "candidate_digest": visual_identity["candidate_digest"],
            "publication_digest": visual_identity["publication_digest"],
            "source_sha": visual_identity["source_sha"],
            "candidate_run_id": str(backend.get("candidate_run_id")),
        }
        observed = {**{key: parity.get(key) for key in expected},
                    "candidate_run_id": str(parity.get("candidate_run_id") or "")}
        if parity.get("status") != "PASS":
            raise RuntimeError("VISUAL_SNAPSHOT_PARITY_FAILED")
        if observed != expected:
            raise RuntimeError("VISUAL_SNAPSHOT_PARITY_IDENTITY_MISMATCH")
        required = ("action_parity", "fair_value_parity", "opportunity_parity",
                    "confidence_parity", "evaluation_snapshot_identity_parity")
        if any(parity.get(field) != "PASS" for field in required):
            raise RuntimeError("VISUAL_SNAPSHOT_PARITY_FIELD_FAILED")
        if parity.get("withheld_publication_leakage") != 0:
            raise RuntimeError("VISUAL_WITHHELD_PUBLICATION_LEAKAGE")
        payload["same_snapshot_parity"] = parity
    elif payload["same_snapshot_parity"] != "PASS":
        raise RuntimeError("VISUAL_SNAPSHOT_PARITY_FAILED")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def finalize(args: argparse.Namespace) -> dict:
    backend = _read(args.backend)
    visual = _read(args.visual)
    if backend.get("status") != "PASS" or visual.get("status") != "PASS":
        raise RuntimeError("RELEASE_FULL_CONSTITUENT_GATE_FAILED")
    if _identity(backend) != _identity(visual):
        raise RuntimeError("RELEASE_FULL_FINAL_IDENTITY_MISMATCH")
    if str(backend.get("candidate_run_id")) != str(visual.get("candidate_run_id")):
        raise RuntimeError("RELEASE_FULL_FINAL_RUN_ID_MISMATCH")
    payload = {
        "schema": "ATLAS_RELEASE_FULL_COMBINED_CERTIFICATION_V1",
        "status": "PASS",
        "release_state": "RELEASE_FULL_PASS_READY_FOR_CONTROLLED_PROMOTION",
        **_identity(backend),
        "candidate_run_id": backend.get("candidate_run_id"),
        "backend_status": backend.get("status"),
        "visual_status": visual.get("status"),
        "provider_calls": 0,
        "reacquisition": "none",
        "report_card_prospective_active": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    backend = sub.add_parser("backend")
    backend.add_argument("--verification", type=Path, required=True)
    backend.add_argument("--qa-dir", type=Path, required=True)
    backend.add_argument("--candidate-run-id", required=True)
    backend.add_argument("--release-sha", required=True)
    backend.add_argument("--output", type=Path, required=True)
    visual = sub.add_parser("visual")
    visual.add_argument("--backend", type=Path, required=True)
    visual.add_argument("--verification", type=Path, required=True)
    visual.add_argument("--visual-summary", type=Path, required=True)
    visual.add_argument("--screenshot-manifest", type=Path, required=True)
    visual.add_argument("--output", type=Path, required=True)
    final = sub.add_parser("finalize")
    final.add_argument("--backend", type=Path, required=True)
    final.add_argument("--visual", type=Path, required=True)
    final.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = {"backend": build_backend, "visual": build_visual, "finalize": finalize}[args.command](args)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
