#!/usr/bin/env python3
"""Explicitly authorized Report Card evidence acquisition entrypoint."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from services.finnhub_shadow_provider import FINNHUB_PAID_CORE_CERTIFICATION_LICENSE, FinnhubShadowAdapter
from services.prospective_report_card import ProspectiveLedger
from services.report_card_market_evidence_acquisition import acquire_market_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--authorization", required=True)
    args = parser.parse_args()
    if not args.ledger.is_file():
        raise FileNotFoundError("PROTECTED_REPORT_CARD_LEDGER_REQUIRED")
    ledger_hash_before = hashlib.sha256(args.ledger.read_bytes()).hexdigest()
    ledger = ProspectiveLedger(args.ledger)
    calendar = json.loads(args.calendar.read_text(encoding="utf-8"))
    provider = FinnhubShadowAdapter(license_class=FINNHUB_PAID_CORE_CERTIFICATION_LICENSE)
    evidence = acquire_market_evidence(
        ledger=ledger,
        provider=provider,
        calendar=calendar,
        now=datetime.now(timezone.utc),
        authorization=args.authorization,
        source_sha=args.source_sha,
    )
    ledger_hash_after = hashlib.sha256(args.ledger.read_bytes()).hexdigest()
    if ledger_hash_after != ledger_hash_before:
        raise RuntimeError("PROTECTED_REPORT_CARD_LEDGER_MUTATED")
    evidence["ledger_file_sha256"] = ledger_hash_before
    evidence_without_hash = {key: value for key, value in evidence.items() if key != "artifact_sha256"}
    canonical = json.dumps(evidence_without_hash, sort_keys=True, separators=(",", ":"), default=str)
    evidence["artifact_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(args.output.suffix + ".pending")
    pending.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
