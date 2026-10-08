#!/usr/bin/env python3
"""Create an ephemeral, non-durable Report Card fixture for browser certification."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from services.prospective_report_card import ProspectiveLedger


def prepare(primary_root: Path, backup_root: Path) -> Path:
    primary_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    ledger = ProspectiveLedger(primary_root / "report-card.sqlite3")
    now = datetime.now(timezone.utc)
    ledger.activate(activation_timestamp=now.isoformat(), now=now)
    ledger.append(
        "SIGNAL",
        "qa-fixture-signal-nvda",
        {
            "semantic_identity": "qa-fixture-buy-now-episode-nvda",
            "ticker": "NVDA",
            "company_name": "NVIDIA Corporation",
            "first_seen_at": now.isoformat(),
            "canonical_recommendation": "BUY_NOW",
            "reference_price": 186.52,
            "reference_price_timestamp": now.isoformat(),
            "atlas_fair_value": 346.05,
            "opportunity": 85.96,
            "decision_confidence": 87.46,
            "withholding_status": "CUSTOMER_PUBLISHABLE",
            "candidate_digest": "qa-fixture-candidate",
            "publication_digest": "qa-fixture-publication",
            "evaluation_snapshot_id": "qa-fixture-snapshot",
            "evidence_ids": ["qa-fixture-evidence"],
        },
        created_at=now,
    )
    ledger.verify()
    ledger.backup(backup_root, now=now)
    return ledger.path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.primary_root, args.backup_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
