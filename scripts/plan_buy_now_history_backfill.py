#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.buy_now_history_continuity import build_history_backfill_plan
from services.daily_buy_now_post_close import continuity_decision
from services.finnhub_incremental_post_close import load_governed_membership


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--last-contiguous-session", required=True)
    parser.add_argument("--retained-artifact-set-sha256", required=True)
    parser.add_argument("--governed-records", type=Path, required=True)
    parser.add_argument("--governed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from datetime import datetime
    continuity = continuity_decision(
        now=datetime.fromisoformat(args.as_of.replace("Z", "+00:00")),
        last_contiguous_session=args.last_contiguous_session,
    )
    if continuity["mode"] != "BOUNDED_BACKFILL":
        raise ValueError(f"BUY_NOW_BACKFILL_NOT_REQUIRED:{continuity['mode']}")
    membership = load_governed_membership(
        records_path=args.governed_records, manifest_path=args.governed_manifest,
    )
    plan = build_history_backfill_plan(
        source_sha=args.source_sha,
        symbols=membership["tickers"],
        missing_sessions=continuity["missing_sessions"],
        membership_identity=membership,
        retained_history_identity={
            "last_contiguous_session": args.last_contiguous_session,
            "artifact_set_sha256": args.retained_artifact_set_sha256,
        },
    )
    payload = {"continuity": continuity, "backfill_plan": plan}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "plan_sha256": plan["plan_sha256"],
        "missing_sessions": continuity["missing_sessions"],
        "request_count": plan["request_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
