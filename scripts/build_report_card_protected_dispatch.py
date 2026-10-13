#!/usr/bin/env python3
"""Build an inert, exact protected-runner dispatch package for owner review."""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source-sha", required=True)
    p.add_argument("--start-date", required=True)
    p.add_argument("--as-of", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if len(a.source_sha) != 40:
        raise ValueError("SOURCE_SHA_REQUIRED")
    package = {"schema_version":"ATLAS_REPORT_CARD_PROTECTED_DISPATCH_V1",
        "workflow":"atlas_report_card_protected_runner_validation.yml", "ref_sha":a.source_sha,
        "inputs":{"authorize_validation":"OWNER_MUST_SUPPLY_REPORT_CARD_PROTECTED_VALIDATE_ONCE",
                  "start_date":a.start_date,"as_of":a.as_of},
        "provider_calls":0,"ledger_mutation_allowed":False,"dispatch_performed":False,
        "gates_opened":[]}
    package["package_sha256"] = digest(package)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    pending = a.output.with_suffix(a.output.suffix + ".pending")
    pending.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n")
    os.replace(pending, a.output)
    return 0

if __name__ == "__main__": raise SystemExit(main())
