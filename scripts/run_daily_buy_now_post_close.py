#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.daily_buy_now_post_close import (
    continuity_decision, schedule_decision, validate_retained_publication,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", required=True)
    parser.add_argument("--last-published-session", default="")
    parser.add_argument("--last-contiguous-session", default="")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Persist a sanitized fail-closed receipt even if configuration/calendar/input
    # validation stops before a schedule is available. Never serialize exception
    # text: provider/host errors may contain sensitive paths or values.
    payload = {"status": "FAILED", "provider_calls": 0, "production_writes": 0,
               "schedule": {"eligible": False}, "error": "COORDINATOR_VALIDATION_FAILED"}
    try:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        boundary = args.last_contiguous_session or args.last_published_session
        if not boundary:
            payload["error"] = "DAILY_BUY_NOW_CONTIGUOUS_BOUNDARY_REQUIRED"
            raise ValueError(payload["error"])
        decision = schedule_decision(now=now, last_published_session=args.last_published_session)
        continuity = continuity_decision(now=now, last_contiguous_session=boundary)
        dry_run = validate_retained_publication(
            root=args.root, output=args.output.parent / "provider_free_publication_validation.json"
        )
        payload = {"status": "PASS", "schedule": decision, "continuity": continuity,
                   "dry_run": dry_run, "provider_calls": 0, "production_writes": 0}
    except Exception:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(payload, sort_keys=True))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
