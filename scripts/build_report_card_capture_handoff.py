#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.report_card_capture_handoff import build_capture_handoff


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--closure", type=Path, required=True)
    parser.add_argument("--acquisition-run-id", required=True)
    parser.add_argument("--closure-run-id", required=True)
    parser.add_argument("--historical-run-identity", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-candidate-digest", required=True)
    parser.add_argument("--expected-publication-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    envelope = build_capture_handoff(
        manifest_path=args.manifest, publication_path=args.publication, closure_path=args.closure,
        expected_acquisition_run_id=args.acquisition_run_id, expected_closure_run_id=args.closure_run_id,
        expected_run_identity=args.historical_run_identity, expected_source_sha=args.expected_source_sha,
        expected_candidate_digest=args.expected_candidate_digest,
        expected_publication_digest=args.expected_publication_digest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(envelope, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
