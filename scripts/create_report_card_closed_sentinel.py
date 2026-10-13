#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from services.report_card_closed_sentinel import create_closed_sentinel


AUTHORIZATION = "REPORT_CARD_CREATE_CLOSED_SENTINEL_ONCE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--durable-root", type=Path, required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.authorization != AUTHORIZATION:
        parser.error("exact CLOSED-sentinel authorization is required")
    evidence = create_closed_sentinel(durable_root=args.durable_root)
    evidence.update({
        "schema_version": "ATLAS_REPORT_CARD_CLOSED_SENTINEL_V1",
        "provider_calls": 0,
        "ledger_mutations": 0,
        "schedule_activated": False,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(args.output.suffix + ".pending")
    pending.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
