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
from services.report_card_market_evidence_acquisition import acquire_market_evidence, build_acquisition_plan
from services.report_card_exchange_calendar import verify_xnys_calendar
from scripts.certify_report_card_durable_readonly import snapshot


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_verified_backup(*, backup_root: Path, primary_tip: str) -> Path:
    """Resolve one sidecar-verified backup for the current logical ledger tip."""
    if not backup_root.is_dir():
        raise FileNotFoundError("PROTECTED_REPORT_CARD_BACKUP_ROOT_REQUIRED")
    matches: list[Path] = []
    for candidate in sorted(backup_root.glob("report-card-*.sqlite3")):
        sidecar = candidate.with_suffix(candidate.suffix + ".sha256")
        if not sidecar.is_file():
            continue
        declared = sidecar.read_text(encoding="utf-8").strip().split()[0]
        if declared != _sha256(candidate):
            continue
        if snapshot(candidate)["ledger_tip"] == primary_tip:
            matches.append(candidate)
    if not matches:
        raise FileNotFoundError("VERIFIED_REPORT_CARD_BACKUP_REQUIRED")
    if len(matches) != 1:
        raise RuntimeError("REPORT_CARD_BACKUP_IDENTITY_AMBIGUOUS")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--mode", choices=("plan", "acquire"), default="plan")
    args = parser.parse_args()
    if not args.ledger.is_file():
        raise FileNotFoundError("PROTECTED_REPORT_CARD_LEDGER_REQUIRED")
    ledger_hash_before = _sha256(args.ledger)
    ledger = ProspectiveLedger(args.ledger)
    primary_tip = ledger.verify()
    backup_ledger = resolve_verified_backup(backup_root=args.backup_root, primary_tip=primary_tip)
    if args.ledger.resolve() == backup_ledger.resolve():
        raise RuntimeError("REPORT_CARD_PRIMARY_BACKUP_NOT_DISTINCT")
    backup_hash_before = _sha256(backup_ledger)
    calendar = json.loads(args.calendar.read_text(encoding="utf-8"))
    generated_at = datetime.fromisoformat(str(calendar.get("generated_at") or ""))
    verify_xnys_calendar(calendar, as_of=generated_at)
    if args.mode == "plan":
        evidence = build_acquisition_plan(
            ledger=ledger, calendar=calendar, authorization=args.authorization,
            source_sha=args.source_sha,
        )
    else:
        provider = FinnhubShadowAdapter(license_class=FINNHUB_PAID_CORE_CERTIFICATION_LICENSE)
        evidence = acquire_market_evidence(
            ledger=ledger,
            provider=provider,
            calendar=calendar,
            now=datetime.now(timezone.utc),
            authorization=args.authorization,
            source_sha=args.source_sha,
            retry_attempts=0,
        )
    ledger_hash_after = _sha256(args.ledger)
    backup_hash_after = _sha256(backup_ledger)
    if ledger_hash_after != ledger_hash_before:
        raise RuntimeError("PROTECTED_REPORT_CARD_LEDGER_MUTATED")
    if backup_hash_after != backup_hash_before:
        raise RuntimeError("PROTECTED_REPORT_CARD_BACKUP_MUTATED")
    evidence["ledger_file_sha256"] = ledger_hash_before
    evidence["backup_file_sha256"] = backup_hash_before
    evidence["backup_file_name"] = backup_ledger.name
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
