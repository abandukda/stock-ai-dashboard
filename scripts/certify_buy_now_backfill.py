#!/usr/bin/env python3
"""Certify combined retained and licensed backfill evidence; never publish."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.buy_now_backfill_certification import (
    build_certification_inputs, combine_backfill_observations,
)
from services.incremental_provider_free_replay import resolve_replay_retained_records
from services.incremental_publication_bridge import (
    certify_incremental_candidate, load_retained_technical_history,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--original-raw-dir", type=Path, required=True)
    p.add_argument("--recovery-raw-dir", type=Path, required=True)
    p.add_argument("--retained-artifact-root", type=Path, required=True)
    p.add_argument("--retained-technical-root", type=Path, required=True)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--workflow-run-id", required=True)
    p.add_argument("--candidate-dir", type=Path, required=True)
    p.add_argument("--checkpoint-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    package = json.loads(a.package.read_text(encoding="utf-8"))
    backfill_plan = package["backfill_plan"]
    observations, unavailable, evidence = combine_backfill_observations(
        plan=backfill_plan, original_raw_dir=a.original_raw_dir,
        recovery_raw_dir=a.recovery_raw_dir,
    )
    # Use a plan-shaped membership view to resolve the exact retained 6,033-row
    # source and then project its governed 1,298 rows.
    membership_plan = {
        "request_keys": [f"{backfill_plan['range_end']}:{ticker}:completed_session_price"
                         for ticker in sorted({r['ticker'] for r in backfill_plan['requests']})],
        "governed_membership": backfill_plan["membership_identity"],
    }
    retained_rows, retained_resolution = resolve_replay_retained_records(
        artifact_root=a.retained_artifact_root, plan=membership_plan,
    )
    history_plan = {
        **membership_plan, "session": backfill_plan["range_end"],
    }
    histories, history_binding = load_retained_technical_history(
        root=a.retained_technical_root, plan=history_plan,
    )
    plan, checkpoint, records = build_certification_inputs(
        backfill_plan=backfill_plan, retained_rows=retained_rows,
        retained_histories=histories, observations=observations,
        unavailable=unavailable,
    )
    report = certify_incremental_candidate(
        plan=plan, checkpoint=checkpoint, acquired_records=records,
        source_sha=a.source_sha, candidate_dir=a.candidate_dir,
        workflow_run_id=a.workflow_run_id,
        evidence_classification="LIVE_PROVIDER_EVIDENCE",
        retained_technical_binding=history_binding,
        checkpoint_dir=a.checkpoint_dir, batch_size=64,
    )
    report["backfill_evidence_validation"] = evidence
    report["retained_record_resolution"] = retained_resolution
    report["terminal_unavailable_count"] = len(unavailable)
    report["terminal_unavailable_symbols"] = sorted(unavailable)
    report["provider_calls_during_certification"] = 0
    report["publication_writes"] = 0
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
