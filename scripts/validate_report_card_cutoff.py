#!/usr/bin/env python3
"""Validate an explicit, timezone-aware UTC Report Card evidence cutoff."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone


def validate_cutoff(value: str) -> str:
    if not value.endswith("Z"):
        raise ValueError("REPORT_CARD_CUTOFF_MUST_BE_EXPLICIT_UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("REPORT_CARD_CUTOFF_INVALID_ISO8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("REPORT_CARD_CUTOFF_MUST_BE_EXPLICIT_UTC")
    if parsed.second or parsed.microsecond:
        raise ValueError("REPORT_CARD_CUTOFF_MUST_USE_MINUTE_PRECISION")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cutoff")
    args = parser.parse_args()
    print(validate_cutoff(args.cutoff))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
