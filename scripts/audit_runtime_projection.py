#!/usr/bin/env python3
"""Read-only audit of every repository artifact that can feed Home or Research."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.runtime_projection_contract import semantic_digest, validate_runtime_projection


PRODUCTION_INPUTS = (
    "market_full_scan.json", "full_evaluation_pool.json", "market_prescreen.json",
    "recovery_scan.json", "etf_scan.json", "discovery_candidate_pool.json",
    "total_market_universe.json", "market_scan_state.json",
)


def audit(root: Path) -> dict:
    manifest = json.loads((root / "publication_manifest.json").read_text(encoding="utf-8"))
    contract = dict(manifest.get("runtime_projection_contract") or {})
    source = dict(contract.get("source_certification") or {})
    results = []
    failures = []
    for name in PRODUCTION_INPUTS:
        path = root / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if name in {"full_evaluation_pool.json", "market_full_scan.json"}:
                valid, reasons = validate_runtime_projection(payload, manifest, artifact_name=name)
            else:
                expected = dict(dict(contract.get("runtime_projection") or {}).get("files") or {}).get(name) or {}
                count = len(payload) if isinstance(payload, list) else 1
                reasons = tuple(reason for condition, reason in (
                    (semantic_digest(payload) != expected.get("semantic_sha256"), "RUNTIME_PROJECTION_DIGEST_MISMATCH"),
                    (count != expected.get("record_count"), "RUNTIME_PROJECTION_COUNT_MISMATCH"),
                ) if condition)
                valid = not reasons
        except (OSError, ValueError, TypeError) as exc:
            valid, reasons = False, (f"UNREADABLE:{type(exc).__name__}",)
        results.append({"path": name, "status": "PASS" if valid else "FAIL", "failure_reasons": list(reasons)})
        failures.extend(f"{name}:{reason}" for reason in reasons)
    return {
        "version": "ATLAS_RUNTIME_PROJECTION_AUDIT_V1",
        "status": "PASS" if not failures else "FAIL",
        "candidate_digest": source.get("candidate_digest"),
        "publication_digest": source.get("publication_digest"),
        "source_sha": source.get("analytical_source_sha"),
        "evidence_snapshot_at": source.get("evidence_snapshot_at"),
        "files": results, "stale_or_mixed_authority_failures": failures,
        "provider_calls": 0, "reacquisition": "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
