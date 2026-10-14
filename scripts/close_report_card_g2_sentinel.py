#!/usr/bin/env python3
"""Idempotent protected-runner cleanup for the G2 acquisition sentinel."""
from __future__ import annotations

import argparse
from pathlib import Path

from services.report_card_g2_protected_transition import atomic_sentinel, verify_sentinel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sentinel", required=True, type=Path)
    args = parser.parse_args()
    atomic_sentinel(args.sentinel, "CLOSED")
    verify_sentinel(args.sentinel, "CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
