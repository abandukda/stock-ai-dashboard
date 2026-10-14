#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from services.report_card_exchange_calendar import build_xnys_calendar, verify_xnys_calendar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--cutoff-utc", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_cutoff = args.cutoff_utc.strip()
    if "T" not in raw_cutoff:
        parser.error("--cutoff-utc must be a timezone-aware UTC timestamp, not a date")
    try:
        parsed = datetime.fromisoformat(raw_cutoff.replace("Z", "+00:00"))
    except ValueError as exc:
        parser.error(f"--cutoff-utc is invalid: {exc}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parser.error("--cutoff-utc must include an explicit UTC offset")
    as_of = parsed.astimezone(timezone.utc)
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        parser.error("--cutoff-utc must use UTC (Z or +00:00)")
    value = build_xnys_calendar(start_date=args.start_date, as_of=as_of)
    verify_xnys_calendar(value, as_of=as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(args.output.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
