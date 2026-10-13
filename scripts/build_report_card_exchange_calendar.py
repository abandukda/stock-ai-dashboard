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
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of).astimezone(timezone.utc)
    value = build_xnys_calendar(start_date=args.start_date, as_of=as_of)
    verify_xnys_calendar(value, as_of=as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(args.output.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
