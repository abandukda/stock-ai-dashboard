#!/usr/bin/env python3
"""Protected entrypoint for one separately authorized daily cycle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from services.finnhub_shadow_provider import FINNHUB_PAID_CORE_CERTIFICATION_LICENSE, FinnhubShadowAdapter
from services.report_card_daily_cycle import run_daily_cycle
from services.report_card_exchange_calendar import verify_xnys_calendar
from services.report_card_market_evidence_acquisition import AUTHORIZATION_TOKEN


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--alert-root", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retry-attempts", type=int, default=0)
    args = parser.parse_args()
    if os.getenv("ATLAS_REPORT_CARD_AUTOMATION_ENABLED") != "true":
        raise PermissionError("REPORT_CARD_AUTOMATION_NOT_ENABLED")
    if os.getenv("ATLAS_REPORT_CARD_KILL_SWITCH", "true") != "false":
        raise PermissionError("REPORT_CARD_AUTOMATION_KILL_SWITCH_ACTIVE")
    if args.authorization != AUTHORIZATION_TOKEN:
        raise PermissionError("REPORT_CARD_ACQUISITION_NOT_AUTHORIZED")
    calendar = json.loads(args.calendar.read_text(encoding="utf-8"))
    verify_xnys_calendar(calendar, as_of=datetime.fromisoformat(calendar["generated_at"]))
    result = run_daily_cycle(
        ledger_path=args.ledger, backup_root=args.backup_root, alert_root=args.alert_root,
        provider=FinnhubShadowAdapter(license_class=FINNHUB_PAID_CORE_CERTIFICATION_LICENSE),
        calendar=calendar, now=datetime.now(timezone.utc), authorization=args.authorization,
        source_sha=args.source_sha, retry_attempts=args.retry_attempts,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(args.output.suffix + ".pending")
    pending.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
