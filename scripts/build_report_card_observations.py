#!/usr/bin/env python3
"""Offline/replay entrypoint for producing a governed observation bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from services.prospective_report_card import ProspectiveLedger
from services.report_card_observation_producer import build_observation_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--market-evidence", required=True, type=Path)
    parser.add_argument("--horizon", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    evidence = json.loads(args.market_evidence.read_text(encoding="utf-8"))
    bundle = build_observation_bundle(
        ledger=ProspectiveLedger(args.ledger), evidence=evidence, horizon=args.horizon,
        certified_at=datetime.now(timezone.utc),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
