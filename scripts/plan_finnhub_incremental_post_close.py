#!/usr/bin/env python3
"""Create the authorized post-close request manifest without calling Finnhub."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.finnhub_incremental_post_close import build_incremental_plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--publication", type=Path, default=Path("market_full_scan.json"))
    parser.add_argument("--changed-symbols", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.publication.read_text(encoding="utf-8"))
    symbols = [
        str(row.get("ticker") or "") for row in rows
        if (row.get("publication_certification") or {}).get("customer_publication_allowed") is True
    ]
    changed: list[str] = []
    if args.changed_symbols:
        payload = json.loads(args.changed_symbols.read_text(encoding="utf-8"))
        changed = list(payload.get("changed_symbols") or [])
    plan = build_incremental_plan(
        session=args.session, customer_symbols=symbols,
        changed_fundamental_symbols=changed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({key: plan[key] for key in (
        "session", "provider_calls", "request_count", "exact_max_requests", "plan_sha256"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
