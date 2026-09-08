#!/usr/bin/env python3
"""Fail closed when an Overnight candidate is stale, misbound, or disallowed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.audit_production_yahoo_dependencies import audit
from services.evidence_lineage_governance import disallowed_lineage_paths


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_candidate(candidate_dir: Path, *, expected_sha: str, root: Path) -> dict[str, Any]:
    errors: list[str] = []
    diagnostics = candidate_dir / "governed_market_acquisition_diagnostics.json"
    manifest_path = candidate_dir / "publication_manifest.json"
    provenance_path = candidate_dir / "artifact_provenance.json"
    full_scan_path = candidate_dir / "market_full_scan.json"
    for path, code in (
        (diagnostics, "GOVERNED_MARKET_DIAGNOSTICS_MISSING"),
        (manifest_path, "PUBLICATION_MANIFEST_MISSING"),
        (provenance_path, "ARTIFACT_PROVENANCE_MISSING"),
        (full_scan_path, "MARKET_FULL_SCAN_MISSING"),
    ):
        if not path.is_file():
            errors.append(code)

    active_count = int(audit(root).get("PRODUCTION_ACTIVE_YAHOO_DEPENDENCY_COUNT") or 0)
    if active_count:
        errors.append("PRODUCTION_ACTIVE_YAHOO_DEPENDENCY_PRESENT")

    manifest = _read(manifest_path) if manifest_path.is_file() else {}
    provenance = _read(provenance_path) if provenance_path.is_file() else {}
    rows = _read(full_scan_path) if full_scan_path.is_file() else []
    if not isinstance(rows, list):
        errors.append("MARKET_FULL_SCAN_SCHEMA_INVALID")
        rows = []
    published_yahoo = sum(bool(disallowed_lineage_paths(row)) for row in rows if isinstance(row, dict))
    if published_yahoo:
        errors.append("PUBLISHED_YAHOO_LINEAGE_PRESENT")
    if int(manifest.get("published_yahoo_lineage_count") or 0) != published_yahoo:
        errors.append("PUBLISHED_YAHOO_LINEAGE_COUNT_MISMATCH")
    if published_yahoo and manifest.get("publication_gate_status") == "PASS":
        errors.append("YAHOO_LINEAGE_MANIFEST_FALSE_PASS")

    for document, label in ((manifest, "MANIFEST"), (provenance, "PROVENANCE")):
        if str(document.get("source_commit_sha") or "") != expected_sha:
            errors.append(f"{label}_SOURCE_SHA_MISMATCH")

    scanner_path = root / "overnight_market_scan.py"
    scanner_sha = hashlib.sha256(scanner_path.read_bytes()).hexdigest()
    if str(provenance.get("scanner_file_sha256") or "") != scanner_sha:
        errors.append("SCANNER_FILE_SHA_MISMATCH")
    if str(manifest.get("scanner_file_sha256") or "") != scanner_sha:
        errors.append("MANIFEST_SCANNER_FILE_SHA_MISMATCH")

    inventory = provenance.get("artifacts") if isinstance(provenance.get("artifacts"), dict) else {}
    actual_files = {path.name for path in candidate_dir.glob("*.json") if path.name != provenance_path.name}
    if actual_files != set(inventory):
        errors.append("CANDIDATE_ARTIFACT_INVENTORY_MISMATCH")
    for name, item in inventory.items():
        path = candidate_dir / name
        expected_hash = str(item.get("sha256") or "") if isinstance(item, dict) else ""
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            errors.append(f"ARTIFACT_HASH_MISMATCH:{name}")

    result = {
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(set(errors)),
        "expected_source_commit_sha": expected_sha,
        "artifact_source_commit_sha": provenance.get("source_commit_sha"),
        "scanner_file_sha256": scanner_sha,
        "production_active_yahoo_dependency_count": active_count,
        "published_yahoo_lineage_count": published_yahoo,
        "artifact_count": len(inventory),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--expected-sha", default=os.getenv("ATLAS_SOURCE_COMMIT_SHA", ""))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = validate_candidate(args.candidate_dir, expected_sha=args.expected_sha, root=args.root)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
