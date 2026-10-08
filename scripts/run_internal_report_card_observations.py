#!/usr/bin/env python3
"""Apply a pre-certified observation bundle without making provider calls."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from services.prospective_report_card import ProspectiveLedger
from services.report_card_observation_activation import apply_observation_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--backup-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    result = apply_observation_bundle(ledger=ProspectiveLedger(args.ledger), backup_root=args.backup_root,
                                      bundle=bundle, now=datetime.now(timezone.utc))
    report = {**asdict(result), "provider_calls": 0, "reacquisition": "none",
              "customer_visible": False, "public_performance_claims_allowed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
