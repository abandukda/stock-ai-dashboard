#!/usr/bin/env python3
"""Build or rehearse a bounded Research refresh without provider access."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path

from services.buy_now_history_backfill_execution import atomic_json
from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.research_refresh_execution import compile_execution_plan, rehearse
from services.research_refresh_readiness import ALLOWED_CAPABILITIES, plan_research_refresh


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "rehearse", "live"))
    parser.add_argument("--tickers", required=True, help="Comma-separated, maximum 25")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--cache-index", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--durable-root", type=Path)
    args = parser.parse_args()
    if args.mode == "live":
        parser.error("LIVE is disabled; use a separately registered protected workflow")
    cache = json.loads(args.cache_index.read_text()) if args.cache_index else {}
    entitlement = {"status": "APPROVED", "contract_id": CONTRACT_ID,
                   "capabilities": list(ALLOWED_CAPABILITIES)}
    upstream = plan_research_refresh(
        args.tickers.split(","), cache, entitlement, source_sha=args.source_sha,
        now=datetime.combine(args.as_of, datetime.min.time(), tzinfo=timezone.utc),
    )
    compiled = compile_execution_plan(upstream, as_of=args.as_of)
    atomic_json(args.output, compiled)
    if args.mode == "rehearse":
        if not args.durable_root:
            parser.error("--durable-root is required for rehearsal")
        result = rehearse(compiled, durable_root=args.durable_root)
        print(json.dumps(result.__dict__, sort_keys=True))
    else:
        print(json.dumps({"package_sha256": compiled["package_sha256"],
                          "request_count": len(compiled["requests"]),
                          "provider_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
