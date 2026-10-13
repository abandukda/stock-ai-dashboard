#!/usr/bin/env python3
"""Independent dead-man checker intended for a host outside GitHub Actions."""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from services.report_card_operational_controls import heartbeat_contract, heartbeat_decision, digest

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=Path, required=True)
    parser.add_argument("--expected-start", required=True)
    parser.add_argument("--now", required=True)
    parser.add_argument("--grace-minutes", type=int, default=45)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    heartbeat = json.loads(args.heartbeat.read_text()) if args.heartbeat.is_file() else {}
    parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    result = heartbeat_decision(now=parse(args.now), expected_start=parse(args.expected_start),
        started_at=parse(heartbeat.get("started_at")), completed_at=parse(heartbeat.get("completed_at")),
        completion_status=heartbeat.get("completion_status"), grace=timedelta(minutes=args.grace_minutes))
    result.update({"checked_at": parse(args.now).astimezone(timezone.utc).isoformat(),
                   "heartbeat_sha256": digest(heartbeat), "provider_calls": 0})
    result["alert_envelope"] = heartbeat_contract(
        heartbeat=heartbeat, expected_run_id=args.expected_run_id, decision=result)
    result["artifact_sha256"] = digest(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(args.output.suffix + ".pending")
    pending.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(pending, args.output)
    return 2 if result["alert_required"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
