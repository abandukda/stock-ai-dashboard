#!/usr/bin/env python3
"""Atomically promote an already-certified daily full-universe bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from services.publication_governance import promote_atomically
from scripts.validate_full_universe_promotion_input import validate


PROMOTED = (
    "market_full_scan.json", "market_prescreen.json", "market_scan_state.json",
    "discovery_candidate_pool.json", "full_evaluation_pool.json",
    "total_market_universe.json", "recovery_scan.json", "etf_scan.json",
)


def _read(path: Path):
    if not path.is_file():
        raise RuntimeError(f"DAILY_BUY_NOW_PROMOTION_INPUT_MISSING:{path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def promote(*, artifact_root: Path, production_root: Path, run_id: str,
            source_sha: str, finalized_session: str) -> dict:
    validated = validate(
        artifact_root, run_id=run_id, candidate="", publication="",
        source_sha=source_sha, require_authorization=False,
    )
    bundle = Path(validated["bundle"])
    manifest = _read(bundle / "publication_manifest.json")
    manifest["finalized_market_session"] = finalized_session
    manifest["published_at"] = datetime.now(timezone.utc).isoformat()
    manifest["daily_operation"] = {
        "schema_version": "ATLAS_DAILY_BUY_NOW_PUBLICATION_V1",
        "workflow_run_id": run_id,
        "source_sha": source_sha,
        "finalized_market_session": finalized_session,
    }
    payloads = {production_root / name: _read(bundle / name) for name in PROMOTED}
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (*payloads.keys(), production_root / "publication_manifest.json") if path.exists()
    }
    promote_atomically(
        payloads, manifest=manifest,
        manifest_path=production_root / "publication_manifest.json",
        audit_path=production_root / "publication_audit.jsonl",
    )
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (*payloads.keys(), production_root / "publication_manifest.json")
    }
    result = {
        **validated, "status": "PUBLISHED", "finalized_market_session": finalized_session,
        "published_at": manifest["published_at"], "prior_sha256": before,
        "published_sha256": after, "rollback_files": sorted(before),
    }
    result["result_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--finalized-session", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = promote(
        artifact_root=args.artifact_root, production_root=args.production_root,
        run_id=args.run_id, source_sha=args.source_sha,
        finalized_session=args.finalized_session,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
