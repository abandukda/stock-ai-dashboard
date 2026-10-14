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

from services.daily_buy_now_post_close import schedule_decision, validate_retained_publication


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", required=True)
    parser.add_argument("--last-published-session", default="")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
    decision = schedule_decision(now=now, last_published_session=args.last_published_session)
    dry_run = validate_retained_publication(
        root=args.root, output=args.output.parent / "provider_free_publication_validation.json"
    )
    payload = {"schedule": decision, "dry_run": dry_run}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
