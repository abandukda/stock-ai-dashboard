#!/usr/bin/env python3
"""Stage an incremental candidate through the existing certified evaluator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.incremental_publication_bridge import (
    certify_incremental_candidate, load_retained_technical_history,
    materialize_acquired_records,
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--acquired-records", type=Path)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--retained-records", type=Path)
    parser.add_argument("--retained-technical-root", type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--certification-checkpoint-dir", type=Path)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--evidence-classification",
        choices=("LIVE_PROVIDER_EVIDENCE", "PROVIDER_FREE_SIMULATED_REPLAY"),
        default="LIVE_PROVIDER_EVIDENCE",
    )
    args = parser.parse_args()
    plan, checkpoint = _read(args.plan), _read(args.checkpoint)
    technical_binding = None
    if args.acquired_records:
        records = _read(args.acquired_records)
    elif args.raw_root and args.retained_records and args.retained_technical_root:
        retained = _read(args.retained_records)
        if not isinstance(retained, list):
            raise ValueError("INCREMENTAL_RETAINED_RECORDS_SCHEMA_INVALID")
        technical, technical_binding = load_retained_technical_history(
            root=args.retained_technical_root, plan=plan,
        )
        records = materialize_acquired_records(
            plan=plan, checkpoint=checkpoint, raw_root=args.raw_root,
            retained_rows=retained, retained_technical_history=technical,
            retained_technical_blockers=(technical_binding or {}).get("history_blockers"),
            consume_retained_history=True,
        )
    else:
        parser.error("provide --acquired-records or --raw-root, --retained-records and --retained-technical-root")
    if not isinstance(records, list):
        raise ValueError("INCREMENTAL_ACQUIRED_RECORDS_SCHEMA_INVALID")
    result = certify_incremental_candidate(
        plan=plan, checkpoint=checkpoint,
        acquired_records=records, source_sha=args.source_sha,
        candidate_dir=args.candidate_dir, workflow_run_id=args.workflow_run_id,
        evidence_classification=args.evidence_classification,
        retained_technical_binding=technical_binding,
        checkpoint_dir=args.certification_checkpoint_dir,
        batch_size=args.batch_size,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
