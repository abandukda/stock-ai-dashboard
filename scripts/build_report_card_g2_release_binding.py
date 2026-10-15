#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.report_card_g2_release_binding import build_g2_release_binding


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protected-validation", type=Path, required=True)
    parser.add_argument("--entitlement", type=Path, required=True)
    parser.add_argument("--release-source-sha", required=True)
    parser.add_argument("--validation-run-id", required=True)
    parser.add_argument("--validation-artifact", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binding = build_g2_release_binding(
        protected_validation=json.loads(args.protected_validation.read_text()),
        entitlement=json.loads(args.entitlement.read_text()),
        release_source_sha=args.release_source_sha,
        validation_run_id=args.validation_run_id,
        validation_artifact=args.validation_artifact,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "package_sha256": binding["package_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
