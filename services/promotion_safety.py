"""Monotonic production-promotion policy for immutable ATLAS candidates.

This module compares artifact-generation identity only.  It never computes or
changes an investment value, rank, score, valuation, or Action.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from services.evidence_lineage_governance import (
    CACHE_GENERATION_VERSION, EVIDENCE_SNAPSHOT_VERSION, PROVIDER_ARCHITECTURE_VERSION,
)

CERTIFY_ONLY = "CERTIFY_ONLY"
CERTIFY_AND_PROMOTE = "CERTIFY_AND_PROMOTE"
RELATIONSHIPS = {"NEWER", "SAME", "OLDER", "UNKNOWN"}
REQUIRED_METHODOLOGIES = {"FOUNDER_GUIDANCE_V1"}


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def artifact_identity(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    item = dict(manifest or {})
    qa = dict(item.get("qa_certification") or {})
    hashes = dict(item.get("artifact_hashes") or {})
    return {
        "run_id": item.get("run_id"),
        "workflow_run_id": item.get("workflow_run_id"),
        "generated_at": item.get("generated_at"),
        "source_sha": item.get("source_commit_sha") or item.get("source_sha"),
        "artifact_digest": hashes.get("market_full_scan.json"),
        "certification_digest": qa.get("report_digest"),
        "provider_architecture_version": item.get("provider_architecture_version"),
        "evidence_snapshot_version": item.get("evidence_snapshot_version"),
        "cache_generation_version": item.get("cache_generation_version"),
        "methodology_versions": list(item.get("methodology_versions") or ()),
        "publication_gate_status": item.get("publication_gate_status"),
        "visual_status": qa.get("visual_status"),
    }


def classify_relationship(candidate: Mapping[str, Any], production: Mapping[str, Any]) -> str:
    candidate_digest = candidate.get("artifact_digest")
    production_digest = production.get("artifact_digest")
    if candidate_digest and production_digest and candidate_digest == production_digest:
        return "SAME"
    candidate_at, production_at = _timestamp(candidate.get("generated_at")), _timestamp(production.get("generated_at"))
    if candidate_at is None or production_at is None:
        return "UNKNOWN"
    if candidate_at > production_at:
        return "NEWER"
    if candidate_at < production_at:
        return "OLDER"
    return "UNKNOWN"


def compatibility_failures(candidate: Mapping[str, Any]) -> list[str]:
    failures = []
    expected = {
        "provider_architecture_version": PROVIDER_ARCHITECTURE_VERSION,
        "evidence_snapshot_version": EVIDENCE_SNAPSHOT_VERSION,
        "cache_generation_version": CACHE_GENERATION_VERSION,
    }
    for key, value in expected.items():
        if candidate.get(key) != value:
            failures.append(f"{key.upper()}_INCOMPATIBLE")
    if not REQUIRED_METHODOLOGIES.issubset(set(candidate.get("methodology_versions") or ())):
        failures.append("METHODOLOGY_GENERATION_INCOMPATIBLE")
    if candidate.get("publication_gate_status") != "PASS":
        failures.append("CANDIDATE_PUBLICATION_NOT_CERTIFIED")
    for key in ("run_id", "generated_at", "source_sha", "artifact_digest"):
        if not candidate.get(key):
            failures.append(f"CANDIDATE_{key.upper()}_MISSING")
    return failures


def promotion_preview(
    candidate_manifest: Mapping[str, Any], production_manifest: Mapping[str, Any], *,
    qa_mode: str = CERTIFY_ONLY, allow_rollback: bool = False,
    rollback_reason: str = "", target_candidate_run_id: str = "",
    target_candidate_sha: str = "", idempotent_reason: str = "",
    chained_candidate_run_id: str = "",
) -> dict[str, Any]:
    candidate, production = artifact_identity(candidate_manifest), artifact_identity(production_manifest)
    relationship = classify_relationship(candidate, production)
    failures = compatibility_failures(candidate)
    mode = str(qa_mode or CERTIFY_ONLY).upper()
    eligible, reason, rollback = False, "CERTIFICATION_ONLY", False
    if mode not in {CERTIFY_ONLY, CERTIFY_AND_PROMOTE}:
        reason = "QA_MODE_INVALID"
    elif mode == CERTIFY_AND_PROMOTE:
        if failures:
            reason = "PROMOTION_INCOMPATIBLE:" + ",".join(failures)
        elif chained_candidate_run_id and str(candidate.get("workflow_run_id") or candidate.get("run_id")) != str(chained_candidate_run_id):
            reason = "AUTOMATED_CHAIN_CANDIDATE_MISMATCH"
        elif relationship == "NEWER":
            eligible, reason = True, "MONOTONIC_NEWER_CANDIDATE"
        elif relationship == "SAME":
            if idempotent_reason.strip():
                eligible, reason = True, "IDEMPOTENT_EXACT_ARTIFACT"
            else:
                reason = "SAME_ARTIFACT_REQUIRES_IDEMPOTENT_REASON"
        elif relationship == "OLDER":
            run_matches = str(target_candidate_run_id) in {
                str(candidate.get("run_id")), str(candidate.get("workflow_run_id")),
            }
            sha_matches = bool(target_candidate_sha) and str(target_candidate_sha) == str(candidate.get("source_sha"))
            if allow_rollback and rollback_reason.strip() and run_matches and sha_matches:
                eligible, reason, rollback = True, "EXPLICIT_GOVERNED_ROLLBACK", True
            else:
                reason = "OLDER_CANDIDATE_HARD_BLOCK"
        else:
            reason = "UNKNOWN_CANDIDATE_AGE_HARD_BLOCK"
    return {
        "version": "ATLAS_MONOTONIC_PROMOTION_V1", "qa_mode": mode,
        "candidate": candidate, "current_production": production,
        "relationship": relationship, "compatibility_failures": failures,
        "promotion_eligible": eligible, "reason": reason,
        "allow_rollback": bool(allow_rollback), "rollback": rollback,
        "rollback_reason": rollback_reason if rollback else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def promotion_history_summary(
    production_manifest: Mapping[str, Any], audit_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize immutable promotion history for operational display only."""
    current = artifact_identity(production_manifest)
    certified = [dict(row) for row in audit_rows if dict(row.get("qa_certification") or {}).get("publication_status") == "PASS"]
    latest = max(certified, key=lambda row: _timestamp(row.get("generated_at")) or datetime.min.replace(tzinfo=timezone.utc), default={})
    latest_identity = artifact_identity(latest)
    governance_rows = [row for row in audit_rows if row.get("promotion_governance")]
    last_promotion = governance_rows[-1] if governance_rows else (audit_rows[-1] if audit_rows else {})
    rollback_rows = [row for row in governance_rows if dict(row.get("promotion_governance") or {}).get("rollback")]
    raw_relationship = classify_relationship(latest_identity, current) if latest else "UNKNOWN"
    display_relationship = {
        "SAME": "CURRENT", "NEWER": "NEWER_AVAILABLE", "OLDER": "PRODUCTION_AHEAD",
    }.get(raw_relationship, "UNKNOWN")
    last_governance = dict(last_promotion.get("promotion_governance") or {})
    return {
        "current_production": current,
        "latest_certified_candidate": latest_identity,
        "relationship": display_relationship,
        "last_promotion": {
            "run_id": last_promotion.get("run_id"),
            "generated_at": last_promotion.get("generated_at"),
            "source_sha": last_promotion.get("source_commit_sha") or last_promotion.get("source_sha"),
            "mode": last_governance.get("qa_mode"),
            "reason": last_governance.get("reason"),
        },
        "last_rollback": ({
            "run_id": rollback_rows[-1].get("run_id"),
            "generated_at": rollback_rows[-1].get("generated_at"),
            "reason": dict(rollback_rows[-1].get("promotion_governance") or {}).get("rollback_reason"),
        } if rollback_rows else None),
    }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--production-manifest", type=Path, required=True)
    parser.add_argument("--qa-mode", default=CERTIFY_ONLY, choices=(CERTIFY_ONLY, CERTIFY_AND_PROMOTE))
    parser.add_argument("--allow-rollback", action="store_true")
    parser.add_argument("--rollback-reason", default="")
    parser.add_argument("--target-candidate-run-id", default="")
    parser.add_argument("--target-candidate-sha", default="")
    parser.add_argument("--idempotent-reason", default="")
    parser.add_argument("--chained-candidate-run-id", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    preview = promotion_preview(
        _read(args.candidate_manifest), _read(args.production_manifest), qa_mode=args.qa_mode,
        allow_rollback=args.allow_rollback, rollback_reason=args.rollback_reason,
        target_candidate_run_id=args.target_candidate_run_id,
        target_candidate_sha=args.target_candidate_sha, idempotent_reason=args.idempotent_reason,
        chained_candidate_run_id=args.chained_candidate_run_id,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(preview, indent=2) + "\n", encoding="utf-8")
    print("=" * 72)
    print(f"QA MODE: {preview['qa_mode']}")
    print(f"Candidate: {preview['candidate']['run_id']} | {preview['candidate']['generated_at']} | {preview['candidate']['source_sha']}")
    print(f"Current Production: {preview['current_production']['run_id']} | {preview['current_production']['generated_at']} | {preview['current_production']['source_sha']}")
    print(f"Relationship: {preview['relationship']}")
    print(f"Promotion eligibility: {'YES' if preview['promotion_eligible'] else 'NO'}")
    print(f"Reason: {preview['reason']}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
